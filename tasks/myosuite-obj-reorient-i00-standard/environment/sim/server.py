"""eai-standard/2.2 sim service for the MyoSuite tasks (docs/STANDARD_MODE_2_2.md): the adapter of the shared layer
rcb_limited.py; the simulator is rcb_myosuite.Session (MyoSuite 2.12.2 on MuJoCo, CPU). HTTP surface: GET /spec,
GET /status, POST /observe, POST /submit, POST /kinematics. Every call is logged to /data/episode.jsonl.

The episode is the frozen instance's (environment/sim/instance.npz, the privileged twin's). The action is MyoSuite's own:
one command per muscle (excitation u = 1 / (1 + exp(-5 (a - 0.5)))), one row per control step. The episode ends the
moment the task's goal has held for its hold time (success), at the task's failure (object dropped, fingers off the key,
...), or when the agent's time is over (the collect hook). Nothing about objects or goals leaves this process: the
proprioception is the limb's own joints and muscles.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal. When the
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
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.npz"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
W, H = 640, 480
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}

os.environ["RCB_SESSION_LOG"] = ""
import rcb_myosuite as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

M.SESSION_LOG = ""          # the sidecar's Session is not the agent's interaction log
_INST = np.load(INSTANCE, allow_pickle=False)
TASK = str(_INST["task"])
NU = int(_INST["model__actuator_ctrlrange"].shape[0])   # the journal's row width, known before the scene is built
EP = L.Episode(DATA, dim=NU, resume="exact")
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Session(TASK, instance=INSTANCE)
assert S.nu == NU, (S.nu, NU)
MD = S.model
DT = S.dt
CTRL_HZ = 1.0 / DT
SUBSTEPS = int(S.base.frame_skip)
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
BODY = M.BODY[TASK]
ROBOT = {"hand": ("MyoHand", "a musculoskeletal model of a human forearm and hand (MyoSuite)"),
         "arm": ("MyoArm", "a musculoskeletal model of a human shoulder, arm and hand (MyoSuite)")}[BODY]
CAMS = [c for c in ("hand_top", "hand_side_inter", "front_view", "side_view") if c in S.cameras()]
DEFAULT_CAMS = ["hand_top"]
MUSCLES = [m["name"] for m in S.muscles()]
# the limb's own joints only: the key's hinge and the OBJ* joints of pen, die and objects are object state, never sent
LIMB = [j for j in S.joints() if j["name"] != "keyjoint" and not j["name"].startswith("OBJ")]
J_NAMES = [j["name"] for j in LIMB]
J_Q = np.array([j["qpos_adr"] for j in LIMB])
J_V = np.array([j["dof_adr"] for j in LIMB])
J_ID = [MD.joint(n).id for n in J_NAMES]
GROUPS = [
    ("joint_pos", [f"q_{n}" for n in J_NAMES], "joint angles of the limb (rad)"),
    ("joint_vel", [f"qd_{n}" for n in J_NAMES], "joint velocities (rad/s)"),
    ("muscle_activation", [f"act_{n}" for n in MUSCLES], "muscle activations in [0, 1] (they follow the excitations "
                                                           "with a first-order delay)"),
    ("muscle_length", [f"len_{n}" for n in MUSCLES], "muscle-tendon lengths (m)"),
    ("joint_effort", [f"effort_{n}" for n in J_NAMES], "generalized force of all muscles on each joint (N m)"),
    ("gripper_opening", [], "none (a hand, not a gripper)"),
    ("tcp_pose", [], "none (a hand, not a gripper); fingertip poses: /kinematics fk"),
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
    T[:3, :3] = data.cam_xmat[i].reshape(3, 3)       # MuJoCo cameras: OpenGL axes (x right, y up, z back)
    T[:3, 3] = data.cam_xpos[i]
    return T


GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])


def camera_info(cam: str) -> dict:
    """World -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
    c2w = _cam_T_gl(S.data, cam)
    ext = np.linalg.inv(c2w @ GL2CV)[:3, :]
    return {"intrinsic_cv": _intrinsic(cam), "extrinsic_cv": ext.tolist(), "cam2world_gl": c2w.tolist(), "image_size": [W, H]}


def _mount(cam: str) -> dict:
    i = MD.camera(cam).id
    body = MD.body(int(MD.cam_bodyid[i])).name
    if body == "world":
        info = camera_info(cam)
        return {"type": "static", "extrinsic_cv": info["extrinsic_cv"], "cam2world_gl": info["cam2world_gl"]}
    b = MD.body(body).id
    Tb = np.eye(4)
    Tb[:3, :3] = S.data.xmat[b].reshape(3, 3)
    Tb[:3, 3] = S.data.xpos[b]
    link_T_cam_cv = np.linalg.inv(Tb) @ _cam_T_gl(S.data, cam) @ GL2CV
    return {"type": "link", "parent_link": body, "link_T_cam_cv": link_T_cam_cv.tolist()}


MOUNTED = {"front_view": "static: the whole body from the front (the hand is small in it)",
           "side_view": "static: the whole body from the side (the hand is small in it)",
           "hand_top": "on the forearm (radius): a close-up of the hand from above; it moves with the forearm (pronation)",
           "hand_side_inter": "on the forearm (radius): a close-up of the hand from the thumb side; it moves with the forearm"}


# ------------------------------------------------------------------------------------------------- kinematics
KD = mujoco.MjData(MD)        # kinematics only: a copy of the start state, never stepped
KD.qpos[:] = S.data.qpos
TIPS = [n for n in ("THtip", "IFtip", "MFtip", "RFtip", "LFtip") if mujoco.mj_name2id(MD, mujoco.mjtObj.mjOBJ_SITE, n) >= 0]
MOUNT_LINKS = sorted({MD.body(int(MD.cam_bodyid[MD.camera(c).id])).name for c in CAMS} - {"world"})
LINKS = TIPS + MOUNT_LINKS
_rb = int(MD.jnt_bodyid[J_ID[0]])
while int(MD.body_parentid[_rb]) != 0:
    _rb = int(MD.body_parentid[_rb])
ROOT_BODY = MD.body(_rb).name
ROOT_POSE = [*S.data.xpos[_rb].tolist(), *S.data.xquat[_rb].tolist()]
LO = np.array([MD.jnt_range[j, 0] if MD.jnt_limited[j] else -np.inf for j in J_ID])
HI = np.array([MD.jnt_range[j, 1] if MD.jnt_limited[j] else np.inf for j in J_ID])


def _fk_kd(q) -> None:
    KD.qpos[J_Q] = q
    mujoco.mj_kinematics(MD, KD)
    mujoco.mj_comPos(MD, KD)      # the Jacobians (mj_jacSite) need it


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
        _fk_kd(np.asarray(req["q"]))
        return L.fk_response({n: _pose(n) for n in req["links"]}, "world")
    q = np.array(req["seed"] if req["seed"] is not None else S.data.qpos[J_Q], dtype=np.float64)
    tg = {k: np.asarray(v[:3]) for k, v in req["targets"].items()}
    jac = np.zeros((3, MD.nv))

    def err(qq):
        _fk_kd(qq)
        return np.concatenate([t - KD.site_xpos[MD.site(k).id] for k, t in tg.items()])

    lam, e = 1e-2, err(q)
    for _ in range(req["max_iters"]):          # Levenberg-Marquardt on the stacked fingertip position errors
        if max(np.linalg.norm(e[3 * i:3 * i + 3]) for i in range(len(tg))) < req["tol_pos_m"]:
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
    return L.ik_response(q, ok, errors, "world", note="fingertips: position only (orientation ignored); no collision check")


# ------------------------------------------------------------------------------------------------- spec
TASK_TEXT = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_text.txt")).read().strip()
EPISODE = (f"one episode, no reset: it ends the moment the task's goal has held for {S.hold_steps} control steps in a row "
           f"({round(S.hold_steps * DT, 3)} s; success), at the task's failure (see task_text), or when your time is over")
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "MyoSuite 2.12.2 on MuJoCo 3.6.0 (CPU)",
    "robot": f"{ROBOT[0]}: {ROBOT[1]}, {NU} muscles",
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "resolution": [W, H], "intrinsic_cv": _intrinsic(c), "mounted": MOUNTED[c],
                    "mount": _mount(c)} for c in CAMS},
    "default_cameras": DEFAULT_CAMS,
    "action_types": {
        "muscle": {
            "dim": NU,
            "layout": MUSCLES,
            "limits": None,
            "units": "one real number a per muscle; excitation u = 1 / (1 + exp(-5 (a - 0.5))); a is not clipped "
                     "(a = -1: u ~ 0.0006, 0.5: 0.5, 1: 0.92, 2: 0.9994)",
            "semantics": "muscle excitations, one row per control step; activations follow them with a first-order delay "
                         "(~10 ms up, ~40 ms down); muscles only pull, one muscle can cross several joints, and its force "
                         "depends on its length and velocity. Rows are `dt` apart (a whole multiple of the control period, "
                         "at most 0.5 s), `linear` (default: from the previous command) or `hold` between rows; every real "
                         "value is a valid command, so nothing is clipped",
        },
        "not_yet": ["joint_position", "joint_torque", "joint_delta"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {"muscles": MUSCLES},
    "world": {"frame": "MyoSuite's world frame, z up; the limb's root is fixed in it (no positions of the scene are given)",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "episode": EPISODE,
    "robot_spec": {
        "name": ROBOT[0], "description": f"{ROBOT[1]}: {NU} muscle actuators, {len(J_NAMES)} joints",
        "base": {"type": "fixed", "link": ROOT_BODY, "pose": ROOT_POSE,
                 "note": "the limb's root body is fixed in the world (pose: x y z + wxyz quaternion)"},
        "joints": [{"name": n, "type": "revolute" if np.isfinite(LO[k]) else "continuous", "unit": "rad",
                    "position_limits": [float(LO[k]), float(HI[k])] if np.isfinite(LO[k]) else None,
                    "velocity_limit": None, "effort_limit": None, "group": BODY} for k, n in enumerate(J_NAMES)],
        "grippers": {},
        "controller": {"type": "muscle actuators (MuJoCo muscle model); no joint-level controller", "control_hz": CTRL_HZ,
                       "physics_hz": CTRL_HZ * SUBSTEPS, "gains": {},
                       "note": "the command is each muscle's excitation (the muscles: static.muscles, the action's layout); "
                               "the joints move only through muscle forces"},
        "tcp": {},
    },
    "kinematics": {"endpoint": "/kinematics", "joint_names": GROUPS[0][1], "frame": "world", "quaternion_order": "wxyz",
                   "links": LINKS, "tcp_frames": [], "ee_frames": TIPS, "ik_targets": TIPS,
                   "ik": {"tol_pos_m": 0.002, "tol_rot_rad": 3.2, "max_iters": 500},
                   "note": "fingertip sites and the camera mounts in the world frame for joint angles q (`joint_pos` order); "
                           "ik: fingertip positions only, over all limb joints"},
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0,
              "max_m": L.DEPTH_MAX_M, "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)  # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()


def ctrl_steps() -> int:
    return int(S.steps)


def proprio_row() -> np.ndarray:
    d = S.data
    return np.concatenate([d.qpos[J_Q], d.qvel[J_V], d.act[:NU], d.actuator_length[:NU], d.qfrc_actuator[J_V]]).astype(np.float32)


def grab(cams, want_depth: bool):
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c, (H, W))
        if want_depth:                       # the same renderer (a second OSMesa context next to a live one reads garbage)
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
    return {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n,
            "physics_steps": n * SUBSTEPS, "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
            "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": L.PROTOCOL, "n_actions": len(ROWS),
            **EP.final_fields()}


def finish(reason: str) -> None:
    """The episode is over: the task's verdict on the steps executed, then the record for the collect hook."""
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


def recorder(cams, fps: int, meta: dict, video: str) -> L.Recorder:
    every = max(1, int(round(CTRL_HZ / max(1, fps)))) if video != "none" else 10**9   # no video: first and last frame
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
    bad = [c for c in cams if c not in CAMS]
    if bad:
        raise ValueError(f"unknown cameras {bad}; cameras: {CAMS}")
    return list(cams)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
            "sim_time_s": round(n * DT, 4), "time_s": round(time.time() - E["t0"], 2),
            "time_left_s": max(0.0, round(WALL_CLOCK_S - (time.time() - E["t0"]), 1)),
            "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            "cameras": {c: camera_info(c) for c in cams}}


def last_command() -> np.ndarray:
    return ROWS[-1].copy() if ROWS else S.rest_action()


def do_submit(meta: dict, A: np.ndarray):
    typ = meta.get("type")
    if typ != "muscle":
        raise ValueError(f"type must be muscle (not yet: {SPEC['action_types']['not_yet']})")
    dt = float(meta.get("dt", DT))
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps = cameras_of(meta), video_fps(meta)
    k = dt / DT
    if A.ndim != 2 or A.shape[1] != NU:
        raise ValueError(f"muscle actions must be (T, {NU}), got {list(A.shape)}")
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
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0,
           "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
           "clipped": [], "n_clipped": 0, "plan": [], "ok": True}
    EP.log({"ev": "submit", "call": E["calls"], "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams,
            "control_steps": ctrl_steps() - before, "note": (meta.get("note") or "")[:500],
            **({"stopped": EP.stop_reason} if EP.stopping else {})})
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
         start_event={"task": TASK, "env": S.env_id, "cameras": CAMS})
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} MyoSuite sim ready ({TASK}: {S.env_id}; startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
try:
    L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics,
                      status=status, on_submit_error=lambda exc: finish("error"), log=EP.log, episode=EP,
                      state_sha=S.state_sha, proprio=proprio_row), port=int(os.environ.get("RCB_PORT", "8000")))
except Exception:  # noqa: BLE001
    traceback.print_exc()
    raise
