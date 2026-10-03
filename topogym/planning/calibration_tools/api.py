"""Source-workspace API. No Env/Interaction conversion or public RPC endpoint."""
from pathlib import Path
from uuid import uuid4

from .contracts import METHODS, CalibrationError, json_value


def open_session(config, output=None, *, kind="physics", budgets=None, candidate=None):
    from .supervisor import Supervisor
    # Config is data, never an Env or an operator handle.
    values = json_value(config)
    if not isinstance(values, dict):
        raise TypeError("config must be SimulatorConfig or a configuration mapping")
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        raise PermissionError("Calibration tools require the trusted source workspace")
    output = output or root / "runs/oracle_dev" / uuid4().hex
    return CalibrationSession(Supervisor(values, output, kind=kind, budgets=budgets, candidate=candidate))


class CalibrationSession:
    def __init__(self, supervisor):
        self._supervisor = supervisor

    @property
    def output(self):
        return self._supervisor.output

    def submit(self, method, *, request_id=None, timeout_s=None, **params):
        return self._supervisor.submit(method, params, request_id=request_id, timeout_s=timeout_s)

    def wait(self, operation_id, *, timeout_s=None):
        return self._supervisor.wait(operation_id, timeout_s=timeout_s)

    def status(self, operation_id=None):
        return self._supervisor.status(operation_id)

    def timings(self):
        """Read completed spans from the parent, including during native stalls."""
        return self._supervisor.timings()

    def compare_runs(self, directories):
        """Read saved reports without sending a request to the physics worker."""
        from .run_comparison import compare_runs
        return compare_runs(directories)

    def drive_object(self, entity, *, request_id=None, **options):
        """Async bounded external-force exploration in an explicitly prepared IPC session."""
        return self.submit("drive_object", entity=entity, request_id=request_id, **options)

    def pause(self):
        return self._supervisor.cancel()

    def cancel(self, operation_id=None):
        return self._supervisor.cancel(operation_id)

    def run_policy(self, policy, *, max_control_steps=100, request_id=None, **options):
        """Async. policy = {path, factory, kwargs}; trusted code, not agent input."""
        return self.submit("run_policy", policy=policy, max_control_steps=max_control_steps,
                           request_id=request_id, **options)

    def run_grasp_trial(self, trial, *, request_id=None, **options):
        """Async execution of declared approach/close/lift/hold/release actions."""
        return self.submit("run_grasp_trial", trial=trial, request_id=request_id, **options)

    def restart(self, *, replay_to=None):
        """New worker/session; replay only receipts of fully committed actions."""
        from .supervisor import Supervisor
        old = self._supervisor
        # Journal remains usable after an unexpected native-process exit.
        import json
        events = []
        journal = old.output / "events.jsonl"
        if journal.exists():
            for line in journal.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    break  # A final torn record is uncommitted, never guessed.
        actions = []
        for row in events:
            if row["kind"] == "control_committed":
                actions.append(row["action"])
            elif row["kind"] == "restore_committed":
                actions = actions[:row["action_count"]]
        if replay_to is not None:
            if type(replay_to) is not int or not 0 <= replay_to <= len(actions):
                raise ValueError("replay_to must address a committed control-action prefix")
            actions = actions[:replay_to]
        else:
            actions = []
        if actions and any(row["kind"] == "object_drive_started" for row in events):
            raise CalibrationError("Action-only replay cannot reproduce external object forces; start a fresh drive run explicitly")
        if any(row["kind"] == "policy_loaded" for row in events) and actions:
            # Action replay restores physics, not arbitrary generator/policy state.
            policy_restored = False
        else:
            policy_restored = None
        old.close()
        self._supervisor = Supervisor(old.config, old.output.parent / (old.output.name + "_restart_" + uuid4().hex[:8]),
                                      kind=old.kind, budgets=old.budgets, candidate=old.candidate)
        try:
            if actions:
                original = json.loads((old.output / "source_manifest.json").read_text())
                current = json.loads((self.output / "source_manifest.json").read_text())
                if original != current:
                    raise CalibrationError("Source changed since the original run; action replay is refused")
            for i, action in enumerate(actions):
                result = self.step(action=action, request_id=f"replay-{i}")
                if result["control_steps"] != 1 or not result["control_step_complete"]:
                    raise CalibrationError("Action prefix replay failed; consult the new session evidence")
        except Exception:
            self.close()
            raise
        return dict(session_id=self.status()["session_id"], replayed_control_steps=len(actions),
                    policy_state_restored=policy_restored, probe_edits_restored=False,
                    scope="reconstructed action prefix; not a portable native checkpoint",
                    output=str(self.output))

    def __getattr__(self, name):
        if name in METHODS - {"run_policy", "close"}:
            def call(*args, request_id=None, timeout_s=None, **params):
                # Named convenience arguments without accepting arbitrary executable payloads.
                positional = {
                    "inspect": ("entity",), "contacts": ("entities",), "capture_frame": ("camera",),
                    "checkpoint": ("name",), "restore": ("checkpoint",), "step": ("action",),
                    "watch": ("events",), "unwatch": ("watch_id",), "step_until": ("event",),
                    "set_object_pose": ("entity", "pose"), "set_relative_pose": ("entity", "reference", "pose"),
                    "pin_object": ("entity",), "unpin_object": ("entity",),
                    "set_probe_grasp": ("hand", "entity", "transform"), "sweep_object": ("entity", "poses"),
                    "solve_ik": ("targets", "seeds"), "check_robot_path": ("path",),
                    "rank_grasps": ("candidates",), "preview_geometry": ("parameters",),
                    "compare_geometry": ("a", "b"), "export_geometry_patch": ("candidate",),
                    "tracking_report": ("tracking_id",), "stop_tracking": ("tracking_id",),
                    "cache_plan": ("plan_bundle",), "check_cached_plan": ("plan_id", "tolerances", "adapter"),
                    "prepare_plan": ("request", "adapter"),
                    "grasp_status": ("hand",), "grasp_trial_report": ("trial_id",),
                    "contact_details": ("entities",), "gripper_geometry": ("hand",),
                }.get(name, ())
                if len(args) > len(positional) or set(positional[:len(args)]) & params.keys():
                    raise TypeError(f"Invalid arguments for {name}")
                params.update(zip(positional, args))
                return self._supervisor.call(name, params, request_id=request_id, timeout_s=timeout_s)
            return call
        raise AttributeError(name)

    def close(self):
        self._supervisor.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
