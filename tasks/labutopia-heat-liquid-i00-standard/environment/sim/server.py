"""eai-standard/2.2 sim service for the LabUtopia tasks (docs/STANDARD_MODE.md): the adapter of the shared layer
rcb_limited.py; the simulator is rcb_labutopia.Session (LabUtopia on Isaac Sim, PhysX on the CPU, RTX cameras). HTTP
surface: GET /spec, GET /status, POST /observe, POST /submit, POST /kinematics. Every call is logged to
/data/episode.jsonl.

The episode is the frozen instance's (environment/sim/instance.json, the privileged twin's). A control step is one
physics step (1/60 s) with a position target and a velocity target for each of the Franka's 9 joints: `joint_position`
rows give the position targets (velocity targets zero), `joint_position_velocity` rows give both, which is what
LabUtopia's own controllers send. The episode ends the moment the family's rule is met (success). Nothing about the
objects or the instruments leaves this process: the proprioception is the robot's own joints, gripper, tool frame and
commands.

Crash recovery (rcb_limited.Episode, resume class `exact`: PhysX on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service, a fresh process, rebuilds the episode and replays the
journal. When the episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect hook
(finalize.sh) makes it exit and replays the trajectory in two fresh processes."""

import json
import math
import os
import sys
import threading
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data")
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.json"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
MAX_FPS = 30  # every second control step; a call returns at most MAX_FRAMES frames per camera
MAX_FRAMES = 300
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {
    "ready": False,
    "step": 0,
    "calls": 0,
    "done": False,
    "reason": None,
    "success": False,
    "t0": time.time(),
    "error": None,
}

os.environ["RCB_SESSION_LOG"] = ""
import rcb_labutopia as M  # noqa: E402

M.SESSION_LOG = ""  # the sidecar's Session is not the agent's interaction log
W, H = M.W, M.H
_INST = json.load(open(INSTANCE))
TASK = _INST["family"]
NA = int(_INST["n_action"])  # the journal's row width, known before the scene is built
EP = L.Episode(DATA, dim=NA, resume="exact")
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()


def first_start() -> float:
    """When this container's service was first started (startups.jsonl, kept across restarts). The agent's budget runs
    from about then: Harbor starts the sidecar with the environment, and the scene takes minutes to build before the
    episode's own clock (E["t0"], set when the service is ready) starts."""
    try:
        with open(EP.f_startups) as f:
            return float(json.loads(f.readline())["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        return time.time()


T_FIRST = first_start()
S = M.Session(instance=INSTANCE, cameras=True)
assert M.N_ACT == NA, (M.N_ACT, NA)
for _c in S.cameras():  # the first frame rendered in a container takes minutes (Isaac Sim prepares the stage for its
    S.render_frame(_c)  # renderer once): it is rendered here, before the service answers, not in an agent's call
DT = S.dt
CTRL_HZ = float(M.CONTROL_HZ)
SUBSTEPS = 1
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
TASK_INFO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "task.json")))
CAMS = S.cameras()
DEFAULT_CAMS = [c for c in TASK_INFO.get("default_cameras") or S.default_cameras() if c in CAMS]
ND = M.N_DOF
ROBOT_SPEC = S.robot_spec()
J_NAMES = [j["name"] for j in ROBOT_SPEC["joints"]]
UNITS = [j["unit"] for j in ROBOT_SPEC["joints"]]
J_LIMITS = np.array([j["position_limits"] for j in ROBOT_SPEC["joints"]], dtype=np.float64)  # joint_position: the joints' own ranges
LAYOUT18 = [f"q_{n}" for n in J_NAMES] + [f"qd_{n}" for n in J_NAMES]
LIMITS18 = S.action_limits()  # joint_position_velocity: the drives' target ranges (rcb_labutopia.Session.action_limits)
TCPS = ["tcp"]
GROUPS = [
    ("joint_pos", [f"q_{n}" for n in J_NAMES], "joint positions: the seven arm joints (rad), then the two fingers (m from the centre line)"),
    ("joint_vel", [f"qd_{n}" for n in J_NAMES], "joint velocities (rad/s; m/s)"),
    ("gripper_opening", ["gripper_opening"], "metres between the two fingers (0 .. 0.08)"),
    ("tcp_pose", [f"tcp_{c}" for c in ("x", "y", "z", "qw", "qx", "qy", "qz")],
     "the tool frame (the point between the fingertips) in the world frame: position (m) and wxyz quaternion"),
    ("joint_effort", [f"effort_{n}" for n in J_NAMES],
     "what each joint's drive asks for, by its own law: stiffness x (position target - q) + damping x (velocity target - "
     "qdot), limited to the effort limit (N m; N for the fingers); it grows when the arm or a finger pushes on something"),
    ("command", [f"cmd_{n}" for n in LAYOUT18], "the targets in effect: 9 position targets, then 9 velocity targets (the last row executed)"),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)
KIN_JOINTS = [f"q_{n}" for n in M.ARM_JOINTS]
LINKS = ["tcp", "panda_hand"]
MOUNT = {c: S.camera_mount(c) for c in CAMS}
MOUNTED = {c: ("static" if MOUNT[c]["type"] == "static" else f"fixed to the link {MOUNT[c]['parent_link']}: it moves with the arm") for c in CAMS}


def do_kinematics(req: dict) -> dict:
    """The tool frame and the wrist camera's link for arm joint positions (world frame). Never touches the simulation."""
    if req["op"] == "fk":
        return L.fk_response(S.fk(req["q"], req["links"]), "world")
    r = S.ik(req["targets"], seed=req["seed"], tol_pos_m=req["tol_pos_m"], tol_rot_rad=req["tol_rot_rad"], max_iters=req["max_iters"])
    return L.ik_response(r["q"], r["ok"], r["error"], "world",
                         note="damped least squares on the seven arm joints within their ranges; no collision check")


# ------------------------------------------------------------------------------------------------- spec
TASK_TEXT = TASK_INFO["task_text"]
CAP = f"{M.MAX_STEPS} control steps ({M.MAX_STEPS * M.CONTROL_DT:g} s of simulated time)"
PERIOD = "1/60 s"
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "LabUtopia on NVIDIA Isaac Sim (PhysX on the CPU, RTX cameras)",
    "robot": ROBOT_SPEC["name"],
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "max_control_steps": M.MAX_STEPS,
    "cameras": {
        c: {
            "rgb": True,
            "depth": True,
            "resolution": [W, H],
            "intrinsic_cv": S.camera_info(c)["intrinsic_cv"],
            "depth_range_m": S.camera_range(c),
            "mounted": MOUNTED[c],
            "mount": MOUNT[c],
        }
        for c in CAMS
    },
    "default_cameras": DEFAULT_CAMS,
    "action_types": {
        "joint_position": {
            "dim": ND,
            "layout": J_NAMES,
            "limits": {n: [float(v) for v in J_LIMITS[k]] for k, n in enumerate(J_NAMES)},
            "units": dict(zip(J_NAMES, UNITS)),
            "semantics": "absolute position targets of the joints' drives (seven arm joints in rad, then the two "
            f"fingers in m from the centre line), one row per control step; the velocity targets are zero. Rows are "
            f"`dt` apart (a whole multiple of the {PERIOD} control period, at most 0.5 s), `linear` (default: from the "
            "previous target) or `hold` between rows; values outside the joints' ranges are clipped and reported. A "
            f"call returns at most {MAX_FRAMES} frames per camera (video_fps up to {MAX_FPS})",
        },
        "joint_position_velocity": {
            "dim": 2 * ND,
            "layout": LAYOUT18,
            "limits": {n: [float(v) for v in LIMITS18[k]] for k, n in enumerate(LAYOUT18)},
            "units": {n: (u if k < ND else u + "/s") for k, (n, u) in enumerate(zip(LAYOUT18, UNITS + UNITS))},
            "semantics": "a position target and a velocity target for every joint's drive (effort = stiffness * "
            "(position target - q) + damping * (velocity target - qdot)): 9 position targets, then 9 velocity targets. "
            "A position target may lie beyond a joint's range (`limits`): the joint stops at its limit and the drive "
            "keeps pushing, which is how a finger target below the point where the finger meets an object squeezes "
            "it. Rows and `dt` as for joint_position; between rows the position targets are `linear` or `hold`, the "
            "velocity targets are the row's for the whole interval",
        },
        "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": TASK_INFO.get("static", {}),
    "world": {
        "frame": "LabUtopia's world frame: z up; the arm's base is in robot_spec.base (no positions of the scene are given)",
        "up": "+z",
        "units": {"length": "m", "angle": "rad", "time": "s"},
        "quaternion_order": "wxyz",
        "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes",
    },
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": f"one episode, no reset: it ends the moment the goal is reached (success), when your time is over, or after {CAP}",
    "robot_spec": ROBOT_SPEC,
    "kinematics": {
        "endpoint": "/kinematics",
        "joint_names": KIN_JOINTS,
        "frame": "world",
        "quaternion_order": "wxyz",
        "links": LINKS,
        "tcp_frames": TCPS,
        "ee_frames": TCPS,
        "ik_targets": TCPS,
        "ik": {"tol_pos_m": 0.001, "tol_rot_rad": 0.01, "max_iters": 300},
        "note": "the tool frame (robot_spec.tcp) and the link the wrist camera sits on, for arm joint positions q (7, "
        "`joint_names` order); ik: one pose for the tool frame; tol_rot_rad >= 3.1 ignores orientation",
    },
    "depth": {
        "modes": list(L.DEPTH_MODES),
        "default": "none",
        "kind": "z-depth",
        "unit": "m",
        "invalid": 0,
        "max_m": L.DEPTH_MAX_M,
        "frames_encoding": "uint16 mm, zlib",
        "noise": L.DEPTH_NOISE,
    },
}
L.check_spec(SPEC)  # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()


def ctrl_steps() -> int:
    return int(S.steps)


def proprio_row() -> np.ndarray:
    return np.concatenate([
        S.joint_positions(), S.joint_velocities(), [S.gripper_opening()], S.tcp_pose(), S.joint_efforts(), S.command(),
    ]).astype(np.float32)


def grab(cams, want_depth: bool):
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c, (H, W))
        if want_depth:
            dep[c] = S.render_depth(c, (H, W))
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: np.asarray(S.camera_info(c)["extrinsic_cv"], dtype=np.float64) for c in cams}


def write_final() -> None:
    if L.final_verdict(DATA):  # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {**summary(), "finalized": False, "live_sha": E.get("live_sha")})


def summary() -> dict:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    return {
        "success": bool(E["success"]),
        "score": float(E.get("score") if E.get("score") is not None else (1.0 if S.success else 0.0)),
        "steps": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
        "reason": E["reason"],
        "done": E["done"],
        "task": TASK,
        "rule": S.rule_name,
        "protocol": L.PROTOCOL,
        "n_actions": len(ROWS),
        "instance_ok_live": bool(S.instance_ok),
        "start_exact_live": bool(S.start_exact),
        **EP.final_fields(),
    }


def finish(reason: str) -> None:
    """The episode is over: the task's verdict on the steps executed, then the record for the collect hook."""
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    E["episode_control_steps"] = ctrl_steps()
    E["success"] = bool(S.success)
    E["score"] = 1.0 if S.success else 0.0
    EP.log(
        {"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"])}
    )
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    S.save_trajectory(
        np.asarray(ROWS, dtype=np.float64).reshape(-1, NA),
        os.path.join(DATA, "trajectory.npz"),
        meta={"source": "standard-mode episode", "reason": E["reason"]},
    )
    L._write_json(os.path.join(DATA, "episode.json"), {**summary(), "live_sha": E["live_sha"]})
    write_final()


def ctrl_step(a, rec) -> bool:
    """One executed control step, journaled. True when the call must stop here."""
    a = S._row(a)  # the 18 targets as the Session executes them (float32)
    running = S.step(a)
    ROWS.append(a)
    stop = EP.journal(a)
    rec.tick()
    if not running:
        finish(S.reason or "done")
    return E["done"] or stop


def recorder(cams, fps: int, meta: dict, video: str) -> L.Recorder:
    every = max(1, int(round(CTRL_HZ / max(1, fps)))) if video != "none" else 10**9  # no video: first and last frame
    return L.Recorder(
        cams, every, grab, proprio_row, extrinsics, ctrl_steps, depth=L.depth_mode(meta), clock_hz=CTRL_HZ
    )


def checked(parse):
    """A request is checked in full before anything is executed. The layer answers a ValueError with 400 and takes any
    other exception for a simulator error that ends the episode (PROTOCOL §4.6), so whatever a malformed field raises
    while it is being checked (null, a list where a number belongs, a number too large for a float) is a ValueError."""

    def run(*args):
        try:
            return parse(*args)
        except ValueError:
            raise
        except (TypeError, OverflowError, AttributeError, LookupError, ArithmeticError) as exc:
            raise ValueError(f"malformed request: {exc!r}"[:300]) from exc

    return run


def number(meta: dict, key: str, default: float) -> float:
    """A request's number: absent or null is the default; anything but a finite number is a 400."""
    v = meta.get(key)
    if v is None:
        return float(default)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key} must be a number, got {type(v).__name__}")
    try:
        v = float(v)
    except OverflowError:
        v = math.inf
    if not math.isfinite(v):
        raise ValueError(f"{key} must be finite")
    return v


def note_of(meta: dict) -> str:
    """The call's free-text note for the log: checked with the other fields, before anything is executed."""
    v = meta.get("note")
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValueError("note must be a string")
    return v[:500]


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 10
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= MAX_FPS):
        raise ValueError(f"video_fps must be in [1, {MAX_FPS}]")
    return int(fps)


def frames_ok(seconds: float, fps: int, video: str) -> None:
    if video != "none" and seconds * fps + 2 > MAX_FRAMES:
        raise ValueError(f"{seconds:g} s at video_fps={fps} is more than max_frames_per_call={MAX_FRAMES} frames")


def cameras_of(meta: dict) -> list:
    cams = meta.get("cameras") or DEFAULT_CAMS
    if isinstance(cams, str) or not isinstance(cams, (list, tuple)) or not all(isinstance(c, str) for c in cams):
        raise ValueError(f"cameras must be a list of camera names; cameras: {CAMS}")
    bad = [c for c in cams if c not in CAMS]
    if bad:
        raise ValueError(f"unknown cameras {bad}; cameras: {CAMS}")
    return list(cams)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "sim_time_s": round(n * DT, 4),
        "time_s": round(time.time() - E["t0"], 2),  # since the episode started (the service ready)
        "time_left_s": max(0.0, round(WALL_CLOCK_S - (time.time() - T_FIRST), 1)),  # of the agent's budget: the start-up counts
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()},
        "done": E["done"],
        "reason": E["reason"],
        "cameras": {c: S.camera_info(c) for c in cams},
    }


@checked
def parse_submit(meta: dict, A: np.ndarray):
    """Every field of a /submit request and its rows, checked; nothing is executed here."""
    typ = meta.get("type")
    if not isinstance(typ, str) or typ not in ("joint_position", "joint_position_velocity"):
        raise ValueError(f"type must be joint_position or joint_position_velocity (not yet: {SPEC['action_types']['not_yet']})")
    dim = 2 * ND if typ == "joint_position_velocity" else ND
    dt = number(meta, "dt", DT)
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps, note = cameras_of(meta), video_fps(meta), note_of(meta)
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != dim:
        raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (math.isfinite(dt) and dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
        raise ValueError(f"dt must be a whole multiple of the {PERIOD} control period and at most 0.5 s; got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if not isinstance(interp, str) or interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    frames_ok(A.shape[0] * dt, fps, video)
    L.depth_mode(meta)  # a bad `depth` is a 400 here, not after the rows
    return typ, dt, interp, video, cams, fps, note


def do_submit(meta: dict, A: np.ndarray):
    typ, dt, interp, video, cams, fps, note = parse_submit(meta, A)
    both = typ == "joint_position_velocity"
    layout, limits = (LAYOUT18, LIMITS18) if both else (J_NAMES, J_LIMITS)
    k = dt / DT
    rec, clipped = recorder(cams, fps, meta, video), []
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    prev = S.command()[:ND]
    n = int(round(k))
    for ri, row in enumerate(A):
        E["step"] += 1
        row = np.asarray(row, dtype=np.float64)
        target = np.clip(row, limits[:, 0], limits[:, 1])
        for j in np.flatnonzero(target != row)[:20]:
            clipped.append({"row": ri, "index": int(j), "reason": f"{layout[j]} limit [{limits[j, 0]:g}, {limits[j, 1]:g}]"})
        q, qd = target[:ND], (target[ND:] if both else np.zeros(ND))
        stop = False
        for s in range(1, n + 1):
            a = q if (interp == "hold" or s == n) else prev + (q - prev) * (s / n)
            if ctrl_step(np.concatenate([a, qd]), rec):
                stop = True
                break
        prev = q
        if stop:
            break
    rec.tick(force=True, last=True)
    out = {
        **meta_common(cams),
        "chunk_id": E["calls"],
        "type": typ,
        "executed_rows": E["step"] - step0,
        "control_steps_chunk": ctrl_steps() - before,
        "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
        "clipped": clipped[:200],
        "n_clipped": len(clipped),
        "plan": [],
        "ok": True,
    }
    EP.log(
        {
            "ev": "submit",
            "call": E["calls"],
            "type": typ,
            "rows": E["step"] - step0,
            "dt": dt,
            "interpolate": interp,
            "cameras": cams,
            "control_steps": ctrl_steps() - before,
            "n_clipped": len(clipped),
            "note": note,
            **({"stopped": EP.stop_reason} if EP.stopping else {}),
        }
    )
    return out, rec.parts(video, fps)


@checked
def parse_observe(meta: dict):
    """Every field of an /observe request, checked; nothing is executed here."""
    cams, fps = cameras_of(meta), video_fps(meta)
    seconds = number(meta, "seconds", 0.0)
    video = meta.get("video", "frames")
    if seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    frames_ok(seconds, fps, video)
    L.depth_mode(meta)  # a bad `depth` is a 400 here, not after the watch
    return cams, fps, seconds, video


def do_observe(meta: dict):
    cams, fps, seconds, video = parse_observe(meta)
    rec, before = recorder(cams, fps, meta, video), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = S.command()
        for _ in range(int(round(seconds / DT))):
            if ctrl_step(hold, rec):
                break
    rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {
        **meta_common(cams),
        "obs_id": E["calls"],
        "seconds": seconds,
        "control_steps_watch": ctrl_steps() - before,
        "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS,
        "ok": True,
    }
    EP.log(
        {
            "ev": "observe",
            "call": E["calls"],
            "seconds": seconds,
            "cameras": cams,
            "control_steps": ctrl_steps() - before,
            **({"stopped": EP.stop_reason} if EP.stopping else {}),
        }
    )
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def status() -> dict:
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": ctrl_steps(),
        "done": E["done"],
        "reason": E["reason"],
        "elapsed_s": round(time.time() - E["t0"], 1),
    }


def end_from_signal() -> None:
    """The collect hook's SIGUSR1: end the episode (the agent's time is over), dump it, exit so the replays can start."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]:
            finish("timeout")
        EP.log({"ev": "exit", "reason": "collect hook: episode dumped"})
        if not os.path.exists(PID_FILE):
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def replay_row(row) -> None:
    """A journaled row during a resume."""
    row = S._row(row)
    S.step(row)
    ROWS.append(row)


EP.begin(
    state=E,
    step=replay_row,
    state_sha=S.state_sha,
    proprio=proprio_row,
    spec=SPEC,
    on_end=end_from_signal,
    start_event={"task": TASK, "rule": S.rule_name, "cameras": CAMS, "instance_ok": bool(S.instance_ok), "start_exact": bool(S.start_exact), "build_s": S.build_s},
)
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} LabUtopia sim ready ({TASK}; startup {EP.n_startups}, resumes {EP.resumes}; scene built in {S.build_s} s)", flush=True)
try:
    L.serve(
        L.Service(
            spec=SPEC,
            lock=LOCK,
            state=E,
            submit=do_submit,
            observe=do_observe,
            kinematics=do_kinematics,
            status=status,
            on_submit_error=lambda exc: finish("error"),
            log=EP.log,
            episode=EP,
            state_sha=S.state_sha,
            proprio=proprio_row,
        ),
        port=int(os.environ.get("RCB_PORT", "8000")),
    )
except Exception:  # noqa: BLE001
    traceback.print_exc()
    raise
