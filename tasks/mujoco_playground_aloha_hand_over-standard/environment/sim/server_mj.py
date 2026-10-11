"""eai-standard/2.1 sim service for the MuJoCo tasks (DexToolBench, MuJoCo Playground): robot as a service.

The sidecar owns the simulator (the task's tooling module, RCB_TOOL = rcb_dtb | rcb_aloha | rcb_panda, with the task's
frozen instance) and serves the same wire protocol as the RoboTwin limited tasks (docs/STANDARD_MODE.md), so
the agent uses the same client (rcb_client.py): GET /spec, GET /status, POST /observe, POST /submit, binary RCB1
responses. What the agent gets: camera RGB (+ depth, with each camera's intrinsics and pose: the viewpoint the image is
rendered from, recomputed for every response, and per frame for a camera that moves), the robot's own joint
positions, velocities and current targets, and the task's definition (DexToolBench: the current goal pose and its index,
as SimToolReal's deployment gives its policy; Playground: the target). Never the object's pose.

Actions: `joint_position` rows (the tooling's N actuator targets), each held for `dt` (a multiple of the control step,
hold or linear interpolation per control step). DexToolBench episodes end when all goals are reached, when a goal times
out (only if RCB_DTB_GOAL_TIMEOUT_S > 0; the standard twins set 0), at RCB_MAX_CONTROL_STEPS, or when the agent's time is
up; Playground episodes run until the agent phase ends and the final state is graded.

Evidence under /data: episode.jsonl (every call), calls/NNNNNN/ (meta + actions), and at the end trajectory.npz
((T, N) per control step), a fresh replay's verdict (deterministic = same final state hash), replay.mp4 and final.json.
The collect hook ends the episode with SIGUSR1. final.json is `finalized` as soon as the verdict is in it; the video is
rendered after that and never changes or delays the verdict (`video_done` tells the collect hook that nothing more comes).

Requests are validated in full before any physics runs: a malformed one (dt / seconds / video_fps not a finite number,
cameras not a list of names, ...) is answered 400 and changes nothing; only a failure of the simulator itself is a 500
that ends the episode. `time_s` / `time_left_s` count from the agent's first request to the service."""
from __future__ import annotations
import errno, importlib, json, math, os, signal, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RCB_SESSION_LOG"] = ""; os.environ["RCB_AGENT_TRACE_DIR"] = ""
import rcb1  # noqa: E402

PROTOCOL = "eai-standard/2.1"
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)   # RCB_DATA / RCB_PORT: test hooks (never set in tasks)
TOOL = importlib.import_module(os.environ.get("RCB_TOOL", "rcb_dtb"))
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
# Episode cap in control steps (0 = none). Set where nothing else ends the episode, e.g. DexToolBench without its per-goal
# time limit (the standard twins: RCB_DTB_GOAL_TIMEOUT_S=0, RCB_MAX_CONTROL_STEPS=360000 = 100 min of robot time).
MAX_CONTROL_STEPS = int(os.environ.get("RCB_MAX_CONTROL_STEPS", "0"))
MAX_VIDEO_FPS = 30; MAX_FRAMES_PER_CALL = 3000   # frames x cameras per response: bounds the service's memory
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_BODY = 64 * 1024 * 1024; MAX_RESP = 256 * 1024 * 1024
LOCK = threading.Lock()
E = {"ready": False, "calls": 0, "rows": 0, "done": False, "reason": None, "t0": time.time(), "finalized": False,
     "t_first": None, "video_done": False}   # t_first: the agent's first request (its clock starts there)

# SIGUSR1 (the collect hook's "episode over") may arrive before the service is ready, e.g. during a resume replay; its
# default action would kill the process. Until the real handler is installed, only remember it.
_USR1 = {"pending": False}
signal.signal(signal.SIGUSR1, lambda *_: _USR1.__setitem__("pending", True))

# Startup watchdog: a scene build that hangs (seen under GPU memory pressure: no crash, so compose never restarted it)
# must end the process so compose's restart (on-failure) retries. Neither a Python thread (it needs the GIL, which a hang
# inside native SAPIEN/Vulkan init may hold) nor SIGALRM's default action (the service is PID 1 in its container, and
# PID 1 ignores default-action signals) can do it; faulthandler's C watchdog thread can: it dumps every thread's
# traceback to stderr (the container log: where it hung) and _exit(1)s. Cancelled as soon as the scene exists (a resume
# replay may take minutes). Before the scene exists no episode exists, so the retry is not a reset.
import faulthandler  # noqa: E402
STARTUP_TIMEOUT_S = float(os.environ.get("RCB_STARTUP_TIMEOUT_S", "300"))
faulthandler.dump_traceback_later(STARTUP_TIMEOUT_S, exit=True)


MAX_RESUMES = int(os.environ.get("RCB_MAX_RESUMES", "2"))
REC_PATH = os.path.join(DATA, "record.f64")      # journal: every executed control step's targets, float64 (N,) rows


def _events() -> list:
    try: return [json.loads(l) for l in open(os.path.join(DATA, "episode.jsonl")) if l.strip()]
    except OSError: return []


def _write_json(path: str, obj: dict) -> None:
    """Atomic: a reader (the collect hook, the verifier) never sees a half-written file."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f: json.dump(obj, f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _give_up(reason: str, infra: bool) -> None:
    """End the trial's episode without a new one: mark it failed, keep the PID file for the collect hook, and idle."""
    log({"ev": "restart_refused", "reason": reason})
    try: prev = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: prev = {}  # noqa
    if not isinstance(prev, dict): prev = {}
    if not (prev.get("finalized") and "deterministic" in prev):     # a verdict already on disk is kept as it is
        prev.update({"success": False, "done": True, "reason": reason, "finalized": True, "protocol": PROTOCOL, **({"infra_error": 1} if infra else {})})
    prev["video_done"] = True                                       # nothing more will be written: the collect hook stops waiting
    _write_json(os.path.join(DATA, "final.json"), prev)
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    signal.signal(signal.SIGUSR1, lambda *_: None); print(f"restart refused: {reason}", flush=True)
    while True: time.sleep(3600)


with open(os.path.join(DATA, "startups.jsonl"), "a") as _f: _f.write(json.dumps({"ts": time.time(), "pid": os.getpid()}) + "\n")

# Back off before rebuilding after a failed start (e.g. a GPU out-of-memory crash while other trials hold the GPU): compose
# restarts immediately, so without a pause every retry meets the same full GPU (seen: 4 starts in 75 s, all failed).
_n_starts = sum(1 for _ in open(os.path.join(DATA, "startups.jsonl")))
if _n_starts > 1 and not os.path.exists(os.path.join(DATA, "episode.jsonl")): time.sleep(min(120, 20 * (_n_starts - 1)))

S = TOOL.Session(INSTANCE, enable_render=True)
E["built"] = True; faulthandler.cancel_dump_traceback_later()    # the scene exists: the startup watchdog stands down (a resume replay may take minutes)
KIND = "dtb" if TOOL.__name__ == "rcb_dtb" else "pg"
CTRL_DT = float(TOOL.CONTROL_DT); N = int(TOOL.N)
NAMES = list(getattr(TOOL, "JOINT_NAMES", None) or getattr(TOOL, "ACTUATOR_NAMES"))
RECORD: list = []                         # the episode: one row of targets per control step


def _cams() -> dict:
    """name -> (mujoco camera id or None, free-camera settings or None)."""
    m = S.model; named = [m.camera(i).name for i in range(m.ncam)]
    want = list(getattr(TOOL, "CAMERAS", ())) or []
    out = {c: (m.camera(c).id, None) for c in want if c in named}
    if not out:   # scenes without named cameras (Panda): four fixed free-camera views around the workspace
        for name, (az, el) in {"front": (180, -20), "left": (90, -25), "right": (270, -25), "top": (180, -70)}.items():
            out[name] = (None, dict(lookat=(0.45, 0.0, 0.25), distance=1.5, azimuth=az, elevation=el))
    return out


CAMS = _cams()
W, H = 320, 240
_R = {"rgb": None, "depth": None}


def _renderer(depth: bool):
    k = "depth" if depth else "rgb"
    if _R[k] is None:
        _R[k] = S.mj.Renderer(S.model, H, W)
        if depth: _R[k].enable_depth_rendering()
    return _R[k]


def _update(r, cam):
    cid, free = CAMS[cam]
    if cid is not None: r.update_scene(S.data, camera=cid)
    else:
        c = S.mj.MjvCamera(); c.lookat[:] = free["lookat"]; c.distance = free["distance"]; c.azimuth = free["azimuth"]; c.elevation = free["elevation"]
        r.update_scene(S.data, camera=c)


def grab(cams, depth: bool):
    imgs, dep = {}, {}
    for c in cams:
        r = _renderer(False); _update(r, c); imgs[c] = r.render().copy()
        if depth:
            r = _renderer(True); _update(r, c); dep[c] = r.render().astype(np.float16)
    return imgs, dep


def _moving(cam: str) -> bool:
    """True for a camera whose pose can change during the episode: a tracking / targeting camera, or one on a body that a
    joint or a mocap pose moves (ALOHA's wrist cameras). Free cameras and cameras fixed to the world never move."""
    cid, _ = CAMS[cam]
    if cid is None: return False
    m = S.model
    if int(m.cam_mode[cid]) != 0: return True
    b = int(m.cam_bodyid[cid])
    while b > 0:
        if int(m.body_jntnum[b]) > 0 or int(m.body_mocapid[b]) >= 0: return True
        b = int(m.body_parentid[b])
    return False


MOVING = {c: _moving(c) for c in CAMS}


def cam2world(cam: str) -> np.ndarray:
    """Camera-to-world pose (4x4, OpenGL convention: x right, y up, looks along -z) of the viewpoint the mono RGB / depth
    image is rendered from, in the current state. A model camera: data.cam_xpos / data.cam_xmat, which is what the
    renderer reads. A free camera: the scene's two eye cameras share their axes and sit ipd/2 to either side of the
    viewpoint, so the viewpoint is their mean (scene.camera[0] alone is the LEFT eye, 3.4 cm off)."""
    cid, _ = CAMS[cam]
    if cid is not None:
        R = np.array(S.data.cam_xmat[cid], float).reshape(3, 3); pos = np.array(S.data.cam_xpos[cid], float)
    else:
        r = _renderer(False); _update(r, cam); a, b = r.scene.camera[0], r.scene.camera[1]
        fwd = np.array(a.forward, float); up = np.array(a.up, float); pos = 0.5 * (np.array(a.pos, float) + np.array(b.pos, float))
        R = np.column_stack([np.cross(fwd, up), up, -fwd])
    return np.vstack([np.column_stack([R, pos]), [0.0, 0.0, 0.0, 1.0]])


def calib() -> dict:
    """Per camera: pinhole intrinsics and the camera-to-world pose in the current state (see cam2world)."""
    out = {}
    for c in CAMS:
        fovy = float(S.model.cam_fovy[CAMS[c][0]]) if CAMS[c][0] is not None else float(S.model.vis.global_.fovy)
        f = 0.5 * H / np.tan(np.deg2rad(fovy) / 2)
        out[c] = {"intrinsic_cv": [[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]], "cam2world_gl": cam2world(c).tolist(),
                  "width": W, "height": H, "fovy_deg": fovy, "moving": MOVING[c]}
    return out


def proprio() -> np.ndarray:
    st = S.state(); q = np.asarray(st.get("q", st.get("qpos"))[:N] if "q" in st else _robot_q(), float)
    qd = np.asarray(st["qd"] if "qd" in st else _robot_qd(), float)
    return np.concatenate([q, qd, np.asarray(st["targets"], float)]).astype(np.float32)


def _robot_q():
    return np.array([S.data.qpos[S.model.jnt_qposadr[S.model.actuator_trnid[a, 0]]] for a in S._act])


def _robot_qd():
    return np.array([S.data.qvel[S.model.jnt_dofadr[S.model.actuator_trnid[a, 0]]] for a in S._act])


def task_info() -> dict:
    if KIND == "dtb":
        p = S.progress()
        return {"goal_index": p["reached"], "n_goals": p["n_goals"], "goal": None if p["done"] else list(S.goals[p["reached"]]),
                "goals_reached": p["reached"], "failed_on_timeout": p["failed"], "steps_left_on_goal": p["steps_left_on_goal"],
                "goal_time_limit_s": round(TOOL.GOAL_TIMEOUT_STEPS * CTRL_DT, 3) or None,
                "pose_format": "x y z qx qy qz qw (world frame, metres)"}
    info = {"target_pos": np.asarray(S.target_pos).tolist()} if hasattr(S, "target_pos") else {}
    if hasattr(S, "target_quat"): info["target_quat_wxyz"] = np.asarray(S.target_quat).tolist()
    return info


PROPRIO_LAYOUT = [f"{n}_pos" for n in NAMES] + [f"{n}_vel" for n in NAMES] + [f"{n}_target" for n in NAMES]
SPEC = {"protocol": PROTOCOL, "simulator": "mujoco", "task_text": S.inst.get("text", ""), "control_dt": CTRL_DT,
        "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "max_control_steps": MAX_CONTROL_STEPS or None,
        "max_video_fps": MAX_VIDEO_FPS, "max_frames_per_call": MAX_FRAMES_PER_CALL,
        "on_service_error": ("if a call fails with a connection error or 5xx, the service may have crashed and resumed the same "
                             "episode (never a reset): the state is the one after the last call that completed on the service, "
                             "which you may not have received; check GET /status (control_steps) before continuing"),
        "cameras": {c: {"rgb": True, "depth": True, "size": [W, H], "moving": MOVING[c]} for c in CAMS},
        "camera_calibration": ('meta["cameras"][cam] of every response: intrinsic_cv (pinhole, pixels) and cam2world_gl (4x4, OpenGL axes: x right, '
                               "y up, the camera looks along -z; the viewpoint the image is rendered from), computed for the state at the END "
                               "of that call (the `last/<cam>` image and the last frame of every stack). A camera with moving = false never "
                               "moves. For a camera with moving = true (mounted on the robot) the response also carries the part "
                               "`cam2world_gl/<cam>`: float64 (n_frames, 4, 4), one pose per returned frame of that camera "
                               '(client: res.raw["cam2world_gl/<cam>"]["data"])'),
        "action_types": {"joint_position": {"dim": N, "layout": NAMES, "lower": S.lower.tolist(), "upper": S.upper.tolist(),
                                            "semantics": "rows `dt` apart (a multiple of control_dt, >= control_dt); each row's targets held "
                                                         "(interpolate=hold) or ramped linearly from the previous row (linear) over its control steps; "
                                                         "clipped to [lower, upper]"},
                         "not_yet": ["ee_pose", "joint_delta"]},
        "proprio_layout": PROPRIO_LAYOUT,
        "budget": {"reset": 0, "wall_clock_s": WALL_CLOCK_S,
                   "clock": "meta time_s / time_left_s are counted from your first request to the service; approximate - the harness's own deadline is authoritative"},
        "episode": (("ends when every goal is reached" + (f", when a goal is not reached within {TOOL.GOAL_TIMEOUT_STEPS * CTRL_DT:g} s" if TOOL.GOAL_TIMEOUT_STEPS else "")
                     + (f", after {MAX_CONTROL_STEPS} control steps" if MAX_CONTROL_STEPS else "") + ", or when your time is up; the recorded trajectory is scored")
                    if KIND == "dtb" else "runs until the agent phase ends; the final state is graded")}


def _agent_time() -> float:
    """Seconds since the agent's first request to the service (0 before it): the agent's clock. The simulator is up
    before the agent starts (the harness installs the agent first), so the service's own start is not that moment."""
    return 0.0 if E["t_first"] is None else time.time() - E["t_first"]


def _touch() -> None:
    """Every request passes here: the first one starts the agent's clock (logged, so a resume keeps it)."""
    if E["t_first"] is None:
        E["t_first"] = time.time(); log({"ev": "first_request", "ts": E["t_first"]})


def meta_common() -> dict:
    return {"calls": E["calls"], "rows": E["rows"], "control_steps": len(RECORD), "sim_time_s": round(len(RECORD) * CTRL_DT, 3),
            "time_s": round(_agent_time(), 2), "time_left_s": max(0.0, round(WALL_CLOCK_S - _agent_time(), 1)),
            "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio().tolist()}, "task": task_info(), "cameras": calib(),
            "done": E["done"], "reason": E["reason"]}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f: f.write(json.dumps({"ts": time.time(), **ev}) + "\n")


def write_final(extra: dict | None = None) -> None:
    d = {"protocol": PROTOCOL, "tool": TOOL.__name__, "calls": E["calls"], "rows": E["rows"], "control_steps": len(RECORD),
         "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "done": E["done"], "reason": E["reason"], "finalized": E["finalized"],
         "video_done": E["video_done"]}
    d.update(E.get("verdict") or {}); d.update(extra or {})
    _write_json(os.path.join(DATA, "final.json"), d)


class Recorder:
    def __init__(self, cams, fps, depth):
        self.cams = cams; self.every = max(1, int(round(1.0 / (CTRL_DT * max(1, fps))))); self.depth = depth
        self.frames = {c: [] for c in cams}; self.dep = {c: [] for c in cams}; self.prop = []; self.n = 0
        self.pose = {c: [] for c in cams if MOVING[c]}     # a moving camera: its pose with every frame
    def tick(self, force=False):
        if force or self.n % self.every == 0:
            imgs, dep = grab(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(imgs[c])
                if c in dep: self.dep[c].append(dep[c])
                if c in self.pose: self.pose[c].append(cam2world(c))
            self.prop.append(proprio())
        self.n += 1
    def parts(self, video: str, fps: int):
        out = []
        for c in self.cams:
            fr = np.stack(self.frames[c]) if self.frames[c] else np.zeros((0, H, W, 3), np.uint8)
            if video in ("mp4", "both") and len(fr):
                import imageio.v2 as imageio, tempfile
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf: path = tf.name
                try:
                    with imageio.get_writer(path, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                            output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"]) as w:
                        for f in fr: w.append_data(np.ascontiguousarray(f))
                    data = open(path, "rb").read()
                finally:
                    try: os.unlink(path)
                    except OSError: pass
                out.append((f"video/{c}", "mp4", data, {"fps": fps, "n": int(len(fr))}))
            if video in ("frames", "both"): out.append(rcb1.array_part(f"frames/{c}", fr))
            if len(fr): out.append(rcb1.array_part(f"last/{c}", fr[-1]))
            if self.dep[c]: out.append(rcb1.array_part(f"depth/{c}", np.stack(self.dep[c])))
            if self.pose.get(c): out.append(rcb1.array_part(f"cam2world_gl/{c}", np.stack(self.pose[c]).astype(np.float64)))
        out.append(rcb1.array_part("proprio", np.stack(self.prop) if self.prop else np.zeros((0, len(PROPRIO_LAYOUT)), np.float32)))
        return out


def _ctrl_step(tg, rec) -> bool:
    """One control step with targets `tg`; returns True if the episode ended (DexToolBench goal rule)."""
    S.step(tg); row = np.asarray(S.targets, float).copy(); RECORD.append(row); RECF.write(row.tobytes()); rec.tick()
    if KIND == "dtb":
        p = S.progress()
        if p["done"]: finish("all goals reached"); return True
        if p["failed"]: finish("goal timeout"); return True
    if MAX_CONTROL_STEPS and len(RECORD) >= MAX_CONTROL_STEPS: finish("step limit"); return True
    return False




# ---- request parsing: everything here runs BEFORE any physics. A malformed request is the caller's mistake: it raises
# ValueError (answered 400, nothing executed), never a simulator error (500, which ends the episode; PROTOCOL §4.6).
VIDEO_MODES = ("mp4", "frames", "both", "none")


def _fps(meta: dict) -> int:
    try: fps = int(meta.get("video_fps", 10))
    except (TypeError, ValueError, OverflowError): raise ValueError("video_fps must be an integer") from None
    if not 1 <= fps <= MAX_VIDEO_FPS: raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
    return fps


def _num(meta: dict, key: str, default: float) -> float:
    """A finite numeric request field; anything else (null, a string, NaN, Infinity) is a 400."""
    try:
        v = meta.get(key, default)
        if isinstance(v, bool): raise TypeError     # JSON true is no number (float(True) is 1.0)
        v = float(v)
    except (TypeError, ValueError, OverflowError): raise ValueError(f"{key} must be a number") from None
    if not math.isfinite(v): raise ValueError(f"{key} must be a finite number")
    return v


def _cameras(meta: dict, default: list) -> list:
    """The requested cameras, each once (unknown names are ignored; none left = the default). A repeated name is dropped
    BEFORE the frame budget and any rendering: the recorder keeps frames per name, so repeats would multiply its work."""
    cams = meta.get("cameras")
    if cams is None: return list(default)
    if not isinstance(cams, (list, tuple)) or not all(isinstance(c, str) for c in cams): raise ValueError(f"cameras must be a list of camera names: {list(CAMS)}")
    return list(dict.fromkeys(c for c in cams if c in CAMS)) or list(default)


def _video(meta: dict, default: str) -> str:
    v = meta.get("video", default)
    if v is None: return default
    if not isinstance(v, str) or v not in VIDEO_MODES: raise ValueError("video must be mp4|frames|both|none")
    return v


def _frame_budget(cams, fps: int, seconds: float, depth: bool) -> None:
    n = (int(seconds * fps) + 2) * len(cams) * (2 if depth else 1)
    if n > MAX_FRAMES_PER_CALL: raise ValueError(f"this call would return {n} frames (cameras x fps x seconds, depth counts double); "
                                                 f"the limit is {MAX_FRAMES_PER_CALL}: use fewer cameras, a lower video_fps or a shorter chunk")


def parse_submit(meta: dict, parts: dict) -> dict:
    """Validate a /submit request completely; returns what do_submit executes. No physics, no state change."""
    if meta.get("type", "joint_position") != "joint_position": raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
    raw = parts["actions"].get("data") if isinstance(parts.get("actions"), dict) else meta.get("actions", [])
    try: A = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError): raise ValueError(f"actions must be a numeric array (T, {N})") from None
    if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"joint_position actions must be (T, {N}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    dt = _num(meta, "dt", CTRL_DT)
    if not 0 < dt <= 1e6: raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}")
    k = int(round(dt / CTRL_DT))
    if k < 1 or abs(k * CTRL_DT - dt) > 1e-6: raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}")
    interp = meta.get("interpolate", "linear")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    cams = _cameras(meta, list(CAMS)[:1]); fps = _fps(meta); video = _video(meta, "mp4"); depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, A.shape[0] * dt, depth)
    return {"A": A, "dt": dt, "k": k, "interp": interp, "cams": cams, "fps": fps, "video": video, "depth": depth, "note": str(meta.get("note") or "")[:500]}


def parse_observe(meta: dict) -> dict:
    """Validate an /observe request completely; returns what do_observe executes."""
    cams = _cameras(meta, list(CAMS)); seconds = _num(meta, "seconds", 0); fps = _fps(meta); video = _video(meta, "frames"); depth = bool(meta.get("include_depth", False))
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    _frame_budget(cams, fps, seconds, depth)
    return {"cams": cams, "seconds": seconds, "fps": fps, "video": video, "depth": depth}


def do_submit(q: dict):
    A, dt, k, interp, cams, fps, video, depth = (q[x] for x in ("A", "dt", "k", "interp", "cams", "fps", "video", "depth"))
    rec = Recorder(cams, fps, depth); rec.tick(force=True); prev = np.asarray(S.targets, float).copy(); n_clip = 0; done = False
    for row in A.astype(np.float64):
        tgt = np.clip(row, S.lower, S.upper); n_clip += int(np.any(tgt != row))
        for j in range(1, k + 1):
            tg = tgt if interp == "hold" else prev + (tgt - prev) * (j / k)
            if _ctrl_step(tg, rec): done = True; break
        prev = tgt
        if done: break
    rec.tick(force=True); E["calls"] += 1; E["rows"] += int(A.shape[0]); RECF.flush()
    out = {**meta_common(), "chunk_id": E["calls"], "type": "joint_position", "executed_rows": int(A.shape[0]), "n_clipped_rows": n_clip, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": "joint_position", "rows": int(A.shape[0]), "dt": dt, "interpolate": interp, "cameras": cams,
         "note": q["note"], "control_steps": len(RECORD), "n_clipped_rows": n_clip, "task": task_info(),
         "rows_total": E["rows"], "state_sha": S.state_sha()})
    d = os.path.join(DATA, "calls", f"{E['calls']:06d}"); os.makedirs(d, exist_ok=True); np.save(os.path.join(d, "actions.npy"), A.astype(np.float32))
    return out, rec.parts(video, fps)


def do_observe(q: dict):
    cams, seconds, fps, video, depth = (q[x] for x in ("cams", "seconds", "fps", "video", "depth"))
    rec = Recorder(cams, fps, depth); rec.tick(force=True)
    if seconds > 0 and not E["done"]:
        hold = np.asarray(S.targets, float).copy()
        for _ in range(int(round(seconds / CTRL_DT))):
            if _ctrl_step(hold, rec): break
        rec.tick(force=True)
    E["calls"] += 1; RECF.flush()
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": len(RECORD),
         "rows_total": E["rows"], "state_sha": S.state_sha()})
    return {**meta_common(), "obs_id": E["calls"], "seconds": seconds, "ok": True}, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def finalize() -> None:
    with LOCK:
        try:
            A = np.asarray(RECORD, float).reshape(-1, N); live_sha = S.state_sha(); live = S.progress() if KIND == "dtb" else S.check()
            np.savez(os.path.join(DATA, "trajectory.npz"), actions=A, tool=TOOL.__name__, meta=json.dumps({"source": "standard-mode episode", "reason": E["reason"]}))
            # the tooling's MAX_STEPS is the privileged mode's hand-in cap (Playground: 3000); the service's episode is bounded
            # by RCB_MAX_CONTROL_STEPS and the agent's time instead, so the verification replay must accept the whole episode
            if hasattr(TOOL, "MAX_STEPS"): TOOL.MAX_STEPS = max(int(TOOL.MAX_STEPS), len(A))
            ver = TOOL.Session(INSTANCE, enable_render=True); r1 = ver.replay(A); det = r1["state_sha"] == live_sha
            v = {"deterministic": bool(det), "live_state_sha": live_sha}
            if KIND == "dtb":
                v.update(progress=round(float(r1["progress"]), 4) if det else 0.0, goals_reached=int(r1["reached"]), n_goals=int(r1["n_goals"]),
                         failed_on_timeout=bool(r1["failed"]), success=bool(det and r1["done"]), live_goals_reached=int(live["reached"]))
            else:
                v.update(success=bool(det and r1["success"]), live_success=bool(live["success"]),
                         **{k: val for k, val in r1.items() if k not in ("success", "state_sha", "steps") and isinstance(val, (int, float, bool))})
            # The verdict is final and on disk (finalized) before any video is rendered: the video never changes, hides or
            # delays it (a slow or failing render, or a collect hook that stops waiting, leaves the verdict as it is).
            E["verdict"] = v; E["finalized"] = True; write_final()
            try:
                tmp = os.path.join(DATA, "replay.tmp.mp4")                 # rendered aside: a half-written replay.mp4 is never collected
                ver.render_video(A, tmp, every=max(2, len(A) // 600), fps=25)
                os.replace(tmp, os.path.join(DATA, "replay.mp4"))
                if os.path.exists(os.path.join(DATA, "replay.tmp.last.png")): os.replace(os.path.join(DATA, "replay.tmp.last.png"), os.path.join(DATA, "replay.last.png"))
                E["verdict"]["video"] = True
            except Exception: traceback.print_exc()  # noqa
        except Exception as exc:  # noqa
            traceback.print_exc()
            if not E["finalized"]:        # no verdict was reached: the verification itself failed
                log({"ev": "finalize_error", "error": repr(exc)}); E["verdict"] = {"finalize_error": repr(exc)[:300]}
        E["finalized"] = True; E["video_done"] = True
        try: write_final()
        except Exception: traceback.print_exc()  # noqa


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    log({"ev": "end", "reason": reason, "control_steps": len(RECORD)}); write_final()


def start_finalize() -> None:
    if E.get("finalizing"): return
    E["finalizing"] = True; threading.Thread(target=finalize, daemon=True).start()


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _rcb1(self, meta, parts):
        body = rcb1.encode(meta, parts)
        if len(body) > MAX_RESP:
            parts = [p for p in parts if not (p[0].startswith("frames/") or p[0].startswith("depth/"))]; meta = {**meta, "degraded": "frames/depth dropped (response too large)"}; body = rcb1.encode(meta, parts)
        self.send_response(200); self.send_header("Content-Type", "application/x-rcb1"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def _body(self):
        try: n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError: raise ValueError("bad Content-Length") from None
        if n < 0: raise ValueError("bad Content-Length")   # read(-1) would read until the client hangs up, without any bound
        if n > MAX_BODY: raise ValueError("request too large")
        raw = self.rfile.read(n) if n else b""
        if raw[:4] == rcb1.MAGIC: return rcb1.decode(raw)
        b = json.loads(raw or b"{}")
        if not isinstance(b, dict): raise ValueError("body must be a JSON object or an RCB1 frame")
        return b, {}
    def do_GET(self):
        _touch()
        if self.path == "/spec": return self._json(200, SPEC)
        if self.path == "/status": return self._json(200, {"calls": E["calls"], "control_steps": len(RECORD), "done": E["done"], "reason": E["reason"], "elapsed_s": round(time.time() - E["t0"], 1)})
        return self._json(404, {"error": "no such endpoint"})
    def do_POST(self):
        _touch()
        if self.path not in ("/submit", "/observe"): return self._json(404, {"error": "no such endpoint"})
        try: self._req = self._body()
        except Exception as exc: return self._json(413 if str(exc) == "request too large" else 400, {"error": str(exc)[:200]})
        with LOCK:
            log({"ev": "call_begin", "path": self.path, "call": E["calls"] + 1})
            try:
                return self._serve()
            finally:
                log({"ev": "call_end", "path": self.path})

    def _serve(self):
        meta, parts = self._req
        if self.path == "/submit" and E["done"]: return self._json(409, {"error": "episode finished", "reason": E["reason"]})
        try:      # the whole request is checked before any physics: whatever is wrong with it is a 400 and changes nothing
            if not isinstance(meta, dict) or not isinstance(parts, dict): raise ValueError("the request's meta must be a JSON object")
            q = parse_submit(meta, parts) if self.path == "/submit" else parse_observe(meta)
        except (ValueError, TypeError, OverflowError, AttributeError, KeyError, IndexError) as exc:
            return self._json(400, {"error": (str(exc) or type(exc).__name__)[:300]})
        try:
            out, blobs = do_submit(q) if self.path == "/submit" else do_observe(q)
        except Exception as exc:  # noqa
            traceback.print_exc(); log({"ev": "error", "error": repr(exc)}); finish("error")   # PROTOCOL §4.6: a 500 ends the episode
            return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        return self._rcb1(out, blobs)


def _end_from_signal():
    with LOCK:
        if not E["done"]: finish("timeout")
    start_finalize()


def _resume_or_start() -> None:
    """Fresh start, or (after a crash: compose restarts the container) resume the SAME episode. The journal holds every
    executed control step; the log holds, per completed call, the step count and the state hash. Replaying the journal up
    to the last completed call rebuilds that exact state (MuJoCo on the CPU is bit-exact) and the hash is checked. A call
    in flight when the service died is lost as a whole; its caller got an error, not a result, so nothing is gained. No
    reset: the episode never goes back to its start. More than MAX_RESUMES crashes end it; if every crash happened while
    serving a call, it counts as the agent's (sim_crashed_on_call), else as infrastructure (sim_crashed)."""
    ev = _events(); starts = [e for e in ev if e.get("ev") == "start"]
    if not starts:
        try: os.remove(REC_PATH)
        except OSError: pass
        log({"ev": "start", "tool": TOOL.__name__, "state_sha": S.state_sha(), "protocol": PROTOCOL}); write_final()
        E["t0"] = time.time(); return
    try: fin = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: fin = {}  # noqa
    if fin.get("finalized") and "deterministic" in fin: _give_up("restarted after finalize", infra=False)
    resumes = [e for e in ev if e.get("ev") == "resumed"]
    in_call = bool(ev) and ev[-1].get("ev") == "call_begin"
    crashes_in_calls = sum(1 for e in resumes if e.get("crashed_in_call")) + int(in_call)
    if len(resumes) >= MAX_RESUMES:
        _give_up("sim_crashed_on_call" if crashes_in_calls == len(resumes) + 1 else "sim_crashed", infra=crashes_in_calls != len(resumes) + 1)
    done = [e for e in ev if e.get("ev") in ("submit", "observe") and "state_sha" in e]
    last = done[-1] if done else starts[0]
    n = int(last.get("control_steps", 0))
    try: R = np.fromfile(REC_PATH, dtype=np.float64)
    except OSError: R = np.zeros(0)
    if R.size < n * N: _give_up("resume_failed: journal shorter than the log", infra=True)
    R = R[: n * N].reshape(n, N)
    for row in R:
        S.step(row); RECORD.append(row.copy())
    if S.state_sha() != last["state_sha"]: _give_up("resume_failed: replayed state differs from the logged one", infra=True)
    R.tofile(REC_PATH)                                   # drop the steps of the call that was in flight
    E["calls"] = int(last.get("call", 0)); E["rows"] = int(last.get("rows_total", 0)); E["t0"] = float(starts[0]["ts"])
    first = [e for e in ev if e.get("ev") == "first_request"]
    if first: E["t_first"] = float(first[0]["ts"])       # the agent's clock keeps running through a crash
    ended = [e for e in ev if e.get("ev") == "end" and int(e.get("control_steps") or 0) <= n]   # not the lost call's
    if ended: E["done"] = True; E["reason"] = ended[-1].get("reason"); E["t_end"] = float(ended[-1]["ts"])
    log({"ev": "resumed", "control_steps": n, "calls": E["calls"], "state_sha": S.state_sha(), "crashed_in_call": in_call,
         "downtime_s": round(time.time() - float(ev[-1]["ts"]), 1)})
    write_final()


def _bind(port: int, handler) -> HTTPServer:
    """The listening server. Under Harbor's egress control the agent's container shares this network namespace, so a
    process of the agent may hold the port when the service (re)starts. Wait for the port instead of failing: an
    exception here would count as a crash of the service (the collect hook's signal is still served meanwhile)."""
    said = False
    while True:
        try: return HTTPServer(("0.0.0.0", port), handler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE: raise
        if not said: said = True; print(f"[sim] port {port} is in use (a process in the agent's container?): waiting for it to be free", flush=True)
        time.sleep(1.0)


_resume_or_start()
signal.signal(signal.SIGUSR1, lambda *_: threading.Thread(target=_end_from_signal, daemon=True).start())
if _USR1["pending"]: threading.Thread(target=_end_from_signal, daemon=True).start()
RECF = open(REC_PATH, "ab")
E["ready"] = True
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} MuJoCo sim ready ({TOOL.__name__})", flush=True)
_bind(int(os.environ.get("RCB_PORT", "8000")), Hd).serve_forever()
