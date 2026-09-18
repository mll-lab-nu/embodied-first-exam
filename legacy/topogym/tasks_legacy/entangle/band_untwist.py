"""Band Untwist (docx 3.3): a rope lying crossed over itself is laid out flat.

**2026-09-10: four spawn shapes, one or two crossings** (`band_untwist_zh.md`
§8). The figure-8 below is one of them; the "6", the twist (the 8 with one more
closed lobe) and O|-|O (a curl at each end of a straight middle rope) come from
`./_band_shapes.py`, and `task.band.shape` picks one per episode. Solved = no
crossing left and both plugs on the table. The oracle plans its grasps with the
move model in `topogym/planning/band_untwist_sequence.py`.

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

from dataclasses import dataclass, field, replace
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.planning import band_untwist_sequence as sequence
from topogym.tasks_legacy.entangle import _band_shapes as shapes
from topogym.supervision import min_bend_radius
from topogym.tasks_legacy.entangle import _figure_eight_geometry as fig8
from topogym.tasks_legacy.entangle.untangle_continuous import settle_scene
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
    """One rope on the table in the shape ``task.band.shape`` names.

    ``seed`` is the run seed, accepted for builder-signature parity with the
    other rope tasks; the layout itself never samples. Per-episode variation is
    written into the task cfg before this class sees it
    (`generation/layout_randomization.py`, the yaml's ``variation:`` block).
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
    def shape(self) -> str:
        shape = str(self.cfg.band.shape)
        if shape not in shapes.SHAPES:
            raise ValueError(f"band.shape must be one of {shapes.SHAPES}, got {shape!r}.")
        return shape

    @property
    def heading_deg(self) -> float:
        """Task-frame heading of the shape's local axis: ``band.heading_deg``
        plus the shape's own base (O|-|O lies across the table, middle along y)."""

        base = float(self.cfg.band.curls.base_heading_deg) if self.shape == "curls" else 0.0
        return float(self.cfg.band.heading_deg) + base

    def figure_eight_spec(self) -> fig8.FigureEightSpec:
        """``band.eight`` (plus the shared ``band`` leaves) as the 8's dataclass."""

        band, eight = self.cfg.band, self.cfg.band.eight
        return fig8.FigureEightSpec(
            closed_lobe_radius=float(eight.closed_lobe_radius),
            open_lobe_radius=float(eight.open_lobe_radius),
            end_gap=float(eight.end_gap),
            half_angle_deg=float(eight.half_angle_deg),
            over_lift=float(band.over_lift),
            base_z=float(band.base_z),
            center=(float(band.center_x), float(band.center_y)),
            heading_deg=float(band.heading_deg),
            arc_points_per_quarter=int(band.arc_points_per_quarter),
            lift_ramp=float(band.lift_ramp),
            over_end=int(eight.over_end),
        )

    def shape_spec(self, *, local: bool = False):
        """The drawn shape as its generator's dataclass. ``local`` puts it at
        the origin, unturned -- the frame the centre window is worked out in."""

        band = self.cfg.band
        where = dict(center=(0.0, 0.0), heading_deg=0.0) if local else dict(
            center=(float(band.center_x), float(band.center_y)), heading_deg=self.heading_deg
        )
        if self.shape == "eight":
            return replace(self.figure_eight_spec(), **where)
        common = dict(
            over_lift=float(band.over_lift),
            base_z=float(band.base_z),
            lift_ramp=float(band.lift_ramp),
            arc_points_per_quarter=int(band.arc_points_per_quarter),
            **where,
        )
        if self.shape == "six":
            six = band.six
            return shapes.SixSpec(
                loop_radius=float(six.loop_radius), half_angle_deg=float(six.half_angle_deg),
                short_len=float(six.short_len), stem_len=float(six.stem_len), short_over=int(six.short_over), **common,
            )
        if self.shape == "twist":
            twist = band.twist
            return shapes.TwistSpec(
                closed_lobe_radius=float(twist.closed_lobe_radius), middle_lobe_radius=float(twist.middle_lobe_radius),
                open_lobe_radius=float(twist.open_lobe_radius), half_angle_deg=float(twist.half_angle_deg),
                end_gap=float(twist.end_gap), over_end_x1=int(twist.over_end_x1), over_end_x2=int(twist.over_end_x2),
                **common,
            )
        curls = band.curls
        return shapes.CurlsSpec(
            loop_radius=float(curls.loop_radius), half_angle_deg=float(curls.half_angle_deg),
            stub_len=float(curls.stub_len), middle_len=float(curls.middle_len), stub_side=str(curls.stub_side),
            stub_over_a=int(curls.stub_over_a), stub_over_b=int(curls.stub_over_b), **common,
        )

    # ----- variation: derived leaves + checks ----------------------------------

    def end_gap_bounds(self) -> tuple[float, float]:
        """Where the plugs of an open lobe may sit (eight and twist)."""

        block = self.cfg.band[self.shape]
        return fig8.end_gap_bounds(
            float(block.open_lobe_radius),
            float(self.cfg.rope.free_end_connector.min_clearance),
            float(block.end_gap_max_ratio),
        )

    def end_gap_from_frac(self, frac: float) -> float:
        block = self.cfg.band[self.shape]
        return fig8.end_gap_from_frac(
            float(block.open_lobe_radius),
            float(frac),
            float(self.cfg.rope.free_end_connector.min_clearance),
            float(block.end_gap_max_ratio),
        )

    def middle_len_bounds(self) -> tuple[float, float]:
        """Where O|-|O's middle rope may sit (`_band_shapes.curls_middle_bounds`)."""

        curls = self.cfg.band.curls
        return shapes.curls_middle_bounds(
            float(curls.stub_len), float(curls.half_angle_deg), str(curls.stub_side),
            min_plug_gap=float(curls.middle_plug_gap), min_middle=float(curls.middle_min), span=float(curls.middle_span),
        )

    def model_params(self) -> sequence.ModelParams:
        """The move model's inputs from the task's literal leaves."""

        band, pinch = self.cfg.band, self.cfg.pinch
        return sequence.ModelParams(
            rope_radius=float(band.tube_radius),
            lift_clearance=float(pinch.lift_clearance),
            place_clearance=float(pinch.place_clearance),
            min_plug_separation=float(self.cfg.rope.free_end_connector.min_clearance),
            merge_radius=float(self.cfg.success.crossing_merge_radius),
            scene_top=float(band.base_z) + float(band.over_lift) + float(band.tube_radius),
            max_hand_height=float(self.cfg.workspace.z_max),
            arm_base_xy=(float(self.cfg.reach.base_xy[0]), float(self.cfg.reach.base_xy[1])),
            # The twist is undone by flips (2026-09-13, §8.15); the other shapes
            # keep the lift-carry-lay moves their GPU evidence was run with.
            flip_moves=self.shape == "twist",
        )

    def plan(self, *, local: bool = False):
        """The oracle's move sequence on the spawn control points, or None.

        In the task frame the landings are held inside the workspace less its
        margin and within reach, as the runtime planner holds them (a wide
        flip that would land outside is dropped for the next candidate); in
        the shape's local frame there is no box yet -- `centre_window` places it.
        """

        params = self.model_params()
        if not local:
            ws = self.cfg.workspace
            # A hair inside the footprint row's own tolerance: a centre drawn at
            # the window's edge puts a landing exactly ``margin`` from the box.
            margin = float(ws.margin) - 1e-6
            params = sequence.replace(
                params,
                landing_box=((float(ws.x[0]) + margin, float(ws.x[1]) - margin), (float(ws.y[0]) + margin, float(ws.y[1]) - margin)),
                max_reach=float(self.cfg.reach.max_hand_dist),
            )
        return sequence.plan(sequence.Rope.from_points(self.control_points(local=local)), params)

    def declared_sequence(self) -> tuple[tuple[int, str], ...]:
        """The crossing sequence the generator built: walking the rope from end
        0, every pass -- which crossing, on top or underneath."""

        rope = sequence.Rope.from_points(self.control_points())
        return sequence.crossing_sequence(
            sequence.crossings(rope, merge_radius=float(self.cfg.success.crossing_merge_radius))
        )

    def predicted_lift(self) -> float:
        """Highest hand the oracle's plan asks for (task z)."""

        plan = self.plan()
        return float(plan.max_hand_height) if plan is not None and plan.moves else float("inf")

    def centre_window(self) -> shapes.CentreWindow | None:
        """Where the shape may be centred with its plan's landings in the
        workspace and every grasp and landing in reach, at this heading.

        Every plan of the fewest moves counts, not only the best: on O|-|O the
        two orders tie, and the heading or the settled rope picks either (seen
        2026-09-11: six vertices whose other order landed 3.7 cm past the margin).
        """

        local = self.control_points(local=True)
        params = self.model_params()
        ws = self.cfg.workspace
        # A wide flip lands far from the pivot; when no centre fits its plan,
        # the plan with narrower flips (or a finishing lay) is what the runtime
        # planner falls back to inside its landing box, so its window counts.
        caps = [params.flip_max_radius, 0.20, 0.15] if params.flip_moves else [params.flip_max_radius]
        for cap in caps:
            found = sequence.plans(sequence.Rope.from_points(local), sequence.replace(params, flip_max_radius=cap))
            moves = [m for p in found for m in p.moves]
            if not moves:
                continue
            window = shapes.centre_window(
                local,
                np.array([m.place_xy for m in moves]),
                np.array([m.grasp_xy for m in moves]),
                heading_deg=self.heading_deg,
                workspace_x=(float(ws.x[0]), float(ws.x[1])),
                workspace_y=(float(ws.y[0]), float(ws.y[1])),
                margin=float(ws.margin),
                arm_base_xy=(float(self.cfg.reach.base_xy[0]), float(self.cfg.reach.base_xy[1])),
                max_hand_dist=float(self.cfg.reach.max_hand_dist),
            )
            if window is not None:
                return window
        return None

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a buildable, solvable layout needs.

        One list for the randomizer's reject step, the offline gates and the
        demo's start-up print (`_band_shapes.band_checks`, plus the open-lobe
        ratio for the 8 and the twist). Reads only literal task leaves
        (``tube_radius`` is the yaml's copy of ``rope.radius``; the box is
        ``workspace:``), so it works on an unresolved task config.
        """

        band, ws = self.cfg.band, self.cfg.workspace
        params = self.model_params()
        plan = self.plan()
        # A plan of two lay moves lays both at slack_min_multi or straighter
        # (the first must land where the model says). A flip plan's finishing
        # lay follows the one-move rules instead (laid loose, `sequence.plans`).
        lays_only = plan is not None and len(plan.moves) > 1 and all(m.kind == "lay" for m in plan.moves)
        slack_floor = params.slack_min_multi if lays_only else params.slack_min
        rows = shapes.band_checks(
            self.control_points(),
            plan,
            expected_crossings=shapes.SHAPE_CROSSINGS[self.shape],
            tube_radius=float(band.tube_radius),
            min_clearance=float(self.cfg.rope.free_end_connector.min_clearance),
            strand_gap_min=float(band.strand_gap_min),
            crossing_spacing_min=float(band.crossing_spacing_min),
            place_clearance=float(self.cfg.pinch.place_clearance),
            workspace_x=(float(ws.x[0]), float(ws.x[1])),
            workspace_y=(float(ws.y[0]), float(ws.y[1])),
            workspace_z_max=float(ws.z_max),
            workspace_margin=float(ws.margin),
            arm_base_xy=params.arm_base_xy,
            max_hand_dist=float(self.cfg.reach.max_hand_dist),
            merge_radius=params.merge_radius,
            lay_down_min=params.min_lay_down,
            slack_range=(slack_floor, params.slack_max),
            rotation_min_deg=params.min_rotation_deg,
        )
        if self.shape in ("eight", "twist"):
            block = band[self.shape]
            ratio = float(block.end_gap) / (2.0 * float(block.open_lobe_radius))
            limit = float(block.end_gap_max_ratio)
            rows.append(("end_gap_ratio", ratio, limit, ratio <= limit + 1e-9))
        # The tube is swept on the spline, which bends tighter than the control
        # polygon the `corner_radius` row reads: 4.6-16.8 mm across the envelope
        # against that row's 15-44 mm (2026-09-12). Below the rope's own radius
        # the tube pinches itself on the inside of the bend; the bar is a tenth
        # more than that, which the whole envelope clears -- the tightest spawns
        # (4.6 mm, a twist at 55 deg with the smallest middle lobe, and 5.2 mm
        # over 400 randomiser seeds) still mesh under Genesis's tetgen switches
        # (2728-2848 nodes). The old 3x-radius rule of thumb was never enforced:
        # it was read off the control polygon, which never goes below 15 mm.
        bend = float(min_bend_radius(self.built_centerline(radius=float(band.tube_radius)))[0])
        bend_limit = 1.1 * float(band.tube_radius)
        rows.append(("centreline_bend", bend, bend_limit, bend >= bend_limit - 1e-9))
        # A two-move plan: the first move's laid rope, bowed off its chord by
        # the bend the model allows it, still keeps the lay-down room from the
        # crossing the second move has to undo (the alternating twist's second
        # move failed 8/11 on the GPU when that rope landed on top of its work,
        # `band_untwist_zh.md` §8.7; the bend band is §8.14).
        if plan is not None and len(plan.moves) > 1:
            room = float(plan.moves[0].margins["room"])  # measured on the bowed lines already
            rows.append(("bend_room", room, params.min_lay_down, room >= params.min_lay_down - 1e-9))
        return rows

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"band_untwist layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )

    def control_points(self, *, local: bool = False) -> np.ndarray:
        spec = self.shape_spec(local=local)
        if self.shape == "eight":
            return fig8.figure_eight_control_points(spec)
        return shapes.shape_control_points(spec)

    def strand_name(self, strand_index: int = 0) -> str:
        return f"rope_{int(strand_index)}"

    def strand_color(self, strand_index: int = 0):
        return tuple(_list(self.cfg.band.color))

    def built_centerline(self, radius: float | None = None) -> np.ndarray:
        """The centreline the tube is swept on: the control points splined, held
        at the resting height, resampled (`rope_mesh` sweeps the tube on this).

        `checks()` measures its bend on its own, because the spline bends
        tighter than the control polygon the `corner_radius` row reads -- and it
        is the spline the tube is built around. ``radius`` is passed in by
        `checks()` (the yaml's literal ``band.tube_radius``), because checks run
        on an unresolved task config where ``rope.radius`` is an interpolation.
        """

        radius = float(self.cfg.rope.radius if radius is None else radius)
        world_points = np.stack(
            [self.position_to_world(point) for point in self.control_points()],
            axis=0,
        )
        centerline = _catmull_rom_centerline(
            world_points,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        centerline = centerline.copy()
        centerline[:, 2] = np.maximum(centerline[:, 2], self.world_z(0.0) + radius)
        return _sample_polyline(centerline, max_segment_length=float(self.cfg.rope.mesh.segment_length))

    def rope_mesh(self) -> RopeMesh:
        """Control points -> smooth centerline -> swept tube mesh.

        Same pipeline as `untangle_continuous.py:rope_mesh`, and for the same
        reasons: spline the sparse control points first and resample second, then
        clamp to the resting height so centripetal Catmull-Rom's undershoot cannot
        sink the tube into the table.
        """

        radius = float(self.cfg.rope.radius)
        centerline = self.built_centerline()
        bottom_clearance = float(centerline[:, 2].min()) - radius - self.world_z(0.0)
        if bottom_clearance < 0.0:
            raise ValueError(
                f"BandUntwist rope spawns {-bottom_clearance * 1000:.2f} mm inside the "
                f"tabletop (band.base_z={float(self.cfg.band.base_z):.4f}, "
                f"rope.radius={radius:.4f}). Raise band.base_z."
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
    # Spawn centreline length (m): the verifier sizes its centreline bins by it.
    rope_length: float = 0.0

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
    """Build the common table with one crossed rope and a plug on each end."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, seed: int = 0) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = BandUntwistLayout(task_cfg, seed=int(seed), task_origin=frames.task_origin)

    def build(self, *, show_viewer: bool = False, include_robot: bool = True) -> BandUntwistScene:
        self.layout.validate()
        tube_radius = float(self.task_cfg.band.tube_radius)
        if abs(tube_radius - float(self.task_cfg.rope.radius)) > 1e-12:
            raise ValueError(
                f"task.band.tube_radius={tube_radius} != task.rope.radius="
                f"{float(self.task_cfg.rope.radius)}: the layout checks would describe a "
                "different tube. Keep the two equal."
            )
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
        # Same tolerance as the layout's end_separation row: at end_frac 0 the gap
        # is exactly min_clearance and float rounding lands a hair under it.
        if len(connectors) == 2 and separation < min_clearance - 1e-9:
            raise ValueError(
                f"the rope's two end plugs spawn {separation * 1000:.0f}mm apart, below the "
                f"{min_clearance * 1000:.0f}mm clearance the gripper needs "
                "(rope.free_end_connector.min_clearance); the layout's end_separation row should have refused this."
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
            rope_length=float(np.linalg.norm(np.diff(mesh.centerline, axis=0), axis=1).sum()),
        )

    def _robot_material(self):
        """Arm outside the deformable coupling by default; see
        `UntangleContinuousSceneBuilder._robot_material` for the history."""

        if bool(getattr(self.task_cfg.pinch, "robot_rope_contact", False)):
            return None
        return gs.materials.Rigid(needs_coup=False)

    def _table_material(self):
        # ``rope.table_friction`` is the table's coup_friction on both paths. The
        # IPC coupler pairs it with the rope's ``fem.friction_mu`` by geometric
        # mean (genesis ipc_coupler/coupler.py); until 2026-09-13 the IPC table
        # kept Genesis's default 0.1, so rope-on-table friction was sqrt(0.3 x
        # 0.1) = 0.17 whatever the yaml said, and a swung tail dragged the rope
        # behind its lift point 5-8 cm (band_untwist_zh.md §8.14).
        if self._rope_backend.name != "pbd":
            return gs.materials.Rigid(coup_type="ipc_only", coup_friction=float(self.task_cfg.rope.table_friction))
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


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Only the
    drawn shape's leaves are derived: the end gap of an open lobe from its
    ``end_frac`` (eight, twist), O|-|O's middle rope from ``middle_frac``, then
    the centre from ``center_x_frac`` / ``center_y_frac`` inside the window
    where the shape and every planned landing fit the workspace and reach.
    Values are cast to float before they go back into OmegaConf. A
    ``ValueError`` (empty range, no window) rejects the draw. The twist's second
    over/under leaf is derived too: the OTHER end is on top at the second
    crossing (the alternating twist, a U twisted one full turn; see the yaml's
    note on ``band.twist``).
    """

    band = task_cfg.band
    if str(band.shape) == "twist":
        band.twist.over_end_x2 = 1 - int(band.twist.over_end_x1)
    layout = BandUntwistLayout(task_cfg)
    shape = layout.shape
    if shape in ("eight", "twist"):
        band[shape].end_gap = float(layout.end_gap_from_frac(float(band[shape].end_frac)))
    if shape == "curls":
        lo, hi = layout.middle_len_bounds()
        band.curls.middle_len = float(lo + min(max(float(band.curls.middle_frac), 0.0), 1.0) * (hi - lo))
    window = layout.centre_window()
    if window is None:
        raise ValueError(f"band_untwist: no centre fits the {shape} with its planned landings in the workspace and reach.")
    center_x, center_y = window.at(float(band.center_x_frac), float(band.center_y_frac))
    band.center_x, band.center_y = float(center_x), float(center_y)


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    BandUntwistLayout(task_cfg).validate()


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
