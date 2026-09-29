"""One owner thread creates and advances Env; socket handlers read snapshots only."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import pwd
import queue
import signal
import socketserver
import threading
import time
from uuid import uuid4

from topogym.utils.io import to_jsonable
from .policy_process import PolicyCancelled, RemotePolicyProxy
from .protocol import (ADMIN_SOCKET, API_VERSION, SOCKET, ProtocolError, atomic_json,
                       receive, send, validate_submit, validate_admin)
from .public_artifacts import PublicArtifacts


def policy_context(runner, instance):
    """Use the very same projection builders as execute_policy, before readiness."""
    from topogym.simulator.rollout_simulation.policy_observation import resolve_profile, build_context
    mode, fields = instance.get("mode", "limited"), instance.get("state_fields", [])
    access = runner.env.interaction(privileged=mode == "unlimited")
    profile = resolve_profile(runner.env, mode=mode, state_fields=fields,
                              settings=instance.get("observation_profile"))
    return build_context(profile, access.action_spec, access.timing_spec), profile


class RolloutSession:
    def __init__(self, runner, instance, public_root, *, proxy_factory=RemotePolicyProxy, usage_config=None):
        self.runner, self.instance, self.proxy_factory = runner, instance, proxy_factory
        self.lock = threading.RLock()
        self.pending = queue.Queue(maxsize=1)
        self.requests = {}
        self.proxy = None
        self.stop = threading.Event()
        self.closed = threading.Event()
        self.usage_config = usage_config or {"mode": "off"}
        self.budget_stop = None
        self.context, profile = policy_context(runner, instance)
        self.publisher = PublicArtifacts(runner, public_root, profile.rgb_camera_ids,
                                         state_fields=profile.state_fields)
        self.publisher.json("spec.json", self.context)
        initial = self.publisher.publish(runner.initial, initial=True)
        healthy = runner.initial["evidence_complete"] and runner.initial["reason"] in {
            "initial_observation", "env_terminal", "env_time_limit"}
        phase = ("faulted" if not healthy else
                 "terminal" if runner.env._terminated or runner.env._truncated else "ready")
        self.state = dict(api_version=API_VERSION, episode_id=runner.episode_id, phase=phase,
            active_request_id=None, initial_path=initial, spec_path=str(Path(public_root)/"spec.json"),
            artifacts_manifest=str(Path(public_root)/"public_artifacts.json"), latest_result_path=initial,
            history_path=str(Path(public_root)/"history.json"),
            stop_reason=None)
        atomic_json(runner.root / "instance.json", instance, 0o600)
        atomic_json(runner.root / "runtime.json", to_jsonable(dict(
            episode_id=runner.episode_id, task_parameters=runner.env._task.config,
            terminal_revision=runner.env._task.terminal_revision,
            timing_spec=runner.env.timing_spec, observation_profile=profile.identity())), 0o600)
        if instance.get("fixture"):
            from topogym.utils.io import sha256_file
            fixture = Path("/opt/topogym-fixtures/fixtures") / (instance["fixture"] + ".py")
            atomic_json(runner.root / "fixture_manifest.json", {
                "fixture": instance["fixture"], "sha256": sha256_file(fixture),
                "files": {name: sha256_file(fixture.parent / name) for name in
                          {fixture.name, "cube_transfer.py"}}}, 0o600)
        self._snapshot()

    def _snapshot(self):
        self.publisher.json("session.json", self.state)

    def _receipt(self, identifier, **values):
        return dict(api_version=API_VERSION, request_id=identifier,
            episode_id=self.runner.episode_id, request_status="accepted", segment_id=None,
            result_path=None, artifacts_manifest=self.state["artifacts_manifest"], error=None, **values)

    def dispatch(self, message):
        """Thread-safe; this method never queries or mutates Env."""
        with self.lock:
            if not isinstance(message, dict) or message.get("api_version") != API_VERSION:
                raise ProtocolError("unsupported_protocol")
            operation = message.get("operation")
            if operation == "status" and set(message) == {"api_version", "operation"}:
                return dict(self.state)
            if operation == "result" and set(message) == {"api_version", "operation", "request_id"}:
                record = self.requests.get(message["request_id"])
                if record is None:
                    raise ProtocolError("unknown_request")
                return dict(record["receipt"])
            if operation != "submit_policy":
                raise ProtocolError("invalid_operation")
            digest = validate_submit(message, self.runner.episode_id)
            identifier = message["request_id"]
            if identifier in self.requests:
                record = self.requests[identifier]
                if record["hash"] != digest:
                    raise ProtocolError("request_id_conflict")
                return dict(record["receipt"])
            if self.stop.is_set() or self.state["phase"] in {"terminal", "closed", "faulted"}:
                raise ProtocolError("episode_ended")
            if self.state["active_request_id"] is not None:
                raise ProtocolError("execution_busy")
            # Round trip freezes caller-owned objects before accepting.
            policy = json.loads(json.dumps(message["policy"], allow_nan=False))
            record = dict(hash=digest, policy=policy, receipt=self._receipt(identifier))
            self.requests[identifier] = record
            self.state.update(phase="executing", active_request_id=identifier)
            self._snapshot()
            self.pending.put_nowait(identifier)
            return dict(record["receipt"])

    def cancel(self, reason="manager_cancelled", *, snapshot=None):
        # Independent of the owner queue and the simulator dispatch lock.
        with self.lock:
            self.stop.set()
            if snapshot is not None and self.budget_stop is None:
                self.budget_stop = snapshot["stop"]
                atomic_json(self.runner.root / "usage_stop.json", snapshot, 0o600)
            if self.budget_stop is not None:
                reason = self.budget_stop["reason"]
            else:
                reason = self.state["stop_reason"] or reason
            self.state.update(phase="closed" if self.closed.is_set() else "closing", stop_reason=reason)
            self._snapshot()
            proxy = self.proxy
        if proxy is not None:
            proxy.cancel()

    def budget_status(self):
        # SegmentRunner marks a record finalizing BEFORE media encoding/sealing.
        # No Env calls: this distinguishes stopped compute from slow archival.
        with self.lock:
            identifier = self.state["active_request_id"]
            segment = self.runner._requests.get(identifier)
            record = self.runner._records.get(segment, {})
            stopped = identifier is None or record.get("status") in {"finalizing", "complete", "incomplete"}
            return {"execution_stopped": bool(stopped), "stop_reason": self.state["stop_reason"]}

    def execute_next(self, timeout=.1):
        """Called only by the thread that owns Env."""
        try:
            identifier = self.pending.get(timeout=timeout)
        except queue.Empty:
            return False
        record = self.requests[identifier]
        directory = self.runner.root / "submissions" / record["hash"]
        # A distinct request can submit identical source later; don't reuse process cwd.
        directory = directory / uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "submission.json", record["policy"], 0o600)
        result = None
        try:
            with self.lock:
                if self.stop.is_set():
                    raise PolicyCancelled()
                self.proxy = self.proxy_factory(record["policy"], directory / "process")
                record["receipt"]["request_status"] = "running"
            try:
                result = self.runner.run_policy(request_id=identifier, policy=self.proxy,
                    submission_hash=record["hash"], mode=self.instance.get("mode", "limited"),
                    observation_profile=self.instance.get("observation_profile"),
                    state_fields=tuple(self.instance.get("state_fields", [])))
            except PolicyCancelled:
                # Core seals the partial result before re-raising cancellation.
                identity = self.runner._requests.get(identifier)
                if identity is not None:
                    result = self.runner._records[identity]["result"]
            if result is None:
                raise RuntimeError("No sealed segment result")
            with self.lock:
                record["receipt"]["request_status"] = "publishing"
            path = self.publisher.publish(result)
            with self.lock:
                record["receipt"].update(request_status="finished", result_path=path,
                    segment_id=result["segment_id"])
                self.state["latest_result_path"] = path
                feedback = result["feedback"]
                self.state["phase"] = ("closing" if self.stop.is_set() else "faulted" if self.runner._failed
                    else "terminal" if feedback.get("task_terminated") or self.runner.env._truncated else "ready")
        except (Exception, PolicyCancelled) as error:
            with self.lock:
                record["receipt"].update(request_status="error", error={"code": "execution_failed"})
                self.state.update(phase="faulted", stop_reason=self.state["stop_reason"] or "execution_failed")
                self.stop.set()
            # Private traceback only; never leak it to the agent response.
            import traceback
            (directory / "worker_error.txt").write_text(traceback.format_exc())
        finally:
            with self.lock:
                proxy, self.proxy = self.proxy, None
            if proxy is not None:
                proxy.close()
                import shutil
                shutil.rmtree(directory / "process" / "cwd")
            with self.lock:
                self.state["active_request_id"] = None
                atomic_json(directory / "receipt.json", record["receipt"], 0o600)
                self._snapshot()
        return True

    def finish(self):
        """Owner thread, after pending/active requests have finished or been cancelled."""
        from topogym.simulator.rollout_simulation.segment_contract import public_info
        self.runner.close()
        final = to_jsonable(public_info(self.runner.env._info()))
        usage = dict(mode="off", enforcement="not_enforced", input_tokens=None, output_tokens=None)
        if self.usage_config["mode"] != "off":
            usage = dict(mode=self.usage_config["mode"], enforcement=self.usage_config["mode"],
                usage_complete=False, budget_qualified=False, failure_reason="usage_unavailable",
                input_tokens=None, output_tokens=None)
        usage_path = self.runner.root / "usage_final.json"
        if usage_path.exists():
            usage = json.loads(usage_path.read_text())
        report = dict(api_version=API_VERSION, episode_id=self.runner.episode_id,
            stop_reason=self.state["stop_reason"], final_feedback=final,
            requests=[v["receipt"] for v in self.requests.values()],
            evidence_complete=not self.runner._failed,
            usage=usage)
        atomic_json(self.runner.root / "session_final.json", report, 0o600)
        with self.lock:
            self.state.update(phase="closed", active_request_id=None)
            self._snapshot()
            self.closed.set()


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False


def serve(session, path, *, admin=False, group=None):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(10)
            try:
                message = receive(self.rfile)
                if admin:
                    validate_admin(message)
                    if message["operation"] == "budget_status":
                        send(self.wfile, session.budget_status())
                        return
                    if message["operation"] == "budget_stop":
                        session.cancel(message["snapshot"]["stop"]["reason"], snapshot=message["snapshot"])
                    else:
                        session.cancel("agent_finished" if message["operation"] == "finish" else "manager_cancelled")
                    value = {"closing": True}
                else:
                    value = session.dispatch(message)
                send(self.wfile, value)
            except (ProtocolError, ValueError, TypeError, KeyError) as error:
                send(self.wfile, dict(api_version=API_VERSION, request_status="rejected",
                    error={"code": getattr(error, "code", "invalid_request")}))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    server = Server(str(path), Handler)
    os.chmod(path, 0o600 if admin else 0o660)
    if group is not None:
        os.chown(path, 0, group)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", default="/etc/topogym/instance.json")
    parser.add_argument("--output", default="/trial/rollout")
    parser.add_argument("--public", default="/rollout")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Worker must run as root; agent and policy run under distinct unprivileged users")
    instance = json.loads(Path(args.instance).read_text())
    os.umask(0o022)
    os.chdir("/trial")  # Genesis/Nyx scratch files must never use agent-writable cwd.
    verifier_logs = Path("/logs/verifier")
    if verifier_logs.exists():
        # Preserve host ownership of the bind mount, but remove group/world write.
        # Image agent UID 10001 differs from both root and the usual host UID.
        if verifier_logs.stat().st_uid in {10001, 10002}:
            raise PermissionError("Verifier mount owner collides with an untrusted container user")
        verifier_logs.chmod(0o755)
    # Bind-mounted input is never trusted as secret storage, but its runtime copy is private.
    with ExitStack() as stack:
        if instance.get("fixture") == "cube_transfer":
            import sys
            sys.path.insert(0, "/opt/topogym-fixtures")
            from fixtures.cube_transfer import register_cube_transfer
            stack.enter_context(register_cube_transfer())
        elif instance.get("fixture") == "cube_pick_place":
            import sys
            sys.path.insert(0, "/opt/topogym-fixtures")
            from fixtures.cube_pick_place import register_cube_pick_place
            stack.enter_context(register_cube_pick_place())
        elif instance.get("fixture") is not None:
            raise ValueError("Unsupported fixture")
        from topogym import make
        from topogym.simulator import SegmentRunner
        config = dict(instance["simulator"])
        config["work_dir"] = "/trial/work"
        env = stack.enter_context(make(**config))
        env.reset(seed=config.get("seed"))
        from topogym.simulator.rollout_simulation.policy_observation import resolve_profile
        profile = resolve_profile(env, mode=instance.get("mode", "limited"),
            state_fields=instance.get("state_fields", []), settings=instance.get("observation_profile"))
        runner = stack.enter_context(SegmentRunner(env, args.output,
            initial_observation_steps=instance.get("initial_observation_steps", 5), initial_profile=profile))
        usage_path = Path("/etc/topogym/usage.json")
        usage_config = json.loads(usage_path.read_text()) if usage_path.exists() else {"mode": "off"}
        session = RolloutSession(runner, instance, args.public, usage_config=usage_config)
        account = pwd.getpwnam("agent")
        if account.pw_uid == pwd.getpwnam("policy").pw_uid:
            raise ValueError("Agent and policy users must differ")
        public = serve(session, SOCKET, group=account.pw_gid)
        admin = serve(session, ADMIN_SOCKET, admin=True)
        stack.callback(public.server_close)
        stack.callback(admin.server_close)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: session.cancel("worker_signal"))
        while not session.stop.is_set() or not session.pending.empty():
            session.execute_next()
        session.finish()
        # Keep the container alive for Harbor verifier/artifact collection. Compose
        # teardown sends SIGTERM again; exit this idle loop on that second signal.
        exit_idle = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: exit_idle.set())
        while not exit_idle.wait(1):
            pass


if __name__ == "__main__":
    main()
