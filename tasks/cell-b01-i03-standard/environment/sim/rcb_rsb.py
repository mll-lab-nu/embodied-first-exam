"""RoboSafeBench in standard mode: the RoboSafeBench-facing half of the sim service (server.py is the eai-standard side).

One frozen instance (instance.json) is one RoboSafeBench episode. The robot is driven through the episode's own control
API, which says what the agent may send (`action_types`); this module only relays it and keeps the record:

  journal row (float64, raw_dim)  =  [type index, the row's values padded with zeros to the widest type, note id]

where the type index is the position of the type in `Codec.types` (the order of the API's `action_types`) and the note
id is the line of DATA/notes.jsonl holding the free text the agent sent with that row (the /submit header's `note`:
the question of `ask_operator`, the text of `report` and of the exits), or -1. A note is appended and fsynced before
the first row that carries it runs, so a journal that names it can always be replayed (crash recovery, the graded
replay, the verifier's evidence).

The control API an episode offers (RoboSafeBench's side, the instance key's `"interface": "control"`; `api_of`):
  action_types() -> {name: {"dim", "layout", "lower", "upper", "units", "semantics", "interpolable": bool,
                            "text": bool}}           the types, in the order the codec numbers them
  control_dt, max_control_steps                       seconds per control step; the technical cap (the family's robot
                                                       time budget in control steps)
  act(type, row: float64[dim], text: str | None) -> {"ok", "result" | "error", "messages"?, "robot"?}
                                                       one row: one control step, or one exit or message (no robot
                                                       time); recorded by the episode itself (ep.calls, ep.record())
  clip(type, rows) -> (rows, [{"row", "index", "reason"}])   static bounds
  command(type) -> float64[dim]                        the row in force in that type's space (a chunk interpolates
                                                       from it)
  hold() -> (type, row)                                the row that keeps the robot as it is (/observe with seconds)
  proprio_layout: list[str]; proprio() -> float array  the robot's own sensors
  cameras: list[str]; camera_spec() -> {camera: {...}} intrinsics and mounting (for /spec)
  render(camera) -> uint8 (h, w, 3); render_depth(camera) -> float32 (h, w) metres, for the RGB-D cameras only
and of the episode itself: `ended` (None until an exit), `state_hash()`; the family judges it (`family.judge`).

Nothing here names a member, a hazard or an object to the agent: the texts that leave the service are the task's
request, the API's own descriptions, the results the API returns and the operator's answers.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

NOTE_NONE = -1
MAX_NOTE = 4000                 # characters of one note (RoboSafeBench's MAX_TEXT)


def load_instance(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def start(key: dict):
    """(family, instance, episode) of a RoboSafeBench instance key (`robosafe.verify.start`). Under the control
    interface the episode's steps are not counted against its budget of calls; its robot time is the technical cap of
    the service (spec.max_control_steps): in standard mode the agent's wall clock is the only budget it plans by
    (PROTOCOL §4.5)."""
    from robosafe import verify
    dev = os.environ.get("RCB_RSB_DEV") == "1"              # development renders only (make_instances.py --dev)
    if not dev and dict(key).get("interface") != "control":
        raise RuntimeError(f"RoboSafeBench is served here under its control interface only; the key asks for "
                           f"{dict(key).get('interface', 'skill')!r}")
    fam, inst, ep = verify.start(key)
    if not dev and getattr(ep, "interface", None) != "control":
        raise RuntimeError(f"the episode was built under {getattr(ep, 'interface', None)!r}, not the control interface")
    return fam, inst, ep


def api_of(ep):
    """The episode's control API: RoboSafeBench's own where the episode has it, else the development stand-in
    (rcb_rsb_dev.py, present only in development renders of the tasks)."""
    if hasattr(ep, "action_types") and hasattr(ep, "act"):
        return ep
    import rcb_rsb_dev                                   # noqa: PLC0415 -- development renders only
    return rcb_rsb_dev.SkillAPI(ep)


def plain(x):
    """JSON-safe copy (numpy scalars and arrays, tuples, non-finite floats)."""
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return plain(x.tolist())
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return x if math.isfinite(x) else str(x)
    if isinstance(x, (str, bool, int)) or x is None:
        return x
    return str(x)


class Notes:
    """DATA/notes.jsonl: one line per note, {"id", "text"}; the id is the line number."""

    def __init__(self, path: str | None):
        self.path, self.texts = path, []
        if path and os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip():
                        self.texts.append(json.loads(line)["text"])
        elif path:                      # an episode without notes still has the file (the collect hook copies it)
            open(path, "a").close()

    def add(self, text: str) -> int:
        i = len(self.texts)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps({"id": i, "text": text}) + "\n")
                f.flush()
                os.fsync(f.fileno())
            fd = os.open(os.path.dirname(os.path.abspath(self.path)), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self.texts.append(text)
        return i

    def get(self, i: int) -> str | None:
        i = int(i)
        if i == NOTE_NONE:
            return None
        if not 0 <= i < len(self.texts):
            raise ValueError(f"note {i} is not in the notes table ({len(self.texts)} notes)")
        return self.texts[i]


class Codec:
    """Journal rows <-> (type, row, note id)."""

    def __init__(self, types: dict):
        self.types = list(types)
        self.dims = {t: int(types[t]["dim"]) for t in self.types}
        self.width = max(self.dims.values())
        self.raw_dim = self.width + 2

    def encode(self, typ: str, row, note: int) -> np.ndarray:
        out = np.zeros(self.raw_dim, dtype=np.float64)
        out[0] = self.types.index(typ)
        row = np.asarray(row, dtype=np.float64).reshape(-1)
        out[1:1 + len(row)] = row
        out[-1] = note
        return out

    def decode(self, raw) -> tuple[str, np.ndarray, int]:
        raw = np.asarray(raw, dtype=np.float64)
        typ = self.types[int(raw[0])]
        return typ, raw[1:1 + self.dims[typ]].copy(), int(raw[-1])


class Session:
    """One episode of one frozen instance, driven by journal rows."""

    def __init__(self, instance: dict, notes_path: str | None = None):
        self.instance = instance
        self.family, self.inst, self.ep = start(instance["key"])
        self.api = api_of(self.ep)
        self.types = self.api.action_types()
        self.codec = Codec(self.types)
        self.notes = Notes(notes_path)
        self._sha_at_end: str | None = None
        self._verdict: dict | None = None
        self.last_operator_answer: str | None = None

    # ---- driving ------------------------------------------------------------------------------------------------
    def step_raw(self, raw) -> dict:
        """One journal row. Returns what the API returned for it (its images left out)."""
        typ, row, note = self.codec.decode(raw)
        out = self.api.act(typ, row, self.notes.get(note))
        out = {k: v for k, v in out.items() if k != "images"}
        res = out.get("result")
        if isinstance(res, dict) and isinstance(res.get("answer"), str):
            self.last_operator_answer = res["answer"]
        return out

    @property
    def ended(self) -> bool:
        return self.ep.ended is not None

    def state_sha(self) -> str:
        """The state hash; once the episode has been judged, the hash it had just before (judging lets the rules that
        fire at the end of an episode fire, which a replay does after taking its hash too)."""
        return self._sha_at_end if self._sha_at_end is not None else self.ep.state_hash()

    def judge(self) -> dict:
        """RoboSafeBench's verdict on the episode as it stands (once: the first call ends the episode's rules)."""
        if self._verdict is None:
            self._sha_at_end = self.ep.state_hash()
            v = self.family.judge(self.inst, self.ep)
            if "judgment_class" not in v:            # RoboSafeBench 0.5.0: judgment apart from capability
                try:
                    from robosafe.hazard.attempt import classify
                except ImportError:
                    classify = None
                if classify is not None:
                    marks = v.get("marks") or {}
                    v = {**v, **classify(v, marks.get("attempted"), getattr(self.inst, "interface", "control"),
                                         bool(marks.get("latency")))}
            self._verdict = plain(v)
        return self._verdict

    def record(self) -> dict:
        rec = plain(self.ep.record())
        rec["final_hash"] = self.state_sha()
        rec["rcb"] = {"slug": self.instance.get("slug"), "types": self.codec.types}
        return rec


def replay(instance: dict, rows: np.ndarray, notes: list[str]) -> dict:
    """The recorded episode from the frozen start, in this process: {"state_sha", "verdict", "record",
    "start_sha"}. A fresh process per replay is the caller's (replay.py)."""
    s = Session(instance)
    s.notes.texts = list(notes)
    start_sha = s.ep.state_hash()
    for raw in np.asarray(rows, dtype=np.float64).reshape(-1, s.codec.raw_dim):
        s.step_raw(raw)
    verdict = s.judge()
    return {"state_sha": s.state_sha(), "start_sha": start_sha, "verdict": verdict, "record": s.record()}
