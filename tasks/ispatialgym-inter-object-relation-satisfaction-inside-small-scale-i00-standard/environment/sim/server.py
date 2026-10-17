"""eai-standard/2.2 sim service for iSpatialGym (docs/benchmarks/ispatialgym.md; docs/STANDARD_MODE.md): the benchmark's
adapter of the shared layer rcb_limited.py. Owns the scene. HTTP surface (rcb_limited.serve): GET /spec, GET /status,
POST /observe, POST /submit (RCB1 bodies and responses), POST /kinematics. Logs every call to /out/episode.jsonl and keeps
/out/final.json current. Nothing about objects, targets or the world frame ever leaves this process.

As BEHAVIOR-1K's service (the same robot on the same simulator), except:
- the action is iSpatialGym's own 23-D JoyLo action (rcb_ispatialgym.py): base velocity command, trunk, both arms, one
  command per gripper; rows are streamed at the 30 Hz control rate, the trunk and arm targets interpolated, the base and
  gripper commands switched at the row; there is no ee_pose action (POST /kinematics solves IK, statelessly);
- the episode ends when upstream's geometric success holds (success), when its control steps run out (max_steps: run_isg's
  policy budget, reason "failed: the episode's control steps ran out"), on the collect hook's signal (timeout) or on a
  simulator error (error); there is no fall rule (upstream has none);
- every pose leaves in the odometry frame (the robot's base at the start of the episode), never in the world frame;
- the verdict is the live episode's (owner 2026-10-17, board 0150/0151): upstream's success under settle-eval, judged
  at every control step the episode runs, is `success`; nothing replays it. When it ends the service writes
  /out/trajectory.npz + /out/episode.json, and the collect hook's SIGUSR1 makes it close the video and exit;
  finalize.sh then writes final.json from episode.json;
- the frozen start is checked when the scene is built, before the agent is served: a start that does not rebuild to
  the frozen one (facts.json: the start-state hash, else every pose within POSE_TOL) gives up as `instance_mismatch`
  (infra_error);
- the video is recorded live (/out/live.mp4): the head camera's frame that every control step renders anyway, every
  third step, encoded off the control loop (rcb_ispatialgym.LiveVideo); a resume re-records it from the start;
- crash recovery: rcb_limited.Episode, resume class `approx` (OmniGibson's rollouts are only bit-exact as the first
  episode of a fresh process): a resumed episode continues from the replayed state, which the gross-divergence guard
  bounds (RCB_RESUME_MAX_DEV_M), and its verdict is the episode it then runs."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/out")   # /data holds the licensed BEHAVIOR dataset here
os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.dirname(os.path.abspath(__file__)))
TASK_TEXT = open(os.path.join(INSTANCE, "task_text.txt")).read().strip()
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
MAX_FRAMES = 300                        # images per response (cameras x frames): 1080x1080 RGB is 3.5 MB a frame
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
DIM = 23                                # the R1Pro's JoyLo action (asserted once the scene exists)
EP = L.Episode(DATA, dim=DIM, resume="approx")
EP.startup()
log = EP.log
MAX_STEPS_REASON = "failed: the episode's control steps ran out"

import rcb_ispatialgym as M  # noqa: E402
CTRL_HZ, SUBSTEPS = M.CTRL_HZ, M.SUBSTEPS
try:
    S = M.Session(INSTANCE)
except BaseException as exc:            # Kit ends the process with exit code 0 on an uncaught exception: exit 1 instead, so
    traceback.print_exc()               # compose restarts the service (with rcb_limited's back-off) and the start is retried
    log({"ev": "startup_error", "error": repr(exc)[:500]})
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(1)
if not S.instance_ok:                   # before the agent is served: the episode must start from the frozen instance
    EP.give_up(f"instance_mismatch: the frozen start state did not rebuild here (start {S.start_sha}, frozen {S.facts['start_sha']})", infra=True)
assert S.action_dim == DIM, (S.action_dim, DIM)
IDX = {k: [int(i) for i in M._np(v).tolist()] for k, v in S.robot.controller_action_idx.items()}
LAYOUT = [""] * DIM
for blk, ii in IDX.items():
    for k, i in enumerate(ii):
        LAYOUT[i] = f"{blk}_{k}" if len(ii) > 1 else blk
SWITCH = IDX["base"] + IDX["gripper_left"] + IDX["gripper_right"]   # commands, switched at the row; the rest interpolated
LIMITS = {}
for blk, ii in IDX.items():
    joints = {"trunk": S.robot.trunk_control_idx, "arm_left": S.robot.arm_control_idx["left"], "arm_right": S.robot.arm_control_idx["right"]}.get(blk)
    for k, i in enumerate(ii):
        if joints is None:
            LIMITS[LAYOUT[i]] = [-1.0, 1.0]
        else:
            j = int(M._np(joints).tolist()[k])
            LIMITS[LAYOUT[i]] = [float(S.robot.joint_lower_limits[j]), float(S.robot.joint_upper_limits[j])]
LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)
CAMS = S.cameras()
MOUNT = {c: ("head (moves with the base and trunk)" if "zed" in c else "left wrist" if "left" in c else "right wrist" if "right" in c else "on the robot") for c in CAMS}
PROPRIO, GROUPS = S.proprio_layout()
RSPEC, KSPEC = S.robot_spec(), S.kinematics_spec()
VIDEO = os.path.join(DATA, "live.mp4")   # every start records it anew (a resume replays the episode from the start)
try:
    VID = M.LiveVideo(VIDEO)
except Exception as exc:  # noqa: BLE001 -- never the verdict: no video, the episode runs on
    VID = None; log({"ev": "video_error", "error": repr(exc)[:300]})


def head_frame():
    return S.frames([S.head_camera])[S.head_camera]


def video_step() -> None:
    if VID is not None:
        VID.offer(S.n, head_frame)


video_step()                            # the start: a video even of an episode without actions


def ctrl_steps() -> int:
    return S.n


def check_success() -> bool:
    return bool(S.success)


def write_final() -> None:
    if L.final_verdict(DATA):           # a verdict on disk (a give-up after crashes) is never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": S.n, "max_steps": S.max_steps,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"],
        "subtask": S.up["subtask"], "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"),
        "live_sha": E.get("live_sha"), "start_sha": S.start_sha, **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        E["live_sha"] = S.state_sha(); E["n_actions"] = len(S.rows)
        S.save_trajectory(os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "reason": E["reason"]})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    st = S.status()
    L._write_json(os.path.join(DATA, "episode.json"), {
        "success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": S.n, "max_steps": S.max_steps,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "subtask": S.up["subtask"],
        "protocol": PROTOCOL, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), "start_sha": S.start_sha,
        "success_step": st["success_step"], "symbolic_success": st["symbolic_success"], "geometric_success": st["geometric_success"],
        "error_metric": st["error_metric"], "graded_by": "live", "replays": 0, **EP.final_fields()})
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["success"] = E["success"] or check_success()
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": S.n, "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    dump()


def cam_spec(c: str) -> dict:
    f = S._cam_fixed()[c]
    return {"rgb": True, "depth": False, "mounted": MOUNT[c], "resolution": list(f["size"]), "calibration_in_obs": OBS_CALIBRATION,
            "intrinsic_cv": f["K"], "mount": {"type": "link", "parent_link": f["parent_link"], "link_T_cam_cv": f["link_T_cam_cv"]}}


SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "iSpatialGym eval v1.0 (OmniGibson / Isaac Sim, BEHAVIOR-1K fork)",
    "robot": "r1pro", "task_text": TASK_TEXT, "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "max_control_steps": S.max_steps, "max_frames_per_call": MAX_FRAMES,
    "cameras": {c: cam_spec(c) for c in CAMS},
    "default_cameras": [S.head_camera],
    "goal_image": {"file": "/app/goal.png", "camera": S.head_camera,
                   "note": "the head camera's view once the task is done (same camera, same resolution and intrinsics); the robot "
                           "itself does not have to match it"},
    "action_types": {
        "joint_position": {"dim": DIM, "layout": LAYOUT, "blocks": {k: [min(v), max(v) + 1] for k, v in IDX.items()},
                           "units": "base_0..2: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate; robot_spec.base); "
                                    "trunk and arm entries: absolute joint targets in rad; gripper_left / gripper_right: one command in [-1, 1] "
                                    "(-1 closed, 1 fully open; robot_spec.grippers)",
                           "limits": LIMITS,
                           "semantics": "streamed at the 30 Hz control rate; rows `dt` apart (a multiple of 1/30 s); trunk and arm joints hold or "
                                        "linearly interpolate between rows, the base and gripper commands switch at the row and hold until the next "
                                        "one; out-of-limit values are clipped and reported"},
        "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO,
    "proprio_groups": GROUPS,
    "static": {"frame": "the odometry frame: the robot's base_link at the start of the episode (x forward, y left, z up), metres; "
                        "poses are position + quaternion XYZW"},
    "world": {"frame": "odometry: the robot's base_link at the start of the episode, x forward, y left, z up; the service gives no "
                       "other frame", "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "xyzw",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV (x right, y down, z forward); extrinsic_cv maps the odometry frame to the camera",
              "camera_timing": "a frame shows the scene as rendered 2 control steps (67 ms) before its frame_step while the robot moves; its "
                               "extrinsic_cv is the pose it was rendered with; proprio is the state at frame_step"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))},
    "episode": (f"one episode, no reset: it ends at the first control step at which the scene matches the goal image (success), after "
                f"{S.max_steps} control steps ({S.max_steps / CTRL_HZ:.1f} s of simulated time; reason \"{MAX_STEPS_REASON}\"), when your "
                "time is up (timeout) or on a simulator error (error)"),
    "robot_spec": RSPEC,
    "kinematics": KSPEC,
    "depth": {"modes": ["none"], "default": "none", "note": "RGB only, as iSpatialGym's evaluation renders it"},
}


def proprio_row() -> np.ndarray:
    return S.proprio_row()


def grab(cams, want_depth: bool):
    if want_depth:
        raise ValueError("this service renders no depth (spec depth.modes: none)")
    return S.frames(list(cams)), {}


def extrinsics(cams) -> dict:
    return S.extrinsics(list(cams))


def calib(cams) -> dict:
    ext = S.extrinsics(list(cams))
    return {c: {"intrinsic_cv": S._cam_fixed()[c]["K"], "extrinsic_cv": ext[c].tolist(), "image_size": S._cam_fixed()[c]["size"]} for c in cams}


# ---------------------------------------------------------------- request fields: checked before anything is executed
def request_number(meta: dict, key: str, default: float) -> float:
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
    if meta.get("video_fps") is None:
        return 5
    fps = request_number(meta, "video_fps", 5)
    if not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


def request_cameras(meta: dict) -> list:
    c = meta.get("cameras")
    if c is None:
        return list(SPEC["default_cameras"])
    if not isinstance(c, (list, tuple)) or not all(isinstance(x, str) for x in c):
        raise ValueError("cameras must be a list of camera names (spec['cameras'])")
    return [x for x in c if x in CAMS] or list(SPEC["default_cameras"])


def request_note(meta: dict) -> str:
    n = meta.get("note")
    if n is not None and not isinstance(n, str):
        raise ValueError("note must be a string")
    return (n or "")[:500]


def request_depth(meta: dict) -> str:
    d = L.depth_mode(meta)
    if d not in ("none",):
        raise ValueError("this service renders no depth (spec depth.modes: none)")
    return d


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=request_depth(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "control_steps_left": max(0, S.max_steps - n),
            "time_s": round(L.agent_time(E), 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
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
def clip_row(row: np.ndarray, clipped: list, ri: int) -> np.ndarray:
    r = row.copy()
    for j, name in enumerate(LAYOUT):
        lo, hi = LIM_ARR[j]
        if r[j] < lo or r[j] > hi:
            clipped.append({"row": ri, "index": int(j), "reason": f"{name} limit [{lo:.3f},{hi:.3f}]"}); r[j] = float(np.clip(r[j], lo, hi))
    return r


def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool:
    """One recorded and journaled control step. True when the call must stop: the episode is over, or the layer stops
    the call (max_call_wall_s, the client hung up)."""
    done = S.step(a); stop = EP.journal(a); rec.tick(); video_step()
    if done: finish("success" if S.success else MAX_STEPS_REASON)
    return E["done"] or stop


def run_rows(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * CTRL_HZ)))
    prev = S.hold_action().astype(np.float64)   # the last command, base velocity 0
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else prev + (target - prev) * (k / steps_per_row)
            a[SWITCH] = target[SWITCH]
            if ctrl_step(a, rec): return
        prev = target


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    # everything about the request is checked here, before the first control step: a bad field is a 400, nothing ran
    typ = meta.get("type"); dt = request_number(meta, "dt", 1.0 / CTRL_HZ); interp = meta.get("interpolate", "linear")
    cams = request_cameras(meta); fps = video_fps(meta); video = meta.get("video", "mp4"); note = request_note(meta)
    if typ != "joint_position": raise ValueError(f"type must be joint_position (not yet: {SPEC['action_types']['not_yet']})")
    if A.ndim != 2 or A.shape[1] != DIM: raise ValueError(f"joint_position actions must be (T, {DIM}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    every = max(1, int(round(CTRL_HZ / max(1, fps))))
    L.check_frames(len(cams), A.shape[0] * max(1, int(round(dt * CTRL_HZ))) // every + 2, limit=MAX_FRAMES)
    rec = recorder(cams, fps, meta); clipped: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    if not E["done"]:
        run_rows(A, dt, interp, rec, clipped)
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": [], "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": note,
         "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "done": E["done"]})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = request_cameras(meta)
    seconds = request_number(meta, "seconds", 0.0); fps = video_fps(meta); video = meta.get("video", "frames")
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in ("mp4", "frames", "both", "none"): raise ValueError("video must be mp4|frames|both|none")
    L.check_frames(len(cams), int(round(seconds * CTRL_HZ)) // max(1, int(round(CTRL_HZ / max(1, fps)))) + 2, limit=MAX_FRAMES)
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = S.hold_action().astype(np.float64)   # the last command, base velocity 0
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
        rec.tick(force=True, last=True)
    else:
        rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    return S.kinematics(req)            # stateless: the model of the robot, never the live joints, never a step


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def _end_from_signal():
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        else: dump()
        if VID is not None:              # the episode is over: no frame comes any more
            v = VID.close()
            log({"ev": "video", **v})
            try:
                ep = L._read_json(os.path.join(DATA, "episode.json")); ep.update(v)
                L._write_json(os.path.join(DATA, "episode.json"), ep)
            except Exception as exc:  # noqa: BLE001 -- never the verdict
                log({"ev": "video_error", "error": repr(exc)[:300]})
        log({"ev": "exit", "reason": "collect hook: episode dumped and video closed, releasing the simulator"})
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the GPU and the memory: finalize.sh writes final.json once this process is gone


REPLAY = {"skipped": 0}


def replay_row(row) -> None:
    """One journaled row during a resume (rollouts are not bit-exact across processes): a row the episode can no longer
    take, because the replay already ended it, is skipped; what that means is decided right after the replay."""
    if S.done:
        REPLAY["skipped"] += 1
    else:
        S.step(row); video_step()


L.check_spec(SPEC)                      # before the episode starts: a bad /spec must not cost a resume
EP.scene_built()
resumed = EP.begin(state=E, step=replay_row, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC,
                   start_event={"subtask": S.up["subtask"], "start_sha": S.start_sha, "cameras": CAMS}, on_end=_end_from_signal)
if resumed and S.done and not E["done"]:
    log({"ev": "resume_ended_early", "skipped_rows": REPLAY["skipped"], "end_reason": S.reason, "success": S.success})
    if S.success:
        E["ready"] = True
        with LOCK: finish("success")
        E["ready"] = False
    else:
        EP.give_up(f"resume_failed: the replayed episode ended ({S.reason}) before the logged one did", infra=True)
E["ready"] = True; write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes}{', resumed at call ' + str(E['calls']) if resumed else ''})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
