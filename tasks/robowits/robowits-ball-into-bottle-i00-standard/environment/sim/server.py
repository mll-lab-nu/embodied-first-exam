"""eai-standard/2.2 sim service for RoboWits (Genesis 0.4.7, bimanual Marvin; docs/protocol/standard_mode.md): the RoboWits
adapter of the shared layer rcb_limited.py (scripts/eai_standard/). Source: scripts/robowits/shared/server.py, copied
unchanged into every RoboWits standard task as environment/sim/server.py by scripts/robowits/mk_tasks.py.
Owns the scene. HTTP surface (rcb_limited.py): GET /spec, GET /status, POST /observe, POST /submit (RCB1 bodies, RCB1
responses: videos / frames / depth / proprio / per-frame step, time and camera poses as raw blobs, never base64), POST
/kinematics (stateless FK / IK on the robot's own model). Logs every call to /data/episode.jsonl, keeps /data/final.json
current, and grades the live episode (docs/protocol/README.md H.4; owner, 2026-10-17): success = the settle window
that ended the episode passed on this simulator (inside the agent's last call, or after its last command when its phase
is over: Session.settle_check), nothing replayed. The verdict goes to final.json first ("finalized", "graded_by":
"live"); then the recorded (T, 16) trajectory, the deliverable, is rendered once into /data/replay.mp4 for people
("video_pending" while it runs; it never changes the verdict). Nothing about objects ever leaves this process.

Crash recovery (rcb_limited.Episode, docs/protocol/standard_mode.md §13): every executed control step is journaled
(/data/journal.f64, the exact row handed to the simulator), every completed call checkpointed (rows, state hash, proprio
row). After a crash, run.sh exits non-zero, compose restarts the container (`restart: on-failure:6`) and this service
rebuilds the frozen scene, replays the journal up to the last checkpoint and continues the SAME episode, never a reset.
Determinism class: `exact` on Genesis' CPU backend (bit-exact in a fresh process on one host), `approx` on the GPU backend
(RCB_ROBOWITS_BACKEND=gpu, the particle families: Genesis declares it nondeterministic).

Not the agent's failures (infra_error = 1 in the verifier's reward.json): a frozen instance that this host cannot rebuild
within tolerance (another CPU vendor, asset or simulator drift) ends the trial at once, before the agent is served, with
a give-up record (reason "instance_mismatch") instead of crashing into every restart. A service that cannot export the
trajectory's rows or hash the end state keeps the verdict the episode ended with (finalize_error; journal.f64 holds the
rows). A crash in the settle window at the end of the agent's phase counts as a crash inside the agent's last call. A restart that finds the verdict on disk (the service died
while it rendered the video) keeps it, marks the video as over and idles without rebuilding the scene.
Requests (PROTOCOL §4.6): every field of a /submit header and an /observe body is checked for type and range before
anything is executed (ValueError -> 400, no physics); a `joint_position` dt that is not a whole number of control periods
is refused, never rounded.

Differences from the RoboTwin service, all from the simulator: rows are streamed at the 30 Hz CONTROL rate (the recorded
step; 4 physics substeps each), the joint action is RoboWits' own JOINT_ABS layout (per arm 7 joints + gripper width),
`ee_pose` is solved by RoboWits' pink/pinocchio IK instead of a planner, and the wrist cameras move, so the calibration
comes with every response and every frame (wrist cameras are link-mounted: /spec gives the link and the offset).
Depth is Genesis' rasterizer z-depth for the same camera and pixels."""
from __future__ import annotations
import json, math, os, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "stack_cubes"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
BACKEND = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu")
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 30; SUBSTEPS = 4
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
# Crash-safe episode bookkeeping, set up before the scene is built (start count, back-off, startup watchdog)
EP = L.Episode(DATA, dim=16, resume="approx" if BACKEND == "gpu" else "exact")
EP.startup()
log = EP.log
_fin = L.final_verdict(DATA)
if _fin is not None:
    # Restarted with the verdict on disk: the service died while it rendered the video (after `finalized`), or the
    # container was restarted after a give-up. The verdict stands and is not touched; after a grade only `video_done` is
    # set, so that the collect hook (`end --wait-key video_done`) does not wait its whole timeout for a video that will
    # not come. Then idle without rebuilding the scene (Episode.begin would refuse this restart too, after the build).
    if not _fin.get("gave_up") and not _fin.get("video_done"):
        _fin.update(video_done=True, video_pending=False); L._write_json(os.path.join(DATA, "final.json"), _fin)
    EP.give_up("restarted after finalize", infra=False)     # never returns; writes nothing over a verdict


def ctrl_steps() -> int:
    return int(S.n_steps) if E["ready"] else 0


def write_final() -> None:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    L._write_json(os.path.join(DATA, "final.json"), {
        "success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "done": E["done"], "task": TASK, "protocol": PROTOCOL,
        "live_success": bool(E["success"]), "finalized": bool(E.get("finalized")), "n_actions": E.get("n_actions"), "replays": 0,
        **({"graded_by": "live", "video_source": "render", "video_pending": bool(E.get("video_pending"))} if E.get("graded_by") else {}),
        "live_sha": E.get("live_sha"), "video": bool(E.get("video")),
        "video_done": bool(E.get("video_done")), "backend": BACKEND, "grade_error": bool(E.get("grade_error")),
        "instance_exact": E.get("instance_exact"), "settle": E.get("settle"), "agent_time_s": E.get("agent_time_s"),
        "final_window": E.get("final_window"), **{k: E[k] for k in ("trajectory_error", "video_error", "finalize_error") if E.get(k)}, **EP.final_fields()})


VERDICT_KEYS = ("success", "graded_by", "grade_error", "n_actions", "live_sha", "reason", "settle", "final_window")


def finalize() -> None:
    """The verdict is the live episode's: E["success"] is True only when a settle window passed on this simulator, the
    one that ended the episode (settle(): inside the agent's last call, or in finish() after its last command when its
    phase is over, after the collect hook stopped the agent's container). Written at once, nothing replayed. Then the
    deliverable (trajectory.npz; journal.f64 holds the same rows) and ONE render pass of the recorded rows for the video,
    which can no longer change the verdict."""
    with LOCK:
        acts = None
        if E.get("final_window") is None:     # a service restarted after the episode ended: the end event has it
            E["final_window"] = logged_final_window()
        try:
            acts = S.record_stop(); E["live_sha"] = S.state_sha(); E["n_actions"] = int(len(acts))
            try:
                S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"), meta={"source": "standard-mode episode (eai-standard/2.2)", "steps": E["step"],
                                                                                   "reason": E["reason"], "resumes": EP.resumes,
                                                                                   "final_window": E.get("final_window")})
            except Exception as exc:  # noqa — journal.f64 holds the same rows; the verdict does not depend on this file
                traceback.print_exc(); E["trajectory_error"] = repr(exc)[:300]
        except Exception as exc:  # noqa
            # The service could not export the episode's rows or hash its end state. The verdict was decided when the episode
            # ended (finish(): the settle window's result, E["success"]) and stands; journal.f64 holds the rows. Recorded
            # as finalize_error, and there is no video.
            traceback.print_exc(); log({"ev": "finalize_error", "error": repr(exc)})
            E["finalize_error"] = repr(exc)[:300]; acts = None
        E["graded_by"] = "live"; E["finalized"] = True; E["video_pending"] = acts is not None and len(acts) > 0
        log({"ev": "verdict", "graded_by": "live", "success": bool(E["success"]), "reason": E["reason"], "n_actions": E.get("n_actions"),
             "live_sha": E.get("live_sha"), "final_window": E.get("final_window")})
        write_final()                     # the verdict is on disk before the video, whose rendering grows with the episode (~N/60 s for N steps)
        verdict = {k: E.get(k) for k in VERDICT_KEYS}
        if E["video_pending"]:
            try:
                # the recorded rows, as they ran live (a settle window that ended the episode is among them); nothing is judged
                S.start_video(os.path.join(DATA, "replay.mp4"), fps=15)
                S.replay(acts, settle=False); S.stop_video()   # + replay.last.png
                E["video"] = video_ok(os.path.join(DATA, "replay.mp4"))
            except Exception as exc:  # noqa — a failed render loses the video only
                traceback.print_exc(); E["video_error"] = repr(exc)[:300]
        E.update(verdict)                # whatever the video did, the verdict written above is the one that stays
        E["video_pending"] = False; E["video_done"] = True; write_final()


def logged_final_window():
    """The final settle window's length from the episode log's last `end` event (None without one)."""
    w = None
    try:
        for line in open(os.path.join(DATA, "episode.jsonl")):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("ev") == "end":
                w = ev.get("final_window")
    except OSError:
        pass
    return w


def video_ok(path: str) -> bool:
    """The video decodes (ffprobe reads at least one frame), not merely exists."""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=300)
        return r.returncode == 0 and int((r.stdout.strip() or "0").split(",")[0]) > 0
    except Exception:  # noqa
        return False


def start_finalize() -> None:
    if E.get("finalizing"): return
    E["finalizing"] = True; threading.Thread(target=finalize, daemon=True).start()


def journal_step(a) -> bool:
    """One control step outside a call (the end-of-episode settle window): executed, journaled and recorded."""
    row = np.asarray(a, dtype=np.float32); guard = S.step(row); EP.journal(row)
    return guard


def settle(step) -> bool:
    """The verdict's settle window (rcb_robowits.Session.settle_check), run on the live simulator: the robot holds its last
    command for 1 s, then the goal must hold for 2 s, the graded objects released and at rest. Its steps are part of the
    episode (journaled and recorded, so the trajectory and its video hold them). Remembers the result for final.json and
    the call's meta."""
    r = S.settle_check(step=step); E["settle"] = r
    if not r["success"] and r["why"].startswith("the step cap") and not S.episode_done:   # the call was stopped instead
        r["why"] = "the call stopped during the settle window (max_call_wall_s reached or the client hung up)"
    if r["success"]:                    # a passed window ends the episode: the recorded rows end with it,
        E["final_window"] = int(r["steps"]); E["final_window_end"] = ctrl_steps()   # even if the call fails after it
    log({"ev": "settle", **r})
    return bool(r["success"])


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    if not E["success"] and reason in ("timeout", "agent_exit"):
        # the agent phase is over: the last command is held for the settle window and the verdict taken there (as the
        # privileged grader does after the last action of a trajectory); never after a simulator error or at the step cap.
        # The window is the end of the agent's last call (docs/protocol/running.md): it runs as a call ("/settle"), so a crash of the
        # simulator inside it counts as a crash inside the agent's calls on the resume (sim_crashed_on_call when it
        # repeats), never as an infrastructure crash between calls.
        cid = EP.call_begin("/settle")
        try:
            E["success"] = settle(journal_step)
            E["final_window"] = int(E["settle"]["steps"])    # the recorded rows end with this window
            E["final_window_end"] = ctrl_steps()
        except Exception:  # noqa
            traceback.print_exc()
        finally:
            EP.call_end(cid, "/settle")
    if E.get("final_window") and E.get("final_window_end") != ctrl_steps():
        E["final_window"] = None        # rows came after that window (a call that failed after it went on): not the end
    E["episode_control_steps"] = ctrl_steps()
    log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1), "success": bool(E["success"]),
         "final_window": E.get("final_window")})
    write_final(); start_finalize()


# ---------------------------------------------------------------- scene
import rcb_robowits as M  # noqa: E402
S = M.Session(TASK, instance=INSTANCE)  # not strict: an instance this host cannot rebuild is reported below, not raised
EP.scene_built()                        # the startup watchdog stands down: a long resume replay is not a hang
if not S.instance_matches:
    # The frozen scene rebuilt here is out of tolerance (another CPU vendor: docs/benchmarks/robowits.md, Hosts; or asset /
    # simulator drift). It would be the same at every restart, and it is not the agent's failure: give up at once with a
    # record (final.json: finalized, gave_up, reason, infra_error = 1) instead of raising into six restarts without one.
    log({"ev": "instance_mismatch", "task": TASK, "state_sha": S.instance_sha, "backend": BACKEND})
    EP.give_up("instance_mismatch: the frozen instance rebuilt on this host is out of tolerance", infra=True)   # never returns
E["instance_exact"] = bool(S.instance_exact)
E["ready"] = True                       # S exists: ctrl_steps() counts its control steps (a resume replay included)
ROBOT = S.robot
CAMS = ["ego", "wrist_right", "wrist_left"]
# The images one call may hold. Every frame a call records stays in memory until its response is sent, and building the
# response takes about three times the frames' size (a per-frame depth map costs about three RGB frames more): a call
# without a bound could exhaust the sidecar's memory, and a service killed for memory is never the agent's failure
# (PROTOCOL §2.6), so one large request could void a failed trial. MAX_FRAMES images of 848x480 peak at about 5.4 GB of
# the sidecar's 11 GiB (measured on the layer's Recorder and encode_response).
MAX_FRAMES = 1500                  # /spec max_frames_per_call: cameras x frames; a frame with per-frame depth counts DEPTH_FRAME
DEPTH_FRAME = 4
MOUNT = {"ego": "static, above and behind the robot", "wrist_right": "right wrist", "wrist_left": "left wrist"}
ARM = {"right": (slice(0, 7), 7), "left": (slice(8, 15), 15)}
LAYOUT = [f"Joint{i}_R" for i in range(1, 8)] + ["right_gripper"] + [f"Joint{i}_L" for i in range(1, 8)] + ["left_gripper"]
GRIP_MAX = float(M.GRIPPER_OPEN)


def joint_limits() -> dict:
    out = {}
    try:
        ent = ROBOT.robot_entity
        for arm, dofs in (("R", ROBOT.right_arm_dofs), ("L", ROBOT.left_arm_dofs)):
            lo, hi = ent.get_dofs_limit(dofs)
            for i, (l, h) in enumerate(zip(lo.cpu().numpy().reshape(-1), hi.cpu().numpy().reshape(-1))):
                out[f"Joint{i + 1}_{arm}"] = [round(float(l), 4), round(float(h), 4)]
    except Exception:  # noqa — older Genesis: fall back to the joint range the IK uses
        traceback.print_exc()
        out = {n: [-3.107, 3.107] for n in LAYOUT if n.startswith("Joint")}
    out["right_gripper"] = out["left_gripper"] = [0.0, GRIP_MAX]
    return out
LIMITS = joint_limits(); LIM_ARR = np.array([LIMITS[n] for n in LAYOUT], dtype=np.float64)   # (16, 2)

CAM_INFO = S.camera_info(CAMS)
R_SPEC = S.robot_spec(); K_SPEC = S.kinematics_spec()
EE = ["r_x", "r_y", "r_z", "r_qw", "r_qx", "r_qy", "r_qz", "l_x", "l_y", "l_z", "l_qw", "l_qx", "l_qy", "l_qz"]
PROPRIO_LAYOUT = (LAYOUT + EE + [f"{n}_cmd" for n in LAYOUT] + [f"{n}_vel" for n in LAYOUT]
                  + ["right_gripper_opening_m", "left_gripper_opening_m"] + [f"{n}_effort" for n in LAYOUT])
PROPRIO_GROUPS = {   # name: [first column, count, meaning]
    "joint_pos": [0, 16, "measured joint positions in the joint_position layout: 7 arm joints (rad) + gripper opening (m) per arm, right first"],
    "tcp_pose": [16, 14, "measured gripper-tip (TCP) pose per arm, right then left: x y z (m) + qw qx qy qz, world frame; the ee_pose "
                         "action's frame (kinematics tcp_frames Gripper_Tip_R, Gripper_Tip_L)"],
    "joint_cmd": [30, 16, "the commanded joint targets being tracked (joint_position layout): the last streamed row step"],
    "joint_vel": [46, 16, "measured joint velocities (rad/s; the gripper entries: opening rate, m/s)"],
    "gripper_opening": [62, 2, "measured opening of the right and left gripper (m): 0 = closed .. 0.1 = fully open; a gripper closed "
                               "on an object stops above 0"],
    "joint_effort": [64, 16, "the force each PD drive applied at the last physics step (N m; gripper entries: the two fingers' sum, N), "
                             "clamped at the drives' force range: a motor-current analogue that rises when the arm pushes against something"],
}
SPEC = {
    "protocol": PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "robowits (Genesis 0.4.7)", "robot": "marvin-bimanual", "task_text": S.spec["text"],
    "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS, "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S,
    "max_frames_per_call": MAX_FRAMES,
    # not a step budget (budget.steps stays null: the wall clock is the budget) but the technical cap of one episode
    # (PROTOCOL §4.5, `max_control_steps`): the tooling's runaway guard, also the longest trajectory the graders accept
    "max_control_steps": int(S.max_steps),
    "cameras": {c: {"rgb": True, "depth": True, "mounted": MOUNT[c], "resolution": list(CAM_INFO[c]["image_size"]), "calibration_in_obs": OBS_CALIBRATION,
                    "intrinsic_cv": CAM_INFO[c]["intrinsic_cv"], "mount": CAM_INFO[c]["mount"],
                    "depth_range_m": [float(S.env._cameras[c]._options.near), min(float(S.env._cameras[c]._options.far), L.DEPTH_MAX_M)]} for c in CAMS},
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {"dim": 16, "layout": LAYOUT, "units": f"rad for the 7 joints of each arm; gripper opening width in metres, 0 = closed .. {GRIP_MAX} = open",
                           "limits": LIMITS,
                           "semantics": "absolute joint targets tracked by the robot's PD controllers, streamed at the 30 Hz control rate; rows `dt` apart "
                                        "(a multiple of 1/30 s), hold or linear interpolation between rows; out-of-limit values are clipped and reported"},
        "ee_pose": {"dim": 16, "layout": ["r_x", "r_y", "r_z", "r_qw", "r_qx", "r_qy", "r_qz", "right_gripper",
                                          "l_x", "l_y", "l_z", "l_qw", "l_qx", "l_qy", "l_qz", "left_gripper"],
                    "frame": "RoboWits world frame, metres: robot base at (0, 0, 1.08), x away from the robot, y to its left, z up",
                    "quaternion": "wxyz, unit norm",
                    "semantics": "each row is solved by inverse kinematics (RoboWits' pink/pinocchio, no collision checking) and driven to in joint space; "
                                 "`dt` is ignored (the joint distance sets the duration); an arm whose IK fails holds and is reported in plan[]",
                    "note": "the pose is the gripper TIP frame (Gripper_Tip_R/L): +z = approach direction, +x = finger-closing direction; "
                            "same convention as the proprio end-effector poses, so an observed pose is a valid target"},
        "not_yet": ["joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},                       # nothing about where things are (standard mode); the task text names the objects
    "world": {"frame": "RoboWits world frame: the robot base at (0, 0, 1.08), x away from the robot, y to its left, z up",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes "
                             "(x right, y up, z backward)"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "5400"))},
    "robot_spec": R_SPEC,
    "kinematics": K_SPEC,
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE,
              "source": "Genesis rasterizer depth of the same camera (the distance along the optical axis)"},
    "episode": ("ends at the first success: after every /submit and every /observe that watches, the goal is checked (the task "
                "predicate, the graded objects released by the robot); when it holds, the service holds the last command for a "
                "settle window (1 s, then 2 s in which the goal must hold and the graded objects stay at rest, within 2 mm; part "
                "of the call and of the episode) and the episode ends with reason \"success\" if the window passes, else it goes "
                "on (meta[\"settle\"] says why). It also ends when the agent's phase ends (the same window then decides; reason "
                "\"agent_exit\" when the agent ended its session with time left, \"timeout\" at the time limit), on a simulator "
                "error, or after max_control_steps control steps (a technical cap, reason \"step_guard\": the call in progress "
                "stops there, and no settle window is run, so the episode ends as a failure); the verdict is the live episode's: "
                "the settle window that ended it (its steps are part of the recording; nothing is replayed to grade it)"),
}
L.check_spec(SPEC)                      # refuse to start with an incomplete spec or a forbidden field


def check_success() -> bool:
    """The goal right now (rcb_robowits.Session.goal): the predicate with the graded objects released. Not the verdict:
    settle() decides."""
    return bool(S.goal()["success"])


def proprio_row() -> np.ndarray:
    q = np.asarray(S.joint_positions(), dtype=np.float64).reshape(-1)
    ep = [np.concatenate([np.asarray(p), np.asarray(qq)]) for p, qq in (S.ee_pose("right"), S.ee_pose("left"))]
    return np.concatenate([q, ep[0], ep[1], S.hold_action(), S.joint_velocities(), [q[7], q[15]], S.joint_efforts()]).astype(np.float32)


def grab(cameras: list[str], want_depth: bool) -> tuple[dict, dict]:
    rgb = {c: np.ascontiguousarray(S.env.render_frame(0, c)[..., :3]) for c in cameras}
    return rgb, ({c: S.render_depth(c) for c in cameras} if want_depth else {})


def extrinsics(cameras: list[str]) -> dict:
    return {c: v["extrinsic_cv"] for c, v in S.camera_info(cameras).items()}


def calib(cameras: list[str]) -> dict:
    return {c: {k: v[k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c, v in S.camera_info(cameras).items()}


def frames_ok(cams: list, steps: int, fps: int, meta: dict) -> None:
    """400 (ValueError), before anything is executed, for a call that would hold more than MAX_FRAMES images: `steps`
    control steps recorded at `fps`, the recorder's first and last frames included."""
    deep = L.depth_mode(meta) in ("frames", "legacy")
    try:
        L.check_frames(len(cams) * (DEPTH_FRAME if deep else 1), steps // int(round(CTRL_HZ / max(1, fps))) + 2, limit=MAX_FRAMES)
    except ValueError as exc:
        raise ValueError(f"{exc}" + (f" (here a frame with per-frame depth counts {DEPTH_FRAME} images)" if deep else "")) from None


class Rec(L.Recorder):
    """The call's recorder, keeping the image budget while the call runs: how many control steps an ee_pose row takes
    (4 to 400) is known only then. At the budget it takes no more frames -- the motion goes on, the last frame is always
    taken -- and meta["frames_skipped"] counts the frames left out."""
    skipped = 0

    def _capture(self, last: bool) -> None:
        per = len(self.cams) * (DEPTH_FRAME if self.mode in ("frames", "legacy") else 1)
        if not last and per * (len(self.steps) + 2) > MAX_FRAMES:
            self.skipped += 1
            return
        super()._capture(last)


def recorder(cams: list[str], fps: int, meta: dict) -> L.Recorder:
    return Rec(cams, int(round(CTRL_HZ / max(1, fps))), grab, proprio_row, extrinsics, ctrl_steps, depth=L.depth_mode(meta), clock_hz=CTRL_HZ)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(L.agent_time(E), 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
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
    """One recorded control step. True when the call must stop here: the episode is over (runaway guard), or the call ran
    past max_call_wall_s / its client hung up (EP.journal)."""
    row = np.asarray(a, dtype=np.float32)   # exactly what the simulator gets (Session.step casts to float32): the journal row
    guard = S.step(row); stop = EP.journal(row); rec.tick()
    if guard: finish("step_guard")
    return E["done"] or stop


def run_joint_position(A: np.ndarray, dt: float, interp: str, rec: L.Recorder, clipped: list) -> None:
    steps_per_row = max(1, int(round(dt * CTRL_HZ)))
    q_prev = np.asarray(S.hold_action(), dtype=np.float64)
    for ri, row in enumerate(A):
        E["step"] += 1
        target = clip_joint_row(row.astype(np.float64), clipped, ri)
        for k in range(1, steps_per_row + 1):
            a = target if interp == "hold" else q_prev + (target - q_prev) * (k / steps_per_row)
            if ctrl_step(a, rec): return
        q_prev = target


def run_ee_pose(A: np.ndarray, rec: L.Recorder, plan: list, clipped: list) -> None:
    for ri, row in enumerate(A):
        E["step"] += 1
        cur = np.asarray(S.hold_action(), dtype=np.float64); goal = cur.copy(); st = {"row": ri}
        for arm, off in (("right", 0), ("left", 8)):
            sl, gi = ARM[arm]
            q = row[off + 3:off + 7]; q = q / max(1e-9, float(np.linalg.norm(q)))
            try:
                q7, ep, er = S.ik(arm, row[off:off + 3], q)
                if not (ep <= 0.02 and er <= 0.35 and np.all(np.isfinite(q7))):    # written so that a NaN residual fails too
                    raise ValueError(f"no IK solution within 2 cm / 20 deg (residual {ep * 1000:.0f} mm / {math.degrees(er):.0f} deg)")
                goal[sl] = np.clip(q7, LIM_ARR[sl, 0], LIM_ARR[sl, 1]); st[arm] = "Success"
            except Exception as exc:  # noqa: BLE001
                st[arm] = f"failed: {str(exc)[:90]}"
            w = float(row[off + 7])
            if w < 0.0 or w > GRIP_MAX:  # clipped and reported, as clip_joint_row does (index: the column of the ee_pose row)
                clipped.append({"row": ri, "index": int(off + 7), "reason": f"{arm}_gripper limit [{0.0:.3f},{GRIP_MAX:.3f}]"})
            goal[gi] = float(np.clip(w, 0.0, GRIP_MAX))
        plan.append(st)
        n = int(np.clip(math.ceil(float(np.max(np.abs(goal - cur))) / 0.04), 4, 400))   # at most ~0.04 rad per control step
        for k in range(1, n + 1):
            if ctrl_step(cur + (goal - cur) * (k / n), rec): return


# ---------------------------------------------------------------- request fields (PROTOCOL §4.6: 400, nothing executed)
# Every field is checked for type and range BEFORE anything is executed or counted. The shared layer answers a ValueError
# with 400; any other exception is a 500 that ends the episode, so nothing here may raise anything else on a bad request.
VIDEO_MODES = ("mp4", "frames", "both", "none")
MAX_VIDEO_FPS = CTRL_HZ            # one frame per control step at most
MAX_DT_S = 0.5


def req_dict(meta) -> dict:
    if not isinstance(meta, dict): raise ValueError("the request header / body must be a JSON object")
    return meta


def req_number(meta: dict, key: str, default: float) -> float:
    """A finite JSON number (not null, a string or a boolean); the default when the field is absent."""
    if key not in meta: return float(default)
    v = meta[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f"{key} must be a number, got {v!r:.60}")
    try: f = float(v)
    except OverflowError: f = math.inf
    if not math.isfinite(f): raise ValueError(f"{key} must be a finite number, got {v!r:.60}")
    return f


def req_choice(meta: dict, key: str, default: str, allowed: tuple) -> str:
    v = meta.get(key, default)
    if not isinstance(v, str) or v not in allowed: raise ValueError(f"{key} must be one of {'|'.join(allowed)}, got {v!r:.60}")
    return v


def req_cameras(meta: dict) -> list:
    """`cameras`: absent, null or a list of names. Names that are not cameras are ignored (as before); none left = every camera."""
    v = meta.get("cameras")
    if v is None: return list(CAMS)
    if not isinstance(v, (list, tuple)) or not all(isinstance(c, str) for c in v):
        raise ValueError(f"cameras must be a list of camera names from {CAMS}")
    return list(dict.fromkeys(c for c in v if c in CAMS)) or list(CAMS)


def req_fps(meta: dict) -> int:
    f = req_number(meta, "video_fps", 10)
    if f != int(f) or not (1 <= f <= MAX_VIDEO_FPS): raise ValueError(f"video_fps must be an integer in [1, {MAX_VIDEO_FPS}], got {meta.get('video_fps')!r:.60}")
    return int(f)


def req_note(meta: dict) -> str:
    v = meta.get("note")
    if v is None: return ""
    if not isinstance(v, str): raise ValueError("note must be a string")
    return v[:500]


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    meta = req_dict(meta)
    typ = meta.get("type")
    if not isinstance(typ, str) or typ not in ("joint_position", "ee_pose"):
        raise ValueError(f"type must be one of joint_position, ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dt = req_number(meta, "dt", 1.0 / CTRL_HZ); interp = req_choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = req_cameras(meta); fps = req_fps(meta); video = req_choice(meta, "video", "mp4", VIDEO_MODES); note = req_note(meta)
    dim = SPEC["action_types"][typ]["dim"]
    if not isinstance(A, np.ndarray) or A.ndim != 2 or A.shape[1] != dim: raise ValueError(f"{typ} actions must be (T, {dim}), got {list(np.shape(A))}")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= MAX_DT_S): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, {MAX_DT_S}] s")
    periods = dt * CTRL_HZ
    if typ == "joint_position" and abs(periods - round(periods)) > 1e-6:     # never rounded (PROTOCOL §4.4); ee_pose ignores dt
        k = max(1, int(round(periods)))
        raise ValueError(f"dt must be a whole number of control periods (k/{CTRL_HZ} s, k = 1..{int(MAX_DT_S * CTRL_HZ)}): {dt} s is "
                         f"{periods:.4f} periods; the nearest is {k}/{CTRL_HZ} = {k / CTRL_HZ!r}")
    if typ == "joint_position" and A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if typ == "ee_pose" and A.shape[0] > 50: raise ValueError("ee_pose: at most 50 rows per submit")
    # the least the rows take (a joint row: dt; an ee_pose row: 4 control steps); what ee_pose rows take beyond it, Rec bounds
    frames_ok(cams, A.shape[0] * (int(round(periods)) if typ == "joint_position" else 4), fps, meta)   # (the depth mode is checked here)
    rec = recorder(cams, fps, meta); clipped: list = []; plan: list = []
    # ---- the request is valid: from here on the chunk is executed
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    if typ == "joint_position": run_joint_position(A, dt, interp, rec, clipped)
    else: run_ee_pose(A, rec, plan, clipped)
    succ = False; settled = None
    if not E["done"] and not EP.stopping and check_success():
        succ = settle(lambda a: ctrl_step(a, rec)); settled = E["settle"]
    rec.tick(force=True, last=True)
    E["success"] = E["success"] or succ
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": clipped[:200], "n_clipped": len(clipped), "plan": plan, "rejected": None, "ok": True,
           **({"frames_skipped": rec.skipped} if rec.skipped else {}), **({"settle": settled} if settled else {})}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": note,
         "control_steps": ctrl_steps() - before, "n_clipped": len(clipped), "plan": plan[:50], "success": succ})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    if succ: finish("success")          # settle() recorded the window: the recorded rows end with it
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def do_observe(meta: dict) -> tuple[dict, list]:
    meta = req_dict(meta)
    cams = req_cameras(meta); seconds = req_number(meta, "seconds", 0); fps = req_fps(meta); video = req_choice(meta, "video", "frames", VIDEO_MODES)
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    watch = seconds > 0 and not E["done"]
    frames_ok(cams, int(round(seconds * CTRL_HZ)) if watch else 0, fps, meta)   # (the depth mode is checked here: ValueError)
    rec = recorder(cams, fps, meta); before = ctrl_steps(); settled = None
    # ---- the request is valid
    rec.tick(force=True, last=not watch)
    if watch:
        hold = np.asarray(S.hold_action(), dtype=np.float64)
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(hold, rec): break
        if not E["done"] and not EP.stopping and check_success():
            E["success"] = settle(lambda a: ctrl_step(a, rec)); settled = E["settle"]
        rec.tick(force=True, last=True)
        if E["success"]: finish("success")  # settle() recorded the window (finish drops it if rows came after it)
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True, **({"frames_skipped": rec.skipped} if rec.skipped else {}),
           **({"settle": settled} if settled else {})}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "control_steps": ctrl_steps() - before})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def do_kinematics(req: dict) -> dict:
    """/kinematics (validated by rcb_limited.parse_kinematics): the tooling's stateless FK / IK, never the simulator."""
    return S.kinematics(req)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


AGENT_EXIT_MARGIN_S = 60.0    # more time left than this when the agent phase ended: the agent ended its own session


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (the agent phase is over): end the episode (finish(): the settle window after the agent's
    last command, on the live simulator), then write the verdict (finalize). The reason
    says who ended it: "agent_exit" when the agent ended its session with more than AGENT_EXIT_MARGIN_S left (by the
    service's clock of the agent, meta time_left_s), "timeout" at the time limit (the reason was "timeout" in both cases
    before 2026-10-14)."""
    with LOCK:
        if not E["done"]:
            # the agent's clock (from its first request); an agent that never sent one: the service's own uptime, which
            # starts before the agent's phase and so overstates the agent's time
            used = L.agent_time(E) if E.get("t_first") is not None else time.time() - E["t0"]
            E["agent_time_s"] = round(used, 1)
            finish("agent_exit" if SPEC["budget"]["wall_clock_s"] - used > AGENT_EXIT_MARGIN_S else "timeout")
        else: start_finalize()


# ---------------------------------------------------------------- start, or resume after a crash
S.record_start()                        # before begin(): a resume replay of the journal is recorded too
EP.begin(state=E, step=S.step, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC,
         start_event={"task": TASK, "eval_index": S.eval_index, "backend": BACKEND}, on_end=end_from_signal)
with LOCK:                              # a SIGUSR1 remembered during the resume may already be ending the episode
    write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=S.state_sha, proprio=proprio_row))
