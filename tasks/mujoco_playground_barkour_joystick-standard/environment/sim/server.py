"""eai-standard/2.2 sim service for MuJoCo Playground's quadruped tasks (docs/STANDARD_MODE.md): the adapter of the
shared layer rcb_limited.py; the simulator is rcb_quadruped.Session (plain MuJoCo on the CPU).
HTTP surface: GET /spec, GET /status, POST /observe, POST /submit, POST /kinematics, and POST /reset when the run grants
resets (RCB_RESET_BUDGET, the optional reset capability of docs/STANDARD_MODE.md / PROTOCOL §4.5; the quadrupeds'
standard tasks default to 10 in their compose file, owner 2026-10-14). Every call is logged to /data/episode.jsonl.

The episode is the frozen instance's: one control step = the instance's control period (Go1, Spot: 1/50 s; Barkour:
1/100 s). A joystick episode ends after the whole command schedule
(the horizon), when the robot meets Playground's termination rule (it falls over: a failure), when the agent submits
`done`, or when its time is over; success = the task's check on the steps executed. A getup episode ends the moment the
check holds (success), after the horizon, on `done` or on timeout. With a reset budget, POST /reset abandons the running
(or ended) episode and starts a new one from the frozen instance; only the last episode is graded, and a success ends
the trial.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal, resetting where
the committed resets did (their journal rows are checkpointed, `persist`). When the
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
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.json"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
RESET_BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET") or 0))  # the compose file's default: 10 (PROTOCOL §4.5)
CAM_W, CAM_H = 320, 240
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None,
     "t_first": None,   # t_first: the agent's first call (its clock starts there; kept through a crash by the checkpoints)
     "resets": 0,       # resets done (the episode is resets + 1)
     "reset_at": []}    # the journal row at which each reset happened: a resume resets there again

os.environ["RCB_SESSION_LOG"] = ""
os.environ["RCB_AGENT_TRACE_DIR"] = ""
import rcb_quadruped as Q  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

EP = L.Episode(DATA, dim=Q.N, resume="exact", persist=("t_first", "resets", "reset_at"))
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = Q.Session(INSTANCE)
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
DT = S.control_dt   # one control step of simulated time (Barkour: 10 ms, as Playground steps it)
CTRL_HZ = 1.0 / DT
SUBSTEPS = S.substeps
M = S.model
CAMS = list(S.cameras)
FEET = S.robot["feet"]
LIMITS = np.stack([S.lower, S.upper], axis=1)
GROUPS = [
    ("joint_pos", S.joint_names, "measured joint positions (rad), in the action's order"),
    ("joint_vel", [f"{j}_vel" for j in S.joint_names], "measured joint velocities (rad/s)"),
    ("joint_effort", [f"{j}_effort" for j in S.joint_names], "actuator torques of those joints (N m)"),
    ("gripper_opening", [], "none (no gripper)"),
    ("tcp_pose", [], "none (no gripper)"),
    ("imu_gyro", ["gyro_x", "gyro_y", "gyro_z"], "angular velocity of the trunk, IMU frame (rad/s)"),
    ("imu_accelerometer", ["acc_x", "acc_y", "acc_z"], "specific force at the IMU, IMU frame (m/s^2; +9.81 up at rest)"),
    ("imu_gravity", ["gravity_x", "gravity_y", "gravity_z"], "unit vector of gravity's direction in the IMU frame "
                                                             "([0, 0, -1] when the trunk is level)"),
    ("imu_linvel", ["linvel_x", "linvel_y", "linvel_z"], "linear velocity of the trunk at the IMU, IMU frame (m/s; the "
                                                         "IMU's velocimeter, what a state estimator gives)"),
    ("foot_contact", [f"{f}_contact" for f in FEET], "1 when the foot touches the ground, else 0"),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)


# ------------------------------------------------------------------------------------------------- cameras
def _intrinsic(cam: str) -> list:
    fovy = math.radians(float(M.cam_fovy[M.camera(cam).id]))
    f = 0.5 * CAM_H / math.tan(fovy / 2)
    return [[f, 0.0, CAM_W / 2], [0.0, f, CAM_H / 2], [0.0, 0.0, 1.0]]


def camera_info(cam: str) -> dict:
    """World -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
    i = M.camera(cam).id
    R_gl = S.data.cam_xmat[i].reshape(3, 3)          # camera axes (OpenGL: x right, y up, z back) in the world
    p = S.data.cam_xpos[i].copy()
    R_cv = R_gl @ np.diag([1.0, -1.0, -1.0])
    ext = np.zeros((3, 4))
    ext[:, :3] = R_cv.T
    ext[:, 3] = -R_cv.T @ p
    c2w = np.eye(4)
    c2w[:3, :3] = R_gl
    c2w[:3, 3] = p
    return {"intrinsic_cv": _intrinsic(cam), "extrinsic_cv": ext.tolist(), "cam2world_gl": c2w.tolist(),
            "image_size": [CAM_W, CAM_H]}


# ------------------------------------------------------------------------------------------------- kinematics
KD = mujoco.MjData(M)        # kinematics only: the trunk at the origin, level; never stepped
_FOOT = {f: M.site(f).id for f in FEET}
_LEG_DOF = {f: [6 + 3 * k + j for j in range(3)] for k, f in enumerate(FEET)}   # actuator order = leg order = FEET


def _fk_kd(q) -> None:
    KD.qpos[:] = 0.0
    KD.qpos[3] = 1.0
    KD.qpos[7:] = q
    mujoco.mj_kinematics(M, KD)


def _foot_pose(f: str) -> list:
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, KD.site_xmat[_FOOT[f]])
    return [*KD.site_xpos[_FOOT[f]].tolist(), *quat.tolist()]


def do_kinematics(req: dict) -> dict:
    """Feet in the trunk frame (the trunk body's origin and axes; x forward, y left, z up). IK solves positions only, one
    leg (3 joints) per foot target, damped least squares within the joint ranges; a foot's orientation is ignored."""
    _touch()
    if req["op"] == "fk":
        _fk_kd(np.asarray(req["q"]))
        return L.fk_response({f: _foot_pose(f) for f in req["links"]}, "trunk")
    q = np.array(req["seed"] if req["seed"] is not None else S.data.qpos[7:], dtype=np.float64)
    errors = {}
    jac = np.zeros((3, M.nv))
    for f, pose in req["targets"].items():
        tgt = np.asarray(pose[:3])
        idx = _LEG_DOF[f]
        for _ in range(req["max_iters"]):
            _fk_kd(q)
            err = tgt - KD.site_xpos[_FOOT[f]]
            if np.linalg.norm(err) < req["tol_pos_m"]:
                break
            mujoco.mj_jacSite(M, KD, jac, None, _FOOT[f])
            J = jac[:, idx]
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(3), err)
            q[[i - 6 for i in idx]] = np.clip(q[[i - 6 for i in idx]] + dq, S.lower[[i - 6 for i in idx]],
                                              S.upper[[i - 6 for i in idx]])
        _fk_kd(q)
        errors[f] = (float(np.linalg.norm(tgt - KD.site_xpos[_FOOT[f]])), 0.0)
    ok = all(e[0] <= req["tol_pos_m"] for e in errors.values())
    return L.ik_response(q, ok, errors, "trunk", note="feet: position only (a foot is a sphere; its orientation is ignored)")


# ------------------------------------------------------------------------------------------------- spec
def schedule_text() -> list:
    if S.commands is None:
        return []
    return [{"from_s": round(int(c["start_step"]) * DT, 2), "vx_mps": round(c["vx"], 4), "vy_mps": round(c["vy"], 4),
             "wz_radps": round(c["wz"], 4)} for c in S.inst["commands"]]


ONE = "one episode, no reset" if not RESET_BUDGET else (
    f"an episode (with up to {RESET_BUDGET} resets: POST /reset starts a new one; only the last is graded)")
TASK_EPISODE = {
    "joystick": f"{ONE}: it ends after {S.horizon} control steps (the {S.horizon * DT:g} s command "
                f"schedule), when the robot meets its termination rule ({S.spec.get('term_text')}: a failure), when you "
                "submit `done`, or when your time is over",
    "getup": f"{ONE}: it ends the moment the robot has stood upright for {Q.HOLD_STEPS} control steps in a "
             f"row (success), after {S.horizon} control steps, when you submit `done`, or when your time is over",
    "stand_on_two": f"{ONE}: it ends the moment the pose has been held for {Q.POSE_HOLD_STEPS} control steps "
                    "in a row (success), when the robot meets the termination rule (a failure: its trunk's up axis below "
                    f"-0.25, or {'a leg' if S.spec.get('hind_leg_contact') else 'a front leg'}'s thigh, calf or hip on the "
                    f"floor), after {S.horizon} control steps, when you "
                    "submit `done`, or when your time is over",
}[S.kind]
_ctl = {"type": "joint position actuators (PD)", "kp_nm_per_rad": float(M.actuator_gainprm[0, 0]),
        "kd_nms_per_rad": float(M.dof_damping[6] - M.actuator_biasprm[0, 2])}
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "MuJoCo 3.3.7 (MuJoCo Playground's scene, plain MuJoCo on the CPU)",
    "robot": S.robot["name"],
    "task_text": S.inst["text"],
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "resolution": [CAM_W, CAM_H], "intrinsic_cv": _intrinsic(c),
                    **({"mounted": "follows the robot", "mount": {"type": "link", "link": S.robot["root"], "note":
                        "follows the robot's centre of mass at a fixed offset; it does not turn with the robot"}}
                       if int(M.cam_mode[M.camera(c).id]) != 0 else
                       {"mounted": "on the robot's head", "mount": {"type": "link", "link": M.body(M.cam_bodyid[M.camera(c).id]).name
                        or S.robot["root"], "note": "fixed to the robot: moves and turns with it"}})}
                for c in CAMS},
    "default_cameras": ["track"],
    "action_types": {
        "joint_position": {
            "dim": Q.N,
            "layout": S.joint_names,
            "limits": dict(zip(S.joint_names, LIMITS.tolist())),
            "units": "rad",
            "semantics": f"absolute targets of the 12 joint position actuators, one per control step ({DT:g} s); rows `dt` "
                         "apart (a multiple of the control period, at most 0.5 s), `hold` or `linear` between rows; values "
                         "outside the limits are clipped and reported",
        },
        "done": {"dim": 0, "layout": [], "semantics": 'ends the episode now, in the current state (no physics); r.submit("done", [])'},
        "not_yet": ["joint_velocity", "joint_torque", "joint_delta"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},
    "world": {"frame": "z up; the robot starts where the episode puts it (no world coordinates are given)", "up": "+z",
              "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes"},
    "budget": {"reset": RESET_BUDGET, "steps": None, "wall_clock_s": WALL_CLOCK_S},   # + "clock" (rcb_limited.CLOCK_NOTE): what time_left_s counts from
    "max_control_steps": S.horizon,
    "episode": TASK_EPISODE,
    "command_schedule": schedule_text(),
    **({"gait": {k: S.gait[k] for k in ("name", "frequency_hz", "foot_height_m", "phase0", "phase_dt")} | {
        "feet": FEET, "rule": "foot i's target height at control step t is get_rz(wrap(phase0[i] + t * phase_dt)) with "
        "Playground's gait.get_rz (a cubic Bezier from 0 up to foot_height_m over the first half of the phase, then "
        "down); phases in rad, wrapped to [-pi, pi)"}} if S.gait else {}),
    "robot_spec": {"name": S.robot["name"], "joints": S.joint_names, "joint_limits": dict(zip(S.joint_names, LIMITS.tolist())),
                   "joint_order": S.robot["joint_text"], "home_pose": dict(zip(S.joint_names, S.home.tolist())),
                   "feet": FEET, "controller": _ctl},
    "kinematics": {"endpoint": "/kinematics", "joint_names": S.joint_names, "frame": "trunk", "quaternion_order": "wxyz",
                   "links": FEET, "tcp_frames": [], "ee_frames": FEET, "ik_targets": FEET,
                   "ik": {"tol_pos_m": 0.002, "tol_rot_rad": 3.2, "max_iters": 100},
                   "note": "poses of the feet in the trunk frame (x forward, y left, z up, metres) for joint positions q; "
                           "ik: one leg per foot, positions only"},
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

_RENDER = {}


def _renderer():
    if "r" not in _RENDER:
        _RENDER["r"] = mujoco.Renderer(M, CAM_H, CAM_W)
    return _RENDER["r"]


def ctrl_steps() -> int:
    return S.steps


def proprio_row() -> np.ndarray:
    d = S.data
    return np.concatenate([d.qpos[7:], d.qvel[6:], d.actuator_force, S.sensor("gyro"), S.sensor("accelerometer"), S.gravity(),
                           S.sensor("local_linvel"), S.foot_contacts()]).astype(np.float32)


def grab(cams, want_depth: bool):
    r = _renderer()
    rgb, dep = {}, {}
    for c in cams:
        r.update_scene(S.data, camera=c)
        rgb[c] = r.render().copy()
        if want_depth:
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
    chk = E.get("check") or {}
    return {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n,
            "physics_steps": n * SUBSTEPS, "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
            "reason": E["reason"], "done": E["done"], "env": S.env, "protocol": L.PROTOCOL, "n_actions": len(ROWS),
            "fell_at": chk.get("fell_at"), "worst_lin_err": chk.get("worst_lin_err"), "worst_yaw_err": chk.get("worst_yaw_err"),
            "tilt_deg": chk.get("tilt_deg"), "imu_height": chk.get("imu_height"), "pose_angle_deg": chk.get("pose_angle_deg"),
            "episodes": E["resets"] + 1, "resets": E["resets"], "reset_budget": RESET_BUDGET, "control_steps_total": EP.rows,
            **EP.final_fields()}


def finish(reason: str) -> None:
    """The episode is over: the task's check on the steps executed, then the record for the collect hook."""
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    E["episode_control_steps"] = ctrl_steps()
    try:
        chk = S.check()
        E["check"] = {k: v for k, v in chk.items() if k != "segments"}
        E["success"] = bool(chk["success"])
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    EP.log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"]),
            "episode": E["resets"] + 1, "journal_rows": EP.rows})
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    np.savez(os.path.join(DATA, "trajectory.npz"), actions=np.asarray(ROWS, dtype=np.float64).reshape(-1, Q.N),
             env=S.env, action_layout=",".join(S.joint_names))
    L._write_json(os.path.join(DATA, "episode.json"), {**summary(), "live_sha": E["live_sha"]})
    write_final()


def after_step() -> None:
    if S.kind in ("joystick", "stand_on_two") and S.fell_at is not None:
        finish("fell")
    elif S.kind in ("getup", "stand_on_two") and S.check()["success"]:
        finish("success")
    elif S.done:
        finish("horizon")


def ctrl_step(a, rec) -> bool:
    """One executed control step, journaled. True when the call must stop here."""
    S.step(a)
    ROWS.append(np.asarray(a, dtype=np.float64))
    stop = EP.journal(a)
    rec.tick()
    after_step()
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
    cams = meta.get("cameras") or ["track"]
    if not isinstance(cams, (list, tuple)) or not all(isinstance(c, str) for c in cams):
        raise ValueError(f"cameras must be a list of camera names: {CAMS}")
    bad = [c for c in cams if c not in CAMS]
    if bad:
        raise ValueError(f"unknown cameras {bad}; cameras: {CAMS}")
    return list(cams)


def _touch() -> None:
    """Every call passes here: the first one starts the agent's clock. The simulator is up before the agent starts (the
    harness installs the agent first), so the service's own start is not that moment."""
    if E.get("t_first") is None:
        E["t_first"] = time.time()


def _agent_time() -> float:
    return 0.0 if E.get("t_first") is None else time.time() - float(E["t_first"])


def _num(meta: dict, key: str, default: float) -> float:
    """A finite numeric request field; anything else (null, a string, NaN, Infinity) is the caller's mistake: a 400
    before any physics, never a simulator error."""
    try:
        v = float(meta.get(key, default))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be a number") from None
    if not math.isfinite(v):
        raise ValueError(f"{key} must be a finite number")
    return v


def _request(meta) -> dict:
    if not isinstance(meta, dict):
        raise ValueError("the request's meta must be a JSON object")
    _touch()
    return meta


def meta_common(cams) -> dict:
    n = ctrl_steps()
    out = {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
           "sim_time_s": round(n * DT, 3), "time_s": round(_agent_time(), 2),
           "time_left_s": max(0.0, round(WALL_CLOCK_S - _agent_time(), 1)),
           "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
           "cameras": {c: camera_info(c) for c in cams}, **reset_counters()}
    if S.kind == "joystick":
        out["command_now"] = dict(zip(("vx_mps", "vy_mps", "wz_radps"), S.command_now().round(4).tolist()))
    return out


def do_submit(meta: dict, A: np.ndarray):
    meta = _request(meta)
    typ = meta.get("type")
    if typ == "done":
        rec = recorder(cameras_of(meta), 5, meta)
        rec.tick(force=True, last=True)  # every response carries the last frames
        E["calls"] += 1
        finish("done")
        return {**meta_common(cameras_of(meta)), "chunk_id": E["calls"], "type": typ, "executed_rows": 0, "ok": True}, rec.parts("none", 5)
    if typ != "joint_position":
        raise ValueError(f"type must be joint_position or done (not yet: {SPEC['action_types']['not_yet']})")
    dt = _num(meta, "dt", DT)
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps = cameras_of(meta), video_fps(meta)
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != Q.N:
        raise ValueError(f"joint_position actions must be (T, {Q.N}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (math.isfinite(dt) and 0 < dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
        raise ValueError(f"dt must be a whole multiple of the {DT:g} s control period and at most 0.5 s; got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    note = str(meta.get("note") or "")[:500]     # read before any physics: a note of any type is not an error
    rec, clipped = recorder(cams, fps, meta), []
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    prev = S.targets.copy()
    for ri, row in enumerate(A):
        E["step"] += 1
        target = np.clip(row, LIMITS[:, 0], LIMITS[:, 1])
        for j in np.flatnonzero(target != row)[:20]:
            clipped.append({"row": ri, "index": int(j), "reason": f"{S.joint_names[j]} limit [{LIMITS[j, 0]:g}, {LIMITS[j, 1]:g}]"})
        n = int(round(k))
        stop = False
        for s in range(1, n + 1):
            a = target if interp == "hold" else prev + (target - prev) * (s / n)
            if ctrl_step(a, rec):
                stop = True
                break
        prev = target
        if stop:
            break
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0,
           "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
           "clipped": clipped[:200], "n_clipped": len(clipped), "plan": [], "ok": True}
    EP.log({"ev": "submit", "call": E["calls"], "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams,
            "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "note": note,
            **({"stopped": EP.stop_reason} if EP.stopping else {})})
    return out, rec.parts(video, fps)


def do_observe(meta: dict):
    meta = _request(meta)
    cams, fps = cameras_of(meta), video_fps(meta)
    seconds = _num(meta, "seconds", 0)
    video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec, before = recorder(cams, fps, meta), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = S.targets.copy()
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


def reset_counters() -> dict:
    if not RESET_BUDGET:
        return {}
    left = 0 if (E["success"] or E.get("exiting")) else RESET_BUDGET - E["resets"]
    return {"episode": E["resets"] + 1, "resets_left": left, "control_steps_total": EP.rows}


def status() -> dict:
    _touch()
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1), **reset_counters()}


class Refused(Exception):
    """A /reset the service turns down (409): nothing changes."""

    def __init__(self, body: dict):
        super().__init__(body.get("error"))
        self.body = body


def do_reset(meta: dict):
    """POST /reset: a new episode from the frozen instance (the running one, if any, is abandoned, never graded)."""
    meta = _request(meta)
    cams, fps = cameras_of(meta), video_fps(meta)
    L.depth_mode(meta)  # a bad depth value is a 400 before anything changes
    if E["success"]:
        raise Refused({"error": "trial finished: an episode succeeded", "reason": E["reason"], "resets_left": 0})
    if E["resets"] >= RESET_BUDGET:
        raise Refused({"error": "reset budget exhausted", "reason": "reset budget exhausted", "budget": RESET_BUDGET,
                       "resets_left": 0})
    abandoned = {"episode": E["resets"] + 1, "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"]}
    if not E["done"]:  # the abandoned episode's end, for the log (never graded: its rows leave the trajectory)
        EP.log({"ev": "end", "reason": "reset", "step": E["step"], "control_steps": ctrl_steps(), "success": False,
                "episode": E["resets"] + 1, "journal_rows": EP.rows})
    S.reset()
    ROWS.clear()
    E["resets"] += 1
    E["reset_at"] = list(E["reset_at"]) + [EP.rows]
    E.update(done=False, reason=None, success=False, t_end=None, episode_control_steps=None, dumped=False, check=None)
    EP._ck = None  # the state changed without a journal row: the checkpoint after this call must hash it anew
    E["calls"] += 1
    EP.log({"ev": "reset", "call": E["calls"], "episode": E["resets"] + 1, "journal_rows": EP.rows,
            "abandoned": abandoned, "state_sha": S.state_sha()})
    rec = recorder(cams, fps, meta)
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


RESUMED = EP.begin(state=E, step=replay_row, state_sha=resume_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
                   start_event={"env": S.env, "seed": S.inst.get("seed"), "cameras": CAMS})
if RESUMED and E["resets"]:  # Episode.begin looks for an "end" of any episode: only the current one's counts
    _ends = [e for e in EP.events() if e.get("ev") == "end" and int(e.get("episode") or 1) == E["resets"] + 1
             and e.get("reason") != "reset" and int(e.get("journal_rows") or 0) <= EP.rows]
    if _ends:
        E.update(done=True, reason=_ends[-1].get("reason"), success=bool(_ends[-1].get("success")),
                 t_end=float(_ends[-1]["ts"]), episode_control_steps=int(_ends[-1].get("control_steps") or ctrl_steps()))
    else:
        E.update(done=False, reason=None, success=False, t_end=None, episode_control_steps=None)
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} MuJoCo Playground quadruped sim ready ({S.env}; startup {EP.n_startups}, resumes {EP.resumes})", flush=True)


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
    """L.serve with this service's handler (the same spec defaults and check, and L.bind: a port still held when the
    service restarts is waited for, not a crash)."""
    svc.spec.setdefault("on_service_error", L.ON_SERVICE_ERROR)
    svc.spec.setdefault("max_call_wall_s", EP.max_call_wall_s)
    L.check_spec(svc.spec)
    L.bind(port, make_handler(svc)).serve_forever()


serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                on_submit_error=lambda exc: finish("error"), log=EP.log, episode=EP, state_sha=S.state_sha,
                proprio=proprio_row), port=int(os.environ.get("RCB_PORT", "8000")))
