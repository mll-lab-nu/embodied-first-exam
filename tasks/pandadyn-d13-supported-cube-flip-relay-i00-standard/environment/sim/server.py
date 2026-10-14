"""eai-standard/2.2 sim service for Panda Dynamic Scenes (ManiSkill 3.0.1 / SAPIEN 3.0.3, CPU PhysX at 1000 Hz; one or two
Franka Panda arms with their task tools; see docs/STANDARD_MODE.md). Owns the scene. HTTP surface (rcb_limited): GET /spec,
GET /status, POST /observe, POST /submit, POST /kinematics (RCB1 bodies, RCB1 responses: videos / frames / depth / proprio
as raw blobs, never base64). Logs every call to /data/episode.jsonl and keeps /data/final.json current. Nothing about
objects ever leaves this process.

Crash recovery (rcb_limited.Episode, docs/STANDARD_MODE.md §13, resume class `exact`): every executed control step is
journaled (the float64 row handed to Session.step), every completed call is checkpointed with the scene's state hash.
After a crash compose restarts the container (`restart: on-failure:6`, run.sh exits non-zero) and this service, a fresh
process, rebuilds the frozen scene, replays the journal up to the last checkpoint (bit-identical: CPU PhysX with enhanced
determinism, one thread), checks the state hash and continues the SAME episode, never a reset.

What is particular to this benchmark:
- the action is the environment's own: per arm 7 absolute joint-position targets + the total gripper aperture, one row
  per 10 ms control step (100 Hz; 10 physics steps of 1 ms), executed by each arm's Ruckig + torque servo; `linear`
  interpolates the targets between rows, `hold` repeats them;
- the scene does not wait: launches and driven fixtures move from the first control step on, and the simulated clock only
  advances with the control steps the agent asks for (/submit rows, /observe watch windows);
- the episode ends at the first control step where the task's event ledger reports success (every phase in order, no
  failure) or a failure (a failure event, a forbidden contact, a safety-limit violation, an object out of bounds, the
  task's horizon), or when the time is up;
- two static cameras (overview, closeup), RGB and z-depth, rendered only when a frame is recorded (rendering never steps
  physics); /kinematics from the arms' own Pinocchio models (stateless);
- the episode is NOT replayed here: when it ends the service writes /data/trajectory.npz + /data/episode.json (live result
  and state hash); the collect hook's SIGUSR1 makes it exit, and environment/sim/finalize.sh replays the trajectory in two
  fresh processes and completes final.json."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
from typing import Callable
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
TEXTS = json.load(open(os.environ.get("RCB_TEXTS", os.path.join(os.path.dirname(__file__), "texts.json"))))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 100; SUBSTEPS = 10
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "10"))
MAX_FRAMES = 1200        # /spec max_frames_per_call: cameras x frames; a frame with per-frame depth counts twice
LOCK = threading.Lock(); PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
I = json.load(open(INSTANCE))
ACTION_DIM = int(I["action_dim"])
EP = L.Episode(DATA, dim=ACTION_DIM, resume="exact")
EP.startup()             # start count, back-off after failed starts, startup watchdog (RCB_STARTUP_TIMEOUT_S) until scene_built()
log = EP.log


def ctrl_steps() -> int:
    return int(S.n_steps)                # = EP.rows: every step Session.step executes is journaled (a resume replays them)


def write_final() -> None:
    if L.final_verdict(DATA):        # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    n = int(E.get("episode_control_steps") or ctrl_steps())
    L._write_json(os.path.join(DATA, "final.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK,
                   "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"),
                   "phase": E.get("phase"), **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        acts = S.actions(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts)); E["phase"] = int(S.u.phase)
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"],
                                                                            "reason": E["reason"], "resumes": EP.resumes})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
                   "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), "phase": E.get("phase"), **EP.final_fields()})
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    if not E["success"]:
        try: E["success"] = check_success()
        except Exception: pass
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1),
         "success": bool(E["success"]), "phase": int(S.u.phase)})
    dump()


# ---------------------------------------------------------------- scene
import rcb_pandadyn as M  # noqa: E402
S = M.Session(I, strict=True)
TASK = S.task
ARMS = list(S.arm_ids)
JOINTS = [f"joint{i}" for i in range(1, 8)]
LAYOUT = [f"{a}_{j}" for a in ARMS for j in JOINTS + ["aperture"]]
CAMS = list(M.CAMERAS)
MOUNT = {"overview": "static, looking at the whole workspace from the front right, above the table",
         "closeup": "static, closer to the task's working area"}
FIRST = {c: S.render_frame(c) for c in CAMS}
CAM0 = S.camera_info(CAMS)
LIM = M._limits()
LIM_ARR = np.array([[lo, hi] for _a in ARMS for lo, hi in list(zip(LIM.LOWER, LIM.UPPER)) + [(0.0, M.APERTURE_MAX)]], dtype=np.float64)
LIMITS = {n: [round(float(lo), 4), round(float(hi), 4)] for n, (lo, hi) in zip(LAYOUT, LIM_ARR)}
QPOS = [f"{a}_{j}" for a in ARMS for j in JOINTS + ["finger_left", "finger_right"]]
PROPRIO_LAYOUT = (QPOS + [f"{a}_tcp_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"{q}_vel" for q in QPOS] + [f"{a}_aperture_m" for a in ARMS]
                  + [f"{a}_{j}_torque" for a in ARMS for j in JOINTS]
                  + [f"{a}_tool_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"{a}_target_{j}" for a in ARMS for j in JOINTS + ["aperture"]])
NQ, NA = len(QPOS), len(ARMS)
GROUPS = {
    "joint_pos": [0, NQ, "measured joint positions per arm (panda-0 first): joint1..7 (rad), finger_left, finger_right (m, each finger's "
                         "opening from the centre)"],
    "tcp_pose": [NQ, 7 * NA, "measured hand TCP pose per arm (panda_hand_tcp: between the fingertips), x y z (m) + quaternion wxyz, world frame"],
    "joint_vel": [NQ + 7 * NA, NQ, "measured joint velocities, the joints of joint_pos (rad/s; m/s for the fingers)"],
    "gripper_opening": [2 * NQ + 7 * NA, NA, "measured aperture per arm (m): finger_left + finger_right, 0 closed .. 0.08 open"],
    "joint_effort": [2 * NQ + 8 * NA, 7 * NA, "the servo's commanded motor torques per arm, joint1..7 (N m)"],
    "tool_pose": [2 * NQ + 15 * NA, 7 * NA, "the pose of each arm's task tool (its tool frame; the hand TCP when the arm has none), x y z + wxyz, world frame"],
    "target": [2 * NQ + 22 * NA, 8 * NA, "each arm's current target row (the last joint_position row the servo received: joint1..7, aperture)"],
}
assert 2 * NQ + 30 * NA == len(PROPRIO_LAYOUT)
RS = S.robot_spec()


def _link_T(uid: str, parent: str, child: str) -> list:
    """The fixed transform parent link -> child frame (4x4), read from the articulation's own link poses."""
    links = {l.entity.name: l for l in S.u.arms[uid].robot.links}
    P, C = links[parent].entity_pose, links[child].entity_pose
    return (P.inv() * C).to_transformation_matrix().round(6).tolist()


def robot_spec() -> dict:
    """The robot's spec sheet in the eai-standard/2.2 shape (STANDARD_MODE.md): joints with their limits, the grippers and
    their command, the servo and its gains, the TCP and tool frames, the bases. Nothing about the scene."""
    L = LIM; sv = RS["servo"]
    joints, gains = [], {}
    for uid in ARMS:
        for i in range(7):
            joints.append({"name": f"{uid}_joint{i + 1}", "type": "revolute", "unit": "rad",
                           "position_limits": [float(L.LOWER[i]), float(L.UPPER[i])], "velocity_limit": float(L.VELOCITY[i]),
                           "effort_limit": float(L.TORQUE[i]), "group": f"{uid}_arm",
                           "note": f"the servo's reference moves at most {sv['max_joint_velocity'][i]:.4g} rad/s"})
            gains[f"{uid}_joint{i + 1}"] = {"stiffness": float(sv["kp"][i]), "damping": float(S.u.arms[uid].servo.kd[i])}
        for f in ("finger_left", "finger_right"):
            joints.append({"name": f"{uid}_{f}", "type": "prismatic", "unit": "m", "position_limits": [0.0, 0.04],
                           "velocity_limit": float(sv["finger_max_velocity_m_s"]), "effort_limit": float(L.FINGER_FORCE),
                           "group": f"{uid}_gripper"})
            gains[f"{uid}_{f}"] = {"stiffness": float(sv["kp"][7]), "damping": float(S.u.arms[uid].servo.kd[7])}
    base = {uid: {"type": "fixed", "link": f"{uid}_panda_link0", "pose": RS["arms"][uid]["base_pose"]} for uid in ARMS}
    tcp = {f"{uid}_tcp": {"parent_link": f"{uid}_panda_hand", "link_T_frame": _link_T(uid, "panda_hand", "panda_hand_tcp"),
                          "definition": "panda_hand_tcp: the point between the fingertips on the hand's axis (ManiSkill's Panda TCP); "
                                        "the proprio tcp_pose columns and the safety limits' TCP use it"} for uid in ARMS}
    for uid in ARMS:
        if RS["arms"][uid]["tool"]:
            tcp[f"{uid}_tool"] = {"parent_link": f"{uid}_panda_hand", "link_T_frame": _link_T(uid, "panda_hand", "tool"),
                                  "definition": f"the frame of the task tool ({RS['arms'][uid]['tool']}) fixed to the hand; the proprio "
                                                "tool_pose columns use it"}
    return {
        "name": "franka-panda" if NA == 1 else "franka-panda-bimanual",
        "description": ("one stock Franka Panda (FER: 7 revolute joints, the standard hand with two prismatic fingers)" if NA == 1 else
                        "two stock Franka Panda (FER) arms, panda-0 (left) and panda-1 (right), each with the standard hand") +
                       ", each hand carrying the task's rigid tool where it has one (spec.static.arms); fixed bases",
        "base": {"type": "fixed", "link": base[ARMS[0]]["link"], "pose": base[ARMS[0]]["pose"], "per_arm": base,
                 "note": "fixed-base arms; `pose` is panda-0's, `per_arm` has every arm's"},
        "joints": joints,
        "grippers": {f"{uid}_gripper": {"joints": [f"{uid}_finger_left", f"{uid}_finger_right"], "finger_travel_m": [0.0, 0.04],
                                        "command": {"index": 8 * i + 7, "range": [0.0, M.APERTURE_MAX], "unit": "m",
                                                    "rule": "the total aperture target: each finger goes to half of it, at most "
                                                            f"{sv['finger_max_velocity_m_s']} m/s, with at most {L.FINGER_FORCE:g} N"},
                                        "opening_m": [0.0, M.APERTURE_MAX], "tcp_frame": f"{uid}_tcp"} for i, uid in enumerate(ARMS)},
        "controller": {"type": "torque servo per arm: every control step the latest target row is turned into a jerk-limited reference "
                               "motion (Ruckig, joints synchronised) and tracked by PD + inverse dynamics with gravity compensation, the "
                               "Panda's torque and torque-rate limits applied (native joint drives off)",
                       "control_hz": float(CTRL_HZ), "physics_hz": 1000.0, "gains": gains,
                       "reference_limits": {"max_joint_velocity": sv["max_joint_velocity"], "max_joint_acceleration": sv["max_joint_acceleration"],
                                            "max_joint_jerk": sv["max_joint_jerk"]},
                       "torque_limit_nm": sv["torque_limit_nm"], "torque_rate_limit_nm_s": sv["torque_rate_limit_nm_s"],
                       "safety_limits": {**RS["safety_limits"], "note": "the Panda's limits the task checks every 1 ms (measured and in the "
                                                                         "servo's reference); exceeding one ends the episode as limit_violation"},
                       "note": "stiffness N m/rad (N/m for the fingers), damping N m s/rad (N s/m); the reference limits are the "
                               "task's fractions of the Panda's limits"},
        "tcp": tcp}


ROBOT_SPEC = robot_spec()
KIN = {"endpoint": "/kinematics", "joint_names": [f"{a}_{j}" for a in ARMS for j in JOINTS], "frame": "world", "quaternion_order": "wxyz",
       "links": [f"{a}_{k}" for a in ARMS for k in ("tcp", "tool", "hand")], "tcp_frames": [f"{a}_tcp" for a in ARMS],
       "ee_frames": [f"{a}_tool" for a in ARMS], "ik_targets": [f"{a}_{k}" for a in ARMS for k in ("tcp", "tool")],
       "ik": {"tol_pos_m": 0.0015, "tol_rot_rad": 0.005, "max_iters": 500, "note": "the arm's own Pinocchio model, joint limits enforced; "
                                                                                     "an unreachable target gives ok = false"},
       "note": "stateless: forward / inverse kinematics of the arms' own models (no physics, no simulated time). `tool` is the task "
               "tool's frame (the hand TCP when the arm has none), `hand` the panda_hand link"}

SPEC = {
    "protocol": PROTOCOL, "protocol_compat": list(L.COMPAT), "simulator": "maniskill (Panda Dynamic Scenes on ManiSkill 3.0.1 / SAPIEN 3.0.3, CPU PhysX at 1000 Hz)",
    "robot": "franka-panda" if NA == 1 else "franka-panda-bimanual",
    "task_text": TEXTS["task_text"] + f" A call returns at most {MAX_FRAMES} images (cameras x frames, per-frame depth counted again).",
    "control_hz": CTRL_HZ, "physics_hz": 1000, "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "on_service_error": L.ON_SERVICE_ERROR,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": [int(FIRST[c].shape[1]), int(FIRST[c].shape[0])],
                    "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": CAM0[c]["intrinsic_cv"], "mount": CAM0[c]["mount"],
                    "depth_range_m": CAM0[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": ACTION_DIM, "layout": LAYOUT, "dtype": "float64 (executed as sent; rcb_client.submit sends float32)",
                           "units": "rad for <arm>_joint1..7 (absolute targets); <arm>_aperture: the total gripper opening target in metres "
                                    "(0 = closed .. 0.08 = open)",
                           "limits": LIMITS,
                           "semantics": "the environment's own action, one row per 10 ms control step: each arm's servo turns its latest "
                                        "targets into a jerk-limited reference motion (Ruckig, joints synchronised) within its speed, "
                                        "acceleration and jerk limits (robot_spec.servo) and tracks it with torque control; rows `dt` apart (a "
                                        "multiple of 0.01 s, at most 0.5 s; anything else is rejected, never rounded), hold or linear "
                                        "interpolation of the targets between rows; out-of-limit values are clipped and reported"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_pose", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": GROUPS,
    "static": {"arms": {a: {"role": RS["arms"][a]["role"], "tool": RS["arms"][a]["tool"]} for a in ARMS}},
    "world": {"frame": "the scene's world frame: z up, the table top is the plane z = 0; the arm bases are in robot_spec.arms",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes (x right, y up, z back)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "3600")), "clock": L.CLOCK_NOTE},
    "max_control_steps": int(round(float(I["horizon_s"]) * CTRL_HZ)),
    "episode": TEXTS["episode"],
    "robot_spec": ROBOT_SPEC,
    "kinematics": KIN,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)       # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()         # the watchdog stands down: a long resume replay below is not a hung build


def check_success() -> bool:
    return S.success()


def proprio_row() -> np.ndarray:
    P = S.proprio()
    cols = ([v for a in ARMS for v in P[a]["q"]] + [v for a in ARMS for v in P[a]["tcp_pose"]] + [v for a in ARMS for v in P[a]["qd"]]
            + [P[a]["aperture"] for a in ARMS] + [v for a in ARMS for v in P[a]["torque"]] + [v for a in ARMS for v in P[a]["tool_pose"]]
            + [v for a in ARMS for v in P[a]["target"]])
    return np.array(cols, dtype=np.float32)


def grab(cams, want_depth: bool):
    rgb = {c: S.render_frame(c) for c in cams}
    return rgb, ({c: S._depth_of(c) for c in cams} if want_depth else {})


EXT = {c: np.asarray(CAM0[c]["extrinsic_cv"], dtype=np.float64) for c in CAMS}


def extrinsics(cams) -> dict:
    return {c: EXT[c] for c in cams}                       # static cameras


def video_fps(meta: dict) -> int:
    """The request's frame rate (default 10): outside [1, 50] it is a 400, never a failed encode that would end the episode."""
    fps = meta.get("video_fps")
    if fps is None:
        return 10
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 50):
        raise ValueError("video_fps must be in [1, 50]")
    return int(fps)


# ---------------------------------------------------------------- request fields
# PROTOCOL §4.6: a malformed request is a 400 and executes nothing. Every field is read and checked by the functions below
# BEFORE the first control step; a field that is absent or JSON null takes its default, a value of the wrong type or out
# of range is a ValueError (the layer's 400). as_400() turns anything else a bad value can raise while it is being read into
# that 400 too: only an error while the simulator is stepping is a simulator error (500, the episode ends).
def number(meta: dict, key: str, default: float) -> float:
    v = meta.get(key)
    if v is None:
        return float(default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{key} must be a finite number")
    return float(v)


def choice(meta: dict, key: str, default: str, allowed: tuple) -> str:
    v = meta.get(key)
    if v is None:
        return default
    if not isinstance(v, str) or v not in allowed:
        raise ValueError(f"{key} must be {'|'.join(allowed)}")
    return v


def cameras(meta: dict) -> list:
    v = meta.get("cameras")
    if v is None:
        return list(CAMS)
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(c, str) for c in v):
        raise ValueError(f"cameras must be a list of camera names ({', '.join(CAMS)})")
    return list(dict.fromkeys(c for c in v if c in CAMS)) or list(CAMS)


def note_text(meta: dict) -> str:
    v = meta.get("note")
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValueError("note must be a string")
    return v[:500]


def as_400(parse: Callable, *args):
    try:
        return parse(*args)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 -- nothing has been executed yet: a bad request, not a simulator error
        raise ValueError(f"malformed request: {exc!r}"[:300]) from None


def frames_check(cams, steps: int, fps: int, meta: dict, video: str) -> None:
    """A call that would return more images than max_frames_per_call is a 400, before anything moves."""
    deep = L.depth_mode(meta) == "frames"
    if video == "none" and not deep:
        n = 2
    else:
        n = steps // max(1, int(round(CTRL_HZ / max(1, fps)))) + 2
    L.check_frames(len(cams), n, depth_frames=deep, limit=MAX_FRAMES)


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    cal = {c: {k: CAM0[c][k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c in cams}
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3), "time_s": round(L.agent_time(E), 2),
            "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            **({"cameras": cal} if OBS_CALIBRATION else {})}


def save_call_evidence(idx: int, meta: dict, rec: L.Recorder) -> None:
    d = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(d, exist_ok=True)
    L._write_json(os.path.join(d, "meta.json"), L._jsonable(meta))
    try:
        from PIL import Image
        for c in rec.cams:
            fr = [f for f in rec.frames[c] if f is not None]
            if fr: Image.fromarray(np.ascontiguousarray(fr[-1])).save(os.path.join(d, f"last_{c}.jpg"), quality=85)
    except Exception:  # noqa
        pass


# ---------------------------------------------------------------- executing chunks
def clip_row(row: np.ndarray, clipped: list, ri: int) -> np.ndarray:
    r = row.copy()
    for j, name in enumerate(LAYOUT):
        lo, hi = LIM_ARR[j]
        if r[j] < lo or r[j] > hi:
            clipped.append({"row": ri, "index": int(j), "reason": f"{name} limit [{lo:.4f},{hi:.4f}]"}); r[j] = float(np.clip(r[j], lo, hi))
    return r


def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool:
    """One recorded control step, journaled for crash recovery. True when the call must stop here: the episode is over
    (success or failure), or the service stops the call (max_call_wall_s, the client hung up)."""
    a = np.asarray(a, dtype=np.float64)                    # the exact row Session.step executes (and records)
    over = S.step(a); stop = EP.journal(a); rec.tick()
    if over: finish(S.end_reason() or "error")
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = int(round(dt * CTRL_HZ))
    q_prev = np.asarray(S.actions()[-1] if S.n_steps else S.hold_action(), dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            if ctrl_step(a, rec): return
        q_prev = target


def parse_submit(meta: dict, A: np.ndarray) -> tuple:
    """Every field of a /submit, checked; nothing is executed here."""
    typ = meta.get("type")
    if not isinstance(typ, str) or typ != "joint_position":
        raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", 1.0 / CTRL_HZ); interp = choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = cameras(meta); fps = video_fps(meta); video = choice(meta, "video", "mp4", ("mp4", "frames", "both", "none"))
    note = note_text(meta); L.depth_mode(meta)
    if A.ndim != 2 or A.shape[1] != ACTION_DIM: raise ValueError(f"{typ} actions must be (T, {ACTION_DIM}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.2f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 0.01 s control period (k/100 s, k = 1..50); got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    frames_check(cams, int(round(A.shape[0] * dt * CTRL_HZ)), fps, meta, video)
    return typ, dt, interp, cams, fps, video, note


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ, dt, interp, cams, fps, video, note = as_400(parse_submit, meta, A)       # a 400 before anything moves
    rec = recorder(cams, fps, meta); clipped: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    run_joint_position(A, dt, interp, rec, clipped)
    rec.tick(force=True, last=True)
    succ = E["success"] or check_success(); E["success"] = succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": note,
         "depth": rec.mode, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "success": succ,
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def parse_observe(meta: dict) -> tuple:
    """Every field of an /observe, checked; nothing is executed here."""
    cams = cameras(meta); seconds = number(meta, "seconds", 0.0); fps = video_fps(meta)
    video = choice(meta, "video", "frames", ("mp4", "frames", "both", "none")); L.depth_mode(meta)
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if abs(seconds * CTRL_HZ - round(seconds * CTRL_HZ)) > 1e-6:
        raise ValueError(f"seconds must be a multiple of the 0.01 s control period; got {seconds}")
    frames_check(cams, int(round(seconds * CTRL_HZ)), fps, meta, video if seconds > 0 else "none")
    return cams, seconds, fps, video


def do_observe(meta: dict) -> tuple[dict, list]:
    cams, seconds, fps, video = as_400(parse_observe, meta)                       # a 400 before anything moves
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(S.actions()[-1] if S.n_steps else S.hold_action(), dtype=np.float64)   # the last targets stay in force
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
        rec.tick(force=True, last=True)
        succ = E["success"] or check_success(); E["success"] = succ
        if succ: finish("success")
    else:
        rec.tick(force=True, last=True)                    # the current frames: no physics
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "depth": rec.mode, "control_steps": ctrl_steps() - before,
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    """Stateless FK / IK on the arms' own Pinocchio models (never the simulator; req already checked by rcb_limited)."""
    names = KIN["joint_names"]
    if req["op"] == "fk":
        q = np.asarray(req["q"], dtype=np.float64)
        poses = {}
        for i, a in enumerate(ARMS):
            fk = S.fk(q[7 * i:7 * i + 7], a)
            for k in ("tcp", "tool", "hand"):
                if f"{a}_{k}" in req["links"]:
                    poses[f"{a}_{k}"] = fk[k]
        return L.fk_response(poses, "world")
    seed = np.asarray(req["seed"], dtype=np.float64) if req["seed"] is not None else np.asarray(
        [v for a in ARMS for v in S.proprio()[a]["q"][:7]], dtype=np.float64)
    q = seed.copy(); ok = True; errors = {}
    for frame, pose in req["targets"].items():
        a, k = frame.rsplit("_", 1); i = ARMS.index(a)
        try:
            q[7 * i:7 * i + 7] = S.ik(pose, a, frame=k, seed=seed[7 * i:7 * i + 7])
        except ValueError:
            ok = False
    for frame, pose in req["targets"].items():
        a, k = frame.rsplit("_", 1); i = ARMS.index(a)
        got = np.asarray(S.fk(q[7 * i:7 * i + 7], a)[k], dtype=np.float64)
        pe = float(np.linalg.norm(got[:3] - np.asarray(pose[:3]))); re = L.quat_angle(got[3:], np.asarray(pose[3:]))
        errors[frame] = (pe, re)
        ok = ok and pe <= req["tol_pos_m"] and re <= req["tol_rot_rad"]
    assert len(q) == len(names)
    return L.ik_response(q, ok, errors, "world")


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "rows": ctrl_steps(), "sim_steps": ctrl_steps() * SUBSTEPS,
            "done": E["done"], "reason": E["reason"], "elapsed_s": round(time.time() - E["t0"], 1)}


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (rcb_limited.Episode runs this in a thread): end the episode, dump it, exit 0."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        else: dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped, releasing the simulator for the fresh-process replays"})
        if not os.path.exists(PID_FILE):   # a SIGUSR1 that came in during a resume: the hook still needs to see this process end
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the memory: finalize.sh starts the replays once this process is gone


def replay_row(row) -> None:
    """One journaled row during a resume (no rendering asked for). A row the scene can no longer take (the episode ended
    earlier than logged) is skipped: the state hash check then refuses the resume (class exact)."""
    if not S.done:
        S.step(np.asarray(row, dtype=np.float64))


EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": TASK, "cameras": CAMS, "initial_sha": S.initial_sha})
if S.done and not E["done"]:       # a resume whose journal ends with the episode's last step
    finish(S.end_reason() or "error")
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
