"""A toy eai-standard/2.2 sim service: the smallest complete adapter of the shared layer (rcb_limited.py), on a numpy
"simulator" (a 3-joint point robot pushing a block on a plane), CPU only. selftest.py drives it to test the layer's crash
recovery; it is also the reference for how a benchmark's environment/sim/server.py uses Episode (docs/STANDARD_MODE.md).

Env: RCB_DATA (record dir), RCB_TOY_RESUME (exact | approx), RCB_TOY_MODE (inprocess: the live episode's verdict, written in-process, as
RoboWits | dump: dump the episode and exit on SIGUSR1, as RoboLab / BEHAVIOR / RoboPaint), test knobs RCB_TOY_STEP_S (wall
time per control step), RCB_TOY_PERTURB (added to the joints at every step after a restart: a nondeterministic simulator),
RCB_TOY_HANG_S (the scene build hangs that long on the first start), RCB_TOY_REFUSE (a reason: the service refuses the
episode at its start, as DexJoCo does with too few CPUs), RCB_TOY_PORT."""
from __future__ import annotations
import hashlib, os, sys, threading, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data"); os.makedirs(os.path.join(DATA, "calls"), exist_ok=True)
MODE = os.environ.get("RCB_TOY_MODE", "inprocess")
CTRL_HZ = 20; N = 3
LOCK = threading.Lock()
E = {"ready": False, "step": 0, "calls": 0, "done": False, "reason": None, "success": False, "t0": time.time(), "error": None}
EP = L.Episode(DATA, dim=N, resume=os.environ.get("RCB_TOY_RESUME", "exact"), persist=("last_note",))
EP.startup()
if os.environ.get("RCB_TOY_REFUSE"):
    EP.give_up(os.environ["RCB_TOY_REFUSE"], infra=True)   # never returns: the verdict, then 409 to every request


class Toy:
    """The simulator: joints q follow their targets at most 0.05 per step; the block moves with the tip once touched."""

    def __init__(self, live: bool = True):
        hang = float(os.environ.get("RCB_TOY_HANG_S", "0"))
        if live and hang and EP.n_startups == 1:
            time.sleep(hang)                               # a scene build that hangs (the watchdog's case)
        self.q = np.zeros(N); self.target = np.zeros(N); self.block = np.array([0.5, 0.0, 0.0]); self.n_steps = 0
        self.rec: list | None = None
        self.perturb = float(os.environ.get("RCB_TOY_PERTURB", "0")) if live and EP.n_startups > 1 else 0.0
        self.step_s = float(os.environ.get("RCB_TOY_STEP_S", "0")) if live else 0.0

    def step(self, a) -> None:
        a = np.asarray(a, dtype=np.float64)
        if self.rec is not None:
            self.rec.append(a.copy())
        self.target = a.copy()
        self.q = self.q + np.clip(self.target - self.q, -0.05, 0.05) + self.perturb
        if np.linalg.norm(self.q - self.block) < 0.1:
            self.block = self.q.copy()
        self.n_steps += 1
        if self.step_s:
            time.sleep(self.step_s)

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.q, self.target, self.block]).tobytes()).hexdigest()[:16]

    def success(self) -> bool:
        return bool(self.block[0] > 0.9)


S = Toy()
EP.scene_built()
LAYOUT = [f"j{i}" for i in range(N)]
SPEC = {
    "protocol": L.PROTOCOL, "protocol_compat": L.COMPAT, "simulator": "toy (numpy)", "robot": "toy-3dof", "task_text": "push the block to x > 0.9",
    "control_hz": CTRL_HZ, "physics_substeps": 1, "max_chunk_s": 10.0, "max_watch_s": 30.0,
    "cameras": {"top": {"rgb": True, "depth": True, "mounted": "static", "resolution": [8, 8], "intrinsic_cv": [[8, 0, 4], [0, 8, 4], [0, 0, 1]],
                        "mount": {"type": "static", "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist()}}},
    "default_cameras": ["top"],
    "action_types": {"joint_position": {"dim": N, "layout": LAYOUT, "units": "m", "limits": {j: [-2.0, 2.0] for j in LAYOUT},
                                        "semantics": "joint targets, rows dt apart, hold or linear"}, "not_yet": ["ee_pose"]},
    "proprio_layout": LAYOUT + [f"{j}_vel" for j in LAYOUT] + ["gripper_opening_m"] + ["x", "y", "z", "qw", "qx", "qy", "qz"] + [f"{j}_effort" for j in LAYOUT],
    "proprio_groups": {"joint_pos": [0, 3, "joints"], "joint_vel": [3, 3, "velocities"], "gripper_opening": [6, 1, "none"],
                       "tcp_pose": [7, 7, "the tip: x y z + qw qx qy qz"], "joint_effort": [14, 3, "target - q"]},
    "static": {}, "world": {"frame": "toy", "up": "+z", "units": {"length": "m"}, "quaternion_order": "wxyz", "camera_axes": "OpenCV"},
    "budget": {"reset": 0, "steps": None, "wall_clock_s": 3600.0},
    "robot_spec": {"name": "toy"}, "depth": {"modes": list(L.DEPTH_MODES), "default": "none"},
    "kinematics": {"endpoint": "/kinematics", "joint_names": LAYOUT, "frame": "world", "quaternion_order": "wxyz", "links": ["tip"],
                   "tcp_frames": ["tip"], "ee_frames": ["tip"], "ik_targets": ["tip"]},
}


def ctrl_steps() -> int:
    return S.n_steps


def proprio_row() -> np.ndarray:
    return np.concatenate([S.q, np.zeros(N), [0.0], S.q, [1, 0, 0, 0], S.target - S.q]).astype(np.float32)


def grab(cams, want_depth):
    img = np.zeros((8, 8, 3), np.uint8); img[..., 0] = int(255 * min(1.0, abs(S.block[0])))
    return {c: img for c in cams}, ({c: np.ones((8, 8), np.float32) for c in cams} if want_depth else {})


def write_final() -> None:
    fin = L._read_json(os.path.join(DATA, "final.json"))
    if L.final_verdict(DATA):
        return
    fin.update({"success": bool(E["success"]), "steps": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"],
                "reason": E["reason"], "protocol": L.PROTOCOL, "finalized": bool(E.get("finalized")), "live_success": bool(E["success"]),
                **({"graded_by": "live", "replays": 0} if E.get("finalized") else {}),
                **EP.final_fields()})
    L._write_json(os.path.join(DATA, "final.json"), fin)


def finish(reason: str) -> None:
    if E["done"]:
        return
    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()
    EP.log({"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"])})
    write_final()


def ctrl_step(a, rec) -> bool:
    S.step(a); stop = EP.journal(a); rec.tick()
    if S.success() and not E["success"]:
        E["success"] = True; finish("success")
    return E["done"] or stop


def clock() -> dict:
    """meta time_s / time_left_s: the agent's clock, from its first request (rcb_limited.agent_time), as every adapter."""
    t = L.agent_time(E)
    return {"time_s": round(t, 2), "time_left_s": max(0.0, round(SPEC["budget"]["wall_clock_s"] - t, 1))}


def do_submit(meta, A):
    if meta.get("type") != "joint_position": raise ValueError("type must be joint_position")
    if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"actions must be (T, {N})")
    if not np.all(np.isfinite(A)): raise ValueError("actions contain NaN/inf")
    if meta.get("note") == "raise": raise RuntimeError("toy simulator error")
    dt = float(meta.get("dt", 1.0 / CTRL_HZ)); k = max(1, int(round(dt * CTRL_HZ)))
    rec = L.Recorder(["top"], 1000, grab, proprio_row, lambda cs: {c: np.eye(4)[:3] for c in cs}, ctrl_steps, clock_hz=CTRL_HZ)
    E["calls"] += 1; step0 = E["step"]; rec.tick(force=True); E["last_note"] = meta.get("note")
    for row in A:
        E["step"] += 1
        for _ in range(k):
            if ctrl_step(row, rec): break
        if E["done"] or EP.stopping: break
    rec.tick(force=True, last=True)
    EP.log({"ev": "submit", "call": E["calls"], "rows": E["step"] - step0, "control_steps": ctrl_steps()})
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "executed_rows": E["step"] - step0, "done": E["done"],
            "reason": E["reason"], "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "ok": True, **clock()}, rec.parts("none", 10)


def do_observe(meta):
    seconds = float(meta.get("seconds", 0))
    if meta.get("note") == "raise": raise RuntimeError("toy renderer error")
    rec = L.Recorder(["top"], 1000, grab, proprio_row, lambda cs: {c: np.eye(4)[:3] for c in cs}, ctrl_steps, clock_hz=CTRL_HZ)
    rec.tick(force=True)
    if seconds > 0 and not E["done"]:
        for _ in range(int(round(seconds * CTRL_HZ))):
            if ctrl_step(S.target.copy(), rec): break
    E["calls"] += 1
    return {"calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "proprio": {"layout": SPEC["proprio_layout"], "now": proprio_row().tolist()}, "ok": True, **clock()}, rec.parts("none", 10)


def status() -> dict:
    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), "done": E["done"], "reason": E["reason"],
            "elapsed_s": round(time.time() - E["t0"], 1), "last_note": E.get("last_note")}


def end_episode() -> None:
    """The collect hook's SIGUSR1: end the episode, then grade in-process (inprocess: the live episode's verdict, nothing
    replayed; PROTOCOL H.4) or dump and exit (dump)."""
    with LOCK:
        if not E["done"]:
            finish("timeout")
        acts = np.asarray(S.rec, dtype=np.float64).reshape(-1, N); live = S.state_sha()
        np.save(os.path.join(DATA, "trajectory.npy"), acts)
        if MODE == "dump":
            L._write_json(os.path.join(DATA, "episode.json"), {"success": bool(E["success"]), "n_actions": len(acts), "live_sha": live,
                                                               "reason": E["reason"], **EP.final_fields()})
            os._exit(0)
        # the live record's fields first, the verdict (finalized + graded_by) last: the collect hook stops waiting at the
        # verdict, so it must never see one without them (the main thread's write_final can run in between)
        fin = L._read_json(os.path.join(DATA, "final.json")); fin.update({"n_actions": len(acts), "live_sha": live})
        L._write_json(os.path.join(DATA, "final.json"), fin)
        E["finalized"] = True; write_final()


S.rec = []                                                  # record_start: the resume replay is recorded too
EP.begin(state=E, step=S.step, state_sha=S.state_sha, proprio=proprio_row, spec=SPEC, start_event={"task": "toy"}, on_end=end_episode)
with LOCK:                                                  # a SIGUSR1 kept during the resume is being served already
    E["ready"] = True; write_final()
open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} toy sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(L.Service(spec=SPEC, lock=LOCK, state=E, submit=do_submit, observe=do_observe, kinematics=lambda req: {"ok": True, "op": req["op"]},
                  status=status, on_submit_error=lambda exc: finish("error"), log=EP.log, episode=EP, state_sha=S.state_sha,
                  proprio=proprio_row), port=int(os.environ.get("RCB_TOY_PORT", "8000")))
