"""eai-standard/2.2 sim service for AM-Bench (Isaac Lab / Isaac Sim 5.1, GPU PhysX; the FA-Hexa: a fully actuated hexarotor
with a 4-joint arm and a two-finger gripper; see docs/protocol/standard_mode.md). Owns the scene. HTTP surface (rcb_limited): GET
/spec, GET /status, POST /observe, POST /submit, POST /kinematics (RCB1 bodies, RCB1 responses: videos / frames / depth /
proprio as raw blobs, never base64). Logs every call to /data/episode.jsonl and keeps /data/final.json current. Nothing
about objects ever leaves this process.

The physics runs camera-free: the two onboard cameras are drawn by a second Isaac process (rcb_ambench.Renderer) from the
states this one sends it (measured: rendering inside the physics process makes AM-Bench's GPU physics timing-dependent), so
the live episode is the same computation as a fresh-process replay of its rows (the privileged grader's), and the live
episode is what is graded (no grading replay since 2026-10-17).

Crash recovery (rcb_limited.Episode, docs/protocol/standard_mode.md §13, resume class `approx`): every executed control step is
journaled (the 8-value row handed to Session.step), every completed call is checkpointed with the scene's state hash.
After a crash compose restarts the container (`restart: on-failure:6`, run.sh exits non-zero) and this service, a fresh
process, rebuilds the frozen scene, replays the journal up to the last checkpoint (the first episode of a fresh process:
the same state, but for the last bits a rare GPU race can change), compares the state with the checkpoint (a deviation is
recorded; a TCP more than RCB_RESUME_MAX_DEV_M away ends the episode as an infrastructure failure) and continues the SAME
episode, never a reset.

Differences from the YAMLab service, all from the robot and the simulator:
- one action type, AM-Bench's own: `ee_pose` rows (x y z qw qx qy qz gripper: the end-effector target and the gripper
  command) streamed at the 120 Hz control rate, `dt` apart, `hold` or `linear` (positions linear, orientation slerp, the
  gripper linear); AM-Bench's controller (floating-base IK + PID on the airframe + PD joint drives) does the rest;
- the airframe is free-flying: /kinematics is the arm on its base (frame `base`, or world with `base_pose`);
- the episode ends at the first control step where AM-Bench's success check holds, or at the task's own time-out (its
  episode length), or when the time is up;
- the episode is graded as it ran (owner 2026-10-17: no grading replay): when it ends the service writes
  /data/trajectory.npz (the deliverable) + /data/episode.json (the live result and the end-state hash); the collect hook's
  SIGUSR1 makes it exit, and environment/sim/finalize.sh writes final.json from it, then films the rows once (an
  illustration, never a verdict);
- the start state is checked before the agent is served: the rebuilt scene's state hash against the frozen instance's
  (instance.json `initial_sha`); a mismatch ends the trial as an infrastructure failure (`instance_mismatch`, a give-up:
  nothing is served)."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
from typing import Callable
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
TEXTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "texts.json")))    # task_text, episode (mk_tasks.py)
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 120; SUBSTEPS = 1; ACTION_DIM = 8
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
LOCK = threading.Lock(); PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
# Resume class `approx` for every AM-Bench task: GPU PhysX replays the journal to the checkpoint's state almost always, but
# a rare race inside a step can leave the last bits different (docs/benchmarks/ambench.md, Determinism; the kill test
# measured a replayed TCP 1e-6 m from its checkpoint, which `exact` turns into resume_failed). A resume records the
# deviation (resume_state_mismatch, resume_max_tcp_dev_m) and continues; the verdict is the live episode's after the
# resume (every task since 2026-10-17; before, fresh replays of the complete recorded trajectory decided, except for a task
# graded by verdict, instance.json "determinism": "verdict").
VERDICT = json.load(open(INSTANCE)).get("determinism") == "verdict"
EP = L.Episode(DATA, dim=ACTION_DIM, resume="approx")
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
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"],
                   "task": S.env_id, "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"),
                   **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory and the live result for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    try:
        acts = S.actions(); E["live_sha"] = S.status()["state_sha"]; E["n_actions"] = int(len(acts))
        # The trajectory is what ran (since 2026-10-17). Until then, after a live success it also held the last command
        # for up to 2 s (`hold_pad_rows`), for the grading replays: the race of docs/benchmarks/ambench.md
        # (Determinism) could move a fresh replay's success one step later. No replay grades the episode any more.
        pad = 0
        E["hold_pad_rows"] = pad
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"],
                                                                            "reason": E["reason"], "resumes": EP.resumes,
                                                                            "hold_pad_rows": pad})
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": S.env_id, "protocol": PROTOCOL,
                   "n_actions": E.get("n_actions"), "hold_pad_rows": E.get("hold_pad_rows", 0), "live_sha": E.get("live_sha"),
                   "determinism_verdict_mode": VERDICT, **INSTANCE_CHECK, **EP.final_fields()})
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    if not E["success"]:
        E["success"] = bool(S.success())
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"])})
    dump()


# ---------------------------------------------------------------- scene
import rcb_ambench as M  # noqa: E402
S = M.Session(INSTANCE, strict=False, cameras=True, depth=True)   # the start-state check is below (instance_mismatch)
# The frozen initial state, checked before anything is served: the rebuilt scene's state hash against instance.json's
# `initial_sha` (what strict mode refused by raising, which crashed the service until the collect hook gave up; the
# replays checked it again until 2026-10-17).
INSTANCE_CHECK = {"instance_sha": S.initial_sha, "instance_expected_sha": L._read_json(INSTANCE).get("initial_sha"),
                  "instance_exact": bool(S.instance_matches), "instance_matches": bool(S.instance_matches)}
if not S.instance_matches:
    L._write_json(os.path.join(DATA, "final.json"), {"task": S.env_id, "protocol": PROTOCOL, "instance_mismatch": True, **INSTANCE_CHECK})
    try:
        S.renderer.close()
    except Exception:  # noqa: BLE001
        pass
    EP.give_up(f"instance_mismatch: the rebuilt scene's state {S.initial_sha} is not the frozen instance's "
               f"{INSTANCE_CHECK['instance_expected_sha']}", infra=True)   # never returns
CAMS = list(S._cams)
MOUNT = {"ee_camera": "on the end effector (ee_link), looking along the gripper", "base_camera": "on the airframe (base_link), looking forward"}
EPISODE_STEPS = int(round(float(S.env.cfg.episode_length_s) * CTRL_HZ)) - 1     # AM-Bench's time-out step


def images() -> dict:
    return {c: S.render_frame(c) for c in CAMS}
FIRST = images()
CAM0 = S.camera_info(CAMS)
PROPRIO_LAYOUT = S.proprio_layout()
_sizes = {g: len(v) for g, v in S.std_proprio().items()}
_starts, _k = {}, 0
for _g in M.PROPRIO_ORDER:
    _starts[_g] = _k; _k += _sizes[_g]
GROUP_TEXT = {
    "joint_pos": "measured joint positions: the arm's four joints (rad; arm_link1..3 pitch, arm_link4 roll), then the two fingers (m)",
    "joint_vel": "measured joint velocities, the joints of joint_pos (rad/s, m/s)",
    "tcp_pose": "measured pose of the tool frame `tcp` (= ee_link, AM-Bench's end-effector command frame): x y z (m) + quaternion wxyz, world",
    "gripper_opening": "the sum of the two finger joints (m): 0.002 = closed on nothing; a gripper closed on something stops wider",
    "gripper_cmd": "the gripper command in force (-1 = closed .. +1 = open)",
    "joint_effort": "the arm's four joint drive efforts (N m): what the PD drives apply (a motor-current analogue: it grows when the arm pushes)",
    "base_pose": "measured pose of the airframe (base_link): x y z (m) + quaternion wxyz, world",
    "base_vel": "measured airframe velocity: linear (m/s) then angular (rad/s), world frame",
    "ee_cmd": "the end-effector target in force (the last ee_pose row's x y z qw qx qy qz, interpolated within a chunk)"}

SPEC = {
    "protocol": PROTOCOL, "protocol_compat": list(L.COMPAT), "simulator": "ambench (AM-Bench on Isaac Lab / Isaac Sim 5.1, GPU PhysX)",
    "robot": "ambench-fahexa", "task_text": TEXTS["task_text"], "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT.get(c, c), "resolution": [int(FIRST[c].shape[1]), int(FIRST[c].shape[0])],
                    "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": CAM0[c]["intrinsic_cv"], "mount": CAM0[c]["mount"],
                    "depth_range_m": CAM0[c]["depth_range_m"]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "ee_pose": {"dim": ACTION_DIM, "layout": ["x", "y", "z", "qw", "qx", "qy", "qz", "gripper"],
                    "frame": "world: z up, the ground is the plane z = 0; positions relative to the environment's origin (the same frame "
                             "as proprio tcp_pose / base_pose), metres",
                    "quaternion": "wxyz (passed on as given with `hold`; normalised along a `linear` interpolation)",
                    "limits": {"gripper": [-1.0, 1.0]},
                    "semantics": "AM-Bench's own action: the target pose of the tool frame `tcp` (= ee_link) and the gripper command (-1 = "
                                 "closed .. +1 = open), one row per control step at 120 Hz; AM-Bench's whole-body controller turns it "
                                 "into an airframe pose (floating-base IK), rotor thrusts (PID) and arm joint targets every step. Rows are "
                                 "`dt` apart (a multiple of 1/120 s, at most 0.5 s; anything else is rejected, never rounded), `hold` (each "
                                 "row for its dt) or `linear` (from the previous target: positions linear, orientation slerp, gripper "
                                 "linear); a gripper value outside [-1, 1] is clipped and reported"},
        "not_yet": ["joint_position", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": {g: [_starts[g], _sizes[g], GROUP_TEXT[g]] for g in M.PROPRIO_ORDER},
    "static": {},
    "world": {"frame": "the task's world frame: z up, the ground is the plane z = 0, positions relative to the environment's origin; at the "
                       "start the airframe hovers level facing +x",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes (x right, y up, z back)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))},
    "max_control_steps": EPISODE_STEPS,
    "episode": TEXTS["episode"],
    "robot_spec": S.robot_spec(),
    "kinematics": S.kinematics_spec(),
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)       # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()         # the watchdog stands down: a long resume replay below is not a hung build


def proprio_row() -> np.ndarray:
    return S.proprio_row()


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


# ---------------------------------------------------------------- request fields
# PROTOCOL §4.6: a malformed request is a 400 and executes nothing. Every field is read and checked by the functions below
# BEFORE the first control step; a field that is absent or JSON null takes its default, a value of the wrong type or out
# of range is a ValueError (the layer's 400). as_400() turns anything else a bad value can raise while it is being read
# into that 400 too: only an error while the simulator is stepping is a simulator error (500, the episode ends).
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
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 4),
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
def end_reason() -> str:
    """success, episode_timeout (AM-Bench's own time-out: the task's episode length ran out) or step_cap."""
    r = S.end_reason() or "step_cap"
    return "episode_timeout" if r == "timeout" else r


def ctrl_step(a: np.ndarray, rec: L.Recorder) -> bool:
    """One recorded control step, journaled for crash recovery. True when the call must stop here: the episode is over
    (success, AM-Bench's time-out), or the service stops the call (max_call_wall_s, the client hung up)."""
    a = np.asarray(a, dtype=np.float64)                    # the exact row Session.step executes (and records)
    over = S.step(a); stop = EP.journal(a); rec.tick()
    if over: finish(end_reason())
    return E["done"] or stop


def slerp(q0: np.ndarray, q1: np.ndarray, s: float) -> np.ndarray:
    q0 = q0 / max(1e-12, float(np.linalg.norm(q0))); q1 = q1 / max(1e-12, float(np.linalg.norm(q1)))
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + s * (q1 - q0); return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    return (math.sin((1 - s) * th) * q0 + math.sin(s * th) * q1) / math.sin(th)


def run_ee_pose(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = int(round(dt * CTRL_HZ))
    prev = np.asarray(S.hold_action(), dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = np.asarray(row, dtype=np.float64).copy()
        if not (-1.0 <= target[7] <= 1.0):
            clipped.append({"row": ri, "index": 7, "reason": "gripper limit [-1, 1]"}); target[7] = float(np.clip(target[7], -1.0, 1.0))
        for k in range(1, steps_per_row + 1):
            if interp == "hold":
                a = target
            else:
                s = k / steps_per_row
                a = np.r_[prev[:3] + (target[:3] - prev[:3]) * s, slerp(prev[3:7], target[3:7], s), prev[7] + (target[7] - prev[7]) * s]
            if ctrl_step(a, rec): return
        prev = target


EE_POS_MAX_M = 30.0      # an ee_pose position further than this from the origin on any axis is a 400 (a unit slip)


def check_ee_rows(A: np.ndarray) -> None:
    """ee_pose rows that cannot be meant (PROTOCOL §4.6: a 400, nothing executed): a position outside the +-EE_POS_MAX_M box
    around the origin, or a quaternion of zero length."""
    for ri, r in enumerate(A):
        if float(np.max(np.abs(r[0:3]))) > EE_POS_MAX_M:
            raise ValueError(f"ee_pose row {ri}: the position {[round(float(v), 4) for v in r[0:3]]} is outside the +-{EE_POS_MAX_M} m "
                             "box around the origin (metres, world frame)")
        if float(np.linalg.norm(r[3:7])) < 1e-6:
            raise ValueError(f"ee_pose row {ri}: the quaternion (wxyz) has zero length")


def parse_submit(meta: dict, A: np.ndarray) -> tuple:
    """Every field of a /submit, checked; nothing is executed here."""
    typ = meta.get("type")
    if not isinstance(typ, str) or typ != "ee_pose":
        raise ValueError(f"type must be ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", 1.0 / CTRL_HZ); interp = choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = cameras(meta); fps = video_fps(meta); video = choice(meta, "video", "mp4", ("mp4", "frames", "both", "none"))
    note = note_text(meta); L.depth_mode(meta)
    if A.ndim != 2 or A.shape[1] != ACTION_DIM: raise ValueError(f"ee_pose actions must be (T, {ACTION_DIM}), got {list(A.shape)}")
    if A.shape[0] < 1: raise ValueError("no rows")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.6f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    check_ee_rows(A)
    return typ, dt, interp, cams, fps, video, note


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ, dt, interp, cams, fps, video, note = as_400(parse_submit, meta, A)       # a 400 before anything moves
    rec = recorder(cams, fps, meta); clipped: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    run_ee_pose(A, dt, interp, rec, clipped)
    rec.tick(force=True, last=True)
    succ = E["success"] or bool(S.success()); E["success"] = succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": [], "rejected": None, "ok": True}
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
        succ = E["success"] or bool(S.success()); E["success"] = succ
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
    """Stateless FK / IK of the arm on its base (numpy model; never the simulator; req already checked by rcb_limited)."""
    return S.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (rcb_limited.Episode runs this in a thread): end the episode, dump it, exit 0."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("time_up")         # the agent's time ran out with the episode still running
        else: dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped (graded by the live episode), releasing the simulator"})
        if not os.path.exists(PID_FILE):   # a SIGUSR1 that came in during a resume: the hook still needs to see this process end
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    try:
        S.renderer.close()
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)          # frees the GPU and the memory: finalize.sh writes final.json, then films, once this process is gone


def replay_row(row) -> None:
    """One journaled row during a resume (no rendering asked for). A row the scene can no longer take (the episode ended
    earlier than logged) is skipped: the state hash check then refuses the resume (class exact)."""
    if not S.done:
        S.step(np.asarray(row, dtype=np.float64))


# The physics of the episode starts here (a resume replays the journal first): finalize.sh counts the GPU faults in
# server.log only from this marker on, in the starts that reached it (a start that died while building the scene and was
# restarted is not the episode's physics).
print("[rcb] the episode's physics starts (live_gpu_faults are counted from here)", flush=True)
EP.begin(state=E, step=replay_row, state_sha=lambda: S.status()["state_sha"], proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
         start_event={"task": S.env_id, "cameras": CAMS, "kinematics_check": S.kinematics_check, "dropped_events": S.dropped_events})
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=lambda: S.status()["state_sha"], proprio=proprio_row))
