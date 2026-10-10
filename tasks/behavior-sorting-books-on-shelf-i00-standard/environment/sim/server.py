"""eai-standard/2.2 sim service for BEHAVIOR-1K v3.9.2 (OmniGibson on Isaac Sim, the 2026 challenge stack; R1Pro; see
docs/STANDARD_MODE.md): the benchmark's adapter of the shared layer rcb_limited.py. Owns the scene. HTTP surface
(rcb_limited.serve): GET /spec, GET /status, POST /observe, POST /submit (RCB1 bodies and responses: videos / frames /
depth / proprio as raw blobs, never base64), POST /kinematics. Logs every call to /out/episode.jsonl and keeps
/out/final.json current. Nothing about objects ever leaves this process.

Differences from the RoboTwin service, all from the simulator:
- rows are streamed at the 30 Hz CONTROL rate (the recorded step, 120 Hz physics); the joint action is the challenge's
  own 25-D R1Pro action (base x, y, yaw as per-step targets in the robot frame, trunk, both arms, both grippers); the
  base entries and the grippers switch at the row, only the trunk and arm joints are interpolated;
- `ee_pose` rows are solved by cuRobo IK (OmniGibson's motion library; both arms together, the trunk may bend, no
  collision checking) and driven to in joint space; the recorded trajectory is still the joint targets that ran;
- the head and wrist cameras move with the robot: every frame carries the pose it was rendered with (the renderer's
  frames lag the physics by 2 control steps while the robot moves); depth is OmniGibson's depth_linear (z-depth),
  attached before the episode starts; /kinematics is the tooling's stateless FK / IK on the robot's own articulation;
- the episode is NOT replayed here. On Isaac only the first replay in a process is bit-exact, and a second Isaac
  simulator in this container would not fit next to the live one. So when the episode ends the service writes
  /out/trajectory.npz + /out/episode.json (live result and state hash); the collect hook's SIGUSR1 makes it exit, and
  environment/sim/finalize.sh replays the trajectory in two fresh processes and completes /out/final.json;
- the episode ends when the BDDL goal holds (success), when the robot has fallen over (the tooling's fall rule,
  OmniGibson's Falling held for 10 s of simulated time: reason "failure: the robot fell over"), on the collect hook's
  signal (timeout), on a simulator error, or at the tooling's runaway guard (MAX_STEPS control steps, reason
  "step_guard"; /spec max_control_steps); /spec "episode" says so;
- a malformed request is a 400 before anything is executed (PROTOCOL §4.6): every field of /submit and /observe is
  checked first (request_number, request_cameras, request_note, video_fps; dt must be a whole number of control
  periods, it is never rounded), so a wrong type, a null or an out-of-range value never reaches the simulator and never
  ends the episode;
- crash recovery (rcb_limited.Episode, docs/STANDARD_MODE.md §13): every executed control step goes to
  /out/journal.f64, every completed call is checkpointed (rows, state hash, proprio row); after a crash compose restarts
  the container (run.sh exits non-zero) and this service replays the journal and continues the SAME episode. Resume
  class `approx`: OmniGibson declares rollouts nondeterministic, so a hash mismatch after the replay is recorded
  (resume_state_mismatch) and the episode goes on unless a TCP is more than RCB_RESUME_MAX_DEV_M (0.05 m) away from its
  checkpoint. The verdict always comes from the two fresh replays of the whole recorded trajectory."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/out")   # /data is the licensed BEHAVIOR dataset mount here
os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "picking_up_trash"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 30; SUBSTEPS = 4
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
EE_POS_MAX_M = 1000.0                   # ee_pose positions beyond this are a 400 (a units slip; float32-safe for the IK)
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
DIM = 25                                # the R1Pro's action with the task's robot config (asserted once the scene exists)
EP = L.Episode(DATA, dim=DIM, resume="approx")   # crash recovery; approx: OmniGibson declares rollouts nondeterministic
EP.startup()                            # start count, back-off after failed starts, startup watchdog (RCB_STARTUP_TIMEOUT_S)
log = EP.log


def ctrl_steps() -> int:
    return int(S.env.episode_steps) if E["ready"] else 0   # OmniGibson's own counter; the service never resets


def write_final() -> None:
    if L.final_verdict(DATA):           # a verdict on disk (a give-up after crashes) is never overwritten
        return
    n = int(E.get("episode_control_steps") or ctrl_steps())
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": PROTOCOL,
        "finalized": False, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        acts = S.record_stop(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts))
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"], "reason": E["reason"]})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"), {
        "success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
        "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), **EP.final_fields()})
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    if not E["success"]:
        try: E["success"] = check_success()
        except Exception: pass
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    dump()


# ---------------------------------------------------------------- scene
import rcb_behavior as M  # noqa: E402
# the robot's own cameras through the tiny-camera wrapper with RCB_CAM_SIZE raised: real images for the agent without
# paying for full-resolution rendering on every one of several thousand control steps
S = M.Session(TASK, instance=INSTANCE, cameras=os.environ.get("RCB_CAMERAS", "tiny"), strict=True)
BLOCKS = {"base": (0, 3), "trunk": (3, 7), "arm_left": (7, 14), "gripper_left": (14, 16), "arm_right": (16, 23), "gripper_right": (23, 25)}
SWITCH = [0, 1, 2, 14, 15, 23, 24]      # base per-step targets and both grippers: switched at the row, never interpolated
assert int(S.action_dim) == DIM, (S.action_dim, DIM)
LAYOUT = ["base_x", "base_y", "base_yaw"] + [f"trunk_{i}" for i in range(4)] + [f"arm_left_{i}" for i in range(7)] + ["gripper_left_0", "gripper_left_1"] \
    + [f"arm_right_{i}" for i in range(7)] + ["gripper_right_0", "gripper_right_1"]
assert DIM == len(LAYOUT), (DIM, len(LAYOUT))
PRIMS = S.primitives()
S._curobo()                             # the ee_pose IK; built before the episode starts (it steps nothing)
FIRST, _ = S._frames(sorted(S._cam_sensors()))
CAMS = sorted(c for c, a in FIRST.items() if min(a.shape[:2]) >= 32)
S.enable_depth(CAMS)                    # z-depth rendered alongside RGB from now on (attached before the episode: no mid-episode USD edit)
MOUNT = {c: ("head (moves with the base and trunk)" if "zed" in c else "left wrist" if "left" in c else "right wrist" if "right" in c else "on the robot") for c in CAMS}
CAMINFO = S.camera_info(CAMS)
RSPEC = S.robot_spec(); KSPEC = S.kinematics_spec()

# joint_position limits: the joints' real limits for trunk and arms; grippers up to upper + 0.02 (the open command: assisted
# grasping releases only on a command at or above the limit); base entries are per-control-step displacements
_names = list(S.robot.joints)
_idx = {"trunk": S.robot.trunk_control_idx, "arm_left": S.robot.arm_control_idx["left"], "arm_right": S.robot.arm_control_idx["right"],
        "gripper_left": S.robot.gripper_control_idx["left"], "gripper_right": S.robot.gripper_control_idx["right"]}
LIMITS = {"base_x": [-0.15, 0.15], "base_y": [-0.15, 0.15], "base_yaw": [-0.3, 0.3]}
for blk, ji in _idx.items():
    for k, j in enumerate(ji.tolist()):
        lo, hi = float(S.robot.joint_lower_limits[j]), float(S.robot.joint_upper_limits[j])
        LIMITS[f"{blk}_{k}"] = [lo, hi + 0.02] if blk.startswith("gripper") else [lo, hi]
LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)
JN = _names                              # proprio: the 28 joints in robot.get_joint_positions() order (6 virtual base joints first)
POSE = ["x", "y", "z", "qx", "qy", "qz", "qw"]
PROPRIO = JN + [f"base_{k}" for k in POSE] + [f"{a}_eef_{k}" for a in ("left", "right") for k in POSE] \
    + [f"{j}_vel" for j in JN] + ["left_gripper_opening", "right_gripper_opening"] + [f"{a}_tcp_{k}" for a in ("left", "right") for k in POSE] \
    + [f"{j}_effort" for j in JN]
NJ = len(JN); NB = 6                     # 28 joints, the first 6 of them the holonomic base's virtual joints
GROUPS = {"base_joint_pos": [0, NB, "virtual joints of the holonomic base (x, y, z m; rx, ry, rz rad) relative to the robot's start frame (robot_spec.base)"],
          "joint_pos": [NB, NJ - NB, "measured joint positions of robot_spec.joints (rad; the fingers in m): trunk, the arms interleaved left/right, the fingers"],
          "base_pose": [NJ, 7, "base_link world pose x y z qx qy qz qw (the kinematics base frame)"],
          "eef_pose": [NJ + 7, 14, "left, then right end-effector world pose x y z qx qy qz qw (the ee_pose action's frame)"],
          "base_joint_vel": [NJ + 21, NB, "measured velocities of the virtual base joints (m/s, rad/s)"],
          "joint_vel": [NJ + 21 + NB, NJ - NB, "measured joint velocities of robot_spec.joints (rad/s; fingers m/s)"],
          "gripper_opening": [2 * NJ + 21, 2, "left, right: measured opening in m (the two fingers' travel summed: 0 = fingertips touch, 0.1 = fully open; stays above 0 when closed on an object)"],
          "tcp_pose": [2 * NJ + 23, 14, "left, then right fingertip centre (robot_spec.tcp left_tcp / right_tcp) world pose x y z qx qy qz qw"],
          "base_joint_effort": [2 * NJ + 37, NB, "drive efforts of the virtual base joints as PhysX measures them"],
          "joint_effort": [2 * NJ + 37 + NB, NJ - NB, "drive effort per joint of robot_spec.joints (N m; fingers N), the simulator's measured joint force (PhysX), not an estimate"]}
assert GROUPS["joint_effort"][0] + GROUPS["joint_effort"][1] == len(PROPRIO), len(PROPRIO)


def cam_spec(c: str) -> dict:
    i = CAMINFO[c]; near = float(S._cam_fixed()[c]["clip"][0])
    return {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": list(i["image_size"]), "calibration_in_obs": OBS_CALIBRATION,
            "intrinsic_cv": i["intrinsic_cv"], "mount": i["mount"], "depth_range_m": [near, L.DEPTH_MAX_M]}


SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "behavior-1k 3.9.2 (OmniGibson / Isaac Sim)", "robot": "r1pro", "task_text": S.spec["text"],
    "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "max_control_steps": int(M.MAX_STEPS),   # the tooling's runaway guard (PROTOCOL §4.5): the episode ends there, reason "step_guard"
    "cameras": {c: cam_spec(c) for c in CAMS},
    "default_cameras": [c for c in S.VIDEO_CAMERAS if c in CAMS],   # the 2.0 client's default: head, left wrist, right wrist
    "action_types": {
        "joint_position": {"dim": DIM, "layout": LAYOUT, "blocks": {k: list(v) for k, v in BLOCKS.items()},
                           "units": "base x, y (m) and yaw (rad) are per-control-step position targets in the ROBOT frame (re-applied every step: "
                                    "hold them to keep driving); trunk and arm entries are absolute joint targets in rad; each gripper is 2 finger targets, 0 = closed "
                                    "(robot_spec.grippers: the open command is the finger's upper limit + 0.02)",
                           "limits": LIMITS,
                           "semantics": "streamed at the 30 Hz control rate; rows `dt` apart (a multiple of 1/30 s); trunk and arm joints hold or linearly "
                                        "interpolate between rows, the base entries and the grippers switch at the row; out-of-limit values are clipped and reported"},
        "ee_pose": {"dim": 16, "layout": ["l_x", "l_y", "l_z", "l_qx", "l_qy", "l_qz", "l_qw", "left_gripper",
                                          "r_x", "r_y", "r_z", "r_qx", "r_qy", "r_qz", "r_qw", "right_gripper"],
                    "frame": "OmniGibson world frame, metres, +z up (the floor is z = 0)", "quaternion": "xyzw, unit norm",
                    "semantics": "each row: cuRobo inverse kinematics for both end effectors together (trunk + both arms; no collision "
                                 "checking), then the trunk and arm joints are driven there in joint space (at most 0.02 rad per control step); "
                                 "`dt` is ignored; the base stands still; if the IK finds no solution nothing moves and plan[] says so; "
                                 "gripper 1 = open, 0 = closed, switched at the start of the row (closing on an object holds it: assisted grasping)",
                    "note": "the pose is the end-effector frame of the proprio `*_eef_*` entries, so an observed pose is a valid target; at most 50 rows per submit"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO,
    "proprio_groups": GROUPS,
    "static": {"floor_z": 0.0, "frame": "OmniGibson world frame, metres, +z up; the floor is the plane z = floor_z; poses are position + quaternion XYZW"},
    "world": {"frame": "OmniGibson's world frame of the scene: right-handed, z up, the floor is the plane z = 0 (the robot starts on it); "
                       "x and y horizontal. The robot's base frame (robot_spec.base) is its base_link: x forward, y left, z up",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "xyzw",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV (x right, y down, z forward); cam2world_gl: OpenGL (x right, y up, z backward)",
              "camera_timing": "a frame (RGB and depth) shows the scene as rendered 2 control steps (67 ms) before its frame_step while the robot "
                               "moves; its extrinsic_cv is the camera pose it was rendered with, so pixels, depth and pose agree; proprio "
                               "is the state at frame_step"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "14400"))},
    "episode": ("one episode, no reset: it ends the moment the task's goal holds (success); when the robot has fallen over, i.e. its "
                f"base has been tilted more than {math.degrees(math.acos(M.FALL_TILT_TOLERANCE)):.1f} degrees from upright (the z of its up "
                f"axis below {M.FALL_TILT_TOLERANCE}: cos(rx) * cos(ry) of base_footprint_rx_joint / _ry_joint) or more than "
                f"{M.FALL_HEIGHT_M:g} m below the floor for {M.FALL_HOLD_STEPS / CTRL_HZ:g} s of simulated time in a row "
                f"({M.FALL_HOLD_STEPS} control steps; reason \"{M.FALL_REASON}\"); when your time is up (timeout); on a simulator error (error); "
                f"or at the runaway guard of {M.MAX_STEPS} control steps ({M.MAX_STEPS / CTRL_HZ / 3600:.2f} h of simulated time; step_guard). "
                "There is no step budget otherwise"),
    "robot_spec": RSPEC,
    "kinematics": KSPEC,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}


def check_success() -> bool:
    return bool(S.env.task.success)


def proprio_row() -> np.ndarray:
    st = S.robot_state()
    return np.concatenate([st["q"], st["base_pose"], st["eef"]["left"], st["eef"]["right"], st["qd"],
                           [st["gripper_opening"]["left"], st["gripper_opening"]["right"]], st["tcp"]["left"], st["tcp"]["right"], st["effort"]]).astype(np.float32)


def grab(cams, want_depth: bool):
    return S._frames(list(cams), depth=want_depth)


def extrinsics(cams) -> dict:
    sens = S._cam_sensors()
    return {c: np.linalg.inv(S._cam_view(sens[c]) @ M.GL2CV)[:3] for c in cams}


def calib(cams) -> dict:
    return {c: {k: v for k, v in i.items() if k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c, i in S.camera_info(list(cams)).items()}


# ---------------------------------------------------------------- request fields: checked before anything is executed
def request_number(meta: dict, key: str, default: float) -> float:
    """A field that must be a finite number. Absent or null: the default (the client drops None). Anything else that is
    not a finite int / float is a 400 (ValueError), never a TypeError / OverflowError that would end the episode."""
    v = meta.get(key)
    if v is None:
        return float(default)
    try:
        f = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    except OverflowError:
        f = None
    if f is None or not math.isfinite(f):
        raise ValueError(f"{key} must be a finite number, got {str(v)[:60]!r}")
    return f


def video_fps(meta: dict) -> int:
    """The request's frame rate (default 5): outside [1, 30] it is a 400, never a failed encode that would end the
    episode after the chunk ran."""
    if meta.get("video_fps") is None:
        return 5
    fps = request_number(meta, "video_fps", 5)
    if not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


def request_cameras(meta: dict) -> list:
    c = meta.get("cameras")
    if c is None:
        return CAMS
    if not isinstance(c, (list, tuple)) or not all(isinstance(x, str) for x in c):
        raise ValueError("cameras must be a list of camera names (spec['cameras'])")
    return [x for x in c if x in CAMS] or CAMS


def request_note(meta: dict) -> str:
    n = meta.get("note")
    if n is not None and not isinstance(n, str):
        raise ValueError("note must be a string")
    return (n or "")[:500]


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(time.time() - E["t0"], 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - (time.time() - E["t0"]), 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            **({"cameras": calib(cams)} if OBS_CALIBRATION else {})}


def save_call_evidence(idx: int, meta: dict, rec: L.Recorder) -> None:
    d = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(d, exist_ok=True)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"))
    try:
        from PIL import Image
        for c in rec.cams:
            fr = [f for f in rec.frames[c] if f is not None]
            if fr: Image.fromarray(np.ascontiguousarray(fr[-1])).save(os.path.join(d, f"last_{c.replace(':', '_')}.jpg"), quality=85)
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
    """One recorded and journaled control step. True when the call must stop: the episode is over (the BDDL goal holding
    also terminates it), or the layer stops the call (max_call_wall_s, the client hung up)."""
    term, trunc = S.step(a); stop = EP.journal(a); rec.tick()
    if term or trunc: finish("success" if check_success() else (S.end_reason or "step_guard"))
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * CTRL_HZ)))
    q_prev = np.asarray(S.hold_action().cpu(), dtype=np.float64).reshape(-1)   # the last command; base entries 0 = stay
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            a[SWITCH] = target[SWITCH]
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list) -> None:
    idx = S.robot.controller_action_idx
    for ri, row in enumerate(A):
        E["step"] += 1
        tg = {}
        for arm, off in (("left", 0), ("right", 8)):
            q = row[off + 3:off + 7]; tg[arm] = (row[off:off + 3], q / max(1e-9, float(np.linalg.norm(q))))
        cur = np.asarray(S.hold_action().cpu(), dtype=np.float64).reshape(-1)
        goal = cur.copy()
        for arm, off in (("left", 0), ("right", 8)):   # the grippers switch at the start of the row
            goal[np.asarray(idx[f"gripper_{arm}"])] = np.asarray(S._gripper_cmd(arm, bool(row[off + 7] >= 0.5)).cpu(), dtype=np.float64)
        try:
            sol, st = S.ik(tg), None
        except Exception as exc:  # noqa: BLE001
            sol, st = None, f"failed: IK error {repr(exc)[:120]}"; traceback.print_exc()
        if sol is not None and not all(np.all(np.isfinite(v)) for v in sol.values()):
            sol, st = None, "failed: the IK returned a non-finite solution (nothing moved)"
        if sol is not None:
            for part, key in (("trunk", "trunk"), ("left", "arm_left"), ("right", "arm_right")):
                goal[np.asarray(idx[key])] = sol[part]
            st = "Success"
        st = st or "failed: no IK solution for the two end-effector poses together (nothing moved)"
        plan.append({"row": ri, "left": st, "right": st})   # one IK for both arms: they succeed or fail together
        clipped: list = []
        goal = clip_joint_row(goal, clipped, ri)
        mv = [j for j in range(DIM) if j not in SWITCH]
        n = int(np.clip(math.ceil(float(np.max(np.abs(goal[mv] - cur[mv]))) / 0.02), 4, 600))
        for k in range(1, n + 1):
            a = cur + (goal - cur) * (k / n); a[SWITCH] = goal[SWITCH]
            if ctrl_step(a, rec): return


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    # everything about the request is checked here, before the first control step: a bad field is a 400, nothing ran
    typ = meta.get("type"); dt = request_number(meta, "dt", 1.0 / CTRL_HZ); interp = meta.get("interpolate", "linear")
    cams = request_cameras(meta); fps = video_fps(meta); video = meta.get("video", "mp4"); note = request_note(meta)
    if typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:      # never rounded: 0.25 s would silently run 8 steps (0.267 s)
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
    if typ == "ee_pose":
        if np.any(np.abs(A[:, [0, 1, 2, 8, 9, 10]]) > EE_POS_MAX_M): raise ValueError(f"ee_pose positions must be within {EE_POS_MAX_M:g} m of the world origin")
        if np.any(np.linalg.norm(A[:, 3:7], axis=1) < 1e-6) or np.any(np.linalg.norm(A[:, 11:15], axis=1) < 1e-6):
            raise ValueError("ee_pose quaternions (xyzw) must not be zero")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
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
         "depth": rec.mode, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = request_cameras(meta)
    seconds = request_number(meta, "seconds", 0.0); fps = video_fps(meta); video = meta.get("video", "frames")
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(S.hold_action().cpu(), dtype=np.float64).reshape(-1)   # last command, base at 0 (stand still)
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
        rec.tick(force=True, last=True)
        succ = E["success"] or check_success(); E["success"] = succ
        if succ: finish("success")
    else:
        rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "depth": rec.mode, "control_steps": ctrl_steps() - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    return S.kinematics(req)            # stateless: the tooling's model of the robot, never the live joints, never a step


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def _end_from_signal():
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        else: dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped, releasing the simulator for the fresh-process replays"})
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the GPU and the memory: finalize.sh starts the replays once this process is gone


REPLAY = {"skipped": 0}


def replay_row(row) -> None:
    """One journaled row during a resume. OmniGibson's rollouts are not bit-exact (resume class `approx`), so the replayed
    episode can end (the goal holds, the robot has fallen over) a few rows before the logged one did: the rows the scene
    can no longer take are skipped instead of raising, which would crash every resume the same way until the service
    gives up. What that means for the episode is decided right after the replay (below)."""
    if S.episode_done:
        REPLAY["skipped"] += 1
    else:
        S.step(row)


L.check_spec(SPEC)                      # before the episode starts: a bad /spec must not cost a resume
EP.scene_built()                        # the scene and everything the service needs exist: the startup watchdog stands down
S.record_start()                        # the trajectory: a resume's journal replay is recorded too
resumed = EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC,
                   start_event={"task": TASK, "instance_id": S.instance_id, "cameras": CAMS}, on_end=_end_from_signal)
if resumed and S.episode_done and not E["done"]:
    # the replayed episode ended although the logged one had not: with the goal holding it is a success like any other
    # (the two fresh replays of the recorded trajectory still decide); anything else (a fall the live run did not have)
    # is the resume's divergence, not the agent's: no verdict on the agent (resume_failed, infra_error = 1)
    log({"ev": "resume_ended_early", "skipped_rows": REPLAY["skipped"], "end_reason": S.end_reason, "success": check_success()})
    if check_success():
        E["ready"] = True
        with LOCK: finish("success")
        E["ready"] = False
    else:
        EP.give_up(f"resume_failed: the replayed episode ended ({S.end_reason or 'step_guard'}) before the logged one did", infra=True)
E["ready"] = True; write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes}{', resumed at call ' + str(E['calls']) if resumed else ''})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
