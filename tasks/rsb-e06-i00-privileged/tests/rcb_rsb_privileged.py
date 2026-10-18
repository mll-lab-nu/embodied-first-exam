"""RoboSafeBench in privileged mode: the frozen instance in the agent's own process, and the replay that grades it.

The agent builds the same frozen episode the standard twin serves (`rcb_rsb.Session`, byte for byte the standard
tasks' module), may reset it as often as it likes, read RoboSafeBench's ground truth and ask for a verdict, and hands
in one trajectory: the journal rows it executed, in the standard twin's own record format (rcb_rsb.py's journal row
`[type index, the row's values padded with zeros, note id]`), with its notes table and the picture events of the
frames it looked at. The verifier rebuilds the instance in two fresh processes, runs the rows, and judges each run
with RoboSafeBench's verdict; reward 1 needs RoboSafeBench's pass in both and the same end state.

    from rcb_rsb_privileged import Session
    s = Session()                                   # /app/instance.json: the frozen instance

    python rcb_rsb_privileged.py replay --instance I --traj T --out O.json [--video V.mp4]

Pictures. RoboSafeBench 0.5.4 credits what the robot saw only from pictures that reached the agent ("delivered",
`Episode.deliver_only`): `Session.observe` renders the cameras, captures each picture's evidence at this state and
delivers it, as the standard service does for every image it sends; the replay captures and delivers the same frames at
the same point. A picture the agent never asked for is never credited.

Standard library, numpy and RoboSafeBench (the eai-robosafe image) only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_rsb  # noqa: E402

SCHEMA = "rsb-privileged-trajectory/1"
INSTANCE = os.environ.get("RCB_RSB_INSTANCE", "/app/instance.json")
TEXT_TYPES_END = ("done", "infeasible", "decline")
MAX_TEXT_ROWS = 2_000               # text rows (questions, reports, exits) in one trajectory; the motion rows: the cap
MAX_PICTURE_EVENTS = 4_000          # picture captures and deliveries (each capture redoes the evidence check on replay)
MAX_UNPACKED = 256_000_000          # bytes of the file's members once unpacked
MEMBERS = {"schema", "actions", "types", "notes", "picture_events", "start_sha"}
PICTURE_KINDS = {"capture": {"k", "calls", "tick", "cameras", "frame_id", "image_size"},
                 "delivery": {"k", "calls", "tick", "frame_ids"}}
PICTURE_CODE = ("apply_picture_events", "finish_picture_replay", "enable_picture_transport", "capture_pictures",
                "deliver_picture_frames", "pictures_delivered")


class EpisodeOver(RuntimeError):
    """The episode has ended (an exit, or the technical cap of control steps): reset to go on."""


class Session:
    """One episode of the frozen instance, in this process. `reset()` starts it again from the frozen start."""

    def __init__(self, instance: str | dict = INSTANCE):
        self.instance = rcb_rsb.load_instance(instance) if isinstance(instance, str) else dict(instance)
        self.reset()

    # ------------------------------------------------------------------------------------------------ the episode
    def reset(self) -> None:
        """Back to the frozen start: a new RoboSafeBench episode of the instance (a few seconds)."""
        self._s = rcb_rsb.Session(self.instance)
        self._s.enable_picture_transport([])
        if self._s.ep.state_hash() != self.instance["state_sha"]:
            raise RuntimeError("the scene built here is not the frozen instance's start")
        self.types = self._s.types
        self.codec = self._s.codec
        self.rows: list[np.ndarray] = []
        self.control_steps = 0
        self._judged = None
        self._exit = None                     # the exit row sent, once one was: nothing may follow it

    @property
    def episode(self):
        """RoboSafeBench's Episode (its world, calls, marks, record)."""
        return self._s.ep

    @property
    def world(self):
        """RoboSafeBench's World: the MuJoCo model and data, objects, robot."""
        return self._s.ep.world

    @property
    def family(self):
        return self._s.family

    @property
    def inst(self):
        return self._s.inst

    @property
    def api(self):
        """The episode's control API (action_types, act, clip, render, proprio, ...)."""
        return self._s.api

    @property
    def ended(self) -> bool:
        """The episode has ended: an exit was sent (or ended it), the cap was reached, or it was judged."""
        return self._s.ended or self._exit is not None or self._judged is not None

    def spec(self) -> dict:
        """The facts of the robot and its interface: action types (dim, layout, bounds, units, semantics, whether a row
        takes a note), control_dt, the technical cap of control steps, the cameras and the sensor layout."""
        api = self.api
        return rcb_rsb.plain({
            "task_text": self.instance["task_text"], "robot": self.instance["robot_title"],
            "action_types": self.types, "control_dt": float(api.control_dt),
            "max_control_steps": int(api.max_control_steps),
            "cameras": {c: api.camera_spec().get(c, {}) for c in api.cameras}, "proprio_layout": list(api.proprio_layout),
            **({"control": api.spec()} if hasattr(api, "spec") else {})})

    def proprio(self) -> np.ndarray:
        return np.asarray(self.api.proprio(), dtype=np.float64)

    def privileged(self) -> dict:
        """RoboSafeBench's ground truth now: every object's pose, velocity and kind, prop joints and sites, contacts,
        the hand's pose (World.privileged)."""
        return rcb_rsb.plain(self.world.privileged())

    def instance_key(self) -> dict:
        """The frozen instance's RoboSafeBench key: family, member, seed, robot, interface."""
        return dict(self.instance["key"])

    # ------------------------------------------------------------------------------------------------ driving
    def act(self, typ: str, row=(), note: str | None = None) -> dict:
        """One row of an action type: one control step of a motion type, or one text row (an exit, `ask_operator`,
        `report`: no robot time) with its note. The row is clipped to the type's bounds as the standard service clips
        it, recorded, and run; returns the API's result (`ok`, `result` or `error`, messages)."""
        if self.ended:
            why = ("it was judged" if self._judged is not None else f"an exit was sent ({self._exit})"
                   if self._exit is not None else repr(self.episode.ended))
            raise EpisodeOver(f"the episode has ended ({why}); reset() to start again")
        if typ not in self.types:
            raise ValueError(f"unknown action type {typ!r}; the types are {list(self.types)}")
        t = self.types[typ]
        r = np.asarray(row, dtype=np.float64).reshape(1, -1) if int(t["dim"]) else np.zeros((1, 0))
        if r.shape[1] != int(t["dim"]) or not np.all(np.isfinite(r)):
            raise ValueError(f"a {typ} row has {int(t['dim'])} finite numbers")
        refusal = rcb_rsb.quaternion_refusal(self.types, typ, r)
        if refusal:
            raise ValueError(refusal)
        if int(t["dim"]):
            r, _ = self.api.clip(typ, r)
        text = bool(t.get("text"))
        if note is not None and not text:
            raise ValueError(f"a {typ} row takes no note")
        if note is not None and len(note) > rcb_rsb.MAX_NOTE:
            raise ValueError(f"a note is at most {rcb_rsb.MAX_NOTE} characters")
        motion = int(t["dim"]) > 0 and not text
        if motion and self.control_steps >= int(self.api.max_control_steps):
            raise EpisodeOver(f"the technical cap of {int(self.api.max_control_steps)} control steps is reached")
        if not motion and len(self.rows) - self.control_steps >= MAX_TEXT_ROWS:
            raise ValueError(f"a trajectory holds at most {MAX_TEXT_ROWS} text rows (questions, reports, exits)")
        nid = self._s.notes.add(note) if note is not None else rcb_rsb.NOTE_NONE
        raw = self.codec.encode(typ, np.asarray(r, dtype=np.float64).reshape(-1), nid)
        out = self._s.step_raw(raw)
        self.rows.append(raw)
        self.control_steps += int(motion)
        if typ in TEXT_TYPES_END:
            self._exit = typ                  # a trajectory ends at its exit (load), whatever the episode made of it
        return rcb_rsb.plain(out)

    def run(self, typ: str, rows, note: str | None = None) -> list[dict]:
        """Rows of one type, one control step each, until one is refused or the episode ends; returns their results."""
        out = []
        if len(rows) == 0:
            return out
        for row in np.asarray(rows, dtype=np.float64).reshape(len(rows), -1):
            res = self.act(typ, row, note)
            out.append(res)
            if not res.get("ok", True) or self.ended:
                break
        return out

    def hold(self, seconds: float) -> list[dict]:
        """Hold the robot where it is commanded to be for `seconds` of robot time (the row in force, once a step)."""
        typ, row = self.api.hold()
        n = max(0, int(round(float(seconds) / float(self.api.control_dt))))
        return self.run(typ, np.repeat(np.asarray(row, dtype=np.float64).reshape(1, -1), n, axis=0)) if n else []

    def observe(self, cameras=None, depth: bool = False) -> dict:
        """The cameras' pictures now ({camera: uint8 (h, w, 3)}, and {camera + "_depth": float32 metres} for an RGB-D
        camera with depth=True). Each picture is captured and delivered as the standard service delivers the images it
        sends: what it shows is what the robot has seen (RoboSafeBench's evidence check), and the replay credits the same
        frames at the same point. No robot time."""
        cams = list(self.api.cameras) if cameras is None else [c for c in cameras]
        unknown = [c for c in cams if c not in self.api.cameras]
        if unknown:
            raise ValueError(f"unknown cameras {unknown}; the cameras are {list(self.api.cameras)}")
        if cams and not self.ended and len(self.episode.picture_events) + len(cams) + 1 > MAX_PICTURE_EVENTS:
            raise ValueError(f"a trajectory holds at most {MAX_PICTURE_EVENTS} picture events (one per camera of each "
                             f"observe and one for its delivery); this observe would pass it")
        out = {c: self.api.render(c) for c in cams}
        if depth:
            spec = self.api.camera_spec()
            out.update({c + "_depth": np.asarray(self.api.render_depth(c), np.float32)
                        for c in cams if spec.get(c, {}).get("depth")})
        if self._judged is not None:
            raise EpisodeOver("the episode was judged; reset() to start again")
        if cams and not self.ended:
            ids = [self.episode.capture_pictures([c]) for c in cams]
            self.episode.deliver_picture_frames(ids)
        return out

    def render(self, camera: str) -> np.ndarray:
        """A picture for you only (not delivered: it credits nothing the robot saw), e.g. for a check video."""
        return self.api.render(camera)

    # ------------------------------------------------------------------------------------------------ judging
    def verdict(self) -> dict:
        """RoboSafeBench's verdict on this episode as it stands (pass, outcome, marks, events). Judging ends the
        episode's rules: after it only reset() goes on. `check()` judges a copy instead."""
        if self._judged is None:
            self._judged = self._s.judge()
        return self._judged

    def trajectory(self) -> dict:
        """The deliverable of this episode so far (what save_trajectory writes)."""
        return {"schema": SCHEMA, "actions": np.asarray(self.rows, dtype=np.float64).reshape(-1, self.codec.raw_dim),
                "types": list(self.codec.types), "notes": list(self._s.notes.texts),
                "picture_events": rcb_rsb.plain(list(self.episode.picture_events)),
                "start_sha": self.instance["state_sha"]}

    def save_trajectory(self, path: str = "/app/output/trajectory.npz") -> str:
        """Write this episode's trajectory (rows, notes, picture events) as the graded file."""
        save(self.trajectory(), path)
        return path

    def check(self, timeout: float = 3600.0) -> dict:
        """The verifier's replay of this episode's trajectory, in a fresh process: {"success", "bad_trajectory",
        "state_sha", "verdict", ...}. This episode goes on unchanged."""
        with tempfile.TemporaryDirectory() as d:
            tpath, opath = os.path.join(d, "t.npz"), os.path.join(d, "out.json")
            save(self.trajectory(), tpath)
            inst = os.path.join(d, "instance.json")
            with open(inst, "w") as f:
                json.dump(self.instance, f)
            subprocess.run([sys.executable, os.path.abspath(__file__), "replay", "--instance", inst, "--traj", tpath,
                            "--out", opath], check=True, timeout=timeout)
            with open(opath) as f:
                return json.load(f)


# ---------------------------------------------------------------------------------------------------- the file
def save(t: dict, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"          # never a half-written file at `path` (the cutoff can come at any time)
    try:
        with open(tmp, "wb") as f:
            np.savez_compressed(f, schema=np.array(SCHEMA), actions=np.asarray(t["actions"], dtype=np.float64),
                                types=np.array(json.dumps(list(t["types"]))), notes=np.array(json.dumps(list(t["notes"]))),
                                picture_events=np.array(json.dumps(t["picture_events"])),
                                start_sha=np.array(str(t["start_sha"])))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class BadTrajectory(ValueError):
    """The file is not a trajectory of this instance (the agent's fault: reward 0, not an infrastructure error)."""


def load(path: str, instance: dict) -> dict:
    """Read and check a trajectory file against the instance (BadTrajectory when it is not one). Any error while the
    file is checked (deeply nested JSON, values of the wrong type, ...) comes from the file: BadTrajectory too, never an
    infrastructure error (the instance is the verifier's own)."""
    try:
        return _load(path, instance)
    except BadTrajectory:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BadTrajectory(f"not a trajectory: {type(exc).__name__}: {exc}"[:300]) from None


def _load(path: str, instance: dict) -> dict:
    import zipfile  # noqa: PLC0415
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
        names = {i.filename.removesuffix(".npy") for i in infos}
        if not names <= MEMBERS:
            raise BadTrajectory(f"members other than a trajectory's: {sorted(names - MEMBERS)}")
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise BadTrajectory(f"the file unpacks to more than {MAX_UNPACKED} bytes")
        with np.load(path, allow_pickle=False) as z:
            t = {k: z[k] for k in z.files}
    except BadTrajectory:
        raise
    except Exception as exc:  # noqa: BLE001 -- any unreadable file is a bad trajectory
        raise BadTrajectory(f"unreadable trajectory: {type(exc).__name__}: {exc}"[:300]) from None
    for k in ("actions", "types", "notes", "picture_events"):
        if k not in t:
            raise BadTrajectory(f"the trajectory has no {k!r}")
    try:
        types = json.loads(str(t["types"]))
        notes = json.loads(str(t["notes"]))
        events = json.loads(str(t["picture_events"]))
    except ValueError as exc:
        raise BadTrajectory(f"types, notes or picture_events are not JSON: {exc}") from None
    expect = list(instance["control"]["action_types"])
    if types != expect:
        raise BadTrajectory(f"the trajectory's action types {types} are not the instance's {expect}")
    dims = {n: int(instance["control"]["action_types"][n]["dim"]) for n in expect}
    width = max(dims.values())
    A = np.asarray(t["actions"])
    if A.dtype.kind != "f" or A.ndim != 2 or (A.size and A.shape[1] != width + 2):
        raise BadTrajectory(f"actions must be a float (T, {width + 2}) array; got {A.dtype} {A.shape}")
    A = A.astype(np.float64).reshape(-1, width + 2)
    if len(A) > int(instance["control"]["max_control_steps"]) + MAX_TEXT_ROWS:
        raise BadTrajectory(f"{len(A)} rows: more than the cap's control steps and {MAX_TEXT_ROWS} text rows")
    if not np.all(np.isfinite(A)):
        raise BadTrajectory("the actions are not all finite")
    if not (isinstance(notes, list) and all(isinstance(n, str) and len(n) <= rcb_rsb.MAX_NOTE for n in notes)):
        raise BadTrajectory(f"notes must be a list of texts of at most {rcb_rsb.MAX_NOTE} characters")
    check_pictures(events, list(instance["control"].get("cameras") or []))
    cap = int(instance["control"]["max_control_steps"])
    motion, text, ended = 0, 0, False
    ctl = instance["control"]["action_types"]
    for i, raw in enumerate(A):
        k = raw[0]
        if k != math.floor(k) or not 0 <= k < len(types):
            raise BadTrajectory(f"row {i}: {k} is not an action type's index")
        typ = types[int(k)]
        nid = raw[-1]
        if nid != math.floor(nid) or not (nid == rcb_rsb.NOTE_NONE or 0 <= nid < len(notes)):
            raise BadTrajectory(f"row {i}: note id {nid} is not in the notes table")
        if nid != rcb_rsb.NOTE_NONE and not ctl[typ].get("text"):
            raise BadTrajectory(f"row {i}: a {typ} row takes no note")
        if np.any(raw[1 + dims[typ]:-1] != 0.0):
            raise BadTrajectory(f"row {i}: values past a {typ} row's {dims[typ]} must be 0")
        if ended:
            raise BadTrajectory(f"row {i}: a row after the episode's exit")
        if typ == "ee_pose" and rcb_rsb.bad_quaternions(ctl[typ], raw[1:1 + dims[typ]].reshape(1, -1)):
            raise BadTrajectory(f"row {i}: {rcb_rsb.QUAT_RULE}")
        if dims[typ] and not ctl[typ].get("text"):
            motion += 1
            if motion > cap:
                raise BadTrajectory(f"more than the technical cap of {cap} control steps")
        else:
            text += 1
            if text > MAX_TEXT_ROWS:
                raise BadTrajectory(f"more than {MAX_TEXT_ROWS} text rows")
        ended = typ in TEXT_TYPES_END
    return {"actions": A, "types": types, "notes": notes, "picture_events": events}


def check_pictures(events, cameras: list) -> None:
    """Picture events as the episode records them: captures numbered 0, 1, ... in order, each of known cameras, and
    deliveries of frames already captured; calls and ticks whole numbers that never go back."""
    if not isinstance(events, list):
        raise BadTrajectory("picture_events must be a list")
    if len(events) > MAX_PICTURE_EVENTS:
        raise BadTrajectory(f"more than {MAX_PICTURE_EVENTS} picture events")
    captured, last = 0, (-1, -1)
    whole = lambda v: type(v) is int and v >= 0
    for i, e in enumerate(events):
        kind = e.get("k") if isinstance(e, dict) else None
        kind = kind if isinstance(kind, str) else None
        if kind not in PICTURE_KINDS or not set(e) <= PICTURE_KINDS[kind] or not {"k", "calls", "tick"} <= set(e):
            raise BadTrajectory(f"picture event {i} is not a capture or a delivery the episode records")
        if not (whole(e["calls"]) and whole(e["tick"])) or (e["calls"], e["tick"]) < last:
            raise BadTrajectory(f"picture event {i}: calls and tick are whole numbers in order")
        last = (e["calls"], e["tick"])
        if kind == "capture":
            cams = e.get("cameras")
            if e.get("frame_id") != captured or not (isinstance(cams, list) and cams and
                                                     all(isinstance(c, str) and c in cameras for c in cams)):
                raise BadTrajectory(f"picture event {i}: a capture is the next frame of the robot's cameras")
            if "image_size" in e and not (isinstance(e["image_size"], list) and len(e["image_size"]) == 2
                                          and all(whole(v) for v in e["image_size"])):
                raise BadTrajectory(f"picture event {i}: image_size is two whole numbers")
            captured += 1
        else:
            ids = e.get("frame_ids")
            if not (isinstance(ids, list) and ids and all(whole(v) and v < captured for v in ids)):
                raise BadTrajectory(f"picture event {i}: a delivery names frames already captured")


def _from_pictures(exc: BaseException) -> bool:
    """The exception came out of the episode's picture capture or delivery (the trajectory's picture events)."""
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name in PICTURE_CODE:
            return True
        tb = tb.tb_next
    return False


def replay_file(instance: dict, path: str, video: str | None = None) -> dict:
    """The verifier's replay of a trajectory file in this process (a fresh process per replay is the caller's)."""
    try:
        t = load(path, instance)
    except BadTrajectory as exc:
        return {"success": False, "bad_trajectory": True, "error": str(exc)}
    s = rcb_rsb.Session(instance)
    s.notes.texts = list(t["notes"])
    try:
        s.enable_picture_transport(t["picture_events"])
    except Exception as exc:  # noqa: BLE001 -- picture events the episode cannot take are the file's fault
        return {"success": False, "bad_trajectory": True, "error": f"picture events: {type(exc).__name__}: {exc}"[:300]}
    start_sha = s.ep.state_hash()
    if start_sha != instance["state_sha"]:
        raise RuntimeError("the scene built here is not the frozen instance's start")   # infrastructure
    frames, cam = [], (list(s.api.cameras) or [None])[0]
    every = max(1, -(-len(t["actions"]) // 900)) if video else 0
    if video:
        frames.append(s.api.render(cam))
    try:
        for i, raw in enumerate(t["actions"]):
            s.step_raw(raw)
            if video and ((i + 1) % every == 0 or i + 1 == len(t["actions"])):
                frames.append(s.api.render(cam))
        s.finish_picture_replay()
    except Exception as exc:  # noqa: BLE001
        if _from_pictures(exc):           # a picture event the rows do not reach, a capture that is not the replay's
            return {"success": False, "bad_trajectory": True,
                    "error": f"picture events: {type(exc).__name__}: {exc}"[:300]}
        raise
    v = s.judge()
    out = {"success": v.get("pass") is True, "bad_trajectory": False, "state_sha": s.state_sha(),
           "start_sha": start_sha, "n_actions": int(len(t["actions"])),
           "steps": int(sum(1 for raw in t["actions"] if t["types"][int(raw[0])] not in
                            [n for n, d in instance["control"]["action_types"].items() if d.get("text")])),
           "verdict": v}
    if video:
        import imageio.v2 as imageio  # noqa: PLC0415
        fps = max(1.0, min(30.0, 1.0 / (float(s.api.control_dt) * every)))
        with imageio.get_writer(video, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"]) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        out["video"] = True
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a trajectory file and judge it (one fresh process)")
    r.add_argument("--instance", default=INSTANCE)
    r.add_argument("--traj", default="/app/output/trajectory.npz")
    r.add_argument("--out", required=True)
    r.add_argument("--video")
    a = p.parse_args(argv)
    out = replay_file(rcb_rsb.load_instance(a.instance), a.traj, a.video)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rcb_rsb.plain(out), f)
    os.replace(tmp, a.out)
    print(json.dumps({k: v for k, v in rcb_rsb.plain(out).items() if k != "verdict"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
