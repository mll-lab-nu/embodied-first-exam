"""eai-standard/2.2 sim service for the MyoSuite tasks (docs/STANDARD_MODE_2_2.md): the adapter of the shared layer
rcb_limited.py; the simulator is rcb_myosuite.Session (MyoSuite 2.12.2 on MuJoCo, CPU). HTTP surface: GET /spec,
GET /status, POST /observe, POST /submit, POST /kinematics, and POST /reset when the run grants resets (RCB_RESET_BUDGET,
the optional reset capability of docs/LIMITED_MODE_PROTOCOL.md; MyoSuite's standard tasks default to 10 in their compose
file, PROTOCOL §4.5). Every call is logged to /data/episode.jsonl.

The episode is the frozen instance's (environment/sim/instance.npz, the privileged twin's). The action is MyoSuite's own:
one command per muscle (excitation u = 1 / (1 + exp(-5 (a - 0.5)))), one row per control step. The episode ends the
moment the task's goal has held for its hold time (success), at the task's failure (object dropped, fingers off the key,
...), or when the agent's time is over (the collect hook). With a reset budget, POST /reset abandons the running (or
ended) episode and starts a new one from the frozen instance; only the last episode is graded, and a success ends the
trial. Nothing about objects or goals leaves this process: the proprioception is the limb's own joints and muscles.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal, resetting where
the committed resets did (their journal rows are checkpointed, `persist`). When the episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect hook (finalize.sh) makes it exit
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
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.npz"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
RESET_BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET") or 0))  # the compose file's default: 10 (PROTOCOL §4.5)
W, H = 640, 480
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
    "resets": 0,  # resets done (the episode is resets + 1)
    "reset_at": [],  # the journal row at which each reset happened: a resume resets there again
}

os.environ["RCB_SESSION_LOG"] = ""
import rcb_myosuite as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

M.SESSION_LOG = ""  # the sidecar's Session is not the agent's interaction log
_INST = np.load(INSTANCE, allow_pickle=False)
TASK = str(_INST["task"])
NU = int(_INST["model__actuator_ctrlrange"].shape[0])  # the journal's row width, known before the scene is built
EP = L.Episode(DATA, dim=NU, resume="exact", persist=("resets", "reset_at"))
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Session(TASK, instance=INSTANCE)
assert S.nu == NU, (S.nu, NU)
MD = S.model
DT = S.dt
CTRL_HZ = 1.0 / DT
SUBSTEPS = int(S.base.frame_skip)
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
BODY = M.BODY[TASK]
ROBOT = {
    "hand": ("MyoHand", "a musculoskeletal model of a human forearm and hand (MyoSuite)"),
    "arm": ("MyoArm", "a musculoskeletal model of a human shoulder, arm and hand (MyoSuite)"),
    "body": ("MyoArm with torso", "a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor (MyoSuite)"),
    "bimanual": ("MyoArm + MPL", "a musculoskeletal right arm and hand (MyoSuite's MyoArm) next to a motorized prosthetic left arm (the Modular Prosthetic Limb)"),
    "legs": ("MyoLegs", "a free-standing musculoskeletal model of a human torso and both legs (MyoSuite)"),
    "osl": ("MyoLeg + OSL", "a free-standing musculoskeletal model of a human with the right leg's muscles and an Open-Source Leg knee-ankle prosthesis on the left (MyoSuite)"),
}[BODY]
TASK_INFO = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "task.json")))
CAMS = list(S.cameras())
DEFAULT_CAMS = list(TASK_INFO["default_cameras"])
ACTS = S.actuators()
ACT_NAMES = [a["name"] for a in ACTS]
MUS_IDX = [a["index"] for a in ACTS if a["kind"] == "muscle"]
MUSCLES = [ACTS[i]["name"] for i in MUS_IDX]
OTHER = [a for a in ACTS if a["kind"] != "muscle"]
ATYPE = "muscle" if not OTHER else "actuators"
ACT_ADR = np.array([int(MD.actuator_actadr[i]) for i in MUS_IDX], dtype=int)
# the body's own joints only: the key's hinge and the OBJ* joints of pen, die and objects are object state, never sent
# (free joints, of the balls, objects and paddles, are left out by S.joints(); a free-standing body's root is reported
# on its own, in root_pose / root_vel)
LIMB = [j for j in S.joints() if j["name"] != "keyjoint" and not j["name"].startswith("OBJ")]
J_NAMES = [j["name"] for j in LIMB]
J_Q = np.array([j["qpos_adr"] for j in LIMB])
J_V = np.array([j["dof_adr"] for j in LIMB])
J_ID = [MD.joint(n).id for n in J_NAMES]
J_SLIDE = [int(MD.jnt_type[j]) == 2 for j in J_ID]
ROOT = MD.joint("root").id if mujoco.mj_name2id(MD, mujoco.mjtObj.mjOBJ_JOINT, "root") >= 0 else None
if ROOT is not None and int(MD.jnt_type[ROOT]) != 0:
    ROOT = None
GROUPS = [
    ("joint_pos", [f"q_{n}" for n in J_NAMES], "joint positions of the body (rad; m for sliding joints)"),
    ("joint_vel", [f"qd_{n}" for n in J_NAMES], "joint velocities (rad/s; m/s)"),
    (
        "muscle_activation",
        [f"act_{n}" for n in MUSCLES],
        "muscle activations in [0, 1] (they follow the excitations with a first-order delay)",
    ),
    ("muscle_length", [f"len_{n}" for n in MUSCLES], "muscle-tendon lengths (m)"),
    ("joint_effort", [f"effort_{n}" for n in J_NAMES], "generalized force of all actuators on each joint (N m; N)"),
    ("gripper_opening", [], "none (a hand, not a gripper)"),
    ("tcp_pose", [], "none (a hand, not a gripper); fingertip poses: /kinematics fk"),
]
if ROOT is not None:
    GROUPS += [
        ("root_pose", ["root_x", "root_y", "root_z", "root_qw", "root_qx", "root_qy", "root_qz"],
         "the pelvis (the free-floating root) in the world frame: position (m) and wxyz quaternion"),
        ("root_vel", ["root_vx", "root_vy", "root_vz", "root_wx", "root_wy", "root_wz"],
         "the root's linear (m/s, world axes) and angular velocity (rad/s, its own axes), as MuJoCo's free joint reports them"),
    ]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)


# ------------------------------------------------------------------------------------------------- cameras
def _intrinsic(cam: str) -> list:
    fovy = math.radians(float(MD.cam_fovy[MD.camera(cam).id]))
    f = 0.5 * H / math.tan(fovy / 2)
    return [[f, 0.0, W / 2], [0.0, f, H / 2], [0.0, 0.0, 1.0]]


def _cam_T_gl(data, cam: str) -> np.ndarray:
    i = MD.camera(cam).id
    T = np.eye(4)
    T[:3, :3] = data.cam_xmat[i].reshape(3, 3)  # MuJoCo cameras: OpenGL axes (x right, y up, z back)
    T[:3, 3] = data.cam_xpos[i]
    return T


GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])


def camera_info(cam: str) -> dict:
    """World -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
    c2w = _cam_T_gl(S.data, cam)
    ext = np.linalg.inv(c2w @ GL2CV)[:3, :]
    return {
        "intrinsic_cv": _intrinsic(cam),
        "extrinsic_cv": ext.tolist(),
        "cam2world_gl": c2w.tolist(),
        "image_size": [W, H],
    }


CAM_MODES = {0: "fixed", 1: "track", 2: "trackcom", 3: "targetbody", 4: "targetbodycom"}


def _mount(cam: str) -> dict:
    i = MD.camera(cam).id
    body = MD.body(int(MD.cam_bodyid[i])).name
    mode = int(MD.cam_mode[i])
    if mode != 0:       # MuJoCo tracking cameras follow a body (or the model's centre of mass) at a fixed offset
        return {"type": "link", "parent_link": body, "tracking": CAM_MODES.get(mode, str(mode)),
                "note": "a MuJoCo tracking camera: it follows its body's position (or the centre of mass of its "
                "subtree) without turning with it; its pose is in every response (extrinsic_cv per frame)"}
    if body == "world":
        info = camera_info(cam)
        return {"type": "static", "extrinsic_cv": info["extrinsic_cv"], "cam2world_gl": info["cam2world_gl"]}
    b = MD.body(body).id
    Tb = np.eye(4)
    Tb[:3, :3] = S.data.xmat[b].reshape(3, 3)
    Tb[:3, 3] = S.data.xpos[b]
    link_T_cam_cv = np.linalg.inv(Tb) @ _cam_T_gl(S.data, cam) @ GL2CV
    return {"type": "link", "parent_link": body, "link_T_cam_cv": link_T_cam_cv.tolist()}


def _mounted(cam: str) -> str:
    m = _mount(cam)
    if m["type"] == "static":
        return "static"
    if "tracking" in m:
        return f"tracking ({m['tracking']}) the body {m['parent_link']}"
    return f"fixed to the body {m['parent_link']}: it moves with it"


MOUNTED = {c: _mounted(c) for c in CAMS}


# ------------------------------------------------------------------------------------------------- kinematics
KD = mujoco.MjData(MD)  # kinematics only: a copy of the start state, never stepped
KD.qpos[:] = S.data.qpos
if ROOT is not None:  # a free-standing body answers in its root's frame (base_pose puts the root somewhere)
    KD.qpos[MD.jnt_qposadr[ROOT]:MD.jnt_qposadr[ROOT] + 7] = [0, 0, 0, 1, 0, 0, 0]
KIN_FRAME = "base" if ROOT is not None else "world"
TIPS = [
    n for n in ("THtip", "IFtip", "MFtip", "RFtip", "LFtip") if mujoco.mj_name2id(MD, mujoco.mjtObj.mjOBJ_SITE, n) >= 0
]
MOUNT_LINKS = sorted({MD.body(int(MD.cam_bodyid[MD.camera(c).id])).name for c in CAMS} - {"world"})
LINKS = TIPS + MOUNT_LINKS
_rb = int(MD.jnt_bodyid[J_ID[0]])
while int(MD.body_parentid[_rb]) != 0:
    _rb = int(MD.body_parentid[_rb])
ROOT_BODY = MD.body(_rb).name
ROOT_POSE = [*S.data.xpos[_rb].tolist(), *S.data.xquat[_rb].tolist()]
LO = np.array([MD.jnt_range[j, 0] if MD.jnt_limited[j] else -np.inf for j in J_ID])
HI = np.array([MD.jnt_range[j, 1] if MD.jnt_limited[j] else np.inf for j in J_ID])


def _fk_kd(q, base_pose=None) -> None:
    if ROOT is not None:
        a = MD.jnt_qposadr[ROOT]
        KD.qpos[a:a + 7] = base_pose if base_pose is not None else [0, 0, 0, 1, 0, 0, 0]
    KD.qpos[J_Q] = q
    mujoco.mj_kinematics(MD, KD)
    mujoco.mj_comPos(MD, KD)  # the Jacobians (mj_jacSite) need it


def _pose(name: str) -> list:
    quat = np.zeros(4)
    if name in TIPS:
        sid = MD.site(name).id
        mujoco.mju_mat2Quat(quat, KD.site_xmat[sid])
        return [*KD.site_xpos[sid].tolist(), *quat.tolist()]
    b = MD.body(name).id
    return [*KD.xpos[b].tolist(), *KD.xquat[b].tolist()]


def do_kinematics(req: dict) -> dict:
    """Fingertips (sites) and the camera mounts (bodies) in the world frame for joint angles q (the limb's joints, in
    `joint_pos` order). IK solves fingertip positions only (Levenberg-Marquardt over all limb joints within their
    ranges); a fingertip's orientation is ignored."""
    if req["op"] == "fk":
        _fk_kd(np.asarray(req["q"]), req.get("base_pose"))
        return L.fk_response({n: _pose(n) for n in req["links"]}, KIN_FRAME)
    q = np.array(req["seed"] if req["seed"] is not None else S.data.qpos[J_Q], dtype=np.float64)
    tg = {k: np.asarray(v[:3]) for k, v in req["targets"].items()}
    jac = np.zeros((3, MD.nv))

    def err(qq):
        _fk_kd(qq)
        return np.concatenate([t - KD.site_xpos[MD.site(k).id] for k, t in tg.items()])

    lam, e = 1e-2, err(q)
    for _ in range(req["max_iters"]):  # Levenberg-Marquardt on the stacked fingertip position errors
        if max(np.linalg.norm(e[3 * i : 3 * i + 3]) for i in range(len(tg))) < req["tol_pos_m"]:
            break
        _fk_kd(q)
        Js = []
        for k in tg:
            mujoco.mj_jacSite(MD, KD, jac, None, MD.site(k).id)
            Js.append(jac[:, J_V].copy())
        J = np.vstack(Js)
        dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(len(e)), e)
        n = np.linalg.norm(dq)
        if n > 0.2:
            dq *= 0.2 / n
        qn = np.clip(q + dq, LO, HI)
        en = err(qn)
        if np.linalg.norm(en) < np.linalg.norm(e):
            q, e, lam = qn, en, max(lam / 2, 1e-6)
        else:
            lam = min(lam * 4, 1e2)
    _fk_kd(q)
    errors = {k: (float(np.linalg.norm(t - KD.site_xpos[MD.site(k).id])), 0.0) for k, t in tg.items()}
    ok = all(v[0] <= req["tol_pos_m"] for v in errors.values())
    return L.ik_response(
        q, ok, errors, KIN_FRAME, note="fingertips: position only (orientation ignored); no collision check"
    )


# ------------------------------------------------------------------------------------------------- spec
TASK_TEXT = TASK_INFO["task_text"]
ONE = "one episode, no reset" if not RESET_BUDGET else (
    f"an episode (with up to {RESET_BUDGET} resets: POST /reset starts a new one; only the last is graded)")
EPISODE = {
    "hold": f"{ONE}: it ends the moment the task's goal has held for {S.hold_steps} control steps in a row "
    f"({round(S.hold_steps * DT, 3)} s; success), at the task's failure (see task_text), or when your time is over",
    "event": f"{ONE}: it ends at the challenge's success event (success), at its failure conditions or "
    "its own time limit (see task_text), or when your time is over",
    "track": f"{ONE}: it lasts {S.track_steps} control steps (the reference motion; then it is judged), "
    "ends early at MyoDex's termination (failure), or when your time is over",
}[S.rule]
MUSCLE_TEXT = (
    "muscles: one real number a per muscle; excitation u = 1 / (1 + exp(-5 (a - 0.5))), a not clipped (a = -1: u ~ "
    "0.0006, 0.5: 0.5, 1: 0.92, 2: 0.9994); activations follow excitations with a first-order delay (~10 ms up, ~40 ms "
    "down); muscles only pull, one can cross several joints, and its force depends on its length and velocity"
)
ACTION = {
    "dim": NU,
    "layout": ACT_NAMES,
    "limits": None,
    "units": MUSCLE_TEXT if not OTHER else MUSCLE_TEXT + "; the other actuators: see `actuators`",
    "semantics": "one row per control step, every actuator in `layout` order. Rows are `dt` apart (a whole multiple of "
    "the control period, at most 0.5 s), `linear` (default: from the previous command) or `hold` between rows; "
    "nothing is clipped by the service (MuJoCo clips the non-muscle controls to their ranges)",
}
if OTHER:
    ACTION["actuators"] = [{"index": a["index"], "name": a["name"], "kind": a["kind"], "command": a["command"]} for a in OTHER]
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "MyoSuite 2.12.2 on MuJoCo 3.6.0 (CPU)",
    "robot": f"{ROBOT[0]}: {ROBOT[1]}, {len(MUSCLES)} muscles" + (f" and {len(OTHER)} other actuators" if OTHER else ""),
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "cameras": {
        c: {
            "rgb": True,
            "depth": True,
            "resolution": [W, H],
            "intrinsic_cv": _intrinsic(c),
            "mounted": MOUNTED[c],
            "mount": _mount(c),
        }
        for c in CAMS
    },
    "default_cameras": DEFAULT_CAMS,
    "action_types": {ATYPE: ACTION, "not_yet": ["joint_position", "joint_torque", "joint_delta"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {"muscles": MUSCLES},
    "world": {
        "frame": "MyoSuite's world frame, z up"
        + ("; the body stands free in it (its root pose is proprioception)" if ROOT is not None
           else "; the body's root is fixed in it")
        + " (no positions of the scene are given)",
        "up": "+z",
        "units": {"length": "m", "angle": "rad", "time": "s"},
        "quaternion_order": "wxyz",
        "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes",
    },
    "budget": {"reset": RESET_BUDGET, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": EPISODE,
    "robot_spec": {
        "name": ROBOT[0],
        "description": f"{ROBOT[1]}: {len(MUSCLES)} muscle actuators"
        + (f", {len(OTHER)} other actuators" if OTHER else "") + f", {len(J_NAMES)} joints",
        "base": (
            {"type": "mobile", "link": ROOT_BODY, "pose_proprio": "root_pose", "velocity_proprio": "root_vel",
             "note": "a free-standing body: nothing holds its root (the pelvis); it moves only through contacts"}
            if ROOT is not None else
            {"type": "fixed", "link": ROOT_BODY, "pose": ROOT_POSE,
             "note": "the body's root is fixed in the world (pose: x y z + wxyz quaternion)"}
        ),
        "joints": [
            {
                "name": n,
                "type": ("prismatic" if J_SLIDE[k] else "revolute") if np.isfinite(LO[k]) else "continuous",
                "unit": "m" if J_SLIDE[k] else "rad",
                "position_limits": [float(LO[k]), float(HI[k])] if np.isfinite(LO[k]) else None,
                "velocity_limit": None,
                "effort_limit": None,
                "group": BODY,
            }
            for k, n in enumerate(J_NAMES)
        ],
        "grippers": {},
        "controller": {
            "type": "muscle actuators (MuJoCo muscle model); no joint-level controller"
            + ("; plus the non-muscle actuators in action_types" if OTHER else ""),
            "control_hz": CTRL_HZ,
            "physics_hz": CTRL_HZ * SUBSTEPS,
            "gains": {},
            "note": "the command is each muscle's excitation (the muscles: static.muscles); the joints move only "
            "through actuator forces",
        },
        "tcp": {},
    },
    "kinematics": {
        "endpoint": "/kinematics",
        "joint_names": GROUPS[0][1],
        "frame": KIN_FRAME,
        "quaternion_order": "wxyz",
        "links": LINKS,
        "tcp_frames": [],
        "ee_frames": TIPS,
        "ik_targets": TIPS,
        "ik": {"tol_pos_m": 0.002, "tol_rot_rad": 3.2, "max_iters": 500},
        "note": "fingertip sites and the camera mounts for joint positions q (`joint_pos` order), in the "
        + ("root's frame (or the world's, given base_pose)" if ROOT is not None else "world frame")
        + "; ik: fingertip positions only, over all body joints",
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
if TASK_INFO.get("reference"):  # MyoDex: the reference motion is the goal (relative to the object's start pose)
    SPEC["reference_motion"] = {
        "columns": ["t_s", "dx_m", "dy_m", "dz_m", "qw", "qx", "qy", "qz"],
        "rows": TASK_INFO["reference"],
        "meaning": "the reference pose of the manipulated item per control step: its centre of mass relative to where "
        "it starts (world axes) and its orientation (world frame, wxyz)",
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
    # joint_effort from the physics, not the mirror: MyoSuite steps its robot wrapper's own MjData and refreshes
    # S.data (base.mj_data) from qpos / qvel / act only, then mj_forward with ctrl = 0. The mirror's qfrc_actuator was
    # the force of a zero command: the wrist / pelvis / MPL position servos read kp * (0 - q) whatever was commanded.
    phys = S.base.robot.mj_data
    parts = [d.qpos[J_Q], d.qvel[J_V], d.act[ACT_ADR], d.actuator_length[MUS_IDX], phys.qfrc_actuator[J_V]]
    if ROOT is not None:
        parts += [d.qpos[MD.jnt_qposadr[ROOT]:MD.jnt_qposadr[ROOT] + 7], d.qvel[MD.jnt_dofadr[ROOT]:MD.jnt_dofadr[ROOT] + 6]]
    return np.concatenate(parts).astype(
        np.float32
    )


def grab(cams, want_depth: bool):
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c, (H, W))
        if want_depth:  # the same renderer (a second OSMesa context next to a live one reads garbage)
            r = S._renderer
            r.enable_depth_rendering()
            r.update_scene(S.data, camera=c)
            dep[c] = r.render().astype(np.float32).copy()
            r.disable_depth_rendering()
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: np.asarray(camera_info(c)["extrinsic_cv"], dtype=np.float64) for c in cams}


def write_final() -> None:
    if L.final_verdict(DATA):  # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {**summary(), "finalized": False, "live_sha": E.get("live_sha")})


def summary() -> dict:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    return {
        "success": bool(E["success"]),
        "steps": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
        "reason": E["reason"],
        "done": E["done"],
        "task": TASK,
        "protocol": L.PROTOCOL,
        "n_actions": len(ROWS),
        "episodes": E["resets"] + 1,
        "resets": E["resets"],
        "reset_budget": RESET_BUDGET,
        "control_steps_total": EP.rows,
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
    EP.log(
        {"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"]),
         "episode": E["resets"] + 1, "journal_rows": EP.rows}
    )
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    S.save_trajectory(
        np.asarray(ROWS, dtype=np.float64).reshape(-1, NU),
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


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 10
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= CTRL_HZ):
        raise ValueError(f"video_fps must be in [1, {CTRL_HZ:g}]")
    return int(fps)


def cameras_of(meta: dict) -> list:
    cams = meta.get("cameras") or DEFAULT_CAMS
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
        "time_s": round(time.time() - E["t0"], 2),
        "time_left_s": max(0.0, round(WALL_CLOCK_S - (time.time() - E["t0"]), 1)),
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()},
        "done": E["done"],
        "reason": E["reason"],
        "cameras": {c: camera_info(c) for c in cams},
        **reset_counters(),
    }


def last_command() -> np.ndarray:
    return ROWS[-1].copy() if ROWS else S.rest_action()


def do_submit(meta: dict, A: np.ndarray):
    typ = meta.get("type")
    if typ != ATYPE:
        raise ValueError(f"type must be {ATYPE} (not yet: {SPEC['action_types']['not_yet']})")
    dt = float(meta.get("dt", DT))
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps = cameras_of(meta), video_fps(meta)
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != NU:
        raise ValueError(f"{ATYPE} actions must be (T, {NU}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (math.isfinite(dt) and dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
        raise ValueError(f"dt must be a whole multiple of the {DT:g} s control period and at most 0.5 s; got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta, video)
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
    out = {
        **meta_common(cams),
        "chunk_id": E["calls"],
        "type": typ,
        "executed_rows": E["step"] - step0,
        "control_steps_chunk": ctrl_steps() - before,
        "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
        "clipped": [],
        "n_clipped": 0,
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
            "note": (meta.get("note") or "")[:500],
            **({"stopped": EP.stop_reason} if EP.stopping else {}),
        }
    )
    return out, rec.parts(video, fps)


def do_observe(meta: dict):
    cams, fps = cameras_of(meta), video_fps(meta)
    seconds = float(meta.get("seconds", 0))
    video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec, before = recorder(cams, fps, meta, video), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = last_command()
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


def reset_counters() -> dict:
    if not RESET_BUDGET:
        return {}
    left = 0 if (E["success"] or E.get("exiting")) else RESET_BUDGET - E["resets"]
    return {"episode": E["resets"] + 1, "resets_left": left, "control_steps_total": EP.rows}


def status() -> dict:
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": ctrl_steps(),
        "done": E["done"],
        "reason": E["reason"],
        "elapsed_s": round(time.time() - E["t0"], 1),
        **reset_counters(),
    }


class Refused(Exception):
    """A /reset the service turns down (409): nothing changes."""

    def __init__(self, body: dict):
        super().__init__(body.get("error"))
        self.body = body


def do_reset(meta: dict):
    """POST /reset: a new episode from the frozen instance (the running one, if any, is abandoned, never graded)."""
    cams, fps = cameras_of(meta), video_fps(meta)
    L.depth_mode(meta)  # a bad depth value is a 400 before anything changes
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


# A resume replays the journal from the frozen instance and resets where the committed resets did: their journal rows
# are in the last checkpoint (`persist`), the one Episode.begin resumes from.
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
    _resume_resets()  # a reset after the last replayed row (or before the first)
    return S.state_sha()


RESUMED = EP.begin(
    state=E,
    step=replay_row,
    state_sha=resume_sha,
    proprio=proprio_row,
    spec=SPEC,
    on_end=end_from_signal,
    start_event={"task": TASK, "env": S.env_id, "cameras": CAMS},
)
if RESUMED and E["resets"]:  # Episode.begin looks for an "end" of any episode: only the current one's counts
    _ends = [e for e in EP.events() if e.get("ev") == "end" and int(e.get("episode") or 1) == E["resets"] + 1
             and int(e.get("journal_rows") or 0) <= EP.rows]
    if _ends:
        E.update(done=True, reason=_ends[-1].get("reason"), t_end=float(_ends[-1]["ts"]),
                 episode_control_steps=int(_ends[-1].get("control_steps") or ctrl_steps()))
    else:
        E.update(done=False, reason=None, t_end=None, episode_control_steps=None)
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(
    f"{L.PROTOCOL} MyoSuite sim ready ({TASK}: {S.env_id}; startup {EP.n_startups}, resumes {EP.resumes})", flush=True
)


def make_handler(svc: L.Service):
    """The shared 2.2 handler, plus POST /reset when the run grants resets (the shared layer has no reset)."""
    base = L.make_handler(svc)

    class H(base):
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

    return H


def serve(svc: L.Service, port: int) -> None:
    """L.serve with this service's handler (the same spec defaults and check)."""
    from http.server import HTTPServer

    svc.spec.setdefault("on_service_error", L.ON_SERVICE_ERROR)
    svc.spec.setdefault("max_call_wall_s", EP.max_call_wall_s)
    L.check_spec(svc.spec)
    HTTPServer(("0.0.0.0", port), make_handler(svc)).serve_forever()


try:
    serve(
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
