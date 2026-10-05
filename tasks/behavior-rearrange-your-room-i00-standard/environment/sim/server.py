"""eai-standard/2.2 sim service for BEHAVIOR-1K v3.9.2 (OmniGibson on Isaac Sim, the 2026 challenge stack; R1Pro; see
docs/STANDARD_MODE_2_2.md): the benchmark's adapter of the shared layer rcb_limited.py. Owns the scene. HTTP surface
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
- crash recovery (rcb_limited.Episode, docs/STANDARD_MODE_2_2.md §13): every executed control step goes to
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
    if term or trunc: finish("success" if check_success() else "step_guard")
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
    typ = meta.get("type"); dt = float(meta.get("dt", 1.0 / CTRL_HZ)); interp = meta.get("interpolate", "linear")
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    fps = int(meta.get("video_fps", 5)); video = meta.get("video", "mp4")
    if typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
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
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": (meta.get("note") or "")[:500],
         "depth": rec.mode, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    seconds = float(meta.get("seconds", 0)); fps = int(meta.get("video_fps", 5)); video = meta.get("video", "frames")
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


L.check_spec(SPEC)                      # before the episode starts: a bad /spec must not cost a resume
EP.scene_built()                        # the scene and everything the service needs exist: the startup watchdog stands down
S.record_start()                        # the trajectory: a resume's journal replay is recorded too
resumed = EP.begin(state=E, step=S.step, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC,
                   start_event={"task": TASK, "instance_id": S.instance_id, "cameras": CAMS}, on_end=_end_from_signal)
E["ready"] = True; write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes}{', resumed at call ' + str(E['calls']) if resumed else ''})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
