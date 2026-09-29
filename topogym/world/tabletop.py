from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import genesis.utils.geom as gu
import numpy as np
from omegaconf import OmegaConf
from topogym.assets.robot import robot_asset

from topogym.world.entities import EntityRegistry
from topogym.world.visuals import lighting, surfaces


def _vec3(value, name: str) -> np.ndarray:
    result = np.asarray(_plain_config(value), dtype=float)
    if result.shape != (3,):
        raise ValueError(f"{name} must contain exactly 3 values; got shape {result.shape}.")
    return result


def _vec2(value, name: str) -> np.ndarray:
    result = np.asarray(_plain_config(value), dtype=float)
    if result.shape != (2,):
        raise ValueError(f"{name} must contain exactly 2 values; got shape {result.shape}.")
    return result


def _matrix4(value, name: str) -> np.ndarray:
    result = np.asarray(_plain_config(value), dtype=float)
    if result.shape != (4, 4):
        raise ValueError(f"{name} must be a 4x4 matrix; got shape {result.shape}.")
    return result


def _plain_config(value):
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class TabletopFrames:
    """World-space origins for the standard tabletop coordinate frames."""

    table_surface_origin: tuple[float, float, float]
    task_origin: tuple[float, float, float]

    def task_to_world(self, position) -> np.ndarray:
        return np.asarray(self.task_origin, dtype=float) + _vec3(position, "task position")

    def task_z_to_world(self, z: float) -> float:
        return float(self.task_origin[2]) + float(z)


@dataclass(frozen=True)
class RobotFootprintCheck:
    table_min_xy: tuple[float, float]
    table_max_xy: tuple[float, float]
    footprint_min_xy: tuple[float, float]
    footprint_max_xy: tuple[float, float]
    clearance_xy: tuple[float, float, float, float]
    edge_margin: float


@dataclass
class TabletopBaseScene:
    scene: Any
    entity_registry: EntityRegistry
    cameras: dict[str, Any]
    frames: TabletopFrames
    robot_footprint: RobotFootprintCheck
    presentation: dict = field(default_factory=dict)

def tabletop_frames_from_config(env_cfg) -> TabletopFrames:
    """Resolve standard tabletop frames without constructing a Genesis scene."""

    table_cfg = env_cfg.world.table
    table_pos = _vec3(table_cfg.pos, "world.table.pos")
    table_size = _vec3(table_cfg.size, "world.table.size")
    derived_surface = np.array(
        [0.0, 0.0, table_pos[2] + 0.5 * table_size[2]],
        dtype=float,
    )
    frame_cfg = getattr(env_cfg, "frames", None)
    if frame_cfg is None:
        table_surface = derived_surface
        task_origin = np.zeros(3, dtype=float)
    else:
        table_surface = _vec3(
            frame_cfg.table_surface.origin,
            "frames.table_surface.origin",
        )
        task_origin = _vec3(frame_cfg.task.origin, "frames.task.origin")
    return TabletopFrames(
        table_surface_origin=tuple(float(value) for value in table_surface),
        task_origin=tuple(float(value) for value in task_origin),
    )


class StandardTabletopSceneBuilder:
    """Build the configured tabletop, robot mount, and camera rig shared by tasks."""

    def __init__(
        self,
        env_cfg,
        robot_cfg,
        *,
        rigid_options=None,
        pbd_options=None,
        scene_options: dict | None = None,
        debug_label: str | None = None,
    ) -> None:
        self.env_cfg = env_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options
        self.pbd_options = pbd_options
        # Extra gs.Scene kwargs from a rope backend (rope_backends protocol):
        # {"pbd_options": ...} for PBD, {"coupler_options"/"fem_options": ...}
        # for FEM+IPC. Supersedes the pbd_options parameter for callers that
        # have moved to the backend seam.
        self.scene_options = scene_options
        self.debug_label = debug_label

    def _debug(self, stage: str) -> None:
        if self.debug_label:
            print(f"{self.debug_label}={stage}", flush=True)

    def create(
        self,
        *,
        show_viewer: bool = False,
        include_robot: bool = True,
        robot_material=None,
        robot_morph_options: dict | None = None,
        table_material=None,
        static_material=None,
        decoration_material=None,
    ) -> TabletopBaseScene:
        """Build the shared tabletop scene.

        ``table_material`` overrides the table's rigid material. The one property
        tasks reach for is ``coup_friction`` -- how much a deformable body grips
        the table. It defaults to 0.1 in Genesis, which is slippery enough that a
        PBD rope slides around under its own residual motion, and it is a
        *separate* knob from the PBD material's own ``static/kinetic_friction``
        (those govern particle-to-particle contact, i.e. rope-on-rope). The
        coupler reads ``geoms_info.coup_friction`` of the rigid geom for
        deformable-vs-rigid contact, so the two can be tuned independently.
        """
        self._debug("validate_begin")
        frames = self._frames()
        footprint = self._validate_geometry(frames)
        self._debug("validate_done")
        scene_kwargs = {}
        if self.rigid_options is not None:
            scene_kwargs["rigid_options"] = self.rigid_options
        if self.pbd_options is not None:
            scene_kwargs["pbd_options"] = self.pbd_options
        renderer = self._select_renderer()
        if renderer is not None:
            scene_kwargs["renderer"] = renderer
        # Explicit scene options can override Genesis' viewer/calibration
        # renderer. Nyx RGB sensors are registered separately in finalize().
        if self.scene_options:
            scene_kwargs.update(self.scene_options)
        viewer_kwargs = {
            "camera_pos": tuple(self.env_cfg.viewer.camera_pos),
            "camera_lookat": tuple(self.env_cfg.viewer.camera_lookat),
            "camera_fov": self.env_cfg.viewer.camera_fov,
            "max_FPS": self.env_cfg.viewer.max_fps,
        }
        viewer_run_in_thread = getattr(self.env_cfg.viewer, "run_in_thread", None)
        if viewer_run_in_thread is not None:
            viewer_kwargs["run_in_thread"] = bool(viewer_run_in_thread)

        self._debug("scene_construct_begin")
        scene = gs.Scene(
            sim_options=gs.options.SimOptions(
                dt=self.env_cfg.sim.dt,
                substeps=self.env_cfg.sim.substeps,
                gravity=tuple(self.env_cfg.sim.gravity),
            ),
            viewer_options=gs.options.ViewerOptions(**viewer_kwargs),
            vis_options=lighting.vis_options(self.env_cfg),
            show_viewer=show_viewer,
            **scene_kwargs,
        )
        self._scene_under_construction = scene
        self._debug("scene_construct_done")
        entity_registry = EntityRegistry()

        # ``static_material`` covers the fixed rigids the builder creates itself
        # (ground plane, stage). Under the IPC coupler these must be declared
        # coup_type='ipc_only' -- the auto-select trips over their base joint --
        # while under the legacy coupler None keeps the Genesis default.
        static_kwargs = {} if static_material is None else {"material": static_material}
        # Collision-free fixtures (the table frame rim) get their own material:
        # under IPC they must be needs_coup=False -- no collision geometry can
        # satisfy any coupling type -- which is also behaviorally identical to
        # what they already are.
        self._decoration_kwargs = (
            {} if decoration_material is None else {"material": decoration_material}
        )

        if bool(self.env_cfg.world.plane.enabled):
            self._debug("ground_add_begin")
            entity_registry.add(
                "ground",
                scene.add_entity(gs.morphs.Plane(), name="ground", **static_kwargs),
            )
            self._debug("ground_add_done")

        table_cfg = self.env_cfg.world.table
        self._debug("table_add_begin")
        table_kwargs = {} if table_material is None else {"material": table_material}
        entity_registry.add(
            "table",
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(table_cfg.pos),
                    size=tuple(table_cfg.size),
                    fixed=True,
                ),
                surface=surfaces.plastic("table", table_cfg.color),
                name="table",
                **table_kwargs,
            ),
        )
        self._debug("table_add_done")
        self._add_table_frame(scene, entity_registry, table_cfg, frames)

        stage_cfg = getattr(self.env_cfg.world, "stage", None)
        if stage_cfg is not None and bool(getattr(stage_cfg, "enabled", True)):
            self._debug("stage_add_begin")
            entity_registry.add(
                "stage",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(stage_cfg.pos),
                        size=tuple(stage_cfg.size),
                        fixed=True,
                    ),
                    surface=surfaces.plastic("stage", stage_cfg.color),
                    name="stage",
                    **static_kwargs,
                ),
            )
            self._debug("stage_add_done")

        if include_robot:
            self._debug("robot_add_begin")
            robot_kwargs = {} if robot_material is None else {"material": robot_material}
            entity_registry.add(
                "robot",
                scene.add_entity(
                    gs.morphs.MJCF(
                        file=robot_asset(self.robot_cfg),
                        pos=tuple(self.env_cfg.robot_mount.pos),
                        euler=tuple(self.env_cfg.robot_mount.euler),
                        **(robot_morph_options or {}),
                    ),
                    name="robot",
                    **robot_kwargs,
                ),
            )
            self._debug("robot_add_done")

        cameras: dict[str, Any] = {}
        camera_cfgs = getattr(self.env_cfg, "cameras", None)
        if camera_cfgs is not None:
            for camera_name, camera_cfg in camera_cfgs.items():
                self._debug(f"camera_add_begin:{camera_name}")
                from topogym.sensors.cameras import create_camera
                camera = create_camera(scene, camera_cfg, entity_registry,
                                       name=str(camera_name), include_robot=include_robot)
                cameras[str(camera_name)] = camera
                self._debug(f"camera_add_done:{camera_name}")

        return TabletopBaseScene(
            scene=scene,
            entity_registry=entity_registry,
            cameras=cameras,
            frames=frames,
            robot_footprint=footprint,
        )

    def _add_table_frame(self, scene, entity_registry: EntityRegistry, table_cfg, frames: TabletopFrames) -> None:
        """Add a purely-decorative border rim around the table top perimeter.

        Applies to every task that builds through this shared tabletop. The rim
        is ``collision=False`` so it never affects physics, and sits at the far
        table edge (~0.5m from the central workspace) so it is never in the way.
        Tune or disable via ``env.world.table.frame`` in config.
        """

        frame_cfg = getattr(table_cfg, "frame", None)
        if frame_cfg is not None and not bool(getattr(frame_cfg, "enabled", True)):
            return

        def _cfg(name: str, default):
            if frame_cfg is None:
                return default
            return getattr(frame_cfg, name, default)

        band_width = float(_cfg("band_width", 0.06))
        height = float(_cfg("height", 0.015))
        color = tuple(_plain_config(_cfg("color", [0.40, 0.26, 0.14])))
        if band_width <= 0.0 or height <= 0.0:
            return

        table_pos = _vec3(table_cfg.pos, "world.table.pos")
        table_size = _vec3(table_cfg.size, "world.table.size")
        surface_z = float(frames.table_surface_origin[2])
        size_x, size_y, size_z = (
            float(table_size[0]),
            float(table_size[1]),
            float(table_size[2]),
        )
        if band_width >= 0.5 * min(size_x, size_y):
            return
        min_x = float(table_pos[0]) - 0.5 * size_x
        max_x = float(table_pos[0]) + 0.5 * size_x
        min_y = float(table_pos[1]) - 0.5 * size_y
        max_y = float(table_pos[1]) + 0.5 * size_y
        z_center = surface_z + 0.5 * height
        # x-side bars run the full depth (size_y) and own the corners; y-side bars
        # run along x and fill the span *between* those corner bars, so their length
        # must come from size_x (not size_y) or they fall short when the table is not
        # square and leave a gap at each corner.
        inner_len_x = size_x - 2.0 * band_width

        bars = [
            ("x_min", (min_x + 0.5 * band_width, float(table_pos[1]), z_center), (band_width, size_y, height)),
            ("x_max", (max_x - 0.5 * band_width, float(table_pos[1]), z_center), (band_width, size_y, height)),
            ("y_min", (float(table_pos[0]), min_y + 0.5 * band_width, z_center), (inner_len_x, band_width, height)),
            ("y_max", (float(table_pos[0]), max_y - 0.5 * band_width, z_center), (inner_len_x, band_width, height)),
        ]

        # Same-colored panels wrapping the four vertical side faces (table apron).
        if bool(_cfg("sides", True)):
            side_thickness = float(_cfg("side_thickness", 0.012))
            side_z = float(table_pos[2])
            if side_thickness > 0.0:
                bars.extend(
                    [
                        ("side_x_min", (min_x - 0.5 * side_thickness, float(table_pos[1]), side_z),
                         (side_thickness, size_y + 2.0 * side_thickness, size_z)),
                        ("side_x_max", (max_x + 0.5 * side_thickness, float(table_pos[1]), side_z),
                         (side_thickness, size_y + 2.0 * side_thickness, size_z)),
                        ("side_y_min", (float(table_pos[0]), min_y - 0.5 * side_thickness, side_z),
                         (size_x, side_thickness, size_z)),
                        ("side_y_max", (float(table_pos[0]), max_y + 0.5 * side_thickness, side_z),
                         (size_x, side_thickness, size_z)),
                    ]
                )
        surface = surfaces.plastic("frame", color)
        decoration_kwargs = getattr(self, "_decoration_kwargs", {})
        for label, pos, size in bars:
            name = f"table_frame_{label}"
            entity_registry.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(pos=pos, size=size, fixed=True, collision=False),
                    surface=surface,
                    name=name,
                    **decoration_kwargs,
                ),
            )

    def finalize(self, base_scene: TabletopBaseScene) -> None:
        from topogym.world.visuals.presentation import prepare_presentation

        base_scene.presentation = prepare_presentation(
            base_scene.scene, base_scene.entity_registry, self.env_cfg, base_scene.cameras,
        )
        base_scene.scene.build(n_envs=self.env_cfg.sim.n_envs)
        for camera in base_scene.cameras.values():
            if getattr(camera, "_attached_link", None) is not None:
                camera.move_to_attach()

    def _frames(self) -> TabletopFrames:
        return tabletop_frames_from_config(self.env_cfg)

    def _select_renderer(self):
        """Nyx supplies RGB; Genesis cameras retain poses and calibration only."""
        kind = str(getattr(getattr(self.env_cfg, "renderer", None), "type", "nyx"))
        n_envs = int(getattr(self.env_cfg.sim, "n_envs", 0) or 0)
        if kind != "nyx":
            raise ValueError("Simulator RGB requires env.renderer.type=nyx")
        if n_envs != 0:
            raise ValueError("The shared simulator currently requires env.sim.n_envs=0")
        if self.env_cfg.get("cameras") and gs.backend != gs.cuda:
            raise ValueError("Nyx RGB requires CUDA; disable RGB for CPU physics")
        return None  # Nyx sensors are registered in finalize(), before build().

    def _validate_geometry(self, frames: TabletopFrames) -> RobotFootprintCheck:
        table_cfg = self.env_cfg.world.table
        table_pos = _vec3(table_cfg.pos, "world.table.pos")
        table_size = _vec3(table_cfg.size, "world.table.size")
        if np.any(table_size <= 0.0):
            raise ValueError(f"world.table.size must be positive; got {table_size.tolist()}.")

        table_min = table_pos - 0.5 * table_size
        table_max = table_pos + 0.5 * table_size
        surface_z = float(frames.table_surface_origin[2])
        surface_error = abs(float(table_max[2]) - surface_z)
        tolerance = float(getattr(table_cfg, "surface_tolerance", 1e-6))
        if surface_error > tolerance:
            raise ValueError(
                "Table surface frame does not match the table collision top: "
                f"frame_z={surface_z:.7f}, collision_top_z={table_max[2]:.7f}, "
                f"error={surface_error:.7f}."
            )

        mount_cfg = self.env_cfg.robot_mount
        mount_pos = _vec3(mount_cfg.pos, "robot_mount.pos")
        mount_tolerance = float(getattr(mount_cfg, "surface_tolerance", 1e-6))
        mount_error = abs(float(mount_pos[2]) - surface_z)
        if mount_error > mount_tolerance:
            raise ValueError(
                "Robot mounting plane must coincide with the table surface: "
                f"mount_z={mount_pos[2]:.7f}, table_surface_z={surface_z:.7f}, "
                f"error={mount_error:.7f}."
            )

        footprint_min_cfg = getattr(mount_cfg, "footprint_min", None)
        footprint_max_cfg = getattr(mount_cfg, "footprint_max", None)
        if footprint_min_cfg is not None or footprint_max_cfg is not None:
            if footprint_min_cfg is None or footprint_max_cfg is None:
                raise ValueError(
                    "robot_mount.footprint_min and footprint_max must be "
                    "configured together."
                )
            footprint_offset_min = _vec2(
                footprint_min_cfg,
                "robot_mount.footprint_min",
            )
            footprint_offset_max = _vec2(
                footprint_max_cfg,
                "robot_mount.footprint_max",
            )
            if np.any(footprint_offset_min >= footprint_offset_max):
                raise ValueError(
                    "robot_mount footprint bounds must satisfy min < max; "
                    f"got {footprint_offset_min.tolist()}.."
                    f"{footprint_offset_max.tolist()}."
                )
        else:
            footprint_size = _vec2(
                getattr(mount_cfg, "footprint_size", (0.20, 0.20)),
                "robot_mount.footprint_size",
            )
            if np.any(footprint_size <= 0.0):
                raise ValueError(
                    "robot_mount.footprint_size must be a positive XY size so "
                    "the mount can be checked against the table."
                )
            footprint_offset_min = -0.5 * footprint_size
            footprint_offset_max = 0.5 * footprint_size
        margin = float(getattr(mount_cfg, "edge_margin", 0.0))
        if margin < 0.0:
            raise ValueError("robot_mount.edge_margin must be non-negative.")

        footprint_min = mount_pos[:2] + footprint_offset_min
        footprint_max = mount_pos[:2] + footprint_offset_max
        allowed_min = table_min[:2] + margin
        allowed_max = table_max[:2] - margin
        if np.any(footprint_min < allowed_min) or np.any(footprint_max > allowed_max):
            raise ValueError(
                "Robot base footprint is not strictly inside the table area: "
                f"table_xy={table_min[:2].tolist()}..{table_max[:2].tolist()}, "
                f"footprint_xy={footprint_min.tolist()}..{footprint_max.tolist()}, "
                f"required_margin={margin:.4f}."
            )

        stage_cfg = getattr(self.env_cfg.world, "stage", None)
        if stage_cfg is not None and bool(getattr(stage_cfg, "enabled", True)):
            stage_pos = _vec3(stage_cfg.pos, "world.stage.pos")
            stage_size = _vec3(stage_cfg.size, "world.stage.size")
            stage_min = stage_pos - 0.5 * stage_size
            stage_max = stage_pos + 0.5 * stage_size
            if np.any(stage_min[:2] < table_min[:2]) or np.any(stage_max[:2] > table_max[:2]):
                raise ValueError(
                    "The shared manipulation stage must fit on the table: "
                    f"stage_xy={stage_min[:2].tolist()}..{stage_max[:2].tolist()}, "
                    f"table_xy={table_min[:2].tolist()}..{table_max[:2].tolist()}."
                )
            stage_bottom_error = abs(float(stage_min[2]) - surface_z)
            if stage_bottom_error > tolerance:
                raise ValueError(
                    "The shared manipulation stage must rest on the table surface: "
                    f"stage_bottom_z={stage_min[2]:.7f}, table_surface_z={surface_z:.7f}."
                )

        clearances = (
            float(footprint_min[0] - table_min[0]),
            float(table_max[0] - footprint_max[0]),
            float(footprint_min[1] - table_min[1]),
            float(table_max[1] - footprint_max[1]),
        )
        return RobotFootprintCheck(
            table_min_xy=tuple(float(value) for value in table_min[:2]),
            table_max_xy=tuple(float(value) for value in table_max[:2]),
            footprint_min_xy=tuple(float(value) for value in footprint_min),
            footprint_max_xy=tuple(float(value) for value in footprint_max),
            clearance_xy=clearances,
            edge_margin=margin,
        )
