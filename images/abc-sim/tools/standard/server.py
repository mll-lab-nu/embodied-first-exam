"""eai-standard/2.2 sim service for the ABC Sim tasks (docs/protocol/standard_mode.md): the adapter of the shared layer
rcb_limited.py (/srv/rcb_limited.py, from the shared standard files); the simulator is rcb_abc.Session (abc_sim on
MuJoCo 3.6.0, CPU physics, EGL rendering). HTTP surface: GET /spec, GET /status, POST /observe, POST /submit,
POST /kinematics, and POST /reset when the run grants resets (RCB_RESET_BUDGET; the standard tasks' default is 0).
Every call is logged to /data/episode.jsonl.

The episode is the frozen instance's (environment/sim/instance.npz, the privileged twin's). The action is abc_sim's own
14 numbers per control step: the two arms' joint position targets (rad) and gripper openings (0 closed .. 1 open). The
episode ends the moment the task's success has held for 1.02 s (30 control steps; ball tray: the countdown completed
with the ball on the tray and both handles held), at the task's failure (ball tray only), or when the agent's time is
over (the collect hook). Nothing about the scene leaves this process: the proprioception is the robot's own joints,
grippers and tool frames; every camera is fixed in the world or rides on an arm.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal, resetting where
the committed resets did. When the episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect
hook (finalize.sh) makes it exit and writes the verdict.

The verdict is the live episode's (PROTOCOL H.4): `success` in episode.json is the task's rule as Session.step applied
it to the steps this service ran (its 1.02 s hold is part of the rule). Nothing is replayed to grade it. The frozen
initial state is checked when the episode begins: a fresh start whose built scene does not hash to the instance's
recorded sha gives up as an infrastructure failure (`instance_mismatch`) before the agent is served."""

import contextlib
import json
import math
import os
import sys
import threading
import time
import traceback

import numpy as np

sys.path.insert(0, os.environ.get("RCB_SRV", "/srv"))
import rcb_limited as L  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data")
SRV = os.environ.get("RCB_SRV", "/srv")
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(SRV, "instance.npz"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
RESET_BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET") or 0))
W, H = 640, 480
# Images one call may return (cameras x frames, per-frame depth counted again), checked before anything runs: every
# frame is held until the response is sent (0.9 MB per 640 x 480 RGB frame; the simulator itself peaks at 2.4 GB).
MAX_FRAMES = 1000
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(),
     "error": None, "resets": 0, "reset_at": []}

os.environ["RCB_SESSION_LOG"] = ""
import rcb_abc as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

M.SESSION_LOG = ""  # the sidecar's Session is not the agent's interaction log
NU = 14
EP = L.Episode(DATA, dim=NU, resume="exact", persist=("resets", "reset_at"))
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Session(instance=INSTANCE)
MD = S.model
DT = S.dt
CTRL_HZ = 1.0 / DT
SUBSTEPS = int(S.env._control_decimation)
ROWS: list = []  # every executed row of the current episode: trajectory.npz
TASK_INFO = json.load(open(os.path.join(SRV, "task.json")))
CAMS = [c for c in M.CAMERAS if c in S.cameras()]
DEFAULT_CAMS = list(TASK_INFO.get("default_cameras") or M.DEFAULT_CAMERAS)
LIM = S.action_limits()
LO, HI = np.array(LIM["low"]), np.array(LIM["high"])
ARM_J = [mujoco.mj_name2id(MD, mujoco.mjtObj.mjOBJ_JOINT, n) for n in M.ARM_JOINTS]
FINGERS = {s: (MD.joint(f"{s}_left_finger").id, MD.joint(f"{s}_right_finger").id) for s in M.SIDES}
ROBOT_JOINTS = set(ARM_J) | {j for pair in FINGERS.values() for j in pair}
GRIP_ACT = {s: MD.actuator(f"{s}_gripper").id for s in M.SIDES}


def own_body(b: int) -> bool:
    """Whether body `b` is fixed in the world or moved by the robot's own joints alone (a camera on anything else would
    give away where that thing is)."""
    while b > 0:
        if int(MD.body_mocapid[b]) >= 0:
            return False
        first = int(MD.body_jntadr[b])
        if any(j not in ROBOT_JOINTS for j in range(first, first + int(MD.body_jntnum[b]))):
            return False
        b = int(MD.body_parentid[b])
    return True


SCENE_CAMS = [c for c in CAMS if not own_body(int(MD.cam_bodyid[MD.camera(c).id]))]
assert not SCENE_CAMS, f"cameras on scene bodies: {SCENE_CAMS}"   # every ABC camera is static or on an arm
GROUPS = [
    ("joint_pos", [f"q_{n}" for n in M.ACTION_LAYOUT],
     "the 14 action coordinates measured: joint angles (rad) and gripper openings (0 closed .. 1 open), action order"),
    ("joint_vel", [f"qd_{n}" for n in M.ACTION_LAYOUT], "their velocities (rad/s; gripper opening per second)"),
    ("gripper_opening", ["left_gripper_opening_m", "right_gripper_opening_m"],
     "metres the two fingers of each gripper have travelled apart from closed (0 .. 0.095)"),
    ("tcp_pose", [f"{s}_tcp_{k}" for s in M.SIDES for k in ("x", "y", "z", "qw", "qx", "qy", "qz")],
     "each arm's tool centre point (kinematics frames left_tcp / right_tcp) in the world frame: position (m), wxyz"),
    ("joint_effort", [f"effort_{n}" for n in M.ACTION_LAYOUT],
     "each servo's force: joint torques (N m) and gripper force (N), as the simulator applies them"),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)


# ------------------------------------------------------------------------------------------------- cameras
def _intrinsic(cam: str) -> list:
    return S.camera_info(cam, (H, W))["intrinsic_cv"]


def camera_info(cam: str) -> dict:
    """World -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
    return S.camera_info(cam, (H, W))


GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])


def _mount(cam: str) -> dict:
    i = MD.camera(cam).id
    b = int(MD.cam_bodyid[i])
    info = camera_info(cam)
    fixed = all(int(MD.body_jntnum[x]) == 0 for x in _chain(b))
    if fixed:
        return {"type": "static", "extrinsic_cv": info["extrinsic_cv"], "cam2world_gl": info["cam2world_gl"]}
    Tb = np.eye(4)
    Tb[:3, :3] = S.data.xmat[b].reshape(3, 3)
    Tb[:3, 3] = S.data.xpos[b]
    link_T_cam_cv = np.linalg.inv(Tb) @ np.asarray(info["cam2world_gl"]) @ GL2CV
    return {"type": "link", "parent_link": MD.body(b).name, "link_T_cam_cv": link_T_cam_cv.tolist()}


def _chain(b: int) -> list:
    out = []
    while b > 0:
        out.append(b)
        b = int(MD.body_parentid[b])
    return out


MOUNTS = {c: _mount(c) for c in CAMS}
MOUNTED = {c: "static" if m["type"] == "static" else f"on the arm link {m['parent_link']}: it moves with it"
           for c, m in MOUNTS.items()}
KIN = M.Kinematics(MD, S.data)
KIN_LINKS = [*M.Kinematics.FRAMES, *KIN.links]


# ------------------------------------------------------------------------------------------------- kinematics
def do_kinematics(req: dict) -> dict:
    """The robot's kinematic model (stateless): fk of the tool frames and arm links for 14 action coordinates q; ik of
    tool-frame poses, each frame with its own arm's six joints (damped least squares, several starts, within the joint
    ranges); no collision check."""
    if req["op"] == "fk":
        r = KIN.answer({"op": "fk", "q": req["q"], "links": req["links"]}, S.robot_q())
        return L.fk_response(r["poses"], "world")
    r = KIN.answer({"op": "ik", "targets": req["targets"], "seed": req["seed"], "tol_pos_m": req["tol_pos_m"],
                    "tol_rot_rad": req["tol_rot_rad"], "max_iters": req["max_iters"]}, S.robot_q())
    errors = {k: (v["pos_m"], v["rot_rad"]) for k, v in r["error"].items()}
    return L.ik_response(r["q"], r["ok"], errors, "world", note=r["note"])


# ------------------------------------------------------------------------------------------------- spec
TASK_TEXT = TASK_INFO["task_text"]
ONE = "one episode, no reset" if not RESET_BUDGET else (
    f"an episode (with up to {RESET_BUDGET} resets: POST /reset starts a new one; only the last is graded)")
EPISODE = (f"{ONE}: it ends in success the moment the task's goal has held for {M.HOLD_STEPS} control steps in a row "
           f"({round(M.HOLD_STEPS * DT, 2)} s), or when your time is over" if S.rule != "tray" else
           f"{ONE}: it ends in success when the tray's countdown completes with the ball on the tray and both handles "
           "held throughout, in failure the moment the ball leaves the tray or a handle is let go during the "
           "countdown, or when your time is over")
JOINT_TEXT = ("one row per control step, 14 numbers in `layout` order: each arm's six joint position targets (rad) and its "
              "gripper opening (0 = closed, 1 = open: each finger 0.0475 m from closed; up to 1.042). Rows are `dt` apart "
              f"(a whole multiple of the {DT:g} s control period, at most 0.5 s), `linear` (default: from the previous "
              "target) or `hold` between rows. The simulator rounds each command to float32; a value outside `limits` "
              "is clamped to it by the servo (reported in meta.clipped; the row is executed as sent)")
ACTION = {"dim": NU, "layout": list(M.ACTION_LAYOUT), "limits": {"low": LO.tolist(), "high": HI.tolist()},
          "units": "rad (joints), opening in [0, 1.042] (grippers)", "semantics": JOINT_TEXT}


def _joint(n: str, k: int) -> dict:
    if n.endswith("_gripper"):
        s = n.split("_")[0]
        a = GRIP_ACT[s]
        return {"name": n, "type": "prismatic", "unit": "m",
                "position_limits": [float(MD.actuator_ctrlrange[a, 0]), float(MD.actuator_ctrlrange[a, 1])],
                "velocity_limit": None, "effort_limit": None, "group": f"{s}_gripper",
                "note": f"the finger travel of {s}_left_finger (its twin {s}_right_finger mirrors it); the action entry "
                        f"and q_{n} give it as a fraction of {M.GRIPPER_M} m (0 closed, 1 open)"}
    j = MD.joint(n).id
    a = MD.actuator(n).id
    return {"name": n, "type": "revolute", "unit": "rad", "position_limits": MD.jnt_range[j].tolist(),
            "velocity_limit": None, "effort_limit": float(MD.actuator_forcerange[a, 1]), "group": f"{n.split('_')[0]}_arm"}


def _gains() -> dict:
    out = {}
    for n in M.ACTION_LAYOUT:
        a = MD.actuator(n).id
        out[n] = {"stiffness": float(MD.actuator_gainprm[a, 0]), "damping": float(-MD.actuator_biasprm[a, 2])}
    return out


BASES = {s: [*S.data.xpos[MD.body(f"{s}_arm").id].tolist(), *S.data.xquat[MD.body(f"{s}_arm").id].tolist()]
         for s in M.SIDES}
BASE_MID = [*((np.array(BASES["left"][:3]) + np.array(BASES["right"][:3])) / 2).tolist(), *BASES["left"][3:]]


def _link_T_site(site: str) -> list:
    """The site's constant pose in its body's frame (4 x 4)."""
    i = MD.site(site).id
    T = np.eye(4)
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, MD.site_quat[i])
    T[:3, :3] = R.reshape(3, 3)
    T[:3, 3] = MD.site_pos[i]
    return T.tolist()
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "ABC Sim (abc_sim) on MuJoCo 3.6.0 (CPU physics; cameras rendered over EGL)",
    "robot": "two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) at a table",
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "max_frames_per_call": MAX_FRAMES,
    "cameras": {c: {"rgb": True, "depth": True, "resolution": [W, H], "intrinsic_cv": _intrinsic(c),
                    "depth_range_m": [float(MD.vis.map.znear * MD.stat.extent), float(MD.vis.map.zfar * MD.stat.extent)],
                    "mounted": MOUNTED[c], "mount": MOUNTS[c]} for c in CAMS},
    "default_cameras": DEFAULT_CAMS,
    "action_types": {"joint_position": ACTION, "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {"arms": list(M.SIDES), "control_period_s": DT},
    "world": {
        "frame": "the table's world frame: x forward (away from the arms' bases), y to the left as the arms face, z up "
        "(no positions of the scene are given)",
        "up": "+z",
        "units": {"length": "m", "angle": "rad", "time": "s"},
        "quaternion_order": "wxyz",
        "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: "
        "OpenGL axes",
    },
    "budget": {"reset": RESET_BUDGET, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": EPISODE,
    "robot_spec": {
        "name": "I2RT YAM, bimanual",
        "description": "two 6-joint I2RT YAM arms side by side, each with a parallel two-finger gripper and a wrist "
        "camera; the left arm is the one at +y",
        "base": {"type": "fixed", "pose": BASE_MID, "link": "the midpoint between the two arms' base links",
                 "arm_bases": {f"{s}_arm": BASES[s] for s in M.SIDES},
                 "note": "both arms' bases are fixed in the world (x y z + wxyz quaternion); `pose` is the midpoint "
                 "between them, `arm_bases` each arm's own"},
        "joints": [_joint(n, k) for k, n in enumerate(M.ACTION_LAYOUT)],
        "grippers": {s: {"joints": [f"{s}_left_finger", f"{s}_right_finger"], "opening_m": [0.0, 2 * M.GRIPPER_M],
                         "command": "the action's <side>_gripper entry: 0 = closed, 1 = open (each finger 0.0475 m "
                         "from closed), up to 1.042; a position servo on the finger travel",
                         "tcp_frame": f"{s}_tcp"} for s in M.SIDES},
        "controller": {"type": "joint position servos (MuJoCo position actuators with velocity damping) on the 12 arm "
                       "joints and the 2 grippers", "control_hz": CTRL_HZ, "physics_hz": CTRL_HZ * SUBSTEPS,
                       "gains": _gains(),
                       "note": "the targets are held for the whole control step; force limits in joints[].effort_limit"},
        "tcp": {f"{s}_tcp": {"parent_link": f"{s}_link_6", "link_T_frame": _link_T_site(f"{s}_tcp_site"),
                             "definition": f"the arm's tool centre point (abc_sim's {s}_tcp_site)"} for s in M.SIDES}
        | {f"{s}_grasp": {"parent_link": f"{s}_link_6", "link_T_frame": _link_T_site(f"{s}_grasp_site"),
                          "definition": f"the point between the finger pads ({s}_grasp_site)"} for s in M.SIDES},
    },
    "kinematics": {
        "endpoint": "/kinematics",
        "joint_names": GROUPS[0][1],
        "frame": "world",
        "quaternion_order": "wxyz",
        "links": KIN_LINKS,
        "tcp_frames": ["left_tcp", "right_tcp"],
        "ee_frames": list(M.Kinematics.FRAMES),
        "ik_targets": list(M.Kinematics.FRAMES),
        "ik": {"tol_pos_m": 0.002, "tol_rot_rad": 0.02, "max_iters": 300},
        "note": "tool frames and arm links for 14 action coordinates q (joint_pos order), world frame; ik: each target "
        "frame with its own arm's six joints, position and orientation; no collision check",
    },
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0,
              "max_m": L.DEPTH_MAX_M, "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
if RESET_BUDGET:
    SPEC["reset"] = (
        f"POST /reset (JSON or RCB1 {{cameras, video_fps, depth}}; no physics) abandons the running episode, or follows "
        f"one that has ended, and starts a new one from the same frozen starting state, {RESET_BUDGET} times in all; it "
        "returns the new episode's first frames and proprioception. Only the last episode is graded: an episode you "
        "reset away is never graded, a success ends the trial (409 after it), and when your time is up the episode then "
        "running is the one graded. The wall clock never restarts. /status and every meta add `episode`, `resets_left` "
        "and `control_steps_total` (all episodes); `control_steps` counts the current episode's."
    )
L.check_spec(SPEC)  # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()


def ctrl_steps() -> int:
    return int(S.steps)


def proprio_row() -> np.ndarray:
    d = S.data
    eff = np.array([float(d.qfrc_actuator[MD.jnt_dofadr[MD.joint(n).id]]) if not n.endswith("_gripper")
                    else float(d.actuator_force[GRIP_ACT[n.split("_")[0]]]) for n in M.ACTION_LAYOUT])
    opening = [float(d.qpos[MD.jnt_qposadr[FINGERS[s][0]]] - d.qpos[MD.jnt_qposadr[FINGERS[s][1]]]) for s in M.SIDES]
    tcp = [x for s in M.SIDES for x in S.site_pose(f"{s}_tcp_site")]
    return np.concatenate([S.robot_q(), S.robot_qd(), opening, tcp, eff]).astype(np.float32)


def grab(cams, want_depth: bool):
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c, (H, W))
        if want_depth:
            dep[c] = S.render_depth(c, (H, W))
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: np.asarray(camera_info(c)["extrinsic_cv"], dtype=np.float64) for c in cams}


def write_final() -> None:
    if L.final_verdict(DATA):  # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {**summary(), "finalized": False, "live_sha": E.get("live_sha")})


def summary() -> dict:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    return {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n,
            "physics_steps": n * SUBSTEPS, "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
            "reason": E["reason"], "done": E["done"], "task": S.family, "protocol": L.PROTOCOL, "n_actions": len(ROWS),
            "episodes": E["resets"] + 1, "resets": E["resets"], "reset_budget": RESET_BUDGET,
            "control_steps_total": EP.rows, **EP.final_fields()}


def finish(reason: str) -> None:
    """The episode is over: the task's verdict on the steps executed, then the record for the collect hook."""
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    E["episode_control_steps"] = ctrl_steps()
    E["success"] = bool(S.success) and reason != "error"
    EP.log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"]),
            "episode": E["resets"] + 1, "journal_rows": EP.rows})
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    S.save_trajectory(np.asarray(ROWS, dtype=np.float64).reshape(-1, NU), os.path.join(DATA, "trajectory.npz"),
                      meta={"source": "standard-mode episode", "reason": E["reason"]})
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


@contextlib.contextmanager
def checking():
    """Checking a request, before anything runs: a field of the wrong type is a 400 with nothing changed, never a
    simulator error that ends the episode."""
    try:
        yield
    except ValueError:
        raise
    except (TypeError, AttributeError, KeyError, IndexError, OverflowError) as exc:
        raise ValueError(f"malformed request: {exc!r}"[:300]) from None


def number(meta: dict, key: str, default: float) -> float:
    v = meta.get(key)
    if v is None:
        return float(default)
    try:
        if isinstance(v, bool):
            raise TypeError
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be a number of seconds, got {v!r}"[:200]) from None
    if not math.isfinite(x):
        raise ValueError(f"{key} must be finite")
    return x


def note_of(meta: dict) -> str:
    note = meta.get("note")
    return "" if note is None else str(note)[:500]


def frame_every(fps: int, video: str) -> int:
    return max(1, int(round(CTRL_HZ / max(1, fps)))) if video != "none" else 10**9  # no video: first and last frame


def recorder(cams, fps: int, meta: dict, video: str, steps: int = 0) -> L.Recorder:
    every = frame_every(fps, video)
    L.check_frames(len(cams), 2 + steps // every, L.depth_mode(meta) in ("frames", "legacy"), MAX_FRAMES)
    return L.Recorder(cams, every, grab, proprio_row, extrinsics, ctrl_steps, depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 10
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= CTRL_HZ):
        raise ValueError(f"video_fps must be in [1, {CTRL_HZ:g}]")
    return int(fps)


def cameras_of(meta: dict) -> list:
    cams = meta.get("cameras") or DEFAULT_CAMS
    if not isinstance(cams, (list, tuple)) or not all(isinstance(c, str) for c in cams):
        raise ValueError(f"cameras must be a list of camera names; cameras: {CAMS}")
    bad = [c for c in cams if c not in CAMS]
    if bad:
        raise ValueError(f"unknown cameras {bad}; cameras: {CAMS}")
    return list(dict.fromkeys(cams))


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
            "sim_time_s": round(n * DT, 4), "time_s": round(L.agent_time(E), 2),
            "time_left_s": max(0.0, round(WALL_CLOCK_S - L.agent_time(E), 1)),
            "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()}, "done": E["done"],
            "reason": E["reason"], "cameras": {c: camera_info(c) for c in cams}, **reset_counters()}


def last_command() -> np.ndarray:
    return ROWS[-1].copy() if ROWS else S.hold_action()


def clipped_entries(A: np.ndarray):
    """The entries the servos clamp: abc_sim rounds every command to float32 and MuJoCo clamps it to the actuator's
    range. The row itself is executed as sent (clipping it here would change the physics in the last bits: the clamped
    float32 command is not the float32 of the limit), so this only reports what the simulator does."""
    A32 = A.astype(np.float32).astype(np.float64)
    bad = np.argwhere((A32 < LO) | (A32 > HI))
    clipped = [{"row": int(r), "index": int(i), "reason": f"{M.ACTION_LAYOUT[i]} clamped to "
                f"[{LO[i]:.4f}, {HI[i]:.4f}] by the servo"} for r, i in bad[:200]]
    return clipped, int(len(bad))


def do_submit(meta: dict, A: np.ndarray):
    with checking():  # every field, before a single control step runs
        typ = meta.get("type")
        if typ != "joint_position":
            raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
        dt = number(meta, "dt", DT)
        interp = meta.get("interpolate", "linear")
        video = meta.get("video", "mp4")
        cams, fps, note = cameras_of(meta), video_fps(meta), note_of(meta)
        k = dt / DT
        if A.ndim != 2 or A.shape[1] != NU:
            raise ValueError(f"joint_position actions must be (T, {NU}), got {list(A.shape)}")
        if A.shape[0] < 1:
            raise ValueError("a chunk needs at least one row")
        if not np.all(np.isfinite(A)):
            raise ValueError("actions contain NaN/inf")
        if not (dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
            raise ValueError(f"dt must be a whole multiple of the {DT:g} s control period and at most 0.5 s; got {dt}")
        if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
            raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
        if not isinstance(interp, str) or interp not in ("hold", "linear"):
            raise ValueError("interpolate must be hold|linear")
        if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
            raise ValueError("video must be mp4|frames|both|none")
        rec = recorder(cams, fps, meta, video, steps=A.shape[0] * int(round(k)))
    A = np.asarray(A, dtype=np.float64)
    clipped, n_clipped = clipped_entries(A)
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    prev = last_command()
    n = int(round(k))
    for row in A:
        E["step"] += 1
        target = np.asarray(row, dtype=np.float64)
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
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0,
           "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
           "clipped": clipped, "n_clipped": n_clipped, "plan": [], "ok": True}
    EP.log({"ev": "submit", "call": E["calls"], "rows": E["step"] - step0, "dt": dt, "interpolate": interp,
            "cameras": cams, "control_steps": ctrl_steps() - before, "n_clipped": n_clipped, "note": note,
            **({"stopped": EP.stop_reason} if EP.stopping else {})})
    return out, rec.parts(video, fps)


def do_observe(meta: dict):
    with checking():  # every field, before a single control step runs
        cams, fps = cameras_of(meta), video_fps(meta)
        seconds = number(meta, "seconds", 0.0)
        video = meta.get("video", "frames")
        if seconds < 0 or seconds > MAX_WATCH_S:
            raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
        if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
            raise ValueError("video must be mp4|frames|both|none")
        rec, before = recorder(cams, fps, meta, video, steps=int(round(seconds / DT))), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = last_command()
        for _ in range(int(round(seconds / DT))):
            if ctrl_step(hold, rec):
                break
    rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    EP.log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams,
            "control_steps": ctrl_steps() - before, **({"stopped": EP.stop_reason} if EP.stopping else {})})
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def reset_counters() -> dict:
    if not RESET_BUDGET:
        return {}
    left = 0 if (E["success"] or E.get("exiting")) else RESET_BUDGET - E["resets"]
    return {"episode": E["resets"] + 1, "resets_left": left, "control_steps_total": EP.rows}


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"],
            "reason": E["reason"], "elapsed_s": round(time.time() - E["t0"], 1), **reset_counters()}


class Refused(Exception):
    """A /reset the service turns down (409): nothing changes."""

    def __init__(self, body: dict):
        super().__init__(body.get("error"))
        self.body = body


def do_reset(meta: dict):
    """POST /reset: a new episode from the frozen instance (the running one, if any, is abandoned, never graded)."""
    with checking():
        cams, fps = cameras_of(meta), video_fps(meta)
        L.check_frames(len(cams), 2, L.depth_mode(meta) in ("frames", "legacy"), MAX_FRAMES)
    if E["success"]:
        raise Refused({"error": "trial finished: an episode succeeded", "reason": E["reason"], "resets_left": 0})
    if E["resets"] >= RESET_BUDGET:
        raise Refused({"error": "reset budget exhausted", "reason": "reset budget exhausted", "budget": RESET_BUDGET,
                       "resets_left": 0})
    abandoned = {"episode": E["resets"] + 1, "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"]}
    S.reset()
    ROWS.clear()
    E["resets"] += 1
    E["reset_at"] = list(E["reset_at"]) + [EP.rows]
    E.update(done=False, reason=None, success=False, t_end=None, episode_control_steps=None, dumped=False)
    EP._ck = None  # the state changed without a journal row: the checkpoint after this call must hash it anew
    E["calls"] += 1
    EP.log({"ev": "reset", "call": E["calls"], "episode": E["resets"] + 1, "journal_rows": EP.rows,
            "abandoned": abandoned, "state_sha": S.state_sha()})
    rec = recorder(cams, fps, meta, "frames")
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "reset_id": E["resets"], "ok": True}
    return out, rec.parts("frames", fps)


def end_from_signal() -> None:
    """The collect hook's SIGUSR1: end the episode (the agent's time is over), dump it, exit so the hook can grade it."""
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


_CPS = [e for e in EP.events() if e.get("ev") == "checkpoint"]
RESUME = {"at": list((_CPS[-1].get("persist") or {}).get("reset_at") or []) if _CPS else [], "i": 0}


def _resume_resets() -> None:
    while RESUME["at"] and int(RESUME["at"][0]) <= RESUME["i"]:
        RESUME["at"].pop(0)
        S.reset()
        ROWS.clear()


def replay_row(row) -> None:
    """A journaled row during a resume."""
    _resume_resets()
    S.step(row)
    ROWS.append(np.asarray(row, dtype=np.float64))
    RESUME["i"] += 1


def resume_sha() -> str:
    _resume_resets()
    return S.state_sha()


# The frozen initial state, checked at the episode's start: a fresh start whose scene does not hash to the instance's
# recorded sha is no trial of this task (an infrastructure failure, before the agent is served).
if not any(e.get("ev") == "start" for e in EP.events()) and S.state_sha() != S.instance_sha:
    if not L.final_verdict(DATA):
        _fin = os.path.join(DATA, "final.json")
        L._write_json(_fin, {**L._read_json(_fin), "instance_mismatch": 1, "start_sha": S.state_sha(),
                             "instance_sha": S.instance_sha})
    EP.give_up(f"instance_mismatch: the scene started at {S.state_sha()}, the frozen instance records {S.instance_sha}",
               infra=True)
RESUMED = EP.begin(state=E, step=replay_row, state_sha=resume_sha, proprio=proprio_row, spec=SPEC,
                   on_end=end_from_signal,
                   start_event={"task": S.family, "cameras": CAMS, "instance_sha": S.instance_sha, "gl": M.GL})
if RESUMED and E["resets"]:
    _ends = [e for e in EP.events() if e.get("ev") == "end" and int(e.get("episode") or 1) == E["resets"] + 1
             and int(e.get("journal_rows") or 0) <= EP.rows]
    if _ends:
        E.update(done=True, reason=_ends[-1].get("reason"), t_end=float(_ends[-1]["ts"]),
                 episode_control_steps=int(_ends[-1].get("control_steps") or ctrl_steps()))
    else:
        E.update(done=False, reason=None, t_end=None, episode_control_steps=None)
if E["done"]:
    dump()
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} ABC Sim service ready ({S.family}; gl {M.GL}; startup {EP.n_startups}, resumes {EP.resumes})",
      flush=True)


def make_handler(svc: L.Service):
    """The shared 2.2 handler, plus POST /reset when the run grants resets (the shared layer has no reset)."""
    base = L.make_handler(svc)

    class Hdl(base):
        def do_POST(self):
            if self.path != "/reset" or not RESET_BUDGET:
                return super().do_POST()
            try:
                meta, _ = self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json(413 if "too large" in str(exc) else 400, {"error": str(exc)[:200]})
            with LOCK:
                if E.get("exiting"):
                    return self._json(409, {"error": "trial finished: your time is up", "reason": E.get("reason"),
                                            "resets_left": 0})
                cid = EP.call_begin(self.path, self.connection)
                out = blobs = err = None
                try:
                    out, blobs = do_reset(meta)
                except Refused as exc:
                    err = (409, exc.body)
                except ValueError as exc:
                    err = (400, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc()
                    E["error"] = repr(exc)
                    EP.log({"ev": "error", "path": self.path, "error": repr(exc)})
                    try:
                        finish("error")
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
                    err = (500, {"error": "simulator error", "detail": repr(exc)[:200]})
                finally:
                    if out is not None or (err and err[0] == 500):
                        try:
                            EP.checkpoint(E, S.state_sha, proprio_row)
                        except Exception:  # noqa: BLE001
                            traceback.print_exc()
                    EP.call_end(cid, self.path)
            if err is not None:
                return self._json(*err)
            return self._rcb1({**out, "stopped": None}, blobs)

    return Hdl


def serve(svc: L.Service, port: int) -> None:
    svc.spec.setdefault("on_service_error", L.ON_SERVICE_ERROR)
    svc.spec.setdefault("max_call_wall_s", EP.max_call_wall_s)
    L.check_spec(svc.spec)
    L.bind(port, make_handler(svc)).serve_forever()


try:
    serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics,
                    status=status, on_submit_error=lambda exc: finish("error"), log=EP.log, episode=EP,
                    state_sha=S.state_sha, proprio=proprio_row), port=int(os.environ.get("RCB_PORT", "8000")))
except Exception:  # noqa: BLE001
    traceback.print_exc()
    raise
