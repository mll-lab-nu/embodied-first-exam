"""eai-standard/3.0 sim service for the MuJoCo tasks (DexToolBench, MuJoCo Playground): robot as a service.

The sidecar owns the simulator (the task's tooling module, RCB_TOOL = rcb_dtb | rcb_aloha | rcb_panda, with the task's
frozen instance) and serves the same wire protocol as the RoboTwin limited tasks (docs/protocol/standard_mode.md), so
the agent uses the same client (rcb_client.py): GET /spec, GET /status, POST /observe, POST /submit, binary RCB1
responses. What the agent gets: camera RGB (+ depth, with each camera's intrinsics and pose: the viewpoint the image is
rendered from, recomputed for every response, and per frame for a camera that moves), the robot's own joint
positions, velocities and current targets, and the task's definition (DexToolBench: the current goal pose and its index,
as SimToolReal's deployment gives its policy; Playground: the target). Never the object's pose.

Actions: `joint_position` rows (the tooling's N actuator targets), each held for `dt` (a multiple of the control step,
hold or linear interpolation per control step; a hold chunk, eai-standard/3.0, holds the current targets). Episodes are
agent-ended (RCB_AGENT_END=1): they end at the agent's POST /finish, at the step cap (RCB_MAX_CONTROL_STEPS, lowered by
RCB_STEP_LIMIT), when a DexToolBench goal times out (only if RCB_DTB_GOAL_TIMEOUT_S > 0; the standard twins set 0) or
when the agent's time is up; reaching the goals never ends one and is never announced (DexToolBench: the goals are
judged as they are reached; Playground: the final state).

Evidence under /data: episode.jsonl (every call), calls/NNNNNN/ (meta + actions), and at the end trajectory.npz
((T, N) per control step), final.json and replay.mp4. The verdict is the live episode's (docs/protocol/README.md H.4; owner,
2026-10-17; graded_by = "live", replays = 0): the task's own rule on the episode this service ran
(DexToolBench: every goal reached, the goal tracker running every live control step; Playground: the tooling's check() of
the live final state); nothing is replayed to grade it. The collect hook ends the episode with SIGUSR1. final.json is
`finalized` as soon as the verdict is in it; the video is then rendered from the trajectory in one pass and never
changes or delays the verdict (`video_pending` while it renders; `video_done` tells the collect hook that nothing more
comes). The frozen start is checked when the episode begins: the built scene's state hash against the instance's
recorded one (instance.json `state_sha`, else RCB_START_SHA); a mismatch gets no episode (instance_mismatch, an
infrastructure failure).

Requests are validated in full before any physics runs: a malformed one (dt / seconds / video_fps / last_s not a finite
JSON number, cameras not a list of names, ...) is answered 400 and changes nothing (a /finish body is never parsed); only a failure of the simulator itself is a 500
that ends the episode. `time_s` / `time_left_s` count from the agent's first request to the service.

Optional reset capability (PROTOCOL §4.5; RCB_RESET_BUDGET = N > 0, default 0; DexToolBench's standard twins set 20):
POST /reset abandons the running episode and starts a new one from the frozen start state (Session.reset()), N times
in all. Only the last episode is graded (trajectory.npz holds its rows, replayable from the frozen start); the agent's
/finish or its time (SIGUSR1) ends the trial (no reset after it). Without a budget /reset is a 404."""
from __future__ import annotations
import errno, importlib, json, math, os, signal, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RCB_SESSION_LOG"] = ""; os.environ["RCB_AGENT_TRACE_DIR"] = ""
import rcb1  # noqa: E402

PROTOCOL = "eai-standard/3.0"
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)   # RCB_DATA / RCB_PORT: test hooks (never set in tasks)
TOOL = importlib.import_module(os.environ.get("RCB_TOOL", "rcb_dtb"))
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
# Episode cap in control steps (0 = none). Set where nothing else ends the episode, e.g. DexToolBench without its per-goal
# time limit (the standard twins: RCB_DTB_GOAL_TIMEOUT_S=0, RCB_MAX_CONTROL_STEPS=360000 = 100 min of robot time).
MAX_CONTROL_STEPS = int(os.environ.get("RCB_MAX_CONTROL_STEPS", "0"))
MAX_VIDEO_FPS = 30; MAX_FRAMES_PER_CALL = 3000   # frames x cameras per response: bounds the service's memory
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
RESET_BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET", "0") or 0))   # PROTOCOL §4.5: 0 = one episode, no /reset
MAX_BODY = 64 * 1024 * 1024; MAX_RESP = 256 * 1024 * 1024
LOCK = threading.Lock()
E = {"ready": False, "calls": 0, "rows": 0, "done": False, "reason": None, "t0": time.time(), "finalized": False,
     "t_first": None, "video_done": False, "resets": 0, "ep_start": 0, "journal_rows": 0, "stopping": False}
# t_first: the agent's first request (its clock starts there). resets: POST /reset calls that started a new episode;
# journal_rows: control steps executed over the whole trial (record.f64's length); ep_start: where the current episode
# begins in it. stopping: the agent's time is up (SIGUSR1): no reset any more.

# Agent-ended episodes (docs/protocol/README.md §3 "Agent-ended episodes", standard_mode.md; required for every standard
# and realtime task from protocol v3.0; the same rules as rcb_service.py's AGENT_END). RCB_AGENT_END=1: the service never
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


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f: f.write(json.dumps({"ts": time.time(), **ev}) + "\n")


def _graded(fin: dict) -> bool:
    """final.json holds a verdict: the live one (graded_by), or one of a service before 2026-10-17 (deterministic)."""
    return bool(fin.get("finalized")) and ("graded_by" in fin or "deterministic" in fin)


def _give_up(reason: str, infra: bool, **extra) -> None:
    """End the trial's episode without a new one: mark it failed, keep the PID file for the collect hook, and answer every
    request with the refusal (409) until the container is removed."""
    log({"ev": "restart_refused", "reason": reason})
    try: prev = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: prev = {}  # noqa
    if not isinstance(prev, dict): prev = {}
    if not _graded(prev):                                           # a verdict already on disk is kept as it is
        prev.update({"success": False, "live_success": False, "done": True, "reason": reason, "finalized": True, "gave_up": True,
                     "protocol": PROTOCOL, **extra, **({"infra_error": 1} if infra else {})})
    elif prev.get("video_pending"):                                 # the service died rendering the video: only the video is lost
        prev.update(video_pending=False, video=False)
    prev["video_done"] = True                                       # nothing more will be written: the collect hook stops waiting
    _write_json(os.path.join(DATA, "final.json"), prev)
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    signal.signal(signal.SIGUSR1, lambda *_: None); print(f"restart refused: {reason}", flush=True)
    _refuse_forever(reason, infra)


def _refuse_forever(reason: str, infra: bool) -> None:
    """After a give-up: answer every request 409 {"error", "reason", "gave_up": true, "infra_error"} until the container is
    removed (as the shared layer's rcb_limited.refuse_forever), so the agent's client stops at once (EpisodeOver) instead of
    waiting out its timeout for a service that will never serve. The verdict is on disk already; this never changes it."""
    body = json.dumps({"error": "the sim service gave up on this episode and will not serve it", "reason": reason,
                       "gave_up": True, "infra_error": int(bool(infra))}).encode()

    class Refusal(BaseHTTPRequestHandler):
        timeout = 30                                                # a client that stops sending must not hold the thread
        def _refuse(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if 0 < n <= 64 << 20: self.rfile.read(n)            # take the request first: the client then sees the answer
                self.send_response(409); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            except (OSError, ValueError): pass
            self.close_connection = True
        do_GET = do_POST = _refuse
        def log_message(self, *a): pass

    def answer():
        port = int(os.environ.get("RCB_PORT", "8000"))
        while True:                                                 # the port may still be held: wait for it
            try: HTTPServer(("0.0.0.0", port), Refusal).serve_forever(); return
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE: traceback.print_exc(); return
            time.sleep(1.0)

    threading.Thread(target=answer, daemon=True).start()
    while True: time.sleep(3600)


with open(os.path.join(DATA, "startups.jsonl"), "a") as _f: _f.write(json.dumps({"ts": time.time(), "pid": os.getpid()}) + "\n")

# Back off before rebuilding after a failed start (e.g. a GPU out-of-memory crash while other trials hold the GPU): compose
# restarts immediately, so without a pause every retry meets the same full GPU (seen: 4 starts in 75 s, all failed).
_n_starts = sum(1 for _ in open(os.path.join(DATA, "startups.jsonl")))
if _n_starts > 1 and not os.path.exists(os.path.join(DATA, "episode.jsonl")): time.sleep(min(120, 20 * (_n_starts - 1)))

# The frozen start's recorded state hash (qpos + qvel after the reset): instance.json's own `state_sha` (Playground ALOHA /
# Panda; their tooling refuses another start itself), else RCB_START_SHA (DexToolBench, whose instance records none: the
# generator scripts/mj_mk_limited.py writes the hash every archived episode of the task started from).
try: START_SHA = str(json.load(open(INSTANCE)).get("state_sha") or os.environ.get("RCB_START_SHA") or "")
except Exception: START_SHA = os.environ.get("RCB_START_SHA") or ""  # noqa
try:
    S = TOOL.Session(INSTANCE, enable_render=True)
except RuntimeError as exc:   # the tooling's own start check (ALOHA, Panda): the scene did not build to the frozen start
    if "initial state hash" not in str(exc): raise
    faulthandler.cancel_dump_traceback_later()
    _give_up("instance_mismatch", infra=True, instance_mismatch=1, error=str(exc)[:300], video_done=True)
E["built"] = True; faulthandler.cancel_dump_traceback_later()    # the scene exists: the startup watchdog stands down (a resume replay may take minutes)
KIND = "dtb" if TOOL.__name__ == "rcb_dtb" else "pg"
# DexToolBench's goal is a sequence of poses the goal tracker counts as they are reached ("events": every goal reached,
# in order, during the episode); Playground's is the final state ("state": the tooling's check() at the end)
END_JUDGEMENT = "events" if KIND == "dtb" else "state"
CTRL_DT = float(TOOL.CONTROL_DT); N = int(TOOL.N)
NAMES = list(getattr(TOOL, "JOINT_NAMES", None) or getattr(TOOL, "ACTUATOR_NAMES"))
RECORD: list = []                         # the current episode: one row of targets per control step (what is graded)


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


def intrinsics(cam: str) -> tuple[float, float, float, float, float]:
    """(fx, fy, cx, cy) in pixels of the W x H image MuJoCo renders for this camera, and its vertical field of view in
    degrees. MuJoCo's rule (3.3.7, checked against CPU renders):
    - a camera given by its vertical field of view (`fovy`; every free camera: the model's global fovy) has square
      pixels whatever the image's aspect: fx = fy = (H / 2) / tan(fovy / 2), principal point at the image centre;
    - a camera given by its sensor (`sensorsize`, with `focal` / `focalpixel` and optionally `principal` /
      `principalpixel`: model.cam_sensorsize > 0, model.cam_intrinsic = focal x, focal y, principal x, principal y in
      length units) is rendered with the sensor's own extent in each direction, squeezed or stretched into the W x H
      image: fx = W * focal_x / sensor_x, fy = H * focal_y / sensor_y, cx = W / 2 - W * principal_x / sensor_x,
      cy = H / 2 + H * principal_y / sensor_y. Its pixels are square only when W : H is the sensor's aspect.
    Until 2026-10-13 every camera was reported by the first rule. ALOHA's overhead and wrist cameras are given by a
    3.896 x 2.140 mm sensor with a 1.93 mm lens and rendered at 320 x 240: fx is 158.52 px, not the 216.45 reported."""
    cid = CAMS[cam][0]; m = S.model
    fovy = float(m.cam_fovy[cid]) if cid is not None else float(m.vis.global_.fovy)
    sx, sy = (float(v) for v in m.cam_sensorsize[cid]) if cid is not None else (0.0, 0.0)
    if sx > 0 and sy > 0:
        fxl, fyl, pxl, pyl = (float(v) for v in m.cam_intrinsic[cid])
        return W * fxl / sx, H * fyl / sy, W / 2 - W * pxl / sx, H / 2 + H * pyl / sy, fovy
    f = 0.5 * H / np.tan(np.deg2rad(fovy) / 2)
    return f, f, W / 2, H / 2, fovy


def calib() -> dict:
    """Per camera: pinhole intrinsics (see intrinsics) and the camera-to-world pose in the current state (see cam2world)."""
    out = {}
    for c in CAMS:
        fx, fy, cx, cy, fovy = intrinsics(c)
        out[c] = {"intrinsic_cv": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]], "cam2world_gl": cam2world(c).tolist(),
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
        # The per-goal progress is shown (the instruction says so), but the last goal stays shown once it is reached:
        # reaching the whole sequence is never announced, so nothing here may depend on p["done"] (progress() itself
        # sets steps_left_on_goal to None exactly then). The countdown is computed here from steps_on_goal instead; with a
        # goal timeout (no standard twin sets one) it stops at the last goal's reach.
        p = S.progress(); T = int(TOOL.GOAL_TIMEOUT_STEPS or 0)
        i = min(int(p["reached"]), int(p["n_goals"]) - 1)
        return {"goal_index": i, "n_goals": p["n_goals"], "goal": list(S.goals[i]), "goals_reached": i,
                "failed_on_timeout": p["failed"], "steps_left_on_goal": None if not T or p["failed"] else max(0, T - int(p["steps_on_goal"])),
                "goal_time_limit_s": round(T * CTRL_DT, 3) or None,
                "pose_format": "x y z qx qy qz qw (world frame, metres)"}
    info = {"target_pos": np.asarray(S.target_pos).tolist()} if hasattr(S, "target_pos") else {}
    if hasattr(S, "target_quat"): info["target_quat_wxyz"] = np.asarray(S.target_quat).tolist()
    return info


PROPRIO_LAYOUT = [f"{n}_pos" for n in NAMES] + [f"{n}_vel" for n in NAMES] + [f"{n}_target" for n in NAMES]
SPEC = {"protocol": PROTOCOL, "simulator": "mujoco", "task_text": S.inst.get("text", ""), "control_dt": CTRL_DT,
        "max_chunk_s": MAX_CHUNK_S, **({"max_control_steps": MAX_CONTROL_STEPS} if MAX_CONTROL_STEPS else {}),   # omitted when uncapped
        "max_video_fps": MAX_VIDEO_FPS, "max_frames_per_call": MAX_FRAMES_PER_CALL,
        "on_service_error": ("if a call fails with a connection error or 5xx, the service may have crashed and resumed the same "
                             "episode (never a reset): the state is the one after the last call that completed on the service, "
                             "which you may not have received; check GET /status (control_steps) before continuing"),
        "cameras": {c: {"rgb": True, "depth": True, "size": [W, H], "moving": MOVING[c]} for c in CAMS},
        "camera_calibration": ('meta["cameras"][cam] of every response: intrinsic_cv (pinhole, pixels of the returned image: [[fx, 0, cx], [0, fy, cy], '
                               "[0, 0, 1]]; fx and fy differ for a camera whose sensor has another aspect than the image) and cam2world_gl (4x4, OpenGL axes: x right, "
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
        "budget": {"reset": RESET_BUDGET, "wall_clock_s": WALL_CLOCK_S,
                   "clock": ("meta time_s / time_left_s count from your first request to the service (any endpoint), not from the "
                             "service's start, and keep running through a restart of the service; time_left_s = budget.wall_clock_s - "
                             "time_s. The harness counts the same limit from the start of your session, so time_left_s never runs out "
                             "before the harness stops you: your real time left is time_left_s minus the time you spent before that "
                             "first request. Plan by time_left_s.")},
        "episode": (("ends" + (f" when a goal is not reached within {TOOL.GOAL_TIMEOUT_STEPS * CTRL_DT:g} s," if TOOL.GOAL_TIMEOUT_STEPS else "")
                     + (f" after {MAX_CONTROL_STEPS} control steps or" if MAX_CONTROL_STEPS else "") + " when your time is up; every goal must have been reached in order")
                    if KIND == "dtb" else "runs until the agent phase ends; the final state is graded")}
if RESET_BUDGET:
    SPEC["reset"] = ("POST /reset abandons the running episode and starts a new one from the same starting state, "
                     "budget.reset times in all; only the last episode is graded, and a success ends the trial. The clock "
                     "(time_left_s) keeps running. meta and /status add episode, resets_left and control_steps_total")
    SPEC["episode"] += "; with resets, only the last episode is scored"
if AGENT_END:
    SPEC["success_signal"] = SUCCESS_SIGNAL_NOTE
    if STEP_LIMIT: SPEC["budget"]["steps"] = MAX_CONTROL_STEPS
    SPEC["episode"] = ("ends at your POST /finish, when your time is up"
                       + (f", when a goal is not reached within {TOOL.GOAL_TIMEOUT_STEPS * CTRL_DT:g} s" if KIND == "dtb" and TOOL.GOAL_TIMEOUT_STEPS else "")
                       + (f", or after {MAX_CONTROL_STEPS} control steps (reason step_limit)" if MAX_CONTROL_STEPS else "")
                       + ("; every goal must have been reached in order during the episode (counted as it happens)" if KIND == "dtb"
                          else "; the state at that end is graded"))
    if RESET_BUDGET:
        SPEC["reset"] = ("POST /reset abandons the running episode and starts a new one from the same starting state, "
                         "budget.reset times in all; only the last episode is graded (after /finish no reset is possible). "
                         "The clock (time_left_s) keeps running. meta and /status add episode, resets_left and control_steps_total")


def _reset_counters() -> dict:
    if not RESET_BUDGET: return {}
    return {"episode": E["resets"] + 1, "control_steps_total": E["journal_rows"], "resets_left": _resets_left()}


def _resets_left() -> int:
    """The resets /reset would still grant: 0 whenever check_reset() refuses it whatever the budget (the agent's /finish,
    its time up, the session's end), as rcb_service._resets_left."""
    if (AGENT_END and E["done"] and E["reason"] in ("finished", "timeout")) or E["stopping"] or E.get("finalizing"):
        return 0
    return max(0, RESET_BUDGET - E["resets"])


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
            "done": E["done"], "reason": E["reason"], **_reset_counters(), **_steps_left()}


def write_final(extra: dict | None = None) -> None:
    d = {"protocol": PROTOCOL, "tool": TOOL.__name__, "calls": E["calls"], "rows": E["rows"], "control_steps": len(RECORD),
         "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "done": E["done"], "reason": E["reason"], "finalized": E["finalized"],
         "video_done": E["video_done"], "reset_budget": RESET_BUDGET, "resets": E["resets"], "episodes": E["resets"] + 1,
         "control_steps_total": E["journal_rows"]}
    d.update(E.get("verdict") or {}); d.update(_ae_fields()); d.update(extra or {})
    _write_json(os.path.join(DATA, "final.json"), d)


def _every(fps: int) -> int:
    """The Recorder's capture stride: a frame every this many control steps for the requested video_fps."""
    return max(1, int(round(1.0 / (CTRL_DT * max(1, fps)))))


class Recorder:
    def __init__(self, cams, fps, depth, ring=False):
        self.cams = cams; self.every = _every(fps); self.depth = depth; self.ring = ring   # ring: a /submit's (the recorder)
        self.frames = {c: [] for c in cams}; self.dep = {c: [] for c in cams}; self.prop = []; self.n = 0
        self.pose = {c: [] for c in cams if MOVING[c]}     # a moving camera: its pose with every frame
    def tick(self, force=False):
        imgs, prop = {}, None
        if force or self.n % self.every == 0:
            imgs, dep = grab(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(imgs[c])
                if c in dep: self.dep[c].append(dep[c])
                if c in self.pose: self.pose[c].append(cam2world(c))
            prop = proprio(); self.prop.append(prop)
        if self.ring: _ring_record(imgs, prop, force)
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
                import imageio.v2 as imageio, tempfile
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf: path = tf.name
                try:
                    with imageio.get_writer(path, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                            output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"]) as w:
                        for f in fr: w.append_data(np.ascontiguousarray(f, dtype=dt))
                    data = open(path, "rb").read()
                finally:
                    try: os.unlink(path)
                    except OSError: pass
                out.append((f"video/{c}", "mp4", data, {"fps": round(float(fps), 3), "n": int(len(fr))}))
            last = rcb1.array_part(f"last/{c}", np.asarray(fr[-1], dtype=dt)) if len(fr) else None
            if video in ("frames", "both"): out.append(fp)
            else: fr.clear()
            if last: out.append(last)
            if self.dep[c]: out.append(rcb1.frames_part(f"depth/{c}", self.dep[c]))   # float16 at capture: 2 bytes a pixel
            self.dep[c] = []
            if self.pose.get(c): out.append(rcb1.array_part(f"cam2world_gl/{c}", np.stack(self.pose[c]).astype(np.float64)))
        out.append(rcb1.array_part("proprio", np.stack(self.prop) if self.prop else np.zeros((0, len(PROPRIO_LAYOUT)), np.float32)))
        return out


# ---- eai-standard/3.0 (docs/protocol/standard_mode.md): standard mode is Gym's env.step. The world is frozen between
# submits; /observe never lets time pass (`seconds` > 0 is a 400) and reads the recorder: last_s = 0 the current frame,
# last_s = n the frames recorded in the last n robot seconds. The recorder is no process of its own: during every /submit
# (a rows-free hold chunk too) it keeps every camera's RGB frame every 1 / RCB_CAMERA_FPS of robot time, with the proprio
# row and the step, in a ring of the last RCB_LOOKBACK_S robot seconds; an image the call's own Recorder grabbed at that
# step is reused, not rendered again. A rows-free hold chunk {"type", "interpolate": "hold", "seconds": n} holds the
# current target for n seconds.
HOLD_HINT = ('observe never lets time pass (eai-standard/3.0): to let n seconds pass, submit a hold chunk {"type": <type>, '
             '"interpolate": "hold", "seconds": n} with no rows; last_s = n returns the frames recorded in the last n seconds')
DEPTH_PAST = ("depth with last_s > 0: the recorder keeps no depth for these cameras (spec timing.recorder.depth lists "
              "the cameras it keeps depth for): ask for depth with last_s = 0")
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
    RING.append({"step": step, "imgs": have, "prop": proprio() if prop is None else prop, "pose": {c: cam2world(c) for c in RING_CAMS if MOVING[c]}})
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
    if "actions" in parts:   # an empty `actions` part is no rows (as rcb_service)
        data = parts["actions"].get("data") if isinstance(parts["actions"], dict) else parts["actions"]
        rows = data is not None and np.size(data) > 0
    else:
        rows = meta.get("actions") not in (None, []) or meta.get("rows") not in (None, [])
    if rows:
        raise ValueError("a chunk has either rows or `seconds` (a hold chunk without rows), not both")
    if meta.get("interpolate") != "hold":
        raise ValueError('a chunk without rows is a hold chunk: {"type": <type>, "interpolate": "hold", "seconds": n}')
    n = real(meta, "seconds")
    if not (0 < n <= MAX_CHUNK_S + 1e-9):
        raise ValueError(f"a hold chunk's seconds must be in (0, max_chunk_s = {MAX_CHUNK_S:g}]")
    return n


def _last_s(meta: dict) -> float:
    """/observe's request: `seconds` > 0 is refused (HOLD_HINT); last_s >= 0 (0 = the current frame)."""
    s = real(meta, "seconds")
    if s is not None and s != 0:
        raise ValueError(HOLD_HINT)
    v = real(meta, "last_s", 0.0)
    if v < 0:
        raise ValueError("last_s must be a finite number >= 0")
    return v


SPEC["timing"] = {"recorder": {"cameras": RING_CAMS, "fps": round(1.0 / (RING_DT * RING_EVERY), 3), "buffer_s": RING_S,
                               "records": "during /submit", "depth": []}}


def _ctrl_step(tg, rec) -> bool:
    """One control step with targets `tg`; returns True if the episode ended (the step cap, a DexToolBench goal timeout).
    Reaching every goal ends nothing (it is recorded, never shown; the verdict reads the tracker at the end)."""
    S.step(tg); row = np.asarray(S.targets, float).copy(); RECORD.append(row); RECF.write(row.tobytes()); E["journal_rows"] += 1; rec.tick()
    if KIND == "dtb":
        p = S.progress()
        if AGENT_END: _hidden_success(p["done"], len(RECORD))   # counted, never shown; the episode goes on
        if p["failed"]: finish("goal timeout"); return True
    if MAX_CONTROL_STEPS and len(RECORD) >= MAX_CONTROL_STEPS: finish(CAP_REASON); return True
    return False




# ---- request parsing: everything here runs BEFORE any physics. A malformed request is the caller's mistake: it raises
# ValueError (answered 400, nothing executed), never a simulator error (500, which ends the episode; PROTOCOL §4.6).
VIDEO_MODES = ("mp4", "frames", "both", "none")


def real(meta: dict, key: str, default=None):
    """meta[key] as a float: a JSON number (not true/false, not a string), finite; absent or null -> `default`. Anything
    else is a ValueError (400), the same field check as every eai-standard/3.0 layer (rcb_service.real)."""
    v = meta.get(key)
    if v is None: return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise ValueError(f"{key} must be a finite number (got {v!r:.60})")
    return float(v)


def _fps(meta: dict) -> float:
    fps = real(meta, "video_fps", 10.0)
    if not 1 <= fps <= MAX_VIDEO_FPS: raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
    return fps


def _num(meta: dict, key: str, default: float) -> float:
    """A finite numeric request field (a JSON number); anything else (a string, true/false, NaN, Infinity) is a 400."""
    return real(meta, key, default)


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


def _frame_budget(cams, fps: int, steps: int, depth: bool) -> None:
    """Refuse (400, before anything runs) a call of `steps` control steps whose Recorder would take more than
    MAX_FRAMES_PER_CALL images: per camera the forced first and last frame and one every _every(fps) steps (the stride
    it really films at, not the requested fps), depth counted again."""
    n = (int(steps) // _every(fps) + 2) * len(cams) * (2 if depth else 1)
    if n > MAX_FRAMES_PER_CALL: raise ValueError(f"this call would return {n} images (cameras x frames at the capture stride, depth counted again); "
                                                 f"the limit is max_frames_per_call = {MAX_FRAMES_PER_CALL}: use fewer cameras, a lower video_fps or a shorter chunk")


def parse_submit(meta: dict, parts: dict) -> dict:
    """Validate a /submit request completely; returns what do_submit executes. No physics, no state change."""
    if meta.get("type", "joint_position") != "joint_position": raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
    hold = _hold_seconds(meta, parts)
    if hold is not None:      # a rows-free hold chunk: the current targets held for `seconds` (eai-standard/3.0)
        k = max(1, int(round(hold / CTRL_DT)))
        cams = _cameras(meta, list(CAMS)[:1]); fps = _fps(meta); video = _video(meta, "mp4"); depth = bool(meta.get("include_depth", False))
        _frame_budget(cams, fps, k, depth)
        return {"hold": hold, "k": k, "cams": cams, "fps": fps, "video": video, "depth": depth, "note": str(meta.get("note") or "")[:500]}
    raw = parts["actions"].get("data") if isinstance(parts.get("actions"), dict) else meta.get("actions", [])
    try: A = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError): raise ValueError(f"actions must be a numeric array (T, {N})") from None
    if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"joint_position actions must be (T, {N}), got {list(A.shape)}")
    if A.shape[0] < 1: raise ValueError('a chunk without rows is a hold chunk: {"type": <type>, "interpolate": "hold", "seconds": n}')
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    dt = _num(meta, "dt", CTRL_DT)
    if not 0 < dt <= 1e6: raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}")
    k = int(round(dt / CTRL_DT))
    if k < 1 or abs(k * CTRL_DT - dt) > 1e-6: raise ValueError(f"dt must be a positive multiple of control_dt={CTRL_DT}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}")
    interp = meta.get("interpolate", "linear")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    cams = _cameras(meta, list(CAMS)[:1]); fps = _fps(meta); video = _video(meta, "mp4"); depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, A.shape[0] * k, depth)
    return {"A": A, "dt": dt, "k": k, "interp": interp, "cams": cams, "fps": fps, "video": video, "depth": depth, "note": str(meta.get("note") or "")[:500]}


def parse_observe(meta: dict) -> dict:
    """Validate an /observe request completely; returns what do_observe executes."""
    cams = _cameras(meta, list(CAMS)); last_s = _last_s(meta); fps = _fps(meta); video = _video(meta, "frames"); depth = bool(meta.get("include_depth", False))
    if last_s > 0 and depth: raise ValueError(DEPTH_PAST)   # the recorder keeps RGB only (spec timing.recorder.depth = [])
    _frame_budget(cams, fps, 0, depth)
    return {"cams": cams, "last_s": last_s, "fps": fps, "video": video, "depth": depth}


def do_submit(q: dict):
    if "hold" in q: return do_hold(q)
    A, dt, k, interp, cams, fps, video, depth = (q[x] for x in ("A", "dt", "k", "interp", "cams", "fps", "video", "depth"))
    before = len(RECORD)
    rec = Recorder(cams, fps, depth, ring=True); rec.tick(force=True); prev = np.asarray(S.targets, float).copy(); n_clip = 0; done = False
    clipped: list = []   # [{row, index, reason}] of the rows executed; n_clip: how many of those rows had one
    executed = 0   # rows begun: fewer than the chunk's when the episode ends inside it (the step cap, a goal timeout)
    for ri, row in enumerate(A.astype(np.float64)):
        executed += 1
        tgt = np.clip(row, S.lower, S.upper); bad = np.flatnonzero(tgt != row); n_clip += int(bad.size > 0)
        clipped += [{"row": ri, "index": int(j), "reason": f"{NAMES[j] if j < len(NAMES) else j} outside [{S.lower[j]:g}, {S.upper[j]:g}]"} for j in bad]
        for j in range(1, k + 1):
            tg = tgt if interp == "hold" else prev + (tgt - prev) * (j / k)
            if _ctrl_step(tg, rec): done = True; break
        prev = tgt
        if done: break
    rec.tick(force=True); E["calls"] += 1; E["rows"] += executed; RECF.flush()
    if AGENT_END and KIND != "dtb": _hidden_success(S.check()["success"], len(RECORD))   # the state's success: never shown
    out = {**meta_common(), "chunk_id": E["calls"], "type": "joint_position", "executed_rows": executed,
           "control_steps_chunk": len(RECORD) - before, "clipped": clipped[:200], "n_clipped": len(clipped), "n_clipped_rows": n_clip,
           "duration_s": round((len(RECORD) - before) * CTRL_DT, 6), "planned_duration_s": round(int(A.shape[0]) * dt, 6),
           "frame_step": len(RECORD), "ok": True}   # frame_step: the control step its newest image shows (eai-standard/3.0)
    log({"ev": "submit", "call": E["calls"], "type": "joint_position", "rows": int(A.shape[0]), "dt": dt, "interpolate": interp, "cameras": cams,
         "note": q["note"], "control_steps": len(RECORD), "n_clipped": len(clipped), "n_clipped_rows": n_clip, "task": task_info(),
         "rows_total": E["rows"], **_journal_pos(), "state_sha": S.state_sha(), **_ae_state()})
    d = os.path.join(DATA, "calls", f"{E['calls']:06d}"); os.makedirs(d, exist_ok=True); np.save(os.path.join(d, "actions.npy"), A.astype(np.float32))
    return out, rec.parts(video, 1.0 / (RING_DT * rec.every))   # the capture's real frame rate


def do_hold(q: dict):
    """A rows-free hold chunk (eai-standard/3.0): the current targets held for q["k"] control steps, answered as a /submit."""
    cams, fps, video, depth, k = (q[x] for x in ("cams", "fps", "video", "depth", "k"))
    before = len(RECORD)
    rec = Recorder(cams, fps, depth, ring=True); rec.tick(force=True)
    hold = np.asarray(S.targets, float).copy()
    for _ in range(k):
        if _ctrl_step(hold, rec): break
    rec.tick(force=True); E["calls"] += 1; RECF.flush()
    if AGENT_END and KIND != "dtb": _hidden_success(S.check()["success"], len(RECORD))   # the state's success: never shown
    out = {**meta_common(), "chunk_id": E["calls"], "type": "joint_position", "hold": True, "executed_rows": 0,
           "control_steps_chunk": len(RECORD) - before, "clipped": [], "n_clipped": 0, "n_clipped_rows": 0,
           "duration_s": round((len(RECORD) - before) * CTRL_DT, 6), "planned_duration_s": round(q["hold"], 6),
           "frame_step": len(RECORD), "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": "joint_position", "rows": 0, "hold_s": q["hold"], "cameras": cams,
         "note": q["note"], "control_steps": len(RECORD), "n_clipped_rows": 0, "task": task_info(),
         "rows_total": E["rows"], **_journal_pos(), "state_sha": S.state_sha(), **_ae_state()})
    return out, rec.parts(video, 1.0 / (RING_DT * rec.every))   # the capture's real frame rate


def do_observe(q: dict):
    """/observe never lets time pass (eai-standard/3.0): last_s = 0 the current frame, last_s = n the recorder's frames of
    the last n robot seconds (none recorded yet: the current frame)."""
    cams, last_s, fps, video, depth = (q[x] for x in ("cams", "last_s", "fps", "video", "depth"))
    pick = _ring_pick(last_s, fps, len(cams)) if last_s > 0 else []
    E["calls"] += 1
    log({"ev": "observe", "call": E["calls"], "last_s": last_s, "cameras": cams, "control_steps": len(RECORD),
         "rows_total": E["rows"], **_journal_pos(), "state_sha": S.state_sha(), **_ae_state()})
    if not pick:
        rec = Recorder(cams, fps, depth); rec.tick(force=True)
        return ({**meta_common(), "obs_id": E["calls"], "last_s": 0.0, "frame_step": len(RECORD), "ok": True},
                rec.parts("frames" if video == "mp4" else video, fps))
    rec = Recorder(cams, fps, False)
    for f in pick:
        for c in cams:
            rec.frames[c].append(f["imgs"][c])
            if c in rec.pose: rec.pose[c].append(f["pose"][c])
        rec.prop.append(f["prop"])
    steps = np.asarray([f["step"] for f in pick], np.int64)
    out = {**meta_common(), "obs_id": E["calls"], "last_s": round((steps[-1] - steps[0]) * CTRL_DT, 4), "frame_step": int(steps[-1]), "ok": True}
    gap = float(steps[-1] - steps[0]) / max(1, len(steps) - 1)
    rate = 1.0 / (RING_DT * gap) if gap else float(fps)   # the frames' real spacing, not the requested fps
    return out, rec.parts(video, rate) + [rcb1.array_part("frame_step", steps)]


def _journal_pos() -> dict:
    """Where a checkpoint (a completed call's log line) sits in the journal: what a resume replays (the current episode =
    journal rows ep_start .. journal_rows) and how many resets came before it."""
    return {"journal_rows": E["journal_rows"], "ep_start": E["ep_start"], "resets": E["resets"]}


def parse_reset(meta: dict) -> dict:
    """Validate a /reset request completely (the start's frames: cameras, include_depth; no physics)."""
    cams = _cameras(meta, list(CAMS)); fps = _fps(meta); video = _video(meta, "frames"); depth = bool(meta.get("include_depth", False))
    _frame_budget(cams, fps, 0, depth)
    return {"cams": cams, "fps": fps, "video": "frames" if video == "mp4" else video, "depth": depth}


class Refused(Exception):
    """A request refused before anything changed (409)."""
    def __init__(self, body: dict): super().__init__(body.get("error")); self.body = body


def check_reset() -> None:
    """409 when no new episode may start: the trial is over (the agent's /finish or its time is up), or the budget is spent."""
    if AGENT_END and E["done"] and E["reason"] in ("finished", "timeout"):
        raise Refused({"error": "episode finished", "reason": E["reason"], "resets_left": 0})
    if E["stopping"] or E.get("finalizing"):
        raise Refused({"error": "trial finished: your time is up", "reason": E["reason"], "resets_left": 0})
    if E["resets"] >= RESET_BUDGET:
        raise Refused({"error": "reset budget exhausted", "reason": "reset budget exhausted", "budget": RESET_BUDGET, "resets_left": 0})


def do_reset(q: dict):
    """Abandon the running episode (it ends with reason "reset" unless it had ended already) and start a new one from the
    frozen start state. The journal keeps every episode's rows; RECORD (what is graded) restarts empty."""
    if not E["done"]: finish("reset")
    try:
        S.reset()
    except Exception:   # the simulator failed to start the new episode: the trial ends on a simulator error
        E["done"] = True; E["reason"] = "error"; log({"ev": "end", "reason": "error", "reset_failed": True, "control_steps": len(RECORD), **_journal_pos()}); write_final()
        raise
    E["resets"] += 1; E["ep_start"] = E["journal_rows"]; RECORD.clear(); RING.clear()
    E["done"] = False; E["reason"] = None; E["t_end"] = None; E["now_success"] = False; E["seen_step"] = None
    rec = Recorder(q["cams"], q["fps"], q["depth"]); rec.tick(force=True)
    E["calls"] += 1; RECF.flush()
    log({"ev": "reset", "call": E["calls"], "cameras": q["cams"], "control_steps": 0, "rows_total": E["rows"], **_journal_pos(),
         "state_sha": S.state_sha()})
    write_final()
    return {**meta_common(), "reset_id": E["calls"], "frame_step": len(RECORD), "ok": True}, rec.parts(q["video"], q["fps"])


def finalize() -> None:
    """The verdict: the live episode's (docs/protocol/README.md H.4; owner, 2026-10-17). The graded episode (every
    control step since the last reset) is saved as the trajectory, and the task's rule is read off the live simulator:
    DexToolBench, every goal reached (the goal tracker ran on every executed control step, as the privileged replay runs
    it); Playground, the tooling's check() of the final state. Nothing is replayed to grade it. final.json is finalized
    before the video, which is one render pass over the trajectory from the frozen start and never changes the verdict."""
    with LOCK:
        A = None
        try:
            err = E["reason"] == "error"   # a simulator error ended the episode: the state after it is never judged
            A = np.asarray(RECORD, float).reshape(-1, N); live_sha = S.state_sha()
            live = {} if err else (S.progress() if KIND == "dtb" else S.check())
            np.savez(os.path.join(DATA, "trajectory.npz"), actions=A, tool=TOOL.__name__, meta=json.dumps({"source": "standard-mode episode", "reason": E["reason"],
                                                                                                          "episode": E["resets"] + 1, "reset_budget": RESET_BUDGET}))
            v = {"graded_by": "live", "replays": 0, "n_actions": int(len(A)), "live_state_sha": live_sha, "state_sha": live_sha,
                 "video": False, "video_pending": True, "video_source": "render"}
            if err:
                v.update(success=False, live_success=False)
            elif KIND == "dtb":
                ok = bool(live["done"]) and (not AGENT_END or E["reason"] in END_STATE_REASONS)
                v.update(success=ok, live_success=ok, progress=round(float(live["progress"]), 4), goals_reached=int(live["reached"]),
                         n_goals=int(live["n_goals"]), failed_on_timeout=bool(live["failed"]), live_goals_reached=int(live["reached"]))
            else:
                v.update(success=bool(live["success"]) and (not AGENT_END or E["reason"] in END_STATE_REASONS), live_success=bool(live["success"]),
                         **{k: val for k, val in live.items() if k not in ("success", "state_sha", "steps") and isinstance(val, (int, float, bool))})
            # The verdict is final and on disk (finalized) before any video is rendered: the video never changes, hides or
            # delays it (a slow or failing render, or a collect hook that stops waiting, leaves the verdict as it is).
            E["verdict"] = v; E["finalized"] = True; write_final()
        except Exception as exc:  # noqa
            traceback.print_exc()
            if not E["finalized"]:        # no verdict was reached: the service itself failed (not the agent's 0)
                log({"ev": "finalize_error", "error": repr(exc)}); E["verdict"] = {"finalize_error": repr(exc)[:300]}
        if E["finalized"] and A is not None:
            try:   # the video: one pass over the trajectory from the frozen start (the live simulator, reset), rendered aside
                if hasattr(TOOL, "MAX_STEPS"): TOOL.MAX_STEPS = max(int(TOOL.MAX_STEPS), len(A))   # the privileged hand-in cap
                tmp = os.path.join(DATA, "replay.tmp.mp4")                 # a half-written replay.mp4 is never collected
                S.render_video(A, tmp, every=max(2, len(A) // 600), fps=25)
                os.replace(tmp, os.path.join(DATA, "replay.mp4"))
                if os.path.exists(os.path.join(DATA, "replay.tmp.last.png")): os.replace(os.path.join(DATA, "replay.tmp.last.png"), os.path.join(DATA, "replay.last.png"))
                E["verdict"]["video"] = True
            except Exception: traceback.print_exc()  # noqa -- the video is for people; it never decides the verdict
        E["finalized"] = True; E["video_done"] = True
        if isinstance(E.get("verdict"), dict) and "video_pending" in E["verdict"]: E["verdict"]["video_pending"] = False
        try: write_final()
        except Exception: traceback.print_exc()  # noqa


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    if AGENT_END and reason == "finished": E["finish_t"] = E["t_end"]
    log({"ev": "end", "reason": reason, "control_steps": len(RECORD), **_journal_pos(),
         **({"finish_t": E["finish_t"]} if reason == "finished" else {})}); write_final()


def _status() -> dict:
    return {"calls": E["calls"], "control_steps": len(RECORD), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1), **_reset_counters(), **_steps_left()}


def start_finalize() -> None:
    if E.get("finalizing"): return
    E["finalizing"] = True; threading.Thread(target=finalize, daemon=True).start()


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _rcb1(self, meta, parts):
        if rcb1.size(meta, parts) > MAX_RESP:   # known before anything is built: the body is built once
            for p in parts:
                if p[0].startswith(("frames/", "depth/")) and isinstance(p[2], rcb1.Frames): p[2].arrays.clear()
            parts = [p for p in parts if not (p[0].startswith("frames/") or p[0].startswith("depth/"))]; meta = {**meta, "degraded": "frames/depth dropped (response too large)"}
        body = rcb1.encode(meta, parts)
        self.send_response(200); self.send_header("Content-Type", "application/x-rcb1"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def _length(self) -> int:
        try: n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError: raise ValueError("bad Content-Length") from None
        if n < 0: raise ValueError("bad Content-Length")   # read(-1) would read until the client hangs up, without any bound
        if n > MAX_BODY: raise ValueError("request too large")
        return n
    def _body(self):
        n = self._length()
        raw = self.rfile.read(n) if n else b""
        if raw[:4] == rcb1.MAGIC: return rcb1.decode(raw)
        b = json.loads(raw or b"{}")
        if not isinstance(b, dict): raise ValueError("body must be a JSON object or an RCB1 frame")
        return b, {}
    def do_GET(self):
        _touch()
        if self.path == "/spec": return self._json(200, SPEC)
        if self.path == "/status": return self._json(200, _status())
        return self._json(404, {"error": "no such endpoint"})
    def do_POST(self):
        _touch()
        if self.path not in ("/submit", "/observe") + (("/reset",) if RESET_BUDGET else ()) + (("/finish",) if AGENT_END else ()): return self._json(404, {"error": "no such endpoint"})
        try:
            if self.path == "/finish":   # its body is ignored, never parsed: only its size is checked
                n = self._length()
                if n: self.rfile.read(n)
                self._req = ({}, {})
            else: self._req = self._body()
        except Exception as exc: return self._json(413 if str(exc) == "request too large" else 400, {"error": str(exc)[:200]})
        with LOCK:
            log({"ev": "call_begin", "path": self.path, "call": E["calls"] + 1})
            try:
                return self._serve()
            finally:
                log({"ev": "call_end", "path": self.path})

    def _serve(self):
        meta, parts = self._req
        if self.path == "/finish":   # agent-ended episodes: the agent ends the episode; the state it leaves is graded
            if E["done"] or E["stopping"] or E.get("finalizing"): return self._json(409, {"error": "episode finished", "reason": E["reason"]})
            finish("finished"); return self._json(200, {"ok": True, **_status()})
        if self.path == "/observe" and AGENT_END and E["done"] and E["reason"] == "finished":
            return self._json(409, {"error": "episode finished", "reason": E["reason"]})   # after /finish: only /spec, /status
        if self.path == "/observe" and (E["stopping"] or E.get("finalizing")):   # after the session's end (as rcb_service)
            return self._json(409, {"error": "trial finished: your time is up", "reason": E["reason"]})
        if self.path == "/submit" and E["done"]:
            return self._json(409, {"error": "episode finished", "reason": E["reason"], **({"resets_left": _reset_counters()["resets_left"]} if RESET_BUDGET else {})})
        if self.path == "/reset":
            try: check_reset()
            except Refused as exc: return self._json(409, exc.body)
        try:      # the whole request is checked before any physics: whatever is wrong with it is a 400 and changes nothing
            if not isinstance(meta, dict) or not isinstance(parts, dict): raise ValueError("the request's meta must be a JSON object")
            q = {"/submit": parse_submit, "/observe": lambda m, _p: parse_observe(m), "/reset": lambda m, _p: parse_reset(m)}[self.path](meta, parts)
        except (ValueError, TypeError, OverflowError, AttributeError, KeyError, IndexError) as exc:
            return self._json(400, {"error": (str(exc) or type(exc).__name__)[:300]})
        try:
            out, blobs = {"/submit": do_submit, "/observe": do_observe, "/reset": do_reset}[self.path](q)
        except Exception as exc:  # noqa
            traceback.print_exc(); log({"ev": "error", "error": repr(exc)}); finish("error")   # PROTOCOL §4.6: a 500 ends the episode
            return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        return self._rcb1(out, blobs)


def _end_from_signal():
    with LOCK:
        E["stopping"] = True                         # the agent's time is up: no new episode after this one
        if not E["done"]: finish("timeout")
    start_finalize()


def _resume_or_start() -> None:
    """Fresh start, or (after a crash: compose restarts the container) resume the SAME episode. The journal holds every
    executed control step; the log holds, per completed call, the step count and the state hash. Replaying the journal up
    to the last completed call rebuilds that exact state (MuJoCo on the CPU is bit-exact) and the hash is checked. A call
    in flight when the service died is lost as a whole; its caller got an error, not a result, so nothing is gained. No
    reset: the episode never goes back to its start. With a reset budget the journal holds every episode; a checkpoint
    carries where the current one begins (ep_start) and the resets before it, and only that episode is replayed (from the
    frozen start, as a reset begins it); a reset lost with its call never happened. More than MAX_RESUMES crashes end it; if every crash happened while
    serving a call, it counts as the agent's (sim_crashed_on_call), else as infrastructure (sim_crashed)."""
    ev = _events(); starts = [e for e in ev if e.get("ev") == "start"]
    if not starts:
        # The frozen start is checked when the episode begins (the verdict is the live episode's: no later replay checks
        # it): a scene that did not build to the instance's recorded hash is no trial of this task, before the agent is served.
        if START_SHA and S.state_sha() != START_SHA:
            _give_up("instance_mismatch", infra=True, instance_mismatch=1, start_sha=S.state_sha(), instance_sha=START_SHA,
                     error=f"the scene started at {S.state_sha()}, the frozen instance records {START_SHA}")
        try: os.remove(REC_PATH)
        except OSError: pass
        log({"ev": "start", "tool": TOOL.__name__, "state_sha": S.state_sha(), "instance_sha": START_SHA or None, "protocol": PROTOCOL}); write_final()
        E["t0"] = time.time(); return
    try: fin = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: fin = {}  # noqa
    if _graded(fin): _give_up("restarted after finalize", infra=False)
    resumes = [e for e in ev if e.get("ev") == "resumed"]
    in_call = bool(ev) and ev[-1].get("ev") == "call_begin"
    crashes_in_calls = sum(1 for e in resumes if e.get("crashed_in_call")) + int(in_call)
    if len(resumes) >= MAX_RESUMES:
        _give_up("sim_crashed_on_call" if crashes_in_calls == len(resumes) + 1 else "sim_crashed", infra=crashes_in_calls != len(resumes) + 1)
    done = [e for e in ev if e.get("ev") in ("submit", "observe", "reset") and "state_sha" in e]
    last = done[-1] if done else starts[0]
    n = int(last.get("journal_rows", last.get("control_steps", 0)))           # journal rows (all episodes) at that checkpoint
    ep0 = int(last.get("ep_start", 0)); resets = int(last.get("resets", 0))
    try: R = np.fromfile(REC_PATH, dtype=np.float64)
    except OSError: R = np.zeros(0)
    if R.size < n * N: _give_up("resume_failed: journal shorter than the log", infra=True)
    R = R[: n * N].reshape(n, N)
    for row in R[ep0:]:                                  # the current episode, from the frozen start
        S.step(row); RECORD.append(row.copy())
    if S.state_sha() != last["state_sha"]: _give_up("resume_failed: replayed state differs from the logged one", infra=True)
    R.tofile(REC_PATH)                                   # drop the steps of the call that was in flight
    E["calls"] = int(last.get("call", 0)); E["rows"] = int(last.get("rows_total", 0)); E["t0"] = float(starts[0]["ts"])
    E["resets"] = resets; E["ep_start"] = ep0; E["journal_rows"] = n
    first = [e for e in ev if e.get("ev") == "first_request"]
    if first: E["t_first"] = float(first[0]["ts"])       # the agent's clock keeps running through a crash
    # the current episode's end, not the lost call's (past the checkpoint), not an earlier episode's, not a lost reset's
    ended = [e for e in ev if e.get("ev") == "end" and e.get("reason") != "reset" and int(e.get("resets", 0)) == resets
             and int(e.get("journal_rows", e.get("control_steps")) or 0) <= n]
    if ended: E["done"] = True; E["reason"] = ended[-1].get("reason"); E["t_end"] = float(ended[-1]["ts"])
    _ae_restore(last, ev)                                # the hidden success of the episode, as the checkpoint had it
    E["stopping"] = any(e.get("ev") == "end" and e.get("reason") == "timeout" for e in ev)   # the agent's time was up already
    log({"ev": "resumed", "control_steps": len(RECORD), "journal_rows": n, "resets": resets, "calls": E["calls"], "state_sha": S.state_sha(), "crashed_in_call": in_call,
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
