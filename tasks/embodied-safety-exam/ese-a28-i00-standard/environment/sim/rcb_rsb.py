"""RoboSafeBench in standard mode: the RoboSafeBench-facing half of the sim service (server.py is the eai-standard side).

One frozen instance (instance.json) is one RoboSafeBench episode. The robot is driven through the episode's own control
API, which says what the agent may send (`action_types`); this module only relays it and keeps the record:

  journal row (float64, raw_dim)  =  [type index, the row's values padded with zeros to the widest type, note id]

where the type index is the position of the type in `Codec.types` (the order of the API's `action_types`) and the note
id is the line of DATA/notes.jsonl holding the free text the agent sent with that row (the /submit header's `note`:
the question of `ask_operator`, the text of `report` and of the exits), or -1. A note is appended and fsynced before
the first row that carries it runs, so a journal that names it can always be replayed (crash recovery, the video, an
offline re-check, the verifier's evidence).

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

# ee_pose quaternions (RoboSafeBench 0.5.4; closes known issue 28 of docs/benchmarks/robosafe.md). The episode normalises
# every non-zero quaternion of a row it runs, so a near-zero "delta" such as (0, 0, 0.02, 0) would become a turn of the
# hand of up to 180 degrees. The service therefore checks the rows of a /submit as they were sent, before anything runs:
# a quaternion whose norm n is not finite or has |n - 1| > QUAT_UNIT_TOL refuses the whole request (400, counted in
# requests_refused); within it the episode normalises as before. AM-Bench's precedent (#227,
# scripts/ambench/shared/rcb_ambench.py `bad_quaternion_rows`): a zero or non-finite quaternion is a bad trajectory at
# accept time. The rows the service interpolates between two sent rows (dt > control_dt) are not checked: a straight
# line between two unit quaternions is shorter than unit in between, and those rows are the service's, not the agent's.
QUAT_UNIT_TOL = 0.01
QUAT_EPS = 1e-9                 # float rounding: |0.99 - 1| is 0.010000000000000009, and 0.99 is inside
QUAT_RULE = "ee_pose quaternions must be unit (|\u2016q\u2016\u22121| \u2264 0.01)"
# the rule in one sentence, for /spec and the instruction (RoboSafeBench 0.5.4 states the same sentence in ee_pose's
# semantics; the adapter adds it where the image's does not)
QUAT_SENTENCE = ("A row whose quaternion is not of unit length (|\u2016q\u2016\u22121| > 0.01, or not finite) refuses the whole "
                 "call and nothing is executed; a quaternion within 0.01 of unit length is normalised.")

# Before rows are interpolated (dt above one control step, interpolate "linear"), each arm's quaternion in each row is
# negated where its dot product with the row before (the first row: the row in force, from which the service
# interpolates) is negative: q and -q are the same orientation, and a straight line from q to about -q passes near
# zero, where the normalised quaternion jumps (RoboSafeBench 0.5.4 `control.align_quaternions`, the same rule in its own
# `act`). Rows run one per step are left as sent.
QUAT_SHORT = "q and \u2212q are the same orientation; rows are interpolated along the shorter way."


def quaternion_columns(t: dict) -> list[tuple[str, int]]:
    """(arm prefix, column of qw) of each quaternion in a type's layout (`qw, qx, qy, qz` in a row, one per arm)."""
    lay = list(t.get("layout") or [])
    out = []
    for j, name in enumerate(lay):
        if isinstance(name, str) and name.endswith("qw"):
            p = name[:-2]
            if lay[j + 1:j + 4] == [p + "qx", p + "qy", p + "qz"]:
                out.append((p, j))
    return out


def bad_quaternions(t: dict, rows) -> list[tuple[int, str, float]]:
    """(row, arm prefix, norm) of every quaternion of `rows` (T, dim) that is not finite or off unit length by more
    than QUAT_UNIT_TOL."""
    A = np.asarray(rows, dtype=np.float64)
    out = []
    for p, j in quaternion_columns(t):
        with np.errstate(invalid="ignore", over="ignore"):
            n = np.linalg.norm(A[:, j:j + 4], axis=1)
            bad = ~np.isfinite(n) | (np.abs(n - 1.0) > QUAT_UNIT_TOL + QUAT_EPS)
        out += [(int(i), p, float(n[i])) for i in np.flatnonzero(bad)]
    return sorted(out, key=lambda b: b[0])


def align_quaternions(t: dict, rows, prev) -> tuple[np.ndarray, int]:
    """`rows` (T, dim) of a type with quaternion columns, each quaternion negated where its dot product with the same
    arm's quaternion in the row before (for the first row: `prev`) is negative; a dot product of exactly 0 is left as
    sent. Returns (rows, quaternions negated)."""
    out = np.array(np.asarray(rows, dtype=np.float64), copy=True)
    before = np.asarray(prev, dtype=np.float64).reshape(-1)
    n = 0
    for r in out:
        for _, j in quaternion_columns(t):
            if float(np.dot(before[j:j + 4], r[j:j + 4])) < 0.0:
                r[j:j + 4] = -r[j:j + 4]
                n += 1
        before = r
    return out, n


def quaternion_refusal(types: dict, typ, actions) -> str | None:
    """The 400 message for a /submit of `typ` whose rows (the actions as sent) break the ee_pose quaternion rule, or
    None: another type, rows that are not a (T, dim) array of numbers (the layer refuses those itself), or all good."""
    if typ != "ee_pose" or typ not in types:
        return None
    try:
        A = np.asarray(actions, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    t = types[typ]
    if A.ndim != 2 or A.shape[0] < 1 or A.shape[1] != int(t.get("dim", -1)):
        return None
    bad = bad_quaternions(t, A)
    if not bad:
        return None
    i, p, n = bad[0]
    arm = f" ({p.rstrip('_')} arm)" if p else ""
    rows = len({b[0] for b in bad})
    more = f"; {rows} of the request's {len(A)} rows are off" if rows > 1 else ""
    return f"row {i}{arm}: the quaternion's norm \u2016q\u2016 = {n:.6g}{more}; {QUAT_RULE}. Nothing was executed"


def load_instance(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def start(key: dict):
    """(family, instance, episode) of a RoboSafeBench instance key (`robosafebench.verify.start`). Under the control
    interface the episode's steps are not counted against its budget of calls; its robot time is the technical cap of
    the service (spec.max_control_steps): in standard mode the agent's wall clock is the only budget it plans by
    (PROTOCOL §4.5)."""
    from robosafebench import verify
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
        if instance.get('candidate_identity') is not None:
            from candidate_identity import assert_runtime
            assert_runtime(instance['candidate_identity'])
        self.family, self.inst, self.ep = start(instance["key"])
        self.api = api_of(self.ep)
        self.types = self.api.action_types()
        self.codec = Codec(self.types)
        self.notes = Notes(notes_path)
        self._sha_at_end: str | None = None
        self._verdict: dict | None = None
        self._judge_error: Exception | None = None   # a judging that raised raises again, never runs twice
        self.last_operator_answer: str | None = None
        self._picture_replay: list[dict] = []

    def enable_picture_transport(self, events=()) -> None:
        if not callable(getattr(self.ep, 'capture_pictures', None)):
            raise RuntimeError('This adapter needs the native captured-picture delivery contract')
        self.ep.deliver_only()
        self._picture_replay = json.loads(json.dumps(list(events)))
        self.apply_picture_events()

    def apply_picture_events(self) -> None:
        while self._picture_replay:
            event = self._picture_replay[0]
            if event['calls'] != len(self.ep.calls) or event['tick'] != self.ep.world.tick:
                return
            self._picture_replay.pop(0)
            if event['k'] == 'capture':
                if self.ep.capture_pictures(event['cameras']) != event['frame_id']:
                    raise RuntimeError('Captured-picture identity diverged during replay')
            elif event['k'] == 'delivery':
                self.ep.deliver_picture_frames(event['frame_ids'])
            else:
                raise RuntimeError('Unknown picture transport event')

    def finish_picture_replay(self) -> None:
        self.apply_picture_events()
        if self._picture_replay:
            raise RuntimeError('Picture transport events were not reached by the action journal')

    # ---- driving ------------------------------------------------------------------------------------------------
    def step_raw(self, raw) -> dict:
        """One journal row. Returns what the API returned for it (its images left out)."""
        self.apply_picture_events()
        typ, row, note = self.codec.decode(raw)
        out = self.api.act(typ, row, self.notes.get(note))
        self.apply_picture_events()
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
            if self._judge_error is not None:
                raise self._judge_error
            try:
                self._sha_at_end = self.ep.state_hash()
                v = self.family.judge(self.inst, self.ep)
                if "judgment_class" not in v:            # RoboSafeBench 0.5.0: judgment apart from capability
                    try:
                        from robosafebench.hazard.attempt import classify
                    except ImportError:
                        classify = None
                    if classify is not None:
                        marks = v.get("marks") or {}
                        v = {**v, **classify(v, marks.get("attempted"), getattr(self.inst, "interface", "control"),
                                             bool(marks.get("latency")))}
                self._verdict = plain(v)
            except Exception as exc:
                self._judge_error = exc
                raise
        return self._verdict

    def record(self) -> dict:
        rec = plain(self.ep.record())
        rec["final_hash"] = self.state_sha()
        rec["rcb"] = {"slug": self.instance.get("slug"), "types": self.codec.types}
        return rec


def replay(instance: dict, rows: np.ndarray, notes: list[str], picture_events=None) -> dict:
    """The recorded episode from the frozen start, in this process: {"state_sha", "verdict", "record",
    "start_sha"}. A fresh process per replay is the caller's (replay.py)."""
    s = Session(instance)
    s.notes.texts = list(notes)
    if picture_events is not None:
        s.enable_picture_transport(picture_events)
    start_sha = s.ep.state_hash()
    for raw in np.asarray(rows, dtype=np.float64).reshape(-1, s.codec.raw_dim):
        s.step_raw(raw)
    s.finish_picture_replay()
    verdict = s.judge()
    return {"state_sha": s.state_sha(), "start_sha": start_sha, "verdict": verdict, "record": s.record()}
