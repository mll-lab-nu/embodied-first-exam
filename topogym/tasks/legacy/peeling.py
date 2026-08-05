from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0]


def _yaw_quat(yaw: float) -> tuple[float, float, float, float]:
    half = 0.5 * float(yaw)
    return (float(np.cos(half)), 0.0, 0.0, float(np.sin(half)))


def _rotate_xy(offset, yaw: float) -> np.ndarray:
    offset = np.asarray(offset, dtype=float)
    c = float(np.cos(float(yaw)))
    s = float(np.sin(float(yaw)))
    return np.array(
        [
            c * offset[0] - s * offset[1],
            s * offset[0] + c * offset[1],
        ],
        dtype=float,
    )


def _polygon_axes(corners: np.ndarray) -> list[np.ndarray]:
    axes: list[np.ndarray] = []
    for index in range(len(corners)):
        edge = corners[(index + 1) % len(corners)] - corners[index]
        normal = np.array([-edge[1], edge[0]], dtype=float)
        norm = float(np.linalg.norm(normal))
        if norm > 1e-9:
            axes.append(normal / norm)
    return axes


def _polygons_overlap(a: np.ndarray, b: np.ndarray, *, tolerance: float = 0.0) -> bool:
    for axis in [*_polygon_axes(a), *_polygon_axes(b)]:
        a_proj = a @ axis
        b_proj = b @ axis
        if float(a_proj.max()) < float(b_proj.min()) - tolerance:
            return False
        if float(b_proj.max()) < float(a_proj.min()) - tolerance:
            return False
    return True


@dataclass(frozen=True)
class PeelingLayout:
    """Geometry and semantic peel-zone logic for the Level 1 peeling task."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def world_z(self, z: float) -> float:
        """Config z -> Genesis world z (task frame adds the tabletop origin height)."""
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        return float(z)

    def to_world(self, pos) -> np.ndarray:
        """Config position -> Genesis world position (task frame adds task_origin)."""
        pos = np.asarray(pos, dtype=float)
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        return pos

    def film_names(self) -> list[str]:
        return [str(name) for name in self.cfg.films.keys()]

    def film(self, film_name: str):
        return self.cfg.films[str(film_name)]

    def film_label(self, film_name: str) -> str:
        return str(getattr(self.film(film_name), "label", film_name))

    def film_pos(self, film_name: str) -> np.ndarray:
        return self.to_world(_list(self.film(film_name).pos))

    def film_size(self, film_name: str) -> np.ndarray:
        return np.asarray(_list(self.film(film_name).size), dtype=float)

    def film_yaw(self, film_name: str) -> float:
        return float(getattr(self.film(film_name), "yaw", 0.0))

    def film_layer(self, film_name: str) -> int:
        return int(getattr(self.film(film_name), "layer", 0))

    def film_corners_xy(self, film_name: str) -> np.ndarray:
        center = self.film_pos(film_name)[:2]
        size = self.film_size(film_name)
        yaw = self.film_yaw(film_name)
        hx = 0.5 * float(size[0])
        hy = 0.5 * float(size[1])
        local = np.array(
            [
                [-hx, -hy],
                [hx, -hy],
                [hx, hy],
                [-hx, hy],
            ],
            dtype=float,
        )
        return np.array([center + _rotate_xy(point, yaw) for point in local], dtype=float)

    def film_top_z(self, film_name: str) -> float:
        pos = self.film_pos(film_name)
        return float(pos[2] + 0.5 * self.film_size(film_name)[2])

    def zone_corner(self, film_name: str) -> str:
        return str(getattr(self.film(film_name).peel_zone, "corner", "upper_right"))

    def zone_center(self, film_name: str) -> np.ndarray:
        film = self.film(film_name)
        center = self.film_pos(film_name)
        size = self.film_size(film_name)
        inset = np.asarray(_list(getattr(film.peel_zone, "inset", [0.015, 0.015])), dtype=float)
        sx, sy = self._corner_signs(self.zone_corner(film_name))
        local = np.array(
            [
                sx * max(0.0, 0.5 * float(size[0]) - float(inset[0])),
                sy * max(0.0, 0.5 * float(size[1]) - float(inset[1])),
            ],
            dtype=float,
        )
        xy = center[:2] + _rotate_xy(local, self.film_yaw(film_name))
        z = self.film_top_z(film_name) + float(getattr(self.cfg.peel_zones, "z_offset", 0.006))
        return np.array([xy[0], xy[1], z], dtype=float)

    def zone_marker_positions(self, film_name: str) -> list[np.ndarray]:
        marker_cfg = self.cfg.peel_zones.marker
        center = self.zone_center(film_name)
        marker_size = np.asarray(_list(marker_cfg.zone_size), dtype=float)
        dash_count = max(2, int(getattr(marker_cfg, "dash_count_per_side", 4)))
        hx = 0.5 * float(marker_size[0])
        hy = 0.5 * float(marker_size[1])
        local_points: list[np.ndarray] = []
        for alpha in np.linspace(-1.0, 1.0, dash_count):
            local_points.append(np.array([alpha * hx, -hy], dtype=float))
            local_points.append(np.array([alpha * hx, hy], dtype=float))
            local_points.append(np.array([-hx, alpha * hy], dtype=float))
            local_points.append(np.array([hx, alpha * hy], dtype=float))
        yaw = self.film_yaw(film_name)
        return [
            np.array([*(center[:2] + _rotate_xy(point, yaw)), center[2]], dtype=float)
            for point in local_points
        ]

    def hidden_marker_pos(self, index: int) -> np.ndarray:
        return np.array([0.05 + 0.01 * int(index), 0.0, -1.0], dtype=float)

    def higher_overlapping_films(self, film_name: str, *, peeled: tuple[str, ...] = ()) -> tuple[str, ...]:
        peeled_set = set(peeled)
        if film_name in peeled_set:
            return ()
        film_layer = self.film_layer(film_name)
        film_poly = self.film_corners_xy(film_name)
        tolerance = float(getattr(self.cfg.peel_zones, "overlap_tolerance", 0.002))
        blockers: list[str] = []
        for other_name in self.film_names():
            if other_name == film_name or other_name in peeled_set:
                continue
            if self.film_layer(other_name) <= film_layer:
                continue
            if _polygons_overlap(film_poly, self.film_corners_xy(other_name), tolerance=tolerance):
                blockers.append(other_name)
        return tuple(blockers)

    def is_zone_covered(self, film_name: str, *, peeled: tuple[str, ...] = ()) -> bool:
        zone_xy = self.zone_center(film_name)[:2]
        film_layer = self.film_layer(film_name)
        for other_name in self.film_names():
            if other_name == film_name or other_name in peeled:
                continue
            if self.film_layer(other_name) <= film_layer:
                continue
            if self.point_inside_film(zone_xy, other_name):
                return True
        return False

    def is_film_active(self, film_name: str, *, peeled: tuple[str, ...] = ()) -> bool:
        if film_name in peeled:
            return False
        if bool(getattr(self.cfg.peel_zones, "block_if_any_higher_overlap", True)):
            return len(self.higher_overlapping_films(film_name, peeled=peeled)) == 0
        return not self.is_zone_covered(film_name, peeled=peeled)

    def active_film_names(self, *, peeled: tuple[str, ...] = ()) -> tuple[str, ...]:
        return tuple(
            film_name
            for film_name in self.film_names()
            if self.is_film_active(film_name, peeled=peeled)
        )

    def point_inside_film(self, xy, film_name: str) -> bool:
        xy = np.asarray(xy, dtype=float)
        center = self.film_pos(film_name)[:2]
        local = _rotate_xy(xy - center, -self.film_yaw(film_name))
        half = 0.5 * self.film_size(film_name)[:2]
        tolerance = float(getattr(self.cfg.peel_zones, "overlap_tolerance", 0.002))
        return bool(np.all(np.abs(local) <= half + tolerance))

    def target_slot_pos(self, film_name: str) -> np.ndarray:
        return self.to_world(_list(self.cfg.separation_slots.slots[str(film_name)].pos))

    def target_film_pos(self, film_name: str) -> np.ndarray:
        slot_pos = self.target_slot_pos(film_name)
        film_size = self.film_size(film_name)
        surface_clearance = float(getattr(self.cfg.separation_slots, "surface_clearance", 0.0))
        if hasattr(self.cfg.separation_slots, "surface_z"):
            z = self.world_z(float(self.cfg.separation_slots.surface_z)) + surface_clearance + 0.5 * float(film_size[2])
        else:
            slot_size = np.asarray(_list(self.cfg.separation_slots.slot_size), dtype=float)
            z = float(slot_pos[2] + 0.5 * slot_size[2] + surface_clearance + 0.5 * film_size[2])
        return np.array(
            [
                slot_pos[0],
                slot_pos[1],
                z,
            ],
            dtype=float,
        )

    def oracle_sequence(self) -> tuple[str, ...]:
        oracle = getattr(self.cfg, "oracle", None)
        if oracle is not None and hasattr(oracle, "sequence"):
            return tuple(str(name) for name in oracle.sequence)
        return tuple(sorted(self.film_names(), key=lambda name: self.film_layer(name), reverse=True))

    @staticmethod
    def _corner_signs(corner: str) -> tuple[float, float]:
        aliases = {
            "upper_right": (1.0, 1.0),
            "top_right": (1.0, 1.0),
            "upper_left": (-1.0, 1.0),
            "top_left": (-1.0, 1.0),
            "lower_right": (1.0, -1.0),
            "bottom_right": (1.0, -1.0),
            "lower_left": (-1.0, -1.0),
            "bottom_left": (-1.0, -1.0),
        }
        try:
            return aliases[str(corner)]
        except KeyError as exc:
            raise ValueError(f"Unknown peel-zone corner {corner!r}.") from exc


@dataclass
class PeelingScene:
    scene: Any
    manifest: EntityManifest
    layout: PeelingLayout
    peeled: list[str] = field(default_factory=list)
    zone_markers: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    cameras: dict = field(default_factory=dict)


def apply_peel_zone_markers(peeling_scene: PeelingScene) -> None:
    layout = peeling_scene.layout
    if not peeling_scene.zone_markers:
        return
    active_films = set(layout.active_film_names(peeled=tuple(peeling_scene.peeled)))
    show_inactive = bool(getattr(layout.cfg.peel_zones.marker, "show_inactive", True))
    hidden_index = 0
    for film_name, marker_sets in peeling_scene.zone_markers.items():
        positions = layout.zone_marker_positions(film_name)
        visible_kind = None
        if film_name not in peeling_scene.peeled:
            if film_name in active_films:
                visible_kind = "active"
            elif show_inactive:
                visible_kind = "inactive"
        for kind, entities in marker_sets.items():
            for index, entity in enumerate(entities):
                pos = positions[index] if kind == visible_kind else layout.hidden_marker_pos(hidden_index)
                entity.set_pos(tuple(pos), zero_velocity=True)
                hidden_index += 1


class PeelingSceneBuilder:
    """Build the Level 1 tabletop peeling scene."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = getattr(env_cfg, "frames", None)
        task_frame = getattr(frames, "task", None) if frames is not None else None
        origin = getattr(task_frame, "origin", None) if task_frame is not None else None
        task_origin = tuple(float(v) for v in origin) if origin is not None else (0.0, 0.0, 0.0)
        self.layout = PeelingLayout(task_cfg, task_origin=task_origin)

    def build(self, *, show_viewer: bool = False) -> PeelingScene:
        # Use the shared standard tabletop (identical table + frame/border + cameras
        # + geometry validation as every other task) instead of a self-rolled scene.
        tabletop_builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg)
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest
        self.layout = PeelingLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)

        self._add_board(scene, manifest)
        self._add_substrate(scene, manifest)
        self._add_targets(scene, manifest)
        self._add_films(scene, manifest)
        zone_markers = self._add_peel_zone_markers(scene)

        tabletop_builder.finalize(tabletop)
        peeling_scene = PeelingScene(
            scene=scene,
            manifest=manifest,
            layout=self.layout,
            zone_markers=zone_markers,
            cameras=tabletop.cameras,
        )
        for film_name in self.layout.film_names():
            entity = manifest.get(film_name)
            entity.set_quat(_yaw_quat(self.layout.film_yaw(film_name)), zero_velocity=True, relative=False)
        apply_peel_zone_markers(peeling_scene)
        return peeling_scene

    def _add_board(self, scene, manifest: EntityManifest) -> None:
        if not box_entity_enabled(self.task_cfg.board):
            return
        manifest.add(
            self.task_cfg.board.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.to_world(_list(self.task_cfg.board.pos))),
                    size=tuple(self.task_cfg.board.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.board.color),
                name=self.task_cfg.board.name,
            ),
        )

    def _add_substrate(self, scene, manifest: EntityManifest) -> None:
        if not box_entity_enabled(self.task_cfg.substrate):
            return
        manifest.add(
            self.task_cfg.substrate.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.to_world(_list(self.task_cfg.substrate.pos))),
                    size=tuple(self.task_cfg.substrate.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.substrate.color),
                name=self.task_cfg.substrate.name,
            ),
        )

    def _add_targets(self, scene, manifest: EntityManifest) -> None:
        """Per-film target endpoints: a collision landing pad + concentric
        red/white rectangular rings (bullseye) sized to that film's footprint."""
        marker_cfg = getattr(self.task_cfg, "target_marker", None)
        if marker_cfg is None or not bool(getattr(marker_cfg, "enabled", True)):
            return
        slots = self.task_cfg.separation_slots.slots
        colors = [tuple(float(v) for v in _list(color)) for color in _list(marker_cfg.colors)]
        ring_count = int(getattr(marker_cfg, "ring_count", 3))
        outer_margin = float(getattr(marker_cfg, "outer_margin", 0.012))
        ring_step = float(getattr(marker_cfg, "ring_step", 0.016))
        height = float(getattr(marker_cfg, "height", 0.0006))
        z_gap = float(getattr(marker_cfg, "z_gap", 0.0002))
        collision = bool(getattr(marker_cfg, "collision", True))
        for film_name in self.layout.film_names():
            if str(film_name) not in slots:
                continue
            slot_pos = self.layout.to_world(_list(slots[str(film_name)].pos))
            fx, fy = (float(v) for v in self.layout.film_size(film_name)[:2])
            base_z = float(slot_pos[2])
            # Collision landing pad (films rest on it; sized to film + margin).
            manifest.add(
                f"peel_target_{film_name}_pad",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=(float(slot_pos[0]), float(slot_pos[1]), base_z + 0.5 * height),
                        size=(fx + 2.0 * outer_margin, fy + 2.0 * outer_margin, height),
                        fixed=True,
                        collision=collision,
                    ),
                    surface=materials.plastic("marker", colors[-1]),
                    name=f"peel_target_{film_name}_pad",
                ),
            )
            # Concentric red/white rectangular rings stacked as thin layers.
            for i in range(ring_count):
                sx = fx + 2.0 * outer_margin - 2.0 * i * ring_step
                sy = fy + 2.0 * outer_margin - 2.0 * i * ring_step
                if sx <= 0.004 or sy <= 0.004:
                    break
                center_z = base_z + height + z_gap + (i + 0.5) * height
                manifest.add(
                    f"peel_target_{film_name}_ring_{i}",
                    scene.add_entity(
                        gs.morphs.Box(
                            pos=(float(slot_pos[0]), float(slot_pos[1]), center_z),
                            size=(sx, sy, height),
                            fixed=True,
                            collision=False,
                        ),
                        surface=materials.plastic("marker", colors[i % len(colors)]),
                        name=f"peel_target_{film_name}_ring_{i}",
                    ),
                )

    def _add_films(self, scene, manifest: EntityManifest) -> None:
        for film_name in sorted(self.layout.film_names(), key=self.layout.film_layer):
            film = self.task_cfg.films[film_name]
            manifest.add(
                film_name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(self.layout.film_pos(film_name)),
                        size=tuple(film.size),
                        fixed=bool(getattr(film, "fixed", True)),
                        collision=bool(getattr(film, "collision", True)),
                        visualization=True,
                    ),
                    surface=materials.plastic("deformable", film.color),
                    name=film_name,
                ),
            )

    def _add_peel_zone_markers(self, scene) -> dict[str, dict[str, list[Any]]]:
        marker_cfg = self.task_cfg.peel_zones.marker
        if not bool(getattr(marker_cfg, "enabled", True)):
            return {}
        marker_size = tuple(marker_cfg.dash_size)
        zone_markers: dict[str, dict[str, list[Any]]] = {}
        dash_count = max(2, int(getattr(marker_cfg, "dash_count_per_side", 4)))
        dash_total = dash_count * 4
        hidden_index = 0
        for film_name in self.layout.film_names():
            zone_markers[film_name] = {"active": [], "inactive": []}
            for kind, color_attr in (("active", "active_color"), ("inactive", "inactive_color")):
                color = tuple(getattr(marker_cfg, color_attr))
                for index in range(dash_total):
                    entity = scene.add_entity(
                        gs.morphs.Box(
                            pos=tuple(self.layout.hidden_marker_pos(hidden_index)),
                            size=marker_size,
                            fixed=True,
                        ),
                        surface=materials.plastic("marker", color),
                        name=f"peel_zone_{film_name}_{kind}_{index:02d}",
                    )
                    zone_markers[film_name][kind].append(entity)
                    hidden_index += 1
        return zone_markers

    def _add_cameras(self, scene) -> dict:
        cameras: dict = {}
        cam_section = getattr(self.env_cfg, "cameras", None)
        if cam_section is None:
            return cameras
        for cam_name, cam_cfg in cam_section.items():
            cameras[cam_name] = scene.add_camera(
                res=tuple(cam_cfg.res),
                pos=tuple(cam_cfg.pos),
                lookat=tuple(cam_cfg.lookat),
                up=tuple(cam_cfg.up),
                fov=cam_cfg.fov,
                GUI=False,
            )
        return cameras
