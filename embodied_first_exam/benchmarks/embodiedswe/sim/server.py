"""eai-standard/3.0 sim service for EmbodiedSWE (robobench on Isaac Lab 2.3.2 / Isaac Sim 5.1, GPU PhysX; see
docs/protocol/standard_mode.md and tasks/embodiedswe/README.md "Standard mode"). Owns the scene. HTTP surface
(rcb_limited): GET /spec, GET /status, POST /observe, POST /submit, POST /kinematics (RCB1 bodies and responses).

The scene is the privileged task's: EmbodiedSWE's own build of the preset from the same frozen instance (instance.json,
seed, GPU PhysX; rcb_embodiedswe.build), checked against the instance's recorded start state before anything is served
(the cameras are created before the env's one sim.reset() and change nothing of it). The task's grader (grader/<scene>.py,
EmbodiedSWE's rubric) is built on the env and records after every control step, as in the privileged rollout.

Actions (esw_std): only `ee_pose`, streamed: rows `dt` apart (a multiple of the control period, at most 0.5 s), linear
(slerp for quaternions) or hold between rows; every control step hands the robot EmbodiedSWE's native action for the
target of that step (Franka: the OSC pose target of panda_hand, its action smoothing inverted; G1: the native wrist
poses + hand targets [+ base command]). Between calls the last row stays in force (a watch holds it).

The episode: no reset, agent-ended (PROTOCOL §3): a success (the grader's check_success, the privileged verdict's
predicate) never ends the episode and is never shown: it ends at the agent's POST /finish, at a broken tool-only rule
(spatula: a failure, also after a success), at the runaway cap (rcb_embodiedswe.MAX_STEPS, reason step_limit), on a
simulator error or when the agent's time is up (the collect hook). The verdict is read on the live state it ends in
(rcb_embodiedswe._final: success, progress = the rubric's score, the tool-only record), no grading replay (the rubric's own stage memory included: what it records as it happens counts). GPU PhysX repeats a run bit for bit only in the same process history (the cameras
in the scene and this start-up's reads of the articulation change the later bits; drawing them does not): a replay in
another process is not bit-exact, so the video is filmed live (live_video.py) and crash recovery is class `approx` (the
journal holds the native action rows).

Per call, images are bounded by spec.max_frames_per_call (PROTOCOL §3 "Images per call": the frames really captured,
at the recorder's stride, per-frame depth counted again), checked before anything runs; the shared Recorder holds one
copy of the frames and the shared layer builds the body once."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
from typing import Callable
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402
import rcb_agent_end as AE  # noqa: E402
import live_video  # noqa: E402

PROTOCOL = L.PROTOCOL
SRV = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK_FILE = os.environ.get("RCB_TASK_FILE", os.path.join(SRV, "task.json")); TASK = json.load(open(TASK_FILE))
PRESET = TASK["preset"]
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(TASK_FILE), "instance.json"))
GRADER = os.path.join(os.path.dirname(TASK_FILE), TASK["grader"])
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
# images per call (cameras x frames, per-frame depth counted again): 240 RGB frames of 640x480 are 221 MB, so the largest
# legal response stays under the shared layer's 256 MiB body limit (rcb_limited.MAX_RESP) with its mp4s, and nothing is dropped
MAX_FRAMES = int(os.environ.get("RCB_MAX_FRAMES_PER_CALL", "240"))
NATIVE_DIM = {"franka.osc": 8, "bimanual_franka.osc": 16, "g1.pink_ik": 28, "g1.loco_pink_ik": 32}[PRESET.split(".", 2)[2]]
LOCK = threading.Lock(); PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None, "tgt": None}
EP = L.Episode(DATA, dim=NATIVE_DIM, resume="approx", persist=AE.persist(("tgt", "verdict")))   # the verdict: success stays success through a resume
EP.startup()
log = EP.log

# ---------------------------------------------------------------- scene
import rcb_embodiedswe as R  # noqa: E402
import esw_std as X  # noqa: E402
R.launch(cameras=True)
INST = R.load_instance(INSTANCE)
CAMS_OBJ = X.Cameras([])


def _building_env():
    """robobench's BaseEnv.__init__ under construction (the camera hook runs inside its sim.reset()): its scene, robot,
    room."""
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if f.f_code.co_name == "__init__" and s is not None and hasattr(s, "scene") and hasattr(s, "robot") and "room" in f.f_locals:
            return s.scene, s.robot, f.f_locals["room"]
        f = f.f_back
    raise RuntimeError("camera hook: the env under construction was not found")


def make_cameras():
    scene, robot, room = _building_env()
    import omni.usd
    CAMS_OBJ.views = X.views_before_reset(scene, robot, room, omni.usd.get_context().get_stage())
    return CAMS_OBJ.make()


env, _ = R._build_with_camera(INST, make_cameras)
grader = R.load_grader(GRADER, PRESET)(env)
START = R.check_start(env, INST)
INSTANCE_CHECK = {k: START[k] for k in ("instance_sha", "instance_ok", "instance_max_abs_diff", "instance_within_tol", "instance_mismatch",
                                        "gpu_model", "instance_gpu")}
INSTANCE_CHECK["instance_exact"] = bool(START["instance_ok"]); INSTANCE_CHECK["instance_expected_sha"] = INST["state_sha"]
if START["instance_mismatch"]:
    L._write_json(os.path.join(DATA, "final.json"), {"task": PRESET, "protocol": PROTOCOL, **INSTANCE_CHECK})
    EP.give_up(f"instance_mismatch: the rebuilt scene (state {START['instance_sha']}) is not the frozen instance "
               f"({INST['state_sha']}) on the GPU model that froze it", infra=True)   # never returns
RIG = X.make_rig(env)
assert RIG.native_dim == NATIVE_DIM, (RIG.native_dim, NATIVE_DIM)
CTRL_HZ = RIG.ctrl_hz; SUBSTEPS = RIG.substeps; DIM = RIG.dim
CAMS_OBJ.aim(env)
TRAJ = R.Recorder(env, PRESET, int(INST["seed"]))
TOOL = getattr(env, "_esw_tool_only", None)


def ctrl_steps() -> int:
    return len(TRAJ.actions)


# ---------------------------------------------------------------- cameras: render once per control step
_R = {"step": -1}


def render() -> None:
    n = ctrl_steps()
    if _R["step"] != n:
        env.sim.render()
        for c in CAMS_OBJ.cams.values():
            c.update(env.dt)
        _R["step"] = n


# warm-up renders before the first frame: a new view's first frames come out noisy without the renderer's temporal
# history (measured: wheel_carry's pick and place views); rendering changes nothing of the physics
for _ in range(int(os.environ.get("RCB_WARMUP_RENDERS", "12"))):
    env.sim.render()
render()
CALIB = X.calibrate(CAMS_OBJ, RIG)          # intrinsics; static extrinsics; link_T_cam_cv of the mounted ones (measured)
CAMS = [v["name"] for v in CAMS_OBJ.views]
# the cameras and frame rate a call gets when it names none: the robot's own cameras and one static view (the scene's
# "front" or "wide" view, else "overview"), at the highest rate (at most 5 fps) at which the longest default call, a
# 30 s watch with raw frames, fits max_frames_per_call: every call legal at the defaults is answered in full
MOUNTED_CAMS = [v["name"] for v in CAMS_OBJ.views if v.get("link_prim")]
DEFAULT_CAMS = [next(c for c in ("front", "wide", "overview") if c in CAMS)] + MOUNTED_CAMS
DEFAULT_FPS = next((f for f in range(5, 0, -1) if len(DEFAULT_CAMS) * (int(round(30.0 * CTRL_HZ))
                    // max(1, int(round(CTRL_HZ / f))) + 2) <= MAX_FRAMES), 0)
if not DEFAULT_FPS:
    raise RuntimeError(f"no default video_fps fits max_frames_per_call = {MAX_FRAMES} with the cameras {DEFAULT_CAMS}")


def cam_world_T_cv(c: str) -> np.ndarray:
    m = CALIB[c]
    return m["world_T_cv"] if m["mount"]["type"] == "static" else RIG.link_T(m["parent_body"]) @ m["link_T_cv"]


def camera_info(cams) -> dict:
    out = {}
    for c in cams:
        Tw = cam_world_T_cv(c)
        out[c] = {"intrinsic_cv": CALIB[c]["K"].tolist(), "extrinsic_cv": np.linalg.inv(Tw)[:3].tolist(),
                  "cam2world_gl": (Tw @ X.GL2CV).tolist(), "image_size": [X.W, X.H]}
    return out


def grab(cams, want_depth: bool):
    render()
    rgb, dep = {}, {}
    for c in cams:
        out = CAMS_OBJ.cams[c].data.output
        rgb[c] = out["rgb"][0, ..., :3].to("cpu").numpy()
        if want_depth:
            dep[c] = out["distance_to_image_plane"][0].to("cpu").numpy()
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: np.linalg.inv(cam_world_T_cv(c))[:3] for c in cams}


def video_frame():
    """The live video's frame: every camera, half size, three to a row."""
    rgb, _ = grab(CAMS, False)
    tiles = [np.ascontiguousarray(rgb[c][::2, ::2]) for c in CAMS]
    cols = min(3, len(tiles))
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)


VIDEO = live_video.LiveVideo(DATA, ctrl_hz=CTRL_HZ, frame=video_frame, log=EP.log)

# ---------------------------------------------------------------- the spec
PLAY, PGROUPS = RIG.proprio_spec()
KIN = RIG.kinematics_spec()
CAM0 = camera_info(CAMS)
KIN_DEV = RIG.kin_check()
if KIN_DEV > 0.002:
    raise RuntimeError(f"kinematic model: FK of the measured joints is {KIN_DEV * 1000:.2f} mm from the simulator's wrist/hand")
STEP_S = 1.0 / CTRL_HZ
SPEC = {
    "protocol": PROTOCOL, "simulator": "embodiedswe (robobench on Isaac Lab 2.3.2 / Isaac Sim 5.1, GPU PhysX)",
    "robot": RIG.robot_spec()["name"], "task_text": TASK["text"] + ("\n\n" + TASK["success"] if TASK.get("success") else ""), "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "physics_hz": 1.0 / env.dt,
    "max_chunk_s": MAX_CHUNK_S, "max_frames_per_call": MAX_FRAMES,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": v["what"], "resolution": [X.W, X.H], "calibration_in_obs": True,
                    "intrinsic_cv": CAM0[c]["intrinsic_cv"], "mount": CALIB[c]["mount"], "depth_range_m": [0.01, 100.0]}
                for c, v in ((v["name"], v) for v in CAMS_OBJ.views)},
    "default_cameras": list(DEFAULT_CAMS),
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "14400")),
               "default_video_fps": DEFAULT_FPS, "images_per_call": (f"max_frames_per_call = {MAX_FRAMES} images per call (PROTOCOL §3 \"Images per call\"): cameras x the "
                     "frames really captured (the first, one every round(control_hz / video_fps) control steps, the last), a "
                     "per-frame depth one more image each; video mp4, frames and both capture the same frames, video none only "
                     "the first and the last. A call over it is a 400 before anything runs. Defaults: "
                     f"cameras {DEFAULT_CAMS}, video_fps {DEFAULT_FPS} (the longest call at the defaults fits)")},
    "action_types": {
        "ee_pose": {"dim": DIM, "layout": list(RIG.layout), "frame": "world (the simulator's world frame, metres; z up)", "quaternion": "wxyz",
                    "description": RIG.describe_action(),
                    "semantics": (f"targets streamed at the {CTRL_HZ:g} Hz control rate: rows `dt` apart (a multiple of {STEP_S:.6f} s, at most "
                                  "0.5 s; anything else is a 400, never rounded); between rows linear (positions, joint targets; quaternions "
                                  "slerped) or hold (`interpolate`); the first row starts from the target in force. Each control step hands "
                                  "the robot's own controller the target of that step: " + RIG.controller_text() + ". The last row stays in "
                                  "force after the call (a watch holds it). Joint targets go to the position drives as given (not clipped, "
                                  "as in EmbodiedSWE): a target past a joint's limit presses the joint against that limit (a firmer grip)."),
                    "joint_limits": RIG.action_limits()},
        "not_yet": ["joint_position", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"],
        "note": "joint_position is not offered: these robots are driven through EmbodiedSWE's own task-space controllers (operational-space "
                "torque control, Pink IK), and a joint-position mode would be another controller; use /kinematics to plan in joint space"},
    "proprio_layout": PLAY, "proprio_groups": PGROUPS,
    "static": {},
    "world": {"frame": "the simulator's world frame (one environment, its origin at the world origin); z up; every pose, camera "
                       "extrinsic and ee_pose target is in it", "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"},
              "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes (x right, y up, z back)"},
    "max_control_steps": int(R.MAX_STEPS),
    "episode": ("one episode, no reset: a success never ends it and is never shown; it ends at your POST /finish, "
                + ("when the hand or a finger touches the bread (the tool-only rule: that disqualifies the episode), " if TOOL else "")
                + f"when your time is up, on a simulator error, or after {int(R.MAX_STEPS):,} control steps "
                f"({R.MAX_STEPS / CTRL_HZ / 3600:.1f} h of simulated time: a technical cap, reason \"step_limit\"); graded as it stands then"),
    "robot_spec": RIG.robot_spec(),
    "kinematics": KIN,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE},
}
L.check_spec(SPEC)
EP.scene_built()


# ---------------------------------------------------------------- the episode record
def write_final() -> None:
    if L.final_verdict(DATA):
        return
    n = ctrl_steps()
    L._write_json(os.path.join(DATA, "final.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": PRESET,
                   "protocol": PROTOCOL, "finalized": False, **EP.final_fields(), **AE.final_fields(E, n)})


def verdict() -> dict:
    """The privileged verdict on the live state (rcb_embodiedswe._final: success, progress, the tool-only record)."""
    try:
        return R._final(env, grader, INST)
    except Exception as exc:  # noqa: BLE001 -- the env broken by a failed step: success 0, progress = the rubric's peak
        traceback.print_exc()
        return R._unreadable_final(env, grader, exc)


def last_frame():
    """The live video's last frame, or None when it would need a render outside the main thread (the collect hook's
    SIGUSR1 runs the end in a thread, and a Kit render from there hangs): after a call the cameras already show the end
    state; only a resumed episode (replayed without rendering) ends without its last frame."""
    if _R["step"] != ctrl_steps() and threading.current_thread() is not threading.main_thread():
        return None
    return video_frame()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    V = dict(E.get("verdict") or verdict())
    # The live episode's ending decides: after a crash and an (approx) resume the verdict comes back from the checkpoint;
    # an episode that ended in success stays a success even when its replayed state reads otherwise, and a tool contact
    # (the disqualification) wins over everything
    if E.get("reason") == "success" and not V.get("success"):
        V.update({"success": True, "success_restored": True})
    if E.get("reason") == "tool_contact" or (TOOL is not None and TOOL.touched):
        V.update({"success": False})
    E["success"] = bool(V.get("success"))
    try:
        TRAJ.frame()
    except Exception as exc:  # noqa: BLE001
        log({"ev": "final_frame_error", "error": repr(exc)[:300]})
    try:
        TRAJ.save(os.path.join(DATA, "trajectory.npz"), label="standard", final_sha=V.get("final_sha") or "")
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = ctrl_steps()
    L._write_json(os.path.join(DATA, "episode.json"),
                  {**{k: v for k, v in V.items() if k != "final_sha"}, "success": bool(V.get("success")), "live_sha": V.get("final_sha"),
                   "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": PRESET, "protocol": PROTOCOL,
                   "n_actions": n, "success_seen_step": E.get("success_step"), **INSTANCE_CHECK, **EP.final_fields(), **AE.final_fields(E, n),
                   **({"infra_error": 1} if E["reason"] == "infra_error" else {})})
    write_final()
    VIDEO.last(ctrl_steps(), frame=last_frame)


def finish(reason: str) -> None:
    if E["done"]:
        return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    E["verdict"] = verdict(); E["success"] = bool(E["verdict"].get("success"))
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1),
         "success": E["success"], "progress": E["verdict"].get("progress")})
    dump()


def check_success() -> bool:
    if TOOL is not None and TOOL.touched:
        return False
    return bool(grader.check_success()[0])


# ---------------------------------------------------------------- request fields (a 400 before anything runs)
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
        return list(DEFAULT_CAMS)
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not v or not all(isinstance(c, str) for c in v):
        raise ValueError(f"cameras must be a non-empty list of camera names ({', '.join(CAMS)})")
    bad = [c for c in v if c not in CAMS]
    if bad:
        raise ValueError(f"unknown camera(s) {bad}: the cameras are {', '.join(CAMS)}")
    return list(dict.fromkeys(v))


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return DEFAULT_FPS
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


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
    except Exception as exc:  # noqa: BLE001 -- nothing executed yet: a bad request, not a simulator error
        raise ValueError(f"malformed request: {exc!r}"[:300]) from None


def every_of(fps: int, video: str = "frames") -> int:
    """The recorder's stride in control steps; video "none" captures only the call's first and last frame."""
    if video == "none":
        return 1 << 62
    return max(1, int(round(CTRL_HZ / max(1, fps))))


def frames_ok(cams, steps: int, fps: int, depth: str, video: str) -> None:
    """A 400 before anything runs for a call of `steps` control steps over max_frames_per_call (PROTOCOL §3): the frames
    the recorder captures at its stride (rcb_limited.frames_per_call), per-frame depth counted again."""
    n = L.frames_per_call(steps, every_of(fps, video)) if steps > 0 else 1
    L.check_frames(len(cams), n, depth in ("frames", "legacy"), MAX_FRAMES)


def recorder(cams, fps: int, video: str, depth: str) -> L.Recorder:
    """The shared Recorder; max_images is a guard only (every call is checked before it runs): past the budget it stops
    filming, keeps the last frame and counts frames_skipped."""
    return L.Recorder(cams, every_of(fps, video), grab, proprio_row, extrinsics, ctrl_steps, depth=depth, clock_hz=CTRL_HZ,
                      max_images=MAX_FRAMES)


def proprio_row() -> np.ndarray:
    return RIG.proprio()


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 4),
            "time_s": round(L.agent_time(E), 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
            "proprio": {"layout": PLAY, "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"], "cameras": camera_info(cams)}


def save_call_evidence(idx: int, meta: dict, rec: L.Recorder) -> None:
    """The call's record on disk (meta + last frames); a disk failure here costs the record, never the episode."""
    try:
        d = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(d, exist_ok=True)
        L._write_json(os.path.join(d, "meta.json"), L._jsonable(meta))
        from PIL import Image
        for c in rec.cams:
            if rec.frames[c] and rec.frames[c][-1] is not None:
                Image.fromarray(rec.frames[c][-1]).save(os.path.join(d, f"last_{c}.jpg"), quality=85)
    except Exception as exc:  # noqa: BLE001
        log({"ev": "evidence_error", "call": idx, "error": repr(exc)[:300]})


class InfraError(RuntimeError):
    """A host failure (disk, ffmpeg) after the call ran: the episode ends infra_error, not as the agent's sim error."""


def respond(out: dict, rec: L.Recorder, video: str, fps: int) -> list:
    """The response parts (the shared layer sizes and builds the body); when the frames/video cannot be built (an
    encoder or disk failure) the call still answers, degraded to what is left: extrinsics, proprio, the per-frame arrays."""
    if rec.skipped:
        out["frames_skipped"] = rec.skipped
    try:
        return rec.parts(video, fps)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(); log({"ev": "response_error", "error": repr(exc)[:300]})
        out["degraded"] = f"the frames/video could not be built ({type(exc).__name__}): dropped from this response"
    try:
        return rec.parts("none", fps)
    except Exception as exc:  # noqa: BLE001
        raise InfraError(f"the response could not be built: {exc!r}"[:300]) from exc


def executing(fn: Callable) -> Callable:
    """A ValueError once the call has started executing is a simulator error (500), not a bad request (400)."""
    def run(*args):
        try:
            return fn(*args)
        except ValueError as exc:
            raise RuntimeError(f"during execution: {exc}") from exc
    return run


# ---------------------------------------------------------------- executing
def native_step(native: np.ndarray) -> None:
    """One control step of EmbodiedSWE's native action, as the privileged rollout executes it (recorded, then stepped,
    then the grader records)."""
    import torch
    a = np.asarray(native, dtype=np.float32)
    TRAJ.actions.append(a.copy())
    env.step(torch.as_tensor(a, device=env.device).reshape(1, -1))
    grader.record()
    h = grader.history  # bounded: the peak-progress record and the latest one (the verdict reads only the peak)
    if len(h) > 2:
        h[:] = [h[1] if h[1][0]["progress"] > h[0][0]["progress"] else h[0], h[-1]]
    TRAJ.after_step()


def ctrl_step(target: np.ndarray, rec: L.Recorder) -> bool:
    """One control step towards `target` (a full ee_pose row); journaled. True when the call must stop here."""
    native = RIG.native(target)
    native_step(native); stop = EP.journal(native); rec.tick(); VIDEO.offer(ctrl_steps())
    AE.hidden_success(E, check_success(), log, ctrl_steps())   # the success is only recorded, never ends the episode
    if TOOL is not None and TOOL.touched:
        finish("tool_contact")
    elif ctrl_steps() >= R.MAX_STEPS:
        finish("step_limit")
    return E["done"] or stop


def parse_submit(meta: dict, A: np.ndarray) -> tuple:
    typ = meta.get("type")
    if typ == "joint_position":
        raise ValueError("joint_position is not offered by this task (spec.action_types.note): use ee_pose; /kinematics gives FK and IK")
    if not isinstance(typ, str) or typ != "ee_pose":
        raise ValueError(f"type must be ee_pose (not offered: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", STEP_S); interp = choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = cameras(meta); fps = video_fps(meta); video = choice(meta, "video", "mp4", ("mp4", "frames", "both", "none"))
    note = note_text(meta); depth = L.depth_mode(meta)
    if A.ndim != 2 or A.shape[1] != DIM or A.shape[0] < 1:
        raise ValueError(f"ee_pose actions must be (T, {DIM}) with T >= 1, got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (STEP_S - 1e-9 <= dt <= 0.5 + 1e-9):
        raise ValueError(f"dt must be in [{STEP_S:.6f}, 0.5] s")
    k = dt * CTRL_HZ
    if abs(k - round(k)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the {STEP_S:.6f} s control period (k / {CTRL_HZ:g} s); got {dt}")
    k = int(round(k))
    if A.shape[0] * k * STEP_S > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s = {MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    RIG.check_rows(A)
    frames_ok(cams, A.shape[0] * k, fps, depth, video)
    return dt, k, interp, cams, fps, video, note, depth


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    return executing(run_submit)(A, *as_400(parse_submit, meta, A))


def run_submit(A, dt, k, interp, cams, fps, video, note, depth) -> tuple[dict, list]:
    rec = recorder(cams, fps, video, depth); clipped: list = []
    E["calls"] += 1; step0 = E["step"]; before = ctrl_steps(); rec.tick(force=True)
    prev = np.asarray(E["tgt"], dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        row = np.asarray(row, dtype=np.float64)
        stop = False
        for j in range(1, k + 1):
            t = row if interp == "hold" else X.interp_row(RIG, prev, row, j / k)
            E["tgt"] = [float(v) for v in t]
            if ctrl_step(t, rec):
                stop = True; break
        E["tgt"] = [float(v) for v in row] if not stop else E["tgt"]
        prev = row
        if stop:
            break
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": "ee_pose", "executed_rows": E["step"] - step0,
           "control_steps_chunk": ctrl_steps() - before, "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
           "clipped": clipped[:200], "n_clipped": len(clipped), "plan": [], "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": "ee_pose", "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams,
         "note": note, "depth": depth, "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "done": E["done"],
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    save_call_evidence(E["calls"], {k_: v for k_, v in out.items() if k_ != "cameras"}, rec)
    return out, respond(out, rec, video, fps)


def parse_observe(meta: dict) -> tuple:
    cams = cameras(meta); seconds = number(meta, "seconds", 0.0); fps = video_fps(meta)
    video = choice(meta, "video", "frames", ("mp4", "frames", "both", "none")); depth = L.depth_mode(meta)
    if seconds < 0 or seconds > MAX_CHUNK_S:
        raise ValueError(f"seconds must be in [0, {MAX_CHUNK_S}] (max_chunk_s)")
    steps = int(round(seconds * CTRL_HZ))
    frames_ok(cams, steps, fps, depth, video)
    return cams, seconds, steps, fps, video, depth


def do_observe(meta: dict) -> tuple[dict, list]:
    return executing(run_observe)(*as_400(parse_observe, meta))


def run_observe(cams, seconds, steps, fps, video, depth) -> tuple[dict, list]:
    rec = recorder(cams, fps, video, depth); before = ctrl_steps()
    if steps > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(E["tgt"], dtype=np.float64)
        for _ in range(steps):
            if ctrl_step(hold, rec):
                break
        rec.tick(force=True, last=True)
    else:
        rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "depth": depth, "control_steps": ctrl_steps() - before,
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    if steps > 0:
        save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, respond(out, rec, video if steps > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    return RIG.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1), **AE.steps_left(ctrl_steps())}


def end_from_signal() -> None:
    with LOCK:
        E["exiting"] = True
        if not E["done"]:
            finish("timeout")
        else:
            dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped (graded by the live episode), releasing the simulator"})
        if not os.path.exists(PID_FILE):
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)


def replay_row(row) -> None:
    """One journaled native row during a resume (nothing rendered)."""
    native_step(np.asarray(row, dtype=np.float64)); RIG.after_replay(row)


E["tgt"] = [float(v) for v in RIG.hold()]
TRAJ.frame()
VIDEO.offer(0)
resumed = EP.begin(state=E, step=replay_row, state_sha=lambda: R.state_sha(env), proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
                   start_event={"task": PRESET, "seed": int(INST["seed"]), "cameras": CAMS, "kinematics_dev_m": round(KIN_DEV, 6),
                                **{k: v for k, v in INSTANCE_CHECK.items()}})
if resumed:
    VIDEO.truncate(ctrl_steps())
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready: {PRESET} (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
AE.serve(AE.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                    on_submit_error=lambda exc: finish("infra_error" if isinstance(exc, InfraError) else "error"), log=log, episode=EP,
                    state_sha=lambda: R.state_sha(env), proprio=proprio_row,
                    finish=lambda: finish("finished"), end_step_limit=lambda: finish("step_limit")))
