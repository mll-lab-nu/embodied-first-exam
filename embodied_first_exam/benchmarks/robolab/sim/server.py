"""eai-standard/2.2 sim service for NVIDIA RoboLab (Isaac Lab 2.3 / Isaac Sim 5.1, Franka + Robotiq 2F-85; see
docs/protocol/standard_mode.md). Owns the scene. HTTP surface (rcb_limited): GET /spec, GET /status, POST /observe,
POST /submit, POST /kinematics (RCB1 bodies, RCB1 responses: videos / frames / depth / proprio as raw blobs, never base64).
Logs every call to /data/episode.jsonl and keeps /data/final.json current. Nothing about objects ever leaves this process.

Crash recovery (rcb_limited.Episode, docs/protocol/standard_mode.md §13, resume class `exact`): every executed control step is
journaled (the 8-D float32 row handed to Session.step), every completed call is checkpointed with the scene's state hash.
After a crash compose restarts the container (`restart: on-failure:6`, run.sh exits non-zero) and this service, a fresh
process, rebuilds the frozen scene, replays the journal up to the last checkpoint (its first replay: bit-exact with PhysX
on the CPU), checks the state hash and continues the SAME episode, never a reset.

Differences from the RoboTwin service, all from the simulator:
- rows are streamed at the 15 Hz CONTROL rate (the recorded step: sim dt 1/120 s x decimation 8); the joint action is
  RoboLab's own (7 Franka joint targets + the binary Robotiq command, which is switched, never interpolated);
- `ee_pose` is driven by Isaac Lab's differential IK in closed loop (one update per control step, as the privileged-mode
  `move_ee` primitive does it), not by a planner;
- the wrist camera moves: every frame carries each camera's pose (the wrist one from the gripper link's measured pose and
  the camera's fixed mount), depth comes from the same renders as the RGB, /kinematics from a numpy model of the arm
  (rcb_robolab: camera_info, render_depth, proprio, kinematics: the privileged tooling's own calls);
- the episode is graded as it ran (owner 2026-10-17: no grading replay). When it ends the service
  writes /data/trajectory.npz (the deliverable) + /data/episode.json (the live result: RoboLab's success term, checked
  after every control step and through the hold of the last command after the agent's phase; the end-state hash); the
  collect hook's SIGUSR1 makes it exit, and environment/sim/finalize.sh writes /data/final.json from it;
- the start state is checked before the agent is served: the rebuilt scene against the frozen instance's recorded state
  (instance.json `state_sha`, else every object pose and robot joint within the tooling's tolerance); a scene that matches
  neither ends the trial as an infrastructure failure (`instance_mismatch`, a give-up: nothing is served);
- the video is filmed live (live_video.py): Isaac Lab renders every camera with each control step anyway, so a frame (the
  viewport cameras + the wrist camera, the tooling's own video frame) is kept every 3 control steps (5 per simulated
  second) as a JPEG file; the collect hook encodes live.mp4 after the verdict."""
from __future__ import annotations
import math, os, sys, threading, time, traceback
from typing import Callable
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402
import live_video  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "banana_in_bowl"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 15; SUBSTEPS = 8; ACTION_DIM = 8
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
LOCK = threading.Lock(); PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
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
                   "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        acts = S.record_stop(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts))
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"],
                                                                            "reason": E["reason"], "resumes": EP.resumes})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
                   "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), "settle_steps": E.get("settle_steps"),
                   **({"settle_error": E["settle_error"]} if E.get("settle_error") else {}), **INSTANCE_CHECK, **EP.final_fields()})
    write_final()
    VIDEO.last(ctrl_steps())  # after the verdict is on disk: a render that fails or hangs here never costs it


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    if reason == "timeout" and not E["success"] and not S.episode_done and ctrl_steps():
        # the agent's phase is over: the last command is held for up to SETTLE_STEPS control steps on the live simulator
        # (journaled and recorded: the trajectory holds them) while RoboLab's term is checked, as the privileged grader's
        # replay does after a trajectory's last row; the live verdict includes this hold
        try:
            hold = np.asarray(S.hold_action(), dtype=np.float32); n = 0
            while n < M.SETTLE_STEPS and not S.episode_done:
                n += 1; S.step(hold); EP.journal(hold); VIDEO.offer(ctrl_steps())
            E["settle_steps"] = n
        except Exception as exc:  # noqa: BLE001 -- a simulator error during the hold: recorded; the term is judged as it stands
            traceback.print_exc(); E["settle_error"] = repr(exc)[:300]; log({"ev": "settle_error", "error": E["settle_error"]})
    E["episode_control_steps"] = ctrl_steps()
    if not E["success"]:
        try: E["success"] = check_success()
        except Exception: pass
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    dump()


# ---------------------------------------------------------------- scene
import rcb_robolab as M  # noqa: E402
S = M.Session(TASK, instance=INSTANCE, strict=False, depth=True)   # the start-state check is below (instance_mismatch)
# The frozen initial state, checked before anything is served: the rebuilt scene's state hash against instance.json's
# `state_sha`; a differing hash with every object pose and robot joint within the tooling's tolerance is accepted
# (another host's last bits, as the tooling's strict mode does), anything else is an infrastructure failure.
INSTANCE_CHECK = {"instance_sha": S.instance_sha, "instance_expected_sha": L._read_json(INSTANCE).get("state_sha"),
                  "instance_exact": bool(S.instance_exact), "instance_matches": bool(S.instance_matches)}
if not S.instance_matches:
    L._write_json(os.path.join(DATA, "final.json"), {"task": TASK, "protocol": PROTOCOL, "instance_mismatch": True, **INSTANCE_CHECK})
    EP.give_up(f"instance_mismatch: the rebuilt scene (state {S.instance_sha}) is not the frozen instance "
               f"({INSTANCE_CHECK['instance_expected_sha']}) and its poses differ", infra=True)   # never returns
VIDEO = live_video.LiveVideo(DATA, ctrl_hz=CTRL_HZ, frame=S._video_frame, log=EP.log)   # Isaac Lab renders every step anyway
LAYOUT = [f"panda_joint{i}" for i in range(1, 8)] + ["gripper"]
MOUNT = {"wrist_cam": "on the gripper (wrist)", "over_shoulder_left_camera": "static, over the robot's left shoulder",
         "egocentric_mirrored_camera": "static, facing the robot across the table"}


def images() -> dict:
    """Every camera on its own: RoboLab's viewport cameras and its image-observation cameras (the wrist)."""
    from robolab.core.observations.observation_utils import unpack_image_obs, unpack_viewport_cams
    out = {}
    for fn in (unpack_viewport_cams, unpack_image_obs):
        try:
            for k, v in fn(S._obs, env_id=0).items():
                if k != "combined_image":
                    out[k] = np.ascontiguousarray(np.asarray(v)[..., :3].astype(np.uint8))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    return out
FIRST = images(); CAMS = [c for c in ("egocentric_mirrored_camera", "over_shoulder_left_camera", "wrist_cam") if c in FIRST] + \
    sorted(c for c in FIRST if c not in ("egocentric_mirrored_camera", "over_shoulder_left_camera", "wrist_cam"))


def joint_limits() -> dict:
    lim = S.robot.data.soft_joint_pos_limits[0, S.arm_ids].detach().cpu().numpy()
    out = {n: [round(float(lo), 4), round(float(hi), 4)] for n, (lo, hi) in zip(LAYOUT[:7], lim)}
    out["gripper"] = [0.0, 1.0]
    return out
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)   # (8, 2)
CAM0 = S.camera_info(CAMS)
JOINTS8 = LAYOUT[:7] + ["finger_joint"]
PROPRIO_LAYOUT = JOINTS8 + ["x", "y", "z", "qw", "qx", "qy", "qz", "gripper_cmd"] + [f"{j}_vel" for j in JOINTS8] + ["gripper_opening_m"] + \
    [f"{j}_effort" for j in LAYOUT[:7]]

SPEC = {
    "protocol": PROTOCOL, "protocol_compat": list(L.COMPAT), "simulator": "robolab (Isaac Lab 2.3 / Isaac Sim 5.1)", "robot": "franka-robotiq-2f85",
    "task_text": S.spec["text"], "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT.get(c, "static"), "resolution": [int(FIRST[c].shape[1]), int(FIRST[c].shape[0])],
                    "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": CAM0[c]["intrinsic_cv"], "mount": CAM0[c]["mount"],
                    "depth_range_m": CAM0[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": 8, "layout": LAYOUT, "units": "rad for panda_joint1..7; gripper command 0 = open, 1 = closed (binary Robotiq action)",
                           "limits": LIMITS,
                           "semantics": "absolute joint targets tracked by the robot's PD controllers, streamed at the 15 Hz control rate; rows `dt` apart "
                                        "(a multiple of 1/15 s, at most 0.5 s; anything else is rejected, never rounded), hold or linear interpolation between "
                                        "rows for the arm joints; the gripper command is binary and switches at the row, never interpolated; out-of-limit "
                                        "values are clipped and reported"},
        "ee_pose": {"dim": 8, "layout": ["x", "y", "z", "qw", "qx", "qy", "qz", "gripper"],
                    "frame": "env-local = the robot's root frame (Franka base at the origin, x forward towards the table, z up), metres",
                    "quaternion": "wxyz, unit norm",
                    "semantics": "each row is driven to by Isaac Lab's differential IK in closed loop (one update per control step along a straight "
                                 "line, at most 0.25 m/s), `dt` is ignored; a row that does not converge within 6 mm is reported in plan[]",
                    "note": "the pose is the FINGERTIP-CENTRE tool frame: RoboLab's eef_frame (the gripper flange) moved 0.162 m along the approach "
                            "axis to the ends of the closed fingertips; same convention as the proprio end-effector pose"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": {
        "joint_pos": [0, 8, "measured joint positions (rad): panda_joint1..7, then finger_joint (the Robotiq's driven knuckle: 0 open .. pi/4 closed)"],
        "tcp_pose": [8, 7, "measured fingertip-centre (tcp) pose: x y z (m) + quaternion wxyz, world frame (the 2.0 columns)"],
        "gripper_cmd": [15, 1, "the gripper command in force: 0 open, 1 closed"],
        "joint_vel": [16, 8, "measured joint velocities (rad/s), the joints of joint_pos"],
        "gripper_opening": [24, 1, "measured distance between the Robotiq finger pads (m): ~0.085 fully open, ~0.002 closed on nothing; "
                                   "a gripper closed on something stops above that"],
        "joint_effort": [25, 7, "drive-effort estimate of panda_joint1..7 (N m): stiffness * (target - q) + damping * (0 - qdot) of their PD "
                                "drives, clipped to effort_limit (a motor-current analogue: it grows when the arm pushes on something)"]},
    "static": {},
    "world": {"frame": "env-local = the robot's root frame: the Franka base (panda_link0) at the origin, x forward (towards the table), y to the robot's left, z up",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes (x right, y up, z back)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))},
    # PROTOCOL §4.5: no step budget, but a technical cap is stated here. The tooling's runaway guard ends the episode after
    # MAX_STEPS control steps (reason "step_guard"); at this service's 3-15 control steps/s the wall clock ends it first.
    "max_control_steps": int(M.MAX_STEPS),
    "episode": "one episode, no reset: it ends at the first control step where RoboLab's success term holds (checked after every "
               "control step; \"the gripper\" is both Robotiq fingers), when your time is up (the last command is then held for "
               f"{M.SETTLE_STEPS} more control steps while the term is checked), on a simulator error, or after {int(M.MAX_STEPS):,} control steps "
               f"({M.MAX_STEPS / CTRL_HZ / 60:.0f} min of simulated time: a technical cap, reason \"step_guard\", "
               "spec.max_control_steps; graded as it stands)",
    "robot_spec": S.robot_spec(),
    "kinematics": S.kinematics_spec(),
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)       # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()         # the watchdog stands down: a long resume replay below is not a hung build


def check_success() -> bool:
    res = S.env.get_env_results()[0]
    ok = res.get("success")
    if ok is None:
        ok = bool(S.env.termination_manager.get_term("success")[0].item())
    return bool(ok)


def proprio_row() -> np.ndarray:
    P = S.proprio()
    return np.array(P["joint_pos"] + P["tcp_pose"] + [P["gripper_cmd"]] + P["joint_vel"] + [P["gripper_opening"]] + P["joint_effort"], dtype=np.float32)


def grab(cams, want_depth: bool):
    imgs = images()
    return {c: imgs.get(c) for c in cams}, ({c: S.render_depth(c) for c in cams} if want_depth else {})


def extrinsics(cams) -> dict:
    return {c: np.asarray(ci["extrinsic_cv"], dtype=np.float64) for c, ci in S.camera_info(cams).items()}


def video_fps(meta: dict) -> int:
    """The request's frame rate (default 5): outside [1, 30] it is a 400 (2.1's rule), never a failed encode that would end
    the episode."""
    fps = meta.get("video_fps")
    if fps is None:
        return 5
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


# ---------------------------------------------------------------- request fields
# PROTOCOL §4.6: a malformed request is a 400 and executes nothing. Every field is read and checked by the functions below
# BEFORE the first control step; a field that is absent or JSON null takes its default, a value of the wrong type or out
# of range is a ValueError (the layer's 400). as_400() turns anything else a bad value can raise while it is being read
# (TypeError, OverflowError, AttributeError, ...) into that 400 too: only an error while the simulator is stepping is a
# simulator error (500, the episode ends).
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
    return [c for c in v if c in CAMS] or list(CAMS)


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


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    cal = {c: {k: ci[k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c, ci in S.camera_info(cams).items()}
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(L.agent_time(E), 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
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
def clip_joint_row(row: np.ndarray, clipped: list, ri: int) -> np.ndarray:
    r = row.copy()
    for j, name in enumerate(LAYOUT):
        lo, hi = LIM_ARR[j]
        if r[j] < lo or r[j] > hi:
            clipped.append({"row": ri, "index": int(j), "reason": f"{name} limit [{lo:.3f},{hi:.3f}]"}); r[j] = float(np.clip(r[j], lo, hi))
    return r


def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool:
    """One recorded control step, journaled for crash recovery. True when the call must stop here: the episode is over
    (RoboLab's success term also terminates it), or the service stops the call (max_call_wall_s, the client hung up)."""
    a = np.asarray(a, dtype=np.float32)                    # the exact row Session.step executes (and records)
    over = S.step(a); stop = EP.journal(a); rec.tick(); VIDEO.offer(ctrl_steps())
    if over: finish("success" if check_success() else "step_guard")
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = int(round(dt * CTRL_HZ))
    q_prev = np.asarray(S.hold_action(), dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            a[7] = target[7]                               # the binary gripper switches, it is never ramped
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list) -> None:
    speed, max_dq, tol = 0.25, 0.08, 0.006
    for ri, row in enumerate(A):
        E["step"] += 1
        p1 = np.asarray(row[0:3], dtype=np.float64); q1 = np.asarray(row[3:7], dtype=np.float64); q1 = q1 / max(1e-9, float(np.linalg.norm(q1)))
        grip = float(np.clip(row[7], 0.0, 1.0)); p0, _ = S.ee_pose()
        n_way = max(1, int(math.ceil(float(np.linalg.norm(p1 - p0)) / (speed / CTRL_HZ))))
        st, err = "not converged", None
        for i in range(n_way + 80):
            wp = p1 if i >= n_way else p0 + (p1 - p0) * ((i + 1) / n_way)
            try:
                q_des = S.ik_step(wp, q1)
            except Exception as exc:  # noqa: BLE001
                st = f"failed: {str(exc)[:80]}"; break
            cur = np.asarray(S.hold_action(), dtype=np.float64); a = cur.copy()
            a[0:7] = cur[0:7] + np.clip(q_des - cur[0:7], -max_dq, max_dq); a[7] = grip
            if ctrl_step(a, rec): st = "episode over" if E["done"] else f"stopped ({EP.stop_reason})"; break
            err = float(np.linalg.norm(S.ee_pose()[0] - p1))
            if i >= n_way and err < tol: st = "Success"; break
        plan.append({"row": ri, "arm": st, "ee_error_m": None if err is None else round(err, 4)})
        if E["done"] or EP.stopping: return


EE_POS_MAX_M = 2.0       # an ee_pose target further than this from the robot's base on any axis is a 400 (the arm reaches < 1 m)


def check_ee_rows(A: np.ndarray) -> None:
    """ee_pose rows that cannot be meant (PROTOCOL §4.6: a 400, nothing executed): a position outside the +-EE_POS_MAX_M
    box around the robot's base (a unit slip; such a row used to run thousands of control steps towards nowhere, and a
    huge value ended the episode with a simulator error), or a quaternion of zero length."""
    for ri, row in enumerate(A):
        if float(np.max(np.abs(row[0:3]))) > EE_POS_MAX_M:
            raise ValueError(f"ee_pose row {ri}: position {[round(float(v), 4) for v in row[0:3]]} is outside the +-{EE_POS_MAX_M} m box "
                             f"around the robot's base (metres, the robot's root frame)")
        if float(np.linalg.norm(row[3:7])) < 1e-6:
            raise ValueError(f"ee_pose row {ri}: the quaternion (wxyz) has zero length")


def parse_submit(meta: dict, A: np.ndarray) -> tuple:
    """Every field of a /submit, checked; nothing is executed here."""
    typ = meta.get("type")
    if not isinstance(typ, str) or typ not in ("joint_position", "ee_pose"):
        raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", 1.0 / CTRL_HZ); interp = choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = cameras(meta); fps = video_fps(meta); video = choice(meta, "video", "mp4", ("mp4", "frames", "both", "none"))
    note = note_text(meta); L.depth_mode(meta)
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
    if typ == "ee_pose": check_ee_rows(A)
    return typ, dt, interp, cams, fps, video, note


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ, dt, interp, cams, fps, video, note = as_400(parse_submit, meta, A)       # a 400 before anything moves
    rec = recorder(cams, fps, meta); clipped: list = []; plan: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, rec, plan)
    rec.tick(force=True, last=True)
    succ = E["success"] or check_success(); E["success"] = succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": note,
         "depth": rec.mode, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ,
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
    return cams, seconds, fps, video


def do_observe(meta: dict) -> tuple[dict, list]:
    cams, seconds, fps, video = as_400(parse_observe, meta)                       # a 400 before anything moves
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(S.hold_action(), dtype=np.float64)
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
    """Stateless FK / IK on the arm's numpy model (never the simulator; req already checked by rcb_limited)."""
    return S.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (rcb_limited.Episode runs this in a thread): end the episode, dump it, exit 0."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        else: dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped (graded by the live episode), releasing the simulator"})
        if not os.path.exists(PID_FILE):   # a SIGUSR1 that came in during a resume: the hook still needs to see this process end
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the GPU and the memory: finalize.sh writes final.json once this process is gone


def replay_row(row) -> None:
    """One journaled row during a resume (no rendering asked for). A row the scene can no longer take (the episode ended
    earlier than logged) is skipped: the state hash check then refuses the resume (class exact)."""
    if not S.episode_done:
        S.step(np.asarray(row, dtype=np.float32)); VIDEO.offer(ctrl_steps())   # slots already on disk are skipped


S.record_start()         # the resume replay is recorded too: trajectory.npz is the whole episode
VIDEO.offer(0)           # the start state (a restarted service has it on disk already)
resumed = EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": TASK, "seed": S.seed, "cameras": CAMS, "kinematics_check": S.kinematics_check})
if resumed:
    VIDEO.truncate(ctrl_steps())   # frames of the call lost in the crash show rolled-back states
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
