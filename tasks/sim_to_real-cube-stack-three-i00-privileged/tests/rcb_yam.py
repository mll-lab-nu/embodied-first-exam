"""rcb_yam — the sim_to_real benchmark's I2RT YAM station in plain MuJoCo, for robot_coding_bench.

Robot = I2RT's bimanual YAM station as built in the lab: two YAM arms with `linear_4310` grippers and wrist-mounted
Intel RealSense D405 cameras, mounted 0.61 m apart on the table top (z = 0), both facing +x, plus a third D405 on the
gantry above and behind them. Arm model = MuJoCo Menagerie's `i2rt_yam/yam_linear_4310.xml` (MIT, @f054586, derived
from I2RT's SDK v1.3.6 with the SDK's PD gains and gravity compensation); station extrinsics = I2RT's
`robot_models/station/yam_station_linear_4310_d405` (MIT). World frame = the left arm's base frame: +x forward, +y to
the left, +z up, metres; the right arm's base is at (0, -0.61, 0).

Physics 500 Hz (Menagerie's timestep 0.002, implicitfast), control 50 Hz (10 substeps). Each control step takes 14
position targets: per arm (`left/`, `right/`) joint1..joint6 (rad) and `gripper` (finger rail travel, m: 0 = closed,
0.0475 = fully open, down to -0.005 to squeeze). The targets the robot follows are rate limited the way the real
station's command filter is (MAX_JOINT_SPEED for the joints, MAX_GRIPPER_SPEED for the gripper): `step()` moves each
target at most that far towards the command, and records what it applied, so every recorded trajectory can be sent to
the physical robot unchanged.

Families (the instance's "family" picks one; object poses come from the instance file):
  cube_stack_three   three 4 cm cubes (blue, green, red) on the table in front of the left arm. Success at the end of the
                     trajectory: blue on the table, green on blue, red on green (each centred within 2 cm of the one
                     below, at the stacking height within 1 cm), all three at rest and touched by neither gripper.
  handover_to_bin    a 4 x 4 x 10 cm block stands on the table at the left arm's outer side (beyond the right arm's
                     reach); an open bin is fixed to the table at the right arm's outer side (beyond the left arm's
                     reach). Success at the end: the block is in the bin (centre within the inner walls and less than
                     one half-length above the rim, i.e. standing or lying on the bin floor), at rest and touched by
                     neither gripper.
In both, the trajectory fails if the two arms ever touch each other (a safety rule of the physical station).
trajectory = (T, 14) applied targets, one row per control step, T <= MAX_STEPS.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


def _pick_gl() -> None:
    """Rendering backend: EGL (GPU) if it works here, else OSMesa (CPU). Checked once per process, before mujoco is
    imported; an explicit RCB_MUJOCO_GL wins. Physics never depends on it."""
    if os.environ.get("RCB_MUJOCO_GL"):
        os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = os.environ["RCB_MUJOCO_GL"]
        return
    if os.environ.get("_RCB_GL_CHECKED"):
        return
    import subprocess

    probe = (
        "import mujoco; m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom size=\\'.1\\'/></worldbody></mujoco>'); "
        "d = mujoco.MjData(m); mujoco.mj_forward(m, d); r = mujoco.Renderer(m, 240, 320); r.update_scene(d); r.render(); r.render()"
    )
    env = {**os.environ, "MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"}
    try:
        ok = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, timeout=60).returncode == 0
    except Exception:
        ok = False
    gl = "egl" if ok else "osmesa"
    os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = gl
    os.environ["_RCB_GL_CHECKED"] = gl


_pick_gl()

YAM_XML = Path(os.environ.get("RCB_YAM_ROOT", "/opt/eai_s2r/menagerie/i2rt_yam")) / "yam_linear_4310.xml"
SIM_DT = 0.002
CONTROL_DT = 0.02
SUBSTEPS = 10
MAX_STEPS = 3000  # 60 s of control
MAX_JOINT_SPEED = 3.0  # rad/s, every arm joint
MAX_GRIPPER_SPEED = 0.25  # m/s of finger rail travel
ARM_JOINTS = [f"joint{i}" for i in range(1, 7)]
ACTUATOR_NAMES = [f"{s}/{j}" for s in ("left", "right") for j in (*ARM_JOINTS, "gripper")]
N = len(ACTUATOR_NAMES)  # 14
MAX_DELTA = np.array(([MAX_JOINT_SPEED * CONTROL_DT] * 6 + [MAX_GRIPPER_SPEED * CONTROL_DT]) * 2)
HOME_ARM = np.zeros(6)  # the rest pose the real arms power up in
HOME_GRIPPER = 0.0475  # fully open
RIGHT_BASE = np.array([0.0, -0.61, 0.0])
CAMERAS = ("top_cam", "front_view", "left/wrist_cam", "right/wrist_cam")
REST_SPEED = 0.05  # m/s: "at rest"

# I2RT station: left_base -> top_camera (optical frame, +z along the optical axis), full precision from the URDF.
TOP_CAM_POS = "-0.16649488039785276 -0.3050000004052651 0.9543205295851617"
TOP_CAM_QUAT = "0.18301153618854285 -0.6830116697534223 0.683014178599981 -0.1830122084286862"
D405 = 'focal="1.93e-3 1.93e-3" resolution="1280 720" sensorsize="3896e-6 2140e-6"'

CUBE_HALF = 0.02
CUBES = {"cube_blue": "0.12 0.3 0.85 1", "cube_green": "0.15 0.65 0.25 1", "cube_red": "0.85 0.15 0.12 1"}
STACK_XY_TOL = 0.02
STACK_Z_TOL = 0.01
BLOCK_HALF = (0.02, 0.02, 0.05)
BIN_INNER_HALF = 0.08  # 16 x 16 cm inside
BIN_WALL = 0.01
BIN_HEIGHT = 0.06

# Written under Harbor's agent-log mount (/logs/agent, collected even if the agent tidies /app/output) when it exists.
_LOGDIR = "/logs/agent/rcb" if os.path.isdir("/logs/agent") else "/app/output"
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", f"{_LOGDIR}/rcb_session_log.jsonl")
TRACE_DIR = os.environ.get("RCB_AGENT_TRACE_DIR", f"{_LOGDIR}/rcb_trace")
TRACE_MAX_FILES = 300
TRACE_MAX_BYTES = 400 * 1024 * 1024


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n")
    except OSError:
        pass


def _quat_z(yaw: float) -> str:
    return f"{np.cos(yaw / 2):.12g} 0 0 {np.sin(yaw / 2):.12g}"


def _objects_xml(inst: dict) -> str:
    fam, obj = inst["family"], inst["objects"]
    out = []
    if fam == "cube_stack_three":
        for name, rgba in CUBES.items():
            x, y = obj[name]["xy"]
            out.append(
                f'<body name="{name}" pos="{x!r} {y!r} {CUBE_HALF}" quat="{_quat_z(obj[name]["yaw"])}"><freejoint name="{name}"/>'
                f'<geom name="{name}" type="box" size="{CUBE_HALF} {CUBE_HALF} {CUBE_HALF}" mass="0.04" rgba="{rgba}" '
                f'friction="0.8 0.005 0.0001"/></body>'
            )
    elif fam == "handover_to_bin":
        x, y = obj["block"]["xy"]
        hx, hy, hz = BLOCK_HALF
        out.append(
            f'<body name="block" pos="{x!r} {y!r} {hz}" quat="{_quat_z(obj["block"]["yaw"])}"><freejoint name="block"/>'
            f'<geom name="block" type="box" size="{hx} {hy} {hz}" mass="0.08" rgba="0.95 0.6 0.1 1" friction="0.8 0.005 0.0001"/></body>'
        )
        x, y = obj["bin"]["xy"]
        a, w, h = BIN_INNER_HALF, BIN_WALL, BIN_HEIGHT
        walls = [(0, 0, w / 2, a + w, a + w, w / 2)]  # floor
        walls += [(sx * (a + w / 2), 0, h / 2, w / 2, a + w, h / 2) for sx in (-1, 1)]
        walls += [(0, sy * (a + w / 2), h / 2, a, w / 2, h / 2) for sy in (-1, 1)]
        geoms = "".join(
            f'<geom name="bin_{i}" type="box" pos="{px} {py} {pz}" size="{sx} {sy} {sz}" rgba="0.35 0.4 0.45 1"/>'
            for i, (px, py, pz, sx, sy, sz) in enumerate(walls)
        )
        out.append(
            f'<body name="bin" pos="{x!r} {y!r} 0" quat="{_quat_z(obj["bin"]["yaw"])}">{geoms}<site name="bin_center" pos="0 0 {w}"/></body>'
        )
    else:
        raise ValueError(f"unknown family {fam!r}")
    return "\n    ".join(out)


def scene_xml(inst: dict, yam_xml: str | Path = YAM_XML) -> str:
    """The MJCF of the station with the instance's objects."""
    return f"""<mujoco model="sim_to_real_yam_station">
  <compiler angle="radian"/>
  <option timestep="{SIM_DT}" integrator="implicitfast"/>
  <visual><headlight diffuse="0.45 0.45 0.45" ambient="0.35 0.35 0.35" specular="0 0 0"/><global offwidth="1280" offheight="720"/></visual>
  <asset>
    <model name="yam" file="{yam_xml}"/>
    <texture name="tabletop" type="2d" builtin="checker" rgb1="0.78 0.72 0.62" rgb2="0.74 0.68 0.58" width="512" height="512"/>
    <material name="tabletop" texture="tabletop" texrepeat="6 8" reflectance="0.05"/>
  </asset>
  <worldbody>
    <light name="key" pos="0.3 -0.3 1.6" dir="0 0 -1" directional="true" diffuse="0.6 0.6 0.6"/>
    <geom name="table" type="box" pos="0.25 -0.305 -0.02" size="0.55 0.75 0.02" material="tabletop"/>
    <frame name="left_mount"><attach model="yam" body="arm" prefix="left/"/></frame>
    <frame name="right_mount" pos="{RIGHT_BASE[0]} {RIGHT_BASE[1]} {RIGHT_BASE[2]}"><attach model="yam" body="arm" prefix="right/"/></frame>
    <body name="top_camera" pos="{TOP_CAM_POS}" quat="{TOP_CAM_QUAT}"><camera name="top_cam" quat="0 1 0 0" {D405}/></body>
    <camera name="front_view" pos="1.15 -0.305 0.75" xyaxes="0 1 0 -0.55 0 0.84" fovy="58"/>
    {_objects_xml(inst)}
  </worldbody>
</mujoco>"""


def load_model(inst: dict):
    import mujoco

    return mujoco.MjModel.from_xml_string(scene_xml(inst))


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco

        self.mj = mujoco
        self.inst = json.load(open(instance))
        self.family = self.inst["family"]
        self.seed = int(self.inst["seed"])
        self.model = load_model(self.inst)
        self.data = mujoco.MjData(self.model)
        m = self.model
        self._act = np.array([m.actuator(n).id for n in ACTUATOR_NAMES])
        self.lower = m.actuator_ctrlrange[self._act, 0].copy()
        self.upper = m.actuator_ctrlrange[self._act, 1].copy()
        self._qadr = {
            f"{s}/{j}": m.jnt_qposadr[m.joint(f"{s}/{j}").id]
            for s in ("left", "right")
            for j in (*ARM_JOINTS, "left_finger", "right_finger")
        }
        self._side = {}  # robot geom id -> "left" / "right"
        for g in range(m.ngeom):
            b = m.body(m.geom_bodyid[g]).name
            if b.startswith(("left/", "right/")):
                self._side[g] = b.split("/")[0]
        self.objects = list(CUBES) if self.family == "cube_stack_three" else ["block"]
        self._obj_body = {o: m.body(o).id for o in self.objects}
        self._obj_geom = {m.geom(o).id: o for o in self.objects}
        self._obj_q = {o: m.jnt_qposadr[m.body_jntadr[self._obj_body[o]]] for o in self.objects}
        self._obj_v = {o: m.jnt_dofadr[m.body_jntadr[self._obj_body[o]]] for o in self.objects}
        if self.family == "handover_to_bin":
            self._bin = m.body("bin").id
        self._renderer = None
        self.enable_render = enable_render
        self._recording: list | None = None
        self._trace: list | None = None
        self.resets = 0
        self.total_steps = 0
        _slog("session_start", family=self.family, seed=self.seed)
        import atexit

        atexit.register(
            lambda: (
                self._trace_dump(),
                _slog("session_end", resets=self.resets, sim_steps=self.total_steps * SUBSTEPS),
            )
        )
        self.reset()
        exp = self.inst.get("state_sha")
        if exp and self.state_sha() != exp:
            raise RuntimeError(f"initial state hash {self.state_sha()} != instance {exp}")

    # ---------------------------------------------------------------- simulation
    def reset(self) -> None:
        self._trace_dump()
        m, d = self.model, self.data
        self.mj.mj_resetData(m, d)
        for s in ("left", "right"):
            for j, v in zip(ARM_JOINTS, HOME_ARM):
                d.qpos[self._qadr[f"{s}/{j}"]] = v
            d.qpos[self._qadr[f"{s}/left_finger"]] = d.qpos[self._qadr[f"{s}/right_finger"]] = HOME_GRIPPER
        d.ctrl[self._act] = np.tile(np.r_[HOME_ARM, HOME_GRIPPER], 2)
        self.mj.mj_forward(m, d)
        self.targets = d.ctrl[self._act].copy()
        self.steps = 0
        self.arm_collision = False
        self.resets += 1
        self._recording = self._recording if self._recording is None else []
        self._trace = [] if TRACE_DIR else None
        _slog("reset", n=self.resets)

    def step(self, targets) -> dict[str, Any]:
        """One control step (1/50 s) towards `targets` (14,): clipped to the limits, then rate limited."""
        cmd = np.asarray(targets, dtype=np.float64).reshape(N)
        if not np.all(np.isfinite(cmd)):
            raise ValueError("targets contain NaN/inf")
        cmd = np.clip(cmd, self.lower, self.upper)
        tg = self.targets + np.clip(cmd - self.targets, -MAX_DELTA, MAX_DELTA)
        self.targets = tg
        self.data.ctrl[self._act] = tg
        for _ in range(SUBSTEPS):
            self.mj.mj_step(self.model, self.data)
            self.arm_collision |= self._arms_touch()
        self.steps += 1
        self.total_steps += 1
        if self._recording is not None:
            self._recording.append(tg.copy())
        if self._trace is not None:
            self._trace.append(tg.astype(np.float32))
        return self.check()

    def _arms_touch(self) -> bool:
        d = self.data
        for c in d.contact[: d.ncon]:
            a, b = self._side.get(c.geom1), self._side.get(c.geom2)
            if a and b and a != b:
                return True
        return False

    def _gripper_contacts(self) -> set[str]:
        """Objects touched by any robot geom right now."""
        d, out = self.data, set()
        for c in d.contact[: d.ncon]:
            for g, o in ((c.geom1, c.geom2), (c.geom2, c.geom1)):
                if g in self._side and o in self._obj_geom:
                    out.add(self._obj_geom[o])
        return out

    def _obj_speed(self, o: str) -> float:
        a = self._obj_v[o]
        return float(np.linalg.norm(self.data.qvel[a : a + 3]))

    # ------------------------------------------------------------------- success
    def check(self) -> dict[str, Any]:
        d = self.data
        touched = self._gripper_contacts()
        rest = all(self._obj_speed(o) < REST_SPEED for o in self.objects)
        out: dict[str, Any] = {}
        if self.family == "cube_stack_three":
            p = {o: d.xpos[self._obj_body[o]] for o in self.objects}
            b, g, r = p["cube_blue"], p["cube_green"], p["cube_red"]
            on_table = abs(b[2] - CUBE_HALF) < STACK_Z_TOL
            gb = bool(np.linalg.norm(g[:2] - b[:2]) < STACK_XY_TOL and abs(g[2] - b[2] - 2 * CUBE_HALF) < STACK_Z_TOL)
            rg = bool(np.linalg.norm(r[:2] - g[:2]) < STACK_XY_TOL and abs(r[2] - g[2] - 2 * CUBE_HALF) < STACK_Z_TOL)
            goal = bool(on_table and gb and rg)
            out = {"blue_on_table": bool(on_table), "green_on_blue": gb, "red_on_green": rg}
        else:
            blk = d.xpos[self._obj_body["block"]]
            rel = d.xmat[self._bin].reshape(3, 3).T @ (blk - d.xpos[self._bin])
            # centre inside the inner walls, and low enough that the block reaches below the rim (standing or lying)
            inside = bool(np.all(np.abs(rel[:2]) < BIN_INNER_HALF) and BIN_WALL < rel[2] < BIN_HEIGHT + BLOCK_HALF[2])
            goal = inside
            out = {"block_in_bin": inside, "block_z": round(float(blk[2]), 4)}
        ok = bool(goal and rest and not touched and not self.arm_collision)
        return {
            "success": ok,
            **out,
            "at_rest": bool(rest),
            "gripper_touches_object": bool(touched),
            "arm_collision": bool(self.arm_collision),
            "time_s": round(self.steps * CONTROL_DT, 3),
        }

    # --------------------------------------------------------------------- state
    def state(self) -> dict[str, Any]:
        d, m = self.data, self.model
        q = {n: float(d.qpos[a]) for n, a in self._qadr.items()}
        sites = {n: d.site_xpos[m.site(n).id].copy() for n in ("left/grasp_site", "right/grasp_site")}
        site_mats = {n: d.site_xmat[m.site(n).id].reshape(3, 3).copy() for n in ("left/grasp_site", "right/grasp_site")}
        objs = {
            o: {"pos": d.xpos[self._obj_body[o]].copy(), "quat_wxyz": d.xquat[self._obj_body[o]].copy()}
            for o in self.objects
        }
        out = {
            "qpos": d.qpos.copy(),
            "qvel": d.qvel.copy(),
            "joints": q,
            "targets": self.targets.copy(),
            "sites": sites,
            "site_mats": site_mats,
            "objects": objs,
        }
        if self.family == "handover_to_bin":
            out["bin"] = {"pos": d.xpos[self._bin].copy(), "quat_wxyz": d.xquat[self._bin].copy()}
        return {**out, **self.check()}

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    # ------------------------------------------------------- record and replay
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        a = np.array(self._recording or [], dtype=np.float64).reshape(-1, N)
        self._recording = None
        _slog("record", n_actions=int(len(a)), success=self.check()["success"])
        return a

    def save_trajectory(
        self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None
    ) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            actions=np.asarray(actions, dtype=np.float64),
            family=self.family,
            seed=self.seed,
            action_layout="14 applied position targets per control step (1/50 s): " + ",".join(ACTUATOR_NAMES),
            meta=json.dumps(meta or {}),
        )

    def replay(self, actions) -> dict[str, Any]:
        """Fresh replay from the start (what the verifier does): every row must already respect the rate limit."""
        self.reset()
        self._trace = None
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N:
            raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        if len(A) > MAX_STEPS:
            raise ValueError(f"trajectory longer than {MAX_STEPS} control steps")
        speed_ok = trajectory_respects_limits(A, self.lower, self.upper)
        for row in A:
            self.step(row)
        r = self.check()
        _slog("replay", n_actions=int(len(A)), success=r["success"])
        return {
            **r,
            "success": bool(r["success"] and speed_ok),
            "limits_ok": bool(speed_ok),
            "state_sha": self.state_sha(),
            "steps": self.steps,
        }

    # ----------------------------------------------------------------- cameras
    def render(self, camera: str = "top_cam", size: tuple[int, int] = (424, 240)) -> np.ndarray:
        """RGB (H, W, 3) uint8. The D405 cameras (top_cam, left/wrist_cam, right/wrist_cam) have 16:9 intrinsics."""
        if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
            self._renderer = self.mj.Renderer(self.model, size[1], size[0])
        self._renderer.update_scene(self.data, camera=camera)
        return self._renderer.render().copy()

    def render_grid(self, cameras=CAMERAS, size=(424, 240)) -> np.ndarray:
        tiles = [self.render(c, size) for c in cameras]
        while len(tiles) % 2:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i : i + 2], axis=1) for i in range(0, len(tiles), 2)], axis=0)

    def render_video(self, actions, path: str | Path, every: int = 2, fps: int = 25) -> dict[str, Any]:
        import imageio.v2 as imageio

        self.reset()
        self._trace = None
        frames = [self.render_grid()]
        for i, row in enumerate(np.asarray(actions, dtype=np.float64)):
            self.step(row)
            if (i + 1) % every == 0:
                frames.append(self.render_grid())
        frames.append(self.render_grid())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), frames[-1])
        return {**self.check(), "n_frames": len(frames), "video": str(path)}

    def _trace_dump(self) -> None:
        tr = self._trace
        self._trace = None
        if not tr or not TRACE_DIR:
            return
        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            ents = [e for e in os.scandir(TRACE_DIR) if e.name.endswith(".npz")]
            if len(ents) >= TRACE_MAX_FILES or sum(e.stat().st_size for e in ents) >= TRACE_MAX_BYTES:
                return
            np.savez_compressed(
                os.path.join(TRACE_DIR, f"{os.getpid()}_{self.resets:05d}.npz"),
                actions=np.stack(tr),
                success=self.check()["success"],
                t_end=time.time(),
            )
        except Exception:
            pass


def trajectory_respects_limits(A, lower, upper) -> bool:
    """Every row within the actuator limits and within MAX_DELTA of the previous row (the first: of the home targets)."""
    A = np.asarray(A, dtype=np.float64)
    if len(A) == 0:
        return True
    prev = np.vstack([np.tile(np.r_[HOME_ARM, HOME_GRIPPER], 2)[None], A[:-1]])
    within = np.all(A >= lower - 1e-9) and np.all(A <= upper + 1e-9)
    return bool(within and np.all(np.abs(A - prev) <= MAX_DELTA + 1e-9))


def make_instance(family: str, seed: int) -> dict:
    """Draw a frozen instance (object poses) for `family` from `seed`."""
    rng = np.random.default_rng(seed)
    if family == "cube_stack_three":
        while True:
            xy = np.c_[rng.uniform(0.22, 0.36, 3), rng.uniform(-0.20, 0.12, 3)]
            if min(np.linalg.norm(xy[i] - xy[j]) for i in range(3) for j in range(i)) > 0.09:
                break
        objs = {
            name: {
                "xy": [round(float(v), 4) for v in xy[i]],
                "yaw": round(float(rng.uniform(-np.pi / 4, np.pi / 4)), 4),
            }
            for i, name in enumerate(CUBES)
        }
    elif family == "handover_to_bin":
        objs = {
            "block": {
                "xy": [round(float(rng.uniform(0.26, 0.34)), 4), round(float(rng.uniform(0.17, 0.23)), 4)],
                "yaw": round(float(rng.uniform(-0.5, 0.5)), 4),
            },
            "bin": {
                "xy": [round(float(rng.uniform(0.28, 0.34)), 4), round(float(rng.uniform(-0.84, -0.79)), 4)],
                "yaw": round(float(rng.uniform(-0.2, 0.2)), 4),
            },
        }
    else:
        raise ValueError(family)
    return {"benchmark": "sim_to_real", "family": family, "seed": seed, "objects": objs}


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"family": s.family, "seed": s.seed, "state_sha": s.state_sha(), **s.check()}))
