"""Standard-mode sim service of the IKEA MuJoCo tasks (robot as a service; the shared layer rcb_limited.py of
scripts/eai_standard/v2_4/, copied unchanged, serves eai-standard/2.4 and answers 2.1 / 2.2 requests unchanged).
Source: scripts/ikea_mujoco/standard/server.py, copied unchanged into every tasks/ikea-<task>-i00-standard/environment/sim/.
Adapted from the RoboTangle / RoboARC standard services.

Physics: the scene's own runtime (rcb_ikea.Session, the privileged twin's tooling, copied unchanged): MuJoCo 3.14.0 on
the CPU, float64; one control step = data.ctrl[:] = row, then 4 physics steps of the scene (S.step: physics + the
scene's mechanism + its success monitor). Exactly what the privileged grader replays.
HTTP (rcb_limited.py): GET /spec, GET /status, POST /observe, POST /submit (RCB1), POST /kinematics (stateless FK / IK on
a scratch copy of the robot's MuJoCo model). Nothing about the furniture parts ever leaves this process.

Frame (the robot frame; called the world frame in every text the agent sees): origin at the LEFT arm's base link (Panda
left_link0, ViperX left_base_link) on its mounting, the axes of that link (+z up, x the arm's forward direction). Every
pose this service gives or takes (proprio tcp_pose, /kinematics in and out, camera extrinsic_cv / cam2world_gl, static
camera mounts, robot_spec.base) is in it. The scene's MuJoCo world frame, and so every position of the scene (parts,
table, work surface), stays in this process; physics, the recorded rows, the grader and the state hashes do not depend
on the frame. The right arm's base pose in it is rig geometry (robot_spec.base), like ALOHA's fixed rig.

Cameras (ikea_rig.py): four ALOHA-style cameras added at service start without touching the model: cam_high and cam_low
(static), cam_left_wrist and cam_right_wrist (on each hand), 848 x 480; posed from a scratch copy of the joint positions;
OpenCV intrinsics and per-frame extrinsics (robot frame). RGB: Nyx, RoboARC's renderer and look (ikea_nyx.py: a separate
render process with its own Python environment, fed the scene once and per-frame poses; RCB_RENDER=egl draws MuJoCo's
raster instead, for tests only). Depth on request: MuJoCo's raster (EGL) at the same cameras, as RoboARC's.

Speed rule (clamp, not fail; the robots' real limits, rcb_ikea.JOINT_SPEED_LIMITS_RAD_S / GRIPPER_SPEED_LIMITS, the one
table that rcb_ikea.Session.applied() also enforces in both modes and in the grader's replay): each limited target (the arm
joints; a gripper only if the table limits it, none today) moves at most its limit x control step from the previous control
step's target. A row that asks for more takes the control steps it needs (each one executed, journaled and recorded, so
the verifier's replay runs exactly what ran, and the Session clamp leaves those rows unchanged) and meta["clipped"] says
so. An unlimited gripper switches at the row.

Budget: the wall clock only (PROTOCOL v2.0 H.7: the privileged twin's cutoff). spec budget.wall_clock_s (RCB_WALL_CLOCK_S,
10800 s) counts from the agent's first request to the service (any endpoint), so the service's time_left_s never runs out
before Harbor's [agent] timeout_sec does; at 0 the episode ends (reason "timeout") between calls.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU is bit-deterministic): every executed control
step is journaled (journal.f64, float64), every completed call checkpointed (rows, state hash, proprio). After a crash
compose restarts the container and the service replays the journal and continues the SAME episode.

Episode end (the live verdict = the grader's verdict, rcb_ikea.Session.final_check(), as RoboWits #243 / BEHAVIOR #254):
  - success: the first time status()["success"] holds (success.py AND released AND at rest AND no breakdown so far)
    AND the settled check passes: final_check() on a snapshot (the last executed row held SETTLE_S more, the same rules
    again), restored bit-exactly afterwards (evaluating never changes the physics or the journal). If the settled check
    fails, the episode goes on (meta settle_failed counts it): the agent can still fix it. Both checks run after every
    /submit and every watching /observe;
  - sim_breakdown: status()["breakdown"] (a non-finite state, a MuJoCo BADQACC / BADQPOS / BADQVEL warning, a part
    contact deeper than 10 mm), checked on every control step; no success;
  - timeout (the wall clock), or error (a simulator error).
Then the service writes /data/trajectory.npz (rcb_ikea layout: ctrl (N, nu) float64 = every executed control step,
substeps, timestep, actuators) and /data/episode.json (live result, final state hash); the collect hook (finalize.sh) ends
the service and writes final.json. The verifier replays trajectory.npz itself (two fresh processes, rcb_ikea.py replay,
final_check(): the terminal rules at the end of the rows and after a 1.0 s hold of the last row), with no network.
A live video of cam_high (/data/live.mp4, RCB_LIVE_FPS frames per simulated second) is recorded during the episode; it
never affects the verdict."""
from __future__ import annotations
import json, math, os, queue, shutil, sys, threading, time, traceback
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "lack")
BINDING = json.load(open(os.environ.get("RCB_BINDING", os.path.join(HERE, "runtime_binding.json"))))
RIG_SPEC = json.load(open(os.environ.get("RCB_RIG", os.path.join(HERE, "rig.json"))))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "10800"))
LIVE_FPS = int(os.environ.get("RCB_LIVE_FPS", "10")); LIVE_CAM = os.environ.get("RCB_LIVE_CAMERA", "cam_high")
# /spec max_frames_per_call (cameras x frames; a frame with per-frame depth counts DEPTH_WEIGHT more). The recorder holds every frame
# of a call (848 x 480 RGB = 1.2 MB) and stacks and encodes them again: 1000 keeps one call near 3.7 GB at its peak,
# inside the sidecar's 8 GB cap (3000 could take the service past it: an OOM kill in the middle of a call).
MAX_FRAMES = 1000
# per-frame depth (depth="frames") is float32 here and float64 in the shared encoder (x 1000, rint): it costs about five
# RGB frames of memory, "legacy" (float16 per frame) about three; both count that much against MAX_FRAMES
DEPTH_WEIGHT = {"frames": 5, "legacy": 3}
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None,
     "service_s": 0.0, "t_first": None, "deadline": float("inf")}
JOBS: queue.Queue = queue.Queue()      # simulator work (physics, rendering), executed in order by the main thread
PID_FILE = os.path.join(DATA, "server.pid")
NU = int(BINDING["nu"])
EP = L.Episode(DATA, dim=NU, resume="exact", persist=("service_s",))
EP.startup()
log = EP.log


def on_main(fn, *a):
    """Run fn on the main thread (the owner of the EGL context) and return its result or raise its exception."""
    if threading.current_thread() is threading.main_thread():
        return fn(*a)
    done, box = threading.Event(), {}

    def job():
        try:
            box["r"] = fn(*a)
        except BaseException as exc:  # noqa: BLE001 — handed back to the HTTP thread
            box["e"] = exc
        finally:
            done.set()
    JOBS.put(job); done.wait()
    if "e" in box:
        raise box["e"]
    return box["r"]


# ---------------------------------------------------------------- scene (the frozen instance, checked against the binding)
import mujoco  # noqa: E402
import rcb_ikea as R  # noqa: E402
import ikea_rig  # noqa: E402

scene_dir = os.path.join(R.SCENES_ROOT, TASK)
files = R.scene_files(scene_dir)
instance_exact = files == BINDING["scene_files"]
s = R.Session(TASK)
init_sha = s.state_sha()
instance_ok = init_sha == BINDING["initial_state_sha256"] and s.nu == NU and s.actuators == BINDING["actuators"]
runtime = {"mujoco": mujoco.__version__, "numpy": np.__version__, "python": sys.version.split()[0]}
L._write_json(os.path.join(DATA, "startup_binding.json"), {
    "task": TASK, "instance_exact": instance_exact, "instance_ok": instance_ok, "initial_state_sha": init_sha,
    "scene_digest": R.digest(files), "runtime": runtime, "runtime_matches": runtime == BINDING["runtime"]})
if not (instance_exact and instance_ok and runtime == BINDING["runtime"]):
    # the sidecar's scene or runtime is not the one the task was validated on: infrastructure, never the agent's 0
    EP.scene_built()
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": False, "done": True, "finalized": True, "deterministic": False, "instance_mismatch": True, "infra_error": 1,
        "reason": "instance_mismatch", "task": TASK, "protocol": PROTOCOL, **EP.final_fields(),
        "differing_files": sorted(k for k in set(files) | set(BINDING["scene_files"]) if files.get(k) != BINDING["scene_files"].get(k))[:50]})
    open(PID_FILE, "w").write(str(os.getpid()))
    raise SystemExit(0)
EP.scene_built()
m, d = s.model, s.data
CTRL_DT = float(s.control_dt); CTRL_HZ = 1.0 / CTRL_DT
SNAP = mujoco.MjData(m)                 # status() evaluation snapshot (restored bit-exactly)
KD = mujoco.MjData(m)                   # /kinematics scratch data (never the live data)
RIG = ikea_rig.Rig(m, RIG_SPEC)
RIG.update(d); RIG.depth(RIG.names[0])   # build MuJoCo's EGL raster (depth) now: a host without EGL fails at start-up (infra),
                                         # not in the agent's first depth request (where it would read as a simulator error)
CAMS = list(RIG.names)
RENDER = os.environ.get("RCB_RENDER", "nyx")      # nyx: the agent's images; egl: MuJoCo's raster RGB (tests only)
if RENDER not in ("nyx", "egl"):
    raise SystemExit(f"RCB_RENDER must be nyx or egl, not {RENDER!r}")
NYX = None
if RENDER == "nyx":
    import tempfile
    import ikea_nyx  # noqa: E402
    NYX = ikea_nyx.NyxRig(m, RIG, RIG_SPEC, tempfile.mkdtemp(prefix="ikea_nyx_"), log_path=os.path.join(DATA, "nyx.log"))
    log({"ev": "nyx_ready", **NYX.startup})

# ---------------------------------------------------------------- the robot, from the model (two arms: left_, right_)
ARMS = ["left", "right"]
ACT = list(s.actuators)
# The arms' name separator, from the model: `left_` / `right_` in most scenes, `left/` / `right/` (MuJoCo Menagerie's
# attach prefixes) in some; every robot name below (actuators, joints, bodies, sites) uses the scene's own.
SEP = ACT[0][len("left")] if ACT and ACT[0].startswith("left") else "_"
assert SEP in "_/" and all(n.startswith(("left" + SEP, "right" + SEP)) for n in ACT), ("arm name prefixes", ACT)
ACT_LIM = []
for i in range(NU):
    lim = bool(m.actuator_ctrllimited[i]); lo, hi = m.actuator_ctrlrange[i]
    ACT_LIM.append([float(lo), float(hi)] if lim else None)
LO = np.array([l[0] if l else -np.inf for l in ACT_LIM]); HI = np.array([l[1] if l else np.inf for l in ACT_LIM])
GRIP = {}; ARM_JOINTS = {}; FINGERS = {}
for a in ARMS:
    idx = [i for i, n in enumerate(ACT) if n.startswith(a + SEP)]
    g = [i for i in idx if m.actuator_trntype[i] == mujoco.mjtTrn.mjTRN_TENDON or "gripper" in ACT[i]]
    assert len(g) == 1, (a, g)
    GRIP[a] = g[0]
    ARM_JOINTS[a] = [int(m.actuator_trnid[i, 0]) for i in idx if i != g[0]]
    FINGERS[a] = [j for j in range(m.njnt) if m.joint(j).name.startswith(a + SEP) and m.jnt_type[j] == mujoco.mjtJoint.mjJNT_SLIDE]
ARM_COLS = np.array([i for i in range(NU) if i not in GRIP.values()])
GRIP_COLS = [GRIP[a] for a in ARMS]
STEP_LIMIT = np.asarray(s.step_limit, dtype=np.float64)    # per actuator, per control step (inf: not limited); rcb_ikea's table
SPEED = STEP_LIMIT / CTRL_DT                               # per actuator, per second
LIM_COLS = np.flatnonzero(np.isfinite(STEP_LIMIT))         # the arm joints (+ any gripper the table limits)
assert set(ARM_COLS.tolist()) <= set(LIM_COLS.tolist()), "every arm joint has a speed limit"


def _limit_words() -> str:
    """The speed rule in words, from the table (the same for both arms)."""
    groups: dict = {}
    for c in LIM_COLS:
        if ACT[c].startswith("left" + SEP):
            groups.setdefault(float(SPEED[c]), []).append(ACT[c].split(SEP, 1)[1])
    unit = lambda c: "rad" if c in ARM_COLS else "units"  # noqa: E731
    parts = []
    for v, names in groups.items():
        c0 = ACT.index("left" + SEP + names[0])
        parts.append(f"{', '.join(names)}: at most {v * CTRL_DT:g} {unit(c0)} per control step ({v:g} {unit(c0)}/s)")
    return "; ".join(parts) + " (the same for both arms)"


SPEED_WORDS = _limit_words()
ROBOT_KIND = "viperx" if TASK == "svallet" else "panda"
GRIP_RULE = ("the gripper command slews at its limit from the row's first control step" if np.isfinite(STEP_LIMIT[GRIP_COLS]).all()
             else "the gripper switches at the row")
TCP = {a: f"{a}{SEP}tcp" if ROBOT_KIND == "panda" else f"{a}{SEP}gripper" for a in ARMS}
EE = {a: f"{a}{SEP}hand" if ROBOT_KIND == "panda" else f"{a}{SEP}gripper_link" for a in ARMS}
BASE = {a: f"{a}{SEP}link0" if ROBOT_KIND == "panda" else f"{a}{SEP}base_link" for a in ARMS}
JN = [m.joint(j).name for a in ARMS for j in ARM_JOINTS[a]]
QADR = np.array([m.jnt_qposadr[j] for a in ARMS for j in ARM_JOINTS[a]])
VADR = np.array([m.jnt_dofadr[j] for a in ARMS for j in ARM_JOINTS[a]])
JLIM = [[float(m.jnt_range[j, 0]), float(m.jnt_range[j, 1])] if m.jnt_limited[j] else None for a in ARMS for j in ARM_JOINTS[a]]
ROBOT_BODIES = [m.body(i).name for i in range(m.nbody) if m.body(i).name.startswith(("left" + SEP, "right" + SEP))]
LINKS = ROBOT_BODIES + [TCP[a] for a in ARMS]
SITE_ID = {TCP[a]: m.site(TCP[a]).id for a in ARMS}
NJ = len(JN)


def _quat(xmat) -> np.ndarray:
    q = np.zeros(4); mujoco.mju_mat2Quat(q, np.asarray(xmat, dtype=np.float64).reshape(9)); return q


def link_pose(dd, name) -> np.ndarray:
    """A link's (body or tcp site's) pose x y z qw qx qy qz in the MuJoCo world frame (internal)."""
    if name in SITE_ID:
        i = SITE_ID[name]; return np.concatenate([dd.site_xpos[i], _quat(dd.site_xmat[i])])
    b = m.body(name).id
    return np.concatenate([dd.xpos[b], dd.xquat[b]])


# ---------------------------------------------------------------- the robot frame (the agent's "world frame")
ROOT = BASE["left"]
_root = m.body(ROOT).id
assert int(m.body_parentid[_root]) == 0 and int(m.body_dofnum[_root]) == 0, "the left base link is fixed to the world"
T_WR = np.eye(4); T_WR[:3, :3] = np.asarray(d.xmat[_root]).reshape(3, 3); T_WR[:3, 3] = d.xpos[_root]   # robot -> world
assert abs(T_WR[2, 2] - 1.0) < 1e-9, "the left arm's base link must be upright (+z up)"
T_RW = np.eye(4); T_RW[:3, :3] = T_WR[:3, :3].T; T_RW[:3, 3] = -T_WR[:3, :3].T @ T_WR[:3, 3]         # world -> robot
Q_WR = _quat(T_WR[:3, :3]); Q_RW = Q_WR * np.array([1.0, -1.0, -1.0, -1.0])


def _moved(T, Q, pose) -> np.ndarray:
    p = np.asarray(pose, dtype=np.float64).reshape(7)
    q = np.zeros(4); mujoco.mju_mulQuat(q, Q, p[3:])
    return np.concatenate([T[:3, :3] @ p[:3] + T[:3, 3], q])


def to_robot(pose) -> np.ndarray:
    """A MuJoCo-world pose (x y z qw qx qy qz) -> the robot frame."""
    return _moved(T_RW, Q_RW, pose)


def to_world(pose) -> np.ndarray:
    """A robot-frame pose -> the MuJoCo world frame (IK on the model)."""
    return _moved(T_WR, Q_WR, pose)


def ext_to_robot(E34) -> np.ndarray:
    """extrinsic_cv world -> camera  becomes  robot -> camera."""
    Ex = np.eye(4); Ex[:3] = np.asarray(E34, dtype=np.float64)
    return (Ex @ T_WR)[:3]


def c2w_to_robot(T44) -> np.ndarray:
    """cam2world_gl camera -> world  becomes  camera -> robot."""
    return T_RW @ np.asarray(T44, dtype=np.float64)


def _kd_set(q) -> None:
    KD.qpos[:] = m.qpos0
    KD.qpos[QADR] = np.asarray(q, dtype=np.float64)
    mujoco.mj_kinematics(m, KD); mujoco.mj_comPos(m, KD)


# ---------------------------------------------------------------- spec
PROPRIO_LAYOUT = (list(JN) + [f"{n}_vel" for n in JN] + [f"{a}{SEP}gripper_opening_m" for a in ARMS]
                  + [f"{TCP[a]}_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"{n}_cmd" for n in ACT] + [f"{n}_effort" for n in ACT])
PROPRIO_GROUPS = {
    "joint_pos": [0, NJ, "measured arm joint positions (rad), left arm then right arm (kinematics.joint_names)"],
    "joint_vel": [NJ, NJ, "measured arm joint velocities (rad/s), same order"],
    "gripper_opening": [2 * NJ, 2, "measured opening of each gripper (m): the sum of its two finger joint positions"
                                   + (" (0 = closed, 0.08 = fully open)" if ROBOT_KIND == "panda" else " (finger rail travel)")
                                   + "; a gripper closed on something stops above 0"],
    "tcp_pose": [2 * NJ + 2, 14, f"measured tool-frame pose per arm (sites {TCP['left']}, {TCP['right']}: between the fingertips): "
                                 "x y z (m) + qw qx qy qz, world frame (spec world.frame; kinematics tcp_frames)"],
    "joint_cmd": [2 * NJ + 16, NU, "the actuator commands being applied (the joint_position layout: the last executed control "
                                   "step, clipped and speed-limited)"],
    "joint_effort": [2 * NJ + 16 + NU, NU, "the force of each actuator (N m for the arm joints; the gripper actuator's force): a "
                                           "motor-current analogue that rises when the arm pushes against something"],
}
assert len(PROPRIO_LAYOUT) == 2 * NJ + 16 + 2 * NU
WORLD_FRAME = (f"the world frame: origin at the left arm's base link ({ROOT}) on its mounting, +z up, x along that arm's "
               "forward direction; no positions of the scene are given; every pose, camera extrinsic and kinematics answer of "
               "this service is in it (robot_spec.base: the left base link is its origin, the right base's pose in it is the "
               "rig's fixed geometry)")
if ROBOT_KIND == "panda":
    GRIP_WORDS = ("Menagerie Panda hand, tendon-coupled fingers: command 0 = closed .. 255 = open (the hand squeezes at its "
                  "tendon force limit, about 70 N per finger, at any width when commanded 0)")
    ARM_WORDS = "7 joint position targets (rad) per arm (joint7 is not limited)"
else:
    GRIP_WORDS = "ViperX parallel gripper: finger rail position target, 0.002 m = closed .. 0.037 m = open"
    ARM_WORDS = "6 joint position targets (rad) per arm: waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate (not limited)"
TEXTS = json.load(open(os.path.join(HERE, "task_text.json")))
R_SPEC = {
    "name": "dual Franka Panda (MuJoCo Menagerie) with Panda hands" if ROBOT_KIND == "panda" else "dual ViperX 300 s (MuJoCo Menagerie ALOHA)",
    "arms": ARMS,
    "base": {a: {"link": BASE[a], "type": "fixed", "pose": [round(float(v), 6) for v in to_robot(link_pose(d, BASE[a]))],
                 "note": "x y z qw qx qy qz in the world frame (spec world.frame)"
                         + ("; the origin" if a == "left" else "; the rig's fixed geometry")} for a in ARMS},
    "joints": {a: [m.joint(j).name for j in ARM_JOINTS[a]] for a in ARMS},
    "grippers": {a: {"actuator": ACT[GRIP[a]], "command": GRIP_WORDS, "limits": ACT_LIM[GRIP[a]],
                     "finger_joints": [m.joint(j).name for j in FINGERS[a]]} for a in ARMS},
    "tcp": {a: {"site": TCP[a], "note": "between the fingertips; the proprio tcp_pose and the kinematics tcp frame"} for a in ARMS},
    "ee_link": {a: EE[a] for a in ARMS},
    "controller": {"type": "MuJoCo position actuators (the scene's own gains and force limits) tracking the commanded targets",
                   "speed_limit_per_s": {ACT[c]: float(SPEED[c]) for c in LIM_COLS},
                   "step_limit_per_control_step": {ACT[c]: float(STEP_LIMIT[c]) for c in LIM_COLS},
                   "speed_rule": f"each limited target moves {SPEED_WORDS}; clamp, not fail"},
}
K_SPEC = {"endpoint": "/kinematics", "joint_names": list(JN), "frame": "world", "quaternion_order": "wxyz", "links": LINKS,
          "tcp_frames": [TCP[a] for a in ARMS], "ee_frames": [EE[a] for a in ARMS], "ik_targets": [TCP[a] for a in ARMS],
          "joint_limits": {n: l for n, l in zip(JN, JLIM)},
          "ik": {"method": "damped least squares on the robot's MuJoCo model (no collision checking)", "tol_pos_m": 0.001,
                 "tol_rot_rad": 0.01, "max_iters": 200},
          "note": "stateless: computed on a scratch copy of the robot model; never moves the robot or advances time. q follows "
                  "joint_names (both arms); fk returns every link of `links` (bodies + the tcp sites); poses in the world "
                  "frame of spec world.frame"}


def _r(a, n=8) -> list:
    return [[round(float(v), n) for v in row] for row in np.asarray(a, dtype=np.float64)]


def mount_robot(c) -> dict:
    info = RIG.mount_info(c)
    if info["type"] == "static":
        info["extrinsic_cv"] = _r(ext_to_robot(info["extrinsic_cv"]))
        info["note"] = "world (spec world.frame) -> camera, OpenCV axes; the camera does not move"
    return info


CAM_SPEC = {}
RIG.update(d)
for c in CAMS:
    CAM_SPEC[c] = {"rgb": True, "depth": True, "mounted": "static" if RIG.mounts[c]["type"] == "static" else f"on the robot link {RIG.mounts[c]['body']}",
                   "resolution": [RIG.W, RIG.H], "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": RIG.intrinsic_cv(c),
                   "fovy_deg": RIG.fovy(c), "mount": mount_robot(c), "depth_range_m": [round(RIG.near, 4), round(RIG.far, 1)],
                   "rgb_renderer": ("Nyx path tracer (RoboARC's renderer and look: 32 samples per pixel, denoised, Reinhard tone "
                                    "mapping, SMAA, studio HDRI and point lights)" if NYX is not None else "MuJoCo raster (EGL)")}
SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "mujoco 3.14.0 (CPU, float64; the scene's own runtime and mechanism)",
    "robot": R_SPEC["name"], "task_text": TEXTS["task_text"],
    "control_hz": CTRL_HZ, "control_dt": CTRL_DT, "physics_substeps": int(R.SUBSTEPS), "physics_dt": float(s.timestep),
    "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "max_frames_per_call": MAX_FRAMES,
    "cameras": CAM_SPEC, "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {
            "dim": NU, "layout": ACT, "dtype": "float32 or float64 (rows are executed in float64; send float64 to replay a recorded "
                                               "float64 trajectory exactly)",
            "units": f"per arm (left{SEP}, then right{SEP}): {ARM_WORDS}; then the gripper command ({GRIP_WORDS})",
            "limits": {n: l for n, l in zip(ACT, ACT_LIM)},
            "step_limit_per_control_step": {ACT[c]: float(STEP_LIMIT[c]) for c in LIM_COLS},
            "semantics": (f"absolute actuator targets, one control step = {CTRL_DT * 1000:g} ms ({CTRL_HZ:g} Hz: the row is applied "
                          f"for {R.SUBSTEPS} physics steps of {s.timestep * 1000:g} ms). Rows are `dt` apart (a multiple of "
                          f"{CTRL_DT:g} s, at most 0.5 s), with `hold` (every control step of the row uses the row) or `linear` "
                          f"(default; the arm targets are interpolated from the previous row per control step; {GRIP_RULE}). "
                          "Out-of-limit values are clipped to the actuator's control range and reported in clipped[]; null "
                          f"limits are never clipped. Speed rule (the robot's real limits; clamp, not fail): {SPEED_WORDS}; a "
                          "row that asks for more takes the control steps it needs, and clipped[] says so. The position servos "
                          "track the targets.")},
        "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT, "proprio_groups": PROPRIO_GROUPS,
    "static": {},
    "world": {"frame": WORLD_FRAME, "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes "
                             "(x right, y up, z backward)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S,
               "clock": "time_s and elapsed_s count from your first request to the service; time_left_s is wall_clock_s minus "
                        "that, so it never runs out before the harness's limit does"},
    "episode": ("one episode, no reset. It ends at the first settled success (evaluated after every /submit and every /observe "
                "that watches: the task's success requirements AND the terminal rules: no robot link touches any part, every "
                f"part at rest (at most {R.REST_LIN_M_S:g} m/s and {R.REST_ANG_RAD_S:g} rad/s), no simulator breakdown so far; "
                f"then, on a copy, the last executed row held {R.SETTLE_S:g} s more and the same checked again: if that fails "
                "the episode goes on, meta settle_failed counts it), on a "
                "simulator breakdown (reason sim_breakdown, no success: a non-finite state, a MuJoCo BADQACC / BADQPOS / "
                f"BADQVEL warning, a part contact deeper than {R.BREAKDOWN_DEPTH_M * 1000:g} mm), when the wall-clock budget "
                "is used up (reason timeout; graded as it stands), or on a simulator error. The recorded control steps are "
                "then replayed from the initial state in fresh processes and graded: the same rules at the end of the rows "
                f"and again after the last row is held {R.SETTLE_S:g} s more"),
    "robot_spec": R_SPEC, "kinematics": K_SPEC,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE,
              "source": "MuJoCo's OpenGL depth buffer at the same camera and pixels as the RGB (the RGB is Nyx's; distance along the "
                        "optical axis)"},
}
L.check_spec(SPEC)


# ---------------------------------------------------------------- episode bookkeeping
def ctrl_steps() -> int:
    return len(s.rows)


def sim_time() -> float:
    return float(d.time)


def service_time() -> float:
    """Evidence only (not a budget): the wall time spent inside /submit and /observe, the call in progress included."""
    return float(E["service_s"]) + (time.time() - E["call_t0"] if E.get("call_t0") else 0.0)


def agent_time() -> float:
    """Seconds since the agent's first request to the service (0 before it): the agent's clock. The service is up before
    the agent starts (Harbor installs the agent first), so the service's own start is not that moment."""
    return 0.0 if E["t_first"] is None else time.time() - E["t_first"]


def time_left() -> float:
    return max(0.0, WALL_CLOCK_S - agent_time())


def write_final() -> None:
    if L.final_verdict(DATA):
        return
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": bool(E["success"]), "infra_error": int(E["reason"] == "error" and bool(E.get("error_infra"))),
        "sim_error": int(E["reason"] == "error" and not E.get("error_infra")),
        "dump_error": E.get("dump_error"), "steps": E["step"], "calls": E["calls"],
        "control_steps": ctrl_steps(), "physics_steps": ctrl_steps() * R.SUBSTEPS, "sim_time_s": sim_time(),
        "elapsed_s": round(agent_time(), 1), "service_time_s": round(service_time(), 1),
        "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": PROTOCOL,
        "finalized": False, "n_actions": E.get("n_actions"), "live_rows": E.get("live_rows"), "live_sha": E.get("live_sha"),
        "live_verdict": E.get("verdict"), **EP.final_fields()})


LIVE = {"w": None, "next": 0.0, "frames": 0, "path": None, "last": None}


def live_open() -> None:
    if LIVE_FPS <= 0 or LIVE_CAM not in CAMS:
        return
    try:
        import imageio.v2 as imageio
        n = EP.n_startups
        LIVE["path"] = os.path.join(DATA, "live.mp4" if n <= 1 else f"live.{n}.mp4")
        LIVE["w"] = imageio.get_writer(LIVE["path"], format="FFMPEG", mode="I", fps=LIVE_FPS, codec="libx264", macro_block_size=1,
                                       output_params=["-pix_fmt", "yuv420p"])
        LIVE["next"] = sim_time()
    except Exception:  # noqa: BLE001 — the live video is evidence only
        traceback.print_exc(); LIVE["w"] = None
        return
    live_tick()     # the start frame: every graded trial has a video, a trial with no step too (PROTOCOL §4)


def live_tick() -> None:
    if LIVE["w"] is None or sim_time() + 1e-9 < LIVE["next"]:
        return
    try:
        img = grab([LIVE_CAM], False)[0][LIVE_CAM]
        LIVE["w"].append_data(img); LIVE["frames"] += 1; LIVE["last"] = img
    except Exception:  # noqa: BLE001
        traceback.print_exc(); LIVE["w"] = None
    while LIVE["next"] <= sim_time() + 1e-9:
        LIVE["next"] += 1.0 / LIVE_FPS


def live_close() -> None:
    w, LIVE["w"] = LIVE["w"], None
    if w is not None:
        try:
            w.close()
            if LIVE["last"] is not None:
                from PIL import Image
                Image.fromarray(LIVE["last"]).save(os.path.join(DATA, "live.last.png"))
        except Exception:  # noqa: BLE001
            traceback.print_exc()


def dump() -> None:
    """The episode is over: save the recorded control rows and the live result for the collect hook (main thread)."""
    if E.get("dumped"):
        return
    E["dumped"] = True
    try:
        E["live_sha"] = s.state_sha(); E["n_actions"] = E["live_rows"] = ctrl_steps()
        rows = np.array(s.rows, dtype=np.float64).reshape(-1, NU)
        tmp = os.path.join(DATA, "trajectory.tmp.npz")
        np.savez_compressed(tmp, ctrl=rows, substeps=np.int64(R.SUBSTEPS), timestep=np.float64(s.timestep), actuators=np.array(ACT))
        os.replace(tmp, os.path.join(DATA, "trajectory.npz"))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)}); E["dump_error"] = repr(exc)[:300]
    # the verdict first, then the video (evidence only: a hung or failing encoder must not hold the verdict back)
    episode_json()
    write_final()
    t = threading.Thread(target=live_close, daemon=True)   # bounded: a hung encoder must not keep the service alive
    t.start(); t.join(float(os.environ.get("RCB_LIVE_CLOSE_S", "300")))
    episode_json()


def episode_json() -> None:
    L._write_json(os.path.join(DATA, "episode.json"), {
        "success": bool(E["success"]), "infra_error": int(E["reason"] == "error" and bool(E.get("error_infra"))),
        "sim_error": int(E["reason"] == "error" and not E.get("error_infra")),
        "dump_error": E.get("dump_error"), "steps": E["step"], "calls": E["calls"],
        "control_steps": ctrl_steps(), "physics_steps": ctrl_steps() * R.SUBSTEPS, "sim_time_s": sim_time(),
        "elapsed_s": round(((E.get("t_end") or time.time()) - E["t_first"]) if E["t_first"] else 0.0, 1),
        "service_time_s": round(service_time(), 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
        "n_actions": E.get("n_actions"), "live_rows": E.get("live_rows"), "live_sha": E.get("live_sha"), "live_verdict": E.get("verdict"),
        "live_video": LIVE["path"] and os.path.basename(LIVE["path"]), "live_video_frames": LIVE["frames"], **EP.final_fields()})


def verdict() -> dict:
    """rcb_ikea.Session.status() on the current state (the grader's terminal rules), side-effect free: the live data (and
    the mechanism's model fields) are restored bit-exactly afterwards (a success report may run physics on the live state,
    e.g. a support probe, and restore it itself)."""
    mujoco.mj_copyData(SNAP, m, d); eqd = m.eq_data.copy()
    try:
        st = s.status()
    finally:
        mujoco.mj_copyData(d, m, SNAP); m.eq_data[:] = eqd
    v = {k: st[k] for k in ("success", "goal", "released", "at_rest", "breakdown", "rows", "state_sha")}
    t = st.get("terminal") or {}
    v.update({k: t.get(k) for k in ("max_part_speed_m_s", "max_part_angular_rad_s", "fastest_part", "robot_part_contacts",
                                    "max_part_depth_mm")})
    E["verdict"] = v
    return v


def settled() -> dict:
    """rcb_ikea.Session.final_check() (status() now and after holding the last executed row SETTLE_S more) on the
    current state, side-effect free: final_check restores the session itself, and the live data and the mechanism's
    model fields are restored bit-exactly afterwards as in verdict()."""
    mujoco.mj_copyData(SNAP, m, d); eqd = m.eq_data.copy()
    try:
        fc = s.final_check()
    finally:
        mujoco.mj_copyData(d, m, SNAP); m.eq_data[:] = eqd
    st = fc["settled"]
    E["settled_verdict"] = {k: st[k] for k in ("success", "goal", "released", "at_rest", "breakdown")}
    return fc


def evaluate() -> bool:
    """After a call: end the episode at the first SETTLED success of the terminal rules (or at a breakdown). A success
    whose settled check fails does not end the episode."""
    if E["done"]:
        return bool(E["success"])
    v = verdict()
    if v["breakdown"] is not None:
        finish("sim_breakdown")
    elif v["success"]:
        if settled()["success"]:
            E["success"] = True
            finish("success")
        else:
            E["settle_failed"] = E.get("settle_failed", 0) + 1
            log({"ev": "settle_failed", "step": E["step"], "control_steps": ctrl_steps(), "settled": E["settled_verdict"]})
    return bool(E["success"])


def finish(reason: str) -> None:
    if E["done"]:
        return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    if not E["success"] and reason not in ("sim_breakdown", "error"):
        try:
            E["success"] = bool(verdict()["success"]) and bool(settled()["success"])   # graded as it stands (the verifier's replays decide)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    if reason in ("sim_breakdown", "error"):
        E["success"] = False
    log({"ev": "end", "reason": reason, "error_infra": bool(E.get("error_infra")), "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(agent_time(), 1),
         "service_time_s": round(service_time(), 1), "success": bool(E["success"]), "breakdown": s.validity.breakdown})
    dump()


def fail(exc: BaseException) -> None:
    """A simulator error in /submit or /observe ends the episode (reason "error"): infra_error if it is the service's
    (infra_exception), else sim_error (the agent's 0)."""
    if not E["done"]:
        E["error_infra"] = bool(infra_exception(exc))
    finish("error")


# ---------------------------------------------------------------- observation
def proprio_row() -> np.ndarray:
    tcp = [to_robot(link_pose(d, TCP[a])) for a in ARMS]
    grip = [float(sum(d.qpos[m.jnt_qposadr[j]] for j in FINGERS[a])) for a in ARMS]
    return np.concatenate([d.qpos[QADR], d.qvel[VADR], grip, *tcp, d.ctrl, d.actuator_force]).astype(np.float32)


def grab(cameras: list, want_depth: bool) -> tuple[dict, dict]:
    """RGB of `cameras` at the current state (Nyx, one request for all of them; a camera already drawn at this control
    step is reused), and MuJoCo's raster depth when asked."""
    RIG.update(d, key=(ctrl_steps(), E["calls"]))
    now = ctrl_steps()
    todo = [c for c in cameras if FRAME_CACHE.get(c, (None,))[0] != now]
    if todo:
        new = NYX.render(RIG.kd, todo) if NYX is not None else {c: RIG.rgb(c) for c in todo}
        for c, img in new.items():
            FRAME_CACHE[c] = (now, img)
    rgb = {c: FRAME_CACHE[c][1] for c in cameras}
    dep = {c: RIG.depth(c) for c in cameras} if want_depth else {}
    return rgb, dep


FRAME_CACHE: dict = {}                  # camera -> (control step, RGB)


def extrinsics(cameras: list) -> dict:
    RIG.update(d, key=(ctrl_steps(), E["calls"]))
    return {c: ext_to_robot(RIG.extrinsic_cv(c)) for c in cameras}


def calib(cameras: list) -> dict:
    RIG.update(d, key=(ctrl_steps(), E["calls"]))
    return {c: {"intrinsic_cv": RIG.intrinsic_cv(c), "extrinsic_cv": ext_to_robot(RIG.extrinsic_cv(c)).tolist(),
                "cam2world_gl": c2w_to_robot(RIG.cam2world_gl(c)).tolist(), "image_size": [RIG.W, RIG.H]} for c in cameras}


class Rec(L.Recorder):
    """The call's recorder, keeping the image budget while the call runs (a speed-limited row takes more control steps
    than asked, known only then): at the budget it takes no more frames -- the motion goes on, the last frame is always
    taken -- and meta["frames_skipped"] counts the frames left out."""
    skipped = 0

    def _capture(self, last: bool) -> None:
        per = len(self.cams) * (1 + DEPTH_WEIGHT.get(self.mode, 0))
        if not last and per * (len(self.steps) + 2) > MAX_FRAMES:
            self.skipped += 1
            return
        super()._capture(last)


def recorder(cams: list, fps: int, meta: dict) -> L.Recorder:
    return Rec(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
               depth=L.depth_mode(meta), clock_hz=CTRL_HZ, time_clock=sim_time, fps=fps)


def meta_common(cams) -> dict:
    return {"step": E["step"], "rows": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "sim_steps": ctrl_steps() * R.SUBSTEPS,
            "physics_steps": ctrl_steps() * R.SUBSTEPS, "sim_time_s": sim_time(), "time_s": round(agent_time(), 2),
            "time_left_s": round(time_left(), 1), "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()},
            "done": E["done"], "reason": E["reason"], "settle_failed": E.get("settle_failed", 0),
            **({"cameras": calib(cams)} if OBS_CALIBRATION else {})}


CALLS_KEPT = 200     # the last calls' evidence (meta + last frames) on the sidecar's disk; older ones are removed


def save_call_evidence(idx: int, meta: dict, rec: L.Recorder) -> None:
    root = os.path.join(DATA, "calls")
    for old in sorted(os.listdir(root))[:-CALLS_KEPT] if os.path.isdir(root) else []:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    dd = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(dd, exist_ok=True)
    json.dump(meta, open(os.path.join(dd, "meta.json"), "w"))
    try:
        from PIL import Image
        for c in rec.cams:
            if rec.frames[c] and rec.frames[c][-1] is not None:
                Image.fromarray(np.ascontiguousarray(rec.frames[c][-1])).save(os.path.join(dd, f"last_{c}.jpg"), quality=85)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- executing chunks
def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool | None:
    """One recorded control step (the row as executed: float64, clipped, speed-limited). True when the call must stop here
    (the episode ended: a breakdown; the call ran past max_call_wall_s or its client hung up: EP.journal)."""
    if EP.poll_stop():
        return None             # stopped before this step: nothing executed (the caller does not count it)
    row = np.asarray(a, dtype=np.float64)
    s.step(row)
    stop = EP.journal(row)
    if s.validity.breakdown is not None:
        finish("sim_breakdown")
        return True
    live_tick()
    rec.tick()
    return E["done"] or stop


def clip_rows(A: np.ndarray, clipped: list) -> tuple[np.ndarray, int]:
    bad = (A < LO) | (A > HI)
    n = int(bad.sum())
    if n:
        for ri, j in zip(*np.nonzero(bad)):
            if len(clipped) >= 200:
                break
            clipped.append({"row": int(ri), "index": int(j), "reason": f"{ACT[j]} limit [{LO[j]:g}, {HI[j]:g}]"})
    return np.clip(A, LO, HI), n


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> int:
    """Rows `dt` apart (`linear` interpolation of the arm targets or `hold`), under the speed rule: every limited target
    (the arm joints; a gripper only if the table limits it) moves at most STEP_LIMIT per control step from the previous control step's
    target, exactly as rcb_ikea.Session.applied() (only targets beyond limit + SPEED_TOL are moved, to prev +- limit), so
    the Session clamp leaves the executed rows unchanged. A row that asks for more takes the control steps it needs
    (reported in clipped[]), so every row is still reached. Returns the number of slowed rows."""
    steps_per_row = L.control_periods(dt, CTRL_HZ)
    q_prev = np.array(d.ctrl, dtype=np.float64)
    lim = STEP_LIMIT[LIM_COLS]; n_slow = 0
    for ri, target in enumerate(A):
        reach = np.abs(target[LIM_COLS] - q_prev[LIM_COLS])
        n = max(steps_per_row, int(math.ceil(float((reach / lim).max(initial=0.0)) - 1e-9)))
        slowed = False
        for k in range(1, n + 1):
            a = target.copy() if interp == "hold" or k >= steps_per_row else q_prev + (target - q_prev) * (k / steps_per_row)
            a[GRIP_COLS] = target[GRIP_COLS]                   # the gripper command is the row's (then limited, if it is)
            cmd = np.array(d.ctrl, dtype=np.float64)
            dd = a[LIM_COLS] - cmd[LIM_COLS]
            over = np.abs(dd) > lim + R.SPEED_TOL
            if over.any():
                cols = LIM_COLS[over]
                a[cols] = cmd[cols] + np.sign(dd[over]) * lim[over]
                slowed = True
            stop = ctrl_step(a, rec)
            if stop is None:                                   # nothing executed: the row is not counted
                return n_slow + int(slowed and k > 1)
            if k == 1:
                E["step"] += 1
            if stop:
                return n_slow + int(slowed)
        if slowed:
            n_slow += 1
            if len(clipped) < 200:
                w = int(np.argmax(reach / lim)); j = int(LIM_COLS[w])
                u = "rad" if j in ARM_COLS else "units"
                clipped.append({"row": ri, "index": j, "reason": (
                    f"speed: {ACT[j]} asked to move {float(reach[w]):.4f} {u} "
                    f"{'at once' if interp == 'hold' else f'in {steps_per_row} control step(s)'}; it moves at most "
                    f"{lim[w]:g} {u} per control step ({SPEED[j]:g} {u}/s), so this row took {n} control steps")})
        q_prev = target
    return n_slow


def _call(fn):
    """Service time (evidence only): the wall time spent inside /submit and /observe (main thread)."""
    def wrapped(*a):
        E["call_t0"] = t = time.time()
        try:
            return fn(*a)
        finally:
            E["service_s"] = float(E["service_s"]) + (time.time() - t); E["call_t0"] = None
    return wrapped


class EncodeError(OSError):
    """The response's video / frame encoding failed after the rows ran (imageio / ffmpeg): the service's own fault,
    infrastructure (infra_exception), never the agent's: the request was validated and its frames bounded."""


def encode_parts(rec, video: str, fps: int) -> list:
    try:
        return rec.parts(video, fps)
    except Exception as exc:  # noqa: BLE001
        raise EncodeError(f"response encoding failed: {exc!r}"[:300]) from exc


def req_cameras(meta: dict) -> list:
    """The request's cameras (a list of names; unknown names are dropped, none left = every camera). A malformed field is
    the caller's error, a 400 before anything executes (PROTOCOL §4.6), never a simulator error."""
    c = meta.get("cameras")
    if c is None:
        return list(CAMS)
    if not isinstance(c, list) or not all(isinstance(x, str) for x in c):
        raise ValueError("cameras must be a list of camera names")
    return [x for x in c if x in CAMS] or list(CAMS)


def req_note(meta: dict) -> str:
    n = meta.get("note")
    if n is not None and not isinstance(n, str):
        raise ValueError("note must be a string")
    return (n or "")[:500]


def infra_exception(exc: BaseException) -> bool:
    """Which errors in /submit or /observe are the service's infrastructure (reason "error", infra_error): the render
    process (ikea_nyx.RenderError), the host (OSError: disk, pipes; MemoryError). Everything else raised while the agent's
    rows run (the scene's code, MuJoCo) is a simulator error the rows caused (sim_error 1: the agent's 0,
    STANDARD_MODE.md "500"), so an agent cannot void a failed episode by breaking the simulator. Both end the episode
    with reason "error"."""
    render = getattr(sys.modules.get("ikea_nyx"), "RenderError", ())
    return isinstance(exc, (OSError, MemoryError) + ((render,) if render else ()))


def _frames(cams, fps, seconds, depth_mode) -> int:
    return int(len(cams) * (math.ceil(seconds * fps) + 2) * (1 + DEPTH_WEIGHT.get(depth_mode, 0)))


@_call
def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    if E["done"]:               # the episode ended (the deadline) between the request's admission and this job
        raise ValueError("episode finished")
    typ = meta.get("type"); interp = meta.get("interpolate", "linear")
    note = req_note(meta)
    try:
        dt = float(meta.get("dt", CTRL_DT))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("dt must be a number")
    cams = req_cameras(meta)
    fps = meta.get("video_fps", 10); video = meta.get("video", "mp4")
    if typ != "joint_position":
        raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
    if A.ndim != 2 or A.shape[1] != NU or A.shape[0] < 1:
        raise ValueError(f"joint_position actions must be (T, {NU}) with T >= 1, got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    k = L.control_periods(dt, CTRL_HZ)
    if A.shape[0] * k * CTRL_DT > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    if not isinstance(fps, (int, float)) or not 1 <= fps <= 30:
        raise ValueError("video_fps must be in [1, 30]")
    fps = int(fps); depth = L.depth_mode(meta)
    if _frames(cams, fps, A.shape[0] * k * CTRL_DT, depth) > MAX_FRAMES:
        raise ValueError(f"more than {MAX_FRAMES} frames in one response (cameras x (fps x seconds + 2); a frame with per-frame depth counts 6, legacy depth 4)")
    try:   # executing: a ValueError from here on is the simulator's (a 400 would hide it), never the request's
        rec = recorder(cams, fps, meta); clipped: list = []
        E["calls"] += 1; step0 = E["step"]; before = ctrl_steps()
        A, n_clipped = clip_rows(np.asarray(A, dtype=np.float64), clipped)
        rec.tick(force=True)
        n_slow = run_joint_position(A, dt, interp, rec, clipped)
        rec.tick(force=True, last=True)
        succ = evaluate()
        out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0,
               "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * R.SUBSTEPS,
               "clipped": clipped, "n_clipped": n_clipped + n_slow, "n_speed_limited_rows": n_slow, "plan": [], "rejected": None,
               "ok": True, "settle_failed": E.get("settle_failed", 0), **({"frames_skipped": rec.skipped} if rec.skipped else {})}
        log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams,
             "note": note, "control_steps": ctrl_steps() - before, "n_clipped": n_clipped, "n_slow": n_slow,
             "success": succ, "verdict": E.get("verdict")})
        save_call_evidence(E["calls"], {k_: v for k_, v in out.items() if k_ != "cameras"}, rec)
    except ValueError as exc:
        raise RuntimeError(f"simulator error: {exc}") from exc
    return out, encode_parts(rec, video, fps)


@_call
def do_observe(meta: dict) -> tuple[dict, list]:
    cams = req_cameras(meta)
    try:
        seconds = float(meta.get("seconds", 0))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("seconds must be a number")
    fps = meta.get("video_fps", 10); video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    if not isinstance(fps, (int, float)) or not 1 <= fps <= 30:
        raise ValueError("video_fps must be in [1, 30]")
    fps = int(fps); depth = L.depth_mode(meta)
    if _frames(cams, fps, seconds, depth) > MAX_FRAMES:
        raise ValueError(f"more than {MAX_FRAMES} frames in one response (cameras x (fps x seconds + 2); a frame with per-frame depth counts 6, legacy depth 4)")
    try:   # executing: a ValueError from here on is the simulator's (a 400 would hide it), never the request's
        rec = recorder(cams, fps, meta); before = ctrl_steps()
        watch = seconds > 0 and not E["done"]
        rec.tick(force=True, last=not watch)
        if watch:
            hold = np.array(d.ctrl, dtype=np.float64)
            for _ in range(int(round(seconds * CTRL_HZ))):
                r = ctrl_step(hold, rec)
                if r or r is None:
                    break
            rec.tick(force=True, last=True)
            evaluate()
        E["calls"] += 1
        out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
               "physics_steps_watch": (ctrl_steps() - before) * R.SUBSTEPS, "ok": True}
        log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before})
        if seconds > 0:
            save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    except ValueError as exc:
        raise RuntimeError(f"simulator error: {exc}") from exc
    return out, encode_parts(rec, video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


# ---------------------------------------------------------------- /kinematics (stateless, scratch data, robot frame)
def _arm_cols(arm) -> list:
    off = 0 if arm == "left" else len(ARM_JOINTS["left"])
    return list(range(off, off + len(ARM_JOINTS[arm])))


def do_kinematics(req: dict) -> dict:
    if req["op"] == "fk":
        _kd_set(req["q"])
        return L.fk_response({k: to_robot(link_pose(KD, k)) for k in req["links"]}, "world")
    q = np.array(req["seed"] if req["seed"] is not None else d.qpos[QADR], dtype=np.float64)
    lo = np.array([l[0] if l else -np.inf for l in JLIM]); hi = np.array([l[1] if l else np.inf for l in JLIM])
    tg = {f: to_world(p) for f, p in req["targets"].items()}       # the request is in the robot frame
    for _ in range(int(req["max_iters"])):
        _kd_set(q); done = True
        for frame, pose in tg.items():
            arm = "left" if frame == TCP["left"] else "right"
            cur = link_pose(KD, frame)
            ep = np.asarray(pose[:3]) - cur[:3]
            qe = np.zeros(4); qc = np.zeros(4); mujoco.mju_negQuat(qc, cur[3:]); mujoco.mju_mulQuat(qe, np.asarray(pose[3:]), qc)
            er = np.zeros(3); mujoco.mju_quat2Vel(er, qe, 1.0)
            if float(np.linalg.norm(ep)) <= req["tol_pos_m"] and float(np.linalg.norm(er)) <= req["tol_rot_rad"]:
                continue
            done = False
            jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv)); mujoco.mj_jacSite(m, KD, jp, jr, SITE_ID[frame])
            cols = _arm_cols(arm); J = np.vstack([jp, jr])[:, VADR[cols]]
            e = np.concatenate([ep, er])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
            q[cols] = np.clip(q[cols] + dq, lo[cols], hi[cols])
        if done:
            break
    _kd_set(q)
    errs = {}
    for frame, pose in tg.items():
        cur = link_pose(KD, frame)
        qe = np.zeros(4); qc = np.zeros(4); mujoco.mju_negQuat(qc, cur[3:]); mujoco.mju_mulQuat(qe, np.asarray(pose[3:]), qc)
        er = np.zeros(3); mujoco.mju_quat2Vel(er, qe, 1.0)
        errs[frame] = (float(np.linalg.norm(np.asarray(pose[:3]) - cur[:3])), float(np.linalg.norm(er)))
    ok = all(e[0] <= req["tol_pos_m"] and e[1] <= req["tol_rot_rad"] for e in errs.values())
    return L.ik_response(q, ok, errs, "world")


def status() -> dict:
    return {"step": E["step"], "rows": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "sim_steps": ctrl_steps() * R.SUBSTEPS,
            "physics_steps": ctrl_steps() * R.SUBSTEPS, "done": E["done"], "reason": E["reason"], "settle_failed": E.get("settle_failed", 0),
            "elapsed_s": round(agent_time(), 1), "time_left_s": round(time_left(), 1)}


# ---------------------------------------------------------------- the agent's clock (from its first request)
def start_clock(t_first: float) -> None:
    E["t_first"] = t_first
    E["deadline"] = time.monotonic() + WALL_CLOCK_S - (time.time() - t_first)


def touch() -> None:
    """Every HTTP request passes here (any endpoint; a port probe that only connects does not): the first one starts the
    agent's clock and is logged in episode.jsonl, so that a resumed service keeps it (never back to full)."""
    if E["t_first"] is None:
        t = time.time()
        start_clock(t)
        log({"ev": "first_request", "t_first": t})


_make_handler = L.make_handler


def _touching_handler(svc):
    """rcb_limited's handler with touch() before every request (L.serve builds its handler with L.make_handler)."""
    base = _make_handler(svc)

    class Handler(base):
        def do_GET(self):
            touch()
            return base.do_GET(self)

        def do_POST(self):
            touch()
            return base.do_POST(self)
    return Handler


L.make_handler = _touching_handler


def deadline_reached() -> bool:
    return E["ready"] and not E["done"] and time.monotonic() >= E["deadline"]


def end_from_signal() -> None:
    JOBS.put(_end_and_exit)


def _end_and_exit() -> None:
    E["exiting"] = True
    if not E["done"]:
        finish("timeout")
    else:
        dump()
    log({"ev": "exit", "reason": "collect hook: episode dumped"})
    if not os.path.exists(PID_FILE):
        open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)


def replay_row(row) -> None:
    s.step(np.asarray(row, dtype=np.float64))


# ---------------------------------------------------------------- start, or resume after a crash
resumed = EP.begin(state=E, step=replay_row, state_sha=s.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
                   start_event={"task": TASK, "initial_state_sha": init_sha})
if E.get("done") and E.get("reason") == "error":   # a resumed, ended episode keeps its error's class (infra or sim)
    _ends = [e for e in EP.events() if e.get("ev") == "end"]
    E["error_infra"] = bool(_ends and _ends[-1].get("error_infra"))
_first = [e for e in EP.events() if e.get("ev") == "first_request"]
if _first:                              # a resumed service: the agent's clock keeps running from its first request
    start_clock(float(_first[0]["t_first"]))
E["ready"] = True
live_open()
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} IKEA MuJoCo sim ready: task {TASK}, startup {EP.n_startups}, resumes {EP.resumes}, rows {ctrl_steps()}", flush=True)
threading.Thread(target=L.serve, daemon=True, args=(L.Service(
    spec=SPEC, lock=LOCK, state=E, submit=lambda meta, A: on_main(do_submit, meta, A), observe=lambda meta: on_main(do_observe, meta),
    kinematics=lambda req: on_main(do_kinematics, req), status=status, on_submit_error=lambda exc: on_main(fail, exc), log=log,
    episode=EP, state_sha=lambda: on_main(s.state_sha), proprio=lambda: on_main(proprio_row)),)).start()
while True:
    if deadline_reached():                      # between simulator jobs: never inside a call
        finish("timeout")
    try:
        job = JOBS.get(timeout=0.5)
    except queue.Empty:
        continue
    job()
