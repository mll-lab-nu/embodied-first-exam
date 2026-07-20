from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import genesis as gs
import genesis.utils.geom as gu
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.world import materials


_V1_TABLE_POS = (-0.1356786, 0.0, 0.45982145)
_V1_TABLE_SIZE = (1.5, 1.4, 0.9196429)
_V1_SURFACE_ORIGIN = (0.0, 0.0, 0.9196429)
_V1_ROBOT_MOUNT = (-0.570, 0.0, 0.9196429)
_V1_FOOTPRINT_MIN = (-0.154079, -0.094614)
_V1_FOOTPRINT_MAX = (0.071567, 0.094671)


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
    manifest: EntityManifest
    cameras: dict[str, Any]
    frames: TabletopFrames
    robot_footprint: RobotFootprintCheck


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
    """Build the frozen table, robot mount, and camera rig shared by tasks."""

    def __init__(
        self,
        env_cfg,
        robot_cfg,
        *,
        rigid_options=None,
        pbd_options=None,
        debug_label: str | None = None,
    ) -> None:
        self.env_cfg = env_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options
        self.pbd_options = pbd_options
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
    ) -> TabletopBaseScene:
        self._debug("validate_begin")
        self._validate_locked_preset()
        frames = self._frames()
        footprint = self._validate_geometry(frames)
        self._debug("validate_done")
        scene_kwargs = {}
        if self.rigid_options is not None:
            scene_kwargs["rigid_options"] = self.rigid_options
        if self.pbd_options is not None:
            scene_kwargs["pbd_options"] = self.pbd_options
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
            show_viewer=show_viewer,
            **scene_kwargs,
        )
        self._debug("scene_construct_done")
        manifest = EntityManifest()

        if bool(self.env_cfg.world.plane.enabled):
            self._debug("ground_add_begin")
            manifest.add("ground", scene.add_entity(gs.morphs.Plane(), name="ground"))
            self._debug("ground_add_done")

        table_cfg = self.env_cfg.world.table
        self._debug("table_add_begin")
        manifest.add(
            "table",
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(table_cfg.pos),
                    size=tuple(table_cfg.size),
                    fixed=True,
                ),
                surface=materials.plastic("table", table_cfg.color),
                name="table",
            ),
        )
        self._debug("table_add_done")
        self._add_table_frame(scene, manifest, table_cfg, frames)

        stage_cfg = getattr(self.env_cfg.world, "stage", None)
        if stage_cfg is not None and bool(getattr(stage_cfg, "enabled", True)):
            self._debug("stage_add_begin")
            manifest.add(
                "stage",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(stage_cfg.pos),
                        size=tuple(stage_cfg.size),
                        fixed=True,
                    ),
                    surface=materials.plastic("stage", stage_cfg.color),
                    name="stage",
                ),
            )
            self._debug("stage_add_done")

        if include_robot:
            self._debug("robot_add_begin")
            robot_kwargs = {} if robot_material is None else {"material": robot_material}
            manifest.add(
                "robot",
                scene.add_entity(
                    gs.morphs.MJCF(
                        file=self.robot_cfg.robot.asset,
                        pos=tuple(self.env_cfg.robot_mount.pos),
                        euler=tuple(self.env_cfg.robot_mount.euler),
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
                camera = scene.add_camera(
                    res=tuple(camera_cfg.res),
                    pos=tuple(camera_cfg.pos),
                    lookat=tuple(camera_cfg.lookat),
                    up=tuple(camera_cfg.up),
                    fov=float(camera_cfg.fov),
                    near=float(getattr(camera_cfg, "near", 0.1)),
                    far=float(getattr(camera_cfg, "far", 20.0)),
                    debug=bool(getattr(camera_cfg, "debug", False)),
                    GUI=False,
                )
                attach_cfg = getattr(camera_cfg, "attach", None)
                if attach_cfg is not None and bool(getattr(attach_cfg, "enabled", True)):
                    self._attach_camera(camera_name, camera, attach_cfg, manifest, include_robot)
                cameras[str(camera_name)] = camera
                self._debug(f"camera_add_done:{camera_name}")

        return TabletopBaseScene(
            scene=scene,
            manifest=manifest,
            cameras=cameras,
            frames=frames,
            robot_footprint=footprint,
        )

    def _add_table_frame(self, scene, manifest: EntityManifest, table_cfg, frames: TabletopFrames) -> None:
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
        inner_len_y = size_y - 2.0 * band_width

        # x-side bars span the full depth (they own the corners); y-side bars
        # fill the remaining inner span so the four bars read as one picture frame.
        bars = [
            ("x_min", (min_x + 0.5 * band_width, float(table_pos[1]), z_center), (band_width, size_y, height)),
            ("x_max", (max_x - 0.5 * band_width, float(table_pos[1]), z_center), (band_width, size_y, height)),
            ("y_min", (float(table_pos[0]), min_y + 0.5 * band_width, z_center), (inner_len_y, band_width, height)),
            ("y_max", (float(table_pos[0]), max_y - 0.5 * band_width, z_center), (inner_len_y, band_width, height)),
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
        surface = materials.plastic("frame", color)
        for label, pos, size in bars:
            name = f"table_frame_{label}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(pos=pos, size=size, fixed=True, collision=False),
                    surface=surface,
                    name=name,
                ),
            )

    def finalize(self, base_scene: TabletopBaseScene) -> None:
        base_scene.scene.build(n_envs=self.env_cfg.sim.n_envs)
        for camera in base_scene.cameras.values():
            if getattr(camera, "_attached_link", None) is not None:
                camera.move_to_attach()

    def _attach_camera(
        self,
        camera_name: str,
        camera,
        attach_cfg,
        manifest: EntityManifest,
        include_robot: bool,
    ) -> None:
        entity_name = str(getattr(attach_cfg, "entity", "robot"))
        if entity_name == "robot" and not include_robot:
            self._debug(f"camera_attach_skipped:{camera_name}:robot_not_included")
            return

        entity = manifest.get(entity_name)
        link_name = str(getattr(attach_cfg, "link", "hand"))
        link = entity.get_link(link_name)

        if hasattr(attach_cfg, "offset_T"):
            offset_T = _matrix4(attach_cfg.offset_T, f"cameras.{camera_name}.attach.offset_T")
        else:
            offset_pos = _vec3(
                getattr(attach_cfg, "offset_pos", [0.0, 0.0, 0.0]),
                f"cameras.{camera_name}.attach.offset_pos",
            )
            offset_lookat = _vec3(
                getattr(attach_cfg, "offset_lookat", [0.1, 0.0, 0.0]),
                f"cameras.{camera_name}.attach.offset_lookat",
            )
            offset_up = _vec3(
                getattr(attach_cfg, "offset_up", [0.0, 0.0, 1.0]),
                f"cameras.{camera_name}.attach.offset_up",
            )
            offset_T = gu.pos_lookat_up_to_T(offset_pos, offset_lookat, offset_up)

        camera.attach(link, offset_T)

    def _frames(self) -> TabletopFrames:
        return tabletop_frames_from_config(self.env_cfg)

    def _validate_locked_preset(self) -> None:
        preset_cfg = getattr(self.env_cfg, "preset", None)
        if preset_cfg is None or not bool(getattr(preset_cfg, "locked", False)):
            return
        preset_id = str(getattr(preset_cfg, "id", ""))
        if preset_id != "topogym_tabletop_v1":
            raise ValueError(f"Unknown locked tabletop preset {preset_id!r}.")
        if str(getattr(preset_cfg, "version", "")) != "1.3":
            raise ValueError(
                "Locked topogym_tabletop_v1 requires preset.version=1.3."
            )

        self._require_close(
            self.env_cfg.world.table.pos,
            _V1_TABLE_POS,
            "world.table.pos",
        )
        self._require_close(
            self.env_cfg.world.table.size,
            _V1_TABLE_SIZE,
            "world.table.size",
        )
        self._require_close(
            self.env_cfg.frames.table_surface.origin,
            _V1_SURFACE_ORIGIN,
            "frames.table_surface.origin",
        )
        self._require_close(
            self.env_cfg.frames.task.origin,
            _V1_SURFACE_ORIGIN,
            "frames.task.origin",
        )
        self._require_close(
            self.env_cfg.robot_mount.pos,
            _V1_ROBOT_MOUNT,
            "robot_mount.pos",
        )
        self._require_close(
            self.env_cfg.robot_mount.footprint_min,
            _V1_FOOTPRINT_MIN,
            "robot_mount.footprint_min",
        )
        self._require_close(
            self.env_cfg.robot_mount.footprint_max,
            _V1_FOOTPRINT_MAX,
            "robot_mount.footprint_max",
        )
        if str(getattr(self.env_cfg.robot_mount, "mobility", "")) != "fixed":
            raise ValueError(
                "Locked topogym_tabletop_v1 requires robot_mount.mobility=fixed."
            )
        self._require_close(self.env_cfg.sim.gravity, (0.0, 0.0, -9.81), "sim.gravity")
        if abs(float(self.env_cfg.sim.dt) - 0.01) > 1e-12:
            raise ValueError("Locked topogym_tabletop_v1 requires sim.dt=0.01.")
        if int(self.env_cfg.sim.substeps) != 4:
            raise ValueError("Locked topogym_tabletop_v1 requires sim.substeps=4.")

        base_camera = self.env_cfg.cameras.base_camera
        if tuple(int(value) for value in base_camera.res) != (256, 256):
            raise ValueError(
                "Locked topogym_tabletop_v1 requires base_camera.res=[256, 256]."
            )
        self._require_close(
            base_camera.pos,
            (0.30, 0.00, 1.3196429),
            "cameras.base_camera.pos",
        )
        self._require_close(
            base_camera.lookat,
            (0.00, 0.00, 0.7196429),
            "cameras.base_camera.lookat",
        )
        if abs(float(base_camera.fov) - 90.0) > 1e-9:
            raise ValueError(
                "Locked topogym_tabletop_v1 requires base_camera.fov=90."
            )

    @staticmethod
    def _require_close(actual, expected, name: str, *, atol: float = 1e-7) -> None:
        actual_array = np.asarray(list(actual), dtype=float)
        expected_array = np.asarray(list(expected), dtype=float)
        if actual_array.shape != expected_array.shape or not np.allclose(
            actual_array,
            expected_array,
            rtol=0.0,
            atol=atol,
        ):
            raise ValueError(
                f"Locked topogym_tabletop_v1 requires {name}="
                f"{expected_array.tolist()}; got {actual_array.tolist()}."
            )

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
