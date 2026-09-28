"""rcb_aloha — MuJoCo Playground `AlohaSinglePegInsertion` in plain MuJoCo for robot_coding_bench.

Scene = MuJoCo Playground's `manipulation/aloha/xmls/mjx_single_peg_insertion.xml` (Apache-2.0, @4057c14) with the
ALOHA 2 robot from MuJoCo Menagerie (@1b86ece, the commit Playground pins): two ViperX 300s arms, 7 position actuators
each (6 joints + gripper finger), a blue socket (a square tube, open towards +x, red wall at the back) and a red peg.
Physics 400 Hz (Playground's sim_dt = 0.0025, implicitfast), control 50 Hz (8 substeps).

Instance = Playground's reset randomization with a fixed seed: the peg and the socket are shifted in x and y by
U(-0.1, 0.1) m each from the `home` keyframe. The robot starts in `home`.

Success (defined here from Playground's own insertion geometry; Playground itself only has a shaped RL reward):
at the end of the trajectory the peg's tip (site `peg_end2`) is within 5 mm of the socket's axis (the line through
sites `socket_rear` and `socket_entrance`) and at least 25 % of the socket's depth inside it (axial parameter
t <= 0.75, t = 0 at the rear wall, 1 at the entrance). trajectory = (T, 14) actuator targets, one row per control step.
"""
from __future__ import annotations
import hashlib, json, os, sys, time
from pathlib import Path
from typing import Any
import numpy as np

ROOT = Path(os.environ.get("RCB_MJ_ROOT", "/opt/rcb_mj"))
SIM_DT = 0.0025
CONTROL_DT = 0.02
SUBSTEPS = int(round(CONTROL_DT / SIM_DT))       # 8
MAX_STEPS = 3000                                   # 60 s of control; longer trajectories are rejected
LINE_TOL_M = 0.005; DEPTH_T_MAX = 0.75
ACTUATOR_NAMES = [f"{s}/{j}" for s in ("left", "right") for j in ("waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate", "gripper")]
N = len(ACTUATOR_NAMES)                            # 14
CAMERAS = ("overhead_cam", "teleoperator_pov", "wrist_cam_left", "wrist_cam_right")

# Written under Harbor's agent-log mount (/logs/agent, collected even if the agent tidies /app/output; one run deleted
# its /app/output copies) when it exists, else under /app/output.
_LOGDIR = "/logs/agent/rcb" if os.path.isdir("/logs/agent") else "/app/output"
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", f"{_LOGDIR}/rcb_session_log.jsonl")
TRACE_DIR = os.environ.get("RCB_AGENT_TRACE_DIR", f"{_LOGDIR}/rcb_trace")
TRACE_MAX_FILES = 300; TRACE_MAX_BYTES = 400 * 1024 * 1024


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG: return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f: f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n")
    except OSError: pass


def load_model():
    import mujoco
    assets = {}
    for d in (ROOT / "menagerie/aloha", ROOT / "menagerie/aloha/assets", ROOT / "playground/aloha/xmls", ROOT / "playground/aloha/xmls/assets"):
        for f in d.glob("*"):
            if f.is_file(): assets[f.name] = f.read_bytes()
    m = mujoco.MjModel.from_xml_string((ROOT / "playground/aloha/xmls/mjx_single_peg_insertion.xml").read_text(), assets)
    m.opt.timestep = SIM_DT
    return m


def instance_offsets(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-0.1, 0.1, 2), rng.uniform(-0.1, 0.1, 2)          # peg xy, socket xy


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco
        self.mj = mujoco
        self.inst = json.load(open(instance)); self.seed = int(self.inst["seed"])
        self.peg_xy = np.array(self.inst["peg_xy_offset"], float); self.socket_xy = np.array(self.inst["socket_xy_offset"], float)
        self.model = load_model(); self.data = mujoco.MjData(self.model); m = self.model
        self._act = np.array([m.actuator(n).id for n in ACTUATOR_NAMES])
        self.lower = m.actuator_ctrlrange[self._act, 0].copy(); self.upper = m.actuator_ctrlrange[self._act, 1].copy()
        self._peg = m.body("peg").id; self._socket = m.body("socket").id
        self._peg_q = m.jnt_qposadr[m.body_jntadr[self._peg]]; self._sock_q = m.jnt_qposadr[m.body_jntadr[self._socket]]
        self._s_ent = m.site("socket_entrance").id; self._s_rear = m.site("socket_rear").id; self._p_end2 = m.site("peg_end2").id
        self._renderer = None; self.enable_render = enable_render
        self._recording: list | None = None; self._trace: list | None = None; self.resets = 0; self.total_steps = 0
        _slog("session_start", task="aloha_single_peg_insertion", seed=self.seed)
        import atexit
        atexit.register(lambda: (self._trace_dump(), _slog("session_end", resets=self.resets, sim_steps=self.total_steps * SUBSTEPS)))
        self.reset()
        exp = self.inst.get("state_sha")
        if exp and self.state_sha() != exp: raise RuntimeError(f"initial state hash {self.state_sha()} != instance {exp}")

    def reset(self) -> None:
        self._trace_dump(); m, d = self.model, self.data
        self.mj.mj_resetDataKeyframe(m, d, m.key("home").id)
        d.qpos[self._peg_q:self._peg_q + 2] += self.peg_xy; d.qpos[self._sock_q:self._sock_q + 2] += self.socket_xy
        d.qvel[:] = 0.0; self.mj.mj_forward(m, d)
        self.targets = d.ctrl[self._act].copy(); self.steps = 0; self.resets += 1
        self._recording = self._recording if self._recording is None else []
        self._trace = [] if TRACE_DIR else None; _slog("reset", n=self.resets)

    def step(self, targets) -> dict[str, Any]:
        tg = np.clip(np.asarray(targets, dtype=np.float64).reshape(N), self.lower, self.upper)
        if not np.all(np.isfinite(tg)): raise ValueError("targets contain NaN/inf")
        self.targets = tg; self.data.ctrl[self._act] = tg
        for _ in range(SUBSTEPS): self.mj.mj_step(self.model, self.data)
        self.steps += 1; self.total_steps += 1
        if self._recording is not None: self._recording.append(tg.copy())
        if self._trace is not None: self._trace.append(tg.astype(np.float32))
        return self.check()

    def check(self) -> dict[str, Any]:
        d = self.data; rear = d.site_xpos[self._s_rear]; ent = d.site_xpos[self._s_ent]; tip = d.site_xpos[self._p_end2]
        ab = ent - rear; t = float(np.dot(tip - rear, ab) / (np.dot(ab, ab) + 1e-12)); dist = float(np.linalg.norm(tip - (rear + t * ab)))
        inserted = dist < LINE_TOL_M and 0.0 <= t <= DEPTH_T_MAX
        return {"inserted": bool(inserted), "tip_to_axis_m": round(dist, 5), "axial_t": round(t, 4),
                "socket_z": round(float(d.xpos[self._socket][2]), 4), "peg_z": round(float(d.xpos[self._peg][2]), 4), "time_s": round(self.steps * CONTROL_DT, 3)}

    def state(self) -> dict[str, Any]:
        d, m = self.data, self.model
        sites = {n: d.site_xpos[m.site(n).id].copy() for n in ("socket_entrance", "socket_rear", "peg_end1", "peg_end2", "left/gripper", "right/gripper")}
        return {"qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "targets": self.targets.copy(), "sites": sites,
                "peg_pos": d.xpos[self._peg].copy(), "peg_quat_wxyz": d.xquat[self._peg].copy(),
                "socket_pos": d.xpos[self._socket].copy(), "socket_quat_wxyz": d.xquat[self._socket].copy(), **self.check()}

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    def record_start(self) -> None: self._recording = []

    def record_stop(self) -> np.ndarray:
        a = np.array(self._recording or [], dtype=np.float64).reshape(-1, N); self._recording = None
        _slog("record", n_actions=int(len(a)), inserted=self.check()["inserted"]); return a

    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task="aloha_single_peg_insertion", seed=self.seed,
                 action_layout="14 actuator targets per control step (1/50 s): " + ",".join(ACTUATOR_NAMES), meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        self.reset(); self._trace = None; A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        if len(A) > MAX_STEPS: raise ValueError(f"trajectory longer than {MAX_STEPS} control steps")
        for row in A: self.step(row)
        r = self.check(); _slog("replay", n_actions=int(len(A)), inserted=r["inserted"])
        return {**r, "state_sha": self.state_sha(), "steps": self.steps}

    def render(self, camera: str = "overhead_cam", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
            self._renderer = self.mj.Renderer(self.model, size[1], size[0])
        self._renderer.update_scene(self.data, camera=camera); return self._renderer.render().copy()

    def render_grid(self, cameras=CAMERAS, size=(320, 240)) -> np.ndarray:
        tiles = [self.render(c, size) for c in cameras]
        while len(tiles) % 2: tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + 2], axis=1) for i in range(0, len(tiles), 2)], axis=0)

    def render_video(self, actions, path: str | Path, every: int = 2, fps: int = 25) -> dict[str, Any]:
        import imageio.v2 as imageio
        self.reset(); self._trace = None; frames = [self.render_grid()]
        for i, row in enumerate(np.asarray(actions, dtype=np.float64)):
            self.step(row)
            if (i + 1) % every == 0: frames.append(self.render_grid())
        frames.append(self.render_grid())
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames: w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), frames[-1])
        return {**self.check(), "n_frames": len(frames), "video": str(path)}

    def _trace_dump(self) -> None:
        tr = self._trace; self._trace = None
        if not tr or not TRACE_DIR: return
        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            ents = [e for e in os.scandir(TRACE_DIR) if e.name.endswith(".npz")]
            if len(ents) >= TRACE_MAX_FILES or sum(e.stat().st_size for e in ents) >= TRACE_MAX_BYTES: return
            np.savez_compressed(os.path.join(TRACE_DIR, f"{os.getpid()}_{self.resets:05d}.npz"), actions=np.stack(tr),
                                inserted=self.check()["inserted"], t_end=time.time())
        except Exception: pass


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"seed": s.seed, "state_sha": s.state_sha(), **s.check()}))
