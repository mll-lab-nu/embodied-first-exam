"""Band Untwist (docx 3.3): a rope lying in a figure-8 is opened into an O.

**How this departs from the docx, and why.** The docx hangs a CLOSED elastic
band on a wall peg, twisted into an 8, and has the arm flip the lower loop. That
was built (`world/closed_band.py`, `tests/closed_band_spike.py`, 2026-08-21) and
does not hold up under FEM+IPC: hanging free, the 8's two strands sit 40 mm
apart at the crossing -- four times the contact range -- so nothing resists the
stored elastic energy and the band springs flat within 0.25 s of release. A task
that solves itself is not a task. The same spike's notes record when an 8 *does*
hold: lying on a table, where gravity presses one strand onto the other and
friction holds the shape.

So this scene is an OPEN rope (the `untangle_continuous` FEM tube, unchanged) laid
on the tabletop in a figure-8: a closed lobe, a crossing, and an open lobe whose
two ends lie side by side. Tabletop friction replaces the peg as the boundary
condition. The reading is the docx's: the rope's top-down self-crossing count,
1 at spawn, 0 when solved. Both rope ends carry the free-end plug the other rope
tasks use, so the gripper closes on a rigid body and the rope follows it through
the backend's link attachment.

The oracle grasps the end whose strand is ON TOP at the crossing, lifts that
strand clear, carries it across the other strand and lays it down beside it:
1 -> 0. The contrast is the docx's "flip from the wrong side": the same move on
the OTHER end lays a second crossing on top of the first, 1 -> 2
(`run.oracle_mode=wrong_end`). Which end is which is measured, not assumed --
`verification/band_untwist_verifier.py` reads over/under off the settled rope.

Geometry (lobe radii, crossing angle, end gap, over-lift) lives in
`./_figure_eight_geometry.py`, which is Genesis-free so the offline gate
`tests/check_band_untwist_geometry.py` can import it on a machine without a
solver. Rope spawning follows `untangle_continuous.py:rope_mesh` step for step;
`settle_scene` is reused from there unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks.entangle import _figure_eight_geometry as fig8
from topogym.tasks.entangle.untangle_continuous import settle_scene
from topogym.world.rope import (
    RopeEndpointHandle,
    RopeMesh,
    catmull_rom_centerline as _catmull_rom_centerline,
    make_elastic_tube_mesh as _make_elastic_tube_mesh,
    resolve_mesh_dir as _resolve_mesh_dir,
    safe_asset_name as _safe_asset_name,
    sample_polyline as _sample_polyline,
    write_obj as _write_obj,
)
from topogym.world import (
    StandardTabletopSceneBuilder,
    materials,
    rope as rope_prefab,
    TabletopBaseScene,
    tabletop_frames_from_config,
)
from topogym.world.rope_backends import rope_backend as _make_rope_backend

__all__ = [
    "BandUntwistLayout",
    "BandUntwistScene",
    "BandUntwistSceneBuilder",
    "settle_scene",
]


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class BandUntwistLayout:
    """One hand-authored figure-8 rope on the table.

    ``seed`` is accepted for builder-signature parity with the other rope tasks
    and is currently unused: the layout is fixed by ``task.figure_eight``. The
    variation plan (`docs/develop/tasks/variation_and_difficulty_plan_zh.md`)
    is where it becomes a real layout seed.
    """

    cfg: Any
    seed: int = 0
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(f"BandUntwist position must have shape (3,), got {result}.")
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported BandUntwist coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(f"Unsupported BandUntwist coordinate_frame={self.coordinate_frame!r}.")

    @property
    def n_strands(self) -> int:
        return 1

    @property
    def over_end(self) -> int:
        """The rope end whose strand the generator raised at the crossing."""

        return int(fig8.OVER_END)

    def figure_eight_spec(self) -> fig8.FigureEightSpec:
        """The task-frame ``figure_eight:`` block as the generator's dataclass."""

        block = self.cfg.figure_eight
        center = _list(block.center)
        return fig8.FigureEightSpec(
            closed_lobe_radius=float(block.closed_lobe_radius),
            open_lobe_radius=float(block.open_lobe_radius),
            end_gap=float(block.end_gap),
            half_angle_deg=float(block.half_angle_deg),
            over_lift=float(block.over_lift),
            base_z=float(block.base_z),
            center=(float(center[0]), float(center[1])),
            heading_deg=float(block.heading_deg),
            arc_points_per_quarter=int(block.arc_points_per_quarter),
            lift_ramp=float(block.lift_ramp),
        )

    def control_points(self) -> np.ndarray:
        return fig8.figure_eight_control_points(self.figure_eight_spec())

    def strand_name(self, strand_index: int = 0) -> str:
        return f"rope_{int(strand_index)}"

    def strand_color(self, strand_index: int = 0):
        return tuple(_list(self.cfg.figure_eight.color))

    def rope_mesh(self) -> RopeMesh:
        """Control points -> smooth centerline -> swept tube mesh.

        Same pipeline as `untangle_continuous.py:rope_mesh`, and for the same
        reasons: spline the sparse control points first and resample second, then
        clamp to the resting height so centripetal Catmull-Rom's undershoot cannot
        sink the tube into the table.
        """

        radius = float(self.cfg.rope.radius)
        world_points = np.stack(
            [self.position_to_world(point) for point in self.control_points()],
            axis=0,
        )
        centerline = _catmull_rom_centerline(
            world_points,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        floor_z = self.world_z(0.0) + radius
        centerline = centerline.copy()
        centerline[:, 2] = np.maximum(centerline[:, 2], floor_z)
        centerline = _sample_polyline(
            centerline,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        bottom_clearance = float(centerline[:, 2].min()) - radius - self.world_z(0.0)
        if bottom_clearance < 0.0:
            raise ValueError(
                f"BandUntwist rope spawns {-bottom_clearance * 1000:.2f} mm inside the "
                f"tabletop (figure_eight.base_z={float(self.cfg.figure_eight.base_z):.4f}, "
                f"rope.radius={radius:.4f}). Raise figure_eight.base_z."
            )
        model = str(self.cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported BandUntwist rope model: {model!r}.")
        vertices, faces = _make_elastic_tube_mesh(
            centerline,
            radius=radius,
            radial_segments=int(self.cfg.rope.mesh.radial_segments),
        )
        mesh_dir = _resolve_mesh_dir(self.cfg.rope.mesh.output_dir)
        name = _safe_asset_name(self.strand_name(0))
        return RopeMesh(
            path=mesh_dir / f"{name}_{model}.obj",
            centerline=centerline,
            vertices=vertices,
            faces=faces,
            endpoint_centers=(centerline[0], centerline[-1]),
        )


@dataclass
class BandUntwistScene:
    """The built scene. Attribute names match `UntangleContinuousScene` where the
    meaning is the same, so `settle_scene`, `supervision.rope_stability` and
    `RopeTrace` work on it unchanged (they only ask for ``strand_entities``,
    ``strand_centerline``, ``strand_particles``, ``particle_arclength`` and
    ``rope_backend``)."""

    scene: Any
    manifest: EntityManifest
    layout: BandUntwistLayout
    cameras: dict = field(default_factory=dict)
    rope_handles: dict[str, RopeEndpointHandle] = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None
    # strand index (always 0) -> (P,) normalized arc length per FEM node; see
    # `_particle_arclength`.
    particle_arclength: dict[int, np.ndarray] = field(default_factory=dict)
    # rope END index (0, 1) -> rigid plug attached to that end. Keyed by end, not
    # by strand: the one rope has two graspable ends and either may be picked.
    free_end_connectors: dict[int, Any] = field(default_factory=dict)
    # rope end -> compass heading (rad) the rope leaves that end on, at spawn.
    # The plug's yaw, and the yaw the gripper closes at.
    end_headings: dict[int, float] = field(default_factory=dict)
    # Plug axis height above the table when it rests on its flange.
    connector_rest_height: float = 0.0
    rope_backend: Any | None = None

    @property
    def rope_entity(self):
        return self.rope_handles[self.layout.strand_name(0)].entity

    @property
    def strand_entities(self) -> dict[int, Any]:
        return {0: self.rope_entity}

    def strand_centerline(self, strand_index: int = 0, *, samples: int = 80) -> np.ndarray:
        """Ordered centerline from the unordered node cloud, by arc-length binning.

        Same construction as `UntangleContinuousScene.strand_centerline`: each
        node's stored normalized arc length picks its bin, and a bin's mean is a
        centerline sample -- averaging away the tube's thickness and any single
        node's jitter.
        """

        positions = self.strand_particles(strand_index)
        arclength = self.particle_arclength[int(strand_index)]
        if len(arclength) != len(positions):
            raise ValueError(
                f"{len(arclength)} arclengths for {len(positions)} nodes -- "
                "the scene's material map is stale."
            )
        edges = np.linspace(0.0, 1.0, int(samples) + 1)
        bucket = np.clip(np.digitize(arclength, edges[1:-1]), 0, int(samples) - 1)
        points = [
            positions[bucket == index].mean(axis=0)
            for index in range(int(samples))
            if np.any(bucket == index)
        ]
        if len(points) < 2:
            raise ValueError("rope collapsed to < 2 centerline samples.")
        return np.stack(points, axis=0)

    def strand_particles(self, strand_index: int = 0) -> np.ndarray:
        return np.asarray(self.rope_backend.nodes(self.strand_entities[int(strand_index)]), dtype=float)

    def connector_xy(self, end: int) -> tuple[float, float]:
        raw = self.free_end_connectors[int(end)].get_pos()
        if hasattr(raw, "detach"):
            raw = raw.detach().cpu().numpy()
        position = np.asarray(raw, dtype=float).reshape(-1)
        return float(position[0]), float(position[1])


class BandUntwistSceneBuilder:
    """Build the common table with one figure-8 rope and a plug on each end."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, seed: int = 0) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = BandUntwistLayout(task_cfg, seed=int(seed), task_origin=frames.task_origin)

    def build(self, *, show_viewer: bool = False, include_robot: bool = True) -> BandUntwistScene:
        backend = _make_rope_backend(self.task_cfg.rope)
        self._rope_backend = backend
        backend.pre_scene()

        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            scene_options=backend.scene_options(),
        )
        # All four materials are passed on purpose: under IPC a fixed Box left on
        # the Genesis default Rigid() gets auto-typed as external_articulation
        # and libuipc dies with an unrelated CUDA error (closed_band spike,
        # 2026-08-21). `cable_routing.py` is the reference call.
        tabletop = tabletop_builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            robot_material=self._robot_material(),
            table_material=self._table_material(),
            static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material(),
        )
        scene = tabletop.scene
        manifest = tabletop.manifest
        layout = self.layout

        mesh = layout.rope_mesh()
        _write_obj(mesh.path, mesh.vertices, mesh.faces)
        rope_name = layout.strand_name(0)
        rope_entity = scene.add_entity(
            rope_prefab.tube_morph(mesh.path, self.task_cfg.rope),
            material=backend.material(),
            surface=materials.plastic("deformable", layout.strand_color(0), vis_mode="visual"),
            name=rope_name,
        )
        manifest.add(rope_name, rope_entity)

        connectors, headings, rest_height = self._add_end_connectors(scene, manifest, layout, mesh)

        # Free-end clearance rule (untangle_continuous, 2026-08-07): two plugs
        # inside one gripper span make the closing fingers ambiguous. Here the
        # two plugs are the two ends of the same rope, lying side by side.
        separation = float(np.linalg.norm(mesh.endpoint_centers[0][:2] - mesh.endpoint_centers[1][:2]))
        min_clearance = float(getattr(self.task_cfg.rope.free_end_connector, "min_clearance", 0.07))
        if len(connectors) == 2 and separation < min_clearance:
            raise ValueError(
                f"the rope's two end plugs spawn {separation * 1000:.0f}mm apart, below the "
                f"{min_clearance * 1000:.0f}mm clearance the gripper needs "
                "(rope.free_end_connector.min_clearance). Widen figure_eight.end_gap."
            )

        # Follow-band capacity is declared before finalize (= scene.build): the
        # FEM coupler reads it during build. One band per end; the backend keys
        # them by declaration order. No anchor -- both ends are free and the rope
        # is held by friction alone, which is the task's boundary condition.
        anchor_radius = float(self.task_cfg.rope.anchor_radius)
        follow_enabled = bool(getattr(self.task_cfg.rope.free_end_connector, "follow_enabled", True))
        band_tokens: dict[int, int] = {}
        if follow_enabled:
            for end in sorted(connectors):
                band_tokens[end] = int(
                    backend.declare_follow(rope_entity, mesh.endpoint_centers[end], anchor_radius)
                )

        tabletop_builder.finalize(tabletop)

        particle_arclength = {0: _particle_arclength(backend, rope_entity, mesh.centerline)}
        end_indices: dict[int, tuple[int, ...]] = {}
        for end in (0, 1):
            connector = connectors.get(end)
            if connector is not None and follow_enabled:
                end_indices[end] = tuple(
                    backend.follow_link(rope_entity, connector.base_link, band=band_tokens[end])
                )
            else:
                end_indices[end] = tuple(
                    backend.resolve_indices(rope_entity, (mesh.endpoint_centers[end],), anchor_radius)
                )

        rope_handles = {
            rope_name: RopeEndpointHandle(
                name=rope_name,
                entity=rope_entity,
                start_center=mesh.endpoint_centers[0],
                end_center=mesh.endpoint_centers[1],
                start_indices=end_indices[0],
                end_indices=end_indices[1],
            )
        }
        return BandUntwistScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            rope_handles=rope_handles,
            tabletop=tabletop,
            particle_arclength=particle_arclength,
            free_end_connectors=connectors,
            end_headings=headings,
            connector_rest_height=rest_height,
            rope_backend=backend,
        )

    def _robot_material(self):
        """Arm outside the deformable coupling by default; see
        `UntangleContinuousSceneBuilder._robot_material` for the history."""

        if bool(getattr(self.task_cfg.pinch, "robot_rope_contact", False)):
            return None
        return gs.materials.Rigid(needs_coup=False)

    def _table_material(self):
        if self._rope_backend.name != "pbd":
            return gs.materials.Rigid(coup_type="ipc_only")
        return gs.materials.Rigid(coup_friction=float(self.task_cfg.rope.table_friction))

    def _add_end_connectors(
        self,
        scene,
        manifest: EntityManifest,
        layout: BandUntwistLayout,
        mesh: RopeMesh,
    ) -> tuple[dict[int, Any], dict[int, float], float]:
        """A rigid plug on EACH rope end, lying flat, pointing out along the rope.

        Same part and the same reasons as `untangle_continuous.py:_add_free_end_connectors`
        (rigid body for the gripper; rope follows the link's pose). The one
        difference: the plug's yaw follows the rope's own direction at that end
        (`cable_routing.py:rope_axis_heading` does the same), because this rope's
        ends do not lie along x.
        """

        connector_cfg = getattr(self.task_cfg.rope, "free_end_connector", None)
        if connector_cfg is None or not bool(getattr(connector_cfg, "enabled", False)):
            return {}, {}, 0.0

        connector_path = rope_prefab.connector_obj_path(
            connector_cfg,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
        )
        rest_height = float(connector_cfg.flange_radius)
        axis_z = layout.world_z(0.0) + rest_height

        connectors: dict[int, Any] = {}
        headings: dict[int, float] = {}
        for end in (0, 1):
            heading = _end_heading(mesh.centerline, end)
            free_end = np.asarray(mesh.endpoint_centers[end], dtype=float)
            name = f"free_end_connector_{end}"
            headings[end] = heading
            connectors[end] = manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Mesh(
                        file=str(connector_path),
                        pos=(float(free_end[0]), float(free_end[1]), axis_z),
                        # Solid of revolution about local +z with the cap (cable
                        # entry) on top. -90 deg about y lays that axis flat along
                        # +x; the yaw then turns the pin to point out along the
                        # rope's direction at this end, cap facing back down it.
                        euler=(0.0, -90.0, float(np.degrees(heading))),
                        scale=1.0,
                        decimate=False,
                        convexify=True,
                        fixed=False,
                        collision=True,
                        file_meshes_are_zup=True,
                    ),
                    material=gs.materials.Rigid(
                        rho=float(connector_cfg.rho),
                        friction=float(connector_cfg.friction),
                        needs_coup=False,
                    ),
                    surface=materials.plastic("connector", connector_cfg.color),
                    name=name,
                ),
            )
        return connectors, headings, rest_height


def _end_heading(centerline: np.ndarray, end: int) -> float:
    """Compass angle (rad) the rope leaves ``end`` on, pointing away from the rope."""

    if int(end) == 0:
        tip, before = centerline[0], centerline[1]
    else:
        tip, before = centerline[-1], centerline[-2]
    direction = np.asarray(tip[:2], dtype=float) - np.asarray(before[:2], dtype=float)
    if float(np.linalg.norm(direction)) <= 1e-9:
        return 0.0
    return float(np.arctan2(direction[1], direction[0]))


def _particle_arclength(backend, rope_entity, centerline: np.ndarray) -> np.ndarray:
    """Each FEM node's normalized position along the rope (0..1), fixed at spawn.

    The tube is tetrahedralized, so the node cloud carries no ordering; each node
    takes the arc length of its nearest spawn-centerline vertex, once, while the
    exact centerline is known. Same construction as untangle_continuous.
    """

    particles = np.asarray(backend.nodes(rope_entity), dtype=float)
    centerline = np.asarray(centerline, dtype=float)
    segment = np.linalg.norm(np.diff(centerline, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(segment)])
    total = float(cumulative[-1])
    if total <= 0.0:
        raise ValueError("Degenerate rope centerline: zero total length.")
    nearest = np.argmin(
        np.linalg.norm(particles[:, None, :] - centerline[None, :, :], axis=2),
        axis=1,
    )
    return cumulative[nearest] / total
