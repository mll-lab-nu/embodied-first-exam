"""eai-standard/2.2 sim service for YAMLab (Isaac Lab / Isaac Sim 5.1; two I2RT YAM arms with parallel grippers; see
docs/STANDARD_MODE_2_2.md). Owns the scene. HTTP surface (rcb_limited): GET /spec, GET /status, POST /observe, POST /submit,
POST /kinematics (RCB1 bodies, RCB1 responses: videos / frames / depth / proprio as raw blobs, never base64). Logs every call
to /data/episode.jsonl and keeps /data/final.json current. Nothing about objects ever leaves this process.

Crash recovery (rcb_limited.Episode, docs/STANDARD_MODE_2_2.md §13, resume class `exact`): every executed control step is
journaled (the 14-D float32 row handed to Session.step), every completed call is checkpointed with the scene's state hash.
After a crash compose restarts the container (`restart: on-failure:6`, run.sh exits non-zero) and this service, a fresh
process, rebuilds the frozen scene, replays the journal up to the last checkpoint (the first run in a fresh process:
bit-identical with PhysX on the CPU, the tooling's fixed env seed and its render after every restore), checks the state
hash and continues the SAME episode, never a reset.

Differences from the RoboLab service, all from the robot and the simulator:
- two arms: the joint action is YAMLab's own 14-D one (6 joint targets + the gripper's finger target per arm), streamed at
  the 30 Hz CONTROL rate (sim dt 1/120 s x decimation 4); the gripper target is continuous (metres), so `linear`
  interpolates it like the joints;
- `ee_pose` rows hold both arms' tool-frame targets (16 values) and drive them together by Isaac Lab's differential IK in
  closed loop (one update per arm per control step, as the privileged-mode `move_ee` primitive does it);
- three cameras (top: static; left_wrist / right_wrist: on each arm's link_6), rendered when a frame is recorded (rendering
  never steps physics); depth from the same renders; /kinematics from numpy models of both arms;
- the episode ends at the first control step where YAMLab's success check (evaluation thresholds) has latched every stage,
  or when a task object falls off the table (YAMLab's own termination), or when the time is up;
- the episode is NOT replayed here (a second Isaac simulator in this container would not fit next to the live one): when it
  ends the service writes /data/trajectory.npz + /data/episode.json (live result and state hash); the collect hook's SIGUSR1
  makes it exit, and environment/sim/finalize.sh replays the trajectory in two fresh processes and completes final.json."""
from __future__ import annotations
import math, os, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "put_pot_on_cooktop"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 30; SUBSTEPS = 4; ACTION_DIM = 14
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
import rcb_yamlab as M  # noqa: E402
S = M.Session(TASK, instance=INSTANCE, strict=True, depth=True)
ARMS = M.ARMS
LAYOUT = [f"{a}_{j}" for a in ARMS for j in list(M.ARM_JOINTS) + ["gripper"]]
CAMS = list(M.CAMERAS)
MOUNT = {"top": "static, above the table looking down at the workspace", "left_wrist": "on the left arm's wrist (link_6)",
         "right_wrist": "on the right arm's wrist (link_6)"}


def images() -> dict:
    return {c: S.render_frame(c) for c in CAMS}
FIRST = images()


def joint_limits() -> dict:
    out = {}
    for a in ARMS:
        lim = M._np(S.arm[a].data.soft_joint_pos_limits)[0]
        for j, i in zip(M.ARM_JOINTS, S.joint_ids[a][:6]):
            out[f"{a}_{j}"] = [round(float(lim[i, 0]), 4), round(float(lim[i, 1]), 4)]
        out[f"{a}_gripper"] = [M.FINGER_OPEN, M.FINGER_CLOSED]
    return out
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)   # (14, 2)
CAM0 = S.camera_info(CAMS)
JPOS = [f"{a}_{j}" for a in ARMS for j in list(M.ARM_JOINTS) + ["left_finger"]]
PROPRIO_LAYOUT = (JPOS + [f"{a}_tcp_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz")] + [f"{a}_gripper_cmd" for a in ARMS]
                  + [f"{j}_vel" for j in JPOS] + [f"{a}_gripper_opening_m" for a in ARMS] + [f"{a}_{j}_effort" for a in ARMS for j in M.ARM_JOINTS])

SPEC = {
    "protocol": PROTOCOL, "protocol_compat": list(L.COMPAT), "simulator": "yamlab (YAMLab on Isaac Lab / Isaac Sim 5.1)", "robot": "i2rt-yam-bimanual",
    "task_text": S.spec["text"], "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": [int(FIRST[c].shape[1]), int(FIRST[c].shape[0])],
                    "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": CAM0[c]["intrinsic_cv"], "mount": CAM0[c]["mount"],
                    "depth_range_m": CAM0[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": ACTION_DIM, "layout": LAYOUT,
                           "units": "rad for <arm>_joint1..6; <arm>_gripper: the position target of that arm's left_finger joint in metres "
                                    "(-0.0475 = fully open .. 0.0 = closed; the other finger mirrors it)",
                           "limits": LIMITS,
                           "semantics": "YAMLab's own action: absolute joint targets tracked by PD drives, streamed at the 30 Hz control rate; "
                                        "rows `dt` apart (a multiple of 1/30 s, at most 0.5 s; anything else is rejected, never rounded), hold "
                                        "or linear interpolation between rows (the gripper targets too); out-of-limit values are clipped and "
                                        "reported"},
        "ee_pose": {"dim": 16, "layout": [f"{a}_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")],
                    "frame": "world: x forward from the arm bases towards the far side of the table, y to the left, z up, metres",
                    "quaternion": "wxyz, unit norm",
                    "semantics": "per row, both arms' tool frames are driven to their targets together by Isaac Lab's differential IK in closed "
                                 "loop (one update per arm per control step along a straight line, at most 0.25 m/s), `dt` is ignored; an arm "
                                 "that does not converge within 6 mm is reported in plan[]; the grippers take the row's targets (metres, as "
                                 "in joint_position) at the row's first step",
                    "note": "the pose is the arm's TOOL frame <arm>_tcp: the midpoint of its two fingertips, 0.1426 m from link_6 along "
                            "link_6's +z (approach) axis, with link_6's orientation; same frame as the proprio tcp columns"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": {
        "joint_pos": [0, 14, "measured joint positions: left joint1..6 (rad), left_finger (m), right joint1..6, right_finger"],
        "tcp_pose": [14, 14, "measured tool-frame poses: left_tcp then right_tcp, each x y z (m) + quaternion wxyz, world frame"],
        "gripper_cmd": [28, 2, "the gripper targets in force (m): left, right"],
        "joint_vel": [30, 14, "measured joint velocities, the joints of joint_pos (rad/s, m/s for the fingers)"],
        "gripper_opening": [44, 2, "how far each gripper is open (m): -(left_finger + right_finger), 0 closed on nothing, 0.095 fully open; "
                                   "a gripper closed on something stops above 0"],
        "joint_effort": [46, 12, "drive-effort estimate of left joint1..6 then right joint1..6 (N m): stiffness * (target - q) + damping * "
                                 "(0 - qdot) of their PD drives, clipped to effort_limit (a motor-current analogue: it grows when an arm "
                                 "pushes on something)"]},
    "static": {},
    "world": {"frame": "the workstation's world frame: x forward (from the arm bases towards the far side of the table), y to the left, "
                       "z up; the arm bases and every tool frame are in it (spec.robot_spec)",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes (x right, y up, z back)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))},
    "episode": "one episode, no reset: it ends at the first control step where every stage of YAMLab's success check has latched "
               "(checked after every control step), when a task object falls off the table, when your time is up, or on a simulator error",
    "robot_spec": S.robot_spec(),
    "kinematics": S.kinematics_spec(),
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)       # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()         # the watchdog stands down: a long resume replay below is not a hung build


def check_success() -> bool:
    return S.success()


def proprio_row() -> np.ndarray:
    P = S.proprio()
    return np.array(P["joint_pos"] + P["tcp_pose"] + P["gripper_cmd"] + P["joint_vel"] + P["gripper_opening"] + P["joint_effort"], dtype=np.float32)


def grab(cams, want_depth: bool):
    return {c: S.render_frame(c) for c in cams}, ({c: S.render_depth(c) for c in cams} if want_depth else {})


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


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    cal = {c: {k: ci[k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c, ci in S.camera_info(cams).items()}
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(time.time() - E["t0"], 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - (time.time() - E["t0"]), 1)),
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


def end_reason() -> str:
    if S.success():
        return "success"
    return "object_fell" if S.fallen() else "step_guard"


def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool:
    """One recorded control step, journaled for crash recovery. True when the call must stop here: the episode is over
    (success, a task object off the table, the runaway guard), or the service stops the call (max_call_wall_s, the client
    hung up)."""
    a = np.asarray(a, dtype=np.float32)                    # the exact row Session.step executes (and records)
    over = S.step(a); stop = EP.journal(a); rec.tick()
    if over: finish(end_reason())
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = int(round(dt * CTRL_HZ))
    q_prev = np.asarray(S.hold_action(), dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list, clipped: list) -> None:
    speed, max_dq, tol = 0.25, 0.08, 0.006
    for ri, row in enumerate(A):
        E["step"] += 1
        goals = {}
        for i, a in enumerate(ARMS):
            r = np.asarray(row[8 * i:8 * i + 8], dtype=np.float64)
            p1 = r[0:3]; q1 = r[3:7] / max(1e-9, float(np.linalg.norm(r[3:7])))
            g = float(r[7])
            if not (M.FINGER_OPEN <= g <= M.FINGER_CLOSED):
                clipped.append({"row": ri, "index": 8 * i + 7, "reason": f"{a}_gripper limit [{M.FINGER_OPEN},{M.FINGER_CLOSED}]"})
                g = float(np.clip(g, M.FINGER_OPEN, M.FINGER_CLOSED))
            p0, _ = S.ee_pose(a)
            goals[a] = (p0, p1, q1, g, max(1, int(math.ceil(float(np.linalg.norm(p1 - p0)) / (speed / CTRL_HZ)))))
        n_way = max(v[4] for v in goals.values())
        st = {a: "not converged" for a in ARMS}; err = {a: None for a in ARMS}
        for i in range(n_way + 80):
            cur = np.asarray(S.hold_action(), dtype=np.float64); act = cur.copy()
            try:
                for a, (p0, p1, q1, g, _n) in goals.items():
                    wp = p1 if i >= n_way else p0 + (p1 - p0) * ((i + 1) / n_way)
                    q_des = S.ik_step(a, wp, q1)
                    sl = M.ARM_SLICE[a]
                    act[sl] = cur[sl] + np.clip(q_des - cur[sl], -max_dq, max_dq); act[M.GRIP_INDEX[a]] = g
            except Exception as exc:  # noqa: BLE001
                st = {a: f"failed: {str(exc)[:80]}" for a in ARMS}; break
            if ctrl_step(act, rec):
                st = {a: ("episode over" if E["done"] else f"stopped ({EP.stop_reason})") for a in ARMS}; break
            for a, (_p0, p1, _q1, _g, _n) in goals.items():
                err[a] = float(np.linalg.norm(S.ee_pose(a)[0] - p1))
            if i >= n_way and all(e is not None and e < tol for e in err.values()):
                st = {a: "Success" for a in ARMS}; break
        plan.append({"row": ri, **{f"{a}_arm": st[a] for a in ARMS}, **{f"{a}_ee_error_m": (None if err[a] is None else round(err[a], 4)) for a in ARMS}})
        if E["done"] or EP.stopping: return


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ = meta.get("type"); dt = float(meta.get("dt", 1.0 / CTRL_HZ)); interp = meta.get("interpolate", "linear")
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    fps = video_fps(meta); video = meta.get("video", "mp4")
    if typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not math.isfinite(dt) or not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); clipped: list = []; plan: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, rec, plan, clipped)
    rec.tick(force=True, last=True)
    succ = E["success"] or check_success(); E["success"] = succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": (meta.get("note") or "")[:500],
         "depth": rec.mode, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ,
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    seconds = float(meta.get("seconds", 0)); fps = video_fps(meta); video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
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
    """Stateless FK / IK on the arms' numpy models (never the simulator; req already checked by rcb_limited)."""
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
        log({"ev": "exit", "reason": "collect hook: episode dumped, releasing the simulator for the fresh-process replays"})
        if not os.path.exists(PID_FILE):   # a SIGUSR1 that came in during a resume: the hook still needs to see this process end
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the GPU and the memory: finalize.sh starts the replays once this process is gone


def replay_row(row) -> None:
    """One journaled row during a resume (no rendering asked for). A row the scene can no longer take (the episode ended
    earlier than logged) is skipped: the state hash check then refuses the resume (class exact)."""
    if not S.episode_done:
        S.step(np.asarray(row, dtype=np.float32))


S.record_start()         # the resume replay is recorded too: trajectory.npz is the whole episode
EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": TASK, "assets": S.assets, "cameras": CAMS, "kinematics_check": S.kinematics_check})
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
