"""One owned worker, private inherited pipe, bounded requests and durable receipts."""
from copy import deepcopy
from collections import deque
from dataclasses import asdict
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import threading
import time
from uuid import uuid4

from .contracts import (Budgets, METHODS, CalibrationError, OperationTimeout,
                        RequestConflict, UnsupportedCapability, WorkerLost,
                        digest, identifier, json_value)


class Supervisor:
    def __init__(self, config, output, *, kind="physics", budgets=None, worker_target=None,
                 candidate=None, startup_cancelled=None):
        if kind not in {"physics", "geometry"}:
            raise ValueError("kind must be physics or geometry")
        from .candidates import validate_candidate, candidate_config
        self.candidate = validate_candidate(candidate)
        if self.candidate:
            if kind != "physics":
                raise UnsupportedCapability("Candidates require a physics session")
            config = candidate_config(config, self.candidate)
        self.output = Path(output).absolute()
        if any(p.is_symlink() for p in (self.output, *self.output.parents)):
            raise ValueError("Development output must not traverse symlinks")
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.budgets = budgets if isinstance(budgets, Budgets) else Budgets(**(budgets or {}))
        self.session_id = uuid4().hex
        self.config = json_value(config)
        if self.config.get("seed") is None:
            self.config["seed"] = 0  # Persist a concrete seed for replay.
        self.kind = kind
        self._lock = threading.RLock()
        self._records = {}
        self._active = None
        self._last = {}
        from .profiling import TimingBook
        self._timings = TimingBook()
        self._samples = deque(maxlen=32)
        self._tracking = {}
        self._task_summary = None
        self._profile_stream = (self.output / "profile.jsonl").open("x", buffering=1)
        self._closed = False
        self._closing = False
        self._failure = None
        self._ready = threading.Event()
        self._stop_monitor = threading.Event()
        self._ctx = mp.get_context("spawn")
        parent, child = self._ctx.Pipe(duplex=True)
        self._pipe = parent
        self._cancel = self._ctx.Event()
        if worker_target is None:
            from .worker import worker_main
            worker_target = worker_main
        self._worker = self._ctx.Process(target=worker_target, args=(
            child, self._cancel, self.config, str(self.output), self.session_id, kind),
            kwargs=dict(candidate=self.candidate) if self.candidate else {}, daemon=False)
        from topogym.utils.io import write_json_atomic
        write_json_atomic(self.output / "session.json", dict(
            session_id=self.session_id, config=self.config, kind=kind, budgets=asdict(self.budgets),
            role="oracle_development", formal_qualification=False, candidate=self.candidate), mode=0o600)
        self._started = time.monotonic()
        self._worker.start()
        child.close()
        self._thread = threading.Thread(target=self._monitor, name="calibration-supervisor", daemon=True)
        self._thread.start()
        # Monitor, rather than the caller, enforces the startup deadline.
        while not self._ready.wait(.05) and time.monotonic()-self._started <= self.budgets.startup_s+5:
            if startup_cancelled is not None and startup_cancelled():
                self._fail("WorkerLost", "Candidate startup cancelled")
                break
        if not self._ready.is_set():
            self._fail("OperationTimeout", "Worker startup timed out")
        if self._failure:
            error = self._failure
            self.close()
            self._raise(error)

    def _save(self, row):
        from topogym.utils.io import write_json_atomic
        write_json_atomic(self.output / "operations" / f"{row['operation_id']}.json", row, mode=0o600)

    @staticmethod
    def _raise(error):
        classes = {cls.__name__: cls for cls in (
            CalibrationError, OperationTimeout, RequestConflict, UnsupportedCapability, WorkerLost)}
        cls = classes.get(error["type"], CalibrationError)
        raise cls(error["message"])

    def submit(self, method, params=None, *, request_id=None, timeout_s=None):
        if method not in METHODS:
            raise ValueError("Unknown development operation")
        params = json_value(params or {})
        token = identifier(request_id or uuid4().hex)
        signature = digest(dict(method=method, params=params))
        timeout = (self.budgets.policy_s if method in {"run_policy", "step_until", "run_grasp_trial", "drive_object"} else
                   self.budgets.render_s if method == "capture_frame" else self.budgets.operation_s)
        if timeout_s is not None:
            from math import isfinite
            if isinstance(timeout_s, bool) or not isfinite(timeout_s) or timeout_s <= 0:
                raise ValueError("timeout_s must be finite and positive")
            timeout = float(timeout_s)
        with self._lock:
            if token in self._records:
                if self._records[token]["signature"] != signature:
                    raise RequestConflict("request_id reused with a different operation")
                return token
            if self._closed or self._failure:
                raise WorkerLost("Session closed or worker lost; restart explicitly")
            if self._active is not None:
                raise CalibrationError("Worker busy; status/cancel remain available")
            self._cancel.clear()
            row = dict(operation_id=token, method=method, params=params, signature=signature,
                       status="running", started=time.monotonic(), timeout_s=timeout,
                       session_id=self.session_id)
            self._save(row)  # Write-ahead receipt precedes pipe delivery.
            self._records[token] = row
            self._active = token
            try:
                self._pipe.send(dict(operation_id=token, method=method, params=params,
                                     session_id=self.session_id))
            except (EOFError, BrokenPipeError, OSError) as error:
                self._fail("WorkerLost", str(error))
            return token

    def wait(self, operation_id, *, timeout_s=None):
        start = time.monotonic()
        while True:
            with self._lock:
                row = deepcopy(self._records[operation_id])
            if row["status"] != "running":
                if "error" in row:
                    self._raise(row["error"])
                return row["result"]
            if timeout_s is not None and time.monotonic() - start >= timeout_s:
                raise TimeoutError(f"Still running: {operation_id}; query status before retrying")
            self._stop_monitor.wait(.025)

    def call(self, method, params=None, **options):
        return self.wait(self.submit(method, params, **options))

    def status(self, operation_id=None):
        with self._lock:
            if operation_id is not None:
                row = deepcopy(self._records[operation_id])
                if row["status"] == "running":
                    row["progress"] = self._progress()
                return row
            return dict(session_id=self.session_id, pid=self._worker.pid,
                        worker_alive=self._worker.is_alive(), active=self._active,
                        progress=self._progress(), failure=self._failure, closed=self._closed)

    def _progress(self):
        result = deepcopy(self._last)
        measured = self._timings.progress()
        result.update({key: value for key, value in measured.items() if value is not None})
        result["last_saved_state"] = deepcopy(self._last.get("state_ref"))
        result["tracking"] = deepcopy(self._tracking)
        result["task_summary"] = deepcopy(self._task_summary)
        return result

    def timings(self):
        with self._lock:
            return self._timings.snapshot()

    def _save_timings(self):
        from topogym.utils.io import write_json_atomic
        write_json_atomic(self.output / "timings.json", self._timings.snapshot(), mode=0o600)
        self._profile_stream.flush()
        os.fsync(self._profile_stream.fileno())

    def _failure_window(self, failure=None):
        from topogym.utils.io import write_json_atomic
        pending = {}
        path = self.output / "events.jsonl"
        if path.exists():
            with path.open() as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        break  # Only a fully written event is committed.
                    key = row.get("window_id")
                    if row["kind"] == "event_window_triggered":
                        pending[key] = row
                    elif row["kind"] == "event_window_progress" and key in pending:
                        pending[key]["after"].append(row["after"])
                    elif row["kind"] in {"event_window", "event_window_incomplete"}:
                        pending.pop(key, None)
        write_json_atomic(self.output / "failure_window.json", dict(
            failure=failure or self._failure, progress=self._progress(), before=list(self._samples),
            pending_windows=list(pending.values()), after=[], after_available=False,
            scope="committed control-boundary numerical summaries; not native checkpoints or fabricated post-failure states",
            physics_evidence="execution/private/physics_states.jsonl"), mode=0o600)

    def cancel(self, operation_id=None):
        with self._lock:
            if operation_id is not None and operation_id != self._active:
                raise CalibrationError("Operation is not active")
            self._cancel.set()
            return dict(requested=True, operation_id=self._active,
                        boundary="next control step or probe sample; native calls may require watchdog termination")

    def _terminate(self):
        # Only this spawned process and its own session's descendants.
        process = self._worker
        if process.is_alive():
            try:
                if os.name == "posix" and os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
            process.join(timeout=1)
            if process.is_alive():
                try:
                    if os.name == "posix" and os.getpgid(process.pid) == process.pid:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                process.join(timeout=1)

    def _fail(self, kind, message):
        with self._lock:
            if self._failure is not None:
                return
            self._failure = dict(type=kind, message=message)
            if self._active is not None:
                row = self._records[self._active]
                row.update(status="failed", error=self._failure, completed=time.monotonic(),
                           last_progress=self._progress(), replay_uncommitted_action=False)
                self._save(row)
                self._active = None
            from topogym.utils.io import write_json_atomic
            write_json_atomic(self.output / "worker_failure.json", self._failure, mode=0o600)
            self._save_timings()
            self._ready.set()
        self._terminate()
        self._failure_window()

    def _monitor(self):
        import psutil
        sampled = 0.
        try:
            with (self.output / "resources.jsonl").open("x") as resources:
                while not self._stop_monitor.is_set():
                    if self._pipe.poll(.05):
                        message = self._pipe.recv()
                        with self._lock:
                            kind = message["kind"]
                            if kind in {"span_begin", "span_end"}:
                                self._profile_stream.write(json.dumps(message) + "\n")
                                self._timings.accept(message)
                            elif kind == "control_sample":
                                self._samples.append(message["sample"])
                            elif kind == "tracking_summary":
                                self._tracking[message["summary"]["tracking_id"]] = message["summary"]
                            elif kind == "task_summary":
                                self._task_summary = message["summary"]
                            elif kind == "ready":
                                self._last = message["progress"]
                                self._save_timings()
                                self._ready.set()
                            elif kind == "progress":
                                self._last = message["progress"]
                            elif kind == "startup_error":
                                self._fail(message["error"]["type"], message["error"]["message"])
                                return
                            elif kind == "result":
                                row = self._records[message["operation_id"]]
                                row.update(completed=time.monotonic(), status="failed" if "error" in message else "complete")
                                row.update({k: message[k] for k in ("error", "result") if k in message})
                                self._save(row)
                                self._active = None
                                self._save_timings()
                                if "error" in message:
                                    self._failure_window(message["error"])
                    now = time.monotonic()
                    with self._lock:
                        active = deepcopy(self._records.get(self._active))
                        closing = self._closed
                    if now - sampled >= 1:
                        memory = psutil.virtual_memory().percent
                        resources.write(json.dumps(dict(time=time.time(), cpu_percent=psutil.cpu_percent(),
                                                        memory_percent=memory, progress=self._progress())) + "\n")
                        resources.flush()
                        from topogym.utils.io import write_json_atomic
                        write_json_atomic(self.output / "progress.json", self._progress(), mode=0o600)
                        sampled = now
                        if memory >= self.budgets.memory_percent:
                            self._fail("WorkerLost", f"System memory {memory}% reached worker stop threshold")
                            return
                    stalled = self._timings.expired_step(self.budgets.physics_step_s, now)
                    if stalled:
                        target = stalled['metadata'].get('target_physics_step', stalled['metadata'].get('target_native_frame'))
                        self._fail("OperationTimeout", f"{stalled['stage']} {target} "
                                   f"exceeded physics_step_s={self.budgets.physics_step_s}; worker terminated")
                        return
                    if active and now - active["started"] > active["timeout_s"]:
                        self._fail("OperationTimeout", f"{active['method']} exceeded {active['timeout_s']}s; worker terminated")
                        return
                    if not self._ready.is_set() and now - self._started > self.budgets.startup_s:
                        self._fail("OperationTimeout", "Worker startup exceeded budget")
                        return
                    if not self._worker.is_alive() and not closing and not self._closing:
                        self._fail("WorkerLost", f"Worker exited ({self._worker.exitcode})")
                        return
        except (EOFError, OSError) as error:
            if not self._closed and not self._closing:
                self._fail("WorkerLost", f"Private pipe closed: {error}")
        except Exception as error:
            self._fail("WorkerLost", f"Supervisor failed: {type(error).__name__}: {error}")

    def close(self):
        if self._closed:
            return
        self._closing = True
        if self._active is not None and self._failure is None:
            self._fail("WorkerLost", "Session closed during an operation; uncommitted work was discarded")
        if self._active is None and self._failure is None:
            try:
                self.call("close", timeout_s=10.)
            except CalibrationError:
                pass
        self._closed = True
        self._stop_monitor.set()
        self._terminate()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)
        self._pipe.close()
        self._profile_stream.close()
