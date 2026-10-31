"""eai-standard/2.2 sim service for TactileLab (Isaac Lab 2.3 / Isaac Sim 5.1, PhysX on the GPU, a Newton sidecar for the
deformable bodies; a dual-arm X-Trainer whose right gripper carries two GelSight Mini sensors; see
docs/protocol/standard_mode.md and tasks/tactilelab/README.md). Owns the scene. HTTP surface (rcb_limited): GET /spec,
GET /status, POST /observe, POST /submit, POST /kinematics (RCB1 bodies and responses). Logs every call to
/data/episode.jsonl and keeps /data/final.json current. Nothing about objects ever leaves this process.

The scene is the privileged tooling's own (rcb_tactilelab.Session on the frozen instance, the same rows, the same step):
- the action is the privileged row (22 numbers: both end-effector targets, both gripper commands, the finger-gap
  overrides, the right finger's drive settings), with sentinels where the privileged row has NaN (the protocol refuses
  NaN): an all-zero quaternion holds that arm, a negative gap is no override, a drive setting <= 0 leaves it unchanged
  (one above its range, rcb_tactilelab.FINGER_DRIVE_RANGE, is a 400; the settings act only in the rigid assembly tasks).
  The service turns them back into NaN, so every executed control step is exactly a privileged row, and it refuses
  (400) the rows the privileged grader refuses (rcb_tactilelab.rows_problem); journal.f64 holds every executed step,
  trajectory.npz the episode's rows up to its final hold, which a privileged replay's settle repeats (the privileged
  CLI replays it: at most max_rows(task) rows);
- rows are `dt` apart (a multiple of the 1/60 s control period, at most 0.5 s) with `linear` (positions linearly,
  orientations by slerp, from the arm's last target or, for a held arm, its measured pose) or `hold` between rows; the
  gripper commands, gaps and drive settings switch at the row;
- cameras: the two wrist cameras (RGB and z-depth, Isaac's renders) and the two GelSight Mini images of the right
  gripper (the Taxim tactile render of each gel pad, RGB only), rendered only when a frame is asked for (rendering never
  steps physics);
- the success rule is the privileged grader's, run on the live simulator: whenever the task's success condition holds
  after a control step, the last command is held for SETTLE_STEPS (60) more control steps (in the call's response: its
  frames, `frame_step`) and the task is judged (is_success: for a latching task the latch, its end-of-episode checks and
  no early failure); if it is solved the episode ends in success (later rows are not executed), else the episode goes
  on and the next control step at which the condition holds, SETTLE_STEPS or more after that hold, starts another.
  The agent's rows stop once the episode has run AGENT_CAP = max_rows(task) - SETTLE_STEPS control steps (holds
  included; reason "step_guard"); then, as when the agent's time is up, the same full hold runs (as the pseudo-call
  "/end": a crash in it is inside the agent's last call, docs/protocol/running.md) and the task is judged once more,
  so an episode runs at most max_control_steps(task) = max_rows(task) + SETTLE_STEPS control steps; a simulator error
  during that hold scores 0 (reason "error"). A task whose own rule has failed for good (its truncation: the bottle
  dropped, the wrist above its ceiling, the cloth state not finite, ...) ends the episode (`failed`); a simulator
  error (an exception in a step, an error the soft-body solver reports) ends it with reason "error" (the agent's 0,
  `sim_error`). A host fault (fault_check): a Newton sidecar process that dies, goes silent or does not start, or a
  GPU or host error raised in a step or reported by the soft-body solver (rcb_tactilelab.HOST_FAULT: CUDA / Warp /
  PhysX / torch errors, out of memory, a lost device, an OS error). The episode's first host fault in a call, a hold
  or the journal replay of a resume is taken as the host's (its one host-fault credit): the call in flight is closed
  as the host's (a `call_end` with `host_fault`, so the crash is never counted as the agent's `crashed_in_call`), the
  service exits non-zero, compose restarts it and the episode resumes from its journal (rcb_limited's resume limits
  apply). A later one is the rows' when the host passes a health check (host_check: the GPU computes and has memory
  free): the episode ends with reason "error" (`sidecar_error` / `gpu_error`, the agent's 0), during a resume by a
  give-up with that reason; when the check fails it is the host's again (another resume; a host that keeps failing
  ends the episode as `sim_crashed`, infrastructure), and so is a fault in a resume at a step the episode had passed
  before (more than SETTLE_STEPS before the checkpoint it resumes to). A fault while the scene is built is always the
  host's;
- the start state is checked before the agent is served: the rebuilt scene's state hash against instance.json's
  `state_sha` (exact; PROTOCOL §4). A scene that does not rebuild to it ends the trial as an infrastructure failure
  (`instance_mismatch`, a give-up: nothing is served);
- crash recovery (rcb_limited.Episode, docs/protocol/standard_mode.md §13): every executed control step is journaled,
  every completed call checkpointed with the state hash; a restarted service rebuilds the frozen scene, replays the
  journal (its first episode in a fresh process: bit-exact with PhysX and Newton's deterministic kernels, resume class
  `exact`; the dough tasks' MPM is not guaranteed bit for bit: `approx`) and continues the SAME episode;
- the video is filmed live (live_video.py): a frame of the third-person video camera (no observation: neither /observe
  nor /spec has it) with both tactile images in its corner every 12 control steps (5 per simulated second); the collect
  hook encodes live.mp4 after the verdict;
- graded by the live episode (no replay): on the collect hook's SIGUSR1 the service ends the episode, writes
  /data/trajectory.npz + /data/episode.json and exits; environment/sim/finalize.sh writes final.json from it."""
from __future__ import annotations
import math, os, re, sys, threading, time, traceback
from typing import Callable
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402
import live_video  # noqa: E402

PROTOCOL = L.PROTOCOL
DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(DATA, exist_ok=True); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
TASK = os.environ.get("RCB_TASK", "lift"); INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(__file__), "instance.json"))
OBS_CALIBRATION = os.environ.get("RCB_OBS_CALIBRATION", "1") == "1"
CTRL_HZ = 60; SUBSTEPS = 2; ACTION_DIM = 22
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10")); MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
# /spec max_frames_per_call (PROTOCOL §3 "Images per call"): a 10 s chunk with its 60-step hold at 30 fps from the four
# cameras with depth (2,656 images) fits; the sim's memory cap covers a response of this many 640x480 frames
MAX_FRAMES_PER_CALL = 3000
LOCK = threading.Lock(); PID_FILE = os.path.join(DATA, "server.pid")
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None,
     "settles": 0, "truncation": None, "target": None, "hold_after": 0, "final_hold_from": None}   # the last five: EP persist keys
import rcb_tactilelab as M  # noqa: E402

RESUME = "approx" if M.replays(TASK) == 1 else "exact"   # the dough's MPM is not guaranteed bit for bit
EP = L.Episode(DATA, dim=ACTION_DIM, resume=RESUME, persist=("settles", "truncation", "target", "hold_after", "final_hold_from"))
EP.startup()             # start count, back-off after failed starts, startup watchdog (RCB_STARTUP_TIMEOUT_S) until scene_built()
log = EP.log
SETTLE = int(M.SETTLE_STEPS); CAP = int(M.max_rows(TASK))
AGENT_CAP = CAP - SETTLE   # the agent's rows stop here (an in-call hold may run to CAP - 1); then the final hold (<= CAP + SETTLE)


def ctrl_steps() -> int:
    return int(S.sim_steps)              # = EP.rows: every step Session.step executes is journaled (a resume replays them)


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
        acts = S.record_stop()
        if E.get("final_hold_from") is not None:   # the final hold is the privileged replay's settle: not rows
            acts = acts[: int(E["final_hold_from"])]
        E["n_actions"] = int(len(acts))
        if len(acts):
            S.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"))
        E["live_sha"] = S.state_sha()
    except Exception as exc:  # noqa
        traceback.print_exc(); log({"ev": "dump_error", "error": repr(exc)})
    n = int(E.get("episode_control_steps") or 0)
    L._write_json(os.path.join(DATA, "episode.json"),
                  {"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS,
                   "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1), "reason": E["reason"], "task": TASK, "protocol": PROTOCOL,
                   "n_actions": E.get("n_actions"), "live_sha": E.get("live_sha"), "settle_steps": E.get("settle_steps"),
                   "settles": int(E.get("settles") or 0), "truncation": E.get("truncation"),
                   **({"sim_error_reason": E["sim_error_reason"]} if E.get("sim_error_reason") else {}),
                   **({f"{E.get('fault_kind') or 'sidecar'}_error": 1} if E.get("fault_error") else {}),
                   **({"settle_error": E["settle_error"]} if E.get("settle_error") else {}), **INSTANCE_CHECK, **EP.final_fields()})
    write_final()
    VIDEO.last(ctrl_steps())  # after the verdict is on disk: a render that fails or hangs here never costs it


def sim_err() -> str | None:
    """The episode's simulator error: the task's (an exception, the soft-body solver's error) or a host fault counted as
    the rows' (fault_check)."""
    return E.get("fault_error") or S.sim_error()


HEALTH_FREE_GIB = 2.0   # host_check: GPU memory that must be free (the sidecar's own memory is released when it dies)


def host_check() -> tuple[bool, dict]:
    """The host's health before a repeated host fault is counted as the rows': the GPU answers (nvidia-smi), computes
    (a 2048 x 2048 matrix product on it, synchronised, finite) and has HEALTH_FREE_GIB of memory free."""
    out: dict = {}
    try:
        import subprocess
        import torch
        q = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader", "-i", "0"],
                           capture_output=True, text=True, timeout=30)
        out["nvidia_smi"] = (q.stdout.strip() or q.stderr.strip())[:200]
        if q.returncode != 0:
            return False, out
        free, _total = torch.cuda.mem_get_info()
        out["gpu_free_gib"] = round(free / 2**30, 2)
        x = torch.randn(2048, 2048, device="cuda")
        v = float((x @ x).abs().mean().item()); torch.cuda.synchronize()
        out["matmul_ok"] = math.isfinite(v)
        del x
        return bool(out["matmul_ok"] and out["gpu_free_gib"] >= HEALTH_FREE_GIB), out
    except Exception as exc:  # noqa: BLE001 -- the GPU does not compute: the host's
        out["error"] = repr(exc)[:300]
        return False, out


def fault_now(exc_text: str | None = None) -> tuple[str, str] | None:
    """(kind, message) of a host fault now: the Newton sidecar's process ("sidecar"), or a GPU / host error raised in the
    step (exc_text) or recorded by the task ("gpu"; rcb_tactilelab.HOST_FAULT); None."""
    why = M.sidecar_failure()
    if why is not None:
        return "sidecar", why
    for t in (exc_text, S.sim_error()):
        if M.host_fault_error(t):
            return "gpu", str(t)
    return None


def _exit_host(where: str, kind: str, why: str) -> None:
    """The host's: close the call in flight as the host's and exit non-zero for a resume (the journal holds the steps)."""
    try:
        if EP._call is not None:   # this crash must not count as the agent's crashed_in_call
            EP.call_end(EP._call["id"], f"{kind}_failure", host_fault=True)
        print(f"[tactilelab] host fault ({kind}, {where}), exiting for a resume: {why[:500]}", file=sys.stderr, flush=True)
    finally:
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(3)


def fault_check(where: str = "call", exc_text: str | None = None) -> None:
    """A host fault (fault_now) at this control step. `where`: "call" or "hold" (the agent's rows or a hold on them),
    "resume" (the journal replay) or "startup" (the scene build: always the host's). The episode's first fault in a call,
    hold or resume is the host's (its one host-fault credit): exit for a resume. A later one is the rows' when
    host_check() passes: E["fault_error"] (the caller ends the episode, reason "error"), during a resume a give-up with
    reason "error"; else the host's again, as is a fault in a resume more than SETTLE control steps before the
    checkpoint it resumes to (the episode passed that step before)."""
    f = fault_now(exc_text)
    if f is None or E.get("fault_error"):
        return
    kind, why = f
    n = ctrl_steps()
    ev = EP.events()
    credit = where != "startup" and not any(e.get("ev") == "host_fault" and e.get("credit") for e in ev)
    if where == "startup" or credit:
        log({"ev": "host_fault", "kind": kind, "where": where, "control_steps": n, "credit": credit, "error": why[:500]})
        _exit_host(where, kind, why)
    cps = [int(e.get("control_steps") or 0) for e in ev if e.get("ev") == "checkpoint"]
    if where == "resume" and n < (cps[-1] if cps else 0) - SETTLE:
        log({"ev": "host_fault", "kind": kind, "where": where, "control_steps": n, "credit": False, "passed_before": True,
             "error": why[:500]})
        _exit_host(where, kind, why)
    healthy, probe = host_check()
    log({"ev": "host_fault", "kind": kind, "where": where, "control_steps": n, "credit": False, "healthy": healthy,
         "probe": probe, "error": why[:500]})
    if not healthy:
        _exit_host(where, kind, why)
    msg = f"a second host fault ({kind}) at control step {n} on a healthy host: the rows' ({why[:300]})"
    print(f"[tactilelab] {msg}", file=sys.stderr, flush=True)
    if where == "resume":    # no call is served yet: the episode ends here (the agent's 0)
        L._write_json(os.path.join(DATA, "final.json"), {**L._read_json(os.path.join(DATA, "final.json")),
                      f"{kind}_error": 1, "sim_error_reason": msg[:300], **INSTANCE_CHECK})
        EP.give_up("error", infra=False)   # never returns
    E["fault_error"] = msg; E["fault_kind"] = kind


def step_live(a: np.ndarray, where: str) -> bool:
    """One journaled control step of the live episode (a row or a hold); a host fault in it goes to fault_check.
    Returns EP.journal's stop flag."""
    try:
        S.step(a)
    except Exception as exc:
        fault_check(where, f"{type(exc).__name__}: {exc}")   # the host's: exits; the rows': E["fault_error"]
        raise                                                # and the exception ends the episode
    stop = EP.journal(a)
    fault_check(where)
    return stop


def judged() -> bool:
    """The task's success condition as the privileged grader judges it (the latch and the task's final checks), and no
    simulator error."""
    return bool(S.task.is_success()) and sim_err() is None


def hold_steps(n: int, rec: L.Recorder | None = None) -> int:
    """Hold the last command for n control steps on the live simulator (journaled, recorded, filmed; in the response
    of the call it ends, with `rec`), as the privileged replay's settle does after a trajectory's last row. Returns the
    steps executed (fewer only on a simulator error)."""
    hold = np.asarray(S.hold_action(), dtype=np.float64); k = 0
    while k < n:
        step_live(hold, "hold"); k += 1
        if rec is not None: rec.tick()
        VIDEO.offer(ctrl_steps())
        if sim_err() is not None: break
    return k


def finish(reason: str) -> None:
    if E["done"]: return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    if reason in ("timeout", "step_guard") and not E["success"] and ctrl_steps() and sim_err() is None:
        # the agent's phase is over: the last command is held for SETTLE control steps on the live simulator (journaled;
        # the privileged replay's settle, so trajectory.npz ends before it), then the task is judged, as the privileged
        # grader's replay does after a trajectory's last row; the live verdict includes this hold. It runs as the
        # pseudo-call "/end" when no call is open (the collect hook's end): a crash in it is inside the agent's last call
        E["final_hold_from"] = ctrl_steps()
        cid = EP.call_begin("/end") if EP._call is None else None
        try:
            E["settle_steps"] = hold_steps(SETTLE)
        except Exception as exc:  # noqa: BLE001 -- a simulator error during the hold: the agent's 0 (PROTOCOL §4)
            traceback.print_exc(); E["settle_error"] = repr(exc)[:300]; log({"ev": "settle_error", "error": E["settle_error"]})
        finally:
            if cid is not None:
                EP.call_end(cid, "/end")
    E["episode_control_steps"] = ctrl_steps()
    if sim_err() is not None or E.get("settle_error"):
        E["sim_error_reason"] = str(sim_err() or E.get("settle_error"))[:300]
        if reason != "error":
            E["reason"] = "error"        # a simulator error in the episode is the agent's 0 (PROTOCOL §4)
        E["success"] = False
    elif not E["success"] and reason not in ("error", "failed"):
        try: E["success"] = judged()
        except Exception: pass
    log({"ev": "end", "reason": E["reason"], "step": E["step"], "control_steps": ctrl_steps(), "elapsed_s": round(E["t_end"] - E["t0"], 1),
         "success": bool(E["success"])})
    dump()


# ---------------------------------------------------------------- scene
S = M.Session(TASK, instance=INSTANCE, cameras=True, tactile=True, video_camera=True)
# the agent's rows stop at AGENT_CAP (step_once); a hold started before it ends by CAP, and the final hold runs in full by
# CAP + SETTLE = the Session's own runaway guard (max_control_steps)
assert S.max_steps == CAP + SETTLE
# the tooling renders the cameras and reads the tactile sensors in every step's observation when its cameras are on; this
# service renders only when a frame is asked for (rendering and the tactile raycast never step physics)
S.task.get_observation = lambda: {"policy": {}, "privileged": {}}
TACTILE_READ = S.task.sensors.get("tactile")   # the task's tactile provider (the right gripper's two gel pads), read on demand
INSTANCE_CHECK = {"instance_sha": S.reset_sha, "instance_expected_sha": L._read_json(INSTANCE).get("state_sha"),
                  "instance_exact": bool(S.instance_exact), "instance_matches": bool(S.instance_matches), "instance_host": M.host_gpu()}
if not S.instance_matches:
    L._write_json(os.path.join(DATA, "final.json"), {"task": TASK, "protocol": PROTOCOL, "instance_mismatch": True, **INSTANCE_CHECK})
    EP.give_up(f"instance_mismatch: the rebuilt scene (state {S.reset_sha}) is not the frozen instance "
               f"({INSTANCE_CHECK['instance_expected_sha']})", infra=True)   # never returns
SC = S.task.scene; ROB = SC.robot
from tactilelab_tasks.core import math as tm  # noqa: E402
from tactilelab_tasks.core.types import JOINT_NAMES, EE_LINKS, GEL_BODIES, GRIPPER_WIDTH_OFFSET  # noqa: E402
from tactilelab_tasks.backends.robot import ARM_GAINS, FINGER_GAINS, JOINT_LIMITS, ARM_VEL_LIMIT  # noqa: E402
from tactilelab_tasks.backends.isaaclab_scene import WRIST_CAM_RIGHT_POS, WRIST_CAM_RIGHT_ORI_DEG, left_wrist_mount  # noqa: E402
from tactilelab_tasks.backends.isaaclab_scene import WRIST_CAM_HFOV_DEG, WRIST_CAM_HFOV_RANGE_DEG, wrist_hfov  # noqa: E402

WRIST = {"wrist_right": "J1_6", "wrist_left": "J2_6"}
TACT = {"tactile_right": "gsmini_right", "tactile_left": "gsmini_left"}   # the two gel pads of the RIGHT gripper
TCP_OFFSET = 0.1777                       # the gel-pad centre along the wrist's +z axis (m)
EFFORT = {j: ARM_GAINS[j.split("_")[1]][2] if int(j.split("_")[1]) <= 6 else FINGER_GAINS[2] for j in JOINT_NAMES}
VEL_LIMIT = dict(zip(JOINT_NAMES, (round(float(v), 6) for v in
                                   ROB.articulation.root_physx_view.get_dof_max_velocities()[0, ROB._joint_ids].tolist())))
GAINS = {j: (ARM_GAINS[j.split("_")[1]][:2] if int(j.split("_")[1]) <= 6 else FINGER_GAINS[:2]) for j in JOINT_NAMES}


def _T(pose7) -> np.ndarray:
    p = np.asarray(pose7, dtype=np.float64).reshape(7); T = np.eye(4)
    T[:3, :3] = tm.quat_to_matrix(p[3:7]); T[:3, 3] = p[:3]; return T


def _pose(T) -> list:
    return [float(v) for v in tm.pose_from_matrix(np.asarray(T, dtype=np.float64))]


# ---------------------------------------------------------------- kinematic model (/kinematics, camera mounts, tcp frames)
import pinocchio as pin  # noqa: E402
from tactilelab_tasks.backends.ik_pink import DEFAULT_URDF  # noqa: E402
_full = pin.buildModelFromUrdf(DEFAULT_URDF)
_lock = [_full.getJointId(n) for n in list(_full.names)[1:] if n not in JOINT_NAMES]
KM = pin.buildReducedModel(_full, _lock, pin.neutral(_full)); KD = KM.createData()
_KNAMES = list(KM.names)[1:]
_TO_MODEL = np.array([JOINT_NAMES.index(n) for n in _KNAMES])     # model joint i = JOINT_NAMES[_TO_MODEL[i]]
BASE_T = _T(ROB.base_pose())              # the robot's base_link in the env frame (fixed; = M.ROBOT_BASE, the Session checks it)
LINK_NAMES = ["base_link"] + [f"J{a}_{j}" for a in (1, 2) for j in range(1, 9)]


def _q_model(q16) -> np.ndarray:
    q = np.asarray(q16, dtype=np.float64).reshape(16)
    return q[_TO_MODEL]


def _fk_links(q16) -> dict:
    """{link: 4x4 env-frame transform} for the URDF links and the frames defined on them (FRAMES)."""
    pin.forwardKinematics(KM, KD, _q_model(q16)); pin.updateFramePlacements(KM, KD)
    out = {}
    for n in LINK_NAMES:
        out[n] = BASE_T @ KD.oMf[KM.getFrameId(n)].homogeneous
    for n, (parent, off) in FRAMES.items():
        out[n] = out[parent] @ off
    return out


def _gel_parents() -> dict:
    """The finger link each gel pad body is fixed to, from the robot's USD joints (else the nearest finger link)."""
    out = {}
    try:
        from pxr import UsdPhysics
        from isaaclab.sim.utils.stage import get_current_stage
        for prim in get_current_stage().Traverse():
            if not prim.IsA(UsdPhysics.Joint):
                continue
            j = UsdPhysics.Joint(prim)
            b0 = [str(x) for x in j.GetBody0Rel().GetTargets()]; b1 = [str(x) for x in j.GetBody1Rel().GetTargets()]
            if not (b0 and b1):
                continue
            for g in GEL_BODIES:
                for a, b in ((b0[0], b1[0]), (b1[0], b0[0])):
                    if a.endswith("/" + g) and b.rsplit("/", 1)[-1] in LINK_NAMES:
                        out[g] = b.rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return out


FRAMES: dict = {"tcp_right": ("J1_6", np.eye(4)), "tcp_left": ("J2_6", np.eye(4))}
FRAMES["tcp_right"][1][2, 3] = TCP_OFFSET; FRAMES["tcp_left"][1][2, 3] = TCP_OFFSET
_q0 = ROB.joint_pos()
_links0 = _fk_links(_q0)
_par = _gel_parents()
for _g in GEL_BODIES:
    _p = _par.get(_g) or min(("J1_7", "J1_8"), key=lambda l: float(np.linalg.norm(_links0[l][:3, 3] - _T(ROB.body_pose(_g))[:3, 3])))
    FRAMES[_g] = (_p, np.linalg.inv(_links0[_p]) @ _T(ROB.body_pose(_g)))   # fixed: the pad is rigid on its finger
# the model against the simulator at the start state: the wrists and the pads (a log line, never a decision)
_links0 = _fk_links(_q0)
KIN_CHECK = {n: round(float(np.linalg.norm(_links0[n][:3, 3] - np.asarray(ROB.body_pose(n))[:3])), 6) for n in list(EE_LINKS) + list(GEL_BODIES)}


def _mount_wrist(name: str) -> np.ndarray:
    """link_T_cam_cv of a wrist camera: its USD offset (OpenGL axes) turned into OpenCV axes."""
    if name == "wrist_right":
        pos, q = WRIST_CAM_RIGHT_POS, tm.quat_from_euler_xyz_deg(WRIST_CAM_RIGHT_ORI_DEG)
    else:
        pos, q = left_wrist_mount()
    T = np.eye(4); T[:3, :3] = tm.quat_to_matrix(np.asarray(q, dtype=np.float64)) @ np.diag([1.0, -1.0, -1.0]); T[:3, 3] = pos
    return T


MOUNT_T = {**{c: _mount_wrist(c) for c in WRIST}, **{c: np.eye(4) for c in TACT}}
PARENT = {**WRIST, **TACT}


def cam_world_T(cam: str, links: dict | None = None) -> np.ndarray:
    """world_T_cam (OpenCV axes) of a camera now: its parent link's measured pose x its fixed mount."""
    cam = lens_of(cam)[0]
    link = PARENT[cam]
    T_link = _T(ROB.body_pose(link)) if link in EE_LINKS or link in GEL_BODIES else (links or _fk_links(ROB.joint_pos()))[link]
    return T_link @ MOUNT_T[cam]


# ---------------------------------------------------------------- cameras
# A wrist camera with another horizontal field of view for one call: "<wrist camera>@<hfov_deg>" in `cameras` (e.g.
# "wrist_right@90"; WRIST_CAM_HFOV_RANGE_DEG): rendered by the wrist camera's lens camera (same mount, aperture and
# resolution, that focal length; IsaacLabScene.render_cameras), so the wrist camera itself never changes; its frames,
# depth, extrinsics and calibration come back under that name.
LENS = re.compile(r"(wrist_right|wrist_left)@(\d+(?:\.\d+)?)", re.ASCII)


def lens_of(c: str) -> tuple:
    """A requested camera name -> (camera, hfov_deg or None for its own lens); a malformed field of view is a ValueError."""
    if "@" not in c:
        return c, None
    m = LENS.fullmatch(c)
    if m is None:
        raise ValueError(f"camera {c!r}: a field of view is '<wrist camera>@<hfov_deg>' (e.g. 'wrist_right@90'), for "
                         f"{' and '.join(WRIST)} only")
    return m.group(1), wrist_hfov(float(m.group(2)))


def render(depth: bool = False, lenses=(), wrists: bool = True) -> dict:
    """{camera: uint8 (H, W, 3)} (+ {"<wrist cam>_depth": float32 (H, W) m}) of every camera, rendered now (the wrist
    cameras' default lens only with `wrists`); `lenses`: requested names "<wrist camera>@<hfov_deg>" (at most one per
    wrist camera: cameras()), rendered by the lens cameras (both wrist cameras in the same render) and returned under
    those names."""
    out = {}
    try:
        r = SC.render_cameras(depth=depth) if wrists else {}
        for c in WRIST:
            if f"{c}_rgb" in r: out[c] = r[f"{c}_rgb"]
            if f"{c}_depth" in r: out[f"{c}_depth"] = r[f"{c}_depth"]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    names = {lens_of(n)[0]: n for n in lenses}
    if names:
        try:
            r = SC.render_cameras(depth=depth, hfov_deg={c: lens_of(n)[1] for c, n in names.items()})
            for c, n in names.items():
                if f"{c}_rgb" in r: out[n] = r[f"{c}_rgb"]
                if f"{c}_depth" in r: out[f"{n}_depth"] = r[f"{c}_depth"]
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    try:
        t = TACTILE_READ() if TACTILE_READ is not None else {}
        for c in TACT:
            k = f"{c}_rgb"
            if k in t: out[c] = np.ascontiguousarray(np.asarray(t[k])[..., :3].astype(np.uint8))
        out["_tactile"] = t
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return out


FIRST = render(depth=True)
CAMS = [c for c in ("wrist_right", "wrist_left", "tactile_right", "tactile_left") if c in FIRST]
WINFO = SC.camera_info()
K0 = {c: np.asarray(WINFO[c]["intrinsic_cv"], dtype=np.float64) for c in WRIST if c in WINFO}


KLENS: dict = {}


def intrinsic_cv(c: str):
    """The intrinsic matrix of a requested camera's images (its own lens: K0; "<wrist camera>@<hfov_deg>": that render's)."""
    cam, h = lens_of(c)
    if h is None:
        return K0[cam].tolist() if cam in K0 else None
    if (cam, h) not in KLENS:
        KLENS[(cam, h)] = SC.wrist_intrinsics(cam, h).tolist()
    return KLENS[(cam, h)]


def camera_info(cams) -> dict:
    links = _fk_links(ROB.joint_pos())
    out = {}
    for c in cams:
        Tw = cam_world_T(c, links); ext = np.linalg.inv(Tw)[:3, :]
        img = FIRST.get(lens_of(c)[0])
        out[c] = {"intrinsic_cv": intrinsic_cv(c), "extrinsic_cv": ext.tolist(),
                  "cam2world_gl": (Tw @ np.diag([1.0, -1.0, -1.0, 1.0])).tolist(),
                  "image_size": [int(img.shape[1]), int(img.shape[0])] if img is not None else None}
    return out


def _tactile_frames() -> list:
    try:
        t = TACTILE_READ() if TACTILE_READ is not None else {}
    except Exception:  # noqa: BLE001
        traceback.print_exc(); return []
    return [np.ascontiguousarray(np.asarray(t[f"{c}_rgb"])[..., :3].astype(np.uint8)) for c in TACT if f"{c}_rgb" in t]


def video_frame():
    """The live video's frame: the third-person video camera (no observation of the agent's), the two tactile images
    side by side in its top-right corner; without that camera, both wrist cameras with the tactile images below them."""
    try:
        img = SC.render_video()
    except Exception:  # noqa: BLE001
        traceback.print_exc(); img = None
    if img is not None:
        img = img.copy(); tiles = _tactile_frames()
        if tiles:
            th, m = img.shape[0] // 5, 8                          # 144 rows at 720; the tile's own aspect (4:3)
            tw = int(round(th * tiles[0].shape[1] / tiles[0].shape[0]))
            for k, t in enumerate(tiles):
                ys = (np.arange(th) * t.shape[0] // th); xs = (np.arange(tw) * t.shape[1] // tw)
                small = t[ys][:, xs]
                x0 = img.shape[1] - m - (len(tiles) - k) * (tw + m); y0 = m
                img[y0 - 2:y0 + th + 2, x0 - 2:x0 + tw + 2] = 255
                img[y0:y0 + th, x0:x0 + tw] = small
        return img
    f = render()
    if "wrist_right" not in f or "wrist_left" not in f:
        return None
    top = np.concatenate([f["wrist_right"], f["wrist_left"]], axis=1)
    tiles = [f[c] for c in ("tactile_right", "tactile_left") if c in f]
    if not tiles:
        return top
    h = max(t.shape[0] for t in tiles)
    row = np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 0), (0, 0))) for t in tiles], axis=1)
    pad = top.shape[1] - row.shape[1]
    if pad >= 0:
        row = np.pad(row, ((0, 0), (pad // 2, pad - pad // 2), (0, 0)))
    else:
        row = row[:, :top.shape[1]]
    return np.concatenate([top, row], axis=0)


VIDEO = live_video.LiveVideo(DATA, ctrl_hz=CTRL_HZ, frame=video_frame, log=EP.log)

# ---------------------------------------------------------------- proprio
PROPRIO_LAYOUT = (list(JOINT_NAMES) + [f"{j}_vel" for j in JOINT_NAMES] + [f"{j}_effort" for j in JOINT_NAMES]
                  + [f"tcp_right_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"tcp_left_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"ee_right_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + [f"ee_left_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
                  + ["gripper_opening_right", "gripper_opening_left", "gripper_cmd_right", "gripper_cmd_left",
                     "tactile_right_press_mm", "tactile_left_press_mm", "tactile_right_contact_frac", "tactile_left_contact_frac"])


def proprio_row(tact: dict | None = None) -> np.ndarray:
    q = ROB.joint_pos(); qd = ROB.joint_vel(); qt = ROB.joint_pos_target()
    eff = []
    vel_f, eff_f, kp_f, kd_f = S.finger_drive    # the right fingers' drive in force (stock where columns 18-21 change nothing)
    for i, j in enumerate(JOINT_NAMES):
        if j.startswith(("J1_7", "J1_8")):
            k, d, lim = kp_f, kd_f, eff_f
        else:
            (k, d), lim = GAINS[j], EFFORT[j]
        eff.append(float(np.clip(k * (qt[i] - q[i]) - d * qd[i], -lim, lim)))
    ee = [np.asarray(ROB.ee_pose(a), dtype=np.float64) for a in (0, 1)]
    tcp = [_pose(_T(ee[a]) @ FRAMES[("tcp_right", "tcp_left")[a]][1]) for a in (0, 1)]
    if tact is None:
        try:
            tact = TACTILE_READ() if TACTILE_READ is not None else {}
        except Exception:  # noqa: BLE001
            tact = {}
    tp = [float(np.asarray(tact.get(f"tactile_{s}_press_mm", 0.0))) for s in ("right", "left")]
    tc = [float(np.mean(np.asarray(tact[f"tactile_{s}_contact"]))) if f"tactile_{s}_contact" in tact else 0.0 for s in ("right", "left")]
    cmd = [float(v) for v in getattr(ROB, "_gripper_cmd", np.zeros(2))]
    return np.array(list(q) + list(qd) + eff + tcp[0] + tcp[1] + list(ee[0]) + list(ee[1])
                    + [ROB.gripper_width(0), ROB.gripper_width(1)] + cmd + tp + tc, dtype=np.float32)


def _g(name: str) -> int:
    return PROPRIO_LAYOUT.index(name)


# ---------------------------------------------------------------- spec
FINGER_DRIVE_SPEC = {
    "columns": [18, 19, 20, 21], "names": ["velocity_limit_m_s", "effort_limit_n", "stiffness_n_per_m", "damping_n_s_per_m"],
    "stock": list(M.FINGER_DRIVE_STOCK), "range": [list(r) for r in M.FINGER_DRIVE_RANGE], "range_rule": "(lo, hi]",
    "applies": bool(S.finger_drive_applies),
    "rule": ("the right gripper's two finger joints: a value in (lo, hi] sets that setting from its row on, until changed; "
             "<= 0 leaves it unchanged; above hi is a 400 (0.2 m/s and 20 N, the stock values, are the drive's maxima; a "
             "stiffness of 10,000 saturates the drive at its effort limit, a constant-force jaw). Send the stock values to "
             "restore the stock drive. " + ("In this task the settings act on the fingers." if S.finger_drive_applies else
                                            "In this task they change nothing (checked and recorded only)."))}
ROW_LAYOUT = ([f"right_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")] + [f"left_{k}" for k in ("x", "y", "z", "qw", "qx", "qy", "qz")]
              + ["right_gripper", "left_gripper", "right_gap_m", "left_gap_m", "right_finger_velocity_limit",
                 "right_finger_effort_limit", "right_finger_drive_kp", "right_finger_drive_kd"])


def robot_spec() -> dict:
    joints = []
    for j in JOINT_NAMES:
        arm = int(j[1]); idx = int(j.split("_")[1])
        finger = idx >= 7
        joints.append({"name": j, "type": "prismatic" if finger else "revolute", "unit": "m" if finger else "rad",
                       "position_limits": [float(v) for v in JOINT_LIMITS[j]], "velocity_limit": VEL_LIMIT[j],
                       "effort_limit": float(EFFORT[j]), "group": f"{'right' if arm == 1 else 'left'}_{'gripper' if finger else 'arm'}",
                       **({} if finger else {"rated_velocity": float(ARM_VEL_LIMIT), "rated_source": "the robot's URDF"})})
    gr = lambda a: {"joints": [f"J{a}_7_joint", f"J{a}_8_joint"], "opening_m": [0.0, 0.10],   # noqa: E731
                    "command": {"entries": [("right_gripper" if a == 1 else "left_gripper"), ("right_gap_m" if a == 1 else "left_gap_m")],
                                "range": [0, 1], "rule": "0 = open, 1 = closed (binary, switched at the row); a gap >= 0 m overrides it "
                                                          "with that opening between the fingers (width = 0.082 + q7 - q8)"},
                    "tcp_frame": "tcp_right" if a == 1 else "tcp_left",
                    **({"sensors": "two GelSight Mini tactile sensors, one per finger (cameras tactile_right, tactile_left)"} if a == 1 else {})}
    return {
        "name": "X-Trainer (dual-arm, 6-DoF arms with parallel grippers; the right gripper's fingers are GelSight Mini sensors)",
        "description": "two 6-DoF arms on one fixed base (right J1_*, left J2_*), each with a two-finger prismatic gripper; the "
                       "end-effector frames are the wrist links J1_6 / J2_6; the right gripper carries two GelSight Mini tactile pads",
        "base": {"type": "fixed", "pose": _pose(BASE_T)},
        "joints": joints,
        "grippers": {"right": gr(1), "left": gr(2)},
        "controller": {"type": "joint PD drives (implicit) tracking a differential IK (Pink, Pinocchio) of the end-effector targets, "
                               "one IK solve per physics substep", "control_hz": CTRL_HZ, "physics_hz": CTRL_HZ * SUBSTEPS,
                       "gains": {j: {"stiffness": float(GAINS[j][0]), "damping": float(GAINS[j][1])} for j in JOINT_NAMES},
                       "finger_drive": FINGER_DRIVE_SPEC},
        "tcp": {"tcp_right": {"parent_link": "J1_6", "link_T_frame": FRAMES["tcp_right"][1].tolist(),
                              "definition": "the centre between the right gripper's gel pads: the wrist link J1_6 moved 0.1777 m along its +z axis"},
                "tcp_left": {"parent_link": "J2_6", "link_T_frame": FRAMES["tcp_left"][1].tolist(),
                             "definition": "the left gripper's fingertip centre: the wrist link J2_6 moved 0.1777 m along its +z axis"},
                "J1_6": {"parent_link": "J1_6", "link_T_frame": np.eye(4).tolist(), "definition": "the right ee_pose frame (the wrist link)"},
                "J2_6": {"parent_link": "J2_6", "link_T_frame": np.eye(4).tolist(), "definition": "the left ee_pose frame (the wrist link)"}},
    }


def kinematics_spec() -> dict:
    return {"endpoint": "/kinematics", "joint_names": list(JOINT_NAMES), "frame": "world", "quaternion_order": "wxyz",
            "links": LINK_NAMES + list(FRAMES), "tcp_frames": ["tcp_right", "tcp_left"], "ee_frames": ["J1_6", "J2_6"],
            "ik_targets": ["J1_6", "J2_6", "tcp_right", "tcp_left"],
            "ik": {"solver": "damped least squares on the robot's URDF model (Pinocchio), the 12 arm joints; the fingers keep the seed's values",
                   "seed_default": "the robot's start configuration", "tol_pos_m": 0.002, "tol_rot_rad": 0.02, "max_iters": 300},
            "note": "the same URDF model as the ee_pose controller's IK; the gel pad frames gsmini_right / gsmini_left ride on the right "
                    "fingers (the tactile cameras' parent links)"}


MOUNT_DESC = {"wrist_right": "on the right wrist (link J1_6), looking along the gripper", "wrist_left": "on the left wrist (link J2_6)",
              "tactile_right": "a GelSight Mini on the right gripper's finger (gel pad gsmini_right): the image of its gel",
              "tactile_left": "a GelSight Mini on the right gripper's other finger (gel pad gsmini_left): the image of its gel"}


def _cam_spec(c: str) -> dict:
    img = FIRST[c]
    tact = c in TACT
    lo, hi = WRIST_CAM_HFOV_RANGE_DEG
    fov = None if tact else {
        "hfov_deg": round(WRIST_CAM_HFOV_DEG, 4), "vfov_deg": round(float(np.degrees(2 * np.arctan(img.shape[0] / 2 / K0[c][1, 1]))), 4),
        "hfov_deg_range": [lo, round(hi, 4)],
        "request": (f"'{c}@<hfov_deg>' in a call's cameras (e.g. '{c}@90') renders this camera with that horizontal field of view, "
                    f"{lo:g} up to {hi:.4f} degrees (the default, the widest), in that call (one field of view per camera and call): same mount and resolution, square pixels, "
                    f"principal point at the centre, fx = fy = {img.shape[1] / 2:g} / tan(hfov / 2); its frames, depth and "
                    "extrinsic_cv, and with calibration_in_obs its intrinsic_cv in the response's meta cameras, come back under "
                    "that name; rendered by a second camera at the same mount (this camera itself never changes); a field of view other "
                    "than the last one asked for (or the first one) costs a few more renders, and once asked for that second camera is "
                    "rendered with every later render too (slightly slower renders); without it, the default lens")}
    return {"rgb": True, "depth": not tact, "mounted": MOUNT_DESC[c], "resolution": [int(img.shape[1]), int(img.shape[0])],
            "calibration_in_obs": OBS_CALIBRATION, "intrinsic_cv": None if tact else K0[c].tolist(),
            **({"field_of_view": fov} if fov else {}),
            "mount": {"type": "link", "parent_link": PARENT[c], "link_T_cam_cv": MOUNT_T[c].tolist()},
            **({"depth_range_m": [0.01, 100.0]} if not tact else
               {"kind": "tactile image (Taxim render of the gel's deformation against what it touches, 60 x 80 taxels); not a pinhole "
                        "camera: intrinsic_cv is null and its pose is the gel pad's frame; depth requests return 0 for it"})}


SPEC = {
    "protocol": PROTOCOL, "protocol_compat": list(L.COMPAT), "simulator": "tactilelab (Isaac Lab 2.3 / Isaac Sim 5.1, PhysX on the GPU; "
    "Newton for deformable bodies)", "robot": "xtrainer-gsmini",
    "task_text": __import__("tactilelab_tasks").TASKS[TASK].description or TASK, "control_hz": CTRL_HZ, "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S, "max_watch_s": MAX_WATCH_S, "max_frames_per_call": MAX_FRAMES_PER_CALL,
    "cameras": {c: _cam_spec(c) for c in CAMS},
    "default_cameras": [c for c in ("wrist_right", "tactile_right", "tactile_left") if c in CAMS],
    "action_types": {
        "ee_pose": {"dim": ACTION_DIM, "layout": ROW_LAYOUT,
                    "frame": "the env frame (metres, z up; the robot base at (-0.5, 0, 1.1) facing +x)", "quaternion": "wxyz",
                    "units": "m and unit quaternions for the targets; 0/1 gripper commands; m for gaps; m/s, N and the drive's own units "
                             "for the right finger drive settings",
                    "semantics": "per row: the right and the left end-effector (wrist link J1_6 / J2_6) targets, tracked by a differential IK "
                                 "(one solve per physics substep) and the joint PD drives; rows `dt` apart (a multiple of 1/60 s, at most 0.5 s; "
                                 "anything else is rejected, never rounded) with `linear` interpolation (positions linearly, orientations by "
                                 "slerp, from the arm's last target or, for a held arm, its measured pose) or `hold`; a far target is not reached "
                                 "in one step. Gripper commands, gaps and drive settings switch at the row (drive settings stay in force until "
                                 "changed). Sentinels: an all-zero quaternion holds that arm where it is (its three position numbers are then "
                                 "ignored); a gap < 0 means no override (use the open / closed command); a drive setting <= 0 leaves it unchanged "
                                 "(robot_spec.controller.finger_drive: ranges, stock values, whether they act in this task)",
                    "limits": {"position_box_m": M.BOX_M, "position_box_center": list(M.ROBOT_BASE),
                               "position_box_rule": f"each finite target's x, y and z within +-{M.BOX_M:g} m of position_box_center, "
                                                    "the robot base (env frame, metres); else a 400",
                               "gripper": [0, 1],
                               "finger_drive_max": [float(r[1]) for r in M.FINGER_DRIVE_RANGE]}},
        "not_yet": ["joint_position", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"]},
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": {
        "joint_pos": [0, 16, "measured joint positions: J1_1..J1_6 (right arm, rad), J2_1..J2_6 (left arm, rad), J1_7, J1_8, J2_7, J2_8 (fingers, m)"],
        "joint_vel": [16, 16, "measured joint velocities, the joints of joint_pos"],
        "joint_effort": [32, 16, "drive-effort estimate of each joint: stiffness * (target - q) - damping * qdot of its PD drive, clipped to its "
                                 "effort limit (N m for the arms, N for the fingers): a motor-current analogue"],
        "tcp_pose": [_g("tcp_right_x"), 14, "measured fingertip-centre poses, right then left: x y z (m) + quaternion wxyz, env frame"],
        "ee_pose": [_g("ee_right_x"), 14, "measured ee_pose frames (wrist links J1_6, J2_6), right then left, env frame"],
        "gripper_opening": [_g("gripper_opening_right"), 2, "measured opening between the fingers (m), right then left: 0.082 + q7 - q8"],
        "gripper_cmd": [_g("gripper_cmd_right"), 2, "the gripper commands in force (0 open, 1 closed)"],
        "tactile": [_g("tactile_right_press_mm"), 4, "the right gripper's GelSight pads: press depth of the gel (mm, right and left pad), "
                                                     "then the fraction of each gel's taxels in contact; the sensor's own reading, "
                                                     "computed from the same contact as the tactile images"]},
    "static": {"table": "a table in front of the robot", "robot": "the X-Trainer on a fixed base behind the table"},
    "world": {"frame": "the env frame: metres, z up, x away from the robot (its base at (-0.5, 0, 1.1) facing +x), y to the robot's left",
              "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz",
              "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))},
    # no step budget, a technical episode cap stated here (rcb_tactilelab.max_control_steps: the privileged twin's row cap and
    # the replay's settle): the agent's rows stop at AGENT_CAP (reason "step_guard"), then the final hold and the judgement
    "max_control_steps": int(M.max_control_steps(TASK)),
    "episode": (f"one episode, no reset: whenever the task's success condition holds after a control step, the last command is held for "
                f"{SETTLE} more control steps (1 s, in that call's response) and the task judged: solved ends the episode in success "
                f"(later rows are not executed), else the episode goes on and the next hold starts no earlier than {SETTLE} control "
                "steps after this one" + (" (this task's condition latches once reached: the "
                "judgement fails only if the task has failed for good or an end-of-episode check of the instruction fails)"
                if getattr(S.task, "latch", True) else " (this task's condition must still hold after the hold)") +
                f". It also ends when your time is up (the last command is then held for {SETTLE} control steps and the task judged), "
                f"when the task fails for good (\"failed\": the task's stated early-failure conditions), on a simulator error, or once "
                f"the episode has run {AGENT_CAP:,} control steps, holds included ({AGENT_CAP / CTRL_HZ:.0f} s of simulated time: the "
                f"task's technical cap, reason \"step_guard\"; a hold already running finishes first; then held and judged as at the "
                f"time limit); spec.max_control_steps = {CAP + SETTLE:,} is the most an episode runs, its final hold included"),
    "robot_spec": robot_spec(),
    "kinematics": kinematics_spec(),
    "depth": {"modes": list(L.DEPTH_MODES), "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": L.DEPTH_MAX_M,
              "frames_encoding": "uint16 mm, zlib", "noise": L.DEPTH_NOISE, "cameras": list(WRIST)},
}
L.check_spec(SPEC)       # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()         # the watchdog stands down: a long resume replay below is not a hung build


# ---------------------------------------------------------------- per call
def grab(cams, want_depth: bool):
    f = render(depth=want_depth, lenses=[c for c in cams if "@" in c], wrists=any(c in WRIST for c in cams))
    rgb = {c: f.get(c) for c in cams}
    dep = {c: f[f"{c}_depth"] for c in cams if f"{c}_depth" in f} if want_depth else {}
    return rgb, dep


def extrinsics(cams) -> dict:
    links = _fk_links(ROB.joint_pos())
    return {c: np.linalg.inv(cam_world_T(c, links))[:3, :] for c in cams}   # a camera's lens never moves it


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 5
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


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
        return list(SPEC["default_cameras"])
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(c, str) for c in v):
        raise ValueError(f"cameras must be a list of camera names ({', '.join(CAMS)})")
    # "<wrist camera>@<hfov_deg>": that camera with that horizontal field of view (spec cameras.<cam>.field_of_view),
    # one per wrist camera and call
    lens = [lens_of(c)[0] for c in dict.fromkeys(v) if "@" in c]
    if len(lens) != len(set(lens)):
        raise ValueError("cameras: one field of view per wrist camera per call ('<wrist camera>@<hfov_deg>')")
    return [c for c in v if (lens_of(c)[0] if "@" in c else c) in CAMS] or list(SPEC["default_cameras"])


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
                      depth=L.depth_mode(meta), clock_hz=CTRL_HZ, max_images=MAX_FRAMES_PER_CALL)


def frames_of(cams, n_steps: int, fps: int, depth: str) -> int:
    """400 (ValueError) before anything moves for a call of n_steps control steps (its rows or watch and the 60-step hold)
    that would capture more than max_frames_per_call images at the Recorder's stride. A call that runs longer than that
    (a second hold after a success that did not last) stops filming at the budget instead (Recorder max_images,
    meta["frames_skipped"])."""
    every = max(1, int(round(CTRL_HZ / max(1, fps))))
    return L.check_frames(len(dict.fromkeys(cams)), L.frames_per_call(n_steps, every), depth in ("frames", "legacy"),
                          MAX_FRAMES_PER_CALL)


def meta_common(cams) -> dict:
    n = ctrl_steps()
    return {"step": E["step"], "calls": E["calls"], "control_steps": n, "physics_steps": n * SUBSTEPS, "sim_time_s": round(n / CTRL_HZ, 3),
            "time_s": round(L.agent_time(E), 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - L.agent_time(E), 1)),
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "done": E["done"], "reason": E["reason"],
            **({"cameras": camera_info(cams)} if OBS_CALIBRATION else {})}


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
def decode_row(row: np.ndarray) -> np.ndarray:
    """A request row (sentinels) -> the privileged row (NaN = hold / no override / unchanged)."""
    r = np.asarray(row, dtype=np.float64).copy()
    for arm in (0, 1):
        if not np.any(r[7 * arm + 3:7 * arm + 7]):
            r[7 * arm:7 * arm + 7] = np.nan
    r[14:16] = np.rint(r[14:16])
    for i in (16, 17):
        if r[i] < 0: r[i] = np.nan
    for i in range(18, 22):
        if r[i] <= 0: r[i] = np.nan
    return r


def check_rows(A: np.ndarray) -> None:
    """Rows that cannot be meant (docs/protocol/standard_mode.md §11: a 400, nothing executed): the sentinel-only checks
    here, then the privileged grader's own (rcb_tactilelab.rows_problem on the decoded rows: the same rows are refused
    in both modes)."""
    for ri, row in enumerate(A):
        if not all(v in (0.0, 1.0) for v in row[14:16]):
            raise ValueError(f"row {ri}: gripper commands (columns 14, 15) must be 0 (open) or 1 (closed)")
        for i, (lo, hi) in enumerate(M.FINGER_DRIVE_RANGE):
            if float(row[18 + i]) > hi:
                raise ValueError(f"row {ri}: column {18 + i}, the right finger {M.FINGER_DRIVE_NAMES[i]}, is above its maximum {hi:g} "
                                 "(<= 0 = unchanged; robot_spec.controller.finger_drive)")
    why = M.rows_problem(np.stack([decode_row(r) for r in A]))
    if why is not None:
        raise ValueError(why if why.startswith("row ") else f"rows: {why}")


def step_once(a: np.ndarray, rec: L.Recorder | None) -> bool:
    """One recorded control step, journaled for crash recovery, then the task's rule. True when the call must stop here:
    the episode is over, or the service stops the call (max_call_wall_s, the client hung up)."""
    if ctrl_steps() >= AGENT_CAP:
        finish("step_guard"); return True
    a = np.asarray(a, dtype=np.float64)                    # the exact row Session.step executes (and records)
    stop = step_live(a, "call")
    if rec is not None: rec.tick()
    VIDEO.offer(ctrl_steps())
    after_step(rec)
    return E["done"] or stop


def after_step(rec: L.Recorder | None = None) -> None:
    """The task's rule after a control step (on the live simulator): a simulator error ends the episode; the task failing
    for good ends it; the success condition holding triggers the settle hold and the judgement."""
    if sim_err() is not None:
        finish("error"); return
    tr = getattr(S.task, "truncation_reason", None)
    if tr and tr != "timeout":
        E["truncation"] = str(tr)[:200]; finish("failed"); return
    if ctrl_steps() < int(E.get("hold_after") or 0) or not judged():
        return
    # the condition holds: hold the last command SETTLE steps (in this call's response), then judge. A hold that ends
    # unsolved leaves the episode going; the next step at which the condition holds, SETTLE or more steps later, starts
    # another hold (a condition that flickers, or a latch whose end check fails, never turns every row into a hold)
    E["settles"] = int(E.get("settles") or 0) + 1
    k = hold_steps(SETTLE, rec)
    E["hold_after"] = ctrl_steps() + SETTLE
    log({"ev": "settle", "control_steps": ctrl_steps(), "held": k})
    if sim_err() is not None:
        finish("error"); return
    tr = getattr(S.task, "truncation_reason", None)
    if tr and tr != "timeout":
        E["truncation"] = str(tr)[:200]; finish("failed"); return
    if judged():
        E["success"] = True; E["settle_steps"] = k; finish("success")


def lerp_pose(p0: np.ndarray, p1: np.ndarray, u: float) -> np.ndarray:
    q0 = p0[3:] / np.linalg.norm(p0[3:]); q1 = p1[3:] / np.linalg.norm(p1[3:])
    if float(np.dot(q0, q1)) < 0.0:
        q1 = -q1
    d = float(np.clip(np.dot(q0, q1), -1.0, 1.0))
    if d > 0.9995:
        q = (1.0 - u) * q0 + u * q1
    else:
        th = math.acos(d); q = (math.sin((1.0 - u) * th) * q0 + math.sin(u * th) * q1) / math.sin(th)
    return np.concatenate([(1.0 - u) * p0[:3] + u * p1[:3], q / np.linalg.norm(q)])


def run_ee_pose(A: np.ndarray, dt: float, interp: str, rec: L.Recorder) -> None:
    k = int(round(dt * CTRL_HZ))
    for row in A:
        E["step"] += 1
        r = decode_row(row)
        tg = E.get("target") or [None, None]
        start = [np.asarray(tg[a], dtype=np.float64) if tg[a] is not None else np.asarray(ROB.ee_pose(a), dtype=np.float64) for a in (0, 1)]
        for j in range(1, k + 1):
            a = r.copy()
            if j > 1:
                a[18:22] = np.nan                          # drive settings are applied once, at the row
            if interp == "linear" and k > 1 and j < k:
                for arm in (0, 1):
                    if np.all(np.isfinite(r[7 * arm:7 * arm + 7])):
                        a[7 * arm:7 * arm + 7] = lerp_pose(start[arm], r[7 * arm:7 * arm + 7], j / k)
            cut = step_once(a, rec)
            # the targets of the last executed step: the next `linear` row starts there (a row cut mid-interpolation
            # leaves the arm's target where the cut left it, never at the row's end)
            E["target"] = [[float(v) for v in a[7 * arm:7 * arm + 7]] if np.all(np.isfinite(a[7 * arm:7 * arm + 7])) else None
                           for arm in (0, 1)]
            if cut:
                break
        if E["done"] or EP.stopping:
            return


def parse_submit(meta: dict, A: np.ndarray) -> tuple:
    typ = meta.get("type")
    if not isinstance(typ, str) or typ != "ee_pose":
        raise ValueError(f"type must be ee_pose (not yet: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", 1.0 / CTRL_HZ); interp = choice(meta, "interpolate", "linear", ("hold", "linear"))
    cams = cameras(meta); fps = video_fps(meta); video = choice(meta, "video", "mp4", ("mp4", "frames", "both", "none"))
    note = note_text(meta); depth = L.depth_mode(meta)
    if A.ndim != 2 or A.shape[1] != ACTION_DIM or A.shape[0] < 1:
        raise ValueError(f"ee_pose actions must be (T, {ACTION_DIM}) with T >= 1, got {list(A.shape)}")
    if not (1.0 / CTRL_HZ - 1e-9 <= dt <= 0.5): raise ValueError(f"dt must be in [{1.0 / CTRL_HZ:.4f}, 0.5] s")
    if abs(dt * CTRL_HZ - round(dt * CTRL_HZ)) > 1e-6:
        raise ValueError(f"dt must be a multiple of the 1/{CTRL_HZ} s control period (k/{CTRL_HZ} s, k = 1..{int(0.5 * CTRL_HZ)}); got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9: raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    check_rows(A)
    frames_of(cams, int(A.shape[0] * round(dt * CTRL_HZ)) + SETTLE, fps, depth)
    return typ, dt, interp, cams, fps, video, note


def do_submit(meta: dict, A: np.ndarray) -> tuple[dict, list]:
    typ, dt, interp, cams, fps, video, note = as_400(parse_submit, meta, A)       # a 400 before anything moves
    rec = recorder(cams, fps, meta)
    E["calls"] += 1; step0 = E["step"]
    before = ctrl_steps(); rec.tick(force=True)
    run_ee_pose(A, dt, interp, rec)
    rec.tick(force=True, last=True)
    out = {**meta_common(cams), "chunk_id": E["calls"], "type": typ, "executed_rows": E["step"] - step0, "control_steps_chunk": ctrl_steps() - before,
           "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS, "clipped": [], "n_clipped": 0, "plan": [], "rejected": None, "ok": True,
           **({"frames_skipped": rec.skipped} if rec.skipped else {})}
    log({"ev": "submit", "call": E["calls"], "type": typ, "rows": E["step"] - step0, "dt": dt, "interpolate": interp, "cameras": cams, "note": note,
         "depth": rec.mode, **({"frames_skipped": rec.skipped} if rec.skipped else {}), "control_steps": ctrl_steps() - before,
         "success": bool(E["success"]),
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    out["done"] = E["done"]; out["reason"] = E["reason"]
    return out, rec.parts(video, fps)


def parse_observe(meta: dict) -> tuple:
    cams = cameras(meta); seconds = number(meta, "seconds", 0.0); fps = video_fps(meta)
    video = choice(meta, "video", "frames", ("mp4", "frames", "both", "none")); depth = L.depth_mode(meta)
    if seconds < 0 or seconds > MAX_WATCH_S: raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    frames_of(cams, int(round(seconds * CTRL_HZ)) + SETTLE, fps, depth)
    return cams, seconds, fps, video


def do_observe(meta: dict) -> tuple[dict, list]:
    cams, seconds, fps, video = as_400(parse_observe, meta)                       # a 400 before anything moves
    rec = recorder(cams, fps, meta); before = ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = np.asarray(S.hold_action(), dtype=np.float64)
        for _ in range(int(round(seconds * CTRL_HZ))):
            if step_once(hold, rec): break
        rec.tick(force=True, last=True)
    else:
        rec.tick(force=True, last=True)                    # the current frames: no physics
    E["calls"] += 1
    out = {**meta_common(cams), "obs_id": E["calls"], "seconds": seconds, "control_steps_watch": ctrl_steps() - before,
           "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS, "ok": True, **({"frames_skipped": rec.skipped} if rec.skipped else {})}
    log({"ev": "observe", "call": E["calls"], "seconds": seconds, "cameras": cams, "depth": rec.mode, "control_steps": ctrl_steps() - before,
         **({"stopped": EP.stop_reason} if EP.stopping else {})})
    if seconds > 0: save_call_evidence(E["calls"], {k: v for k, v in out.items() if k != "cameras"}, rec)
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


# ---------------------------------------------------------------- /kinematics (stateless: the URDF model, never the simulator)
Q_START = np.asarray(_q0, dtype=np.float64)
ARM_IDX = [i for i, n in enumerate(_KNAMES) if int(n.split("_")[1]) <= 6]   # model indices of the 12 arm joints


def _frame_T_model(name: str, qm: np.ndarray) -> np.ndarray:
    pin.forwardKinematics(KM, KD, qm); pin.updateFramePlacements(KM, KD)
    if name in LINK_NAMES:
        return BASE_T @ KD.oMf[KM.getFrameId(name)].homogeneous
    parent, off = FRAMES[name]
    return BASE_T @ KD.oMf[KM.getFrameId(parent)].homogeneous @ off


def _ik(targets: dict, seed16, tol_p: float, tol_r: float, iters: int):
    qm = _q_model(seed16).copy()
    tg = {k: _T(v) for k, v in targets.items()}
    lo, hi = KM.lowerPositionLimit, KM.upperPositionLimit
    err = {}
    for _ in range(int(iters) + 1):
        J_rows, e_rows, err = [], [], {}
        pin.computeJointJacobians(KM, KD, qm); pin.updateFramePlacements(KM, KD)
        for name, Tt in tg.items():
            parent, off = (name, np.eye(4)) if name in LINK_NAMES else FRAMES[name]
            fid = KM.getFrameId(parent)
            Tc = BASE_T @ KD.oMf[fid].homogeneous @ off
            dp = Tt[:3, 3] - Tc[:3, 3]
            dR = pin.log3(Tt[:3, :3] @ Tc[:3, :3].T)
            err[name] = (float(np.linalg.norm(dp)), float(np.linalg.norm(dR)))
            Jl = pin.getFrameJacobian(KM, KD, fid, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
            Rb = BASE_T[:3, :3]
            Jv = Rb @ Jl[:3]; Jw = Rb @ Jl[3:]
            r = (Tc[:3, 3] - (BASE_T @ KD.oMf[fid].homogeneous)[:3, 3])
            Jv = Jv - np.cross(r, Jw.T).T                  # the offset frame's linear velocity
            J_rows.append(np.vstack([Jv, Jw])); e_rows.append(np.concatenate([dp, dR]))
        if all(p <= tol_p and r <= tol_r for p, r in err.values()):
            return qm, True, err
        J = np.vstack(J_rows)[:, ARM_IDX]; e = np.concatenate(e_rows)
        lam = 1e-2
        dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(J.shape[0]), e)
        qm[ARM_IDX] = np.clip(qm[ARM_IDX] + np.clip(dq, -0.2, 0.2), lo[ARM_IDX], hi[ARM_IDX])
    return qm, False, err


def do_kinematics(req: dict) -> dict:
    if req["op"] == "fk":
        q16 = np.asarray(req["q"], dtype=np.float64)
        qm = _q_model(q16)
        return L.fk_response({l: _pose(_frame_T_model(l, qm)) for l in req["links"]}, "world")
    seed = Q_START if req.get("seed") is None else np.asarray(req["seed"], dtype=np.float64)
    qm, ok, err = _ik(req["targets"], seed, req["tol_pos_m"], req["tol_rot_rad"], req["max_iters"])
    q16 = np.zeros(16); q16[_TO_MODEL] = qm
    return L.ik_response(q16, ok, err, "world")


SPEC["kinematics"]["ik"].update({"tol_pos_m": 0.002, "tol_rot_rad": 0.02})


def status() -> dict:
    if E.get("end_requested"):
        end_now()                          # never returns
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1)}


def end_now() -> None:
    """End the episode, dump it and exit 0 (on the main thread: Isaac renders and steps only there)."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]: finish("timeout")
        else: dump()
        log({"ev": "exit", "reason": "collect hook: episode dumped (graded by the live episode), releasing the simulator"})
        if not os.path.exists(PID_FILE):   # a SIGUSR1 that came in during a resume: the hook still needs to see this process end
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)          # frees the GPU and the memory: finalize.sh writes final.json once this process is gone


def end_from_signal() -> None:
    """The collect hook's SIGUSR1 (rcb_limited.Episode runs this in a thread). Isaac Sim renders (the hold's video frames,
    the last frame) only on the main thread, which serves the HTTP requests: this thread asks it to end the episode through
    its own GET /status (answered after any call in progress), and keeps asking until the process is gone."""
    import urllib.request
    E["exiting"] = True          # from the signal on, no request runs the simulator (PROTOCOL H.4); the hold below does not
    E["end_requested"] = True    # go through a request
    while True:
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/status", timeout=3600).read()
        except Exception:  # noqa: BLE001 -- not listening yet (a resume), or the process is exiting
            pass
        time.sleep(2)


def replay_row(row) -> None:
    """One journaled row during a resume (no rendering asked for beyond the video's missing slots)."""
    r = np.asarray(row, dtype=np.float64)
    try:
        S.step(r)
    except Exception as exc:
        fault_check("resume", f"{type(exc).__name__}: {exc}")   # a host fault during the resume (fault_check)
        raise
    fault_check("resume")
    VIDEO.offer(ctrl_steps())   # slots already on disk are skipped


def state_sha() -> str:
    return S.state_sha()


fault_check("startup")   # a sidecar or GPU fault while the scene was built or reset (even if restarted): the host's, a restart
S.record_start()         # the resume replay is recorded too: trajectory.npz is the whole episode up to its final hold
VIDEO.offer(0)           # the start state (a restarted service has it on disk already)
resumed = EP.begin(state=E, step=replay_row, state_sha=state_sha, proprio=proprio_row, spec=SPEC, on_end=end_from_signal,
                   start_event={"task": TASK, "seed": S.seed, "cameras": CAMS, "kinematics_check_m": KIN_CHECK, "resume": RESUME})
if resumed:
    VIDEO.truncate(ctrl_steps())   # frames of the call lost in the crash show rolled-back states
E["ready"] = True; write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{PROTOCOL} sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=do_kinematics, status=status,
                  on_submit_error=lambda exc: finish("error"), log=log, episode=EP, state_sha=state_sha, proprio=proprio_row))
