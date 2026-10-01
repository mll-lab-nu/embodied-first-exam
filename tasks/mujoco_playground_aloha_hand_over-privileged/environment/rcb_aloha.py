"""rcb_aloha — MuJoCo Playground's ALOHA tasks in plain MuJoCo for robot_coding_bench: `AlohaSinglePegInsertion`
(below) and `AlohaHandOver` (see ENVS; the instance's "env" picks one).

AlohaHandOver = Playground's `mjx_hand_over.xml`: a red box (4 x 3 x 6 cm) starts on the left arm's side, shifted by
U(-0.05, 0.05) x U(-0.1, 0.1) m; a translucent target box (mocap) is placed at (0.2, 0, 0.25) + U(-0.15, 0.15)^3 m with
x >= 0.15 (the right arm's side). Physics 200 Hz (Playground's sim_dt = 0.005), control 50 Hz (4 substeps). Success
(defined here from Playground's reward and termination): at the end of the trajectory the box is within 3 cm of the
target, touches the right gripper's fingers and not the left arm, and is off the table (z >= 0.05).

AlohaSinglePegInsertion:

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


def _pick_gl() -> None:
    """Rendering backend: EGL (GPU) if it works here, else OSMesa (CPU). Checked once per process, before mujoco is
    imported; an explicit RCB_MUJOCO_GL wins. Physics never depends on it."""
    if os.environ.get("RCB_MUJOCO_GL"):
        os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = os.environ["RCB_MUJOCO_GL"]; return
    if os.environ.get("_RCB_GL_CHECKED"): return
    import subprocess
    probe = ("import mujoco; m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom size=\\'.1\\'/></worldbody></mujoco>'); "
             "d = mujoco.MjData(m); mujoco.mj_forward(m, d); r = mujoco.Renderer(m, 240, 320); r.update_scene(d); r.render(); r.render()")
    env = {**os.environ, "MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"}
    try: ok = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, timeout=60).returncode == 0
    except Exception: ok = False
    gl = "egl" if ok else "osmesa"
    os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = gl; os.environ["_RCB_GL_CHECKED"] = gl


_pick_gl()

ROOT = Path(os.environ.get("RCB_MJ_ROOT", "/opt/rcb_mj"))
CONTROL_DT = 0.02
ENVS = {"AlohaSinglePegInsertion": {"xml": "mjx_single_peg_insertion.xml", "sim_dt": 0.0025, "task": "aloha_single_peg_insertion"},
        "AlohaHandOver": {"xml": "mjx_hand_over.xml", "sim_dt": 0.005, "task": "aloha_hand_over"}}
SIM_DT = 0.0025                                    # AlohaSinglePegInsertion (per env: ENVS[env]["sim_dt"])
SUBSTEPS = int(round(CONTROL_DT / SIM_DT))       # 8 (AlohaHandOver: 4)
HANDOVER_TOL_M = 0.03
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


def load_model(env: str = "AlohaSinglePegInsertion"):
    import mujoco
    assets = {}
    for d in (ROOT / "menagerie/aloha", ROOT / "menagerie/aloha/assets", ROOT / "playground/aloha/xmls", ROOT / "playground/aloha/xmls/assets"):
        for f in d.glob("*"):
            if f.is_file(): assets[f.name] = f.read_bytes()
    m = mujoco.MjModel.from_xml_string((ROOT / "playground/aloha/xmls" / ENVS[env]["xml"]).read_text(), assets)
    m.opt.timestep = ENVS[env]["sim_dt"]
    return m


def instance_offsets(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-0.1, 0.1, 2), rng.uniform(-0.1, 0.1, 2)          # peg xy, socket xy


def handover_instance(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Playground's AlohaHandOver reset randomization, drawn with numpy: box xy offset, target position."""
    rng = np.random.default_rng(seed)
    box = np.array([rng.uniform(-0.05, 0.05), rng.uniform(-0.1, 0.1)])
    tgt = np.array([0.20, 0.0, 0.25]) + rng.uniform(-0.15, 0.15, 3); tgt[0] = max(tgt[0], 0.15)
    return box, tgt


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco
        self.mj = mujoco
        self.inst = json.load(open(instance)); self.seed = int(self.inst["seed"]); self.env = self.inst.get("env", "AlohaSinglePegInsertion")
        self.substeps = int(round(CONTROL_DT / ENVS[self.env]["sim_dt"]))
        self.model = load_model(self.env); self.data = mujoco.MjData(self.model); m = self.model
        self._act = np.array([m.actuator(n).id for n in ACTUATOR_NAMES])
        self.lower = m.actuator_ctrlrange[self._act, 0].copy(); self.upper = m.actuator_ctrlrange[self._act, 1].copy()
        if self.env == "AlohaSinglePegInsertion":
            self.peg_xy = np.array(self.inst["peg_xy_offset"], float); self.socket_xy = np.array(self.inst["socket_xy_offset"], float)
            self._peg = m.body("peg").id; self._socket = m.body("socket").id
            self._peg_q = m.jnt_qposadr[m.body_jntadr[self._peg]]; self._sock_q = m.jnt_qposadr[m.body_jntadr[self._socket]]
            self._s_ent = m.site("socket_entrance").id; self._s_rear = m.site("socket_rear").id; self._p_end2 = m.site("peg_end2").id
        else:
            self.box_xy = np.array(self.inst["box_xy_offset"], float); self.target_pos = np.array(self.inst["target_pos"], float)
            self._box = m.body("box").id; self._box_q = m.jnt_qposadr[m.body_jntadr[self._box]]; self._box_geom = m.geom("box").id
            self._mocap = m.body_mocapid[m.body("mocap_target").id]
            self._right_geoms = {g for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name.startswith("right/") and "finger" in m.body(m.geom_bodyid[g]).name}
            self._left_geoms = {g for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name.startswith("left/")}
        self._renderer = None; self.enable_render = enable_render
        self._recording: list | None = None; self._trace: list | None = None; self.resets = 0; self.total_steps = 0
        _slog("session_start", task=ENVS[self.env]["task"], seed=self.seed)
        import atexit
        atexit.register(lambda: (self._trace_dump(), _slog("session_end", resets=self.resets, sim_steps=self.total_steps * self.substeps)))
        self.reset()
        exp = self.inst.get("state_sha")
        if exp and self.state_sha() != exp: raise RuntimeError(f"initial state hash {self.state_sha()} != instance {exp}")

    def reset(self) -> None:
        self._trace_dump(); m, d = self.model, self.data
        self.mj.mj_resetDataKeyframe(m, d, m.key("home").id)
        if self.env == "AlohaSinglePegInsertion":
            d.qpos[self._peg_q:self._peg_q + 2] += self.peg_xy; d.qpos[self._sock_q:self._sock_q + 2] += self.socket_xy
        else:
            d.qpos[self._box_q:self._box_q + 2] += self.box_xy; d.mocap_pos[self._mocap] = self.target_pos
        d.qvel[:] = 0.0; self.mj.mj_forward(m, d)
        self.targets = d.ctrl[self._act].copy(); self.steps = 0; self.resets += 1
        self._recording = self._recording if self._recording is None else []
        self._trace = [] if TRACE_DIR else None; _slog("reset", n=self.resets)

    def step(self, targets) -> dict[str, Any]:
        tg = np.clip(np.asarray(targets, dtype=np.float64).reshape(N), self.lower, self.upper)
        if not np.all(np.isfinite(tg)): raise ValueError("targets contain NaN/inf")
        self.targets = tg; self.data.ctrl[self._act] = tg
        for _ in range(self.substeps): self.mj.mj_step(self.model, self.data)
        self.steps += 1; self.total_steps += 1
        if self._recording is not None: self._recording.append(tg.copy())
        if self._trace is not None: self._trace.append(tg.astype(np.float32))
        return self.check()

    def check(self) -> dict[str, Any]:
        if self.env == "AlohaHandOver": return self._check_handover()
        d = self.data; rear = d.site_xpos[self._s_rear]; ent = d.site_xpos[self._s_ent]; tip = d.site_xpos[self._p_end2]
        ab = ent - rear; t = float(np.dot(tip - rear, ab) / (np.dot(ab, ab) + 1e-12)); dist = float(np.linalg.norm(tip - (rear + t * ab)))
        inserted = dist < LINE_TOL_M and 0.0 <= t <= DEPTH_T_MAX
        return {"success": bool(inserted), "inserted": bool(inserted), "tip_to_axis_m": round(dist, 5), "axial_t": round(t, 4),
                "socket_z": round(float(d.xpos[self._socket][2]), 4), "peg_z": round(float(d.xpos[self._peg][2]), 4), "time_s": round(self.steps * CONTROL_DT, 3)}

    def _check_handover(self) -> dict[str, Any]:
        d = self.data; box = d.xpos[self._box]; dist = float(np.linalg.norm(box - self.target_pos))
        right = left = False
        for c in d.contact[:d.ncon]:
            pair = {c.geom1, c.geom2}
            if self._box_geom in pair:
                other = (pair - {self._box_geom}) or {self._box_geom}; o = next(iter(other))
                right |= o in self._right_geoms; left |= o in self._left_geoms
        ok = dist < HANDOVER_TOL_M and right and not left and box[2] >= 0.05
        return {"success": bool(ok), "box_to_target_m": round(dist, 4), "right_holds": bool(right), "left_touches": bool(left),
                "box_z": round(float(box[2]), 4), "time_s": round(self.steps * CONTROL_DT, 3)}

    def state(self) -> dict[str, Any]:
        d, m = self.data, self.model
        if self.env == "AlohaHandOver":
            sites = {n: d.site_xpos[m.site(n).id].copy() for n in ("box_top", "box_bottom", "left/gripper", "right/gripper")}
            return {"qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "targets": self.targets.copy(), "sites": sites, "box_pos": d.xpos[self._box].copy(),
                    "box_quat_wxyz": d.xquat[self._box].copy(), "target_pos": self.target_pos.copy(), **self.check()}
        sites = {n: d.site_xpos[m.site(n).id].copy() for n in ("socket_entrance", "socket_rear", "peg_end1", "peg_end2", "left/gripper", "right/gripper")}
        return {"qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "targets": self.targets.copy(), "sites": sites,
                "peg_pos": d.xpos[self._peg].copy(), "peg_quat_wxyz": d.xquat[self._peg].copy(),
                "socket_pos": d.xpos[self._socket].copy(), "socket_quat_wxyz": d.xquat[self._socket].copy(), **self.check()}

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    def record_start(self) -> None: self._recording = []

    def record_stop(self) -> np.ndarray:
        a = np.array(self._recording or [], dtype=np.float64).reshape(-1, N); self._recording = None
        _slog("record", n_actions=int(len(a)), success=self.check()["success"]); return a

    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=ENVS[self.env]["task"], seed=self.seed,
                 action_layout="14 actuator targets per control step (1/50 s): " + ",".join(ACTUATOR_NAMES), meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        self.reset(); self._trace = None; A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        if len(A) > MAX_STEPS: raise ValueError(f"trajectory longer than {MAX_STEPS} control steps")
        for row in A: self.step(row)
        r = self.check(); _slog("replay", n_actions=int(len(A)), success=r["success"])
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
                                success=self.check()["success"], t_end=time.time())
        except Exception: pass


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"seed": s.seed, "state_sha": s.state_sha(), **s.check()}))
