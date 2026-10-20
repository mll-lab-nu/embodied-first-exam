"""rcb_panda — MuJoCo Playground's Franka Panda tasks in plain MuJoCo for Embodied First Exam (the instance's "env").

Scenes = MuJoCo Playground's `manipulation/franka_emika_panda/xmls` (Apache-2.0, @4057c14) with the Panda from MuJoCo
Menagerie (@1b86ece, the commit Playground pins): 7 joint position actuators + 1 finger actuator (0 = closed ..
0.04 m = open), gripper site `gripper` between the fingertips. Physics 200 Hz (Playground's sim_dt = 0.005),
control 50 Hz (4 substeps). Playground only has shaped RL rewards; success is defined here from them.

PandaPickCubeOrientation (`mjx_single_cube.xml`, keyframe `home`): a 4 x 4 x 6 cm box on the floor, shifted by
U(-0.2, 0.2)^2 m in xy; a translucent target box at the box's start + U(-0.2, 0.2)^2 x U(0.2, 0.4) m, rotated by
U(0, 45 deg) about a random axis. Success: at the end the box is within 2 cm of the target and within 15 deg of its
orientation.

PandaOpenCabinet (`mjx_cabinet.xml`, keyframe `upright` + Playground's random arm perturbation of up to 30 deg per
joint): a handle on a slide (x from 0.5 m down to 0.0 m) with a shelf behind a barrier; the target is at
x = 0.3 + U(-0.1, 0.1) m. Success: at the end the handle is within 1.5 cm of the target along x.

trajectory = (T, 8) actuator targets, one row per control step (1/50 s).
"""
from __future__ import annotations
import hashlib, json, os, sys, time
from pathlib import Path
from typing import Any
import numpy as np


def _pick_gl() -> None:
    """Rendering backend: EGL (GPU) if it works here, else OSMesa (CPU); checked once, before mujoco is imported."""
    if os.environ.get("RCB_MUJOCO_GL"):
        os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = os.environ["RCB_MUJOCO_GL"]; return
    if os.environ.get("_RCB_GL_CHECKED"): return
    import subprocess
    probe = ("import mujoco; m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom size=\\'.1\\'/></worldbody></mujoco>'); "
             "d = mujoco.MjData(m); mujoco.mj_forward(m, d); r = mujoco.Renderer(m, 240, 320); r.update_scene(d); r.render(); r.render()")
    try: ok = subprocess.run([sys.executable, "-c", probe], env={**os.environ, "MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"}, capture_output=True, timeout=60).returncode == 0
    except Exception: ok = False
    gl = "egl" if ok else "osmesa"; os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = gl; os.environ["_RCB_GL_CHECKED"] = gl


_pick_gl()

ROOT = Path(os.environ.get("RCB_MJ_ROOT", "/opt/rcb_mj"))
SIM_DT = 0.005; CONTROL_DT = 0.02; SUBSTEPS = 4; MAX_STEPS = 3000
ACTUATOR_NAMES = [f"actuator{i}" for i in range(1, 9)]
N = len(ACTUATOR_NAMES)
ENVS = {"PandaPickCubeOrientation": {"xml": "mjx_single_cube.xml", "key": "home", "task": "panda_pick_cube_orientation", "obj": "box"},
        "PandaOpenCabinet": {"xml": "mjx_cabinet.xml", "key": "upright", "task": "panda_open_cabinet", "obj": "handle"}}
PICK_POS_TOL = 0.02; PICK_ROT_TOL_DEG = 15.0; CABINET_TOL = 0.015

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


def load_model(env: str):
    import mujoco
    assets = {}
    for d in (ROOT / "menagerie/franka_emika_panda", ROOT / "menagerie/franka_emika_panda/assets", ROOT / "playground/franka_emika_panda/xmls"):
        for f in d.glob("*"):
            if f.is_file(): assets[f.name] = f.read_bytes()
    m = mujoco.MjModel.from_xml_string((ROOT / "playground/franka_emika_panda/xmls" / ENVS[env]["xml"]).read_text(), assets)
    m.opt.timestep = SIM_DT
    if env == "PandaOpenCabinet": m.geom("hand_capsule").conaffinity = 3        # as Playground's env does
    return m


def _axis_angle_quat(axis, theta):
    axis = np.asarray(axis, float); axis = axis / np.linalg.norm(axis)
    return np.concatenate([[np.cos(theta / 2)], np.sin(theta / 2) * axis])


def pick_instance(seed: int, init_box=(0.5, 0.0, 0.03)):
    """Playground's PandaPickCubeOrientation reset randomization, drawn with numpy."""
    rng = np.random.default_rng(seed); b0 = np.array(init_box)
    box = b0 + np.concatenate([rng.uniform(-0.2, 0.2, 2), [0.0]])
    tgt = b0 + np.concatenate([rng.uniform(-0.2, 0.2, 2), [rng.uniform(0.2, 0.4)]])
    q = _axis_angle_quat(rng.uniform(-1, 1, 3), rng.uniform(0, np.deg2rad(45)))
    return box, tgt, q


def cabinet_instance(seed: int):
    """Playground's PandaOpenCabinet reset randomization, drawn with numpy: target x and the arm perturbation."""
    rng = np.random.default_rng(seed); eps = np.deg2rad(30)
    tx = 0.3 + rng.uniform(-0.1, 0.1)
    lo = np.array([-eps, -eps, -eps, -2 * eps, -eps, 0, -eps]); hi = np.array([eps, eps, eps, 0, eps, 2 * eps, eps])
    return np.array([tx, 0.0, 0.5]), rng.uniform(lo, hi)


def _quat_angle_deg(a, b) -> float:
    d = abs(float(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b)))); return float(np.degrees(2 * np.arccos(min(1.0, d))))


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco
        self.mj = mujoco
        self.inst = json.load(open(instance)); self.env = self.inst["env"]; self.seed = int(self.inst["seed"])
        self.model = load_model(self.env); self.data = mujoco.MjData(self.model); m = self.model
        self._act = np.array([m.actuator(n).id for n in ACTUATOR_NAMES])
        self.lower = m.actuator_ctrlrange[self._act, 0].copy(); self.upper = m.actuator_ctrlrange[self._act, 1].copy()
        self._obj = m.body(ENVS[self.env]["obj"]).id; self._mocap = m.body_mocapid[m.body("mocap_target").id]
        self._gripper = m.site("gripper").id
        self.target_pos = np.array(self.inst["target_pos"], float)
        self.target_quat = np.array(self.inst.get("target_quat_wxyz", [1, 0, 0, 0]), float)
        self.cameras = [m.camera(i).name for i in range(m.ncam)] or ["free"]
        self._renderer = None; self.enable_render = enable_render
        self._recording: list | None = None; self._trace: list | None = None; self.resets = 0; self.total_steps = 0
        _slog("session_start", task=ENVS[self.env]["task"], seed=self.seed)
        import atexit
        atexit.register(lambda: (self._trace_dump(), _slog("session_end", resets=self.resets, sim_steps=self.total_steps * SUBSTEPS)))
        self.reset()
        exp = self.inst.get("state_sha")
        if exp and self.state_sha() != exp: raise RuntimeError(f"initial state hash {self.state_sha()} != instance {exp}")

    def reset(self) -> None:
        self._trace_dump(); m, d = self.model, self.data
        self.mj.mj_resetDataKeyframe(m, d, m.key(ENVS[self.env]["key"]).id)
        if self.env == "PandaPickCubeOrientation":
            qa = m.jnt_qposadr[m.body_jntadr[self._obj]]; d.qpos[qa:qa + 3] = self.inst["box_pos"]
        else:
            pert = np.array(self.inst["arm_perturbation"], float); d.qpos[:7] += pert; d.ctrl[:7] += pert
        d.mocap_pos[self._mocap] = self.target_pos; d.mocap_quat[self._mocap] = self.target_quat
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
        d = self.data; p = d.xpos[self._obj]
        if self.env == "PandaPickCubeOrientation":
            err = float(np.linalg.norm(p - self.target_pos)); rot = _quat_angle_deg(d.xquat[self._obj], self.target_quat)
            return {"success": bool(err < PICK_POS_TOL and rot < PICK_ROT_TOL_DEG), "box_to_target_m": round(err, 4), "rot_err_deg": round(rot, 2),
                    "box_z": round(float(p[2]), 4), "time_s": round(self.steps * CONTROL_DT, 3)}
        err = float(abs(p[0] - self.target_pos[0]))
        return {"success": bool(err < CABINET_TOL), "handle_x": round(float(p[0]), 4), "handle_to_target_m": round(err, 4), "time_s": round(self.steps * CONTROL_DT, 3)}

    def state(self) -> dict[str, Any]:
        d = self.data
        return {"qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "targets": self.targets.copy(), "gripper_pos": d.site_xpos[self._gripper].copy(),
                "gripper_mat": d.site_xmat[self._gripper].reshape(3, 3).copy(), "object_pos": d.xpos[self._obj].copy(),
                "object_quat_wxyz": d.xquat[self._obj].copy(), "target_pos": self.target_pos.copy(), "target_quat_wxyz": self.target_quat.copy(), **self.check()}

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    def record_start(self) -> None: self._recording = []

    def record_stop(self) -> np.ndarray:
        a = np.array(self._recording or [], dtype=np.float64).reshape(-1, N); self._recording = None
        _slog("record", n_actions=int(len(a)), success=self.check()["success"]); return a

    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=ENVS[self.env]["task"], seed=self.seed,
                 action_layout="8 actuator targets per control step (1/50 s): joint1..joint7 (rad), finger (0..0.04 m)", meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        self.reset(); self._trace = None; A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        if len(A) > MAX_STEPS: raise ValueError(f"trajectory longer than {MAX_STEPS} control steps")
        for row in A: self.step(row)
        r = self.check(); _slog("replay", n_actions=int(len(A)), success=r["success"])
        return {**r, "state_sha": self.state_sha(), "steps": self.steps}

    def render(self, camera: str | None = None, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
            self._renderer = self.mj.Renderer(self.model, size[1], size[0])
        cam = camera if camera else (self.cameras[0] if self.cameras != ["free"] else None)
        if cam in (None, "free"):
            c = self.mj.MjvCamera(); c.lookat[:] = [0.4, 0.0, 0.3]; c.distance = 1.6; c.azimuth = 150; c.elevation = -25
            self._renderer.update_scene(self.data, camera=c)
        else:
            self._renderer.update_scene(self.data, camera=cam)
        return self._renderer.render().copy()

    def render_grid(self, size=(320, 240)) -> np.ndarray:
        views = []
        for az, el in ((150, -25), (210, -25), (90, -60), (180, -5)):
            if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
                self._renderer = self.mj.Renderer(self.model, size[1], size[0])
            c = self.mj.MjvCamera(); c.lookat[:] = [0.45, 0.0, 0.25]; c.distance = 1.5; c.azimuth = az; c.elevation = el
            self._renderer.update_scene(self.data, camera=c); views.append(self._renderer.render().copy())
        return np.concatenate([np.concatenate(views[:2], axis=1), np.concatenate(views[2:], axis=1)], axis=0)

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
            np.savez_compressed(os.path.join(TRACE_DIR, f"{os.getpid()}_{self.resets:05d}.npz"), actions=np.stack(tr), success=self.check()["success"], t_end=time.time())
        except Exception: pass


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"env": s.env, "seed": s.seed, "state_sha": s.state_sha(), **s.check()}))
