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
- protocol v1.0 items the MuJoCo service gets in the migration (docs/PROTOCOL.md §7): the eai-standard/2.1 name, a
  simulator error (500) ends the episode with reason "error", an oversized body is answered with 413.

What the agent gets: camera RGB (+ depth) with each camera's calibration, the robot's own joints, end-effector
positions and last command, and the task's instruction. Never an object's pose, the scene layout or the success check.
The episode runs until the agent's time is up; the state after the last executed control step is graded.

Evidence under /data: episode.jsonl (every call), calls/NNNNNN/ (meta + actions), and at the end trajectory.npz
((T, dim) per control step) and final.json with a fresh replay's verdict (deterministic = same final state hash) and
"finalized": true, written together in one atomic step. Only then replay.mp4 and replay.last.png are rendered (a second
replay): optional, they can add "video": true to final.json and nothing else, and no failure there (an exception, a
crash, the collect hook running out of time) changes the verdict. /data/video.pending exists while that rendering runs.

A request is validated as a whole before any physics: whatever is wrong with it is a 400 and nothing ran (PROTOCOL
§4.6). Only an error while the simulator executes is a 500, which ends the episode.
"""

from __future__ import annotations

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
VIDEO_PENDING = os.path.join(DATA, "video.pending")  # exists while the optional replay video is being rendered
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


def _remove(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def _give_up(reason: str, infra: bool) -> None:
    """End the trial's episode without a new one: mark it failed, keep the PID file for the collect hook, and idle.
    A verdict already on disk (final.json has "deterministic") is never overwritten (PROTOCOL §4.7), whatever else the
    file says: at most its missing "finalized" flag is set, which changes nothing the verdict says."""
    log({"ev": "restart_refused", "reason": reason})
    prev = _load_final()
    if "deterministic" in prev:
        if not prev.get("finalized"):
            prev["finalized"] = True
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
# time_left_s counts from the first start of this process: the sidecar starts together with the agent's container, so
# that is the agent's own clock to within a second or two (earlier, when the harness sets the agent up first), not the
# end of the scene build 20-60 s later. The episode's own clock (E["t0"]: time_s, elapsed_s) starts when the service is
# ready.
try:
    with open(os.path.join(DATA, "startups.jsonl")) as _f:
        T_BOOT = float(json.loads(_f.readline())["ts"])
except Exception:  # noqa: BLE001
    T_BOOT = time.time()

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


def calib() -> dict:
    """Per camera: pinhole intrinsics and camera-to-world pose (OpenGL convention: looks along -z, +y up)."""
    out = {}
    r = _renderer(False)
    for c in CAMS:
        _update(r, c)
        gl = r.scene.camera[0]
        fwd = np.array(gl.forward, float)
        up = np.array(gl.up, float)
        pos = np.array(gl.pos, float)
        right = np.cross(fwd, up)
        R = np.column_stack([right, up, -fwd])
        fovy = float(S.model.cam_fovy[CAMS[c][0]]) if CAMS[c][0] is not None else float(S.model.vis.global_.fovy)
        f = 0.5 * H / np.tan(np.deg2rad(fovy) / 2)
        out[c] = {
            "intrinsic_cv": [[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]],
            "cam2world_gl": np.vstack([np.column_stack([R, pos]), [0, 0, 0, 1]]).tolist(),
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
    "budget": {"reset": 0, "wall_clock_s": WALL_CLOCK_S},
    "episode": "runs until your time is up; the state after the last executed control step is graded",
}


def meta_common() -> dict:
    return {
        "calls": E["calls"],
        "rows": E["rows"],
        "control_steps": len(RECORD),
        "sim_steps": len(RECORD),
        "sim_time_s": round(len(RECORD) * CTRL_DT, 4),
        "time_s": round(time.time() - E["t0"], 2),
        "time_left_s": max(0.0, round(WALL_CLOCK_S - (time.time() - T_BOOT), 1)),
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio().tolist()},
        "task": task_info(),
        "cameras": calib(),  # robot-mounted cameras move: their calibration is current
        "done": E["done"],
        "reason": E["reason"],
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
    d.update(extra or {})
    _dump_final(d)


class Recorder:
    def __init__(self, cams, fps, depth):
        self.cams = cams
        self.every = max(1, int(round(1.0 / (CTRL_DT * max(1, fps)))))
        self.depth = depth
        self.frames = {c: [] for c in cams}
        self.dep = {c: [] for c in cams}
        self.prop = []
        self.n = 0

    def tick(self, force=False):
        if force or self.n % self.every == 0:
            imgs, dep = grab(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(imgs[c])
                if c in dep:
                    self.dep[c].append(dep[c])
            self.prop.append(proprio())
        self.n += 1

    def parts(self, video: str, fps: int):
        out = []
        for c in self.cams:
            fr = np.stack(self.frames[c]) if self.frames[c] else np.zeros((0, H, W, 3), np.uint8)
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
                            w.append_data(np.ascontiguousarray(f))
                    data = open(path, "rb").read()
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                out.append((f"video/{c}", "mp4", data, {"fps": fps, "n": int(len(fr))}))
            if video in ("frames", "both"):
                out.append(rcb1.array_part(f"frames/{c}", fr))
            if len(fr):
                out.append(rcb1.array_part(f"last/{c}", fr[-1]))
            if self.dep[c]:
                out.append(rcb1.array_part(f"depth/{c}", np.stack(self.dep[c])))
        prop = np.stack(self.prop) if self.prop else np.zeros((0, len(PROPRIO_LAYOUT)), np.float32)
        out.append(rcb1.array_part("proprio", prop))
        return out


def _ctrl_step(tg, rec) -> bool:
    """One control step with action `tg`; returns True if the episode ended (technical cap only)."""
    S.step(tg)
    row = np.asarray(S.targets, float).copy()
    RECORD.append(row)
    RECF.write(row.tobytes())
    rec.tick()
    if MAX_CONTROL_STEPS and len(RECORD) >= MAX_CONTROL_STEPS:
        finish("step limit")
        return True
    return False


def _number(meta: dict, key: str, default: float) -> float:
    """A finite number from the request; missing or null means the default."""
    v = meta.get(key)
    if v is None:
        return float(default)
    try:
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
    does not have are left out; if none remains, the default is used."""
    v = meta.get("cameras")
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(c, str) for c in v):
        raise ValueError("cameras must be a list of camera names (see /spec cameras)")
    return [c for c in v if c in CAMS] or list(default)


def _frame_budget(cams, fps: int, seconds: float, depth: bool) -> None:
    n = (int(seconds * fps) + 2) * len(cams) * (2 if depth else 1)
    if n > MAX_FRAMES_PER_CALL:
        raise ValueError(
            f"this call would return {n} frames (cameras x fps x seconds, depth counts double); the limit is "
            f"{MAX_FRAMES_PER_CALL}: use fewer cameras, a lower video_fps or a shorter chunk"
        )


def parse_submit(meta: dict, parts: dict) -> dict:
    """Validate a /submit as a whole, before any physics. Raises ValueError for what is wrong with it (-> 400)."""
    typ = meta.get("type")
    if typ is not None and typ != ACTION_NAME:
        raise ValueError(f"type must be {ACTION_NAME} (see /spec action_types)")
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
    _frame_budget(cams, fps, A.shape[0] * dt, depth)
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
    seconds = _number(meta, "seconds", 0.0)
    if not 0 <= seconds <= MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    fps = _fps(meta)
    video = meta.get("video")
    video = "frames" if video is None else video
    depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, seconds, depth)
    return {"cams": cams, "seconds": seconds, "fps": fps, "video": video, "depth": depth}


def run_submit(q: dict):
    """Execute a validated chunk (parse_submit's result)."""
    A, dt, k, interp, cams, fps = q["A"], q["dt"], q["k"], q["interp"], q["cams"], q["fps"]
    rec = Recorder(cams, fps, q["depth"])
    rec.tick(force=True)
    prev = np.asarray(S.targets, float).copy()
    n_clip = 0
    done = False
    for row in A:
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
    E["rows"] += int(A.shape[0])
    RECF.flush()
    out = {
        **meta_common(),
        "chunk_id": E["calls"],
        "type": ACTION_NAME,
        "executed_rows": int(A.shape[0]),
        "clipped": n_clip,
        "n_clipped_rows": n_clip,
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
        }
    )
    d = os.path.join(DATA, "calls", f"{E['calls']:06d}")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "actions.npy"), A)
    return out, rec.parts(q["video"], fps)


def run_observe(q: dict):
    """Execute a validated observation (parse_observe's result)."""
    cams, seconds, fps, video = q["cams"], q["seconds"], q["fps"], q["video"]
    rec = Recorder(cams, fps, q["depth"])
    rec.tick(force=True)
    if seconds > 0 and not E["done"]:
        hold = S.hold_targets()  # delta channels zero, targets / grip / mode kept: the robot holds still
        for _ in range(int(round(seconds / CTRL_DT))):
            if _ctrl_step(hold, rec):
                break
        rec.tick(force=True)
    E["calls"] += 1
    RECF.flush()
    log(
        {
            "ev": "observe",
            "call": E["calls"],
            "seconds": seconds,
            "cameras": cams,
            "control_steps": len(RECORD),
            "rows_total": E["rows"],
            "state_sha": S.state_sha(),
        }
    )
    out = {**meta_common(), "obs_id": E["calls"], "seconds": seconds, "ok": True}
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def _render_video(ver, A: np.ndarray) -> None:
    """The replay video: strictly optional, and only after the verdict is final on disk. It is rendered under a
    temporary name and renamed when complete; success adds "video": true to final.json and nothing else. Any failure
    here (an exception; a crash, after which the restarted service finds the verdict and idles; the collect hook giving
    up on it) leaves final.json exactly as finalize() wrote it."""
    t = time.time()
    try:
        ver.render_video(A, VIDEO_TMP, every=max(2, len(A) // 300), fps=10)
        os.replace(VIDEO_TMP[:-4] + ".last.png", os.path.join(DATA, "replay.last.png"))
        os.replace(VIDEO_TMP, os.path.join(DATA, "replay.mp4"))
        d = _load_final()
        if d.get("finalized") and "deterministic" in d:
            d["video"] = True
            _dump_final(d)
            E["verdict"]["video"] = True
        log({"ev": "video", "video_s": round(time.time() - t, 1)})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        try:
            log({"ev": "video_error", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
    finally:
        _remove(VIDEO_PENDING, VIDEO_TMP, VIDEO_TMP[:-4] + ".last.png")


def finalize() -> None:
    """The episode is over: replay it in a fresh simulator and write the verdict together with "finalized": true (one
    atomic write of final.json), then, and only then, render the optional video."""
    with LOCK:
        t = time.time()
        ver = A = None
        try:
            A = np.asarray(RECORD, float).reshape(-1, N)
            live_sha = S.state_sha()
            live = S.check()
            np.savez(
                os.path.join(DATA, "trajectory.npz"),
                actions=A,
                tool=TOOL.__name__,
                meta=json.dumps({"source": "standard-mode episode", "reason": E["reason"]}),
            )
            ver = TOOL.Session(INSTANCE, enable_render=True)
            r1 = ver.replay(A)
            det = r1["state_sha"] == live_sha
            E["verdict"] = {
                "deterministic": bool(det),
                "live_state_sha": live_sha,
                "replay_success": bool(r1["success"]),
                "live_success": bool(live["success"]),
                "initial_success": bool(r1["initial_success"]),
                "success": bool(det and r1["success"] and live["success"] and not r1["initial_success"]),
                "final_reward": float(r1["final_reward"]),
            }
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            log({"ev": "finalize_error", "error": repr(exc)})
            E["verdict"] = {"finalize_error": repr(exc)[:300]}
            ver = None
        if ver is not None:
            # Announced before the verdict is written: whoever sees the verdict also sees that a video is on its way.
            open(VIDEO_PENDING, "w").close()
        E["finalized"] = True
        write_final()  # the verdict and "finalized": true, in one atomic write; nothing below changes them
        if ver is not None:
            log({"ev": "verdict", "control_steps": int(len(A)), "verify_s": round(time.time() - t, 1)})
            _render_video(ver, A)


def finish(reason: str) -> None:
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    log({"ev": "end", "reason": reason, "control_steps": len(RECORD)})
    write_final()


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
        body = rcb1.encode(meta, parts)
        if len(body) > MAX_RESP:
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
        if self.path == "/spec":
            return self._json(200, SPEC)
        if self.path == "/status":
            return self._json(
                200,
                {
                    "calls": E["calls"],
                    "control_steps": len(RECORD),
                    "sim_steps": len(RECORD),
                    "rows": E["rows"],
                    "done": E["done"],
                    "reason": E["reason"],
                    "elapsed_s": round(time.time() - E["t0"], 1),
                },
            )
        return self._json(404, {"error": "no such endpoint"})

    def do_POST(self):
        if self.path not in ("/submit", "/observe"):
            return self._json(404, {"error": "no such endpoint"})
        try:
            self._n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
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


calib()  # opens the renderer before the first request


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
        log({"ev": "start", "tool": TOOL.__name__, "state_sha": S.state_sha(), "protocol": PROTOCOL})
        write_final()
        E["t0"] = time.time()
        return
    fin = _load_final()
    if "deterministic" in fin:  # the verdict is on disk: nothing is replayed, redone or rewritten
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
    ended = [e for e in ev if e.get("ev") == "end"]
    if ended:
        E["done"] = True
        E["reason"] = ended[-1].get("reason")
        E["t_end"] = float(ended[-1]["ts"])
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


_resume_or_start()
signal.signal(signal.SIGUSR1, lambda *_: threading.Thread(target=_end_from_signal, daemon=True).start())
if _USR1["pending"]:
    threading.Thread(target=_end_from_signal, daemon=True).start()
RECF = open(REC_PATH, "ab")
E["ready"] = True
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} RoboCasa sim ready ({TOOL.__name__}: {S.inst.get('env_name')})", flush=True)
HTTPServer(("0.0.0.0", 8000), Hd).serve_forever()
