"""rcb-limited/2.2 sim service for TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB; see docs/rcb/LIMITED_MODE_PROTOCOL.md).
Adapted from robot_coding_bench's RoboWits service (fa59c1a6: tasks/robowits-stack-cubes-i00-limited/environment/sim/
server.py); the HTTP surface is the shared layer rcb_limited.py, byte-identical to robot_coding_bench's: GET /spec,
GET /status, POST /observe, POST /submit (RCB1 bodies, RCB1 responses), POST /kinematics (stateless FK / IK on the robot's
own model). Logs every call to /data/episode.jsonl, keeps /data/final.json current, and on episode end exports the
recorded trajectory, replays it for success (+ the state-hash comparison) and renders /data/replay.mp4. Nothing about
objects ever leaves this process.

Differences from the RoboWits service, all from the simulator: the physics runs on the GPU, whose contact solver is not
bit-deterministic, so `deterministic` (live and replay state hashes equal) is reported and not required; rows are
streamed at the task's control rate (control_hz, physics_substeps physics steps each); the joint action is per arm the arm
joint targets plus the gripper opening width; `ee_pose` is solved by bounded least squares over the robot's Genesis
forward kinematics; a task whose own failure predicate fires (e.g. touching the buzz wire) ends the episode with reason
"task_failed" (the simulator cannot continue it); a family may enable passive grasp assistance (the gripper `command` text
of /spec says the rule). Genesis' CUDA context belongs to the thread that built the scene, so every simulator call runs on
the main thread: the HTTP layer serves from a thread and hands submit / observe / kinematics to the main thread's job queue,
and the episode's finalization (replay, video) is queued there too instead of running in a thread of its own."""
from __future__ import annotations
import json, math, os, queue, signal, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "cube_pick_place"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
JOBS: queue.Queue = queue.Queue()      # simulator work, executed in order by the main thread


def on_main(fn, *a):
    """Run fn on the main thread (the owner of the CUDA context) and return its result or raise its exception."""
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


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), **ev}) + "\n")


def ctrl_steps() -> int:
    return int(S.n_steps) if E["ready"] else 0


def write_final() -> None:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    json.dump({"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
               "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": PROTOCOL,
               "finalized": bool(E.get("finalized")), "n_actions": E.get("n_actions"), "replay_success": E.get("replay_success"),
               "deterministic": E.get("deterministic"), "live_sha": E.get("live_sha"), "replay_sha": E.get("replay_sha"), "video": bool(E.get("video")),
               "video_done": bool(E.get("video_done"))},
              open(os.path.join(DATA, "final.json"), "w"))


def finalize() -> None:
    """Runs on the main thread between queued jobs, so no submit / observe can run meanwhile."""
    try:
        acts = S.record_stop(); live_sha = S.state_sha()
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "limited-mode episode (v2)", "steps": E["step"], "reason": E["reason"]})
        E["n_actions"] = int(len(acts)); E["live_sha"] = live_sha
        rep = S.replay(acts); E["replay_success"] = bool(rep["success"]); E["replay_sha"] = rep["state_sha"]; E["deterministic"] = rep["state_sha"] == live_sha
        log({"ev": "replay", "n_actions": int(len(acts)), "replay_success": E["replay_success"], "deterministic": E["deterministic"]})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "finalize_error", "error": repr(exc)})
        acts = None
    # the grading record is complete before the video, whose rendering grows with the episode
    E["finalized"] = True; write_final()
    if acts is not None and len(acts):
        try:
            S.start_video(os.path.join(DATA, "replay.mp4"), fps=15); S.replay(acts); S.stop_video(); E["video"] = True   # + replay.last.png
        except Exception:  # noqa
            traceback.print_exc()
    E["video_done"] = True; write_final()


def start_finalize() -> None:
    if E.get("finalizing"): return
    E["finalizing"] = True; JOBS.put(finalize)


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    if not E["success"]:
        try: E["success"] = check_success()
        except Exception: pass
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    write_final(); start_finalize()


# ---------------------------------------------------------------- scene
import rcb_topogym as M  # noqa: E402
S = M.Session(TASK, instance=INSTANCE, strict=True)
CTRL_HZ = float(S.control_hz); SUBSTEPS = int(S.physics_substeps)
CAMS = list(S.VIDEO_CAMERAS)
CAM_INFO = S.camera_info(CAMS)
MOUNT = {c: ("static" if CAM_INFO[c]["mount"]["type"] == "static" else f"on the robot link {CAM_INFO[c]['mount']['parent_link']}") for c in CAMS}
ARMS = list(S.robot.arms)
LAYOUT = list(S.action_layout)
ARM = {a: (S.robot.arm_slice[a], S.robot.grip_index[a]) for a in ARMS}


def joint_limits() -> dict:
    return {n: [float(l[0]), float(l[1])] for n, l in zip(LAYOUT, S.robot.limits)}   # float32-exact (rcb_topogym): a row at a limit is not clipped
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)

R_SPEC = S.robot_spec(); K_SPEC = S.kinematics_spec()
EE = [f"{a}_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
N = len(LAYOUT)
PROPRIO_LAYOUT = (LAYOUT + EE + [f"{n}_cmd" for n in LAYOUT] + [f"{n}_vel" for n in LAYOUT]
                  + [f"{a}_gripper_opening_m" for a in ARMS] + [f"{n}_effort" for n in LAYOUT])
PROPRIO_GROUPS = {   # name: [first column, count, meaning]
    "joint_pos": [0, N, "measured joint positions in the joint_position layout: per arm its arm joints (rad) + its gripper opening (m)"],
    "tcp_pose": [N, 7 * len(ARMS), "measured tool-frame (TCP) pose per arm, in the order of the arms: x y z (m) + qw qx qy qz, world frame; "
                                   f"the ee_pose action's frame (kinematics tcp_frames {K_SPEC['tcp_frames']})"],
    "joint_cmd": [N + 7 * len(ARMS), N, "the commanded joint targets being tracked (joint_position layout): the last streamed row step"],
    "joint_vel": [2 * N + 7 * len(ARMS), N, "measured joint velocities (rad/s; the gripper entries: opening rate, m/s)"],
    "gripper_opening": [3 * N + 7 * len(ARMS), len(ARMS), "measured opening of each gripper (m): the gap between the finger pads; a "
                                                          "gripper closed on an object stops above 0"],
    "joint_effort": [3 * N + 8 * len(ARMS), N, "the force each PD drive applied (N m; gripper entries: the actuated finger drive): a "
                                               "motor-current analogue that rises when the arm pushes against something"],
}
WORLD_FRAME = (f"TopoGym world frame: +z up, the table top horizontal; the robot base at "
               f"({', '.join(f'{v:.3f}' for v in R_SPEC['base']['pose'][:3])}) (robot_spec.base)")
SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "topogym (Genesis 1.2.1, Nyx RGB)", "robot": R_SPEC["name"],
    "task_text": S.spec["text"], "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": list(CAM_INFO[c]["image_size"]), "calibration_in_obs": OBS_CALIBRATION,
                    "intrinsic_cv": CAM_INFO[c]["intrinsic_cv"], "mount": CAM_INFO[c]["mount"], "depth_range_m": CAM_INFO[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": N, "layout": LAYOUT, "units": "rad for the arm joints; gripper opening width in metres, 0 = closed .. the limit = open",
                           "limits": LIMITS,
                           "semantics": f"absolute joint targets tracked by the robot's PD controllers, streamed at the {CTRL_HZ:g} Hz control rate; rows "
                                        f"`dt` apart (a multiple of 1/{CTRL_HZ:g} s), hold or linear interpolation between rows (the gripper switches "
                                        "at the row); out-of-limit values are clipped and reported"},
        "ee_pose": {"dim": 8 * len(ARMS), "layout": [f"{a}_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")],
                    "frame": WORLD_FRAME, "quaternion": "wxyz, unit norm",
                    "semantics": "each row is solved by inverse kinematics (bounded least squares on the robot's forward kinematics, no collision "
                                 "checking) and driven to in joint space; `dt` is ignored (the joint distance sets the duration); an arm whose IK "
                                 "fails holds and is reported in plan[]",
                    "note": "the pose is each gripper's tool frame (TCP; axes in robot_spec.tcp); same convention as the proprio TCP poses, so "
                            "an observed pose is a valid target"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},                       # nothing about where things are (limited mode); the task text names the objects
    "world": {"frame": WORLD_FRAME, "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes "
                             "(x right, y up, z backward)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))},
    "robot_spec": R_SPEC,
    "kinematics": K_SPEC,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE,
              "source": "Genesis geometric depth at the same camera rig and pixels as the Nyx RGB (the distance along the optical axis); "
                        "it may differ from the RGB at transparent surfaces"},
}
L.check_spec(SPEC)                      # refuse to start with an incomplete spec or a forbidden field


def check_success() -> bool:
    return S.success()


def proprio_row() -> np.ndarray:
    q = S.joint_positions()
    ep = [np.concatenate(S.ee_pose(a)) for a in ARMS]
    return np.concatenate([q, *ep, S.hold_action(), S.joint_velocities(), [q[ARM[a][1]] for a in ARMS], S.joint_efforts()]).astype(np.float32)


def grab(cameras: list[str], want_depth: bool) -> tuple[dict, dict]:
    f = S.env.sensor_frame(depth=want_depth)
    rgb = {c: np.ascontiguousarray(np.asarray(f.rgb[c])[..., :3]) for c in cameras}
    return rgb, ({c: np.asarray(f.depth[c], dtype=np.float32) for c in cameras} if want_depth else {})


def extrinsics(cameras: list[str]) -> dict:
    meta = S.env.sensor_frame().camera_metadata
    return {c: np.asarray(meta[c]["T_camera_cv_from_world"], dtype=np.float64)[:3] for c in cameras}


def calib(cameras: list[str]) -> dict:
    return {c: {k: v[k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c, v in S.camera_info(cameras).items()}


def recorder(cams: list[str], fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, int(round(CTRL_HZ / max(1, fps))), grab, proprio_row, extrinsics, ctrl_steps, depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


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
            if rec.frames[c] and rec.frames[c][-1] is not None: Image.fromarray(np.ascontiguousarray(rec.frames[c][-1])).save(os.path.join(d, f"last_{c}.jpg"), quality=85)
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
    """One recorded control step. True when the episode must stop (runaway guard, or the task's own failure predicate)."""
    guard = S.step(a); rec.tick()
    if guard: finish("step_guard")
    elif S.episode_end not in (None, "success"): finish("task_failed")
    return E["done"]


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * CTRL_HZ)))
    q_prev = np.asarray(S.hold_action(), dtype=np.float64)
    grips = [ARM[a][1] for a in ARMS]
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            a[grips] = target[grips]                          # the gripper switches at the row
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list) -> None:
    for ri, row in enumerate(A):
        E["step"] += 1
        cur = np.asarray(S.hold_action(), dtype=np.float64); goal = cur.copy(); st = {"row": ri}
        for i, arm in enumerate(ARMS):
            sl, gi = ARM[arm]; off = 8 * i
            q = row[off + 3:off + 7]; q = q / max(1e-9, float(np.linalg.norm(q)))
            try:
                qa, ep, er = S.ik(arm, row[off:off + 3], q)
                if ep > 0.02 or er > 0.35:
                    raise ValueError(f"no IK solution within 2 cm / 20 deg (residual {ep * 1000:.0f} mm / {math.degrees(er):.0f} deg)")
                goal[sl] = np.clip(qa, LIM_ARR[sl, 0], LIM_ARR[sl, 1]); st[arm] = "Success"
            except Exception as exc:  # noqa: BLE001
                st[arm] = f"failed: {str(exc)[:90]}"
            goal[gi] = float(np.clip(row[off + 7], LIM_ARR[gi, 0], LIM_ARR[gi, 1]))
        plan.append(st)
        n = int(np.clip(math.ceil(float(np.max(np.abs(goal - cur))) / 0.04), 4, 400))   # at most ~0.04 rad per control step
        for k in range(1, n + 1):
            a = cur + (goal - cur) * (k / n)
            for arm in ARMS: a[ARM[arm][1]] = goal[ARM[arm][1]]
            if ctrl_step(a, rec): return


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ = meta.get("type"); dt = float(meta.get("dt", 1.0 / CTRL_HZ)); interp = meta.get("interpolate", "linear")
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    fps = int(meta.get("video_fps", 10)); video = meta.get("video", "mp4")
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
    succ = check_success(); E["success"] = E["success"] or succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": (meta.get("note") or "")[:500],
         "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    seconds = float(meta.get("seconds", 0)); fps = int(meta.get("video_fps", 10)); video = meta.get("video", "frames")
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    watch = seconds > 0 and not E["done"]
    rec.tick(force=True, last=not watch)
    if watch:
        hold = np.asarray(S.hold_action(), dtype=np.float64)
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
        rec.tick(force=True, last=True)
        succ = check_success(); E["success"] = E["success"] or succ
        if succ: finish("success")
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    """/kinematics (validated by rcb_limited.parse_kinematics): the tooling's stateless FK / IK, never the simulator."""
    return S.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def _end_from_signal():
    if not E["done"]: finish("timeout")
    else: start_finalize()


def on_usr1(*_):
    JOBS.put(_end_from_signal)              # handled by the main thread between simulator jobs
signal.signal(signal.SIGUSR1, on_usr1)

log({"ev": "start", "task": TASK, "eval_index": S.eval_index, "state_sha": S.state_sha(), "protocol": PROTOCOL}); write_final()
S.record_start()
E["ready"] = True; E["t0"] = time.time()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready", flush=True)
L.check_spec(SPEC)
threading.Thread(target=L.serve, daemon=True, args=(L.Service(
    spec=SPEC, lock=LOCK, state=E, submit=lambda meta, A: on_main(do_submit, meta, A), observe=lambda meta: on_main(do_observe, meta),
    kinematics=lambda req: on_main(do_kinematics, req), status=status, on_submit_error=lambda exc: on_main(finish, "error"), log=log),)).start()
while True:                                 # the main thread: simulator jobs in order; signals are handled between them
    try:
        job = JOBS.get(timeout=0.5)
    except queue.Empty:
        continue
    job()
