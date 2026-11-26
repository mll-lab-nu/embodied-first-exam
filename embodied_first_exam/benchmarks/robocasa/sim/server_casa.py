"""Standard-mode sim service for the RoboCasa-series tasks (eai-standard/2.1): robot as a service.

Derived from the MuJoCo service (images/mujoco/limited/server_mj.py, via images/metaworld/standard/server_mw.py) and
identical to it in protocol and lifecycle: GET /spec, GET /status, POST /observe, POST /submit, binary RCB1 responses,
no reset, crash recovery (journal + per-call checkpoints, at most RCB_MAX_RESUMES resumes), startup watchdog, SIGUSR1
from the collect hook ends the episode, /data evidence. Differences, all from robosuite / RoboCasa:
- the action type is the robot's native composite-controller command, laid out per instance by the tool module
  (casa_tool.action_spec): named after its arm channels -- `ee_delta` (mobile Panda, OSC deltas), `joint_position`
  (mobile Panda, absolute joint targets) or `ee_pose` (GR1, absolute grip-site poses solved by whole-body IK);
- watching (/observe with seconds > 0) holds the robot still (S.hold_targets(): delta channels zero, the rest kept);
- cameras are the robot's own (they move with its base), so every response carries their current calibration;
- protocol v1.0 items the MuJoCo service gets in the migration (docs/protocol/README.md §7): the eai-standard/2.1 name, a
  simulator error (500) ends the episode with reason "error", an oversized body is answered with 413.

What the agent gets: camera RGB (+ depth) with each camera's calibration, the robot's own joints, end-effector
positions and last command, and the task's instruction. Never an object's pose, the scene layout or the success check.
The episode runs until the agent's time is up; the state after the last executed control step is graded.

The verdict is the live episode's (docs/protocol/README.md H.4): the environment's own success
check on the state after the last control step this service executed, not already solved at the start, and the
episode not ended by a simulator error. Nothing is replayed to grade it. The frozen initial state is checked when the
episode begins (the instance file's hash, RCB_INSTANCE_SHA, and the start state's hash, RCB_START_SHA, both from the
generator): a scene that did not build to it is refused (instance_mismatch, an infrastructure failure) before the agent
is served.

Evidence under /data: episode.jsonl (every call), calls/NNNNNN/ (meta + actions), and at the end trajectory.npz
((T, dim) per control step) and final.json with the verdict and "finalized": true, written together in one atomic step.
Only then replay.mp4 and replay.last.png are rendered, from trajectory.npz (one render pass, video_source "render"):
optional, they can add "video": true to final.json and nothing else, and no failure there (an exception, a crash, the
collect hook running out of time) changes the verdict. /data/video.pending exists (and final.json says
"video_pending": true) while that rendering runs.

A request is validated as a whole before any physics: whatever is wrong with it is a 400 and nothing ran (PROTOCOL
§4.6). Only an error while the simulator executes is a 500, which ends the episode.
"""

from __future__ import annotations

import errno
import faulthandler
import importlib
import json
import math
import os
import signal
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb1  # noqa: E402

PROTOCOL = "eai-standard/2.1"
DATA = os.environ.get("RCB_DATA", "/data")  # the evidence directory (the variable is for tests; tasks use /data)
os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TOOL = importlib.import_module(os.environ.get("RCB_TOOL", "casa_tool"))
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.npz"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
MAX_CONTROL_STEPS = int(os.environ.get("RCB_MAX_CONTROL_STEPS", "0"))  # technical episode cap (0 = none)
MAX_VIDEO_FPS = 30
MAX_FRAMES_PER_CALL = 3000  # frames x cameras per response: bounds the service's memory
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_BODY = 64 * 1024 * 1024
MAX_RESP = 256 * 1024 * 1024
LOCK = threading.Lock()
E = {"ready": False, "calls": 0, "rows": 0, "done": False, "reason": None, "t0": time.time(), "finalized": False}
E["t_first"] = None  # the agent's first request (its clock starts there: _touch, _agent_time)

# Agent-ended episodes (docs/protocol/README.md §3 "Agent-ended episodes", standard_mode.md; required for every standard
# and realtime task from protocol v2.5; the same rules as rcb_service.py's AGENT_END). RCB_AGENT_END=1: the service never
# shows the task's success and a success never ends the episode; POST /finish (JSON {}) ends it (reason "finished"),
# and so do the step cap (reason "step_limit": RCB_MAX_CONTROL_STEPS, or RCB_STEP_LIMIT=N when set, which may only lower
# it) and the end of the agent's session ("timeout"); those three ends are judged on the state they leave (END_JUDGEMENT
# says how: "state", the task's success as things stand then; "events", a goal judged on moments as they happened).
# A task's own failure rule still ends the episode with 0, after a success too.
AGENT_END = os.environ.get("RCB_AGENT_END") == "1"
STEP_LIMIT = int(os.environ.get("RCB_STEP_LIMIT") or 0) or None
if STEP_LIMIT is not None and (not AGENT_END or STEP_LIMIT < 1):
    raise RuntimeError("RCB_STEP_LIMIT needs RCB_AGENT_END=1 and a positive number of steps")
if STEP_LIMIT:
    MAX_CONTROL_STEPS = min(MAX_CONTROL_STEPS or STEP_LIMIT, STEP_LIMIT)
END_STATE_REASONS = ("finished", "timeout", "step_limit")     # ends judged on the state they leave
CAP_REASON = "step_limit" if AGENT_END else "step limit"     # the step cap's end (judged as it stands either way)
ENDED_BY = {"finished": "finish", "step_limit": "step_limit", "timeout": "session_end", "error": "error",
            "sim_crashed_on_call": "error", "sim_crashed": "error"}   # any other end: "failed" (the task's own rule)
SUCCESS_SIGNAL_NOTE = ("hidden: the service never tells you whether you have succeeded and a success does not end the "
                       "episode; POST /finish (JSON {}) ends it (if you never call it, the end of your session does) and "
                       "the episode is judged then, as the instruction's Goal says: on how things stand at that moment, "
                       "and on any steps the Goal says count as they happen; after /finish every call is refused (409)")
E.update({"now_success": False, "seen_step": None, "trial_seen": False, "finish_t": None})


def _hidden_success(ok, step: int) -> None:
    """The task's success as the state now is: kept, never latched and never shown; the episode's first one is logged."""
    E["now_success"] = bool(ok)
    if ok and E["seen_step"] is None:
        E["seen_step"], E["trial_seen"] = int(step), True
        log({"ev": "hidden_success", "control_steps": int(step)})


def _ae_state() -> dict:
    """The hidden success as a checkpoint (a completed call's log line) keeps it: a resume restores it."""
    return {"now_success": E["now_success"], "seen_step": E["seen_step"], "trial_seen": E["trial_seen"]} if AGENT_END else {}


def _ae_restore(last: dict, ev: list) -> None:
    if not AGENT_END:
        return
    E["now_success"], E["seen_step"] = bool(last.get("now_success")), last.get("seen_step")
    E["trial_seen"] = bool(last.get("trial_seen"))
    fin = [e for e in ev if e.get("ev") == "end" and e.get("reason") == "finished"]
    E["finish_t"] = fin[-1].get("finish_t") if fin else None


def _ae_fields() -> dict:
    """final.json's record of an agent-ended episode (evidence only; nothing without the feature)."""
    if not AGENT_END:
        return {}
    r, t0, ft = E["reason"], E.get("t_first"), E.get("finish_t")
    out = {"success_signal": "hidden", "ended_by": ENDED_BY.get(r, "failed") if r else None, "end_judgement": END_JUDGEMENT,
           "hidden_success_seen": E["seen_step"] is not None, "hidden_success_first_step": E["seen_step"],
           "trial_hidden_success_seen": bool(E["trial_seen"]),
           "finish_time_s": round(float(ft) - float(t0), 1) if ft and t0 else None}
    if STEP_LIMIT:
        out.update(step_limit=MAX_CONTROL_STEPS, steps_used=len(RECORD))
    return out


def _steps_left() -> dict:
    """With a step limit: the limit and what is left of it, in every meta and /status."""
    return {"step_limit": MAX_CONTROL_STEPS, "steps_left": max(0, MAX_CONTROL_STEPS - len(RECORD))} if STEP_LIMIT else {}


# the environment's own success check (_check_success) on the state the episode ends in; a task with a part that counts
# as it happens (a moment under the running water) keeps that in the environment's own check, which records it
END_JUDGEMENT = "state"

# SIGUSR1 (the collect hook's "episode over") may arrive before the service is ready, e.g. during a resume replay; its
# default action would kill the process. Until the real handler is installed, only remember it.
_USR1 = {"pending": False}
signal.signal(signal.SIGUSR1, lambda *_: _USR1.__setitem__("pending", True))

# Startup watchdog (as in server_mj.py): a scene build that hangs must end the process so compose's restart retries.
# faulthandler's C watchdog thread dumps every thread's traceback and _exit(1)s; cancelled once the scene exists.
STARTUP_TIMEOUT_S = float(os.environ.get("RCB_STARTUP_TIMEOUT_S", "300"))
faulthandler.dump_traceback_later(STARTUP_TIMEOUT_S, exit=True)

MAX_RESUMES = int(os.environ.get("RCB_MAX_RESUMES", "2"))
REC_PATH = os.path.join(DATA, "record.f64")  # journal: every executed control step's action, float64 (N,) rows
FINAL = os.path.join(DATA, "final.json")
VIDEO_PENDING = os.path.join(DATA, "video.pending")  # exists while the optional video is being rendered
VIDEO_TMP = os.path.join(DATA, "replay.tmp.mp4")  # the video under construction; renamed to replay.mp4 when complete


def _events() -> list:
    try:
        return [json.loads(line) for line in open(os.path.join(DATA, "episode.jsonl")) if line.strip()]
    except OSError:
        return []


def _dump_final(d: dict) -> None:
    """Replace final.json atomically: a reader (the collect hook, the verifier) never sees a half-written file."""
    tmp = FINAL + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FINAL)


def _load_final() -> dict:
    try:
        d = json.load(open(FINAL))
    except Exception:  # noqa: BLE001
        return {}
    return d if isinstance(d, dict) else {}


def _graded(d: dict) -> bool:
    """final.json holds a verdict: "graded_by" (the live episode's), "deterministic" (an older service's replay verdict),
    or "finalized" (a verdict, or a give-up, that is final)."""
    return bool(d.get("finalized")) or "graded_by" in d or "deterministic" in d


def _remove(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def _give_up(reason: str, infra: bool) -> None:
    """End the trial's episode without a new one: mark it failed, keep the PID file for the collect hook, and idle.
    A verdict already on disk is never overwritten (PROTOCOL §4.7), whatever else the file says: at most its missing
    "finalized" flag is set, or a "video_pending" left by a process that died rendering the video is cleared (that
    video is lost), which changes nothing the verdict says."""
    log({"ev": "restart_refused", "reason": reason})
    prev = _load_final()
    if _graded(prev):
        if not prev.get("finalized") or prev.get("video_pending"):
            prev["finalized"] = True
            prev["video_pending"] = False
            _dump_final(prev)
    else:
        prev.update({"success": False, "done": True, "reason": reason, "finalized": True, "protocol": PROTOCOL})
        if infra:
            prev["infra_error"] = 1
        _dump_final(prev)
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    signal.signal(signal.SIGUSR1, lambda *_: None)
    print(f"restart refused: {reason}", flush=True)
    while True:
        time.sleep(3600)


with open(os.path.join(DATA, "startups.jsonl"), "a") as _f:
    _f.write(json.dumps({"ts": time.time(), "pid": os.getpid()}) + "\n")
# A video that was being rendered when the process died is not resumed: clear its marker and its partial file at once
# (before the scene is rebuilt), so the collect hook stops waiting for it. The verdict on disk is not touched.
_remove(VIDEO_PENDING, VIDEO_TMP, VIDEO_TMP[:-4] + ".last.png")
# Back off before rebuilding after a failed start: compose restarts immediately.
_n_starts = sum(1 for _ in open(os.path.join(DATA, "startups.jsonl")))
if _n_starts > 1 and not os.path.exists(os.path.join(DATA, "episode.jsonl")):
    time.sleep(min(120, 20 * (_n_starts - 1)))

S = TOOL.Session(INSTANCE, enable_render=True)
E["built"] = True
faulthandler.cancel_dump_traceback_later()  # the scene exists: the startup watchdog stands down
CTRL_DT = float(S.control_dt)
N = int(S.action_dim)
NAMES = list(S.action_names)
ACTION_NAME = {12: "ee_delta", 13: "joint_position", 24: "ee_pose"}[N]
ACTION = {
    "dtype": "float64",
    "units": [c["unit"] for c in S.action_spec["channels"]],
    "kinds": [c["kind"] for c in S.action_spec["channels"]],
    "parts": S.action_spec["parts"],
    "frame": S.action_spec["frame"],
    "semantics": (
        "the robot's native composite-controller command (robosuite), applied once per control step; "
        "kinds: delta = motion per control step (0 holds still), absolute = target, grip / mode = held setting"
    ),
    **{k: S.action_spec[k] for k in ("grip", "hybrid_mode") if k in S.action_spec},
}
PROPRIO_LAYOUT = list(S.proprio_layout)
RECORD: list = []  # the episode: one action row per control step


def _cams() -> dict:
    """name -> (mujoco camera id or None, free-camera settings or None), from the session's camera_views."""
    out = {}
    for name, view in S.camera_views.items():
        out[name] = (S.model.camera(view["camera"]).id, None) if "camera" in view else (None, view)
    return out


CAMS = _cams()
W, H = 320, 240
_R = {"rgb": None, "depth": None}


def _renderer(depth: bool):
    k = "depth" if depth else "rgb"
    if _R[k] is None:
        _R[k] = S.mj.Renderer(S.model, H, W)
        if depth:
            _R[k].enable_depth_rendering()
    return _R[k]


def _update(r, cam):
    """Visual geoms only, as robosuite's own cameras (casa_tool.scene_option): no collision geoms in RGB or depth."""
    cid, free = CAMS[cam]
    if cid is not None:
        r.update_scene(S.data, camera=cid, scene_option=TOOL.scene_option())
    else:
        c = S.mj.MjvCamera()
        c.lookat[:] = free["lookat"]
        c.distance = free["distance"]
        c.azimuth = free["azimuth"]
        c.elevation = free["elevation"]
        r.update_scene(S.data, camera=c, scene_option=TOOL.scene_option())


def grab(cams, depth: bool):
    imgs, dep = {}, {}
    for c in cams:
        r = _renderer(False)
        _update(r, c)
        imgs[c] = r.render().copy()
        if depth:
            r = _renderer(True)
            _update(r, c)
            dep[c] = r.render().astype(np.float16)
    return imgs, dep


def cam2world(cam: str) -> np.ndarray:
    """Camera-to-world pose (4x4, OpenGL convention: x right, y up, looks along -z) of the viewpoint the mono RGB / depth
    image is rendered from, in the current state (as server_mj.py). A model camera (every RoboCasa camera): data.cam_xpos
    / data.cam_xmat, which is what the renderer reads. A free camera: the scene's two eye cameras share their axes and sit
    ipd/2 to either side of the viewpoint, so the viewpoint is their mean. scene.camera[0] alone is the LEFT eye, ipd/2 =
    3.4 cm to the left of the viewpoint."""
    cid, _ = CAMS[cam]
    if cid is not None:
        R = np.array(S.data.cam_xmat[cid], float).reshape(3, 3)
        pos = np.array(S.data.cam_xpos[cid], float)
    else:
        r = _renderer(False)
        _update(r, cam)
        a, b = r.scene.camera[0], r.scene.camera[1]
        fwd = np.array(a.forward, float)
        up = np.array(a.up, float)
        pos = 0.5 * (np.array(a.pos, float) + np.array(b.pos, float))
        R = np.column_stack([np.cross(fwd, up), up, -fwd])
    return np.vstack([np.column_stack([R, pos]), [0.0, 0.0, 0.0, 1.0]])


def calib() -> dict:
    """Per camera: pinhole intrinsics and the camera-to-world pose in the current state (see cam2world). The RoboCasa
    cameras are given by their vertical field of view (no sensor size), so pixels are square: fx = fy = (H / 2) /
    tan(fovy / 2), principal point at the image centre."""
    out = {}
    for c in CAMS:
        fovy = float(S.model.cam_fovy[CAMS[c][0]]) if CAMS[c][0] is not None else float(S.model.vis.global_.fovy)
        f = 0.5 * H / np.tan(np.deg2rad(fovy) / 2)
        out[c] = {
            "intrinsic_cv": [[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]],
            "cam2world_gl": cam2world(c).tolist(),
            "width": W,
            "height": H,
            "fovy_deg": fovy,
        }
    return out


def proprio() -> np.ndarray:
    return np.asarray(S.proprio(), np.float32)


def task_info() -> dict:
    return {"instruction": S.inst.get("text", "")}


SPEC = {
    "protocol": PROTOCOL,
    "simulator": "robosuite",
    "task_text": S.inst.get("text", ""),
    "control_dt": CTRL_DT,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "max_control_steps": MAX_CONTROL_STEPS or None,
    "max_video_fps": MAX_VIDEO_FPS,
    "max_frames_per_call": MAX_FRAMES_PER_CALL,
    "on_service_error": (
        "if a call fails with a connection error or 5xx, the service may have crashed and resumed the same "
        "episode (never a reset): the state is the one after the last call that completed on the service, "
        "which you may not have received; check GET /status (control_steps) before continuing"
    ),
    "cameras": {c: {"rgb": True, "depth": True, "size": [W, H]} for c in CAMS},
    "action_types": {
        ACTION_NAME: {
            "dim": N,
            "layout": NAMES,
            "lower": S.lower.tolist(),
            "upper": S.upper.tolist(),
            **ACTION,
            "rows": (
                "rows `dt` apart (a multiple of control_dt, >= control_dt); each row is applied at every control step "
                "it covers (interpolate=hold) or ramped linearly from the previous row (linear); clipped to "
                "[lower, upper]. With dt = control_dt both are the same: one row = one native action."
            ),
        },
        "not_yet": [k for k in ("ee_delta", "joint_position", "ee_pose") if k != ACTION_NAME],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "frames": "world frame: metres, z up; robot-mounted cameras move with the robot (calibration in every response)",
    "budget": {
        "reset": 0,
        "wall_clock_s": WALL_CLOCK_S,
        "clock": (
            "meta time_s / time_left_s count from your first request to the service (any endpoint), not from the "
            "service's start, and keep running through a restart of the service; time_left_s = budget.wall_clock_s - "
            "time_s. The harness counts the same limit from the start of your session, so time_left_s never runs out "
            "before the harness stops you: your real time left is time_left_s minus the time you spent before that "
            "first request. Plan by time_left_s."
        ),
    },
    "episode": "runs until your time is up; the state after the last executed control step is graded",
}
if AGENT_END:
    SPEC["success_signal"] = SUCCESS_SIGNAL_NOTE
    if STEP_LIMIT:
        SPEC["budget"]["steps"] = MAX_CONTROL_STEPS
    SPEC["episode"] = ("runs until your POST /finish or until your time is up"
                       + (f", or for at most {MAX_CONTROL_STEPS} control steps (reason step_limit)" if MAX_CONTROL_STEPS else "")
                       + "; the state after the last executed control step is graded")


def _agent_time() -> float:
    """Seconds since the agent's first request to the service (0 before it): the agent's clock. Harbor counts the
    agent's cutoff around the agent's run only, and the sidecar starts with the environment, before the harness is
    installed: counted from this process's first start, the clock would run ahead of the agent's by that set-up time (a
    median of 79 s over the recorded trials)."""
    return 0.0 if E["t_first"] is None else time.time() - E["t_first"]


def _touch() -> None:
    """Every request passes here: the first one starts the agent's clock (logged, so a resume keeps it). A probe that
    must not start it connects to the port without sending a request."""
    if E["t_first"] is None:
        E["t_first"] = time.time()
        log({"ev": "first_request", "ts": E["t_first"]})


def meta_common() -> dict:
    return {
        "calls": E["calls"],
        "rows": E["rows"],
        "control_steps": len(RECORD),
        "sim_steps": len(RECORD),
        "sim_time_s": round(len(RECORD) * CTRL_DT, 4),
        "time_s": round(_agent_time(), 2),
        "time_left_s": max(0.0, round(WALL_CLOCK_S - _agent_time(), 1)),
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio().tolist()},
        "task": task_info(),
        "cameras": calib(),  # robot-mounted cameras move: their calibration is current
        "done": E["done"],
        "reason": E["reason"],
        **_steps_left(),
    }


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), **ev}) + "\n")


def write_final(extra: dict | None = None) -> None:
    d = {
        "protocol": PROTOCOL,
        "tool": TOOL.__name__,
        "calls": E["calls"],
        "rows": E["rows"],
        "control_steps": len(RECORD),
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
        "done": E["done"],
        "reason": E["reason"],
        "finalized": E["finalized"],
    }
    d.update(E.get("verdict") or {})
    d.update(_ae_fields())
    d.update(extra or {})
    _dump_final(d)


def _every(fps: int) -> int:
    """The Recorder's capture stride: a frame every this many control steps for the requested video_fps."""
    return max(1, int(round(1.0 / (CTRL_DT * max(1, fps)))))


class Recorder:
    def __init__(self, cams, fps, depth, ring=False):
        self.cams = cams
        self.ring = ring  # a /submit's Recorder also feeds the recorder ring (eai-standard/3.0)
        self.every = _every(fps)
        self.depth = depth
        self.frames = {c: [] for c in cams}
        self.dep = {c: [] for c in cams}
        self.prop = []
        self.n = 0

    def tick(self, force=False):
        imgs, prop = {}, None
        if force or self.n % self.every == 0:
            imgs, dep = grab(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(imgs[c])
                if c in dep:
                    self.dep[c].append(dep[c])
            prop = proprio()
            self.prop.append(prop)
        if self.ring:
            _ring_record(imgs, prop, force)
        self.n += 1

    def parts(self, video: str, fps: int):
        """The response's parts, with one copy of the frames: no np.stack; frames/ and depth/ are written into the body
        from the lists (rcb1.frames_part, which hands them over), the mp4 is encoded from the list."""
        out = []
        for c in self.cams:
            fp = rcb1.frames_part(f"frames/{c}", self.frames[c], empty=np.zeros((0, H, W, 3), np.uint8))
            self.frames[c] = []
            fr = fp[2].arrays if isinstance(fp[2], rcb1.Frames) else []
            dt = fp[2].dtype if fr else np.uint8
            if video in ("mp4", "both") and len(fr):
                import imageio.v2 as imageio

                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                    path = tf.name
                try:
                    with imageio.get_writer(
                        path,
                        format="FFMPEG",
                        mode="I",
                        fps=fps,
                        codec="libx264",
                        macro_block_size=1,
                        output_params=["-movflags", "+faststart"],
                    ) as w:
                        for f in fr:
                            w.append_data(np.ascontiguousarray(f, dtype=dt))
                    data = open(path, "rb").read()
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                out.append((f"video/{c}", "mp4", data, {"fps": fps, "n": int(len(fr))}))
            last = rcb1.array_part(f"last/{c}", np.asarray(fr[-1], dtype=dt)) if len(fr) else None
            if video in ("frames", "both"):
                out.append(fp)
            else:
                fr.clear()
            if last:
                out.append(last)
            if self.dep[c]:
                out.append(rcb1.frames_part(f"depth/{c}", self.dep[c]))  # float16 at capture: 2 bytes a pixel
            self.dep[c] = []
        prop = np.stack(self.prop) if self.prop else np.zeros((0, len(PROPRIO_LAYOUT)), np.float32)
        out.append(rcb1.array_part("proprio", prop))
        return out


# ---- eai-standard/3.0 (docs/protocol/standard_mode.md): standard mode is Gym's env.step. The world is frozen between
# submits; /observe never lets time pass (`seconds` > 0 is a 400) and reads the recorder: last_s = 0 the current frame,
# last_s = n the frames recorded in the last n robot seconds. The recorder is no process of its own: during every /submit
# (a rows-free hold chunk too) it keeps every camera's RGB frame every 1 / RCB_CAMERA_FPS of robot time, with the proprio
# row and the step, in a ring of the last RCB_LOOKBACK_S robot seconds; an image the call's own Recorder grabbed at that
# step is reused, not rendered again. A rows-free hold chunk {"type", "interpolate": "hold", "seconds": n} holds the
# current target for n seconds (what /observe with seconds > 0 did before).
EAI_STANDARD = "eai-standard/3.0"
HOLD_HINT = ('observe never lets time pass (eai-standard/3.0): to let n seconds pass, submit a hold chunk {"type": <type>, '
             '"interpolate": "hold", "seconds": n} with no rows; last_s = n returns the frames recorded in the last n seconds')
RING_DT = CTRL_DT                                         # robot seconds per step of _ring_step()
RING_FPS = min(1.0 / RING_DT, max(1e-6, float(os.environ.get("RCB_CAMERA_FPS") or 10)))
RING_EVERY = max(1, int(round(1.0 / (RING_DT * RING_FPS))))
RING_S = max(0.0, float(os.environ.get("RCB_LOOKBACK_S") or 3.0))
RING_CAMS = list(CAMS)
RING: list = []      # [{"step", "imgs": {cam: uint8 HxWx3}, "prop", "pose": {cam: 4x4}}], oldest first


def _ring_step() -> int:
    return int(len(RECORD))


def _ring_record(imgs: dict, prop, force: bool = False) -> None:
    """Recorder.tick's hook during a /submit: every RING_EVERY steps (and at the call's forced first and last frame) the
    frame of every camera; `imgs` / `prop` are what the call's own Recorder has just grabbed at this step (reused)."""
    step = _ring_step()
    if not (force or step % RING_EVERY == 0) or (RING and RING[-1]["step"] == step):
        return
    if RING and step < RING[-1]["step"]:
        RING.clear()                                   # a new episode
    have = {c: imgs[c] for c in RING_CAMS if c in imgs}
    miss = [c for c in RING_CAMS if c not in have]
    if miss:
        got = grab(miss, False)[0]
        have.update({c: got[c] for c in miss if c in got})
    RING.append({"step": step, "imgs": have, "prop": proprio() if prop is None else prop, "pose": {}})
    lo = step - int(round(RING_S / RING_DT))
    while RING and RING[0]["step"] < lo:
        RING.pop(0)


def _ring_pick(last_s: float, fps: int, n_cams: int) -> list:
    """The recorded frames of the last `last_s` robot seconds (at most RING_S), `fps` apart, oldest first; [] when the ring
    does not end at the current state (nothing recorded yet in this episode)."""
    if not RING or RING[-1]["step"] != _ring_step():
        return []
    new = RING[-1]["step"]
    lo = new - int(round(min(last_s, RING_S) / RING_DT))
    gap = max(1, int(round(1.0 / (RING_DT * max(1, fps)))))
    out, nxt = [], new
    for f in reversed(RING):
        if f["step"] < lo or len(out) * max(1, n_cams) >= MAX_FRAMES_PER_CALL:
            break
        if f["step"] <= nxt:
            out.append(f)
            nxt = f["step"] - gap
    return out[::-1]


def _hold_seconds(meta: dict, parts: dict):
    """A rows-free hold chunk (eai-standard/3.0): its `seconds`, or None for a chunk of rows."""
    if meta.get("seconds") is None:
        return None
    if "actions" in parts or meta.get("actions") not in (None, []) or meta.get("rows") not in (None, []):
        raise ValueError("a chunk has either rows or `seconds` (a hold chunk without rows), not both")
    if meta.get("interpolate") != "hold":
        raise ValueError('a chunk without rows is a hold chunk: {"type": <type>, "interpolate": "hold", "seconds": n}')
    v = meta.get("seconds")
    try:
        if isinstance(v, bool):
            raise TypeError
        n = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("seconds must be a number") from None
    if not (math.isfinite(n) and 0 < n <= MAX_CHUNK_S + 1e-9):
        raise ValueError(f"a hold chunk's seconds must be in (0, max_chunk_s = {MAX_CHUNK_S:g}]")
    return n


def _last_s(meta: dict) -> float:
    """/observe's request: `seconds` > 0 is refused (HOLD_HINT); last_s >= 0 (0 = the current frame)."""
    s = meta.get("seconds")
    if s is not None:
        try:
            s = float(s)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("seconds must be a number") from None
        if s != 0:
            raise ValueError(HOLD_HINT)
    v = meta.get("last_s")
    if v is None:
        return 0.0
    try:
        if isinstance(v, bool):
            raise TypeError
        v = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("last_s must be a number of seconds") from None
    if not (math.isfinite(v) and v >= 0):
        raise ValueError("last_s must be a finite number >= 0")
    return v


SPEC["standard"] = EAI_STANDARD
SPEC["timing"] = {"recorder": {"cameras": RING_CAMS, "fps": round(1.0 / (RING_DT * RING_EVERY), 3), "buffer_s": RING_S,
                               "records": "during /submit"}}


def _ctrl_step(tg, rec) -> bool:
    """One control step with action `tg`; returns True if the episode ended (technical cap only)."""
    S.step(tg)
    row = np.asarray(S.targets, float).copy()
    RECORD.append(row)
    RECF.write(row.tobytes())
    rec.tick()
    if MAX_CONTROL_STEPS and len(RECORD) >= MAX_CONTROL_STEPS:
        finish(CAP_REASON)
        return True
    return False


def _number(meta: dict, key: str, default: float) -> float:
    """A finite number from the request; missing or null means the default."""
    v = meta.get(key)
    if v is None:
        return float(default)
    try:
        if isinstance(v, bool):  # JSON true is no number (float(True) is 1.0: `dt: true` ran as one second per row)
            raise TypeError
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be a number") from None
    if not math.isfinite(x):
        raise ValueError(f"{key} must be finite")
    return x


def _fps(meta: dict) -> int:
    fps = int(_number(meta, "video_fps", 10))
    if not 1 <= fps <= MAX_VIDEO_FPS:
        raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
    return fps


def _cameras(meta: dict, default: list) -> list:
    """The requested cameras: a list of names (or one name); missing, null or empty means the default. Names the robot
    does not have are left out; if none remains, the default is used. A repeated name is dropped BEFORE the frame
    budget and any rendering: the recorder keeps frames per name, so repeats would multiply its work."""
    v = meta.get("cameras")
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(c, str) for c in v):
        raise ValueError("cameras must be a list of camera names (see /spec cameras)")
    return list(dict.fromkeys(c for c in v if c in CAMS)) or list(default)


def _frame_budget(cams, fps: int, steps: int, depth: bool) -> None:
    """Refuse (400, before anything runs) a call of `steps` control steps whose Recorder would take more than
    MAX_FRAMES_PER_CALL images: per camera the forced first and last frame and one every _every(fps) steps (the stride
    it really films at, not the requested fps), depth counted again."""
    n = (int(steps) // _every(fps) + 2) * len(cams) * (2 if depth else 1)
    if n > MAX_FRAMES_PER_CALL:
        raise ValueError(
            f"this call would return {n} images (cameras x frames at the capture stride, depth counted again); the "
            f"limit is max_frames_per_call = {MAX_FRAMES_PER_CALL}: use fewer cameras, a lower video_fps or a shorter chunk"
        )


def _parse_hold(meta: dict, hold: float) -> dict:
    """A validated rows-free hold chunk (do_hold executes it)."""
    k = max(1, int(round(hold / CTRL_DT)))
    cams = _cameras(meta, list(CAMS)[:1])
    fps = _fps(meta)
    video = meta.get("video")
    video = "mp4" if video is None else video
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, k, depth)
    return {"hold": hold, "k": k, "cams": cams, "fps": fps, "video": video, "depth": depth, "note": str(meta.get("note") or "")[:500]}


def parse_submit(meta: dict, parts: dict) -> dict:
    """Validate a /submit as a whole, before any physics. Raises ValueError for what is wrong with it (-> 400)."""
    typ = meta.get("type")
    if typ is not None and typ != ACTION_NAME:
        raise ValueError(f"type must be {ACTION_NAME} (see /spec action_types)")
    hold = _hold_seconds(meta, parts)
    if hold is not None:  # a rows-free hold chunk: the robot held still for `seconds` (eai-standard/3.0)
        return _parse_hold(meta, hold)
    try:
        A = np.asarray(parts["actions"]["data"] if "actions" in parts else meta.get("actions", []), np.float64)
    except (TypeError, ValueError, OverflowError, KeyError):
        raise ValueError(f"{ACTION_NAME} actions must be a (T, {N}) array of numbers") from None
    if A.ndim != 2 or A.shape[1] != N:
        raise ValueError(f"{ACTION_NAME} actions must be (T, {N}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    dt = _number(meta, "dt", CTRL_DT)
    if not CTRL_DT - 1e-6 <= dt <= MAX_CHUNK_S + 1e-9:  # bounded before it is divided: no overflow below
        raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}, at most max_chunk_s={MAX_CHUNK_S}")
    k = int(round(dt / CTRL_DT))
    if k < 1 or abs(k * CTRL_DT - dt) > 1e-6:
        raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}")
    interp = meta.get("interpolate")
    interp = "linear" if interp is None else interp
    if not isinstance(interp, str) or interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    cams = _cameras(meta, list(CAMS)[:1])
    fps = _fps(meta)
    video = meta.get("video")
    video = "mp4" if video is None else video
    depth = bool(meta.get("include_depth", False))
    note = meta.get("note")
    note = "" if note is None else note
    if not isinstance(note, str):
        raise ValueError("note must be a string")
    _frame_budget(cams, fps, A.shape[0] * k, depth)
    return {
        "A": A.astype(np.float64),
        "dt": dt,
        "k": k,
        "interp": interp,
        "cams": cams,
        "fps": fps,
        "video": video,
        "depth": depth,
        "note": note[:500],
    }


def parse_observe(meta: dict) -> dict:
    """Validate an /observe as a whole, before any physics. Raises ValueError for what is wrong with it (-> 400)."""
    cams = _cameras(meta, list(CAMS))
    last_s = _last_s(meta)
    fps = _fps(meta)
    video = meta.get("video")
    video = "frames" if video is None else video
    depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, 0, depth)
    return {"cams": cams, "last_s": last_s, "fps": fps, "video": video, "depth": depth}


def run_submit(q: dict):
    """Execute a validated chunk (parse_submit's result)."""
    if "hold" in q:
        return do_hold(q)
    A, dt, k, interp, cams, fps = q["A"], q["dt"], q["k"], q["interp"], q["cams"], q["fps"]
    before = len(RECORD)
    rec = Recorder(cams, fps, q["depth"], ring=True)
    rec.tick(force=True)
    prev = np.asarray(S.targets, float).copy()
    n_clip = 0
    done = False
    executed = 0  # rows begun: fewer than the chunk's when the step limit ends the episode inside it
    for row in A:
        executed += 1
        tgt = np.clip(row, S.lower, S.upper)
        n_clip += int(np.any(tgt != row))
        for j in range(1, k + 1):
            tg = tgt if interp == "hold" else prev + (tgt - prev) * (j / k)
            if _ctrl_step(tg, rec):
                done = True
                break
        prev = tgt
        if done:
            break
    rec.tick(force=True)
    E["calls"] += 1
    E["rows"] += executed
    RECF.flush()
    if AGENT_END:
        _hidden_success(_casa_success(), len(RECORD))   # the state's success: recorded, never shown
    out = {
        **meta_common(),
        "chunk_id": E["calls"],
        "type": ACTION_NAME,
        "executed_rows": executed,
        "clipped": n_clip,
        "n_clipped_rows": n_clip,
        "duration_s": round((len(RECORD) - before) * CTRL_DT, 6),
        "planned_duration_s": round(int(A.shape[0]) * dt, 6),
        "ok": True,
    }
    log(
        {
            "ev": "submit",
            "call": E["calls"],
            "type": ACTION_NAME,
            "rows": int(A.shape[0]),
            "dt": dt,
            "interpolate": interp,
            "cameras": cams,
            "note": q["note"],
            "control_steps": len(RECORD),
            "n_clipped_rows": n_clip,
            "task": task_info(),
            "rows_total": E["rows"],
            "state_sha": S.state_sha(),
            **_ae_state(),
        }
    )
    d = os.path.join(DATA, "calls", f"{E['calls']:06d}")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "actions.npy"), A)
    return out, rec.parts(q["video"], fps)


def do_hold(q: dict):
    """A rows-free hold chunk (eai-standard/3.0): the robot held still (S.hold_targets()) for q["k"] control steps, answered
    as a /submit (what /observe with seconds > 0 did before)."""
    cams, fps, k = q["cams"], q["fps"], q["k"]
    before = len(RECORD)
    rec = Recorder(cams, fps, q["depth"], ring=True)
    rec.tick(force=True)
    hold = S.hold_targets()
    for _ in range(k):
        if _ctrl_step(hold, rec):
            break
    rec.tick(force=True)
    E["calls"] += 1
    RECF.flush()
    if AGENT_END:
        _hidden_success(_casa_success(), len(RECORD))   # the state's success: recorded, never shown
    out = {
        **meta_common(),
        "chunk_id": E["calls"],
        "type": ACTION_NAME,
        "hold": True,
        "executed_rows": 0,
        "clipped": 0,
        "n_clipped_rows": 0,
        "duration_s": round((len(RECORD) - before) * CTRL_DT, 6),
        "planned_duration_s": round(q["hold"], 6),
        "ok": True,
    }
    log(
        {
            "ev": "submit",
            "call": E["calls"],
            "type": ACTION_NAME,
            "rows": 0,
            "hold_s": q["hold"],
            "cameras": cams,
            "note": q["note"],
            "control_steps": len(RECORD),
            "n_clipped_rows": 0,
            "task": task_info(),
            "rows_total": E["rows"],
            "state_sha": S.state_sha(),
            **_ae_state(),
        }
    )
    return out, rec.parts(q["video"], fps)


def run_observe(q: dict):
    """/observe never lets time pass (eai-standard/3.0): last_s = 0 the current frame, last_s = n the recorder's frames of
    the last n robot seconds (none recorded yet: the current frame)."""
    cams, last_s, fps, video = q["cams"], q["last_s"], q["fps"], q["video"]
    pick = _ring_pick(last_s, fps, len(cams)) if last_s > 0 else []
    E["calls"] += 1
    log(
        {
            "ev": "observe",
            "call": E["calls"],
            "last_s": last_s,
            "cameras": cams,
            "control_steps": len(RECORD),
            "rows_total": E["rows"],
            "state_sha": S.state_sha(),
            **_ae_state(),
        }
    )
    if not pick:
        rec = Recorder(cams, fps, q["depth"])
        rec.tick(force=True)
        out = {**meta_common(), "obs_id": E["calls"], "last_s": 0.0, "frame_step": len(RECORD), "ok": True}
        return out, rec.parts("frames" if video == "mp4" else video, fps)
    rec = Recorder(cams, fps, False)
    for f in pick:
        for c in cams:
            rec.frames[c].append(f["imgs"][c])
        rec.prop.append(f["prop"])
    steps = np.asarray([f["step"] for f in pick], np.int64)
    out = {**meta_common(), "obs_id": E["calls"], "last_s": round(float(steps[-1] - steps[0]) * CTRL_DT, 4),
           "frame_step": int(steps[-1]), "ok": True}
    return out, rec.parts(video, fps) + [rcb1.array_part("frame_step", steps)]


def _render_video(A: np.ndarray) -> None:
    """The video: strictly optional, and only after the verdict is final on disk. One render pass: the live session is
    rebuilt from the frozen instance and runs the recorded trajectory again with its camera on (nothing is compared or
    judged; the agent's container is gone and LOCK keeps requests out meanwhile). It is rendered under a temporary name
    and renamed when complete; success adds "video": true to final.json and nothing else. Any failure here (an
    exception; a crash, after which the restarted service finds the verdict and idles; the collect hook giving up on
    it) leaves the verdict exactly as finalize() wrote it."""
    t = time.time()
    try:
        S.render_video(A, VIDEO_TMP, every=max(2, len(A) // 300), fps=10)
        os.replace(VIDEO_TMP[:-4] + ".last.png", os.path.join(DATA, "replay.last.png"))
        os.replace(VIDEO_TMP, os.path.join(DATA, "replay.mp4"))
        E["verdict"]["video"] = True
        log({"ev": "video", "video_s": round(time.time() - t, 1)})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        try:
            log({"ev": "video_error", "error": repr(exc)[:300], "video_s": round(time.time() - t, 1)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        E["verdict"]["video_pending"] = False
        try:
            if _load_final().get("finalized"):
                write_final()  # "video" and "video_pending" only: the verdict's fields are E["verdict"]'s, unchanged
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        _remove(VIDEO_PENDING, VIDEO_TMP, VIDEO_TMP[:-4] + ".last.png")


def finalize() -> None:
    """The episode is over: the verdict is the live episode's (docs/protocol/README.md H.4).
    success = the environment's success check (`_check_success`, as the live episode last ran it) holds on the state
    after the last executed control step, the scene was not solved at the start, and the episode did not end on a
    simulator error (whose state is the partial step's, not the last executed one). Nothing is replayed to grade it.
    The trajectory and the verdict with "finalized": true are written (one atomic write of final.json); then, and only
    then, the optional video is rendered from the trajectory."""
    with LOCK:
        A = None
        try:
            A = np.asarray(RECORD, float).reshape(-1, N)
            live_sha = S.state_sha()
            live = S.check()
            initial = bool(getattr(S, "initial_success", False))
            np.savez(
                os.path.join(DATA, "trajectory.npz"),
                actions=A,
                tool=TOOL.__name__,
                meta=json.dumps({"source": "standard-mode episode", "reason": E["reason"]}),
            )
            live_ok = bool(live["success"])
            E["verdict"] = {
                "graded_by": "live",
                "replays": 0,
                "live_success": live_ok,
                "initial_success": initial,
                "success": bool(live_ok and not initial and E["reason"] != "error"
                                and (not AGENT_END or E["reason"] in END_STATE_REASONS)),
                "live_state_sha": live_sha,
                "state_sha": live_sha,
                "final_reward": float(live.get("reward") or 0.0),
                "n_actions": int(len(A)),
                "video": False,
                "video_pending": True,
                "video_source": "render",
            }
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            log({"ev": "finalize_error", "error": repr(exc)})
            E["verdict"] = {"finalize_error": repr(exc)[:300], "graded_by": "live", "replays": 0}
            A = None
        if A is not None:
            # Announced before the verdict is written: whoever sees the verdict also sees that a video is on its way.
            open(VIDEO_PENDING, "w").close()
        E["finalized"] = True
        write_final()  # the verdict and "finalized": true, in one atomic write; nothing below changes them
        if A is not None:
            log({"ev": "verdict", "control_steps": int(len(A)), "success": E["verdict"]["success"],
                 "live_success": E["verdict"]["live_success"]})
            _render_video(A)


def _casa_success() -> bool:
    """The task's success as the state now is (the check as the live episode last ran it; a scene solved at the start
    never counts): recorded for an agent-ended episode, never shown."""
    return bool(S.check()["success"]) and not bool(getattr(S, "initial_success", False))


def finish(reason: str) -> None:
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    if AGENT_END and reason == "finished":
        E["finish_t"] = E["t_end"]
    log({"ev": "end", "reason": reason, "control_steps": len(RECORD), **({"finish_t": E["finish_t"]} if reason == "finished" else {})})
    write_final()


def _status() -> dict:
    return {"calls": E["calls"], "control_steps": len(RECORD), "sim_steps": len(RECORD), "rows": E["rows"], "done": E["done"],
            "reason": E["reason"], "elapsed_s": round(time.time() - E["t0"], 1), **_steps_left()}


def start_finalize() -> None:
    if E.get("finalizing"):
        return
    E["finalizing"] = True
    threading.Thread(target=finalize, daemon=True).start()


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _rcb1(self, meta, parts):
        if rcb1.size(meta, parts) > MAX_RESP:  # known before anything is built: the body is built once
            for p in parts:
                if p[0].startswith(("frames/", "depth/")) and isinstance(p[2], rcb1.Frames):
                    p[2].arrays.clear()
            parts = [p for p in parts if not (p[0].startswith("frames/") or p[0].startswith("depth/"))]
            meta = {**meta, "degraded": "frames/depth dropped (response too large)"}
        body = rcb1.encode(meta, parts)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-rcb1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        raw = self.rfile.read(self._n) if self._n else b""
        if raw[:4] == rcb1.MAGIC:
            meta, parts = rcb1.decode(raw)
            if not isinstance(meta, dict):
                raise ValueError("the RCB1 header's meta must be a JSON object")
            return meta, parts
        b = json.loads(raw or b"{}")
        if not isinstance(b, dict):
            raise ValueError("body must be a JSON object or an RCB1 frame")
        return b, {}

    def do_GET(self):
        _touch()
        if self.path == "/spec":
            return self._json(200, SPEC)
        if self.path == "/status":
            return self._json(200, _status())
        return self._json(404, {"error": "no such endpoint"})

    def do_POST(self):
        _touch()
        if self.path not in ("/submit", "/observe") + (("/finish",) if AGENT_END else ()):
            return self._json(404, {"error": "no such endpoint"})
        try:
            self._n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            self._n = -1
        if self._n < 0:  # read(-1) would read until the client hangs up, without any bound
            return self._json(400, {"error": "bad Content-Length"})
        if self._n > MAX_BODY:
            return self._json(413, {"error": f"request body over {MAX_BODY} bytes"})
        try:
            self._req = self._body()
        except Exception as exc:  # noqa: BLE001
            return self._json(400, {"error": str(exc)[:200]})
        with LOCK:
            log({"ev": "call_begin", "path": self.path, "call": E["calls"] + 1})
            try:
                return self._serve()
            finally:
                log({"ev": "call_end", "path": self.path})

    def _serve(self):
        meta, parts = self._req
        if self.path == "/finish":  # agent-ended episodes: the agent ends the episode; the state it leaves is graded
            if E["done"] or E.get("finalizing"):
                return self._json(409, {"error": "episode finished", "reason": E["reason"]})
            finish("finished")
            return self._json(200, {"ok": True, **_status()})
        if self.path == "/observe" and AGENT_END and E["done"] and E["reason"] == "finished":
            return self._json(409, {"error": "episode finished", "reason": E["reason"]})  # after /finish: /spec, /status only
        submit = self.path == "/submit"
        if submit and E["done"]:
            return self._json(409, {"error": "episode finished", "reason": E["reason"]})
        # 1. Validation: nothing has run yet, so whatever is wrong here is the request's fault and a 400; it never ends
        #    the episode (PROTOCOL §4.6). ValueError carries the explanation; any other exception is a field of a type
        #    the checks did not expect.
        try:
            q = parse_submit(meta, parts) if submit else parse_observe(meta)
        except ValueError as exc:
            return self._json(400, {"error": str(exc)[:500]})
        except Exception as exc:  # noqa: BLE001
            return self._json(400, {"error": f"malformed request ({type(exc).__name__}: {str(exc)[:200]})"})
        # 2. Execution: an error from here on is the simulator's (500) and ends the episode.
        try:
            out, blobs = run_submit(q) if submit else run_observe(q)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            log({"ev": "error", "error": repr(exc)})
            finish("error")  # protocol v1.0 §4.6: a simulator error ends the episode
            return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        return self._rcb1(out, blobs)


def _end_from_signal():
    with LOCK:
        if not E["done"]:
            finish("timeout")
    start_finalize()


_renderer(False)  # opens the renderer before the first request
calib()


def _start_mismatch(sha: str) -> str | None:
    """Why the scene just built is not the frozen instance's start, or None. The verdict is the live episode's, so no
    later replay from the frozen instance checks the start: it is checked here, before the agent is served (board
    0151). RCB_INSTANCE_SHA: the instance's own hash (casa_tool checks the file against it on load; this checks that the
    file is the task's frozen instance); RCB_START_SHA: the state hash a fresh episode of this instance starts in
    (scripts/<benchmark>/frozen/start_state.json). A frozen instance is never solved at its start (the generator only
    publishes verified ones), so a scene that is is not that instance either."""
    want = os.environ.get("RCB_INSTANCE_SHA", "")
    have = str(getattr(S, "instance_sha", ""))
    if want and have != want:
        return f"the instance file has hash {have[:16]}, the task's frozen instance {want[:16]}"
    want = os.environ.get("RCB_START_SHA", "")
    if want and sha != want:
        return f"the scene starts in state {sha[:16]}, the frozen instance in {want[:16]}"
    if getattr(S, "initial_success", False):
        return "the scene is solved at the start; the frozen instance is not"
    return None


def _resume_or_start() -> None:
    """Fresh start, or (after a crash: compose restarts the container) resume the SAME episode. The journal holds every
    executed control step; the log holds, per completed call, the step count and the state hash. Replaying the journal up
    to the last completed call rebuilds that exact state (MuJoCo on the CPU is bit-exact) and the hash is checked. A call
    in flight when the service died is lost as a whole; its caller got an error, not a result, so nothing is gained. No
    reset: the episode never goes back to its start. More than MAX_RESUMES crashes end it; if every crash happened while
    serving a call, it counts as the agent's (sim_crashed_on_call), else as infrastructure (sim_crashed)."""
    ev = _events()
    starts = [e for e in ev if e.get("ev") == "start"]
    if not starts:
        try:
            os.remove(REC_PATH)
        except OSError:
            pass
        sha = S.state_sha()
        log({"ev": "start", "tool": TOOL.__name__, "state_sha": sha, "protocol": PROTOCOL})
        bad = _start_mismatch(sha)
        if bad:  # before the port is bound: the agent is never served a scene that is not the task's
            _give_up(f"instance_mismatch: {bad}", infra=True)
        write_final()
        E["t0"] = time.time()
        return
    fin = _load_final()
    if _graded(fin):  # the verdict is on disk: nothing is replayed, redone or rewritten
        _give_up("restarted after finalize", infra=False)
    resumes = [e for e in ev if e.get("ev") == "resumed"]
    in_call = bool(ev) and ev[-1].get("ev") == "call_begin"
    crashes_in_calls = sum(1 for e in resumes if e.get("crashed_in_call")) + int(in_call)
    if len(resumes) >= MAX_RESUMES:
        all_in_calls = crashes_in_calls == len(resumes) + 1
        _give_up("sim_crashed_on_call" if all_in_calls else "sim_crashed", infra=not all_in_calls)
    done = [e for e in ev if e.get("ev") in ("submit", "observe") and "state_sha" in e]
    last = done[-1] if done else starts[0]
    n = int(last.get("control_steps", 0))
    try:
        R = np.fromfile(REC_PATH, dtype=np.float64)
    except OSError:
        R = np.zeros(0)
    if R.size < n * N:
        _give_up("resume_failed: journal shorter than the log", infra=True)
    R = R[: n * N].reshape(n, N)
    for row in R:
        S.step(row)
        RECORD.append(row.copy())
    if S.state_sha() != last["state_sha"]:
        _give_up("resume_failed: replayed state differs from the logged one", infra=True)
    R.tofile(REC_PATH)  # drop the steps of the call that was in flight
    E["calls"] = int(last.get("call", 0))
    E["rows"] = int(last.get("rows_total", 0))
    E["t0"] = float(starts[0]["ts"])
    first = [e for e in ev if e.get("ev") == "first_request"]
    if first:
        E["t_first"] = float(first[0]["ts"])  # the agent's clock keeps running through a crash, never back to full
    # the episode's end, if it is within the last completed call: an end past it (the step limit hit by the call that was
    # in flight) was lost with that call, as the call itself
    ended = [e for e in ev if e.get("ev") == "end" and int(e.get("control_steps") or 0) <= n]
    if ended:
        E["done"] = True
        E["reason"] = ended[-1].get("reason")
        E["t_end"] = float(ended[-1]["ts"])
    _ae_restore(last, ev)  # the hidden success of the episode, as the checkpoint had it
    log(
        {
            "ev": "resumed",
            "control_steps": n,
            "calls": E["calls"],
            "state_sha": S.state_sha(),
            "crashed_in_call": in_call,
            "downtime_s": round(time.time() - float(ev[-1]["ts"]), 1),
        }
    )
    write_final()


def _bind(port: int, handler) -> HTTPServer:
    """The listening server. Under Harbor's egress control the agent's container shares this network namespace, so a
    process of the agent may hold the port when the service (re)starts. Wait for the port instead of failing: an
    exception here would count as a crash of the service (the collect hook's signal is still served meanwhile)."""
    said = False
    while True:
        try:
            return HTTPServer(("0.0.0.0", port), handler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
        if not said:
            said = True
            print(f"[sim] port {port} is in use (a process in the agent's container?): waiting for it to be free", flush=True)
        time.sleep(1.0)


_resume_or_start()
signal.signal(signal.SIGUSR1, lambda *_: threading.Thread(target=_end_from_signal, daemon=True).start())
if _USR1["pending"]:
    threading.Thread(target=_end_from_signal, daemon=True).start()
RECF = open(REC_PATH, "ab")
E["ready"] = True
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} RoboCasa sim ready ({TOOL.__name__}: {S.inst.get('env_name')})", flush=True)
_bind(int(os.environ.get("RCB_PORT", "8000")), Hd).serve_forever()  # RCB_PORT: for tests, as RCB_DATA
