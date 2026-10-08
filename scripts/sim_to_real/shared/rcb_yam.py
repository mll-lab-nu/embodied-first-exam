"""rcb_yam — the sim_to_real benchmark's I2RT YAM station in plain MuJoCo, for robot_coding_bench.

Robot = I2RT's bimanual YAM station: two YAM arms with `linear_4310` grippers and wrist-mounted Intel RealSense D405
cameras, mounted 0.61 m apart on the table top (z = 0), both facing +x, plus a third D405 on the gantry above and behind
them. Arm model = MuJoCo Menagerie's `i2rt_yam/yam_linear_4310.xml` (MIT, @f054586, derived from I2RT's SDK v1.3.6 with
the SDK's PD gains and gravity compensation); station extrinsics = I2RT's `yam_station_linear_4310_d405` (MIT). World
frame = the left arm's base frame: +x forward, +y to the left, +z up, metres; the right arm's base is at (0, -0.61, 0).

Scene = assets converted from NVIDIA RoboLab's library (images/sim_to_real, scripts/sim_to_real/assets): scanned YCB
objects with their textures, convex collision hulls and the YCB set's measured masses, RoboLab's fruit models and grey
tote, an oak tabletop and an indoor HDRI room. Physics 500 Hz (implicitfast, elliptic cones), control 50 Hz (10
substeps). Each control step takes 14 position targets: per arm (`left/`, `right/`) joint1..joint6 (rad) and `gripper`
(finger rail travel, m: 0 = closed, 0.0475 = fully open, down to -0.005 to squeeze). The applied targets are rate
limited (MAX_JOINT_SPEED, MAX_GRIPPER_SPEED): `step()` moves each target at most that far towards the command and
records what it applied, so a recorded trajectory can be sent to the physical robot unchanged.

Families (the instance's "family" picks one; the instance holds every object's settled start pose):
  fruits_in_bowl  left arm, cluttered table: a bowl, a banana, a lemon, an orange, a mug and a tomato soup can. Put the
                  banana and the lemon into the bowl.
  pack_tote       both arms: RoboLab's grey tote between the arms; a tomato soup can and a foam brick on the left arm's
                  outer side, a potted meat can and a marker on the right arm's. Put all four into the tote.
Success, both: at the end of the trajectory every goal object is in its container (RoboLab's `object_in_container`: the
object's centroid in the container's local bounding box with one container height of open-top slack, and in contact
with the container), the container is upright,
every object is at rest and touched by neither robot, and the two arms never touched each other.
trajectory = (T, 14) applied targets, one row per control step, T <= MAX_STEPS.
"""

from __future__ import annotations

import functools
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
ASSETS = Path(os.environ.get("RCB_S2R_ASSETS", "/opt/eai_s2r/assets"))
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
UPRIGHT_COS = np.cos(np.radians(20))  # a container counts as upright within 20 degrees

# I2RT station: left_base -> top_camera (optical frame, +z along the optical axis), full precision from the URDF.
TOP_CAM_POS = "-0.16649488039785276 -0.3050000004052651 0.9543205295851617"
TOP_CAM_QUAT = "0.18301153618854285 -0.6830116697534223 0.683014178599981 -0.1830122084286862"
D405 = 'focal="1.93e-3 1.93e-3" resolution="1280 720" sensorsize="3896e-6 2140e-6"'

ROUND = {"lemon", "orange"}  # rolling friction for the round fruits
FAMILIES = {
    "fruits_in_bowl": {
        "objects": ["bowl", "banana", "lemon", "orange", "mug", "tomato_soup_can"],
        "container": "bowl",
        "goal": ["banana", "lemon"],
    },
    "pack_tote": {
        "objects": ["tote", "tomato_soup_can", "foam_brick", "spam_can", "marker"],
        "container": "tote",
        "goal": ["tomato_soup_can", "foam_brick", "spam_can", "marker"],
    },
}
TOTE_WALL = 0.008
TOTE_MASS = 0.6

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


@functools.lru_cache(maxsize=None)
def asset_meta(name: str) -> dict:
    sub = "fixtures" if name == "tote" else "objects"
    return json.loads((ASSETS / sub / name / "meta.json").read_text())


def _object_xml(name: str, pose: dict) -> tuple[str, str]:
    """(<asset> entries, <body>) for one object. The body frame is the asset's mesh frame; pose = settled start pose."""
    if name == "tote":
        return _tote_xml(pose)
    d = ASSETS / "objects" / name
    meta = asset_meta(name)
    cols = sorted(d.glob("col_*.obj"))
    dens = meta["mass"] / meta["hull_volume"]
    a = [f'<mesh name="{name}_vis" file="{d}/visual.obj"/>']
    mat = ""
    if meta["texture"]:
        a += [
            f'<texture name="{name}_tex" type="2d" file="{d}/texture.png"/>',
            f'<material name="{name}_mat" texture="{name}_tex" specular="0.25" shininess="0.3"/>',
        ]
        mat = f' material="{name}_mat"'
    a += [f'<mesh name="{name}_c{i}" file="{c}"/>' for i, c in enumerate(cols)]
    fr = 'condim="6" friction="0.9 0.005 0.0005"' if name in ROUND else 'condim="4" friction="0.9 0.005 0.0001"'
    g = [f'<geom name="{name}" type="mesh" mesh="{name}_vis"{mat} contype="0" conaffinity="0" group="2" density="0"/>']
    g += [
        f'<geom name="{name}_c{i}" type="mesh" mesh="{name}_c{i}" group="3" density="{dens:.6g}" {fr} rgba="0.8 0.3 0.3 0.4"/>'
        for i in range(len(cols))
    ]
    p, q = pose["pos"], pose["quat"]
    body = (
        f'<body name="{name}" pos="{p[0]!r} {p[1]!r} {p[2]!r}" quat="{q[0]!r} {q[1]!r} {q[2]!r} {q[3]!r}">'
        f'<freejoint name="{name}"/>{"".join(g)}</body>'
    )
    return "\n    ".join(a), body


def _tote_xml(pose: dict) -> tuple[str, str]:
    """RoboLab's grey tote (Tote_B09, 42 x 28 x 10.5 cm): its mesh for rendering, box walls for collision."""
    d = ASSETS / "fixtures" / "tote"
    meta = asset_meta("tote")
    (x0, y0, _), (x1, y1, z1) = meta["bbox_min"], meta["bbox_max"]
    hx, hy, w = (x1 - x0) / 2, (y1 - y0) / 2, TOTE_WALL
    boxes = [(0, 0, w / 2, hx, hy, w / 2)]
    boxes += [(sx * (hx - w / 2), 0, z1 / 2, w / 2, hy, z1 / 2) for sx in (-1, 1)]
    boxes += [(0, sy * (hy - w / 2), z1 / 2, hx - w, w / 2, z1 / 2) for sy in (-1, 1)]
    vol = sum(8 * a * b * c for *_, a, b, c in boxes)
    g = [
        '<geom name="tote" type="mesh" mesh="tote_vis" material="tote_mat" contype="0" conaffinity="0" group="2" density="0"/>'
    ]
    g += [
        f'<geom name="tote_c{i}" type="box" pos="{px} {py} {pz}" size="{a} {b} {c}" group="3" density="{TOTE_MASS / vol:.6g}" '
        f'condim="4" friction="0.6 0.005 0.0001" rgba="0.8 0.3 0.3 0.4"/>'
        for i, (px, py, pz, a, b, c) in enumerate(boxes)
    ]
    p, q = pose["pos"], pose["quat"]
    asset = (
        f'<mesh name="tote_vis" file="{d}/visual.obj"/>\n    '
        '<material name="tote_mat" rgba="0.42 0.44 0.46 1" specular="0.2" shininess="0.2"/>'
    )
    body = (
        f'<body name="tote" pos="{p[0]!r} {p[1]!r} {p[2]!r}" quat="{q[0]!r} {q[1]!r} {q[2]!r} {q[3]!r}">'
        f'<freejoint name="tote"/>{"".join(g)}</body>'
    )
    return asset, body


def scene_xml(inst: dict, yam_xml: str | Path = YAM_XML) -> str:
    """The MJCF of the station with the instance's objects at their start poses."""
    parts = [_object_xml(n, inst["objects"][n]) for n in FAMILIES[inst["family"]]["objects"]]
    sky = ASSETS / "sky" / "reading_room"
    return f"""<mujoco model="sim_to_real_yam_station">
  <compiler angle="radian"/>
  <option timestep="{SIM_DT}" integrator="implicitfast" cone="elliptic" impratio="10"/>
  <visual><headlight diffuse="0.35 0.35 0.35" ambient="0.25 0.25 0.25" specular="0 0 0"/><quality shadowsize="4096"/>
    <global offwidth="1280" offheight="720"/></visual>
  <asset>
    <model name="yam" file="{yam_xml}"/>
    <texture name="sky" type="skybox" fileright="{sky}/px.png" fileleft="{sky}/nx.png" fileup="{sky}/pz.png"
      filedown="{sky}/nz.png" filefront="{sky}/py.png" fileback="{sky}/ny.png"/>
    <texture name="oak" type="2d" file="{ASSETS}/materials/oak.png"/>
    <material name="oak" texture="oak" texrepeat="2 2" texuniform="true" specular="0.2" shininess="0.2"/>
    <material name="frame" rgba="0.18 0.18 0.2 1"/>
    {chr(10).join("    " + a for a, _ in parts)}
  </asset>
  <worldbody>
    <light name="key" pos="0.2 -0.3 1.8" dir="0.1 0 -1" castshadow="true" diffuse="0.6 0.6 0.58" cutoff="70"/>
    <light name="fill" pos="1.5 1.0 1.5" dir="-0.6 -0.4 -0.6" directional="true" castshadow="false" diffuse="0.25 0.25 0.27"/>
    <geom name="table" type="box" pos="0.25 -0.305 -0.025" size="0.45 0.75 0.025" material="oak" friction="0.7 0.005 0.0001"/>
    <geom name="table_frame" type="box" pos="0.25 -0.305 -0.39" size="0.4 0.7 0.34" material="frame"/>
    <frame name="left_mount"><attach model="yam" body="arm" prefix="left/"/></frame>
    <frame name="right_mount" pos="{RIGHT_BASE[0]} {RIGHT_BASE[1]} {RIGHT_BASE[2]}"><attach model="yam" body="arm" prefix="right/"/></frame>
    <body name="top_camera" pos="{TOP_CAM_POS}" quat="{TOP_CAM_QUAT}"><camera name="top_cam" quat="0 1 0 0" {D405}/></body>
    <camera name="front_view" pos="1.05 -0.305 0.62" xyaxes="0 1 0 -0.5 0 0.87" fovy="55"/>
    {chr(10).join("    " + b for _, b in parts)}
  </worldbody>
</mujoco>"""


def load_model(inst: dict):
    import mujoco

    return mujoco.MjModel.from_xml_string(scene_xml(inst))


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False):
        import mujoco

        self.mj = mujoco
        self.inst = json.load(open(instance)) if not isinstance(instance, dict) else instance
        self.family = self.inst["family"]
        self.spec = FAMILIES[self.family]
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
        self.objects = list(self.spec["objects"])
        self._obj_body = {o: m.body(o).id for o in self.objects}
        self._obj_geom = {
            g: m.body(m.geom_bodyid[g]).name for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name in self._obj_body
        }
        self._obj_q = {o: m.jnt_qposadr[m.body_jntadr[self._obj_body[o]]] for o in self.objects}
        self._obj_v = {o: m.jnt_dofadr[m.body_jntadr[self._obj_body[o]]] for o in self.objects}
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
        for o in self.objects:
            pose = self.inst["objects"][o]
            d.qpos[self._obj_q[o] : self._obj_q[o] + 7] = np.r_[pose["pos"], pose["quat"]]
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

    def _robot_contacts(self) -> set[str]:
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

    def in_container(self, o: str) -> bool:
        """RoboLab's `object_in_container`: the object's centroid lies in the container's local bounding box, with one
        container height of open-top slack above it, and the object touches the container."""
        c, d = self.spec["container"], self.data
        (x0, y0, z0), (x1, y1, z1) = asset_meta(c)["bbox_min"], asset_meta(c)["bbox_max"]
        R = d.xmat[self._obj_body[c]].reshape(3, 3)
        rel = R.T @ (d.xipos[self._obj_body[o]] - d.xpos[self._obj_body[c]])
        inside = x0 <= rel[0] <= x1 and y0 <= rel[1] <= y1 and z0 <= rel[2] <= z1 + (z1 - z0)
        return bool(inside and (o, c) in self._touching())

    def _touching(self) -> set[tuple[str, str]]:
        d, out = self.data, set()
        for k in d.contact[: d.ncon]:
            a, b = self._obj_geom.get(k.geom1), self._obj_geom.get(k.geom2)
            if a and b and a != b:
                out |= {(a, b), (b, a)}
        return out

    # ------------------------------------------------------------------- success
    def check(self) -> dict[str, Any]:
        d = self.data
        touched = self._robot_contacts()
        rest = all(self._obj_speed(o) < REST_SPEED for o in self.objects)
        c = self.spec["container"]
        upright = bool(d.xmat[self._obj_body[c]].reshape(3, 3)[2, 2] > UPRIGHT_COS)
        inside = {f"{o}_in_{c}": self.in_container(o) for o in self.spec["goal"]}
        ok = bool(all(inside.values()) and upright and rest and not touched and not self.arm_collision)
        return {
            "success": ok,
            **inside,
            f"{c}_upright": upright,
            "at_rest": bool(rest),
            "robot_touches_object": bool(touched),
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
        return {
            "qpos": d.qpos.copy(),
            "qvel": d.qvel.copy(),
            "joints": q,
            "targets": self.targets.copy(),
            "sites": sites,
            "site_mats": site_mats,
            "objects": objs,
            **self.check(),
        }

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


# ------------------------------------------------------------------ instances
LAYOUT = {  # family: {object: (x range, y range, yaw range)}; first entry placed first
    "fruits_in_bowl": {
        "bowl": ((0.27, 0.33), (-0.10, -0.02), (0, 0)),
        "banana": ((0.22, 0.40), (-0.26, 0.18), (-np.pi, np.pi)),
        "lemon": ((0.22, 0.40), (-0.26, 0.18), (-np.pi, np.pi)),
        "orange": ((0.22, 0.40), (-0.26, 0.18), (0, 0)),
        "mug": ((0.22, 0.40), (-0.26, 0.18), (-np.pi, np.pi)),
        "tomato_soup_can": ((0.22, 0.40), (-0.26, 0.18), (-np.pi, np.pi)),
    },
    "pack_tote": {
        "tote": ((0.26, 0.29), (-0.325, -0.285), (np.pi / 2 - 0.08, np.pi / 2 + 0.08)),
        "tomato_soup_can": ((0.20, 0.36), (0.02, 0.17), (-np.pi, np.pi)),
        "foam_brick": ((0.20, 0.36), (0.02, 0.17), (-np.pi, np.pi)),
        "spam_can": ((0.20, 0.36), (-0.78, -0.63), (-np.pi, np.pi)),
        "marker": ((0.20, 0.36), (-0.78, -0.63), (-np.pi, np.pi)),
    },
}


def _footprint(name: str) -> float:
    (x0, y0, _), (x1, y1, _) = asset_meta(name)["bbox_min"], asset_meta(name)["bbox_max"]
    return 0.5 * float(max(x1 - x0, y1 - y0))


def make_instance(family: str, seed: int, settle_s: float = 1.5) -> dict:
    """Draw object poses from `seed` (non-overlapping footprints), then let the scene settle with the arms at rest; the
    settled poses are the frozen instance."""
    rng = np.random.default_rng(seed)
    for _ in range(1000):  # whole-layout restarts
        placed: dict[str, dict] = {}
        for name, ((xa, xb), (ya, yb), (wa, wb)) in LAYOUT[family].items():
            r = _footprint(name)
            for _ in range(200):
                x, y, yaw = rng.uniform(xa, xb), rng.uniform(ya, yb), rng.uniform(wa, wb)
                if all(np.hypot(x - p["pos"][0], y - p["pos"][1]) > r + p["r"] + 0.02 for p in placed.values()):
                    break
            else:
                break
            z = -asset_meta(name)["bbox_min"][2] + 0.003
            placed[name] = {"pos": [x, y, z], "quat": [float(v) for v in _quat_z(yaw).split()], "r": r}
        if len(placed) == len(LAYOUT[family]):
            break
    else:
        raise RuntimeError(f"cannot lay out {family} with seed {seed}")
    inst = {
        "benchmark": "sim_to_real",
        "family": family,
        "seed": seed,
        "objects": {k: {"pos": v["pos"], "quat": v["quat"]} for k, v in placed.items()},
    }
    s = Session(inst)
    for _ in range(int(settle_s / CONTROL_DT)):
        s.step(s.targets)
    d = s.data
    for o in s.objects:
        q = d.qpos[s._obj_q[o] : s._obj_q[o] + 7]
        inst["objects"][o] = {
            "pos": [round(float(v), 6) for v in q[:3]],
            "quat": [round(float(v), 6) for v in q[3:] / np.linalg.norm(q[3:])],
        }
    return inst


if __name__ == "__main__":
    s = Session(sys.argv[1] if len(sys.argv) > 1 else "/app/instance.json")
    print(json.dumps({"family": s.family, "seed": s.seed, "state_sha": s.state_sha(), **s.check()}))
