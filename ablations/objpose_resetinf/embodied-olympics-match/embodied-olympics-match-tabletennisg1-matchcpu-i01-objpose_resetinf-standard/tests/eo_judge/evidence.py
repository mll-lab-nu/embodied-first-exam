"""Read one Run's sealed evidence into an Evidence object (pure reading: no network, no machine state).

Three layouts are read, all into the same object:

  eo-run/1        a Run directory written by the Runner (framework/run): run.json (eo-run/1), evidence.json
                  (eo-evidence/1: the sealed items and what is missing), fixture.json (eo-fixture/1) and the Task
                  release files under task/ (taskspec.json, instruction.md, manifest.lock.json, release.json). Every
                  item is read through evidence.json and its digest checked.
  harbor-trial    a trial directory of the legacy runners (Harbor jobs/<job>/<trial>/): artifacts/data/{final.json,
                  episode.jsonl, replay_check.json, think_calls_<seat>.jsonl, think_usage_<seat>.json}, result.json,
                  matchrun.json, config.json. The verifier's outputs (verifier/verdict.json, reward.json) are never
                  read: an earlier judgement is not evidence.
  verifier        the legacy verifier sandbox: the sim's artifacts in DATA (/data) and the task's tests/ (taskspec.json,
                  contract.json) next to the entry script.

Item names follow fwspec evidence.schema.yaml: world_report, episode, replay_check, gateway.<seat>,
gateway_usage.<seat>, platform_events, run_record, fingerprint, integrity, carry.<seat>.in / .out, reviews.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import canon

# episode rows the judge reads (the rest stays in the file, which is sealed by its digest)
EPISODE_KINDS = ("header", "session", "t0", "match_start", "run", "unit_over", "ready", "review", "ready_refused",
                 "forfeit", "retire", "end", "error", "plugin_fault", "fault", "match_timeout", "wall_cap",
                 "start_timeout", "collect_before_start", "seat_status", "cmd", "resign", "exit", "harness_exit",
                 "turn", "start", "integrity", "review_missing", "referee_retired")
_EV = re.compile(rb'"ev":\s*"([A-Za-z0-9_]+)"')


@dataclass
class Evidence:
    root: Path
    layout: str                                   # eo-run/1 | harbor-trial | verifier
    run: dict = field(default_factory=dict)       # eo-run/1 record ({} for the legacy layouts)
    fixture: dict | None = None
    task: dict = field(default_factory=dict)      # kind, taskspec, taskspec_bytes, instruction, lock, release, contract
    world: dict | None = None                     # eo-world-report/1, or the legacy final.json (ro-final/1)
    world_kind: str | None = None
    replay: dict | None = None
    episode: list = field(default_factory=list)
    episode_read: bool = False
    gateway: dict = field(default_factory=dict)   # seat -> [call record]
    usage: dict = field(default_factory=dict)     # seat -> usage counters
    platform: dict = field(default_factory=dict)  # {"trial_exception", "seat_exceptions": {seat: type}, "events": []}
    legacy: dict = field(default_factory=dict)    # matchrun.json, config.json (legacy layouts only)
    items: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    tampered: list = field(default_factory=list)  # items whose file no longer has the sealed digest
    sport_hook: Path | None = None                # the sport's scoring hook (legacy tests/sport_grade.py), if sealed
    preflight: dict | None = None                 # eo-preflight/1 (Run directory layout)
    fingerprint: dict = field(default_factory=dict)  # fingerprint.json: the Runner's whole execution fingerprint

    @property
    def evidence_digest(self) -> str:
        """sha256(JCS({items, missing})) (evidence.schema.yaml); computed when the Runner sealed nothing."""
        sealed = self.run.get("evidence", {}).get("digest") if self.layout == "eo-run/1" else None
        return sealed or canon.digest({"items": self.items, "missing": self.missing})

    def item(self, name: str) -> dict | None:
        return next((i for i in self.items if i["name"] == name), None)


# ---------------------------------------------------------------------------------------------- reading helpers
def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_episode(path: Path, kinds=EPISODE_KINDS) -> list:
    """The episode rows of the kinds the judge reads, in file order (a torn last line is skipped)."""
    want = {k.encode() for k in kinds}
    rows = []
    with open(path, "rb") as f:
        for line in f:
            m = _EV.search(line[:200])
            if not m or m.group(1) not in want:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def read_jsonl(path: Path) -> list:
    out = []
    with open(path, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _add(ev: Evidence, name: str, path: Path, producer: str, trust: str) -> None:
    ev.items.append({"name": name, "path": str(path.relative_to(ev.root)) if _under(path, ev.root) else path.name,
                     "digest": canon.file_digest(path), "bytes": path.stat().st_size, "producer": producer,
                     "trust": trust})


def _under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _seats_of(world: dict | None) -> list:
    if not world:
        return []
    cfg = world.get("cfg") or {}
    if cfg.get("seats"):
        return list(cfg["seats"])
    return sorted((world.get("seats") or {}).keys())


def _gateway_files(data: Path, seats: list) -> dict:
    """seat -> (calls file, usage file) of the legacy metering proxy (think_calls_<seat>.jsonl, or the single-seat
    think_calls.jsonl)."""
    out = {}
    for s in seats:
        c, u = data / f"think_calls_{s}.jsonl", data / f"think_usage_{s}.json"
        if not c.exists() and len(seats) == 1:
            c, u = data / "think_calls.jsonl", data / "think_usage.json"
        out[s] = (c, u)
    return out


# ---------------------------------------------------------------------------------------------- legacy layouts
def _load_legacy_data(ev: Evidence, data: Path, alt: Path | None = None) -> None:
    def pick(name):
        p = data / name
        if not p.exists() and alt is not None and (alt / name).exists():
            p = alt / name
        return p
    fin = pick("final.json")
    if fin.exists():
        ev.world = _json(fin)
        ev.world_kind = (ev.world or {}).get("schema") or "ro-final/1"
        _add(ev, "world_report", fin, "host", "observed")
    else:
        ev.missing.append({"name": "world_report", "reason": "no final.json (the match service wrote none)"})
    epi = pick("episode.jsonl")
    if epi.exists():
        ev.episode = read_episode(epi)
        ev.episode_read = True
        _add(ev, "episode", epi, "host", "observed")
    elif ev.world is not None:
        ev.missing.append({"name": "episode", "reason": "no episode.jsonl"})
    rc = pick("replay_check.json")
    if rc.exists():
        ev.replay = _json(rc)
        _add(ev, "replay_check", rc, "replay", "observed")
    elif ev.world is not None and ev.world.get("finalized") and not (
            ev.world.get("graded_by") == "live" and ev.world.get("verdict_replay") is False):   # Embodied First Exam
        ev.missing.append({"name": "replay_check", "reason": "no replay_check.json"})
    seats = _seats_of(ev.world)
    modes = (ev.world or {}).get("player_modes") or {}
    for s, (c, u) in _gateway_files(data, seats).items():
        if c.exists():
            ev.gateway[s] = read_jsonl(c)
            _add(ev, f"gateway.{s}", c, "gateway", "observed")
        elif modes.get(s) == "model":
            ev.missing.append({"name": f"gateway.{s}", "reason": "no gateway log for a model seat"})
        if u.exists():
            ev.usage[s] = _json(u) or {}
            _add(ev, f"gateway_usage.{s}", u, "gateway", "observed")


def load_harbor_trial(trial: Path) -> Evidence:
    """A legacy Harbor trial directory (jobs/<job>/<trial>/)."""
    trial = Path(trial)
    ev = Evidence(root=trial, layout="harbor-trial")
    _load_legacy_data(ev, trial / "artifacts" / "data", alt=trial / "verifier")
    res = trial / "result.json"
    if res.exists():
        r = _json(res) or {}
        _add(ev, "platform_events", res, "backend", "observed")
        ev.platform = harbor_events(r)
    mr = trial / "matchrun.json"
    if mr.exists():
        ev.legacy["matchrun"] = _json(mr) or {}
        _add(ev, "run_record", mr, "runner", "observed")
    cfg = trial / "config.json"
    if cfg.exists():
        ev.legacy["config"] = _json(cfg) or {}
    ev.task = {"kind": None, "taskspec": None, "taskspec_bytes": None, "instruction": None, "lock": None,
               "release": None, "contract": None}
    return ev


def load_verifier(data: Path, tests: Path) -> Evidence:
    """The legacy verifier sandbox: DATA (/data) and the task's tests/ directory: the runtime TaskSpec the match
    service read (tests/taskspec.json), and, for a generated Task (gen-2), the Task's identity files in tests/task/
    (taskspec.json eo-taskspec/1, instruction.md, manifest.lock.json, release.json)."""
    data, tests = Path(data), Path(tests)
    ev = Evidence(root=data, layout="verifier")
    _load_legacy_data(ev, data)
    task = {"kind": None, "taskspec": None, "taskspec_bytes": None, "instruction": None, "lock": None,
            "release": None, "contract": None, "runtime_taskspec_bytes": None, "dir": None}
    ts = tests / "taskspec.json"
    if ts.exists():
        raw = ts.read_bytes()
        task["runtime_taskspec_bytes"] = task["taskspec_bytes"] = raw
        try:
            task["taskspec"] = json.loads(raw)
            task["kind"] = task["taskspec"].get("schema")
        except ValueError:
            pass
        ev.items.append({"name": "task.taskspec", "path": "tests/taskspec.json", "digest": canon.bytes_digest(raw),
                         "bytes": len(raw), "producer": "runner", "trust": "observed"})
    ident = tests / "task"
    if (ident / "taskspec.json").is_file():                 # the Task's identity (IMPL-TASK gen-2 tasks)
        v1 = task_files(ident)
        v1.pop("sport_hook", None)
        task.update({k: v for k, v in v1.items() if k != "contract" or v is not None})
        task["dir"] = str(ident)
        for name in ("taskspec.json", "instruction.md", "manifest.lock.json", "release.json"):
            if (ident / name).is_file():
                ev.items.append({"name": f"task.{name}", "path": f"tests/task/{name}",
                                 "digest": canon.file_digest(ident / name), "bytes": (ident / name).stat().st_size,
                                 "producer": "runner", "trust": "observed"})
    ct = tests / "contract.json"
    if ct.exists():
        task["contract"] = _json(ct)
        ev.items.append({"name": "task.contract", "path": "tests/contract.json", "digest": canon.file_digest(ct),
                         "bytes": ct.stat().st_size, "producer": "runner", "trust": "observed"})
    hook = tests / "sport_grade.py"
    if hook.exists():
        ev.sport_hook = hook
        ev.items.append({"name": "task.scoring_hook", "path": "tests/sport_grade.py",
                         "digest": canon.file_digest(hook), "bytes": hook.stat().st_size, "producer": "runner",
                         "trust": "observed"})
    ev.task = task
    return ev


def harbor_events(result: dict) -> dict:
    """Platform events of a Harbor trial result: the trial's exception and each seat's (type names only)."""
    out = {"trial_exception": None, "seat_exceptions": {}, "events": [],
           "seats": sorted(((result or {}).get("seats") or {}).keys())}
    ex = (result or {}).get("exception_info") or {}
    if ex.get("exception_type"):
        out["trial_exception"] = {"type": ex.get("exception_type"), "message": str(ex.get("exception_message"))[:300]}
    for s, r in ((result or {}).get("seats") or {}).items():
        sx = (r or {}).get("exception_info") or {}
        if sx.get("exception_type"):
            out["seat_exceptions"][s] = {"type": sx["exception_type"],
                                         "message": str(sx.get("exception_message"))[:300],
                                         "setup_done": bool(((r or {}).get("agent_setup") or {}).get("finished_at"))}
    return out


# ---------------------------------------------------------------------------------------------- eo-run/1 layout
def load_run_dir(run_dir: Path, *, run: dict | None = None, manifest: dict | None = None,
                 fixture: dict | None = None, task=None) -> Evidence:
    """A Run directory of the Runner (framework/run): run.json + evidence.json (+ fixture.json, task/). The Runner may
    hand its in-memory records instead (`run`, `manifest` = the evidence record, `fixture`, `task` = its Task view):
    the same records it writes there. The Fixture is the sealed fixture.json (an evidence item) when there is one,
    else the one handed in; nothing outside the Run directory is read for it, so re-judging the directory gives the
    Runner's verdict. The Task release files are read from task/ in the Run directory (sealed with it) or, until the
    Runner copies them there, from the Task package the Task view names (its frozen files)."""
    run_dir = Path(run_dir)
    ev = Evidence(root=run_dir, layout="eo-run/1")
    ev.run = dict(run) if run is not None else (_json(run_dir / "run.json") or {})
    if manifest is None:
        manifest = _json(run_dir / ((ev.run.get("evidence") or {}).get("ref") or "evidence.json")) or {}
    ev.missing = list(manifest.get("missing") or [])
    sealed_fixture = None
    for it in manifest.get("items") or []:
        p = run_dir / it.get("path", "")
        ev.items.append(dict(it))
        if not p.is_file():
            ev.missing.append({"name": it.get("name"), "reason": f"sealed item {it.get('path')} is gone"})
            continue
        if canon.file_digest(p) != it.get("digest"):
            ev.tampered.append(it.get("name"))
            continue
        if it.get("name") in ("fixture", "fixture.json") or it.get("path") == "fixture.json":
            sealed_fixture = _json(p)            # the Fixture sealed with the Run
            continue
        _load_item(ev, it.get("name", ""), p)
    if manifest.get("evidence_digest") and not (ev.run.get("evidence") or {}).get("digest"):
        ev.run.setdefault("evidence", {})["digest"] = manifest["evidence_digest"]
    ev.fixture = sealed_fixture if sealed_fixture is not None else fixture
    ev.task = task_files(run_dir / "task", task)
    if (run_dir / "task" / "taskspec.json").is_file():
        ev.task["dir"] = str(run_dir / "task")
    if ev.task.get("sport_hook"):
        ev.sport_hook = ev.task.pop("sport_hook")
    return ev


def task_files(tdir: Path, view=None) -> dict:
    """The Task release's files: tdir (task/ of the Run directory) first, else the package of the Runner's Task view
    (attribute `path`: tests/taskspec.json, contract.json, sport_grade.py of a legacy task; taskspec.json,
    instruction.md, manifest.lock.json of a v1 task); `release` / `status` / `lock` of the view when it has them."""
    task = {"kind": None, "taskspec": None, "taskspec_bytes": None, "instruction": None, "lock": None,
            "release": None, "contract": None, "dir": None}
    roots = [Path(tdir)]
    pkg = Path(getattr(view, "path", "") or "") if view is not None else None
    if pkg and str(pkg) not in ("", "."):
        roots += [pkg, pkg / "tests"]
    for root in roots:
        if task["taskspec_bytes"] is None and (root / "taskspec.json").is_file():
            task["taskspec_bytes"] = (root / "taskspec.json").read_bytes()
            task["taskspec"] = _json(root / "taskspec.json")
            task["kind"] = (task["taskspec"] or {}).get("schema")
        if task["instruction"] is None and (root / "instruction.md").is_file():
            task["instruction"] = (root / "instruction.md").read_bytes()
        for name, key in (("manifest.lock.json", "lock"), ("release.json", "release"), ("contract.json", "contract")):
            if task[key] is None and (root / name).is_file():
                task[key] = _json(root / name)
        if "sport_hook" not in task and (root / "sport_grade.py").is_file():
            task["sport_hook"] = root / "sport_grade.py"
    if view is not None:
        if task["release"] is None and getattr(view, "release", None):
            task["release"] = {"release": view.release, "status": getattr(view, "status", None)}
        if task["lock"] is None and isinstance(getattr(view, "lock", None), dict) and not view.lock.get("stub"):
            task["lock"] = view.lock
    return task


def _load_item(ev: Evidence, name: str, p: Path) -> None:
    if name == "world_report":
        ev.world = _json(p)
        ev.world_kind = (ev.world or {}).get("schema") or "ro-final/1"
    elif name == "episode":
        ev.episode = read_episode(p)
        ev.episode_read = True
    elif name == "replay_check":
        ev.replay = _json(p)
    elif name.startswith("gateway_usage."):
        ev.usage[name.split(".", 1)[1]] = _json(p) or {}
    elif name.startswith("gateway.") and name.endswith(".usage"):
        ev.usage[name[len("gateway."):-len(".usage")]] = _json(p) or {}
    elif name.startswith("gateway."):
        ev.gateway[name.split(".", 1)[1]] = read_jsonl(p)
    elif name == "platform_events":
        data = _json(p) if p.suffix == ".json" else None
        ev.platform = dict(data) if isinstance(data, dict) else {**ev.platform, "events": read_jsonl(p)}
    elif name in ("abort", "backend:abort.json") or p.as_posix().endswith("platform/abort.json"):
        ev.platform = {**ev.platform, "abort": _json(p) or {}}      # the Runner: provisioning or the match failed
    elif name == "backend:end.json" or p.as_posix().endswith("platform/end.json"):
        ev.platform = {**ev.platform, "end": _json(p) or {}}        # how the backend ended ({ended, code, reason})
    elif name == "delivered":
        ev.run.setdefault("delivered", _json(p) or {})
    elif name == "fingerprint":                  # the whole fingerprint (fingerprint.json), with the pre-start check
        ev.fingerprint = _json(p) or {}
        ev.run.setdefault("execution_fingerprint", ev.fingerprint)
    elif name == "preflight":
        ev.preflight = _json(p)
    elif name == "integrity":
        data = _json(p) or {}
        ev.run.setdefault("delivered", {}).setdefault("timing", data)


def load(path) -> Evidence:
    """Detect the layout of `path` and read it."""
    path = Path(path)
    if (path / "run.json").is_file() and (path / "evidence.json").is_file():
        return load_run_dir(path)
    if (path / "artifacts").is_dir() or (path / "result.json").is_file():
        if (path / "result.json").is_file() and not (path / "artifacts").is_dir() and not (path / "verifier").is_dir():
            subs = [d for d in path.iterdir() if d.is_dir() and (d / "result.json").is_file()]
            if len(subs) == 1:                    # a Harbor job directory with one trial
                return load_harbor_trial(subs[0])
        return load_harbor_trial(path)
    subs = [d for d in path.iterdir() if d.is_dir() and (d / "result.json").is_file()] if path.is_dir() else []
    if len(subs) == 1:
        return load_harbor_trial(subs[0])
    raise ValueError(f"{path}: not a Run directory (run.json + evidence.json) nor a Harbor trial directory")
