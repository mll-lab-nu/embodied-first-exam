"""Serial, cancellable comparisons; each candidate owns a fresh supervised worker."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import threading
import time

from .candidates import candidate_config, candidate_trial, validate_candidate
from .contracts import CalibrationError, UnsupportedCapability, digest, json_value, positive_int
from .grasp_trials import normalize_trial
from topogym.utils.io import write_json_atomic


def open_grasp_sweep(config, trial, candidates, output, *, seeds=None, budgets=None, continue_on_error=True):
    """Start a serial background comparison. Use wait/status/cancel or a with block."""
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        raise PermissionError("Calibration sweeps require the trusted source workspace")
    return GraspSweep(config, trial, candidates, output, seeds=seeds, budgets=budgets,
                      continue_on_error=continue_on_error)


class GraspSweep:
    def __init__(self, config, trial, candidates, output, *, seeds=None, budgets=None,
                 continue_on_error=True, _session_factory=None):
        self.config, self.trial = json_value(config), normalize_trial(trial)
        if not isinstance(candidates, (list, tuple)):
            raise ValueError("candidates must be a list")
        positive_int(len(candidates), "candidate count", 128)
        candidates = [validate_candidate(c) for c in candidates]
        names = [c.get("name", f"candidate_{i:03d}") for i, c in enumerate(candidates)]
        if len(set(names)) != len(names):
            raise ValueError("Candidate names must be unique")
        if seeds is None:
            seeds = [self.config.get("seed") if self.config.get("seed") is not None else 0]
        if not isinstance(seeds, (list, tuple)) or not seeds or len(set(seeds)) != len(seeds) or any(
                type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds):
            raise ValueError("seeds must be distinct valid integer seeds")
        positive_int(len(candidates)*len(seeds), "total runs", 128)
        if type(continue_on_error) is not bool:
            raise ValueError("continue_on_error must be boolean")
        from .contracts import Budgets
        self.budgets = budgets if isinstance(budgets, Budgets) else Budgets(**(budgets or {}))
        self.cases = []
        for name, candidate in zip(names, candidates):
            for seed in seeds:
                cfg = candidate_config(dict(self.config, seed=seed), candidate)
                spec = candidate_trial(self.trial, candidate)
                self.cases.append(dict(index=len(self.cases), name=name, seed=seed,
                    candidate=candidate, candidate_id=digest(candidate), config=cfg, trial=spec,
                    action_hash=digest(spec["phases"]), status="pending"))
        self.output = Path(output).absolute()
        if any(p.is_symlink() for p in (self.output, *self.output.parents)):
            raise ValueError("Sweep output must not traverse symlinks")
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        self._lock, self._cancelled = threading.RLock(), threading.Event()
        self._session, self._source = None, None
        self._factory, self.continue_on_error = _session_factory, continue_on_error
        self._status, self._active = "running", None
        self._started = time.monotonic()
        self._save()
        self._thread = threading.Thread(target=self._run, name="calibration-grasp-sweep", daemon=False)
        self._thread.start()

    def _new_session(self, config, output, candidate):
        if self._factory is not None:
            return self._factory(config, output, candidate)
        from .api import CalibrationSession
        from .supervisor import Supervisor
        return CalibrationSession(Supervisor(config, output, budgets=self.budgets,
            candidate=candidate, startup_cancelled=self._cancelled.is_set))

    def _save(self):
        write_json_atomic(self.output / "sweep.json", dict(status=self._status, active=self._active,
            base_config=self.config, base_trial=self.trial, cases=self.cases,
            formal_qualification=False, source_identity=self._source,
            elapsed_wall_s=time.monotonic()-self._started,
            comparison_scope="independent rebuilt episodes; compare recorded seeds, action hashes and parameter differences"), mode=0o600)
        columns = ["name", "seed", "status", "criteria_passed", "maximum_lift_m", "minimum_hold_lift_m",
                   "maximum_hold_slip_m", "longest_qualified_hold_s", "minimum_volume_ratio", "wall_s", "output", "recording"]
        rows = []
        for case in self.cases:
            result = case.get("result", {})
            values = dict(case, **result.get("metrics", {}), wall_s=result.get("wall_s"), recording=result.get("recording"))
            rows.append({key: values.get(key) for key in columns})
        path = self.output / "comparison.csv"
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, columns)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)

    def _run(self):
        try:
            for case in self.cases:
                if self._cancelled.is_set():
                    break
                output = self.output / f"{case['index']:03d}_{case['name']}_seed{case['seed']}"
                with self._lock:
                    self._active = case["index"]
                    case.update(status="starting", output=str(output))
                    self._save()
                session = None
                try:
                    session = self._new_session(case["config"], output, case["candidate"])
                    with self._lock:
                        self._session = session
                    manifest = json.loads((output / "source_manifest.json").read_text())
                    source = digest(manifest)
                    with self._lock:
                        if self._source is None:
                            self._source = source
                        elif source != self._source:
                            raise CalibrationError("Source changed between candidates; comparison stopped")
                        if self._cancelled.is_set():
                            case["status"] = "cancelled"
                            break
                        case.update(status="running", source_identity=source)
                        self._save()
                    result = session.wait(session.run_grasp_trial(case["trial"]))
                    with self._lock:
                        case.update(status=result["status"], result=result)
                        for filename, key in [("candidate.json", "effective_candidate"), ("timings.json", "timings")]:
                            if (output / filename).exists():
                                case[key] = json.loads((output / filename).read_text())
                        self._save()
                    if not self.continue_on_error and result["status"] != "completed":
                        break
                except Exception as error:
                    with self._lock:
                        case.update(status="cancelled" if self._cancelled.is_set() else
                            "unsupported" if isinstance(error, UnsupportedCapability) else "failed",
                            error=dict(type=type(error).__name__, message=str(error)))
                        reports = sorted(output.glob("grasp_trials/*/report.json"))
                        if reports:
                            case["partial_trial"] = json.loads(reports[-1].read_text())
                        self._save()
                    if not self.continue_on_error or "Source changed between candidates" in str(error):
                        break
                finally:
                    if session is not None:
                        session.close()
                    with self._lock:
                        self._session = None
            with self._lock:
                self._status = "cancelled" if self._cancelled.is_set() else (
                    "completed" if all(c["status"] == "completed" for c in self.cases) else "incomplete")
        except Exception as error:
            with self._lock:
                self._status = "failed"
                write_json_atomic(self.output / "sweep_error.json", dict(type=type(error).__name__, message=str(error)))
        finally:
            with self._lock:
                self._active = None
                self._save()

    def status(self):
        with self._lock:
            result = dict(status=self._status, active=self._active,
                completed=sum(c["status"] == "completed" for c in self.cases), total=len(self.cases),
                cases=[{k: c[k] for k in ("name", "seed", "status")} for c in self.cases],
                report=str(self.output / "sweep.json"), comparison=str(self.output / "comparison.csv"))
            session = self._session
        if session is not None:
            result["worker"] = session.status()
        return result

    def wait(self, *, timeout_s=None):
        if timeout_s is not None and (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
                or not 0 < timeout_s < float("inf")):
            raise ValueError("timeout_s must be finite and positive")
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            raise TimeoutError("Sweep still running; query status or cancel")
        return json.loads((self.output / "sweep.json").read_text())

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            session = self._session
        if session is not None:
            session.cancel()
        return self.status()

    def close(self):
        if self._thread.is_alive():
            self.cancel()
            with self._lock:
                session = self._session
            if session is not None:
                session.close()
            self._thread.join()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
