"""rcb_dtb — DexToolBench (SimToolReal) tasks in plain MuJoCo for robot_coding_bench.

Scene = SimToolReal's MuJoCo sim2sim scene (github.com/tylerlum/simtoolreal, MIT, deployment/mujoco/mujoco_sim.py),
rebuilt here without its training stack: KUKA iiwa 14 (MuJoCo Menagerie) + left Sharpa HA4 hand attached at the iiwa
flange, a 0.475 x 0.4 x 0.3 m table (top at z = 0.53 m), the tool (convex-decomposed meshes) and a green goal marker
(no contacts). Physics 600 Hz (implicitfast, elliptic cones, multi-CCD, gravity-compensated robot), control 60 Hz.

A task = one DexToolBench demo: a tool start pose and a sequence of goal poses (world frame). The benchmark's rule:
the current goal counts as reached when all 8 keypoints of the tool's grasp box (0.141 x 0.03025 x 0.0271 m, scaled
by 1.5) are within 1.5 cm of the same keypoints at the goal pose; then the next goal becomes current. Each goal has
10 s (600 control steps); a goal not reached in time ends the attempt. progress = goals reached / number of goals.

trajectory = (T, 29) joint position targets, one row per control step (1/60 s), each held for 10 physics steps:
7 iiwa joints then the 22 Sharpa joints (names: JOINT_NAMES). Replaying it from the frozen start state is bit-exact.
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
SIM_DT = 1.0 / 600.0
CONTROL_DT = 1.0 / 60.0
SUBSTEPS = int(round(CONTROL_DT / SIM_DT))          # 10
# Per-goal time limit. DexToolBench's own eval gives each goal 10 s; ours (owner 2026-09-29): 30 s in privileged mode (the
# default here: the trajectory is replayed offline and the agent can reset freely), none in standard mode (the service
# sets RCB_DTB_GOAL_TIMEOUT_S=0: one episode, no reset). 0 = no per-goal limit.
GOAL_TIMEOUT_STEPS = int(round(float(os.environ.get("RCB_DTB_GOAL_TIMEOUT_S", "30")) / (1.0 / 60.0)))
SUCCESS_TOL_M = 0.01 * 1.5                            # eval_success_tolerance * keypoint_scale
KEYPOINT_HALF = 0.5 * 1.5 * np.array([0.141, 0.03025, 0.0271])
CORNERS = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=np.float64) * KEYPOINT_HALF

IIWA_INIT = np.array([-1.571, 1.571, -0.000, 1.376, -0.000, 1.485, 1.308])
IIWA_JOINTS = [f"joint{i}" for i in range(1, 8)]
IIWA_ACTS = [f"actuator{i}" for i in range(1, 8)]
_F = ["thumb_CMC_FE", "thumb_CMC_AA", "thumb_MCP_FE", "thumb_MCP_AA", "thumb_IP", "index_MCP_FE", "index_MCP_AA", "index_PIP", "index_DIP",
      "middle_MCP_FE", "middle_MCP_AA", "middle_PIP", "middle_DIP", "ring_MCP_FE", "ring_MCP_AA", "ring_PIP", "ring_DIP",
      "pinky_CMC", "pinky_MCP_FE", "pinky_MCP_AA", "pinky_PIP", "pinky_DIP"]
HAND_JOINTS = [f"palmleft_{n}" for n in _F]
HAND_ACTS = [f"palmleft_{n}_ctrl" for n in _F]
JOINT_NAMES = IIWA_JOINTS + HAND_JOINTS
ACTUATOR_NAMES = IIWA_ACTS + HAND_ACTS
N = len(JOINT_NAMES)                                   # 29
INIT_Q = np.concatenate([IIWA_INIT, np.zeros(22)])
CAMERAS = ("front", "side", "top", "oblique")


def _props() -> dict:
    """Table props per tool category, positions relative to the table's centre (SimToolReal's table URDFs, @313d5ae):
    hammer = table_narrow_nail (one 3 x 3 x 6 cm nail), eraser / marker = table_narrow_whiteboard (a 2 x 40 x 40 cm board
    standing at the table's +x edge), spatula = table_narrow_bowl_plate (YCB 024_bowl and 029_plate; their meshes are
    not in the SimToolReal repository, so here a primitive plate and bowl of YCB's size stand in), brush / screwdriver =
    the plain table."""
    import math, mujoco
    B, C = mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_CYLINDER
    grey, white, ceramic = (0.5, 0.5, 0.5, 1), (0.95, 0.95, 0.95, 1), (0.85, 0.85, 0.8, 1)
    board = [{"name": "whiteboard", "type": B, "size": (0.01, 0.2, 0.2), "pos": (0.325, 0.0, 0.35), "rgba": white}]
    bowl = [{"name": "bowl_base", "type": C, "size": (0.045, 0.004), "pos": (-0.15, 0.1, 0.154), "rgba": ceramic}]
    for k in range(12):
        a = 2 * math.pi * k / 12
        bowl.append({"name": f"bowl_wall_{k}", "type": B, "size": (0.004, 0.022, 0.026), "pos": (-0.15 + 0.07 * math.cos(a), 0.1 + 0.07 * math.sin(a), 0.176),
                     "euler": (0.0, 0.35, a), "rgba": ceramic})
    plate = [{"name": "plate", "type": C, "size": (0.13, 0.008), "pos": (0.1, 0.05, 0.158), "rgba": ceramic}]
    return {"hammer": [{"name": "nail", "type": B, "size": (0.015, 0.015, 0.03), "pos": (-0.16, 0.06, 0.175), "rgba": grey}],
            "eraser": board, "marker": board, "spatula": bowl + plate}


PROPS: dict = {}

# Session log (self-reported debugging footprint, like the RoboTwin tooling) and per-rollout traces.
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


def wxyz(p7) -> np.ndarray:
    """(x, y, z, qx, qy, qz, qw) -> quaternion (w, x, y, z)."""
    return np.array([p7[6], p7[3], p7[4], p7[5]], dtype=np.float64)


def _quat_to_mat_wxyz(q) -> np.ndarray:
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def keypoint_distance(obj_pos, obj_quat_wxyz, goal_p7) -> float:
    """Max distance (m) between the 8 grasp-box keypoints at the tool pose and at the goal pose (x y z qx qy qz qw)."""
    a = CORNERS @ _quat_to_mat_wxyz(obj_quat_wxyz).T + np.asarray(obj_pos)
    b = CORNERS @ _quat_to_mat_wxyz(wxyz(goal_p7)).T + np.asarray(goal_p7[:3])
    return float(np.max(np.linalg.norm(a - b, axis=1)))


def _lookat(pos, target, up=(0, 0, 1)):
    f = np.asarray(target, float) - np.asarray(pos, float); f /= np.linalg.norm(f)
    x = np.cross(f, up); x /= np.linalg.norm(x); y = np.cross(x, f)
    return np.concatenate([x, y])


def build_model(category: str, obj: str, start_p7, goal_p7):
    import mujoco
    if not PROPS: PROPS.update(_props())
    spec = mujoco.MjSpec.from_file(str(ROOT / "menagerie/kuka_iiwa_14/scene.xml"))
    spec.option.timestep = SIM_DT
    hand = mujoco.MjSpec.from_file(str(ROOT / "simtoolreal/assets/urdf/left_sharpa_ha4/left_sharpa_ha4_v2_1_offset.xml"))
    next(s for s in spec.sites if s.name == "attachment_site").attach_body(hand.worldbody, "palm", "")
    spec.option.enableflags |= mujoco.mjtEnableBit.mjENBL_MULTICCD
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.iterations = 20; spec.option.ls_iterations = 50
    spec.option.o_solref[:] = np.array([0.02, 1.0]); spec.option.o_solimp[:] = np.array([0.0, 0.95, 0.03, 0.5, 2])
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    for b in spec.bodies: b.gravcomp = 1.0
    base = [b for b in spec.bodies if b.name == "base"]; assert len(base) == 1; base[0].pos = np.array([0.0, 0.8, 0.0])
    fr = np.array([1.0, 0.005, 0.0001])
    t = spec.worldbody.add_body(); t.name = "table"; t.pos = np.array([0.0, 0.0, 0.38])
    g = t.add_geom(); g.name = "table_geom"; g.type = mujoco.mjtGeom.mjGEOM_BOX; g.size = np.array([0.475 / 2, 0.4 / 2, 0.3 / 2])
    g.rgba = np.array([1.0, 1.0, 1.0, 1.0]); g.friction = fr.copy()
    for pr in PROPS.get(category, ()):                  # the category's table props (SimToolReal's table_narrow_*.urdf)
        pg = t.add_geom(); pg.name = pr["name"]; pg.type = pr["type"]; pg.size = np.array((list(pr["size"]) + [0.0, 0.0])[:3], float); pg.pos = np.array(pr["pos"], float)
        if "euler" in pr:
            pg.alt.type = mujoco.mjtOrientation.mjORIENTATION_EULER; pg.alt.euler = np.array(pr["euler"], float)
        pg.rgba = np.array(pr["rgba"], float); pg.friction = fr.copy()
    mesh_dir = ROOT / f"simtoolreal/assets/urdf/dextoolbench/{category}/{obj}/{obj}_collision"
    meshes = sorted(mesh_dir.glob("decomp_*.obj")); assert meshes, f"no collision meshes in {mesh_dir}"
    for name, color, p7, movable, contacts in (("object", (0.5, 0.5, 0.5, 1.0), start_p7, True, True), ("goal_object", (0.0, 1.0, 0.0, 1.0), goal_p7, False, False)):
        body = spec.worldbody.add_body(); body.name = name; body.pos = np.asarray(p7[:3], float); body.quat = wxyz(p7)
        if movable:
            j = body.add_joint(); j.name = f"{name}_free_joint"; j.type = mujoco.mjtJoint.mjJNT_FREE
        for mp in meshes:
            m = spec.add_mesh(); m.name = f"{name}_mesh_{mp.stem}"; m.file = str(mp); m.scale = np.array([1.0, 1.0, 1.0])
            og = body.add_geom(); og.name = f"{name}_object_geom_{mp.stem}"; og.rgba = np.array(color); og.friction = fr.copy()
            og.type = mujoco.mjtGeom.mjGEOM_MESH; og.meshname = m.name
            if not contacts: og.contype = 0; og.conaffinity = 0
    for gg in spec.geoms: gg.condim = 6
    for cname, pos, tgt in (("front", (0.0, -0.95, 0.95), (0.0, 0.1, 0.6)), ("side", (0.95, 0.15, 0.85), (0.0, 0.15, 0.6)),
                            ("top", (0.0, 0.12, 1.65), (0.0, 0.1, 0.55)), ("oblique", (-0.75, -0.6, 1.1), (0.0, 0.1, 0.6))):
        c = spec.worldbody.add_camera(); c.name = cname; c.pos = np.array(pos); c.fovy = 55.0
        c.alt.type = mujoco.mjtOrientation.mjORIENTATION_XYAXES; c.alt.xyaxes = _lookat(pos, tgt)
    model = spec.compile(); model.opt.timestep = SIM_DT
    return model


class Session:
    """One DexToolBench episode in MuJoCo. Privileged mode: the agent may read and even modify s.model / s.data while
    debugging, but only the recorded joint targets are handed in and they are replayed from the frozen start."""

    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco
        self.mj = mujoco
        self.inst = json.load(open(instance)); self.category, self.obj, self.task = self.inst["category"], self.inst["object"], self.inst["task"]
        self.start = list(map(float, self.inst["start_pose"])); self.goals = [list(map(float, g)) for g in self.inst["goals"]]
        self.model = build_model(self.category, self.obj, self.start, self.goals[0])
        self.data = mujoco.MjData(self.model)
        self._jq = np.array([self.model.jnt_qposadr[self.model.joint(n).id] for n in JOINT_NAMES])
        self._jv = np.array([self.model.jnt_dofadr[self.model.joint(n).id] for n in JOINT_NAMES])
        self._act = np.array([self.model.actuator(n).id for n in ACTUATOR_NAMES])
        self._obj = self.model.body("object").id; self._goal = self.model.body("goal_object").id
        self.lower = self.model.actuator_ctrlrange[self._act, 0].copy(); self.upper = self.model.actuator_ctrlrange[self._act, 1].copy()
        self.enable_render = enable_render; self._renderer = None
        self._recording: list | None = None; self._trace: list | None = None; self.resets = 0; self.total_steps = 0
        _slog("session_start", task=f"{self.category}/{self.obj}/{self.task}")
        import atexit
        atexit.register(lambda: (self._trace_dump(), _slog("session_end", resets=self.resets, sim_steps=self.total_steps * SUBSTEPS)))
        self.reset()

    # ---- episode
    def reset(self) -> None:
        self._trace_dump()
        self.mj.mj_resetData(self.model, self.data)
        self.data.qpos[self._jq] = INIT_Q; self.targets = INIT_Q.copy(); self.data.ctrl[self._act] = INIT_Q
        self.goal_index = 0; self.steps_on_goal = 0; self.failed = False; self.steps = 0
        self._set_goal_marker(self.goals[0]); self.mj.mj_forward(self.model, self.data)
        self.resets += 1; self._recording = self._recording if self._recording is None else []
        self._trace = [] if TRACE_DIR else None
        _slog("reset", n=self.resets)

    def _set_goal_marker(self, g) -> None:
        self.model.body_pos[self._goal] = g[:3]; self.model.body_quat[self._goal] = wxyz(g)

    def step(self, targets) -> dict[str, Any]:
        """Hold 29 joint position targets for one control step (10 physics steps), then update the goal tracker."""
        tg = np.clip(np.asarray(targets, dtype=np.float64).reshape(N), self.lower, self.upper)
        if not np.all(np.isfinite(tg)): raise ValueError("targets contain NaN/inf")
        self.targets = tg; self.data.ctrl[self._act] = tg
        for _ in range(SUBSTEPS): self.mj.mj_step(self.model, self.data)
        self.steps += 1; self.total_steps += 1
        if self._recording is not None: self._recording.append(tg.copy())
        if self._trace is not None: self._trace.append(tg.astype(np.float32))
        return self._track()

    def _track(self) -> dict[str, Any]:
        if self.goal_index < len(self.goals) and not self.failed:
            self.steps_on_goal += 1
            if self.goal_distance() < SUCCESS_TOL_M:
                self.goal_index += 1; self.steps_on_goal = 0
                if self.goal_index < len(self.goals): self._set_goal_marker(self.goals[self.goal_index]); self.mj.mj_forward(self.model, self.data)
            elif GOAL_TIMEOUT_STEPS and self.steps_on_goal >= GOAL_TIMEOUT_STEPS:
                self.failed = True
        return self.progress()

    def goal_distance(self, k: int | None = None) -> float:
        k = self.goal_index if k is None else k
        return keypoint_distance(self.data.xpos[self._obj], self.data.xquat[self._obj], self.goals[min(k, len(self.goals) - 1)])

    def progress(self) -> dict[str, Any]:
        n = len(self.goals); done = self.goal_index >= n
        return {"reached": self.goal_index, "n_goals": n, "progress": self.goal_index / n, "done": done, "failed": self.failed,
                "steps_on_goal": self.steps_on_goal, "steps_left_on_goal": None if done or self.failed or not GOAL_TIMEOUT_STEPS else GOAL_TIMEOUT_STEPS - self.steps_on_goal,
                "goal_distance_m": None if done else round(self.goal_distance(), 5)}

    # ---- state (privileged-mode state)
    def state(self) -> dict[str, Any]:
        d = self.data
        return {"q": d.qpos[self._jq].copy(), "qd": d.qvel[self._jv].copy(), "targets": self.targets.copy(),
                "object_pos": d.xpos[self._obj].copy(), "object_quat_wxyz": d.xquat[self._obj].copy(),
                "goal_index": self.goal_index, "goal": None if self.goal_index >= len(self.goals) else list(self.goals[self.goal_index]),
                "palm_pos": d.xpos[self.model.body("palmworld").id].copy() if self._has_body("palmworld") else None, "time_s": self.steps * CONTROL_DT}

    def _has_body(self, name: str) -> bool:
        try: self.model.body(name); return True
        except Exception: return False

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    # ---- recording / replay
    def record_start(self) -> None: self._recording = []

    def record_stop(self) -> np.ndarray:
        a = np.array(self._recording or [], dtype=np.float64).reshape(-1, N); self._recording = None
        _slog("record", n_actions=int(len(a)), progress=self.progress()["progress"]); return a

    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), category=self.category, object=self.obj, task=self.task,
                 action_layout="29 joint position targets per control step (1/60 s): " + ",".join(JOINT_NAMES), meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        self.reset(); self._trace = None
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N: raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        for row in A:
            p = self.step(row)
            if p["done"] or p["failed"]: break
        _slog("replay", n_actions=int(len(A)), progress=self.progress()["progress"])
        return {**self.progress(), "state_sha": self.state_sha(), "steps": self.steps}

    # ---- rendering
    def render(self, camera: str = "front", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
            self._renderer = self.mj.Renderer(self.model, size[1], size[0])
        self._renderer.update_scene(self.data, camera=camera); return self._renderer.render().copy()

    def render_grid(self, cameras=CAMERAS, size=(320, 240)) -> np.ndarray:
        tiles = [self.render(c, size) for c in cameras]
        while len(tiles) % 2: tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + 2], axis=1) for i in range(0, len(tiles), 2)], axis=0)

    def render_video(self, actions, path: str | Path, every: int = 2, fps: int = 30) -> dict[str, Any]:
        import imageio.v2 as imageio
        self.reset(); self._trace = None; frames = [self.render_grid()]
        for i, row in enumerate(np.asarray(actions, dtype=np.float64)):
            p = self.step(row)
            if (i + 1) % every == 0 or p["done"] or p["failed"]: frames.append(self.render_grid())
            if p["done"] or p["failed"]: break
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames: w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), frames[-1])
        return {**self.progress(), "n_frames": len(frames), "video": str(path)}

    # ---- agent traces (self-reported, reconstructed by the verifier)
    def _trace_dump(self) -> None:
        tr = self._trace; self._trace = None
        if not tr or not TRACE_DIR: return
        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            ents = [e for e in os.scandir(TRACE_DIR) if e.name.endswith(".npz")]
            if len(ents) >= TRACE_MAX_FILES or sum(e.stat().st_size for e in ents) >= TRACE_MAX_BYTES: return
            np.savez_compressed(os.path.join(TRACE_DIR, f"{os.getpid()}_{self.resets:05d}.npz"), actions=np.stack(tr),
                                reached=self.goal_index, t_end=time.time())
        except Exception: pass


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"task": f"{s.category}/{s.obj}/{s.task}", "n_goals": len(s.goals), "state_sha": s.state_sha(), **s.progress()}))
