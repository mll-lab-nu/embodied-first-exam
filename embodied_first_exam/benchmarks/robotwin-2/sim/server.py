"""eai-standard/2.1 sim service for RoboTwin 2.0 (see docs/protocol/standard_mode.md).
Owns the scene and the seed. HTTP surface: GET /spec, GET /status, POST /observe, POST /submit (both RCB1 bodies,
RCB1 responses: videos / frames / depth / proprio as raw blobs, never base64). Logs every call to /data/episode.jsonl,
keeps /data/final.json current, and on episode end grades the live episode: success = RoboTwin's check_success on the
episode this service ran (it ends at the first call after which the check holds; at the end of the agent's time the
final state is checked once more), nothing replayed (docs/protocol/README.md H.4; owner, 2026-10-17). The verdict
goes to final.json first ("finalized": true, "graded_by": "live"); then the recorded (T,34) trajectory, which is the
deliverable, is rendered once for people: the six-view /data/replay.mp4 and /data/live.mp4 (rcb_live.py: call-stamped
frames only while physics ran, skipped while nothing moved) in one pass ("video_pending": true while it runs; it never
changes the verdict). It also saves each call's actions under /data/calls/ and appends the trajectory to
/data/trajectory_live.f64 after every call (crash-safe). Nothing about objects ever leaves this process."""
from __future__ import annotations
import errno, io, json, math, os, signal, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RCB_AGENT_TRACE_DIR"] = ""  # the service records the episode itself (rcb_live, trajectory); no per-rollout agent traces
import rcb1  # noqa: E402
import rcb_live  # noqa: E402

PROTOCOL = "eai-standard/2.1"
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)   # RCB_DATA / RCB_PORT: test hooks (never set in tasks)
TASK = os.environ.get("RCB_TASK", "stack_blocks_two"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
TASK_TEXT = json.load(open(INSTANCE)).get("text", TASK)
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
PHYS_HZ = 250; MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
MAX_BODY = 64 * 1024 * 1024; MAX_RESP = 256 * 1024 * 1024
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "frames": [], "error": None}

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
TRAJ_LIVE = os.path.join(DATA, "trajectory_live.f64")       # journal: every physics step's row, float64
MAX_VIDEO_FPS = 30; MAX_FRAMES_PER_CALL = 3000


def _events() -> list:
    try: return [json.loads(l) for l in open(os.path.join(DATA, "episode.jsonl")) if l.strip()]
    except OSError: return []


def _dump_final(d: dict) -> None:
    """final.json is replaced atomically: a reader (the collect hook's copy, the verifier) never sees half a file."""
    tmp = os.path.join(DATA, ".final.json.tmp")
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, os.path.join(DATA, "final.json"))


def _verdict_on_disk(d: dict) -> bool:
    """The live episode's verdict is written before any video; from then on it stands."""
    return isinstance(d, dict) and d.get("graded_by") == "live"


def _give_up(reason: str, infra: bool) -> None:
    """End the trial's episode without a new one: mark it failed (a verdict already on disk is kept, whether or not its
    videos were finished), keep the PID file for the collect hook, and idle."""
    faulthandler.cancel_dump_traceback_later()   # this process idles from here on: the startup watchdog must not end it
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f: f.write(json.dumps({"ts": time.time(), "ev": "restart_refused", "reason": reason}) + "\n")
    try: prev = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: prev = {}  # noqa
    if not isinstance(prev, dict): prev = {}
    if _verdict_on_disk(prev): prev.update(finalized=True, video_pending=False)   # the verdict stands; only a video may be missing
    elif prev.get("finalized"): pass   # an earlier give-up or finalize error stands as written
    else: prev.update({"success": False, "done": True, "reason": reason, "finalized": True, "protocol": PROTOCOL, **({"infra_error": 1} if infra else {})})
    _dump_final(prev)
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    signal.signal(signal.SIGUSR1, lambda *_: None); print(f"restart refused: {reason}", flush=True)
    while True: time.sleep(3600)
with open(os.path.join(DATA, "startups.jsonl"), "a") as _f: _f.write(json.dumps({"ts": time.time(), "pid": os.getpid()}) + "\n")

# Back off before rebuilding after a failed start (e.g. a GPU out-of-memory crash while other trials hold the GPU): compose
# restarts immediately, so without a pause every retry meets the same full GPU (seen: 4 starts in 75 s, all failed).
_n_starts = sum(1 for _ in open(os.path.join(DATA, "startups.jsonl")))
if _n_starts > 1 and not os.path.exists(os.path.join(DATA, "episode.jsonl")): time.sleep(min(120, 20 * (_n_starts - 1)))
if os.environ.get("RCB_TEST_CRASH_ONCE") and sum(1 for _ in open(os.path.join(DATA, "startups.jsonl"))) == 1:
    sys.exit("RCB_TEST_CRASH_ONCE: simulated startup crash")   # test hook for the restart path (never set in tasks)
# A restart that finds the trial already decided (the verdict, e.g. the service died while it rendered the video; or a
# give-up) keeps it and idles at once, without rebuilding the scene.
try: _fin0 = json.load(open(os.path.join(DATA, "final.json")))
except Exception: _fin0 = {}  # noqa
if isinstance(_fin0, dict) and (_verdict_on_disk(_fin0) or _fin0.get("finalized")): _give_up("restarted after finalize", infra=False)


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), **ev}) + "\n")


def write_final() -> None:
    """success = live_success: RoboTwin's check_success on the live episode (E["success"]); "graded_by": "live" marks the
    verdict (written once, at the episode's end, before any video). "video_pending": the one render pass is running."""
    _dump_final({"success": bool(E["success"]), "live_success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "physics_steps": int(E.get("episode_physics_steps") or (int(S._sim_steps) if E["ready"] else 0)),
                 "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": PROTOCOL,
                 "finalized": bool(E.get("finalized")), "n_actions": E.get("n_actions"), "replays": 0,
                 **({"graded_by": "live", "live_sha": E.get("live_sha"), "video_source": "render", "video_pending": bool(E.get("video_pending"))} if E.get("graded_by") else {}),
                 "video": bool(E.get("video")),
                 **{k: E[k] for k in ("trajectory_error", "video_error") if E.get(k)},
                 # the service could not record the episode's end (not the agent's episode): no verdict, an infrastructure error
                 **({"finalize_error": 1, "infra_error": 1} if E.get("finalize_error") else {}),
                 **{k: E[k] for k in ("live_video", "live_frames", "live_skipped", "live_mode", "live_fps", "live_error", "live_truncated") if k in E}})


def finalize() -> None:
    """The verdict is the live episode's (E["success"], judged by finish() on this simulator after the agent's last call):
    written at once, nothing replayed. Then the deliverable (trajectory.npz; trajectory_live.f64 holds the same rows) and
    ONE render pass from it for the videos, which can no longer change the verdict."""
    with LOCK:
        acts = None
        try:
            try: E.update(LIVE.close())
            except Exception as exc: E["live_error"] = repr(exc)  # noqa
            flush_traj()
            acts = S.record_stop(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts))
            try:
                S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (v2)", "steps": E["step"], "reason": E["reason"]})
            except Exception as exc:  # noqa — the journal trajectory_live.f64 holds the same rows; the verdict does not depend on it
                traceback.print_exc(); E["trajectory_error"] = repr(exc)[:300]
            E["graded_by"] = "live"; E["video_pending"] = True; E["finalized"] = True
            log({"ev": "verdict", "graded_by": "live", "success": bool(E["success"]), "reason": E["reason"], "n_actions": E["n_actions"], "live_sha": E["live_sha"]})
            write_final()   # the verdict is on disk before any video is rendered (videos never gate grading)
        except Exception as exc:  # noqa
            traceback.print_exc(); log({"ev": "finalize_error", "error": repr(exc)})
            E["finalize_error"] = repr(exc); E["finalized"] = True; write_final()   # no verdict: the grader reports infra_error
            return
        try:   # one pass over the trajectory renders both videos (replay.mp4: six views; live.mp4: labelled by call)
            E.update(LIVE.render_videos(acts, os.path.join(DATA, "replay.mp4"), every=max(10, len(acts) // 600), fps=25))
        except Exception as exc:  # noqa — a failed render loses the video only
            traceback.print_exc(); E["video_error"] = repr(exc)[:300]
        E["video_pending"] = False; write_final()


def start_finalize() -> None:
    if E.get("finalizing"): return
    E["finalizing"] = True; threading.Thread(target=finalize, daemon=True).start()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_physics_steps"] = int(S._sim_steps)
    if not E["success"]:
        try: E["success"] = bool(ENV.check_success())
        except Exception: pass
    # rows: the journal rows the end belongs to. A resume keeps an end only if its rows are within the last checkpoint: an
    # end logged by a call that was lost with a crash never happened (as the call itself)
    log({"ev": "end", "reason": reason, "step": E["step"], "physics_steps": int(S._sim_steps), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"]),
         "rows": len(S._recording or [])})
    write_final(); start_finalize()


# ---------------------------------------------------------------- scene
from rcb_traj import Session  # noqa: E402
try:
    # gripper_state="command": RoboTwin's own rule (the gripper value Robot.set_gripper stores). The service drives the
    # fingers only through set_gripper, so the value cannot be set apart from them (the privileged verifier, which
    # replays rows an agent wrote, reads the finger targets instead: rcb_traj.Session.gripper_opening).
    S = Session(TASK, instance=INSTANCE, enable_render=True, gripper_state="command")
except RuntimeError as _exc:
    # This host does not rebuild the frozen instance (PROTOCOL §3: seen for four tasks on L40S cards). Before an episode
    # began: after one retry say so in final.json (infra_error) instead of crash-looping until compose gives up. On a
    # resume (the episode began on this host, so the rebuild drifted since): at once; the episode cannot be continued.
    if "instance state hash" in str(_exc) and (_n_starts >= 2 or any(e.get("ev") == "start" for e in _events())):
        traceback.print_exc(); _give_up(f"instance_mismatch: {_exc}"[:300], infra=True)
    raise
E["built"] = True; faulthandler.cancel_dump_traceback_later()    # the scene exists: the startup watchdog stands down (a resume replay may take minutes)
S.max_rows = None   # a standard episode has no row cap (PROTOCOL §4.4): the tool's hand-in cap for privileged trajectories (rcb_traj.MAX_T) is not its
ENV = S.env; ROBOT = ENV.robot
ENV.step_lim = None; ENV.eval_video_path = None; ENV.take_action_cnt = 0; ENV.eval_success = False; ENV.now_obs = {}
L_ARM = [j.get_name() for j in ROBOT.left_arm_joints]; R_ARM = [j.get_name() for j in ROBOT.right_arm_joints]
ALL_CAMS = ["head_camera", "front_camera", "left_camera", "right_camera", "observer_camera", "world_camera1"]
WRIST_CAMS = ("left_camera", "right_camera")     # mounted on the arms: their extrinsics change with every motion


def joint_limits() -> dict:
    out = {}
    for j in list(ROBOT.left_arm_joints) + list(ROBOT.right_arm_joints):
        lo, hi = [float(x) for x in np.asarray(j.get_limits()).reshape(-1)[:2]]
        out[j.get_name()] = [lo, hi] if (math.isfinite(lo) and math.isfinite(hi) and hi - lo < 2 * math.pi + 1e-6) else None   # None = continuous, never clipped
    return out
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] or [-np.inf, np.inf] for n in L_ARM + R_ARM], dtype=np.float64)  # (12, 2)

_EE = lambda p: [f"{p}_x", f"{p}_y", f"{p}_z", f"{p}_qw", f"{p}_qx", f"{p}_qy", f"{p}_qz"]
PROPRIO_GROUPS = {   # name: (first column, n, meaning)
    "joint_cmd": (0, 14, "commanded joint targets (6 + gripper command per arm), same layout as joint_position"),
    "ee_pose": (14, 14, "measured end-effector frame pose per arm (xyz + wxyz), 0.12 m behind the gripper centre; valid ee_pose target"),
    "gripper_cmd": (28, 2, "commanded gripper value per arm (0 closed .. 1 open)"),
    "joint_pos": (30, 14, "measured joint positions (encoders) + measured gripper opening in the command's units; a gripper "
                          "closed on an object stops above 0"),
    "joint_vel": (44, 12, "measured arm joint velocities, rad/s"),
    "tcp_pose": (56, 14, "measured gripper-centre (TCP) pose per arm, xyz + wxyz: where the fingers are"),
    "joint_effort": (70, 12, "drive-effort estimate per arm joint, stiffness*(target-q) + damping*(v_target-qd) (motor-current analogue; "
                             "rises when the arm pushes against something)"),
}
PROPRIO_LAYOUT = (L_ARM + ["left_gripper"] + R_ARM + ["right_gripper"] + _EE("l") + _EE("r") + ["left_gripper_cmd", "right_gripper_cmd"]
                  + [f"{n}_meas" for n in L_ARM] + ["left_gripper_meas"] + [f"{n}_meas" for n in R_ARM] + ["right_gripper_meas"]
                  + [f"{n}_vel" for n in L_ARM + R_ARM] + _EE("l_tcp") + _EE("r_tcp") + [f"{n}_effort" for n in L_ARM + R_ARM])
assert len(PROPRIO_LAYOUT) == 82

SPEC = {
    "protocol": PROTOCOL, "simulator": "robotwin-2.0", "robot": os.environ.get("RCB_EMBODIMENT", "aloha-agilex"), "task_text": TASK_TEXT,
    "physics_hz": PHYS_HZ, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "max_video_fps": MAX_VIDEO_FPS, "max_frames_per_call": MAX_FRAMES_PER_CALL,
    "on_service_error": ("if a call fails with a connection error or 5xx, the service may have crashed and resumed the same episode "
                         "(never a reset): the state is the one after the last call that completed on the service, which you may "
                         "not have received; check GET /status before continuing"), "cameras": {c: {"rgb": True, "depth": c in ("head_camera", "front_camera", "left_camera", "right_camera"),
             "mounted": {"left_camera": "left wrist", "right_camera": "right wrist"}.get(c, "static"), "calibration_in_obs": OBS_CALIBRATION} for c in ALL_CAMS},
    "camera_calibration": ("meta['cameras'][name] of every response = that camera's intrinsic_cv / extrinsic_cv / cam2world_gl in the state the "
                           "response ends in (the `last` frame, and the final sample of frames / depth). Static cameras never move. The wrist "
                           "cameras move with the arms: for each requested wrist camera the response also carries the part `cam2world_gl/<cam>`, "
                           "float64 (n_frames, 4, 4), one camera-to-world pose (OpenGL axes) per returned frame of that camera "
                           "(client: res.raw['cam2world_gl/<cam>']['data'])"),
    "action_types": {
        "joint_position": {"dim": 14, "optional_dim": 28, "layout": L_ARM + ["left_gripper"] + R_ARM + ["right_gripper"], "units": "rad; gripper in [0,1], 0 = closed, 1 = open",
                           "limits": LIMITS, "limits_note": "null = continuous joint (no limit, never clipped)",
                           "semantics": "drive targets streamed at physics rate; rows `dt` apart, hold or linear interpolation between rows; out-of-limit values are clipped and reported. "
                                        "Optional columns 14..27 = joint velocity feed-forward (rad/s, same 14-slot layout; gripper slots ignored) held over the row; "
                                        "without them the service uses the central difference of the streamed targets"},
        "ee_pose": {"dim": 16, "layout": ["l_x", "l_y", "l_z", "l_qw", "l_qx", "l_qy", "l_qz", "left_gripper", "r_x", "r_y", "r_z", "r_qw", "r_qx", "r_qy", "r_qz", "right_gripper"],
                    "frame": "world: origin at the table centre on the floor plane, +z up, robot base at y = -0.65 facing +y, table top at z ~= 0.74",
                    "quaternion": "wxyz, unit norm",
                    "semantics": "each row is planned by CuRobo (table-only collision) and executed; `dt` is ignored (the planner sets the duration); a failed plan holds that arm and is reported in plan[]",
                    "note": "same convention as proprio endpose: RoboTwin's end-effector frame, 0.12 m BEHIND the gripper centre (TCP) along the approach axis; to put the fingers at p command p - 0.12*approach_axis"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "3600")),
               "wall_clock_note": ("meta time_s / time_left_s count from your first request to the service (any endpoint), not from the "
                                   "service's start, and keep running through a restart of the service; time_left_s = budget.wall_clock_s - "
                                   "time_s. The harness counts the same limit from the start of your session, so time_left_s never runs out "
                                   "before the harness stops you: your real time left is time_left_s minus the time you spent before that "
                                   "first request. Plan by time_left_s.")},
    "episode": "one episode, no reset: it ends at the first success (RoboTwin's check_success), when your time is up, or on a simulator error",
}


# ---- proprioception (what a real arm reports: encoders, gripper position, forward kinematics, motor effort)
def _arm_io(side: str):
    ent = ROBOT.left_entity if side == "left" else ROBOT.right_entity
    act = ent.get_active_joints(); joints = ROBOT.left_arm_joints if side == "left" else ROBOT.right_arm_joints
    finger = (ROBOT.left_gripper if side == "left" else ROBOT.right_gripper)[0]           # (joint, multiplier, bias)
    scale = ROBOT.left_gripper_scale if side == "left" else ROBOT.right_gripper_scale
    return ent, [act.index(j) for j in joints], act.index(finger[0]), finger, scale
ARM_IO = {s_: _arm_io(s_) for s_ in ("left", "right")}


def _drive_gain(j, name):
    for a in (name, f"get_{name}"):
        v = getattr(j, a, None)
        if v is not None:
            try: return float(v() if callable(v) else v)
            except Exception: pass  # noqa
    return float("nan")


def _measured(side: str):
    """Measured joint positions/velocities (encoders), measured gripper opening in the command's [0,1] units (from the
    finger joint), and a drive-effort estimate k*(target-q) + d*(v_target-qd) per arm joint (a motor-current analogue)."""
    ent, idx, fidx, finger, scale = ARM_IO[side]
    q = np.asarray(ent.get_qpos(), dtype=np.float64); qd = np.asarray(ent.get_qvel(), dtype=np.float64)
    joints = ROBOT.left_arm_joints if side == "left" else ROBOT.right_arm_joints
    eff = []
    for j, i in zip(joints, idx):
        tgt = float(np.asarray(j.get_drive_target()).reshape(-1)[0]); vt = float(np.asarray(j.get_drive_velocity_target()).reshape(-1)[0])
        eff.append(_drive_gain(j, "stiffness") * (tgt - q[i]) + _drive_gain(j, "damping") * (vt - qd[i]))
    real = (q[fidx] - finger[2]) / finger[1]; g = (real - scale[0]) / (scale[1] - scale[0])
    return q[idx], qd[idx], float(np.clip(g, -0.2, 1.2)), eff


def proprio_row() -> np.ndarray:
    lj = ROBOT.get_left_arm_jointState(); rj = ROBOT.get_right_arm_jointState()
    le = ENV.get_arm_pose("left"); re_ = ENV.get_arm_pose("right")
    base = list(lj[:-1]) + [lj[-1]] + list(rj[:-1]) + [rj[-1]] + list(le) + list(re_) + [ROBOT.left_gripper_val, ROBOT.right_gripper_val]
    lq, lqd, lg, leff = _measured("left"); rq, rqd, rg, reff = _measured("right")
    lt = ROBOT.get_left_tcp_pose(); rt = ROBOT.get_right_tcp_pose()
    ext = list(lq) + [lg] + list(rq) + [rg] + list(lqd) + list(rqd) + list(lt) + list(rt) + list(leff) + list(reff)
    return np.array(base + ext, dtype=np.float32)


def calib() -> dict:
    """Every camera's intrinsic_cv / extrinsic_cv / cam2world_gl in the CURRENT state. Computed for every response: the
    wrist cameras ride on the arms, so their extrinsics change whenever an arm moves (the static cameras' never do)."""
    ENV._update_render(); ENV.cameras.update_picture(); out = {}
    for k, v in ENV.cameras.get_config().items():
        out[k] = {kk: (np.asarray(vv).tolist() if hasattr(vv, "shape") or isinstance(vv, (list, tuple)) else vv) for kk, vv in v.items()}
    return out
if OBS_CALIBRATION: calib()   # fail at startup, not in the first response, if the cameras cannot be read


DEPTH_NOISE = os.environ.get("RCB_DEPTH_NOISE", "off").strip().lower()   # off | realsense
_RNG = np.random.default_rng(int(os.environ.get("RCB_DEPTH_NOISE_SEED", "0")))


def _depth_noise(d: np.ndarray) -> np.ndarray:
    """Optional stereo-camera-like depth: noise grows with distance squared, 1% dropouts (0 = no reading). Off by default."""
    if DEPTH_NOISE != "realsense": return d
    z = d.astype(np.float32); valid = z > 0
    unit = 1000.0 if float(np.nanmax(z) if z.size else 0) > 20 else 1.0          # RoboTwin depth is in mm
    zm = z / unit; noisy = zm + _RNG.normal(0.0, 1.0, z.shape).astype(np.float32) * (0.002 + 0.0025 * zm * zm)
    noisy[_RNG.random(z.shape) < 0.01] = 0.0; noisy[~valid] = 0.0
    return noisy * unit


def grab(cameras: list[str], depth: bool) -> tuple[dict, dict]:
    imgs = {c: S.render_frame(c) for c in cameras}
    dep = {}
    if depth:
        try:
            ENV._update_render(); ENV.cameras.update_picture(); dd = ENV.cameras.get_depth()
            for c in cameras:
                if c in dd: dep[c] = _depth_noise(np.asarray(dd[c]["depth"], dtype=np.float32)).astype(np.float16)
        except Exception:  # noqa
            traceback.print_exc()
    return imgs, dep


class Recorder:
    """Collects frames every `every` physics steps for the requested cameras, plus proprio at each frame."""
    def __init__(self, cameras, fps, depth):
        self.cams = cameras; self.every = max(1, int(round(PHYS_HZ / max(1, fps)))); self.depth = depth
        self.frames = {c: [] for c in cameras}; self.dep = {c: [] for c in cameras}; self.prop = []; self.n = 0
        self.pose = {c: [] for c in cameras if c in WRIST_CAMS} if OBS_CALIBRATION else {}   # a wrist camera: its pose with every frame
    def tick(self, force=False):
        if force or self.n % self.every == 0:
            imgs, dep = grab(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(imgs[c][..., :3])
                if c in dep: self.dep[c].append(dep[c])
            if self.pose:   # grab() has just updated the render scene: the wrist cameras are where the frame was taken from
                cfg = ENV.cameras.get_config()
                for c in self.pose: self.pose[c].append(np.asarray(cfg[c]["cam2world_gl"], dtype=np.float64))
            self.prop.append(proprio_row())
        self.n += 1
    def parts(self, video: str, fps: int):
        out = []
        for c in self.cams:
            fr = np.stack(self.frames[c]) if self.frames[c] else np.zeros((0, 240, 320, 3), np.uint8)
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
            if video in ("frames", "both"):
                out.append(rcb1.array_part(f"frames/{c}", fr))
            if len(fr): out.append(rcb1.array_part(f"last/{c}", fr[-1]))
            if self.dep[c]: out.append(rcb1.array_part(f"depth/{c}", np.stack(self.dep[c])))
            if self.pose.get(c): out.append(rcb1.array_part(f"cam2world_gl/{c}", np.stack(self.pose[c])))
        out.append(rcb1.array_part("proprio", np.stack(self.prop) if self.prop else np.zeros((0, len(PROPRIO_LAYOUT)), np.float32)))
        return out


def touch_clock() -> None:
    """The agent's clock starts at its first request to the service (any endpoint), not when the simulator came up
    (which is before the agent's session begins). Logged, so a resumed service keeps the same origin."""
    if E.get("t_agent0") is None:
        E["t_agent0"] = time.time(); log({"ev": "first_request"})


def agent_time_s() -> float:
    return 0.0 if E.get("t_agent0") is None else time.time() - E["t_agent0"]


def meta_common() -> dict:
    t = agent_time_s()
    return {"step": E["step"], "calls": E["calls"], "physics_steps": int(S._sim_steps), "sim_time_s": round(int(S._sim_steps) / PHYS_HZ, 3),
            "time_s": round(t, 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - t, 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            **({"cameras": calib()} if OBS_CALIBRATION else {})}   # the calibration of the state this response ends in


def save_call_evidence(idx: int, meta: dict, rec: Recorder) -> None:
    d = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(d, exist_ok=True)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"))
    try:
        from PIL import Image
        for c in rec.cams:
            if rec.frames[c]: Image.fromarray(np.ascontiguousarray(rec.frames[c][-1])).save(os.path.join(d, f"last_{c}.jpg"), quality=85)
    except Exception:  # noqa
        pass


# ---------------------------------------------------------------- executing chunks
def clip_joint_row(row: np.ndarray, clipped: list, ri: int) -> np.ndarray:
    r = row.copy()
    idx = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]
    for k, j in enumerate(idx):
        lo, hi = LIM_ARR[k]
        if r[j] < lo or r[j] > hi: clipped.append({"row": ri, "index": int(j), "reason": f"joint limit [{lo:.3f},{hi:.3f}]"}); r[j] = float(np.clip(r[j], lo, hi))
    for j in (6, 13):
        if r[j] < 0 or r[j] > 1: clipped.append({"row": ri, "index": int(j), "reason": "gripper range [0,1]"}); r[j] = float(np.clip(r[j], 0, 1))
    return r


def apply_joint_target(q: np.ndarray, vel: np.ndarray) -> None:
    ROBOT.set_arm_joints(q[0:6], vel[0:6], "left"); ROBOT.set_arm_joints(q[7:13], vel[7:13], "right")
    ROBOT.set_gripper(float(q[6]), "left"); ROBOT.set_gripper(float(q[13]), "right")


def current_joint_cmd() -> np.ndarray:
    lj = ROBOT.get_left_arm_jointState(); rj = ROBOT.get_right_arm_jointState()   # commanded drive targets + gripper val
    return np.array(list(lj) + list(rj), dtype=np.float64)


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * PHYS_HZ))); dt_step = 1.0 / PHYS_HZ
    q_prev = current_joint_cmd()
    rows = [clip_joint_row(row[:14].astype(np.float64), clipped, ri) for ri, row in enumerate(A)]
    vff = A[:, 14:28].astype(np.float64) if A.shape[1] >= 28 else None    # optional velocity feed-forward per row
    # dense 250 Hz target stream for the whole chunk; velocity feed-forward = the given per-row velocities, or a
    # central difference of the streamed targets (as a planner's velocity profile would be; last sample backward).
    dense, dvel = [], []
    for ri, target in enumerate(rows):
        for k in range(1, steps_per_row + 1):
            dense.append(target if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row))
            if vff is not None: dvel.append(vff[ri])
        q_prev = target
    Q = np.stack([current_joint_cmd()] + dense)                       # (1 + n, 14); Q[0] = where the drives are now
    if vff is not None: V = np.stack([np.zeros(14)] + dvel)
    else: V = np.zeros_like(Q); V[1:-1] = (Q[2:] - Q[:-2]) / (2 * dt_step); V[-1] = (Q[-1] - Q[-2]) / dt_step
    for i in range(1, len(Q)):
        apply_joint_target(Q[i], V[i])
        S.step(); LIVE.tick(); rec.tick()
        if E["done"]: return


def run_ee_pose(A: np.ndarray, rec: Recorder, plan: list) -> None:
    for ri, row in enumerate(A):
        lq, rq = row[3:7], row[11:15]
        row = row.copy(); row[3:7] = lq / max(1e-9, np.linalg.norm(lq)); row[11:15] = rq / max(1e-9, np.linalg.norm(rq))
        lp = ROBOT.left_plan_path(list(map(float, row[0:7]))); rp = ROBOT.right_plan_path(list(map(float, row[8:15])))
        st = {"row": ri, "left": (lp or {}).get("status", "?") if isinstance(lp, dict) else "?", "right": (rp or {}).get("status", "?") if isinstance(rp, dict) else "?"}
        plan.append(st)
        lok = isinstance(lp, dict) and lp.get("status") == "Success"; rok = isinstance(rp, dict) and rp.get("status") == "Success"
        ln = int(lp["position"].shape[0]) if lok else 0; rn = int(rp["position"].shape[0]) if rok else 0
        n = max(ln, rn, 50 if not (lok or rok) else 0)
        gl, gr = float(np.clip(row[7], 0, 1)), float(np.clip(row[15], 0, 1)); gl0, gr0 = ROBOT.left_gripper_val, ROBOT.right_gripper_val
        li = ri_ = 0
        for k in range(n):
            if lok and li < ln and (not rok or li / ln <= ri_ / max(1, rn)): ROBOT.set_arm_joints(lp["position"][li], lp["velocity"][li], "left"); li += 1
            if rok and ri_ < rn and (not lok or ri_ / rn <= li / max(1, ln)): ROBOT.set_arm_joints(rp["position"][ri_], rp["velocity"][ri_], "right"); ri_ += 1
            a = (k + 1) / n
            ROBOT.set_gripper(gl0 + (gl - gl0) * a, "left"); ROBOT.set_gripper(gr0 + (gr - gr0) * a, "right")
            S.step(); LIVE.tick(); rec.tick()
            if E["done"]: return


def flush_traj() -> None:
    """Append the rows recorded since the last flush to /data/trajectory_live.f64 (raw float64, 34 per row)."""
    rows = S._recording or []; k = E.get("flushed", 0)
    if len(rows) > k:
        with open(os.path.join(DATA, "trajectory_live.f64"), "ab") as f: f.write(np.asarray(rows[k:], dtype=np.float64).tobytes())
        E["flushed"] = len(rows)


def _fps(meta: dict) -> int:
    try: fps = int(meta.get("video_fps", 10))
    except (TypeError, ValueError, OverflowError): raise ValueError("video_fps must be an integer") from None
    if not 1 <= fps <= MAX_VIDEO_FPS: raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
    return fps


def _num(meta: dict, key: str, default: float) -> float:
    """A numeric request field; anything else is the caller's mistake (400), never a simulator error."""
    try:
        v = meta.get(key, default)
        if isinstance(v, bool): raise TypeError     # JSON true is no number (float(True) is 1.0)
        v = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be a number") from None
    if not math.isfinite(v): raise ValueError(f"{key} must be a finite number")
    return v


def _cams(meta: dict, default: list) -> list:
    c = meta.get("cameras")
    if not c: return [x for x in default if x in ALL_CAMS] or ["head_camera"]
    if isinstance(c, str): c = [c]
    if not isinstance(c, (list, tuple)): raise ValueError("cameras must be a list of camera names")
    # unknown names are ignored; a repeated name is dropped BEFORE the frame budget and any rendering (the recorder keeps
    # frames per name, so repeats would multiply its work)
    return list(dict.fromkeys(x for x in c if isinstance(x, str) and x in ALL_CAMS)) or ["head_camera"]


def _bad_request(exc: Exception) -> ValueError:
    """A field of the wrong type that slipped past the explicit checks is still the caller's mistake: 400, no physics."""
    return ValueError(f"malformed request: {exc!r}"[:200])


def _frame_budget(cams, fps: int, seconds: float, depth: bool) -> None:
    n = (int(seconds * fps) + 2) * len(cams) * (2 if depth else 1)
    if n > MAX_FRAMES_PER_CALL: raise ValueError(f"this call would return {n} frames (cameras x fps x seconds, depth counts double); "
                                                 f"the limit is {MAX_FRAMES_PER_CALL}: use fewer cameras, a lower video_fps or a shorter chunk")


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    try:   # validation only: nothing below this block runs unless the whole request is well-formed
        typ = meta.get("type"); dt = _num(meta, "dt", 0.02); interp = meta.get("interpolate", "linear")
        cams = _cams(meta, ["head_camera"])
        fps = _fps(meta); video = meta.get("video", "mp4"); depth = bool(meta.get("include_depth", False))
        if not isinstance(typ, str) or typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
        dim = SPEC["action_types"][typ]["dim"]; dims = (dim, SPEC["action_types"][typ].get("optional_dim", dim))
        if A.ndim != 2 or A.shape[1] not in dims: raise ValueError(f"{typ} actions must be (T, {dim}) or (T, {dims[1]}), got {list(A.shape)}")
        if A.shape[0] < 1: raise ValueError(f"{typ} actions must have at least one row, got {list(A.shape)}")
        if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
        if not (1.0 / PHYS_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0/PHYS_HZ:.4f}, 0.5] s")
        if typ == "joint_position" and abs(dt * PHYS_HZ - round(dt * PHYS_HZ)) > 1e-6: raise ValueError(f"dt must be a multiple of the physics step 1/{PHYS_HZ} s (e.g. 0.004, 0.008, 0.02)")
        _frame_budget(cams, fps, (A.shape[0] * dt) if typ == "joint_position" else 10.0, depth)
        if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
        if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
        if not isinstance(interp, str) or interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
        if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
        note_full = "" if meta.get("note") is None else str(meta.get("note"))
    except (TypeError, OverflowError, AttributeError, KeyError) as exc:
        raise _bad_request(exc) from None
    rec = Recorder(cams, fps, depth); clipped: list = []; plan: list = []
    note = note_full.replace("\n", " ")[:40]
    LIVE.set_label(E["calls"] + 1, f"submit {typ} x{A.shape[0]}" + (f" dt={dt:g}" if typ == "joint_position" else "") + (f"  [{note}]" if note else ""))
    before = int(S._sim_steps); rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, rec, plan)
    rec.tick(force=True); LIVE.end_call()
    E["step"] += int(A.shape[0]); E["calls"] += 1
    succ = bool(ENV.check_success()); E["success"] = E["success"] or succ
    out = {**meta_common(), "chunk_id": E["calls"], "type": typ, "executed_rows": int(A.shape[0]), "physics_steps_chunk": int(S._sim_steps) - before,
           "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": int(A.shape[0]), "dt": dt, "interpolate": interp, "cameras": cams, "note": note_full[:500],
         "physics_steps": int(S._sim_steps) - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    try: np.save(os.path.join(DATA, "calls", f"{E['calls']:06d}", "actions.npy"), A.astype(np.float32))
    except Exception: pass  # noqa
    flush_traj(); log({"ev": "checkpoint", "call": E["calls"], "step": E["step"], "rows": E.get("flushed", 0), "success": E["success"], "state_sha": S.state_sha()})
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    try:   # validation only (as in do_submit)
        cams = _cams(meta, ALL_CAMS[:4])
        seconds = _num(meta, "seconds", 0); fps = _fps(meta); video = meta.get("video", "frames"); depth = bool(meta.get("include_depth", False))
        if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
        _frame_budget(cams, fps, seconds, depth)
    except (TypeError, OverflowError, AttributeError, KeyError) as exc:
        raise _bad_request(exc) from None
    rec = Recorder(cams, fps, depth); before = int(S._sim_steps); rec.tick(force=True); succ = False
    if seconds > 0 and not E["done"]:
        LIVE.set_label(E["calls"] + 1, f"observe watch {seconds:g}s")
        for _ in range(int(seconds * PHYS_HZ)):
            S.step(); LIVE.tick(); rec.tick()
        rec.tick(force=True); LIVE.end_call()
        succ = bool(ENV.check_success()); E["success"] = E["success"] or succ
    E["calls"] += 1
    out = {**meta_common(), "obs_id": E["calls"], "seconds": seconds, "physics_steps_watch": int(S._sim_steps) - before, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "physics_steps": int(S._sim_steps) - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec); flush_traj()
    if seconds > 0: log({"ev": "checkpoint", "call": E["calls"], "step": E["step"], "rows": E.get("flushed", 0), "success": E["success"], "state_sha": S.state_sha()})
    # the episode ends only after the checkpoint (as in do_submit): a crash before it loses the whole call, end included,
    # and the agent watches again from the state before it; never a "done" whose success the resume cannot see
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


class H(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _rcb1(self, meta: dict, parts: list) -> None:
        body = rcb1.encode(meta, parts)
        if len(body) > MAX_RESP:  # degrade: drop frames/depth, keep mp4 + last + proprio
            parts = [p for p in parts if not (p[0].startswith("frames/") or p[0].startswith("depth/"))]; meta = {**meta, "degraded": f"response over {MAX_RESP} bytes: frames/depth dropped"}
            body = rcb1.encode(meta, parts)
        self.send_response(200); self.send_header("Content-Type", "application/x-rcb1"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
    def _body(self):
        try: n = int(self.headers.get("Content-Length", 0))
        except ValueError: raise ValueError("bad Content-Length")
        if n < 0: raise ValueError("bad Content-Length")   # read(-1) would read until the client hangs up, without any bound
        if n > MAX_BODY: raise ValueError("request too large")
        raw = self.rfile.read(n) if n else b""
        if raw[:4] == rcb1.MAGIC:
            meta, parts = rcb1.decode(raw)
            if not isinstance(meta, dict) or not isinstance(parts, dict): raise ValueError("RCB1 frame: the header must be a JSON object")
            return meta, parts
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict): raise ValueError("body must be a JSON object or an RCB1 frame")
        return body, {}
    def do_GET(self):
        if self.path in ("/spec", "/status"): touch_clock()
        if self.path == "/spec": return self._json(200, SPEC)
        if self.path == "/status": return self._json(200, {"step": E["step"], "calls": E["calls"], "physics_steps": int(S._sim_steps), "done": E["done"], "reason": E["reason"], "elapsed_s": round(time.time() - E["t0"], 1)})
        return self._json(404, {"error": "no such endpoint"})
    def do_POST(self):
        if self.path not in ("/submit", "/observe"): return self._json(404, {"error": "no such endpoint"})
        try: meta, parts = self._body()
        except Exception as exc: return self._json(413 if str(exc) == "request too large" else 400, {"error": str(exc)[:200]})
        with LOCK:
            touch_clock()
            log({"ev": "call_begin", "path": self.path, "call": E["calls"] + 1})
            try: return self._serve(meta, parts)
            finally: log({"ev": "call_end", "path": self.path})

    def _serve(self, meta, parts):
        if True:
            if self.path == "/submit":
                if E["done"]: return self._json(409, {"error": "episode finished", "reason": E["reason"]})
                try: A = np.asarray(parts["actions"]["data"] if "actions" in parts else meta.get("actions", []), dtype=np.float64)
                except (TypeError, ValueError, KeyError, OverflowError, AttributeError) as exc: return self._json(400, {"error": f"actions: {exc}"[:200]})
                try:
                    out, blobs = do_submit(meta, A)
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                except Exception as exc:  # noqa
                    traceback.print_exc(); E["error"] = repr(exc); log({"ev": "error", "error": repr(exc)}); finish("error")
                    return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
            else:
                try:
                    out, blobs = do_observe(meta)
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                except Exception as exc:  # noqa
                    traceback.print_exc(); E["error"] = repr(exc); log({"ev": "error", "error": repr(exc)}); finish("error")
                    return self._json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        return self._rcb1(out, blobs)


def _end_from_signal():
    with LOCK:
        if not E["done"]: finish("timeout")
        else: start_finalize()


def on_usr1(*_):
    threading.Thread(target=_end_from_signal, daemon=True).start()

def _resume_or_start() -> None:
    """Fresh start, or (after a crash: compose restarts the container) resume the SAME episode, never a reset. The
    journal (trajectory_live.f64) holds every physics step's row; each completed call logs a checkpoint (rows so far,
    state hash). Replaying the journal up to the last checkpoint rebuilds that state (the replay is deterministic; the
    hash is checked). A call in flight when the service died is lost as a whole: its caller got an error, not a result.
    More than MAX_RESUMES crashes end the episode: sim_crashed_on_call if every crash happened while serving a call (the
    agent's), else sim_crashed (infrastructure)."""
    S.record_start()
    ev = _events(); starts = [e for e in ev if e.get("ev") == "start"]
    if not starts:
        try: os.remove(TRAJ_LIVE)
        except OSError: pass
        log({"ev": "start", "task": TASK, "seed": S.seed, "state_sha": S.state_sha(), "protocol": PROTOCOL}); write_final()
        E["t0"] = time.time(); return
    try: fin = json.load(open(os.path.join(DATA, "final.json")))
    except Exception: fin = {}  # noqa
    if _verdict_on_disk(fin): _give_up("restarted after finalize", infra=False)   # the verdict stands (a video may be missing)
    resumes = [e for e in ev if e.get("ev") == "resumed"]
    in_call = bool(ev) and ev[-1].get("ev") == "call_begin"
    crashes_in_calls = sum(1 for e in resumes if e.get("crashed_in_call")) + int(in_call)
    if len(resumes) >= MAX_RESUMES:
        agent = crashes_in_calls == len(resumes) + 1
        _give_up("sim_crashed_on_call" if agent else "sim_crashed", infra=not agent)
    cps = [e for e in ev if e.get("ev") == "checkpoint"]
    last = cps[-1] if cps else {"rows": 0, "step": 0, "call": 0, "success": False, "state_sha": starts[0]["state_sha"]}
    n = int(last["rows"]); D = S.action_dim
    try: R = np.fromfile(TRAJ_LIVE, dtype=np.float64)
    except OSError: R = np.zeros(0)
    if R.size < n * D: _give_up("resume_failed: journal shorter than the log", infra=True)
    R = R[: n * D].reshape(n, D)
    for row in R: S.step(row)
    if S.state_sha() != last["state_sha"]: _give_up("resume_failed: replayed state differs from the logged one", infra=True)
    R.tofile(TRAJ_LIVE); E["flushed"] = n
    E["calls"] = int(last.get("call", 0)); E["step"] = int(last.get("step", 0)); E["success"] = bool(last.get("success")); E["t0"] = float(starts[0]["ts"])
    _first = [e for e in ev if e.get("ev") == "first_request"]
    if _first: E["t_agent0"] = float(_first[0]["ts"])
    # the episode's end, if it is within the last checkpoint: an end past it was logged by a call lost with the crash (an
    # end before 2026-10-14 carries no rows and is kept, as before)
    ended = [e for e in ev if e.get("ev") == "end" and int(e.get("rows") or 0) <= n]
    if ended: E["done"] = True; E["reason"] = ended[-1].get("reason"); E["t_end"] = float(ended[-1]["ts"]); E["episode_physics_steps"] = int(ended[-1].get("physics_steps") or n)
    log({"ev": "resumed", "rows": n, "calls": E["calls"], "state_sha": S.state_sha(), "crashed_in_call": in_call, "downtime_s": round(time.time() - float(ev[-1]["ts"]), 1)})
    if not E["done"] and E["success"]:
        # the call that succeeded completed (its checkpoint holds the success) and the crash came before its end was
        # logged: the episode ends here, as that call would have ended it (a success ends the episode)
        E["done"] = True; E["reason"] = "success"; E["t_end"] = float(last.get("ts") or time.time()); E["episode_physics_steps"] = int(S._sim_steps)
        log({"ev": "end", "reason": "success", "step": E["step"], "physics_steps": int(S._sim_steps), "elapsed_s": round(E["t_end"] - E["t0"], 1),
             "success": True, "rows": n, "on_resume": True})
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
signal.signal(signal.SIGUSR1, on_usr1)
if _USR1["pending"]: on_usr1()
E["ready"] = True
LIVE = rcb_live.LiveRecorder(S, DATA, t0=E["t0"]); LIVE.open()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready", flush=True)
_bind(int(os.environ.get("RCB_PORT", "8000")), H).serve_forever()
