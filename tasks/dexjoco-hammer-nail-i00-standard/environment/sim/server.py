"""eai-standard/2.2 sim service for DexJoCo (docs/STANDARD_MODE_2_2.md): the adapter of the shared layer rcb_limited.py;
the simulator is rcb_dexjoco.Session (DexJoCo on MuJoCo 3.4, CPU physics, OSMesa rendering).
HTTP surface: GET /spec, GET /status, POST /observe, POST /submit, POST /kinematics. Every call is logged to
/data/episode.jsonl.

The robot is a Franka Panda with a 16-DoF Allegro hand, or two of them side by side (right arm first). One control step
= 1/50 s (10 physics substeps of 2 ms). Two action types:
  ee_pose         DexJoCo's own row, per arm: the tcp target pose (xyz m, quaternion wxyz, world frame) that its
                  operational-space controller tracks + 16 Allegro joint targets (rad);
  joint_position  per arm: 7 arm joint targets + 16 Allegro joint targets; the arm's targets are turned into a tcp target
                  by forward kinematics (the controller tracks the tcp pose, not the joints).
Either way, the executed (journaled, recorded) row is DexJoCo's own row, so the recorded trajectory replays in the
privileged tooling unchanged. As in DexJoCo's evaluation the episode ends at the first success or task failure;
otherwise when the agent's time is over (the collect hook's SIGUSR1).

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the instance and replays the journal. When the
episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect hook (finalize.sh) makes it exit
and replays the trajectory in two fresh processes."""

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
TASK = os.environ.get("RCB_TASK", "water_plant")
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.npz"))
TASK_TEXT_FILE = os.environ.get("RCB_TASK_TEXT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_text.txt"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
CAM_W, CAM_H = 640, 480
CTRL_HZ = 50.0
DT = 1.0 / CTRL_HZ
SUBSTEPS = 10
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}

os.environ["RCB_SESSION_LOG"] = ""               # the sidecar's Session is not the agent's interaction log
import rcb_dexjoco as M  # noqa: E402
import mujoco  # noqa: E402

M.SESSION_LOG = ""
BIM = TASK.startswith("bimanual_")
ADIM = 46 if BIM else 23
EP = L.Episode(DATA, dim=ADIM, resume="exact")
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Session(TASK, instance=INSTANCE, image_size=(CAM_H, CAM_W))
MD, D = S.model, S.data
ARMS = S.arms()
SFX = {a: (f"_{a}" if BIM else "") for a in ARMS}
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz

# ------------------------------------------------------------------------------------------------- the robot
ARM_JOINTS = {a: [f"joint{i}{SFX[a]}" for i in range(1, 8)] for a in ARMS}
HAND_CTRL = {a: np.asarray(S._hand_ctrl_ids(a)) for a in ARMS}
HAND_JOINTS = {a: [MD.joint(int(MD.actuator_trnid[i, 0])).name for i in HAND_CTRL[a]] for a in ARMS}   # action order
ARM_CTRL = {a: [MD.actuator(f"actuator{i}{SFX[a]}").id for i in range(1, 8)] for a in ARMS}
JOINTS = [j for a in ARMS for j in ARM_JOINTS[a] + HAND_JOINTS[a]]          # kinematics q = proprio joint_pos columns
QADR = np.array([MD.jnt_qposadr[MD.joint(j).id] for j in JOINTS])
VADR = np.array([MD.jnt_dofadr[MD.joint(j).id] for j in JOINTS])
EFF_ACT = np.array([i for a in ARMS for i in list(ARM_CTRL[a]) + list(HAND_CTRL[a])])
TCP_SITE = {a: MD.site(f"attachment_site{SFX[a]}").id for a in ARMS}
TCP = {a: f"tcp{SFX[a]}" for a in ARMS}
MOUNT_BODY = {a: f"attachment{SFX[a]}" for a in ARMS}
LINKS = {a: [f"link{i}{SFX[a]}" for i in range(0, 8) if mujoco.mj_name2id(MD, mujoco.mjtObj.mjOBJ_BODY, f"link{i}{SFX[a]}") >= 0]
         + [MOUNT_BODY[a]] for a in ARMS}
KIN_LINKS = [n for a in ARMS for n in LINKS[a] + [TCP[a]]]
JLIM = {j: MD.jnt_range[MD.joint(j).id].astype(float).tolist() for j in JOINTS}
HLIM = {a: S.hand_limits(a) for a in ARMS}                                   # actuator ctrlrange, action order
ALIM = {}                                                                    # joint_position limits (inside the joint ranges)
for a in ARMS:
    for j in ARM_JOINTS[a]:
        ALIM[j] = JLIM[j]
    for j, (lo, hi) in zip(HAND_JOINTS[a], HLIM[a]):
        ALIM[j] = [max(float(lo), JLIM[j][0]), min(float(hi), JLIM[j][1])]
POSE = ["x", "y", "z", "qw", "qx", "qy", "qz"]
EE_LAYOUT = []                                                               # per arm, right first
for a in ARMS:
    EE_LAYOUT += [f"{TCP[a]}_target_{k}" for k in POSE] + [f"{j}_target" for j in HAND_JOINTS[a]]
JP_LAYOUT = [j for a in ARMS for j in ARM_JOINTS[a] + HAND_JOINTS[a]]

GROUPS = [
    ("joint_pos", JOINTS, "measured joint positions (rad): per arm (right first) the 7 Panda joints, then the 16 Allegro "
                          "joints in the action's order"),
    ("joint_vel", [f"{j}_vel" for j in JOINTS], "measured joint velocities (rad/s)"),
    ("joint_effort", [f"{j}_effort" for j in JOINTS], "actuator efforts (N m): the arm's operational-space torques and the "
                                                      "hand's position-actuator forces"),
    ("gripper_opening", [], "none: a 16-DoF Allegro hand, its finger joints are in joint_pos"),
    ("tcp_pose", [f"{TCP[a]}_{k}" for a in ARMS for k in POSE], "measured tcp pose per arm (x y z m, quaternion wxyz, world)"),
    ("tcp_target", [f"{TCP[a]}_target_{k}" for a in ARMS for k in POSE], "the tcp target the controller tracks now (the "
                                                                         "ee_pose part of the last executed row)"),
    ("hand_target", [f"{j}_target" for a in ARMS for j in HAND_JOINTS[a]], "the Allegro joint targets now (rad)"),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)


def _quat(xmat) -> np.ndarray:
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(xmat, dtype=np.float64).reshape(9))
    return q


# ------------------------------------------------------------------------------------------------- cameras
CAMS = S.cameras()
HAND_CAMS = [c for c in CAMS if c.startswith("handcam")]
DEFAULT_CAMS = [S.default_camera()]
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])


def _intrinsic(cam: str) -> list:
    fovy = math.radians(float(MD.cam_fovy[MD.camera(cam).id]))
    f = 0.5 * CAM_H / math.tan(fovy / 2)
    return [[f, 0.0, CAM_W / 2], [0.0, f, CAM_H / 2], [0.0, 0.0, 1.0]]


def _cam2world_gl(cam: str) -> np.ndarray:
    i = MD.camera(cam).id
    T = np.eye(4)
    T[:3, :3] = D.cam_xmat[i].reshape(3, 3)          # MuJoCo camera axes: OpenGL (x right, y up, z back)
    T[:3, 3] = D.cam_xpos[i]
    return T


def _extrinsic(cam: str) -> np.ndarray:
    return np.linalg.inv(_cam2world_gl(cam) @ GL2CV)[:3, :]


def camera_info(cam: str) -> dict:
    return {"intrinsic_cv": _intrinsic(cam), "extrinsic_cv": _extrinsic(cam).tolist(), "cam2world_gl": _cam2world_gl(cam).tolist(),
            "image_size": [CAM_W, CAM_H]}


def _mount(cam: str) -> dict:
    i = MD.camera(cam).id
    body = MD.body(int(MD.cam_bodyid[i])).name
    if int(MD.cam_bodyid[i]) == 0:
        return {"type": "static", "extrinsic_cv": _extrinsic(cam).tolist(), "cam2world_gl": _cam2world_gl(cam).tolist()}
    T = np.eye(4)                                     # body -> camera (OpenGL axes), then to OpenCV axes
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, MD.cam_quat[i])
    T[:3, :3] = R.reshape(3, 3)
    T[:3, 3] = MD.cam_pos[i]
    return {"type": "link", "parent_link": body, "link_T_cam_cv": (T @ GL2CV).tolist()}


def _mounted(cam: str) -> str:
    if cam.startswith("handcam"):
        side = "the right" if cam.endswith("_right") else "the left" if cam.endswith("_left") else "the"
        return f"on {side} hand's mount (moves with the hand)"
    return {"front": "static, across the table, facing the robot", "back": "static, behind the robot, looking over the table",
            "left": "static, at the robot's left", "right": "static, at the robot's right",
            "top0": "static, above the table, looking down"}.get(cam, "static")


# ------------------------------------------------------------------------------------------------- kinematics
KD = mujoco.MjData(MD)        # kinematics only: never stepped; the robot's joints are set, everything else stays put
ARM_QI = {a: [JOINTS.index(j) for j in ARM_JOINTS[a]] for a in ARMS}


def _fk(q) -> None:
    KD.qpos[:] = D.qpos
    KD.qpos[QADR] = np.asarray(q, dtype=np.float64)
    mujoco.mj_kinematics(MD, KD)


def _link_pose(name: str) -> list:
    for a in ARMS:
        if name == TCP[a]:
            s = TCP_SITE[a]
            return [*KD.site_xpos[s].tolist(), *_quat(KD.site_xmat[s]).tolist()]
    b = MD.body(name).id
    return [*KD.xpos[b].tolist(), *KD.xquat[b].tolist()]


def tcp_from_arm_joints(a: str, q7) -> np.ndarray:
    """The tcp pose (xyz + wxyz) of arm `a` with its 7 joints at q7 (the joint_position action's tcp target)."""
    KD.qpos[:] = D.qpos
    KD.qpos[QADR[ARM_QI[a]]] = q7
    mujoco.mj_kinematics(MD, KD)
    s = TCP_SITE[a]
    return np.concatenate([KD.site_xpos[s], _quat(KD.site_xmat[s])])


def do_kinematics(req: dict) -> dict:
    """World frame. FK: every link of spec kinematics.links for q. IK: per tcp target, damped least squares over that
    arm's 7 joints (position and orientation), within the joint ranges; the hand joints are taken from the seed."""
    if req["op"] == "fk":
        _fk(req["q"])
        return L.fk_response({n: _link_pose(n) for n in req["links"]}, "world")
    q = np.array(req["seed"] if req["seed"] is not None else D.qpos[QADR], dtype=np.float64)
    errors = {}
    jp, jr = np.zeros((3, MD.nv)), np.zeros((3, MD.nv))
    for frame, pose in req["targets"].items():
        a = next(x for x in ARMS if TCP[x] == frame)
        idx = ARM_QI[a]
        dofs = VADR[idx]
        tp, tq = np.asarray(pose[:3]), np.asarray(pose[3:7])
        lo = np.array([JLIM[JOINTS[i]][0] for i in idx]); hi = np.array([JLIM[JOINTS[i]][1] for i in idx])
        for _ in range(req["max_iters"]):
            _fk(q)
            mujoco.mj_comPos(MD, KD)                      # the Jacobian needs cdof, which mj_kinematics alone leaves stale
            s = TCP_SITE[a]
            ep = tp - KD.site_xpos[s]
            cq = _quat(KD.site_xmat[s])
            dq = np.zeros(4); neg = np.zeros(4); er = np.zeros(3)
            mujoco.mju_negQuat(neg, cq); mujoco.mju_mulQuat(dq, tq, neg); mujoco.mju_quat2Vel(er, dq, 1.0)
            if np.linalg.norm(ep) < req["tol_pos_m"] and np.linalg.norm(er) < req["tol_rot_rad"]:
                break
            mujoco.mj_jacSite(MD, KD, jp, jr, s)
            J = np.vstack([jp[:, dofs], jr[:, dofs]])
            err = np.concatenate([ep, er])
            step = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), err)
            q[idx] = np.clip(q[idx] + step, lo, hi)
        _fk(q)
        s = TCP_SITE[a]
        errors[frame] = (float(np.linalg.norm(tp - KD.site_xpos[s])), L.quat_angle(_quat(KD.site_xmat[s]), tq / np.linalg.norm(tq)))
    ok = all(e[0] <= req["tol_pos_m"] and e[1] <= req["tol_rot_rad"] for e in errors.values())
    return L.ik_response(q, ok, errors, "world", note="the tcp (attachment_site) of each arm; the hand joints are the seed's")


# ------------------------------------------------------------------------------------------------- spec
def _joint_spec(a: str) -> list:
    out = []
    for j, ai in zip(ARM_JOINTS[a], ARM_CTRL[a]):
        out.append({"name": j, "type": "revolute", "unit": "rad", "position_limits": JLIM[j], "velocity_limit": None,
                    "effort_limit": float(MD.actuator_ctrlrange[ai][1]), "group": f"{a}_arm"})
    for j, ai in zip(HAND_JOINTS[a], HAND_CTRL[a]):
        fl = bool(MD.actuator_forcelimited[ai]) and float(MD.actuator_forcerange[ai][1]) > 0
        out.append({"name": j, "type": "revolute", "unit": "rad", "position_limits": JLIM[j], "velocity_limit": None,
                    "effort_limit": float(MD.actuator_forcerange[ai][1]) if fl else None, "group": f"{a}_hand"})
    return out


def _tcp_spec(a: str) -> dict:
    s = TCP_SITE[a]
    T = np.eye(4)
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, MD.site_quat[s])
    T[:3, :3] = R.reshape(3, 3)
    T[:3, 3] = MD.site_pos[s]
    return {"parent_link": MD.body(int(MD.site_bodyid[s])).name, "link_T_frame": T.tolist(),
            "definition": "DexJoCo's attachment_site: the flange where the Allegro hand is mounted, the point its "
                          "operational-space controller drives to the ee_pose target (not the fingertips)"}


def _base(a: str) -> list:
    b = D.body(f"link0{SFX[a]}")
    return [*np.round(b.xpos, 6).tolist(), *np.round(b.xquat, 6).tolist()]


GAINS = {}
for _a in ARMS:
    for _j, _ai in zip(HAND_JOINTS[_a], HAND_CTRL[_a]):
        GAINS[_j] = {"stiffness": float(MD.actuator_gainprm[_ai][0]), "damping": float(MD.dof_damping[MD.jnt_dofadr[MD.joint(_j).id]])}
ROBOT_NAME = "franka-allegro-bimanual" if BIM else "franka-allegro"
try:
    TASK_TEXT = open(TASK_TEXT_FILE).read().strip()
except OSError:
    TASK_TEXT = f"DexJoCo {TASK}"
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "DexJoCo @ 8d23b0f on MuJoCo 3.4.0 (CPU physics, OSMesa rendering)",
    "robot": ROBOT_NAME,
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "physics_hz": CTRL_HZ * SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": _mounted(c), "resolution": [CAM_W, CAM_H], "intrinsic_cv": _intrinsic(c),
                    "mount": _mount(c)} for c in CAMS},
    "default_cameras": DEFAULT_CAMS,
    "action_types": {
        "ee_pose": {
            "dim": ADIM, "layout": EE_LAYOUT,
            "units": "per arm (right first): tcp target position (m, world frame), tcp target orientation (quaternion wxyz), "
                     "16 Allegro joint targets (rad)",
            "frame": "world", "quaternion_order": "wxyz", "ee_frames": [TCP[a] for a in ARMS],
            "hand_limits": {j: ALIM[j] for a in ARMS for j in HAND_JOINTS[a]},
            "semantics": "DexJoCo's own action row. The arm tracks the tcp target through DexJoCo's operational-space "
                         "controller (it lags a moving target and stops where contact blocks it); the hand joints are "
                         "position-controlled. Rows are `dt` apart (a whole multiple of 1/50 s, at most 0.5 s); between rows "
                         "positions and joints move linearly and orientations by slerp (`linear`) or jump (`hold`); a row's "
                         "own values land exactly on its last control step. Hand targets outside the ranges are clamped by "
                         "the simulator and reported in `clipped`; a zero quaternion is a 400.",
        },
        "joint_position": {
            "dim": ADIM, "layout": JP_LAYOUT, "units": "rad", "limits": {j: ALIM[j] for j in JP_LAYOUT},
            "semantics": "per arm (right first): 7 Panda joint targets, then the 16 Allegro joint targets. The arm's "
                         "targets are turned into a tcp target by forward kinematics (as POST /kinematics fk) and the arm "
                         "tracks that pose through the same operational-space controller as ee_pose, whose null space "
                         "pulls towards DexJoCo's home posture: the tcp reaches FK(q), the measured joints may differ from q "
                         "in the arm's redundant direction. Rows `dt` apart, `linear` (in joint space) or `hold`; values "
                         "outside the limits are clipped and reported.",
        },
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},
    "world": {"frame": "DexJoCo's world frame: z up, metres; the robot" + ("s stand" if BIM else " stands")
                       + " at low x and reach" + ("" if BIM else "es") + " towards +x"
                       + (" (right arm at y < 0, left arm at y > 0)" if BIM else ""),
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": "one episode, no reset: it ends at the first success, at a task failure (see task_text), or when your time is over",
    "robot_spec": {
        "name": ROBOT_NAME,
        "description": ("two Franka Panda arms side by side, each with a 16-DoF Allegro hand (right arm first)" if BIM
                        else "a Franka Panda arm with a 16-DoF Allegro hand"),
        "base": {"type": "fixed", "pose": _base(ARMS[0]), **({"per_arm": {a: _base(a) for a in ARMS}} if BIM else {}),
                 "note": "pose of the arm's base link (link0), world frame, x y z + quaternion wxyz"},
        "joints": [j for a in ARMS for j in _joint_spec(a)],
        "grippers": {},
        "controller": {"type": "arm: operational-space control of the tcp (torques); hand: joint position actuators",
                       "control_hz": CTRL_HZ, "physics_hz": CTRL_HZ * SUBSTEPS, "gains": GAINS,
                       "note": "arm: DexJoCo's opspace controller drives attachment_site to the tcp target (position gains "
                               "400 N/m, damping ratio 4, gravity compensation, null space towards the home posture), "
                               "torques limited to effort_limit; hand: position actuators (stiffness N m/rad) on joints "
                               "with their own damping (N m s/rad)"},
        "tcp": {TCP[a]: _tcp_spec(a) for a in ARMS},
    },
    "kinematics": {"endpoint": "/kinematics", "joint_names": JOINTS, "frame": "world", "quaternion_order": "wxyz",
                   "links": KIN_LINKS, "tcp_frames": [TCP[a] for a in ARMS], "ee_frames": [TCP[a] for a in ARMS],
                   "ik_targets": [TCP[a] for a in ARMS], "ik": {"tol_pos_m": 0.001, "tol_rot_rad": 0.01, "max_iters": 300},
                   "note": "the arm links, the hand mount (the hand cameras' parent) and the tcp, world frame; ik solves "
                           "each tcp target over that arm's 7 joints"},
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0,
              "max_m": L.DEPTH_MAX_M, "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)  # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()


# ------------------------------------------------------------------------------------------------- state and frames
def ctrl_steps() -> int:
    return int(S.steps)


def proprio_row() -> np.ndarray:
    tcp, tgt, hand = [], [], []
    for a in ARMS:
        s = TCP_SITE[a]
        tcp += [D.site_xpos[s], _quat(D.site_xmat[s])]
        t = S._arm_target(a)
        tgt.append(t[:7]); hand.append(t[7:23])
    return np.concatenate([D.qpos[QADR], D.qvel[VADR], D.actuator_force[EFF_ACT], *tcp, *tgt, *hand]).astype(np.float32)


def grab(cams, want_depth: bool):
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c, (CAM_H, CAM_W))
        if want_depth:
            r = S._renderer                              # the one renderer (a second OSMesa context reads back garbage)
            r.enable_depth_rendering()
            try:
                r.update_scene(D, camera=c)
                dep[c] = r.render().astype(np.float32).copy()
            finally:
                r.disable_depth_rendering()
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: _extrinsic(c) for c in cams}


def summary() -> dict:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    return {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
            "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"],
            "task": TASK, "protocol": L.PROTOCOL, "n_actions": len(ROWS), "task_failure": int(str(E["reason"] or "").startswith("failure")),
            **EP.final_fields()}


def write_final() -> None:
    if L.final_verdict(DATA):  # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {**summary(), "finalized": False, "live_sha": E.get("live_sha")})


def finish(reason: str) -> None:
    """The episode is over: record the live verdict and dump the trajectory for the collect hook."""
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    E["episode_control_steps"] = ctrl_steps()
    E["success"] = bool(S.success)
    EP.log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"])})
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    S.save_trajectory(np.asarray(ROWS, dtype=np.float64).reshape(-1, ADIM), os.path.join(DATA, "trajectory.npz"),
                      {"source": "standard-mode episode", "reason": E["reason"]})
    L._write_json(os.path.join(DATA, "episode.json"), {**summary(), "live_sha": E["live_sha"]})
    write_final()


def ctrl_step(a, rec) -> bool:
    """One executed control step (DexJoCo's own row), journaled. True when the call must stop here."""
    a = np.asarray(a, dtype=np.float64)
    running = S.step(a)
    ROWS.append(a.copy())
    stop = EP.journal(a)
    rec.tick()
    if not running:
        finish(S.reason or "done")
    return E["done"] or stop


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 10
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 50):
        raise ValueError("video_fps must be in [1, 50]")
    return int(fps)


def cameras_of(meta: dict) -> list:
    cams = meta.get("cameras") or DEFAULT_CAMS
    if not isinstance(cams, list) or any(c not in CAMS for c in cams):
        raise ValueError(f"unknown cameras {cams}; cameras: {CAMS}")
    return list(dict.fromkeys(cams))


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
            "sim_time_s": round(n * DT, 3), "time_s": round(time.time() - E["t0"], 2),
            "time_left_s": max(0.0, round(WALL_CLOCK_S - (time.time() - E["t0"]), 1)),
            "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            "cameras": {c: camera_info(c) for c in cams}}


def _native_from_ee(row: np.ndarray, ri: int, clipped: list) -> np.ndarray:
    """ee_pose rows are executed as sent (the recorded row is what the agent commanded); hand targets outside the
    actuator ranges are clamped by MuJoCo itself (ctrllimited) and only reported."""
    for k, a in enumerate(ARMS):
        o = 23 * k
        if float(np.linalg.norm(row[o + 3:o + 7])) < 1e-6:
            raise ValueError(f"row {ri}: the {a} tcp quaternion has zero norm")
        for j in range(16):
            lo, hi = HLIM[a][j]
            v = row[o + 7 + j]
            if v < lo or v > hi:
                clipped.append({"row": ri, "index": int(o + 7 + j), "reason": f"{EE_LAYOUT[o + 7 + j]} outside [{lo:.3f}, {hi:.3f}]: clamped by the simulator"})
    return row


def _clip_joints(row: np.ndarray, ri: int, clipped: list) -> np.ndarray:
    lo = np.array([ALIM[j][0] for j in JP_LAYOUT]); hi = np.array([ALIM[j][1] for j in JP_LAYOUT])
    out = np.clip(row, lo, hi)
    for j in np.flatnonzero(out != row)[:20]:
        clipped.append({"row": ri, "index": int(j), "reason": f"{JP_LAYOUT[j]} limit [{lo[j]:g}, {hi[j]:g}]"})
    return out


def _native_from_joints(q: np.ndarray) -> np.ndarray:
    out = []
    for k, a in enumerate(ARMS):
        o = 23 * k
        out += [tcp_from_arm_joints(a, q[o:o + 7]), q[o + 7:o + 23]]
    return np.concatenate(out)


def _check_chunk(typ: str, A: np.ndarray, dt: float, interp: str, video: str) -> int:
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != ADIM:
        raise ValueError(f"{typ} actions must be (T, {ADIM}), got {list(A.shape)}")
    if A.shape[0] == 0:
        raise ValueError("no rows")
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
    return int(round(k))


def do_submit(meta: dict, A: np.ndarray):
    typ = meta.get("type")
    if typ not in ("ee_pose", "joint_position"):
        raise ValueError(f"type must be ee_pose or joint_position (not yet: {SPEC['action_types']['not_yet']})")
    dt = float(meta.get("dt", DT))
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps = cameras_of(meta), video_fps(meta)
    n = _check_chunk(typ, A, dt, interp, video)
    clipped: list = []
    if typ == "ee_pose":
        A = np.stack([_native_from_ee(np.asarray(r, dtype=np.float64), i, clipped) for i, r in enumerate(A)])
    else:
        A = np.stack([_clip_joints(np.asarray(r, dtype=np.float64), i, clipped) for i, r in enumerate(A)])
    rec = recorder(cams, fps, meta)
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    if typ == "ee_pose":
        prev = np.asarray(S.hold_action(), dtype=np.float64)
    else:
        prev = np.concatenate([np.concatenate([D.qpos[QADR[ARM_QI[a]]], S._arm_target(a)[7:23]]) for a in ARMS])
    for row in A:
        E["step"] += 1
        stop = False
        for s in range(1, n + 1):
            if interp == "hold" or s == n:
                target = row                                  # a row's own values land exactly on its last control step
            else:
                target = prev + (row - prev) * (s / n)
                if typ == "ee_pose":
                    for k in range(len(ARMS)):
                        o = 23 * k
                        target[o + 3:o + 7] = M.quat_slerp(prev[o + 3:o + 7], row[o + 3:o + 7], s / n)
            native = target if typ == "ee_pose" else _native_from_joints(target)
            if ctrl_step(native, rec):
                stop = True
                break
        prev = row
        if stop:
            break
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0,
           "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
           "clipped": clipped[:200], "n_clipped": len(clipped), "plan": [], "ok": True}
    EP.log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp,
            "cameras": cams, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped),
            "note": (meta.get("note") or "")[:500], **({"stopped": EP.stop_reason} if EP.stopping else {})})
    return out, rec.parts(video, fps)


def do_observe(meta: dict):
    cams, fps = cameras_of(meta), video_fps(meta)
    seconds = float(meta.get("seconds", 0))
    video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec, before = recorder(cams, fps, meta), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(S.hold_action(), dtype=np.float64)
        for _ in range(int(round(seconds / DT))):
            if ctrl_step(hold, rec):
                break
    rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    EP.log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before,
            **({"stopped": EP.stop_reason} if EP.stopping else {})})
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


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


EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": TASK, "instance_sha": S.instance_sha, "instance_ok": bool(S.instance_exact), "cameras": CAMS})
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} DexJoCo sim ready ({TASK}; startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=EP.log, episode=EP, state_sha=S.state_sha,
                  proprio=proprio_row), port=int(os.environ.get("RCB_PORT", "8000")))
