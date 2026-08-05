from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import (
    StandardTabletopSceneBuilder,
    materials,
    TabletopBaseScene,
    tabletop_frames_from_config,
)


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


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


def _smooth_corner_blend(distance: float, depth: float) -> float:
    alpha = float(np.clip(1.0 - float(distance) / float(depth), 0.0, 1.0))
    return alpha * alpha * (3.0 - 2.0 * alpha)


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
        raise ValueError(f"Unknown peel corner {corner!r}.") from exc


def _write_obj(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Generated single-film PBD peeling mesh."]
    for vertex in vertices:
        lines.append(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}")
    for face in faces:
        lines.append(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class PeelingClothMesh:
    path: Path
    vertices: np.ndarray
    faces: np.ndarray
    cols: int
    rows: int


@dataclass(frozen=True)
class PeelingPhysicalLayout:
    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(
                f"Peeling position must have shape (3,), got {result}."
            )
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported Peeling coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(
            f"Unsupported Peeling coordinate_frame={self.coordinate_frame!r}."
        )

    @property
    def film_center(self) -> np.ndarray:
        return self.position_to_world(self.cfg.film.center)

    @property
    def film_size(self) -> np.ndarray:
        size = np.asarray(_list(self.cfg.film.size), dtype=float)
        if size.shape != (2,) or np.any(size <= 0.0):
            raise ValueError("film.size must contain two positive values.")
        return size

    @property
    def film_yaw(self) -> float:
        return float(getattr(self.cfg.film, "yaw", 0.0))

    @property
    def peel_corner(self) -> str:
        return str(getattr(self.cfg.film, "peel_corner", "lower_right"))

    @property
    def peel_signs(self) -> tuple[float, float]:
        return _corner_signs(self.peel_corner)

    @property
    def substrate_top_z(self) -> float:
        pos = self.position_to_world(self.cfg.substrate.pos)
        return float(pos[2] + 0.5 * float(self.cfg.substrate.size[2]))

    def grasp_yaw(self) -> float:
        sx, _sy = self.peel_signs
        return float(self.film_yaw + (0.0 if sx > 0.0 else np.pi))

    def cloth_mesh(self) -> PeelingClothMesh:
        cols = int(self.cfg.film.mesh.cols)
        rows = int(self.cfg.film.mesh.rows)
        if cols < 3 or rows < 3:
            raise ValueError("film.mesh cols and rows must both be at least 3.")
        size = self.film_size
        center = self.film_center
        sx, sy = self.peel_signs
        flap_size = np.asarray(
            _list(self.cfg.grasp.flap_size),
            dtype=float,
        )
        if flap_size.shape != (2,) or np.any(flap_size <= 0.0):
            raise ValueError("grasp.flap_size must contain two positive values.")
        initial_lift = float(self.cfg.grasp.initial_lift)
        if initial_lift < 0.0:
            raise ValueError("grasp.initial_lift must be non-negative.")
        xs = np.linspace(-0.5 * size[0], 0.5 * size[0], cols)
        ys = np.linspace(-0.5 * size[1], 0.5 * size[1], rows)
        vertices = []
        for y in ys:
            for x in xs:
                xy = center[:2] + _rotate_xy([x, y], self.film_yaw)
                edge_distance = 0.5 * size[0] - sx * x
                side_distance = 0.5 * size[1] - sy * y
                edge_blend = _smooth_corner_blend(
                    edge_distance,
                    flap_size[0],
                )
                side_blend = _smooth_corner_blend(
                    side_distance,
                    flap_size[1],
                )
                z = center[2] + initial_lift * edge_blend * side_blend
                vertices.append([xy[0], xy[1], z])

        faces = []
        for row in range(rows - 1):
            for col in range(cols - 1):
                lower_left = row * cols + col
                lower_right = lower_left + 1
                upper_left = (row + 1) * cols + col
                upper_right = upper_left + 1
                faces.append([lower_left, lower_right, upper_right])
                faces.append([lower_left, upper_right, upper_left])

        output_dir = Path(str(self.cfg.film.mesh.output_dir))
        if not output_dir.is_absolute():
            output_dir = Path(__file__).resolve().parents[2] / output_dir
        path = output_dir / f"{self.cfg.film.name}_cloth.obj"
        return PeelingClothMesh(
            path=path,
            vertices=np.asarray(vertices, dtype=float),
            faces=np.asarray(faces, dtype=int),
            cols=cols,
            rows=rows,
        )

    def particle_local_xy(self, positions: np.ndarray) -> np.ndarray:
        center = self.film_center
        return np.array(
            [
                _rotate_xy(position[:2] - center[:2], -self.film_yaw)
                for position in np.asarray(positions, dtype=float)
            ],
            dtype=float,
        )

    def particle_groups(
        self,
        positions: np.ndarray,
    ) -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
        local = self.particle_local_xy(positions)
        size = self.film_size
        sx, sy = self.peel_signs
        half = 0.5 * size
        grasp_size = np.asarray(
            _list(self.cfg.grasp.selection_size),
            dtype=float,
        )
        if grasp_size.shape != (2,) or np.any(grasp_size <= 0.0):
            raise ValueError(
                "grasp.selection_size must contain two positive values."
            )
        edge_distance = half[0] - sx * local[:, 0]
        corner_distance = half[1] - sy * local[:, 1]
        grasp_indices = tuple(
            int(index)
            for index in range(len(local))
            if float(edge_distance[index]) <= grasp_size[0]
            and float(corner_distance[index]) <= grasp_size[1]
        )
        if not grasp_indices:
            raise RuntimeError(
                "No cloth particles were selected for the peel corner."
            )

        grasp_set = set(grasp_indices)
        group_count = int(
            getattr(
                self.cfg.adhesion,
                "release_groups",
                self.cfg.film.mesh.cols,
            )
        )
        if group_count < 1:
            raise ValueError("adhesion.release_groups must be positive.")

        grouped_indices: list[list[int]] = [
            [] for _ in range(group_count)
        ]
        for index in range(len(local)):
            if index in grasp_set:
                continue
            progress = float(
                np.clip(edge_distance[index] / size[0], 0.0, 1.0)
            )
            group_index = min(
                int(progress * group_count),
                group_count - 1,
            )
            grouped_indices[group_index].append(index)

        groups = tuple(
            tuple(indices)
            for indices in grouped_indices
            if indices
        )
        if not groups:
            raise RuntimeError("No adhesion particle groups were generated.")
        return grasp_indices, groups

    @property
    def placement_center(self) -> np.ndarray:
        return self.position_to_world(self.cfg.placement.center)

    @property
    def placement_surface_z(self) -> float:
        return self.world_z(float(self.cfg.placement.surface_z))

    def placement_grasp_point(self, z: float) -> np.ndarray:
        sx, sy = self.peel_signs
        local_corner = np.array(
            [
                sx * 0.5 * self.film_size[0],
                sy * 0.5 * self.film_size[1],
            ],
            dtype=float,
        )
        xy = self.placement_center[:2] + _rotate_xy(
            local_corner,
            self.film_yaw,
        )
        return np.array([xy[0], xy[1], self.world_z(float(z))])


@dataclass
class PeelingPhysicalScene:
    scene: Any
    manifest: EntityManifest
    layout: PeelingPhysicalLayout
    film_entity: Any
    grasp_particle_indices: tuple[int, ...]
    adhesion_groups: tuple[tuple[int, ...], ...]
    released_groups: int
    initial_centroid: np.ndarray
    initial_particle_positions: np.ndarray
    source_mesh_vertices: int
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def particle_positions(self) -> np.ndarray:
        return _as_numpy(
            self.film_entity.get_particles_pos()
        ).reshape(-1, 3)

    def grasp_point(self) -> np.ndarray:
        positions = self.particle_positions()
        return positions[list(self.grasp_particle_indices)].mean(axis=0)

    def grasp_particles(self) -> np.ndarray:
        positions = self.particle_positions()
        return positions[list(self.grasp_particle_indices)].copy()

    def set_particles(
        self,
        particle_indices,
        positions: np.ndarray,
    ) -> None:
        indices = [int(index) for index in particle_indices]
        positions = np.asarray(positions, dtype=float)
        if positions.shape != (len(indices), 3):
            raise ValueError(
                "particle positions must have shape "
                f"({len(indices)}, 3), got {positions.shape}."
            )
        self.film_entity.set_particles_pos(
            positions,
            particles_idx_local=indices,
        )
        self.film_entity.set_particles_vel(
            np.zeros_like(positions),
            particles_idx_local=indices,
        )

    def set_grasp_particles(self, positions: np.ndarray) -> None:
        positions = np.asarray(positions, dtype=float)
        if positions.shape != (len(self.grasp_particle_indices), 3):
            raise ValueError(
                "grasp particle positions must have shape "
                f"({len(self.grasp_particle_indices)}, 3), got "
                f"{positions.shape}."
            )
        self.set_particles(
            self.grasp_particle_indices,
            positions,
        )


def release_peeling_groups(
    peeling_scene: PeelingPhysicalScene,
    *,
    count: int = 1,
) -> tuple[int, ...]:
    count = max(0, int(count))
    start = int(peeling_scene.released_groups)
    end = min(len(peeling_scene.adhesion_groups), start + count)
    released_indices: list[int] = []
    for group in peeling_scene.adhesion_groups[start:end]:
        peeling_scene.film_entity.release_particle(
            particles_idx_local=list(group)
        )
        released_indices.extend(group)
    peeling_scene.released_groups = end
    return tuple(released_indices)


def release_all_peeling_groups(
    peeling_scene: PeelingPhysicalScene,
) -> tuple[int, ...]:
    return release_peeling_groups(
        peeling_scene,
        count=len(peeling_scene.adhesion_groups),
    )


@dataclass
class PeelingKinematicSheetDriver:
    """Drive the visible peeled sheet with the same sticky-tip rule as training.

    The driver keeps unreleased particles at their initial flat positions and
    moves released adhesion bands with the tool. This is a deterministic
    contact abstraction for Peeling V1, not a separate oracle state update.
    """

    peeling_scene: PeelingPhysicalScene
    front_blend_fraction: float = 0.18
    curl_height: float = 0.018
    min_release_fraction: float = 0.0

    def __post_init__(self) -> None:
        self._initial_positions = np.asarray(
            self.peeling_scene.initial_particle_positions,
            dtype=float,
        ).reshape(-1, 3)
        self._initial_grasp = self._initial_positions[
            list(self.peeling_scene.grasp_particle_indices)
        ].mean(axis=0)
        local = self.peeling_scene.layout.particle_local_xy(
            self._initial_positions
        )
        sx, _sy = self.peeling_scene.layout.peel_signs
        size = self.peeling_scene.layout.film_size
        self._progress = np.clip(
            (0.5 * size[0] - sx * local[:, 0]) / max(size[0], 1e-8),
            0.0,
            1.0,
        )

    def sync_to_grasp(
        self,
        grasp_pos,
        *,
        release_fraction: float | None = None,
        force_all: bool = False,
    ) -> int:
        """Update the released sheet particles for the current grasp point."""
        grasp_pos = np.asarray(grasp_pos, dtype=float)
        weights = self._weights(
            release_fraction=release_fraction,
            force_all=force_all,
        )
        target_positions = self._initial_positions.copy()
        target_positions += weights[:, None] * (grasp_pos - self._initial_grasp)
        curl = np.sin(np.pi * np.clip(weights, 0.0, 1.0))
        target_positions[:, 2] += float(self.curl_height) * curl
        indices = self._active_indices(
            release_fraction=release_fraction,
            force_all=force_all,
        )
        self.peeling_scene.set_particles(
            indices,
            target_positions[list(indices)],
        )
        return len(indices)

    def _weights(
        self,
        *,
        release_fraction: float | None,
        force_all: bool,
    ) -> np.ndarray:
        if force_all:
            return np.ones(len(self._initial_positions), dtype=float)
        fraction = self._release_fraction(release_fraction)
        if fraction >= 1.0 - 1e-6:
            return np.ones(len(self._initial_positions), dtype=float)
        blend = max(float(self.front_blend_fraction), 1e-6)
        weights = np.zeros(len(self._initial_positions), dtype=float)
        full_mask = self._progress <= max(0.0, fraction - blend)
        weights[full_mask] = 1.0
        blend_mask = (
            (self._progress > max(0.0, fraction - blend))
            & (self._progress <= fraction)
        )
        weights[blend_mask] = np.clip(
            (fraction - self._progress[blend_mask]) / blend,
            0.0,
            1.0,
        )
        weights[list(self.peeling_scene.grasp_particle_indices)] = 1.0
        return weights

    def _active_indices(
        self,
        *,
        release_fraction: float | None,
        force_all: bool,
    ) -> tuple[int, ...]:
        if force_all or self._release_fraction(release_fraction) >= 1.0 - 1e-6:
            return tuple(range(len(self._initial_positions)))
        total = len(self.peeling_scene.adhesion_groups)
        group_count = int(
            np.ceil(self._release_fraction(release_fraction) * max(1, total))
        )
        group_count = int(np.clip(group_count, 0, total))
        active = set(int(index) for index in self.peeling_scene.grasp_particle_indices)
        for group in self.peeling_scene.adhesion_groups[:group_count]:
            active.update(int(index) for index in group)
        return tuple(sorted(active))

    def _release_fraction(self, release_fraction: float | None) -> float:
        if release_fraction is None:
            release_fraction = (
                self.peeling_scene.released_groups
                / max(1, len(self.peeling_scene.adhesion_groups))
            )
        return float(
            np.clip(
                max(float(release_fraction), float(self.min_release_fraction)),
                0.0,
                1.0,
            )
        )


class PeelingPhysicalSceneBuilder:
    def __init__(
        self,
        env_cfg,
        task_cfg,
        robot_cfg,
        *,
        rigid_options=None,
    ) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = PeelingPhysicalLayout(
            task_cfg,
            task_origin=frames.task_origin,
        )

    def build(self, *, show_viewer: bool = False) -> PeelingPhysicalScene:
        pbd = self.task_cfg.film.pbd
        pbd_options = gs.options.PBDOptions(
            particle_size=float(self.task_cfg.film.particle_size),
            max_stretch_solver_iterations=int(
                pbd.max_stretch_solver_iterations
            ),
            max_bending_solver_iterations=int(
                pbd.max_bending_solver_iterations
            ),
            max_volume_solver_iterations=int(
                pbd.max_volume_solver_iterations
            ),
        )
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
            pbd_options=pbd_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest
        self._add_board(scene, manifest)
        self._add_substrate(scene, manifest)
        cloth_mesh = self.layout.cloth_mesh()
        _write_obj(cloth_mesh.path, cloth_mesh.vertices, cloth_mesh.faces)
        film_entity = self._add_film(scene, manifest, cloth_mesh)
        tabletop_builder.finalize(tabletop)

        particle_positions = _as_numpy(
            film_entity.get_particles_pos()
        ).reshape(-1, 3)
        grasp_indices, adhesion_groups = self.layout.particle_groups(
            particle_positions
        )
        covered = set(grasp_indices)
        for group in adhesion_groups:
            covered.update(group)
        if len(covered) != len(particle_positions):
            raise RuntimeError(
                "Peeling particle groups do not cover the complete remeshed "
                f"cloth: covered={len(covered)}, "
                f"particles={len(particle_positions)}."
            )
        adhesion_indices = sorted(
            index for group in adhesion_groups for index in group
        )
        film_entity.fix_particles(particles_idx_local=adhesion_indices)
        initial_release_groups = int(
            self.task_cfg.adhesion.initial_release_groups
        )
        if not 0 <= initial_release_groups <= len(adhesion_groups):
            raise ValueError(
                "adhesion.initial_release_groups must be between 0 and "
                f"{len(adhesion_groups)}."
            )
        peeling_scene = PeelingPhysicalScene(
            scene=scene,
            manifest=manifest,
            layout=self.layout,
            film_entity=film_entity,
            grasp_particle_indices=grasp_indices,
            adhesion_groups=adhesion_groups,
            released_groups=0,
            initial_centroid=particle_positions.mean(axis=0),
            initial_particle_positions=particle_positions.copy(),
            source_mesh_vertices=len(cloth_mesh.vertices),
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        release_peeling_groups(
            peeling_scene,
            count=initial_release_groups,
        )
        return peeling_scene

    def _add_board(self, scene, manifest: EntityManifest) -> None:
        cfg = self.task_cfg.board
        if not box_entity_enabled(cfg):
            return
        manifest.add(
            str(cfg.name),
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(cfg.pos)),
                    size=tuple(cfg.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", cfg.color),
                name=str(cfg.name),
            ),
        )

    def _add_substrate(self, scene, manifest: EntityManifest) -> None:
        cfg = self.task_cfg.substrate
        if not box_entity_enabled(cfg):
            return
        manifest.add(
            str(cfg.name),
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(cfg.pos)),
                    size=tuple(cfg.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", cfg.color),
                name=str(cfg.name),
            ),
        )

    def _add_film(
        self,
        scene,
        manifest: EntityManifest,
        mesh: PeelingClothMesh,
    ):
        cfg = self.task_cfg.film
        cloth = cfg.cloth
        entity = scene.add_entity(
            gs.morphs.Mesh(
                file=str(mesh.path),
                pos=(0.0, 0.0, 0.0),
                scale=1.0,
                decimate=False,
                convexify=False,
                fixed=False,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.PBD.Cloth(
                rho=float(cloth.rho),
                static_friction=float(cloth.static_friction),
                kinetic_friction=float(cloth.kinetic_friction),
                stretch_compliance=float(cloth.stretch_compliance),
                bending_compliance=float(cloth.bending_compliance),
                stretch_relaxation=float(cloth.stretch_relaxation),
                bending_relaxation=float(cloth.bending_relaxation),
                air_resistance=float(cloth.air_resistance),
            ),
            surface=materials.plastic("deformable", cfg.color, vis_mode="visual"),
            name=str(cfg.name),
        )
        manifest.add(str(cfg.name), entity)
        return entity
