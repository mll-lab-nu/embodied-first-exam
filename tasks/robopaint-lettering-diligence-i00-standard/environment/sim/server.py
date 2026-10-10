"""eai-standard/2.2 sim service for the RoboPaint brush tasks (ManiSkill 3.0.1 Panda with a brush; the mark is the task's
brush model in rcb_brush.py; see docs/STANDARD_MODE_2_2.md). Owns the scene and the sheets. HTTP surface (rcb_limited.py, the
services' shared layer): GET /spec, GET /status, POST /observe, POST /submit (RCB1 bodies, RCB1 responses: videos / frames / depth /
proprio as raw blobs, never base64), POST /kinematics (stateless FK / IK of the robot's model). Logs every call to /data/episode.jsonl.
Nothing about the sheets except camera images ever leaves this process: no score, no record of the strokes, no exact canvas, no brush state,
no brush model; depth is the renderer's geometry (the ink and paint are colours on the sheets, never in depth). The target is the picture
/app/target.png in the agent's container.

Differences from the RoboLab service, all from the task:
- rows are streamed at the 20 Hz CONTROL rate (physics 100 Hz, 5 substeps); the joint action is ManiSkill's pd_joint_pos (7 targets);
- `ee_pose` rows are brush-tip poses `dt` apart: the tip target moves on a straight line (orientation slerped) from the previous row's
  target at the 20 Hz control rate, one IK solve per control step (SAPIEN's Pinocchio CLIK, no collision checking), at most
  0.25 m/s (a faster row is slowed down and reported);
- painting has no terminal state: the episode ends only when the agent phase ends (the collect hook) or on a simulator error;
- the trajectory is replayed in fresh processes by the collect hook (environment/sim/finalize.sh) after this service has exited,
  exactly as the privileged verifier does, and only then scored;
- crash recovery (rcb_limited.Episode, docs/STANDARD_MODE_2_2.md §13): every executed control step (the 7 joint targets given to
  Session.step) is journaled and every completed call checkpointed with the state hash; after a crash compose restarts the
  container and this service replays the journal in its fresh process and continues the SAME episode. Resume class `exact`
  (PhysX on the CPU and the CPU brush models repeat bit for bit in a fresh process); the last ee_pose tip target is persisted
  (the start of the next `ee_pose` line)."""
from __future__ import annotations
import json, math, os, signal, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "calli_yong"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 20; SUBSTEPS = 5
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
VIDEOS = ("mp4", "frames", "both", "none")
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "t0": time.time(), "error": None}
EP = L.Episode(DATA, dim=7, resume="exact", persist=("tip_target",))   # the journal rows are Session.step's 7 joint targets
EP.startup()                           # before the scene is built: start count, back-off after failed starts, startup watchdog
log = EP.log


def ctrl_steps() -> int:
    return int(S.n_steps)


def write_final() -> None:
    if L.final_verdict(DATA):          # a verdict on disk (the service gave up after crashes) is never overwritten
        return
    n = int(E.get("episode_control_steps") or ctrl_steps())
    L._write_json(os.path.join(DATA, "final.json"),
                  {"steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK,
                   "protocol": PROTOCOL, "finalized": False, "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), **EP.final_fields()})


def dump() -> None:
    """The episode is over: save the recorded trajectory, the live canvas and its hash for the collect hook (lock held)."""
    if E.get("dumped"): return
    E["dumped"] = True
    live = {}
    try:
        S.painter.finish()
        acts = S.record_stop(); E["n_actions"] = int(len(acts))
        S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode", "steps": E["step"], "reason": E["reason"]})
        live = S.status(); E["live_sha"] = live["state_sha"]
        from PIL import Image
        Image.fromarray(S.canvas("main")).save(os.path.join(DATA, "canvas_live.png"))
        Image.fromarray(S.canvas("practice")).save(os.path.join(DATA, "canvas_live_practice.png"))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    json.dump({"steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
               "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
               "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), **EP.final_fields(),
               "live": {k: v for k, v in live.items() if isinstance(v, (int, float, bool))}}, open(os.path.join(DATA, "episode.json"), "w"))
    write_final()


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time(); E["episode_control_steps"] = ctrl_steps()
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1)})


# ---------------------------------------------------------------- scene
import rcb_brush as M  # noqa: E402
S = M.Session(instance=INSTANCE, task=TASK, strict=True, render=True)
if not S.render_enabled:
    raise SystemExit("the sim service needs a Vulkan-capable GPU for its cameras")
LAYOUT = [f"panda_joint{i}" for i in range(1, 8)]
CAMS = list(M.VIDEO_CAMERAS)
DEFAULT_CAMS = ["canvas_cam", "scene_cam", "side_cam"]           # what the 2.0 client asked for when a call named no camera
MOUNT = {"canvas_cam": "static, straight above the main sheet, looking down; image top = the sheet's far edge (+x), image left = +y",
         "practice_cam": "static, straight above the practice sheet, looking down; image top = +x, image left = +y (portrait)",
         "scene_cam": "static, across the table facing the robot (from +x), looking down at the board",
         "side_cam": "static, low on the robot's right (-y side), a grazing view along the sheets' surface (brush height above the paper)"}


def images(cams) -> dict:
    return {c: S.render_frame(c) for c in cams}


FIRST = images(CAMS)


def joint_limits() -> dict:
    lim = S.robot.get_qlimits()[0].cpu().numpy()[:7]
    return {n: [round(float(lo), 4), round(float(hi), 4)] for n, (lo, hi) in zip(LAYOUT, lim)}
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)   # (7, 2)
G = S.geo

TGT = S.inst["target"]; W0 = S.inst["wells"]; BR = S.inst["brush"]; SH = S.sheet_facts()
TARGET_PX = S.geo.rows
# per medium: what the robot holds and what a user of such a tool would know about it (never the mark's model or a width table)
TASK_TEXT = "Copy the exemplar shown in the picture /app/target.png onto the main sheet (at most the stated number of strokes)."
WORD = "paint" if S.medium == "mypaint" else "ink"      # what the tool carries
if S.medium == "calligraphy":
    ROBOT_TEXT = "franka-panda holding a Chinese calligraphy brush (rigid handle + a collision-free soft tuft; the TCP is the tip of the unbent tuft)"
    TOOL = {"kind": "a large Chinese writing brush (soft hair tuft)", "tuft_length_m": BR["bristle_m"], "handle_stop_depth_m": BR["bristle_m"],
            "hold": "vertical (the tuft points straight down at the start)"}
elif S.medium == "broad_nib":
    ROBOT_TEXT = "franka-panda holding a broad-edge (chisel) dip pen (rigid holder + a collision-free steel nib; the TCP is the middle of the nib's edge)"
    TOOL = {"kind": "a broad-edge steel nib (a chisel-shaped writing edge)", "nib_width_m": BR["nib_width_m"],
            "edge_axis": "the writing edge lies along the tool's y axis (the second column of the tip pose's rotation); at the start pose that is "
                         "along the writing line (world -y)", "holder_stop_depth_m": BR["bristle_m"],
            "hold": "vertical (the pen points straight down at the start); a tilted pen writes with only the part of the edge that touches"}
elif S.medium == "pointed_pen":
    ROBOT_TEXT = "franka-panda holding a pointed flexible dip pen (rigid holder + a collision-free split steel point; the TCP is the point)"
    TOOL = {"kind": "a pointed flexible steel nib (two tines split by a slit)", "hairline_m": BR["hairline_m"], "max_width_m": BR["max_width_m"],
            "flex": (f"a light touch writes a hairline {BR['hairline_m'] * 1000:.1f} mm wide; pressed deeper, the tines spread apart and the "
                     f"line widens, up to {BR['max_width_m'] * 1000:.1f} mm when they are fully open (no wider beyond); how the width follows "
                     f"the press is for you to find out (the practice sheet is there for that)"),
            "spread_axis": "the tines spread along the tool's y axis (the second column of the tip pose's rotation); at the start pose that is "
                           "along the writing line (world -y); a pressed stroke is wide where it moves across that axis and stays thin where it "
                           "moves along it", "holder_stop_depth_m": BR["bristle_m"],
            "hold": "vertical (the pen points straight down at the start)"}
elif S.medium == "mypaint":
    ROBOT_TEXT = "franka-panda holding an oil-paint brush (rigid handle + a collision-free soft tuft; the TCP is the tip of the unbent tuft)"
    TOOL = {"kind": "an oil-paint brush (soft hair tuft)", "tuft_length_m": BR["bristle_m"], "handle_stop_depth_m": BR["bristle_m"],
            "hold": "vertical (the tuft points straight down at the start)"}
else:
    ROBOT_TEXT = "franka-panda holding a brush"
    TOOL = {"kind": S.medium}
WHERE = ("center_xy", "surface_z")      # where things are in the world is never given in standard mode (user, 2026-09-28 20:30)
STATIC = {
    "sheets": {n: {**{k: v for k, v in f.items() if k not in WHERE}, "scored": n == "main",
                   "note": ("scored" if n == "main" else "for test strokes: never scored, never counted")} for n, f in SH.items()},
    "paper_frame": "each sheet is axis-aligned; its millimetres: X to the robot's right, Y towards the robot, origin at the sheet's far-left "
                   "corner seen from the base",
    "target_image": {"file": "/app/target.png", "size_px": [TARGET_PX, TARGET_PX], "covers": "the whole main sheet",
                     "mm_per_px": round(S.geo.px_m * 1000, 6),
                     "pixel_to_paper_mm": "pixel (column u, row v), from 0 at the top-left: centre at X = (u + 0.5) * mm_per_px, "
                                          "Y = (v + 0.5) * mm_per_px (main sheet millimetres, paper_frame)",
                     "orientation": "row 0 = the sheet's far edge (+x), column 0 = its left edge seen from the base (+y); = canvas_cam's orientation",
                     "content": ("the exemplar painting on the main sheet" if S.medium == "mypaint" else "the exemplar in ink on paper")},
    "strokes": {"max_strokes_on_main_sheet": int(TGT["success"]["max_strokes"]),
                "stroke": f"one continuous contact of the {WORD}-loaded tip with the main sheet (tip over the sheet and below its surface)",
                "practice_sheet": "strokes there are never scored and never counted",
                "order": ("not a separate criterion: later strokes lie over and blend into earlier ones, so the order shows in the painting"
                          if S.medium == "mypaint" else "reported, not part of success")},
    "wells": {"wells": [{k: w[k] for k in ("name", "hex", "rgb", "radius_m")} for w in W0["wells"]],
              "plate_half_size_m": W0["plate_half_size"], "rule": W0["rule"]},
    "brush": {**TOOL, "marks_when": f"the tip ({'the nib' + chr(39) + 's edge' if S.medium == 'broad_nib' else ('the point' if S.medium == 'pointed_pen' else 'the tuft')}) is below a sheet's surface over the sheet with {WORD} loaded",
              "starts": f"dry (no {WORD}: strokes leave no mark until the first dip)",
              "loaded": f"not reported by the robot; the tool's tip shows the {WORD}'s colour on the cameras when loaded"},
}


def calib(names) -> dict:
    r = lambda a: [[round(float(x), 6) for x in row] for row in np.asarray(a)]  # noqa: E731
    out = {}
    for n in names:
        prm = S.camera_params(n)
        out[n] = {"intrinsic_cv": r(prm["intrinsic_cv"]), "extrinsic_cv": r(prm["extrinsic_cv"]), "cam2world_gl": r(prm["cam2world_gl"]),
                  "image_size": [int(FIRST[n].shape[1]), int(FIRST[n].shape[0])]}
    return out
CALIB = calib(CAMS)                     # static cameras: computed once (meta["cameras"], the per-frame extrinsics and /spec agree exactly)
EXT = {c: np.asarray(CALIB[c]["extrinsic_cv"], np.float64) for c in CAMS}
NEAR_FAR = {c: [float(S.u.scene.human_render_cameras[c].config.near), float(S.u.scene.human_render_cameras[c].config.far)] for c in CAMS}
TIP = M.TOOL_FRAME
PROPRIO = (LAYOUT + ["tip_x", "tip_y", "tip_z", "tip_qw", "tip_qx", "tip_qy", "tip_qz"]          # the 2.0 columns, unchanged
           + [f"{j}_vel" for j in LAYOUT] + [f"{j}_effort" for j in LAYOUT])                      # 2.2
SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "maniskill 3.0.1 (SAPIEN 3.0.3, PhysX CPU) + a virtual brush",
    "robot": ROBOT_TEXT,
    "task_text": TASK_TEXT,
    "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "physics_hz": CTRL_HZ * SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT.get(c, "static"), "resolution": [int(FIRST[c].shape[1]), int(FIRST[c].shape[0])],
                    "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": CALIB[c]["intrinsic_cv"], "depth_range_m": NEAR_FAR[c],
                    "mount": {"type": "static", "extrinsic_cv": CALIB[c]["extrinsic_cv"], "cam2world_gl": CALIB[c]["cam2world_gl"]}} for c in CAMS},
    "default_cameras": DEFAULT_CAMS,
    "action_types": {
        "joint_position": {"dim": 7, "layout": LAYOUT, "units": "rad", "limits": LIMITS,
                           "semantics": "absolute joint targets (ManiSkill pd_joint_pos, PD-tracked, gravity compensated) streamed at the 20 Hz "
                                        "control rate; rows `dt` apart (a multiple of 1/20 s), hold or linear interpolation between rows; "
                                        "out-of-limit values are clipped and reported"},
        "ee_pose": {"dim": 7, "layout": ["x", "y", "z", "qw", "qx", "qy", "qz"],
                    "frame": "world, metres: z up, the robot base at (-0.615, 0, 0), x away from the base, y to the robot's left",
                    "quaternion": "wxyz, unit norm (brush pointing straight down = the proprio quaternion at the start)",
                    "semantics": f"brush-tip targets `dt` apart: the tip target moves on a straight line from the previous row's target "
                                 f"(orientation slerped) at the 20 Hz control rate with one IK solve per control step (no collision checking); "
                                 f"at most {M.MAX_TIP_SPEED} m/s (a faster row is slowed down, see plan[]); a control step whose IK does not "
                                 f"converge holds the previous joint targets and is counted in plan[]. At most 400 rows per submit."},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO,
    "proprio_groups": {
        "joint_pos": [0, 7, "measured joint positions (rad), panda_joint1..7"],
        "tcp_pose": [7, 7, f"measured pose of the tool frame '{TIP}' (the brush tip, the TCP): x y z (m, world) + quaternion wxyz"],
        "joint_vel": [14, 7, "measured joint velocities (rad/s)"],
        "joint_effort": [21, 7, "PD drive-effort estimate per joint (N m): stiffness * (target - q) - damping * qdot from the measured q, qdot "
                                "and the current joint target, clipped at the drive's effort limit; the robot's links carry no gravity here, so "
                                "it is about 0 at rest and rises while the arm lags a moving target or presses on something with its rigid parts"],
        "gripper_opening": [28, 0, "none: the tool is fixed to the hand (no gripper)"]},
    "static": STATIC,
    "world": {"frame": "defined by the robot: its base (panda_link0) stands at (-0.615, 0, 0) with the world's orientation "
                       "(robot_spec.base.pose); x forward (away from the base), y to the robot's left, z up",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV (x right, y down, z forward); cam2world_gl: OpenGL (x right, y up, z backward)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "7200"))},
    "robot_spec": S.robot_spec(),
    "kinematics": S.kinematics_spec(),
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE,
              "note": "the renderer's geometry: the ink and paint are colours on the sheets and never show in depth"},
    "on_service_error": L.ON_SERVICE_ERROR, "max_call_wall_s": EP.max_call_wall_s,
}


def proprio_row() -> np.ndarray:
    p, q = S.tip_pose()
    return np.concatenate([S.joint_positions(), p, q, S.joint_velocities(), S.joint_efforts()]).astype(np.float32)


def grab(cams, want_depth: bool) -> tuple[dict, dict]:
    """RGB of every requested camera and, if asked, the depth of the same capture (pixel-aligned; never steps)."""
    rgb, dep = {}, {}
    for c in cams:
        rgb[c] = S.render_frame(c)
        if want_depth:
            dep[c] = S._depth_of(c)
    return rgb, dep


def extrinsics(cams) -> dict:
    return {c: EXT[c] for c in cams}


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(cams, max(1, int(round(CTRL_HZ / max(1, fps)))), grab, proprio_row, extrinsics, ctrl_steps,
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(time.time() - E["t0"], 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - (time.time() - E["t0"]), 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            **({"cameras": {c: CALIB[c] for c in cams}} if OBS_CALIBRATION else {})}


def save_call_evidence(idx: int, meta: dict, rec: L.Recorder) -> None:
    d = os.path.join(DATA, "calls", f"{idx:06d}"); os.makedirs(d, exist_ok=True)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"))
    try:
        from PIL import Image
        for c in rec.cams:
            if rec.frames[c] and rec.frames[c][-1] is not None:
                Image.fromarray(np.ascontiguousarray(rec.frames[c][-1])).save(os.path.join(d, f"last_{c}.jpg"), quality=85)
    except Exception:  # noqa: BLE001
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
    """One recorded and journaled control step. True when the call must stop: the episode is over (runaway guard), or the call
    ran past max_call_wall_s / its client hung up (EP.stop_reason)."""
    try:
        S.step(a)
    except M.PrimitiveError:
        finish("step_guard"); return True
    stop = EP.journal(a)
    rec.tick()
    return E["done"] or stop


E["tip_target"] = None                 # last commanded ee_pose target (position, quaternion)


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * CTRL_HZ)))
    E["tip_target"] = None             # joint motion: the next ee_pose line starts from the measured tip
    q_prev = S.hold_action().astype(np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target.copy() if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, dt: float, rec: L.Recorder, plan: list) -> None:
    if E["tip_target"] is None:
        p, q = S.tip_pose(); E["tip_target"] = (p, q)
    for ri, row in enumerate(A):
        E["step"] += 1
        p0, q0 = E["tip_target"]
        p1 = np.asarray(row[0:3], np.float64); q1 = np.asarray(row[3:7], np.float64); q1 = q1 / max(1e-9, float(np.linalg.norm(q1)))
        n_dt = max(1, int(round(dt * CTRL_HZ)))
        n_v = int(math.ceil(float(np.linalg.norm(p1 - p0)) / (M.MAX_TIP_SPEED / CTRL_HZ) - 1e-9))
        n = max(n_dt, n_v); fails = 0
        for k in range(1, n + 1):
            t = k / n
            q, ok, _ = S.ik(p0 + (p1 - p0) * t, M.quat_slerp(q0, q1, t))
            if not ok: fails += 1
            if ctrl_step(q if ok else S.hold_action(), rec):
                E["tip_target"] = (p0 + (p1 - p0) * t, M.quat_slerp(q0, q1, t))
                plan.append({"row": ri, "steps": k, "ik_failures": fails, "slowed": n > n_dt, "stopped": EP.stop_reason or "episode over"}); return
        E["tip_target"] = (p1, q1)
        plan.append({"row": ri, "steps": n, "ik_failures": fails, "slowed": n > n_dt})


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ = meta.get("type"); dt = float(meta.get("dt", 1.0 / CTRL_HZ)); interp = meta.get("interpolate", "linear")
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    fps = int(meta.get("video_fps", 5)); video = meta.get("video", "mp4")
    if typ not in ("joint_position", "ee_pose"): raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dim = SPEC["action_types"][typ]["dim"]
    if A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6: raise ValueError(f"dt must be a multiple of the control period 1/{CTRL_HZ} s")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 400: raise ValueError("ee_pose: at most 400 rows per submit")
    if interp not in ("hold", "linear"): raise ValueError("interpolate must be hold|linear")
    if video not in VIDEOS: raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); clipped: list = []; plan: list = []
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, dt, rec, plan)
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan[:400],
           "rejected": None, "ok": True}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams,
         "note": (meta.get("note") or "")[:500], "control_steps": ctrl_steps() - before, "n_clipped": len(clipped),
         "ik_failures": int(sum(p.get("ik_failures", 0) for p in plan)), "depth": rec.mode})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    cams = [c for c in (meta.get("cameras") or CAMS) if c in CAMS] or CAMS
    seconds = float(meta.get("seconds", 0)); fps = int(meta.get("video_fps", 5)); video = meta.get("video", "frames")
    if not (0 <= seconds <= MAX_WATCH_S): raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if video not in VIDEOS: raise ValueError("video must be mp4|frames|both|none")
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = S.hold_action()
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
    rec.tick(force=True, last=True)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before, "depth": rec.mode})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    return S.kinematics(req)          # the robot's model only: never reads or changes the episode's state


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def _end_from_signal():
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped; the trajectory is replayed in fresh processes next"})
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # finalize.sh starts the replays once this process is gone


L.check_spec(SPEC)                     # a spec that misses a 2.2 field or names a forbidden one never serves
EP.scene_built()                       # the startup watchdog stands down: a long resume replay is not a hang
S.record_start()                       # before begin(): a resume's journal replay is part of the recorded trajectory
resumed = EP.begin(state=E, step=S.step, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC,
                   start_event={"task": TASK, "instance_sha": S.instance_sha, "cameras": CAMS}, on_end=_end_from_signal)
if E.get("tip_target") is not None:    # restored from the checkpoint (JSON lists): back to (position, quaternion) arrays
    E["tip_target"] = tuple(np.asarray(v, np.float64) for v in E["tip_target"])
E["ready"] = True; write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes}{', resumed at control step %d' % ctrl_steps() if resumed else ''})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
