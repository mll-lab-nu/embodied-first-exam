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
"""Pinhole, square pixels, principal point at the image centre: focal 1.277 mm over the 20.955 mm horizontal aperture,
WRIST_CAM_HFOV_DEG = 166.1 x 161.5 degrees at 640 x 480 (fx = fy = 39.0 px)."""
WRIST_CAM_HFOV_DEG = 2.0 * float(np.degrees(np.arctan(WRIST_CAM_APERTURE / 2.0 / WRIST_CAM_FOCAL)))
WRIST_CAM_HFOV_RANGE_DEG = (30.0, WRIST_CAM_HFOV_DEG)
"""The horizontal fields of view one render may ask for (render_cameras(hfov_deg=...)), the default the widest. Each
wrist camera has a lens camera at the same mount (same aperture and resolution) whose focal length is set to the asked
field of view: the wrist camera itself is never changed. A lens camera is not rendered until a field of view is first
asked for; from then on every render renders it too."""
WRIST_CAM_HFOV_TOL_DEG = 0.01
"""A requested field of view this close to the default (e.g. the rounded 166.1) is the default lens."""
LENS_START_HFOV_DEG = 90.0
LENS_SETTLE_RENDERS = 4
"""Renders after a lens camera's focal length changes before its image is taken (the RTX renderer's temporal
anti-aliasing blends earlier frames of the same render product)."""


def wrist_hfov(value: Any) -> Optional[float]:
    """A requested horizontal field of view (degrees) checked: None (the default lens; also for a value within
    WRIST_CAM_HFOV_TOL_DEG of the default, e.g. its rounded 166.1) or a finite number within WRIST_CAM_HFOV_RANGE_DEG;
    anything else is a ValueError."""
    if value is None:
        return None
    lo, hi = WRIST_CAM_HFOV_RANGE_DEG
    try:
        num = not isinstance(value, bool) and isinstance(value, (int, float, np.integer, np.floating))
        v = float(value) if num else None
    except (OverflowError, ValueError):
        v = None
    if v is None or not np.isfinite(v):
        raise ValueError(f"hfov_deg must be a number in [{lo:g}, {hi:.4f}] degrees, got {value!r:.40}")
    if not (lo <= v <= hi + WRIST_CAM_HFOV_TOL_DEG):
        raise ValueError(
            f"hfov_deg must be in [{lo:g}, {hi:.4f}] degrees (the wrist camera's horizontal field of view), got {v:g}"
        )
    return None if v >= hi - WRIST_CAM_HFOV_TOL_DEG else v


def wrist_focal(hfov_deg: Optional[float]) -> float:
    """The focal length (mm) over the wrist camera's aperture that gives this horizontal field of view (None: the stock
    WRIST_CAM_FOCAL, exactly)."""
    if hfov_deg is None or float(hfov_deg) >= WRIST_CAM_HFOV_DEG - WRIST_CAM_HFOV_TOL_DEG:
        return WRIST_CAM_FOCAL
    return WRIST_CAM_APERTURE / 2.0 / float(np.tan(np.radians(float(hfov_deg)) / 2.0))

# ----------------------------------------------------------------------------- video camera (recording only)
# A fixed third-person camera for the recorded videos (the privileged video replay, the standard live video). It is
# no observation: render_cameras() / camera_info() (what the agent gets) leave it out, and it is spawned only when a
# video is recorded (enable_video_camera() before the scene is built). A camera has no physics: the scene state and its
# hash do not change. Pinhole, square pixels: 1280 x 720, focal 18 mm over the 20.955 mm aperture = 60.4 x 36.3
# degrees. The view is the teleoperator's, from behind the two leader arms (y < 0) over the table centre: both arms
# (bases at x = -0.5 and +0.455) and the workspace between them.
VIDEO_CAM_RES = (1280, 720)
VIDEO_CAM_FOCAL = 18.0
VIDEO_CAM_APERTURE = 20.955
VIDEO_CAM_EYE = (0.0, -1.25, 1.90)
VIDEO_CAM_TARGET = (-0.02, 0.0, 1.28)
VIDEO_WARM_RENDERS = 3
_VIDEO_CAMERA = [False]


def enable_video_camera(on: bool = True) -> None:
    """Spawn the third-person video camera in the scenes built from now on (a process-wide switch: the tasks build
    their SceneCfg in several places)."""
    _VIDEO_CAMERA[0] = bool(on)


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
        self.lens: Dict[str, Any] = {}
        self._lens_focal: Dict[str, Any] = {}
        self._lens_on: Dict[str, bool] = {}
        self._lens_idle_handle = None
        self.video_cam = None
        self._video_warm = False
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
        # the ground: a local static slab with the stock ground plane's friction. Isaac Lab's GroundPlaneCfg loads its USD
        # from the Omniverse asset server, which a task container cannot reach (the verifier has no network, the
        # agent's allowlist does not name it); nothing in the tasks rests on the ground (the robot and the desk stand
        # on their own), it only catches a dropped object
        ground = sim_utils.CuboidCfg(
            size=(20.0, 20.0, 0.02),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.3, 0.3, 0.3)),
            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.5, dynamic_friction=0.5),
        )
        ground.func("/World/ground", ground, translation=(0.0, 0.0, -0.01))
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
        if _VIDEO_CAMERA[0]:
            self._spawn_video_camera()

        self.sim.reset()
        self._lens_idle()  # (if the PLAY callback found the cameras uninitialised)
        self._lens_idle_handle = None
        if self.video_cam is not None:
            self.set_video_view(VIDEO_CAM_EYE, VIDEO_CAM_TARGET)
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
                data_types=["rgb", "distance_to_image_plane"],
                update_period=0.0,
            )
            self.cameras[name] = Camera(cam_cfg)
            # its lens camera: the same mount and camera, another focal length (render_cameras(hfov_deg=...)); its own
            # render product, so the wrist camera's images (and the renderer's history of them) never see a lens change
            lens_cfg = cam_cfg.replace(
                prim_path=f"{self.cfg.robot.prim_path}/{link}/{name}_lens_cam",
                spawn=sim_utils.PinholeCameraCfg(
                    focal_length=wrist_focal(LENS_START_HFOV_DEG), horizontal_aperture=WRIST_CAM_APERTURE,
                    clipping_range=(0.01, 100.0),
                ),
            )
            self.lens[name] = Camera(lens_cfg)
            self._lens_focal[name] = np.float32(wrist_focal(LENS_START_HFOV_DEG))
        # the lens cameras are idle from the start: turned off on PLAY right after the cameras initialise (Isaac Lab's
        # sensors at order 10), before SimulationContext.reset()'s warm-up renders, so the wrist cameras' renders are
        # those of a scene without lens cameras
        import weakref

        import omni.timeline

        me = weakref.ref(self)
        self._lens_idle_handle = (
            omni.timeline.get_timeline_interface()
            .get_timeline_event_stream()
            .create_subscription_to_pop_by_type(
                int(omni.timeline.TimelineEventType.PLAY), lambda _e: me() is not None and me()._lens_idle(), order=20
            )
        )

    def _lens_idle(self) -> None:
        for name in self.lens:
            if name not in self._lens_on and self.lens[name].is_initialized:
                self._lens_updates(name, False)

    def _spawn_video_camera(self) -> None:
        import isaaclab.sim as sim_utils
        from isaaclab.sensors import Camera, CameraCfg

        w, h = VIDEO_CAM_RES
        self.video_cam = Camera(
            CameraCfg(
                prim_path="/World/VideoCam",
                spawn=sim_utils.PinholeCameraCfg(
                    focal_length=VIDEO_CAM_FOCAL, horizontal_aperture=VIDEO_CAM_APERTURE, clipping_range=(0.05, 50.0)
                ),
                width=w,
                height=h,
                data_types=["rgb"],
                update_period=0.0,
            )
        )

    def set_video_view(self, eye, target) -> None:
        """Place the video camera at ``eye`` looking at ``target`` (env frame, metres)."""
        import torch

        dev = self.video_cam.device if hasattr(self.video_cam, "device") else self.cfg.device
        self.video_cam.set_world_poses_from_view(
            torch.tensor([list(eye)], dtype=torch.float32, device=dev),
            torch.tensor([list(target)], dtype=torch.float32, device=dev),
        )

    def render_video(self) -> Optional[np.ndarray]:
        """The third-person video camera's RGB (H, W, 3) uint8, rendered now (None without it); never steps physics. The
        first one renders VIDEO_WARM_RENDERS times more (the renderer's temporal history of the camera, placed after the
        scene's warm-up renders, is empty: an unconverged first frame)."""
        if self.video_cam is None:
            return None
        if not self._video_warm:
            for _ in range(VIDEO_WARM_RENDERS):
                self.sim.render()
            self._video_warm = True
        self.sim.render()
        self.video_cam.update(self.cfg.control_dt, force_recompute=True)
        rgb = self.video_cam.data.output["rgb"][0]
        rgb = rgb.detach().cpu().numpy() if hasattr(rgb, "detach") else np.asarray(rgb)
        return np.ascontiguousarray(rgb[..., :3].astype(np.uint8))

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

    def render_cameras(self, depth: bool = False, hfov_deg: Optional[Dict[str, float]] = None) -> Dict[str, np.ndarray]:
        """Render once and return ``{"wrist_right_rgb", "wrist_left_rgb"}`` as (H, W, 3) uint8; with ``depth`` also
        ``{"wrist_right_depth", "wrist_left_depth"}``, (H, W) float32 z-depth in metres (distance to the image plane,
        0 where nothing was hit). ``hfov_deg`` ({"wrist_right" | "wrist_left": degrees}, WRIST_CAM_HFOV_RANGE_DEG): only
        those cameras, each through its lens camera set to that horizontal field of view (wrist_intrinsics() gives the
        matrix); a value None or at the default is the camera itself. Rendering never steps physics."""
        if not self.cameras:
            return {}
        if not hfov_deg:
            return self._render(depth)
        unknown = sorted(set(hfov_deg) - set(self.cameras))
        if unknown:
            raise ValueError(f"hfov_deg names no wrist camera: {unknown} (cameras: {sorted(self.cameras)})")
        want = {n: wrist_focal(wrist_hfov(v)) for n, v in hfov_deg.items()}
        stock = [n for n, f in want.items() if f == WRIST_CAM_FOCAL]
        lens = {n: f for n, f in want.items() if f != WRIST_CAM_FOCAL}
        out = {k: v for k, v in self._render(depth).items() if k.rsplit("_", 1)[0] in stock} if stock else {}
        if lens:
            # a lens camera is idle (not rendered) until first asked for, then renders with every render at its current
            # focal length: after it is turned on or its focal length changes, LENS_SETTLE_RENDERS renders let the
            # renderer's temporal history catch up before the image is taken
            changed = [
                n for n, f in lens.items() if self._lens_focal.get(n) != np.float32(f) or not self._lens_on.get(n)
            ]
            for n in changed:
                self._set_focal(self.lens[n], lens[n]); self._lens_focal[n] = np.float32(lens[n])
                if not self._lens_on.get(n):
                    self._lens_updates(n, True)
            for _ in range(LENS_SETTLE_RENDERS if changed else 0):
                self.sim.render()
            got = self._render(depth, {n: self.lens[n] for n in lens})
            for n in lens:
                if got[f"{n}_rgb"].size == 0:
                    raise RuntimeError(f"lens camera {n}: no image after turning it on")
            out.update(got)
        return out

    def _lens_updates(self, name: str, on: bool) -> None:
        """Turn the rendering of lens camera ``name``'s render product off (an idle render product costs no render time)
        or back on. Turning it back on re-attaches the camera's annotators (Replicator's attach is what restarts their
        data after the render product was off). If the renderer offers no switch the lens camera is left on; a lens
        camera that cannot be turned back on is an error."""
        cam = self.lens[name]
        try:
            from omni.replicator.core.scripts.utils.viewport_manager import ViewportManager

            hts = [ViewportManager._hydra_textures.get(None, rp) for rp in cam.render_product_paths]
            if not all(hasattr(getattr(ht, "hydra_texture", None), "set_updates_enabled") for ht in hts):
                raise TypeError("no hydra texture")
            if not on:
                for ht in hts:
                    ht.hydra_texture.set_updates_enabled(False)
                self._lens_on[name] = False
                return
        except Exception as e:  # noqa: BLE001
            if on:
                raise RuntimeError(f"lens camera {name}: cannot turn it on ({type(e).__name__}: {e})") from e
            print(f"[isaaclab_scene] lens camera {name}: render switch unavailable ({type(e).__name__}: {e}); left on",
                  flush=True)
            self._lens_on[name] = True
            return
        for annotators in cam._rep_registry.values():
            for ann, ht in zip(annotators, hts):
                ann.detach()
                ann.attach([ht])
        for ht in hts:
            ht.hydra_texture.set_updates_enabled(True)
        self._lens_on[name] = True

    @staticmethod
    def _set_focal(cam: Any, focal: float) -> None:
        """A camera's USD focal length (mm), and Isaac Lab's intrinsic matrix computed from it."""
        import omni.usd

        omni.usd.set_prop_val(cam._sensor_prims[0].GetFocalLengthAttr(), float(focal))
        cam._update_intrinsic_matrices(cam._ALL_INDICES)

    def wrist_intrinsics(self, name: str, hfov_deg: Optional[float] = None) -> np.ndarray:
        """intrinsic_cv (3, 3) of wrist camera ``name`` ("wrist_right" | "wrist_left") rendered with this horizontal
        field of view (None: the camera's own lens): Isaac Lab's matrix from the USD camera's focal length and aperture
        (float32, as the USD attribute and Isaac Lab's matrix hold them), the one camera_info() reports for the default.
        Renders nothing and changes no camera."""
        if name not in self.cameras:
            raise ValueError(f"no wrist camera {name!r} (cameras: {sorted(self.cameras)})")
        f = wrist_focal(wrist_hfov(hfov_deg))
        if f == WRIST_CAM_FOCAL:
            return self.cameras[name].data.intrinsic_matrices[0].detach().cpu().numpy().astype(np.float64)
        w, h = self.cfg.camera_res
        fx = float(np.float32(w * float(np.float32(f)) / float(np.float32(WRIST_CAM_APERTURE))))
        return np.array([[fx, 0.0, w * 0.5], [0.0, fx, h * 0.5], [0.0, 0.0, 1.0]], dtype=np.float64)

    def _render(self, depth: bool, cams: Optional[Dict[str, Any]] = None) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        self.sim.render()
        for name, cam in (self.cameras if cams is None else cams).items():
            cam.update(self.cfg.control_dt, force_recompute=True)
            rgb = cam.data.output["rgb"][0]
            rgb = rgb.detach().cpu().numpy() if hasattr(rgb, "detach") else np.asarray(rgb)
            if rgb.ndim == 3 and rgb.shape[-1] == 4:
                rgb = rgb[..., :3]
            out[f"{name}_rgb"] = np.ascontiguousarray(rgb.astype(np.uint8))
            if depth and "distance_to_image_plane" in cam.data.output:
                z = cam.data.output["distance_to_image_plane"][0]
                z = (z.detach().cpu().numpy() if hasattr(z, "detach") else np.asarray(z)).astype(np.float32)
                z = z.reshape(z.shape[0], z.shape[1])
                z[~np.isfinite(z)] = 0.0
                out[f"{name}_depth"] = np.ascontiguousarray(z)
        return out

    def camera_info(self) -> Dict[str, Dict[str, np.ndarray]]:
        """Per wrist camera, at its last render: ``intrinsic_cv`` (3, 3), ``pos_w`` (3,) and ``quat_w_cv`` (wxyz; OpenCV
        axes: x right, y down, z forward), env frame."""
        out: Dict[str, Dict[str, np.ndarray]] = {}
        for name, cam in self.cameras.items():
            d = cam.data
            out[name] = {
                "intrinsic_cv": d.intrinsic_matrices[0].detach().cpu().numpy().astype(np.float64),
                "pos_w": d.pos_w[0].detach().cpu().numpy().astype(np.float64),
                "quat_w_cv": d.quat_w_ros[0].detach().cpu().numpy().astype(np.float64),
            }
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
