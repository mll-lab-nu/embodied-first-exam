"""eai-standard/2.2 sim service for the AutoBio tasks (docs/STANDARD_MODE.md): the adapter of the shared layer
rcb_limited.py; the simulator is rcb_autobio.Session (AutoBio on MuJoCo 3.3.0, CPU). HTTP surface: GET /spec,
GET /status, POST /observe, POST /submit, POST /kinematics. Every call is logged to /data/episode.jsonl.

The episode is the frozen instance's (environment/sim/instance.json, the privileged twin's). The action is AutoBio's
own: one position target per controlled actuator (arm joints, gripper or pipette thumb), one row per 2 ms control
step. Rule `first`: the episode ends the moment AutoBio's check holds (success). Rule `final` (the thermal mixer):
the episode is judged where it ends, at the agent's `done` or when its time is over. Nothing about the objects or the
instruments leaves this process: the proprioception is the robot's own joints, grippers, tool frames and commands.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal. When the
episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect hook (finalize.sh) makes it exit
and replays the trajectory in two fresh processes."""

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
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
MAX_FPS = 50  # AutoBio's own policy rate; a call returns at most MAX_FRAMES frames per camera
MAX_FRAMES = 3000
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
import rcb_autobio as M  # noqa: E402

M.SESSION_LOG = ""  # the sidecar's Session is not the agent's interaction log
W, H = M.W, M.H
_INST = json.load(open(INSTANCE))
TASK = _INST["family"]
NA = int(_INST["n_action"])  # the journal's row width, known before the scene is built
EP = L.Episode(DATA, dim=NA, resume="exact")
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Session(instance=INSTANCE)
assert S.n_act == NA, (S.n_act, NA)
DT = S.dt
CTRL_HZ = 1.0 / DT
SUBSTEPS = 1
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
TASK_INFO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "task.json")))
CAMS = S.cameras()
DEFAULT_CAMS = [c for c in TASK_INFO.get("default_cameras") or S.default_cameras() if c in CAMS]
ACTS = S.actuators()
LAYOUT = [a["name"] for a in ACTS]
LIMITS = np.array([a["range"] for a in ACTS], dtype=np.float64)
JOINTS = S.robot_joints()
J_NAMES = [j["name"] for j in JOINTS]
J_Q = np.array([j["qpos_adr"] for j in JOINTS])
J_V = np.array([j["dof_adr"] for j in JOINTS])
TCPS = S.tcp_frames()
GRIPPERS = list(S.gripper_openings())
GROUPS = [
    ("joint_pos", [f"q_{n}" for n in J_NAMES], "joint positions of the robot: the arm joints, then the gripper's or the hand's, per arm (rad; m for sliding joints)"),
    ("joint_vel", [f"qd_{n}" for n in J_NAMES], "joint velocities (rad/s; m/s)"),
    ("gripper_opening", [f"{g}_opening" for g in GRIPPERS], "metres between the fingertips, per parallel gripper"),
    ("tcp_pose", [f"{t}_{c}" for t in TCPS for c in ("x", "y", "z", "qw", "qx", "qy", "qz")],
     "each tool frame in the world frame: position (m) and wxyz quaternion"),
    ("joint_effort", [f"effort_{n}" for n in J_NAMES], "force of the drives on each joint (N m; N)"),
    ("command", [f"cmd_{n}" for n in LAYOUT], "the position targets in effect, in action order (the last row executed)"),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)
KIN_JOINTS = [f"q_{n}" for n in S.kinematic_joints()]
LINKS = TCPS + [n for n in S._links() if n not in TCPS]
MOUNT = {c: S.camera_mount(c) for c in CAMS}
MOUNTED = {c: ("static" if MOUNT[c]["type"] == "static" else f"fixed to the link {MOUNT[c]['parent_link']}: it moves with the arm") for c in CAMS}


def do_kinematics(req: dict) -> dict:
    """Tool frames and camera-mount links for arm joint positions (world frame). Never touches the simulation."""
    if req["op"] == "fk":
        return L.fk_response(S.fk(req["q"], req["links"]), "world")
    r = S.ik(req["targets"], seed=req["seed"], tol_pos_m=req["tol_pos_m"], tol_rot_rad=req["tol_rot_rad"], max_iters=req["max_iters"])
    return L.ik_response(r["q"], r["ok"], r["error"], "world",
                         note="damped least squares on each arm's 6 joints within their ranges; no collision check")


# ------------------------------------------------------------------------------------------------- spec
TASK_TEXT = TASK_INFO["task_text"]
CAP = f"{M.MAX_STEPS} control steps ({M.MAX_STEPS * M.CONTROL_DT:g} s of simulated time)"
WARNING_END = (
    "; a MuJoCo physics warning (an unstable simulation, e.g. after the robot was driven hard into something) ends it at "
    'once as a failure (reason "failure: simulator warning (unstable state)"), and so does a simulator error (reason "error")'
)
EPISODE = {
    "first": f"one episode, no reset: it ends the moment the goal is reached (success), when your time is over, or after {CAP}",
    "final": 'one episode, no reset: it is judged in the state in which it ends, when you end it with r.submit("done", []), '
    f"when your time is over, or after {CAP}",
}[S.rule] + WARNING_END
ROBOT_SPEC = S.robot_spec()
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "AutoBio on MuJoCo 3.3.0 (CPU)",
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
            "mounted": MOUNTED[c],
            "mount": MOUNT[c],
        }
        for c in CAMS
    },
    "default_cameras": DEFAULT_CAMS,
    "action_types": {
        "joint_position": {
            "dim": NA,
            "layout": LAYOUT,
            "limits": {a["name"]: a["range"] for a in ACTS},
            "units": {a["name"]: a["unit"] for a in ACTS},
            "semantics": "absolute position targets of the robot's PD drives, every entry in `layout` order, one row "
            "per control step. Rows are `dt` apart (a whole multiple of the 0.002 s control period, at most 0.5 s), "
            "`linear` (default: from the previous target) or `hold` between rows; values outside the limits are clipped "
            "and reported. A call returns at most 3000 frames per camera (video_fps up to 50)",
        },
        "done": {
            "dim": 0,
            "layout": [],
            "semantics": 'ends the episode now, in the current state (no physics); r.submit("done", [])',
        },
        "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": TASK_INFO.get("static", {}),
    "world": {
        "frame": "AutoBio's world frame: z up, the floor at z = 0; the arms' bases are in robot_spec.base (no positions of the scene are given)",
        "up": "+z",
        "units": {"length": "m", "angle": "rad", "time": "s"},
        "quaternion_order": "wxyz",
        "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes",
    },
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": EPISODE,
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
        "note": "tool frames (robot_spec.tcp) and the links the wrist cameras sit on, for arm joint positions q (6 per "
        "arm, `joint_names` order; every other joint as at the start); ik: one pose per tool frame, an arm without a "
        "target keeps its seed; tol_rot_rad >= 3.1 ignores orientation",
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
    d = S.data
    tcp = S.tcp_poses()
    grip = S.gripper_openings()
    return np.concatenate([
        d.qpos[J_Q], d.qvel[J_V], [grip[g] for g in GRIPPERS], np.concatenate([tcp[t] for t in TCPS]),
        d.qfrc_actuator[J_V], S.command(),
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
        "score": float(E.get("score") if E.get("score") is not None else S.score),
        "steps": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
        "reason": E["reason"],
        "done": E["done"],
        "task": TASK,
        "rule": S.rule,
        "protocol": L.PROTOCOL,
        "n_actions": len(ROWS),
        "instance_ok_live": bool(S.instance_ok),
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
    E["score"] = float(S.score)
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
    running = S.step(a)
    ROWS.append(np.asarray(a, dtype=np.float64))
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
        "time_s": round(L.agent_time(E), 2),
        "time_left_s": max(0.0, round(WALL_CLOCK_S - L.agent_time(E), 1)),
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()},
        "done": E["done"],
        "reason": E["reason"],
        "cameras": {c: S.camera_info(c) for c in cams},
    }


@checked
def parse_submit(meta: dict, A: np.ndarray):
    """Every field of a /submit request and its rows, checked; nothing is executed here."""
    typ = meta.get("type")
    if not isinstance(typ, str) or typ not in ("joint_position", "done"):
        raise ValueError(f"type must be joint_position or done (not yet: {SPEC['action_types']['not_yet']})")
    cams, note = cameras_of(meta), note_of(meta)
    L.depth_mode(meta)  # a bad `depth` is a 400 here, not after the rows
    if typ == "done":
        return typ, DT, "hold", "none", cams, 10, note
    dt = number(meta, "dt", DT)
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    fps = video_fps(meta)
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != NA:
        raise ValueError(f"joint_position actions must be (T, {NA}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (math.isfinite(dt) and dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
        raise ValueError(f"dt must be a whole multiple of the {DT:g} s control period and at most 0.5 s; got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if not isinstance(interp, str) or interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    frames_ok(A.shape[0] * dt, fps, video)
    return typ, dt, interp, video, cams, fps, note


def do_submit(meta: dict, A: np.ndarray):
    typ, dt, interp, video, cams, fps, note = parse_submit(meta, A)
    if typ == "done":
        rec = recorder(cams, 10, meta, "none")
        rec.tick(force=True, last=True)  # every response carries the last frames
        E["calls"] += 1
        finish("done")
        EP.log({"ev": "submit", "call": E["calls"], "type": "done", "note": note})
        return {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": 0, "ok": True}, rec.parts("none", 10)
    k = dt / DT
    rec, clipped = recorder(cams, fps, meta, video), []
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    prev = S.command()
    n = int(round(k))
    for ri, row in enumerate(A):
        E["step"] += 1
        row = np.asarray(row, dtype=np.float64)
        target = np.clip(row, LIMITS[:, 0], LIMITS[:, 1])
        for j in np.flatnonzero(target != row)[:20]:
            clipped.append({"row": ri, "index": int(j), "reason": f"{LAYOUT[j]} limit [{LIMITS[j, 0]:g}, {LIMITS[j, 1]:g}]"})
        stop = False
        for s in range(1, n + 1):
            a = target if (interp == "hold" or s == n) else prev + (target - prev) * (s / n)
            if ctrl_step(a, rec):
                stop = True
                break
        prev = target
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
    S.step(row)
    ROWS.append(np.asarray(row, dtype=np.float64))


EP.begin(
    state=E,
    step=replay_row,
    state_sha=S.state_sha,
    proprio=proprio_row,
    spec=SPEC,
    on_end=end_from_signal,
    start_event={"task": TASK, "rule": S.rule, "cameras": CAMS, "instance_ok": bool(S.instance_ok)},
)
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} AutoBio sim ready ({TASK}; startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
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
