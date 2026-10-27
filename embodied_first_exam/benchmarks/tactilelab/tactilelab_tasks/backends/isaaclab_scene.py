"""Isaac Lab scene: simulation context, table, robot, rigid objects and two wrist cameras.

No ``ManagerBasedEnv``: :class:`IsaacLabScene` drives ``SimulationContext.step``
directly so a :class:`tactilelab_tasks.core.task.Task` can drop into any stack.

Typical use::

    from tactilelab_tasks.backends.isaaclab_scene import launch_app
    app = launch_app(headless=True)              # before importing the heavy symbols
    from tactilelab_tasks.backends.isaaclab_scene import IsaacLabScene, SceneCfg, ObjectCfg
    scene = IsaacLabScene(SceneCfg(objects=[ObjectCfg("cube", shape="cuboid", dims=(0.04,)*3, pos=(0, 0, 1.13))]))
    scene.build()
    scene.step(action)            # one control tick = 2 physics substeps, IK each substep
    rgb = scene.render_cameras()  # {"wrist_right_rgb": (480, 640, 3) uint8, "wrist_left_rgb": ...}

Timing: physics dt 1/120, decimation 2 (60 Hz control).
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..core import math as m
from ..core.types import (
    CONTROL_DT,
    DECIMATION,
    PHYSICS_DT,
    TABLE_TOP_Z,
    Action,
)
from .robot import RobotCfg, XTrainerGsmini

# ----------------------------------------------------------------------------- wrist cameras
WRIST_CAM_RIGHT_POS = (-0.00896, -0.05315, 0.06515)
WRIST_CAM_RIGHT_ORI_DEG = (142.66, 0.97, -0.79)
"""Right wrist camera under ``J1_6``: local position (m) and extrinsic XYZ Euler angles (deg),
USD camera convention (looks along its -Z, +Y up)."""
WRIST_CAM_FOCAL = 1.277
WRIST_CAM_APERTURE = 20.955
WRIST_CAM_RES = (640, 480)


def left_wrist_mount(
    pos=WRIST_CAM_RIGHT_POS, ori_deg=WRIST_CAM_RIGHT_ORI_DEG
) -> Tuple[Tuple[float, float, float], np.ndarray]:
    """The right mount carried over to the left hand.

    The left hand (``J2_6`` and its fingers) is the right hand rotated 180 degrees
    about the wrist axis (finger origins ``(-0.0625, -0.024)`` vs ``(+0.0625, +0.024)``
    in the two wrist frames), so the same physical camera sits at ``Rz(180) * mount``:
    ``(x, y) -> (-x, -y)`` and yaw + 180 degrees. Returns ``(pos, quat_wxyz)``.
    """
    rz = m.quat_from_euler_xyz_deg([0.0, 0.0, 180.0])
    p = m.quat_rotate(rz, np.asarray(pos, dtype=np.float64))
    q = m.quat_mul(rz, m.quat_from_euler_xyz_deg(ori_deg))
    return (float(p[0]), float(p[1]), float(p[2])), q


# ----------------------------------------------------------------------------- configs
@dataclass
class ObjectCfg:
    """One rigid object. Either ``usd_path`` or ``shape="cuboid"`` with ``dims``."""

    name: str
    usd_path: Optional[str] = None
    pos: Tuple[float, float, float] = (0.0, 0.0, TABLE_TOP_Z)
    ori_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    shape: Optional[str] = None
    dims: Tuple[float, float, float] = (0.04, 0.04, 0.04)
    mass: Optional[float] = None
    kinematic: bool = False
    color: Tuple[float, float, float] = (0.8, 0.3, 0.2)
    friction: Optional[float] = None

    def pose(self) -> np.ndarray:
        return m.pose_from_pos_euler_deg(self.pos, self.ori_deg)


@dataclass
class SceneCfg:
    physics_dt: float = PHYSICS_DT
    decimation: int = DECIMATION
    device: str = "cuda:0"
    robot: RobotCfg = field(default_factory=RobotCfg)
    objects: List[ObjectCfg] = field(default_factory=list)
    cameras: bool = True
    camera_res: Tuple[int, int] = WRIST_CAM_RES
    desk: bool = True
    desk_size: Tuple[float, float] = (1.2, 0.9)
    desk_center_xy: Tuple[float, float] = (-0.05, 0.0)
    light_intensity: float = 2000.0
    ik_kwargs: Dict[str, Any] = field(default_factory=dict)
    physx_bounce_threshold: float = 0.02
    physx_friction_offset: float = 0.01
    physx_friction_correlation: float = 0.0005
    physx_min_position_iters: int = 20
    physx_min_velocity_iters: int = 1
    enhanced_determinism: bool = bool(int(__import__("os").environ.get("TACTILELAB_ENHANCED_DETERMINISM", "0")))
    """PhysX enhanced determinism (also on the GPU pipeline: replays end in the same state; slightly slower)."""

    @property
    def control_dt(self) -> float:
        return self.physics_dt * self.decimation


# ----------------------------------------------------------------------------- app
_APP = None


def launch_app(
    headless: Optional[bool] = None, enable_cameras: bool = True, extra_args: Optional[Sequence[str]] = None
):
    """Start Isaac Sim through ``isaaclab.app.AppLauncher`` (idempotent).

    ``headless`` defaults to the ``HEADLESS`` environment variable. Must run before
    importing ``isaaclab.sim`` and friends.
    """
    global _APP
    if _APP is not None:
        return _APP
    from isaaclab.app import AppLauncher

    parser = argparse.ArgumentParser(add_help=False)
    AppLauncher.add_app_launcher_args(parser)
    args, _ = parser.parse_known_args(list(extra_args or []))
    if headless is None:
        headless = os.environ.get("HEADLESS", "0") not in ("0", "", "false", "False")
    args.headless = bool(headless)
    args.enable_cameras = bool(enable_cameras)
    launcher = AppLauncher(args)
    _APP = launcher.app
    return _APP


# ----------------------------------------------------------------------------- scene
class IsaacLabScene:
    """Robot + table + objects + wrist cameras in one Isaac Lab stage (one env)."""

    def __init__(self, cfg: Optional[SceneCfg] = None):
        self.cfg = cfg or SceneCfg()
        self.sim = None
        self.robot: Optional[XTrainerGsmini] = None
        self.ik = None
        self.objects: Dict[str, Any] = {}
        self.cameras: Dict[str, Any] = {}
        self.tick = 0
        self.base_pose = self.cfg.robot.base_pose()
        self._last_targets: List[Optional[np.ndarray]] = [None, None]
        self._built = False

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        import isaaclab.sim as sim_utils
        from isaaclab.sim import PhysxCfg, SimulationCfg, SimulationContext

        from .ik_pink import PinkIK

        c = self.cfg
        sim_cfg = SimulationCfg(
            dt=c.physics_dt,
            render_interval=c.decimation,
            device=c.device,
            physx=PhysxCfg(
                bounce_threshold_velocity=c.physx_bounce_threshold,
                friction_offset_threshold=c.physx_friction_offset,
                friction_correlation_distance=c.physx_friction_correlation,
                min_position_iteration_count=c.physx_min_position_iters,
                min_velocity_iteration_count=c.physx_min_velocity_iters,
                enable_enhanced_determinism=bool(c.enhanced_determinism),
            ),
        )
        self.sim = SimulationContext(sim_cfg)
        self.sim.set_camera_view(eye=(1.2, -1.6, 1.9), target=(0.0, 0.0, 1.15))

        # ground, light, desk
        sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
        light = sim_utils.DomeLightCfg(intensity=c.light_intensity, color=(1.0, 1.0, 1.0))
        light.func("/World/Light", light)
        if c.desk:
            # The robot USD carries its own 0.79 x 0.62 m worktop (top at base z + 0.0017 = TABLE_TOP_Z).
            # The desk is a larger static slab whose top sits 1 mm under the worktop so the two never fight.
            thickness = 0.04
            top = TABLE_TOP_Z - 0.001
            desk = sim_utils.CuboidCfg(
                size=(c.desk_size[0], c.desk_size[1], thickness),
                collision_props=sim_utils.CollisionPropertiesCfg(),
                visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.42, 0.28)),
                physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.8, dynamic_friction=0.8),
            )
            desk.func("/World/Desk", desk, translation=(c.desk_center_xy[0], c.desk_center_xy[1], top - thickness / 2))

        # robot
        self.robot = XTrainerGsmini(c.robot)
        self.ik = PinkIK(dt=c.physics_dt, **c.ik_kwargs)

        # objects
        for ocfg in c.objects:
            self.objects[ocfg.name] = self._spawn_object(ocfg)

        # cameras
        if c.cameras:
            self._spawn_cameras()

        self.sim.reset()
        self.robot.initialize()
        self.robot.reset()
        self.ik.reset(self.robot.cfg.q0()[:12])
        self._settle(2)
        self._built = True

    def _spawn_object(self, o: ObjectCfg):
        import isaaclab.sim as sim_utils
        from isaaclab.assets import RigidObject, RigidObjectCfg

        rigid = sim_utils.RigidBodyPropertiesCfg(
            kinematic_enabled=o.kinematic, disable_gravity=False, max_depenetration_velocity=5.0
        )
        mass = sim_utils.MassPropertiesCfg(mass=o.mass) if o.mass is not None else None
        pmat = (
            sim_utils.RigidBodyMaterialCfg(static_friction=o.friction, dynamic_friction=o.friction)
            if o.friction is not None
            else None
        )
        if o.shape == "cuboid" or o.usd_path is None:
            spawn = sim_utils.CuboidCfg(
                size=tuple(o.dims),
                rigid_props=rigid,
                mass_props=mass or sim_utils.MassPropertiesCfg(mass=0.05),
                collision_props=sim_utils.CollisionPropertiesCfg(),
                visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=tuple(o.color)),
                physics_material=pmat,
            )
        else:
            spawn = sim_utils.UsdFileCfg(usd_path=o.usd_path, scale=tuple(o.scale), rigid_props=rigid, mass_props=mass)
        q = m.quat_from_euler_xyz_deg(o.ori_deg)
        cfg = RigidObjectCfg(
            prim_path=f"/World/Objects/{o.name}",
            spawn=spawn,
            init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(o.pos), rot=tuple(float(x) for x in q)),
        )
        return RigidObject(cfg)

    def _spawn_cameras(self) -> None:
        import isaaclab.sim as sim_utils
        from isaaclab.sensors import Camera, CameraCfg

        w, h = self.cfg.camera_res
        right_q = m.quat_from_euler_xyz_deg(WRIST_CAM_RIGHT_ORI_DEG)
        left_pos, left_q = left_wrist_mount()
        mounts = {
            "wrist_right": ("J1_6", WRIST_CAM_RIGHT_POS, right_q),
            "wrist_left": ("J2_6", left_pos, left_q),
        }
        for name, (link, pos, quat) in mounts.items():
            cam_cfg = CameraCfg(
                prim_path=f"{self.cfg.robot.prim_path}/{link}/{name}_cam",
                offset=CameraCfg.OffsetCfg(pos=tuple(pos), rot=tuple(float(x) for x in quat), convention="opengl"),
                spawn=sim_utils.PinholeCameraCfg(
                    focal_length=WRIST_CAM_FOCAL, horizontal_aperture=WRIST_CAM_APERTURE, clipping_range=(0.01, 100.0)
                ),
                width=w,
                height=h,
                data_types=["rgb"],
                update_period=0.0,
            )
            self.cameras[name] = Camera(cam_cfg)

    def _settle(self, ticks: int) -> None:
        for _ in range(ticks):
            self.step(Action.hold(self.robot._gripper_cmd))

    # ------------------------------------------------------------------ stepping
    def step(self, action: Action) -> None:
        """One control tick: ``decimation`` physics substeps with an IK solve each."""
        if not isinstance(action, Action):
            action = Action.from_vector(np.asarray(action))
        targets_base: List[Optional[np.ndarray]] = []
        for arm in range(2):
            tgt = action.arm(arm)
            if m.is_nan_pose(tgt):
                targets_base.append(None)
            else:
                targets_base.append(m.pose_relative(self.base_pose, tgt))
        self._last_targets = [None if t is None else t.copy() for t in targets_base]
        self.robot.set_gripper(action.gripper, action.gripper_gap)
        for _ in range(self.cfg.decimation):
            q = self.robot.joint_pos()
            q_arm = self.ik.solve(q[:12], targets_base)
            self.robot.set_arm_targets(q_arm)
            self.robot.write_data_to_sim()
            for obj in self.objects.values():
                obj.write_data_to_sim()
            self.sim.step(render=False)
            self.robot.update(self.cfg.physics_dt)
            for obj in self.objects.values():
                obj.update(self.cfg.physics_dt)
        self.tick += 1

    def render_cameras(self) -> Dict[str, np.ndarray]:
        """Render once and return ``{"wrist_right_rgb", "wrist_left_rgb"}`` as (H, W, 3) uint8."""
        out: Dict[str, np.ndarray] = {}
        if not self.cameras:
            return out
        self.sim.render()
        for name, cam in self.cameras.items():
            cam.update(self.cfg.control_dt, force_recompute=True)
            rgb = cam.data.output["rgb"][0]
            rgb = rgb.detach().cpu().numpy() if hasattr(rgb, "detach") else np.asarray(rgb)
            if rgb.ndim == 3 and rgb.shape[-1] == 4:
                rgb = rgb[..., :3]
            out[f"{name}_rgb"] = np.ascontiguousarray(rgb.astype(np.uint8))
        return out

    # ------------------------------------------------------------------ queries
    def robot_obs(self) -> Dict[str, np.ndarray]:
        return self.robot.obs()

    def ee_pose(self, arm: int) -> np.ndarray:
        return self.robot.ee_pose(arm)

    def ik_errors(self) -> Dict[int, Tuple[float, float]]:
        """``(m, rad)`` error of each commanded arm against its last IK target, from the sim body poses."""
        out = {}
        for arm, tgt in enumerate(self._last_targets):
            if tgt is None:
                continue
            cur = m.pose_relative(self.base_pose, self.robot.ee_pose(arm))
            out[arm] = m.pose_error(cur, tgt)
        return out

    def object_pose(self, name: str) -> np.ndarray:
        obj = self.objects[name]
        st = obj.data.root_link_pose_w[0].detach().cpu().numpy().astype(np.float64)
        return m.pose_from_pos_quat(st[:3], st[3:7])

    def object_velocity(self, name: str) -> np.ndarray:
        return self.objects[name].data.root_vel_w[0].detach().cpu().numpy().astype(np.float64)

    def set_object_pose(self, name: str, pose: np.ndarray, velocity: Optional[np.ndarray] = None) -> None:
        import torch

        obj = self.objects[name]
        pose = np.asarray(pose, dtype=np.float32).reshape(1, 7)
        obj.write_root_link_pose_to_sim(torch.as_tensor(pose, device=obj.device))
        vel = (
            np.zeros((1, 6), dtype=np.float32)
            if velocity is None
            else np.asarray(velocity, dtype=np.float32).reshape(1, 6)
        )
        obj.write_root_velocity_to_sim(torch.as_tensor(vel, device=obj.device))
        obj.write_data_to_sim()

    def reset_objects(self) -> None:
        for ocfg in self.cfg.objects:
            self.set_object_pose(ocfg.name, ocfg.pose())

    def apply_external_force(self, name: str, force, torque=None) -> None:
        """Set a constant external wrench (env frame, N / N m) on the root body of object ``name``.

        The wrench is stored in the object's buffers and written to PhysX at every physics substep until it is
        replaced (zeros clear it) - the two-way coupling knob of the dough tasks (the sidecar's reaction on the tool).
        """
        import torch

        obj = self.objects[name]
        f = torch.as_tensor(np.asarray(force, dtype=np.float32).reshape(1, 1, 3), device=obj.device)
        tq = (
            torch.zeros((1, 1, 3), device=obj.device)
            if torque is None
            else torch.as_tensor(np.asarray(torque, dtype=np.float32).reshape(1, 1, 3), device=obj.device)
        )
        obj.set_external_force_and_torque(f, tq, is_global=True)

    def reset_robot(self, q: Optional[np.ndarray] = None) -> None:
        self.robot.reset(q)
        self.ik.reset(self.robot.joint_pos()[:12])
        self._last_targets = [None, None]

    # ------------------------------------------------------------------ state
    def get_state(self) -> Dict[str, Any]:
        st: Dict[str, Any] = dict(self.robot.get_state())
        st["objects"] = {n: {"pose": self.object_pose(n), "vel": self.object_velocity(n)} for n in self.objects}
        st["tick"] = self.tick
        return st

    def set_state(self, state: Dict[str, Any]) -> None:
        self.robot.set_state(state)
        self.ik.reset(np.asarray(state["robot_q"])[:12])
        for n, s in state.get("objects", {}).items():
            if n in self.objects:
                self.set_object_pose(n, np.asarray(s["pose"]), np.asarray(s.get("vel", np.zeros(6))))
        self.tick = int(state.get("tick", self.tick))

    def close(self) -> None:
        if self.sim is not None:
            try:
                self.sim.clear_all_callbacks()
            except Exception:
                pass


__all__ = [
    "IsaacLabScene",
    "SceneCfg",
    "ObjectCfg",
    "launch_app",
    "left_wrist_mount",
    "WRIST_CAM_RIGHT_POS",
    "WRIST_CAM_RIGHT_ORI_DEG",
]
