"""DexHand adapter of the shared eai-standard/2.2 layer; physics stays in this process."""

from __future__ import annotations

import math
import os
from pathlib import Path
import threading
import time

import mujoco
import numpy as np

import hands
import rcb_limited as L
from runtime import Session

DATA = Path(os.environ.get("RCB_DATA", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
TASK = os.environ["RCB_TASK"]
try:
    HAND, HAND_ERROR = hands.selected(), None  # DEXHAND_HAND on this trusted service, read once; default sharpa
except hands.HandError as exc:  # a hand this task does not offer (task.toml `hands`): refused below, no episode
    HAND, HAND_ERROR = os.environ.get("DEXHAND_HAND", "").strip(), exc
WALL = float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))
HZ = 50
N = 6 + 22  # replaced by the selected hand's width once the scene is built
LOCK = threading.Lock()
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
EP = L.Episode(str(DATA), dim=N, resume="exact")
EP.startup()
if HAND_ERROR is None:
    try:
        S = Session(TASK) if HAND == "sharpa" else Session(TASK, hand=HAND)
    except hands.HandError as exc:
        HAND_ERROR = exc
if HAND_ERROR is not None:
    print(f"[dexhand] DEXHAND_HAND={HAND!r}: {HAND_ERROR}; the service does not start an episode", flush=True)
    if not L.final_verdict(str(DATA)):
        L._write_json(str(DATA / "final.json"), {"hand": HAND, "hand_not_offered": 1})
    EP.give_up("hand_not_offered", infra=True)  # writes the verdict and answers every request 409 until the end
if getattr(S, "hand", "sharpa") != HAND:
    raise RuntimeError(f"runtime built {getattr(S, 'hand', 'sharpa')!r}, service selected {HAND!r}")
EP.scene_built()
MD, D = S.model, S.data
N = S.action_dim
EP.dim = N  # the journal holds rows of the selected hand's width
ROBOT = getattr(S, "robot", hands.HANDS[HAND]["robot"] + "-floating")
# The family's control rate (default 50 Hz with ten 2 ms substeps); one action row is one control.
HZ = int(round(1.0 / float(S.control_dt))) if getattr(S, "control_dt", None) else 50
SUBSTEPS = int(getattr(S, "substeps", 10))
MAX_FPS = min(50, HZ)
JIDS = np.asarray(MD.actuator_trnid[:N, 0], dtype=int)
JOINTS = [MD.joint(int(index)).name for index in JIDS]
QADR = MD.jnt_qposadr[JIDS]
VADR = MD.jnt_dofadr[JIDS]
LIMITS = np.asarray(MD.actuator_ctrlrange[:N], dtype=float)
ROWS = []


def own_body(index: int) -> bool:
    """Admit robot links only: every joint on the ancestry path must be a controlled robot joint."""
    seen_joint = False
    while index:
        start = int(MD.body_jntadr[index])
        count = int(MD.body_jntnum[index])
        for joint in range(start, start + count):
            if joint not in JIDS:
                return False
            seen_joint = True
        if MD.body_mocapid[index] >= 0:
            return False
        index = int(MD.body_parentid[index])
    return seen_joint


LINK_IDS = {MD.body(index).name: index for index in range(1, MD.nbody) if own_body(index)}
if getattr(S, "tcp_bodies", None):
    TCP_IDS = [MD.body(name).id for name in S.tcp_bodies]
elif getattr(S, "tcp_body", None):
    TCP_IDS = [MD.body(S.tcp_body).id]
else:
    TCP_IDS = [int(MD.jnt_bodyid[JIDS[5]])]
TCPS = [MD.body(index).name for index in TCP_IDS]
KIN_DATA = mujoco.MjData(MD)
DEPTH_RENDERER = None
# With video "none" (and no per-frame depth) only a call's last frame reaches the agent: intermediate captures skip
# rendering. Rendering only reads the state (never physics), so this changes no executed control.
RENDER = {"final": False}
CAMERAS = S.cameras()


def pose(data, index: int) -> list:
    quaternion = np.zeros(4)
    mujoco.mju_mat2Quat(quaternion, data.xmat[index])
    return np.concatenate([data.xpos[index], quaternion]).tolist()


def camera_transform(camera: str) -> tuple[np.ndarray, np.ndarray]:
    index = MD.camera(camera).id
    world_gl = np.eye(4)
    world_gl[:3, :3] = D.cam_xmat[index].reshape(3, 3)
    world_gl[:3, 3] = D.cam_xpos[index]
    cv_world = np.diag([1.0, -1.0, -1.0, 1.0]) @ np.linalg.inv(world_gl)
    return world_gl, cv_world[:3]


def camera_spec(camera: str) -> dict:
    index = MD.camera(camera).id
    focal = 240.0 / math.tan(math.radians(float(MD.cam_fovy[index])) / 2)
    world_gl, ext = camera_transform(camera)
    body = int(MD.cam_bodyid[index])
    mount = {"type": "static", "extrinsic_cv": ext.tolist(), "cam2world_gl": world_gl.tolist()}
    if body:
        if not own_body(body):
            raise RuntimeError("a camera attached to a scene object cannot publish calibration")
        world_body = np.eye(4)
        world_body[:3, :3] = D.xmat[body].reshape(3, 3)
        world_body[:3, 3] = D.xpos[body]
        mount = {
            "type": "link",
            "parent_link": MD.body(body).name,
            "link_T_cam_cv": (np.linalg.inv(world_body) @ world_gl @ np.diag([1.0, -1.0, -1.0, 1.0])).tolist(),
        }
    return {
        "rgb": True,
        "depth": True,
        "mounted": "robot" if body else "static",
        "mount": mount,
        "resolution": [640, 480],
        "intrinsic_cv": [[focal, 0.0, 320.0], [0.0, focal, 240.0], [0.0, 0.0, 1.0]],
    }


LAYOUT = JOINTS + [f"{name}_vel" for name in JOINTS] + [f"{name}_effort" for name in JOINTS]
LAYOUT += [f"{tcp}_{name}" for tcp in TCPS for name in ("x", "y", "z", "qw", "qx", "qy", "qz")]
LAYOUT += [f"{name}_target" for name in JOINTS]
GROUPS = {
    "joint_pos": [0, N, "measured wrist and finger joints"],
    "joint_vel": [N, N, "measured joint velocities"],
    "joint_effort": [2 * N, N, "actuator generalized forces"],
    "gripper_opening": [3 * N, 0, "no scalar opening for the five-finger hand"],
    "tcp_pose": [3 * N, 7 * len(TCPS), "mount frame position and quaternion wxyz, per tcp frame"],
    "joint_target": [3 * N + 7 * len(TCPS), N, "current position actuator targets"],
}
JOINT_SPEC = []
for actuator, joint in enumerate(JIDS):
    slide = MD.jnt_type[joint] == mujoco.mjtJoint.mjJNT_SLIDE
    effort_limits = []
    if MD.actuator_forcelimited[actuator]:
        effort_limits.append(float(max(abs(MD.actuator_forcerange[actuator]))))
    if MD.jnt_actfrclimited[joint]:
        effort_limits.append(float(max(abs(MD.jnt_actfrcrange[joint]))))
    JOINT_SPEC.append(
        {
            "name": JOINTS[actuator],
            "type": "prismatic" if slide else "revolute",
            "unit": "m" if slide else "rad",
            "position_limits": MD.jnt_range[joint].tolist(),
            "velocity_limit": None,
            "effort_limit": min(effort_limits) if effort_limits else None,
        }
    )
GAINS = {
    name: {"stiffness": float(MD.actuator_gainprm[index, 0]), "damping": float(-MD.actuator_biasprm[index, 2])}
    for index, name in enumerate(JOINTS)
}
SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": L.COMPAT,
    "simulator": "MuJoCo 3.4.0",
    "robot": ROBOT,
    "hand": HAND,
    "hand_info": hands.info(HAND),
    "task_text": Path(__file__).with_name("task_text.txt").read_text(),
    "control_hz": HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": 10.0,
    "max_watch_s": 30.0,
    "max_frames_per_call": 1000,
    "cameras": {camera: camera_spec(camera) for camera in CAMERAS},
    "default_cameras": ["overview"],
    "action_types": {
        "joint_position": {
            "dim": N,
            "layout": JOINTS,
            "units": "first three m; remaining rad",
            "limits": dict(zip(JOINTS, LIMITS.tolist())),
            "semantics": "position targets, hold or linear interpolation",
        }
    },
    "proprio_layout": LAYOUT,
    "proprio_groups": GROUPS,
    "static": {},
    "world": {
        "frame": "world",
        "up": "+z",
        "units": {"length": "m", "angle": "rad"},
        "quaternion_order": "wxyz",
        "camera_axes": "OpenCV",
    },
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL},
    **({"max_control_steps": int(S.max_control_steps)} if getattr(S, "max_control_steps", None) else {}),
    "robot_spec": {
        "name": ROBOT,
        "joints": JOINT_SPEC,
        "grippers": {},
        "base": {"type": "fixed", "pose": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]},
        "controller": {"type": "position", "control_hz": HZ, "gains": GAINS},
        "tcp": {
            tcp: {
                "parent_link": tcp,
                "link_T_frame": np.eye(4).tolist(),
                "definition": f"mount link frame before the {hands.HANDS[HAND]['model']} palm",
            }
            for tcp in TCPS
        },
    },
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "unit": "m", "invalid": 0, "kind": "z-depth"},
    "kinematics": {
        "endpoint": "/kinematics",
        "joint_names": JOINTS,
        "frame": "world",
        "quaternion_order": "wxyz",
        "links": list(LINK_IDS),
        "tcp_frames": TCPS,
        "ee_frames": TCPS,
        "ik_targets": [],
    },
}


def clock() -> int:
    return int(S.status()["steps"])


def proprio_row() -> np.ndarray:
    tcp = [value for index in TCP_IDS for value in pose(D, index)]
    return np.concatenate([D.qpos[QADR], D.qvel[VADR], D.qfrc_actuator[VADR], tcp, D.ctrl[:N]]).astype(
        np.float32
    )


def grab(cameras, want_depth):
    global DEPTH_RENDERER
    rgb = {camera: S.render_frame(camera) for camera in cameras}
    depth = {}
    if want_depth:
        if DEPTH_RENDERER is None:
            DEPTH_RENDERER = mujoco.Renderer(MD, height=480, width=640)
        DEPTH_RENDERER.enable_depth_rendering()
        for camera in cameras:
            DEPTH_RENDERER.update_scene(D, camera=camera)
            depth[camera] = DEPTH_RENDERER.render().copy()
    return rgb, depth


def extrinsics(cameras):
    return {camera: camera_transform(camera)[1] for camera in cameras}


def finish(reason: str) -> None:
    if E["done"]:
        return
    E.update(done=True, reason=reason)
    EP.log({"ev": "end", "reason": reason, "success": bool(E["success"]), "control_steps": clock()})


def execute(action, recorder=None) -> bool:
    S.step(action)
    ROWS.append(np.asarray(action, dtype=np.float64).copy())
    state = S.status()
    E["success"] = bool(state["success"])
    if state["done"]:
        finish("success" if state["success"] else "task_failure")
    if recorder is not None:
        stop = EP.journal(action)
        recorder.tick()
        return bool(E["done"] or stop)
    return bool(E["done"])


def options(meta, steps: int):
    cameras = meta.get("cameras")
    cameras = SPEC["default_cameras"] if cameras is None else cameras
    if not isinstance(cameras, list) or any(camera not in CAMERAS for camera in cameras):
        raise ValueError("cameras must be a list of published camera names")
    cameras = cameras or SPEC["default_cameras"]
    if meta.get("note") is not None and not isinstance(meta["note"], str):
        raise ValueError("note must be text")
    video = meta.get("video", "mp4")
    if video not in ("none", "mp4", "frames", "both"):
        raise ValueError("video must be none|mp4|frames|both")
    fps = meta.get("video_fps", 10)
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= MAX_FPS:
        raise ValueError(f"video_fps must be between 1 and {MAX_FPS}")
    every = max(1, int(round(HZ / fps)))
    depth = L.depth_mode(meta)
    L.check_frames(len(cameras), math.ceil(steps / every) + 3, depth in ("frames", "legacy"), 1000)
    capture = grab
    if video == "none" and depth not in ("frames", "legacy"):
        def capture(cams, want_depth):
            return grab(cams, want_depth) if RENDER["final"] else ({}, {})
    recorder = L.Recorder(cameras, every, capture, proprio_row, extrinsics, clock, depth=depth, clock_hz=HZ)
    return recorder, video, int(fps)


def response(recorder, video, fps, **extra):
    RENDER["final"] = True
    try:
        recorder.tick(force=True, last=True)
    finally:
        RENDER["final"] = False
    return {
        "ok": True,
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": clock(),
        "done": E["done"],
        "reason": E["reason"],
        "time_s": round(L.agent_time(E), 2),  # since the agent's first request (rcb_limited.agent_time)
        "time_left_s": max(0.0, round(WALL - L.agent_time(E), 1)),
        "proprio": {"layout": LAYOUT, "now": proprio_row().tolist()},
        "cameras": {
            camera: {
                "intrinsic_cv": SPEC["cameras"][camera]["intrinsic_cv"],
                "extrinsic_cv": camera_transform(camera)[1].tolist(),
                "cam2world_gl": camera_transform(camera)[0].tolist(),
            }
            for camera in recorder.cams
        },
        **extra,
    }, recorder.parts(video, fps)


def do_submit(meta, actions):
    if meta.get("type") != "joint_position":
        raise ValueError("type must be joint_position")
    if actions.ndim != 2 or actions.shape[1] != N or not len(actions) or not np.isfinite(actions).all():
        raise ValueError(f"actions must be a nonempty finite (T, {N}) array for the {HAND} hand")
    dt = meta.get("dt")
    dt = 1 / HZ if dt is None else dt
    if isinstance(dt, bool) or not isinstance(dt, (float, int)) or not math.isfinite(dt) or not 1 / HZ <= dt <= 0.5:
        raise ValueError(f"dt must be in [{1 / HZ:g}, 0.5]")
    count = int(round(dt * HZ))
    if abs(count / HZ - dt) > 1e-8 or len(actions) * count > 10 * HZ:
        raise ValueError(f"dt must be a multiple of {1 / HZ:g} s and a chunk at most 10 seconds")
    interpolation = meta.get("interpolate", "hold")
    if interpolation not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    clipped = np.clip(actions, LIMITS[:, 0], LIMITS[:, 1])
    rec, video, fps = options(meta, len(actions) * count)
    rec.tick(force=True)
    E["calls"] += 1
    rows = 0
    previous = D.ctrl[:N].copy()
    for row in clipped:
        E["step"] += 1
        rows += 1
        for index in range(count):
            action = previous + (row - previous) * (index + 1) / count if interpolation == "linear" else row
            if execute(action, rec):
                break
        previous = row
        if E["done"] or EP.stopping:
            break
    return response(rec, video, fps, executed_rows=rows, clipped=int(np.count_nonzero(clipped != actions)))


def do_observe(meta):
    seconds = meta.get("seconds")
    seconds = 0.0 if seconds is None else seconds
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (float, int))
        or not math.isfinite(seconds)
        or not 0 <= seconds <= 30
    ):
        raise ValueError("seconds must be in [0, 30]")
    rec, video, fps = options(meta, int(round(seconds * HZ)))
    rec.tick(force=True)
    E["calls"] += 1
    for _ in range(int(round(seconds * HZ))):
        if E["done"] or execute(D.ctrl[:N].copy(), rec):
            break
    return response(rec, video, fps)


def kinematics(request):
    if request["op"] != "fk":
        raise ValueError("only forward kinematics is provided; ik_targets is empty")
    mujoco.mj_resetData(MD, KIN_DATA)
    KIN_DATA.qpos[QADR] = request["q"]
    mujoco.mj_forward(MD, KIN_DATA)
    return L.fk_response({link: pose(KIN_DATA, LINK_IDS[link]) for link in request["links"]}, "world")


def status():
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": clock(),
        "done": E["done"],
        "reason": E["reason"],
        "elapsed_s": round(time.time() - E["t0"], 3),
    }


def end_episode():
    with LOCK:
        finish("timeout")
        np.savez_compressed(
            DATA / "trajectory.npz",
            actions=np.asarray(ROWS, dtype=np.float64).reshape(-1, N),
            hand=np.array(HAND),
            task=np.array(TASK),
        )
        L._write_json(
            str(DATA / "episode.json"),
            {
                **status(),
                "success": bool(E["success"]),
                "live_sha": S.state_sha(),
                "hand": HAND,
                "n_actions": len(ROWS),
                **EP.final_fields(),
            },
        )
        os._exit(0)


EP.begin(
    state=E,
    step=execute,
    state_sha=S.state_sha,
    proprio=proprio_row,
    spec=SPEC,
    start_event={"task": TASK, "hand": HAND},
    on_end=end_episode,
)
E["ready"] = True
(DATA / "server.pid").write_text(str(os.getpid()))
L.serve(
    L.Service(
        spec=SPEC,
        lock=LOCK,
        state=E,
        submit=do_submit,
        observe=do_observe,
        kinematics=kinematics,
        status=status,
        on_submit_error=lambda exc: finish("error"),
        log=EP.log,
        episode=EP,
        state_sha=S.state_sha,
        proprio=proprio_row,
    ),
    port=int(os.environ.get("RCB_PORT", "8000")),
)
