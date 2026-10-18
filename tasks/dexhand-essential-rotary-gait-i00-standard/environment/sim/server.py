"""DexHand adapter of the shared eai-standard/2.2 layer; physics stays in this process.

The optional reset capability (docs/protocol/standard_mode.md "Optional reset capability", PROTOCOL §4.5) is added here, as the
MyoSuite 2.2 service adds it (the shared layer has none): with RCB_RESET_BUDGET = N > 0 (DexHand's compose files: 20),
POST /reset abandons the running episode, or follows one that has ended, and starts a new one from the frozen start
(Session.reset(): the same state hash as a fresh process); only the last episode is graded. A crash resume replays the
journal and resets where the committed resets did (their journal rows are checkpointed, `persist`).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback

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
RESET_BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET") or 0))  # the compose files' default: 20 (PROTOCOL §4.5)
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
    "resets": 0,  # resets done (the episode is resets + 1)
    "reset_at": [],  # the journal row at which each reset happened: a resume resets there again
}
EP = L.Episode(str(DATA), dim=N, resume="exact", persist=("resets", "reset_at"))
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
# The essential families' close-up views of the held object (scene.py) are returned by default, next to the overview.
DEFAULT_CAMERAS = ["overview"] + [camera for camera in ("inhand_top",) if camera in CAMERAS]


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
    "default_cameras": DEFAULT_CAMERAS,
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
    "budget": {"reset": RESET_BUDGET, "steps": None, "wall_clock_s": WALL},
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

if RESET_BUDGET:
    SPEC["reset"] = (
        f"POST /reset (JSON or RCB1 {{cameras, video_fps, depth}}; no physics) abandons the running episode, or follows "
        f"one that has ended, and starts a new one from the same frozen starting state, {RESET_BUDGET} times in all; it "
        "returns the new episode's first frames and proprioception. Only the last episode is graded: an episode you "
        "reset away is never graded, a success ends the trial (409 after it), and when your time is up the episode then "
        "running is the one graded. The wall clock never restarts. /status and every meta add `episode`, `resets_left` "
        "and `control_steps_total` (all episodes); `control_steps` counts the current episode's."
    )


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


REPLAYING = {"on": False}  # a crash resume is replaying journaled rows: their episode ends were logged live


def finish(reason: str) -> None:
    if E["done"]:
        return
    E.update(done=True, reason=reason)
    if reason == "error":
        E["success"] = False   # a simulator error ends the episode: the state after it is never judged a success
    if REPLAYING["on"]:
        return
    EP.log({"ev": "end", "reason": reason, "success": bool(E["success"]), "control_steps": clock(),
            "episode": E["resets"] + 1, "journal_rows": EP.rows})


def execute(action, recorder=None) -> bool:
    S.step(action)
    ROWS.append(np.asarray(action, dtype=np.float64).copy())
    # journaled before the episode's end is logged, so the end's journal_rows counts the row that ended it
    stop = EP.journal(action) if recorder is not None else False
    state = S.status()
    E["success"] = bool(state["success"])
    if state["done"]:
        finish("success" if state["success"] else "task_failure")
    if recorder is not None:
        recorder.tick()
        return bool(E["done"] or stop)
    return bool(E["done"])


def options(meta, steps: int):
    cameras = meta.get("cameras")
    cameras = DEFAULT_CAMERAS if cameras is None else cameras
    if not isinstance(cameras, list) or any(camera not in CAMERAS for camera in cameras):
        raise ValueError("cameras must be a list of published camera names")
    cameras = list(dict.fromkeys(cameras or DEFAULT_CAMERAS))
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
        **reset_counters(),
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


def reset_counters() -> dict:
    if not RESET_BUDGET:
        return {}
    left = 0 if (E["success"] or E.get("exiting")) else RESET_BUDGET - E["resets"]
    return {"episode": E["resets"] + 1, "resets_left": left, "control_steps_total": EP.rows}


def status():
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": clock(),
        "done": E["done"],
        "reason": E["reason"],
        "elapsed_s": round(time.time() - E["t0"], 3),
        **reset_counters(),
    }


class Refused(Exception):
    """A /reset the service turns down (409): nothing changes."""

    def __init__(self, body: dict):
        super().__init__(body.get("error"))
        self.body = body


def do_reset(meta):
    """POST /reset: a new episode from the frozen start (the running one, if any, is abandoned, never graded)."""
    if not isinstance(meta, dict):
        raise ValueError("the request must be a JSON object")
    # every field first: a malformed request is a 400 before anything changes (one frame per camera here)
    recorder, _, fps = options({key: meta[key] for key in ("cameras", "video_fps", "depth") if key in meta}, 0)
    if E["success"]:
        raise Refused({"error": "trial finished: an episode succeeded", "reason": E["reason"], "resets_left": 0})
    if E["resets"] >= RESET_BUDGET:
        raise Refused({"error": "reset budget exhausted", "reason": "reset budget exhausted", "budget": RESET_BUDGET,
                       "resets_left": 0})
    abandoned = {"episode": E["resets"] + 1, "control_steps": clock(), "done": E["done"], "reason": E["reason"]}
    S.reset()
    ROWS.clear()
    E["resets"] += 1
    E["reset_at"] = list(E["reset_at"]) + [EP.rows]
    E.update(done=False, reason=None, success=False)
    EP._ck = None  # the state changed without a journal row: the checkpoint after this call must hash it anew
    E["calls"] += 1
    EP.log({"ev": "reset", "call": E["calls"], "episode": E["resets"] + 1, "journal_rows": EP.rows,
            "abandoned": abandoned, "state_sha": S.state_sha()})
    return response(recorder, "frames", fps, reset_id=E["resets"])


def end_episode():
    with LOCK:
        E["exiting"] = True
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
                "episodes": E["resets"] + 1,
                "resets": E["resets"],
                "reset_budget": RESET_BUDGET,
                "control_steps_total": EP.rows,
                "start_sha": next((event.get("state_sha") for event in EP.events() if event.get("ev") == "start"), None),
                **EP.final_fields(),
            },
        )
        os._exit(0)


# A resume replays the journal from the frozen start and resets where the committed resets did: their journal rows are
# in the last checkpoint (`persist`), the one Episode.begin resumes from.
_CPS = [event for event in EP.events() if event.get("ev") == "checkpoint"]
RESUME = {"at": list((_CPS[-1].get("persist") or {}).get("reset_at") or []) if _CPS else [], "i": 0}


def _resume_resets() -> None:
    while RESUME["at"] and int(RESUME["at"][0]) <= RESUME["i"]:
        RESUME["at"].pop(0)
        S.reset()
        ROWS.clear()
        E.update(done=False, reason=None, success=False)


def replay_row(row) -> None:
    """A journaled row during a resume (as live: the episode's verdict is the replayed one)."""
    _resume_resets()
    REPLAYING["on"] = True
    try:
        execute(row)
    finally:
        REPLAYING["on"] = False
    RESUME["i"] += 1


def resume_sha() -> str:
    _resume_resets()  # a reset after the last replayed row (or before the first)
    return S.state_sha()


def instance_check() -> dict:
    """The frozen instance, checked when the episode begins (the verdict is the live episode's, so no later replay
    rebuilds the scene): the scene files' sha256 against the generator's record (grading.json `instance_sha256`).
    No reference hash of the built starting state is recorded for DexHand; the start event logs the one this service
    built (`state_sha`), and episode.json repeats it (`start_sha`)."""
    here = Path(__file__).resolve().parent
    try:
        want = json.loads((here / "grading.json").read_text()).get("instance_sha256")
    except (OSError, ValueError, AttributeError):
        want = None
    if not isinstance(want, dict) or not want:
        return {"instance_ok": False, "instance_error": "grading.json records no instance_sha256"}
    bad = []
    for name, sha in sorted(want.items()):
        try:
            got = hashlib.sha256((here / name).read_bytes()).hexdigest()
        except OSError:
            got = None
        if got != sha:
            bad.append(name)
    return {"instance_ok": not bad, **({"instance_error": "differs from the generator's record: " + ", ".join(bad)}
                                       if bad else {})}


if not any(event.get("ev") == "start" for event in EP.events()):   # a fresh episode, not a resume
    INSTANCE = instance_check()
    if not INSTANCE["instance_ok"]:
        print(f"[dexhand] instance_mismatch: {INSTANCE['instance_error']}; the service does not start an episode",
              flush=True)
        if not L.final_verdict(str(DATA)):
            L._write_json(str(DATA / "final.json"), {"hand": HAND, "instance_mismatch": 1, **INSTANCE})
        EP.give_up("instance_mismatch", infra=True)   # writes the verdict and answers every request 409 until the end
else:
    INSTANCE = {}

RESUMED = EP.begin(
    state=E,
    step=replay_row if RESET_BUDGET else execute,
    state_sha=resume_sha if RESET_BUDGET else S.state_sha,
    proprio=proprio_row,
    spec=SPEC,
    start_event={"task": TASK, "hand": HAND, **INSTANCE},
    on_end=end_episode,
)
if RESUMED and E["resets"]:  # Episode.begin looks for an "end" of any episode: only the current one's counts
    _ends = [event for event in EP.events() if event.get("ev") == "end"
             and int(event.get("episode") or 1) == E["resets"] + 1 and int(event.get("journal_rows") or 0) <= EP.rows]
    if _ends:
        E.update(done=True, reason=_ends[-1].get("reason"))
    else:
        E.update(done=False, reason=None)
E["ready"] = True
(DATA / "server.pid").write_text(str(os.getpid()))


def make_handler(svc: L.Service):
    """The shared 2.2 handler, plus POST /reset when the run grants resets (the shared layer has no reset)."""
    base = L.make_handler(svc)

    class Handler(base):
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

    return Handler


def serve(svc: L.Service, port: int) -> None:
    """L.serve with this service's handler (the same spec defaults and check, and L.bind)."""
    svc.spec.setdefault("on_service_error", L.ON_SERVICE_ERROR)
    svc.spec.setdefault("max_call_wall_s", EP.max_call_wall_s)
    L.check_spec(svc.spec)
    L.bind(port, make_handler(svc)).serve_forever()


sys.stdout.flush()
serve(
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
