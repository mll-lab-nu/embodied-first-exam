"""eai-standard/2.2 sim service for TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB; docs/rcb/STANDARD_MODE_2_2.md): the TopoGym
adapter of the shared layer rcb_limited.py (scripts/eai_standard/, copied unchanged into every standard task). Adapted from
robot_coding_bench's RoboWits service. HTTP surface (rcb_limited.py): GET /spec, GET /status, POST /observe, POST /submit
(RCB1 bodies, RCB1 responses), POST /kinematics (stateless FK / IK on the robot's own model). Logs every call to
/data/episode.jsonl and keeps /data/final.json current. Nothing about objects ever leaves this process.

Crash recovery (rcb_limited.Episode, STANDARD_MODE_2_2.md section 13, resume class `approx`: Genesis' GPU contact solver is
not bit-deterministic): every executed control step is journaled (/data/journal.f64, the exact float32 row given to
Session.step), every completed call checkpointed (rows, state hash, proprio row). After a crash run.sh exits non-zero,
compose restarts the container (`restart: on-failure:6`) and this service rebuilds the frozen scene, replays the journal
up to the last checkpoint and continues the SAME episode, never a reset; a hash mismatch is recorded, not fatal, unless a
TCP is more than RCB_RESUME_MAX_DEV_M from its checkpoint.

Episode end and grading (two passes: the live episode, then one fresh replay that also records the video): when the
episode ends (success, the task's failure predicate, the wall clock, an error) the service writes /data/trajectory.npz and
/data/episode.json (the live result and final-state hash, `live_rows`: the rows the live episode executed). The collect
hook's SIGUSR1 makes it exit, releasing the GPU; environment/sim/finalize.sh then replays the trajectory once in a fresh
process, rendering /data/replay.mp4 during that replay, and completes /data/final.json.

Differences from the RoboWits service, all from the simulator: the physics runs on the GPU, so `deterministic` (live and
replay state hashes equal) is reported and not required; rows are streamed at the task's control rate (control_hz,
physics_substeps physics steps each); the joint action is per arm the arm joint targets plus the frozen instance gripper target;
`ee_pose` is solved by bounded least squares over the robot's Genesis forward kinematics; a task whose own failure
predicate fires (e.g. touching the buzz wire) ends the episode with reason "task_failed"; a family may enable passive grasp
assistance (the gripper `command` text of /spec says the rule). Genesis' CUDA context belongs to the thread that built the
scene, so every simulator call runs on the main thread: the HTTP layer serves from a thread and hands submit / observe /
kinematics, the per-call checkpoint's state hash and proprio row, and the episode end to the main thread's job queue."""
from __future__ import annotations
import json, math, os, queue, sys, threading, time, traceback
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
PID_FILE = os.path.join(DATA, "server.pid")
# Crash-safe episode bookkeeping, set up before the scene is built (start count, back-off, startup watchdog); the journal row
# is the action row (its width from the frozen instance: the scene does not exist yet)
EP = L.Episode(DATA, dim=int(json.load(open(INSTANCE))["action_dim"]), resume="approx")
EP.startup()
log = EP.log


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


def ctrl_steps() -> int:
    return int(S.n_steps) if E["ready"] else 0


# Episode ends that are infrastructure failures, never the agent's: a simulator error, and a numerically unstable simulation
# (rcb_topogym.SIMULATOR_INSTABILITY: a cloth particle faster than PARTICLE_SPEED_LIMIT_M_S, before the task's own failure
# predicates; finalize.sh applies the same rule to the replay).
INFRA_REASONS = ("error", "simulator_instability")


def instability_fields() -> dict:
    """The breakdown evidence and the live episode's evidence: its review events (deep task contacts: a success with any
    is held for review by the grader, rcb_topogym.CONTACT_RULE) and its forcing events (rcb_topogym.FORCING: evidence only)."""
    ready = E.get("ready")
    return {"simulator_instability": E["reason"] == "simulator_instability", "instability": getattr(S, "instability", None),
            "review": S.monitor.review() if ready else None, "forcing": S.monitor.forcing() if ready else None}


def write_final() -> None:
    if L.final_verdict(DATA):           # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    n = int(E.get("episode_control_steps") or ctrl_steps())
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": bool(E["success"]), "infra_error": int(E["reason"] in INFRA_REASONS), **instability_fields(), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": S.physics_steps, "sim_time_s": S.sim_time_s,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK,
        "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"), "live_rows": E.get("live_rows"),
        "live_sha": E.get("live_sha"), **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (main thread). Rows
    recorded after the live end (the rest of the chunk that ended it, watch holds) were never commanded live: `live_rows`
    tells the replay where the live episode stopped."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        acts = S.record_stop(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts))
        n_live = E.get("end_row"); E["live_rows"] = int(len(acts) if n_live is None else min(int(n_live), len(acts)))
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"],
                                                                            "reason": E["reason"], "live_rows": E["live_rows"], "resumes": EP.resumes})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"), {
        "success": bool(E["success"]), "infra_error": int(E["reason"] in INFRA_REASONS), **instability_fields(), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": S.physics_steps, "sim_time_s": S.sim_time_s,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
        "n_actions": E.get("n_actions"), "live_rows": E.get("live_rows"), "live_sha": E.get("live_sha"), **EP.final_fields()})
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    E.setdefault("end_row", len(S._recording) if S._recording is not None else None)   # timeout / error / guard ends
    if not E["success"]:
        try: E["success"] = check_success()
        except Exception: pass
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    dump()


# ---------------------------------------------------------------- scene
import rcb_topogym as M  # noqa: E402
try:
    S = M.Session(TASK, instance=INSTANCE, strict=True)
    M.atomic_json(os.path.join(DATA, "startup_binding.json"), dict(
        instance_exact=S.instance_exact, runtime_binding=S.runtime_binding,
        instance_generated=bool(getattr(S, "instance_generated", False)), instance_sha=S.instance_sha,
        initial_state=getattr(S, "initial_state", None)))
except M.InstanceMismatch as exc:
    # This frozen instance is not evaluable. Do not restart it as a GPU crash
    # or wait for a trajectory that could never have been executed.
    EP.scene_built()  # cancel the startup watchdog before clean exit
    M.atomic_json(os.path.join(DATA, "final.json"), {
        "success": False, "replay_success": False, "done": True, "finalized": True,
        "instance_mismatch": True, "infra_error": 0, "reason": "instance_mismatch",
        "error": str(exc), "task": TASK, "protocol": PROTOCOL, **EP.final_fields()})
    raise SystemExit(0)
EP.scene_built()                        # the startup watchdog stands down: a long resume replay is not a hang
E["ready"] = True                       # S exists: ctrl_steps() counts its control steps (a resume replay included)
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
    "gripper_space": S.gripper_space,
    "instance_binding_id": (S.runtime_binding or {}).get("binding_id"),
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "topogym (Genesis 1.2.1, Nyx RGB)", "robot": R_SPEC["name"],
    "task_text": S.spec["text"], "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": list(CAM_INFO[c]["image_size"]), "calibration_in_obs": OBS_CALIBRATION,
                    "intrinsic_cv": CAM_INFO[c]["intrinsic_cv"], "mount": CAM_INFO[c]["mount"], "depth_range_m": CAM_INFO[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": N, "layout": LAYOUT, "units": ("rad for arm joints; native gripper drive targets (ALOHA m, Robotiq rad), see robot_spec.grippers" if S.gripper_space == "native" else "rad for the arm joints; gripper opening width in metres, 0 = closed .. the limit = open"),
                           "limits": LIMITS,
                           "semantics": f"absolute joint targets tracked by the robot's PD controllers, streamed at the {CTRL_HZ:g} Hz control rate; rows "
                                        f"`dt` apart (a multiple of 1/{CTRL_HZ:g} s), hold or linear interpolation between rows (the gripper switches "
                                        "at the row); out-of-limit values are clipped and reported. An arm joint target moves at most "
                                        f"{M.JOINT_STEP_LIMIT_RAD:g} rad per control step ({M.JOINT_STEP_LIMIT_RAD * CTRL_HZ:g} rad/s, as ee_pose rows): "
                                        "a row asking for more takes the control steps it needs and is reported in clipped[]. "
                                        f"No gripper target goes lower than {M.table_guard_words()}: a target "
                                        "that would is stopped there (reported in clipped[])"},
        "ee_pose": {"dim": 8 * len(ARMS), "layout": [f"{a}_{k}" for a in ARMS for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")],
                    "frame": WORLD_FRAME, "quaternion": "wxyz, unit norm",
                    "gripper_units": "same command space and limits as joint_position / robot_spec.grippers",
                    "semantics": "each row is solved by inverse kinematics (bounded least squares on the robot's forward kinematics, no collision "
                                 "checking) and driven to in joint space; `dt` is ignored (the joint distance sets the duration); an arm whose IK "
                                 "fails holds and is reported in plan[]. A solution more than "
                                 f"{M.IK_JUMP_LIMIT_RAD:g} rad from the current joints on any joint is refused the same way (for a small "
                                 "pose change that is another IK branch, which would swing the arm): split long moves into rows. The "
                                 f"table guard applies as for joint_position (no gripper target lower than {M.table_guard_words()}, "
                                 "reported in clipped[])",
                    "note": "the pose is each gripper's tool frame (TCP; axes in robot_spec.tcp); same convention as the proprio TCP poses, so "
                            "an observed pose is a valid target"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},                       # nothing about where things are (standard mode); the task text names the objects
    "world": {"frame": WORLD_FRAME, "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes "
                             "(x right, y up, z backward)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "10800"))},
    "episode": ("ends at the first success (the task predicate is evaluated after every /submit and every /observe that watches), "
                "when the task's own failure predicate fires (reason task_failed), when the wall-clock budget is used up, or on a "
                "simulator error; a simulator "
                f"breakdown (a non-finite state, any cloth particle faster than {M.PARTICLE_SPEED_LIMIT_M_S:g} m/s, an invalid "
                f"soft-body solver state, a rigid task contact deeper than {M.BREAKDOWN_PENETRATION_M * 1000:g} mm) ends it with "
                f"reason {M.SIMULATOR_INSTABILITY}, graded as an infrastructure error, not as the task's failure, unless an arm was "
                f"forcing (an arm drive at {M.FORCING['near_cap']:.0%} of its torque cap or more while the gripper, or a part it "
                f"holds, presses on something with {M.FORCING['contact_n']:g} N or more) within the {M.FORCING['attribution_s']:g} s "
                f"before (reason {M.FORCED_BREAKDOWN}: the agent's failure); forcing itself and task-contact penetration do not end "
                "it (meta safety records them), but a success with a deep task contact (meta safety review) is held for review "
                "instead of credited automatically; the recorded trajectory is then replayed once in a fresh process and graded"),
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
    return L.Recorder(cams, int(round(CTRL_HZ / max(1, fps))), grab, proprio_row, extrinsics, ctrl_steps, depth=L.depth_mode(meta), clock_hz=CTRL_HZ, time_clock=lambda: S.sim_time_s, fps=fps)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": S.physics_steps, "sim_time_s": S.sim_time_s,
            "time_s": round(time.time() - E["t0"], 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - (time.time() - E["t0"]), 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            "safety": S.safety(), **({"cameras": calib(cams)} if OBS_CALIBRATION else {})}


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


def ctrl_step(a: np.ndarray, rec: L.Recorder, *, row_start=False, notes: list | None = None, ri: int | None = None) -> bool:
    """One recorded control step. True when the call must stop here: the episode is over (runaway guard, the task's own
    failure predicate, the wall clock), or the call ran past max_call_wall_s / its client hung up (EP.journal). A gripper
    target the table guard stopped (rcb_topogym._TableGuard) is reported in `notes` (meta["clipped"]), once per row and arm."""
    if deadline_reached():
        finish("timeout")
        return True
    row = np.asarray(a, dtype=np.float32)   # exactly what the simulator gets (Session.step casts to float32): the journal row
    if EP.poll_stop():
        return True
    before = S.n_steps
    guard = S.step(row)
    if S.n_steps != before and row_start:
        E["step"] += 1
    if S.n_steps != before and S.last_guard and notes is not None:
        for arm in ARMS:
            e = S.last_guard.get(arm)
            reason = f"table guard: the {arm} gripper"
            if e and not any(n["row"] == ri and n["reason"].startswith(reason + " ") for n in notes[-8:]):
                notes.append({"row": ri, "index": int(ARM[arm][1]), "reason": (
                    f"{reason} would have reached {e['asked_mm']:+.1f} mm from the tabletop; its target stopped at "
                    f"{e['stopped_mm']:+.1f} mm (no gripper target goes lower than {M.table_guard_words()})")})
    stop = EP.journal(S.hold_action(), physics_steps=S.last_step_ticks) if S.n_steps != before else EP.poll_stop()
    rec.tick()
    if S.episode_end is not None and "end_row" not in E and S._recording is not None:
        E["end_row"] = len(S._recording)      # the row at which the live episode ended (success or a failure predicate)
    if S.episode_end is not None: finish(S.episode_end)
    elif guard: finish("step_guard")
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    """Rows `dt` apart (linear interpolation or hold). Joint-speed limit (rules 2026-10-03, as ee_pose rows): an arm joint
    target moves at most rcb_topogym.JOINT_STEP_LIMIT_RAD per control step; a row that asks for more takes the control
    steps it needs (reported in meta["clipped"]), so every row is still reached."""
    steps_per_row = L.control_periods(dt, CTRL_HZ)
    q_prev = np.asarray(S.hold_action(), dtype=np.float64)
    grips = [ARM[a][1] for a in ARMS]
    arm_cols = [j for j in range(N) if j not in grips]
    limit = M.JOINT_STEP_LIMIT_RAD
    for ri, row in enumerate(A):
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        reach = np.abs(target[arm_cols] - q_prev[arm_cols])
        n = max(steps_per_row, int(math.ceil(float(reach.max(initial=0.)) / limit - 1e-6)))
        slowed = False
        for k in range(1, n + 1):
            a = target.copy() if interp == "hold" or k > steps_per_row else q_prev + (target - q_prev) * (k / steps_per_row)
            a[grips] = target[grips]                          # the gripper switches at the row
            cmd = np.asarray(S.hold_action(), dtype=np.float64)
            d = a[arm_cols] - cmd[arm_cols]
            if np.any(np.abs(d) > limit + 1e-6):
                a[arm_cols] = cmd[arm_cols] + np.clip(d, -limit, limit)
                slowed = True
            if ctrl_step(a, rec, row_start=k == 1, notes=clipped, ri=ri): return
        if slowed:
            j = arm_cols[int(np.argmax(reach))]
            clipped.append({"row": ri, "index": int(j), "reason": (
                f"speed: {LAYOUT[j]} asked to move {float(reach.max()):.3f} rad "
                f"{'at once' if interp == 'hold' else f'in {steps_per_row} control step(s)'}; joint "
                f"targets move at most {limit:g} rad per control step ({limit * CTRL_HZ:g} rad/s), so this row took {n} "
                "control steps")})
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list, clipped: list) -> None:
    """IK per row from the measured joints. A solution farther than rcb_topogym.IK_JUMP_LIMIT_RAD from them on any joint
    is refused (rules 2026-10-03: for a small pose change that is another IK branch, which swings the arm): that arm holds
    and plan[] says why, as for a failed IK."""
    for ri, row in enumerate(A):
        cur = np.asarray(S.hold_action(), dtype=np.float64); goal = cur.copy(); st = {"row": ri}
        for i, arm in enumerate(ARMS):
            sl, gi = ARM[arm]; off = 8 * i
            q = row[off + 3:off + 7]; q = q / max(1e-9, float(np.linalg.norm(q)))
            try:
                qa, ep, er = S.ik(arm, row[off:off + 3], q)
                if ep > 0.02 or er > 0.35:
                    raise ValueError(f"no IK solution within 2 cm / 20 deg (residual {ep * 1000:.0f} mm / {math.degrees(er):.0f} deg)")
                qa = np.clip(qa, LIM_ARR[sl, 0], LIM_ARR[sl, 1])
                jump, joint = S.ik_jump(arm, qa)
                if jump > M.IK_JUMP_LIMIT_RAD:
                    st[arm] = (f"refused: the IK solution is {jump:.2f} rad from the current joints on {joint} (limit "
                               f"{M.IK_JUMP_LIMIT_RAD:g} rad per ee_pose row): for a small pose change that is another IK "
                               "branch, which would swing the arm. Split the motion into rows that change each joint by at "
                               "most that much (for example a few cm and degrees apart), or move the joints with "
                               "joint_position. This arm holds.")
                else:
                    goal[sl] = qa; st[arm] = "Success"
            except Exception as exc:  # noqa: BLE001
                st[arm] = f"failed: {str(exc)[:90]}"
            goal[gi] = float(np.clip(row[off + 7], LIM_ARR[gi, 0], LIM_ARR[gi, 1]))
        plan.append(st)
        n = int(np.clip(math.ceil(float(np.max(np.abs(goal - cur))) / 0.04), 4, 400))   # at most ~0.04 rad per control step
        for k in range(1, n + 1):
            a = cur + (goal - cur) * (k / n)
            for arm in ARMS: a[ARM[arm][1]] = goal[ARM[arm][1]]
            if ctrl_step(a, rec, row_start=k == 1, notes=clipped, ri=ri): return


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ = meta.get("type"); dt = float(meta.get("dt", 1.0 / CTRL_HZ)); interp = meta.get("interpolate", "linear")
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    fps = int(meta.get("video_fps", 10)); video = meta.get("video", "mp4")
    if typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if typ == "joint_position":
        L.control_periods(dt, CTRL_HZ)
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); clipped: list = []; plan: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); before_ticks = S.physics_steps; rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, rec, plan, clipped)
    rec.tick(force=True, last=True)
    succ = check_success(); E["success"] = E["success"] or succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": S.physics_steps - before_ticks, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": (meta.get("note") or "")[:500],
         "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    seconds = float(meta.get("seconds", 0)); fps = int(meta.get("video_fps", 10)); video = meta.get("video", "frames")
    if not math.isfinite(seconds) or seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); before = ctrl_steps(); before_ticks = S.physics_steps
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
           "physics_steps_watch": S.physics_steps - before_ticks, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    """/kinematics (validated by rcb_limited.parse_kinematics): the tooling's stateless FK / IK, never the simulator."""
    return S.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def deadline_reached():
    return E["ready"] and not E["done"] and time.monotonic() >= E["deadline"]


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (rcb_limited.Episode runs this in a thread): the main thread ends the episode, dumps it
    and exits 0 (_end_and_exit), so the GPU is free for finalize.sh's fresh-process replay."""
    JOBS.put(_end_and_exit)


def _end_and_exit() -> None:
    """Main thread, between simulator jobs. No svc.lock here: an HTTP call holds it while it waits for the main thread."""
    E["exiting"] = True                     # the HTTP layer answers 409 from now on
    if not E["done"]: finish("timeout")
    else: dump()
    log({"ev": "exit", "reason": "collect hook: episode dumped, releasing the GPU for the fresh-process replay"})
    if not os.path.exists(PID_FILE):        # a SIGUSR1 that came in during a resume: the hook must still see this process end
        open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)


def replay_row(row) -> None:
    """One journaled row during a resume (main thread, no rendering asked for). As live: after the task's own episode end
    Session.step records the row without moving the scene, and the row of that end is remembered (`live_rows`)."""
    if not S.episode_done:
        S.step(np.asarray(row, dtype=np.float32))
        if S.episode_end is not None and "end_row" not in E and S._recording is not None:
            E["end_row"] = len(S._recording)


# ---------------------------------------------------------------- start, or resume after a crash
E["deadline"] = float("inf")
S.record_start()                        # before begin(): a resume replay of the journal is recorded too
EP.begin(step_ticks=lambda row, ticks: S.step(row, _physics_steps=ticks), state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": TASK, "eval_index": S.eval_index})
E["deadline"] = time.monotonic() + SPEC["budget"]["wall_clock_s"] - (time.time() - E["t0"])   # the wall clock runs from the first start
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
threading.Thread(target=L.serve, daemon=True, args=(L.Service(
    spec=SPEC, lock=LOCK, state=E, submit=lambda meta, A: on_main(do_submit, meta, A), observe=lambda meta: on_main(do_observe, meta),
    kinematics=lambda req: on_main(do_kinematics, req), status=status, on_submit_error=lambda exc: on_main(finish, "error"), log=log,
    episode=EP, state_sha=lambda: on_main(S.state_sha), proprio=lambda: on_main(proprio_row)),)).start()
while True:                                 # the main thread: simulator jobs in order; signals are handled between them
    if deadline_reached():
        finish("timeout")
    try:
        job = JOBS.get(timeout=0.5)
    except queue.Empty:
        continue
    job()
