from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.generation.braid import BraidLayout, BraidSpec, build_braid_spec, verify_braid_spec
from topogym.tasks_legacy.entangle import _swap_crossing_sign_geometry as braid_geometry
from topogym.primitives import ParticleAttachment
from topogym.tasks_legacy._visuals import box_entity_enabled
from topogym.world.rope import (
    RopeEndpointHandle,
    RopeMesh,
    catmull_rom_centerline as _catmull_rom_centerline,
    make_elastic_tube_mesh as _make_elastic_tube_mesh,
    resolve_mesh_dir as _resolve_mesh_dir,
    safe_asset_name as _safe_asset_name,
    sample_polyline as _sample_polyline,
    tensor_to_numpy as _tensor_to_numpy,
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


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class UntangleContinuousLayout:
    """Power strip plus braid-generated rope geometry for the continuous variant.

    Unlike the discrete variant there is no hole board and no hand-authored
    strand path: the whole rope layout comes from a braid word, so ``seed`` is a
    real layout seed here rather than a reserved identity field.
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
            raise ValueError(
                f"UntangleContinuous position must have shape (3,), got {result}."
            )
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported UntangleContinuous coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(
            f"Unsupported UntangleContinuous coordinate_frame={self.coordinate_frame!r}."
        )

    @property
    def n_strands(self) -> int:
        return int(self.cfg.braid.n_strands)

    def braid_layout(self) -> BraidLayout:
        """The task-frame ``braid:`` block as the generator's plain dataclass."""

        braid_cfg = self.cfg.braid
        span = _list(braid_cfg.braid_span)
        return BraidLayout(
            x_start=float(braid_cfg.x_start),
            x_end=float(braid_cfg.x_end),
            center_y=float(braid_cfg.center_y),
            channel_spacing=float(braid_cfg.channel_spacing),
            base_z=float(braid_cfg.base_z),
            over_lift=float(braid_cfg.over_lift),
            braid_span=(float(span[0]), float(span[1])),
            crossing_fill=float(braid_cfg.crossing_fill),
            # swap_crossing_sign's layout axis; absent (untangle_continuous)
            # means the evenly spaced default.
            crossing_frac=(
                None
                if getattr(braid_cfg, "crossing_frac", None) is None
                else float(braid_cfg.crossing_frac)
            ),
        )

    def braid_spec(self) -> BraidSpec:
        """Generate this episode's braid. Deterministic in ``self.seed``.

        ``braid.crossing_sign`` (swap_crossing_sign's anti-shortcut axis) fixes
        the one letter of a length-1 word directly; 0 or absent keeps the
        seed's ``braid/word`` draw, so untangle_continuous and fixed-layout runs
        are unchanged.
        """

        sign = int(getattr(self.cfg.braid, "crossing_sign", 0) or 0)
        word = None
        if sign:
            if int(self.cfg.braid.length) != 1:
                raise ValueError(
                    f"braid.crossing_sign={sign} needs braid.length == 1, "
                    f"got {int(self.cfg.braid.length)}."
                )
            word = (1 if sign > 0 else -1,)
        return build_braid_spec(
            n_strands=self.n_strands,
            length=int(self.cfg.braid.length),
            seed=int(self.seed),
            layout=self.braid_layout(),
            word=word,
        )

    # ----- variation: checks --------------------------------------------------

    def predicted_lift(self) -> float:
        """Task z the oracle's first move lifts to, estimated from the spawn geometry."""

        return braid_geometry.predicted_lift(
            self.braid_spec(),
            float(self.cfg.braid.tube_radius),
            float(self.cfg.pinch.lift_clearance),
        )

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a buildable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate and the
        demo's start-up print. Reads only literal task leaves (``tube_radius``
        is the yaml's copy of ``rope.radius``; the box is ``workspace:``), so it
        works on an unresolved task config.
        """

        braid_cfg, ws = self.cfg.braid, self.cfg.workspace
        connector = self.cfg.rope.free_end_connector
        strip_size = _list(self.cfg.power_strip.size)
        return braid_geometry.braid_checks(
            self.braid_spec(),
            tube_radius=float(braid_cfg.tube_radius),
            min_clearance=float(getattr(connector, "min_clearance", 0.07)),
            # Lying on its side, the plug reaches past the rope end by half the
            # grasp column, the flange and the pin (see _add_free_end_connectors).
            plug_ahead=(
                0.5 * float(connector.column_height)
                + float(connector.flange_height)
                + float(connector.pin_depth)
            ),
            flange_radius=float(connector.flange_radius),
            strip_half_length=0.5 * float(strip_size[1]),
            workspace_x=(float(ws.x[0]), float(ws.x[1])),
            workspace_y=(float(ws.y[0]), float(ws.y[1])),
            workspace_z_max=float(ws.z_max),
            workspace_margin=float(ws.margin),
            lift_clearance=float(self.cfg.pinch.lift_clearance),
            lane_overshoot=float(getattr(self.cfg.pinch, "lane_overshoot", 0.0) or 0.0),
            place_pullback=float(self.cfg.pinch.place_pullback),
            separation_threshold=float(self.cfg.success.separation_threshold),
        )

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"untangle_continuous layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )

    def strand_name(self, strand_index: int) -> str:
        return f"rope_{int(strand_index)}"

    def strand_color(self, strand_index: int):
        colors = _list(self.cfg.braid.strand_colors)
        return tuple(colors[int(strand_index) % len(colors)])

    def rope_mesh(self, strand_index: int, control_points: np.ndarray) -> RopeMesh:
        """Braid control points -> smooth centerline -> swept tube mesh.

        The lane swaps come out of the generator as hard corners; the same
        Catmull-Rom pass cable_routing uses on its hand-authored waypoints rounds
        them here. Rounding matters twice over: a curvature discontinuity renders
        as a facet, and it is also where a PBD tube pinches on itself.
        """

        radius = float(self.cfg.rope.radius)
        world_points = np.stack(
            [self.position_to_world(point) for point in np.asarray(control_points, dtype=float)],
            axis=0,
        )
        # Spline the SPARSE control points, then resample -- the same order
        # cable_routing uses. Order matters: resampling first pins the spline to
        # the chords of the control polyline, so each lane swap can only round
        # over one sample spacing and reads as a visible kink (measured: typical
        # turn angle 19.9 deg vs 12.5 deg for this order).
        centerline = _catmull_rom_centerline(
            world_points,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        # Centripetal Catmull-Rom undershoots below its control points where their
        # spacing changes abruptly (a strand sitting out the early crossings has a
        # 272 mm run butted against a ~40 mm swap window). Left alone that sinks
        # the tube ~3 mm into the tabletop, and PBD resolves the penetration with a
        # huge impulse on step 1 -- the mesh stretches into a sheet across the
        # domain. Clamping the centerline to the resting height is exact rather
        # than a fudge: a rope lying on the table has its centerline exactly one
        # radius up, and the clamp only engages where the spline dipped below.
        floor_z = self.world_z(0.0) + radius
        centerline = centerline.copy()
        centerline[:, 2] = np.maximum(centerline[:, 2], floor_z)
        # Uniform ring spacing for the swept tube (smoothness already decided above).
        centerline = _sample_polyline(
            centerline,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        bottom_clearance = float(centerline[:, 2].min()) - radius - self.world_z(0.0)
        if bottom_clearance < 0.0:
            # Can no longer be tripped by spline undershoot; this catches a
            # misconfigured braid.base_z below the rope radius.
            raise ValueError(
                f"UntangleContinuous strand {strand_index} spawns "
                f"{-bottom_clearance * 1000:.2f} mm inside the tabletop "
                f"(braid.base_z={float(self.cfg.braid.base_z):.4f}, rope.radius={radius:.4f}). "
                "Raise braid.base_z."
            )
        model = str(self.cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported UntangleContinuous rope model: {model!r}.")
        vertices, faces = _make_elastic_tube_mesh(
            centerline,
            radius=radius,
            radial_segments=int(self.cfg.rope.mesh.radial_segments),
        )
        mesh_dir = _resolve_mesh_dir(self.cfg.rope.mesh.output_dir)
        name = _safe_asset_name(self.strand_name(strand_index))
        path = mesh_dir / f"{name}_{model}.obj"
        return RopeMesh(
            path=path,
            centerline=centerline,
            vertices=vertices,
            faces=faces,
            endpoint_centers=(centerline[0], centerline[-1]),
        )


@dataclass
class UntangleContinuousScene:
    scene: Any
    manifest: EntityManifest
    layout: UntangleContinuousLayout
    braid: BraidSpec
    cameras: dict = field(default_factory=dict)
    rope_handles: dict[str, RopeEndpointHandle] = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None
    # strand index -> (P,) normalized arc length along the rope for each PBD
    # particle. See `_particle_arclength`; this is what lets anything downstream
    # recover an *ordered* curve from the unordered particle cloud.
    particle_arclength: dict[int, np.ndarray] = field(default_factory=dict)
    # strand index -> rigid grip fitting welded to that rope's free end.
    free_end_connectors: dict[int, Any] = field(default_factory=dict)
    # Coulomb friction against the tabletop, installed by the builder (it wraps
    # `scene.step`). Genesis supplies nothing that works at rest -- see
    # `TabletopParticleFriction`. Kept here so it can be inspected or uninstalled.
    table_friction: Any | None = None
    # Solver backend (rope_backends protocol). All node access below goes through
    # it, so nothing downstream branches on the solver.
    rope_backend: Any | None = None

    @property
    def strand_entities(self) -> dict[int, Any]:
        """strand index -> rope entity, in braid order."""

        return {
            index: self.rope_handles[self.layout.strand_name(index)].entity
            for index in range(self.layout.n_strands)
        }

    def strand_centerline(self, strand_index: int, *, samples: int = 80) -> np.ndarray:
        """Ordered centerline polyline for one strand, from its particle cloud.

        Particles are unordered (the tube is tetrahedralized), so each one's
        stored normalized arc length is used to bin them along the rope; the mean
        position of a bin is a centerline sample. Averaging over a bin also
        averages away the tube's radial thickness, so these are true centerline
        points rather than surface points -- and it makes the result robust to
        the jitter of any individual particle.
        """

        strand_index = int(strand_index)
        positions = self.strand_particles(strand_index)
        arclength = self.particle_arclength[strand_index]
        if len(arclength) != len(positions):
            raise ValueError(
                f"strand {strand_index}: {len(arclength)} arclengths for "
                f"{len(positions)} particles -- the scene's material map is stale."
            )
        edges = np.linspace(0.0, 1.0, int(samples) + 1)
        bucket = np.clip(np.digitize(arclength, edges[1:-1]), 0, int(samples) - 1)
        points = [
            positions[bucket == index].mean(axis=0)
            for index in range(int(samples))
            if np.any(bucket == index)
        ]
        if len(points) < 2:
            raise ValueError(f"strand {strand_index} collapsed to < 2 centerline samples.")
        return np.stack(points, axis=0)

    def strand_particles(self, strand_index: int) -> np.ndarray:
        """Current ``(P, 3)`` rope node positions for one strand.

        Unordered -- pair with ``particle_arclength[strand_index]`` to recover a
        curve.
        """

        return _particles(self.rope_backend, self.strand_entities[int(strand_index)])

    def grasp_band_indices(self, strand_index: int, arclength: float, *, half_width: float):
        """Particle indices of ``strand_index`` within ``half_width`` of ``arclength``.

        Only the *selection* lives here, because only this task knows that a
        graspable band means "a stretch of rope around an arc length". The
        welding itself is `topogym.primitives.ParticleAttachment`.

        Selecting by stored arc length rather than by 3D proximity matters in a
        tangle: proximity would happily pick up two far-apart stretches of the
        same rope that merely happen to lie near each other.
        """

        s = self.particle_arclength[int(strand_index)]
        indices = np.flatnonzero(np.abs(s - float(arclength)) <= float(half_width))
        if len(indices) == 0:
            indices = np.array([int(np.argmin(np.abs(s - float(arclength))))], dtype=int)
        return indices

    def grasp_attachment(
        self,
        strand_index: int,
        arclength: float,
        *,
        half_width: float,
        parent_pos_fn,
        offset=(0.0, 0.0, 0.0),
        taper: float = 0.0,
    ) -> ParticleAttachment:
        """Assisted grasp of a mid-rope band (design doc §3.5).

        A kinematic weld rather than a friction pinch: this benchmark measures
        topological reasoning, so grasp success is held at 100% and low-level
        control error is kept out of the measurement.

        ``taper`` is the fraction of the half-width over which the grip fades to
        zero (0 = the whole band is held rigidly, 1 = the grip peaks only at the
        exact centre). Fading it matters physically: a rigidly held band is a
        splint that cannot bend or rotate, so every bit of bending the motion
        demands is forced into the two edges. Measured, that kinks a 4 mm-radius
        rope to a 6-9 mm bend radius -- tighter than any real cable of that
        thickness -- which is where the blow-ups start.

        The weight is a Tukey window over arc-length distance from the band
        centre: flat in the core so the grasp still holds firmly, cosine-faded at
        the edges so the rope leaves the grip smoothly.
        """

        strand_index = int(strand_index)
        indices = self.grasp_band_indices(strand_index, arclength, half_width=half_width)
        weights = None
        taper = float(np.clip(taper, 0.0, 1.0))
        if taper > 0.0:
            distance = np.abs(
                self.particle_arclength[strand_index][indices] - float(arclength)
            ) / max(float(half_width), 1e-12)
            flat = 1.0 - taper
            ramp = np.clip((np.clip(distance, 0.0, 1.0) - flat) / max(taper, 1e-12), 0.0, 1.0)
            weights = 0.5 * (1.0 + np.cos(np.pi * ramp))
        return ParticleAttachment(
            self.strand_entities[strand_index],
            indices,
            parent_pos_fn,
            offset=offset,
            weights=weights,
        )


class UntangleContinuousSceneBuilder:
    """Build the common table plus a power strip with braided ropes hanging off it."""

    #: The layout that turns the task config into rope geometry; swap_crossing_sign
    #: substitutes its own (per-crossing positions, lead-in bends, its own checks).
    layout_cls = UntangleContinuousLayout

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, seed: int = 0) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = self.layout_cls(
            task_cfg,
            seed=int(seed),
            task_origin=frames.task_origin,
        )

    def build(
        self,
        *,
        show_viewer: bool = False,
        include_robot: bool = True,
    ) -> UntangleContinuousScene:
        tube_radius = float(self.task_cfg.braid.tube_radius)
        if abs(tube_radius - float(self.task_cfg.rope.radius)) > 1e-12:
            raise ValueError(
                f"braid.tube_radius {tube_radius} != rope.radius "
                f"{float(self.task_cfg.rope.radius)}: the layout checks would describe a "
                "different rope than the one being built."
            )
        self.layout.validate()
        braid = self.layout.braid_spec()
        # The generator's own invariants (reduced word, non-overlapping and
        # flat-enough swap windows, over_lift clearing the particle contact,
        # control points inside the workspace) -- checked here, where the scene
        # is built, rather than only in the inspect demo.
        workspace = self.task_cfg.workspace
        # Those invariants are all statements about a braid word and its swap
        # windows, so they only apply to a layout built from one. A layout that
        # builds its ropes some other way (swap_crossing_sign's three-rope
        # two-crossing cell since 2026-09-12) states its own invariants in its
        # `checks()`, which `validate()` above has just enforced.
        if isinstance(braid, BraidSpec):
            report = verify_braid_spec(
                braid,
                rope_radius=float(self.task_cfg.rope.radius),
                particle_size=float(self.task_cfg.rope.particle_size),
                x_bounds=(float(workspace.x[0]), float(workspace.x[1])),
                y_bounds=(float(workspace.y[0]), float(workspace.y[1])),
            )
            if not report.ok:
                raise ValueError(f"UntangleContinuous braid self-check failed: {report}")

        backend = _make_rope_backend(self.task_cfg.rope)
        self._rope_backend = backend
        backend.pre_scene()

        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            scene_options=backend.scene_options(),
        )
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

        self._add_board(scene, manifest, layout)
        self._add_power_strip(scene, manifest, layout)
        rope_specs = self._add_ropes(scene, manifest, layout, braid)
        connectors = self._add_free_end_connectors(scene, manifest, layout, rope_specs)

        # Free-end clearance rule (2026-08-07, from viewer observation): two
        # plugs close enough that both sit inside the gripper's span make the
        # closing fingers ambiguous, and the weld assist would hide it. Enforce
        # a minimum spawn separation between free-end connectors; the threshold
        # is one finger half-span (40mm) + plug column radius + margin, so the
        # neighbouring plug stays clear of the closing gripper.
        if len(connectors) >= 2:
            min_clearance = float(
                getattr(self.task_cfg.rope.free_end_connector, "min_clearance", 0.07)
            )
            free_ends = {
                strand: np.asarray(rope_specs[strand][2][1], dtype=float)
                for strand in connectors
            }
            strands = sorted(free_ends)
            for a_index, a in enumerate(strands):
                for b in strands[a_index + 1 :]:
                    separation = float(np.linalg.norm(free_ends[a][:2] - free_ends[b][:2]))
                    if separation < min_clearance:
                        raise ValueError(
                            f"free-end connectors of strands {a} and {b} spawn "
                            f"{separation * 1000:.0f}mm apart, below the "
                            f"{min_clearance * 1000:.0f}mm clearance the gripper needs "
                            "(rope.free_end_connector.min_clearance)."
                        )

        # End-constraint *capacity* is declared before finalize (= scene.build):
        # the FEM backend's coupler reads it during build; PBD just buffers.
        anchor_radius = float(self.task_cfg.rope.anchor_radius)
        # rope.fem.rest_shape: "spawn" (the default both this task and
        # swap_crossing_sign have always built) means the stress-free shape is the
        # shape the rope was born in, so a stretch that is lifted and laid down
        # springs back toward its spawn curve -- measured 2026-09-11 as the reason a
        # laid tail settles 4-9 cm from where the planner draws it. "straight" makes
        # it relax toward a straight tube instead, as cable_routing builds its cable.
        rest_shape = str(
            getattr(getattr(self.task_cfg.rope, "fem", None), "rest_shape", None) or "spawn"
        )
        if rest_shape not in ("spawn", "straight"):
            raise ValueError(
                f"rope.fem.rest_shape must be 'spawn' or 'straight', got {rest_shape!r}."
            )
        for strand_index, (_rope_name, rope_entity, endpoint_centers, centerline) in enumerate(
            rope_specs
        ):
            if rest_shape == "straight":
                backend.declare_rest_straight(rope_entity, centerline)
            backend.declare_anchor(rope_entity, (endpoint_centers[0],), anchor_radius)
            if strand_index in connectors and bool(
                getattr(self.task_cfg.rope.free_end_connector, "follow_enabled", True)
            ):
                backend.declare_follow(rope_entity, endpoint_centers[1], anchor_radius)

        tabletop_builder.finalize(tabletop)
        rope_handles: dict[str, RopeEndpointHandle] = {}
        particle_arclength: dict[int, np.ndarray] = {}
        for strand_index, (rope_name, rope_entity, endpoint_centers, centerline) in enumerate(
            rope_specs
        ):
            particle_arclength[strand_index] = _particle_arclength(
                backend, rope_entity, centerline
            )
            # Single-end anchor (design doc decision 2): only the -x end is welded
            # into the power strip; the +x end stays free so it can be grasped and
            # lifted by the lift-test.
            start_indices = tuple(backend.anchor(rope_entity))
            connector = connectors.get(strand_index)
            if not bool(
                getattr(self.task_cfg.rope.free_end_connector, "follow_enabled", True)
            ):
                # Diagnostic gate (rope.free_end_connector.follow_enabled=false):
                # leave the rope end unattached so plug motion and rope motion can
                # be attributed separately. Not a task configuration.
                connector = None
            if connector is not None:
                # The link-carried attachment (PBD: fix_particles_to_link; FEM:
                # constraint targets synced from the link's pose every step).
                # Either way the band follows the link's ROTATION and no position
                # is ever written into the solver -- the crucial difference from
                # the hand-rolled world-axis weld this task used before. See the
                # blow-up debug log for what that weld did.
                end_indices = tuple(backend.follow_link(rope_entity, connector.base_link))
            else:
                end_indices = tuple(
                    backend.resolve_indices(
                        rope_entity, (endpoint_centers[1],), anchor_radius
                    )
                )
            rope_handles[rope_name] = RopeEndpointHandle(
                name=rope_name,
                entity=rope_entity,
                start_center=endpoint_centers[0],
                end_center=endpoint_centers[1],
                start_indices=start_indices,
                end_indices=end_indices,
            )

        rope_scene = UntangleContinuousScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            braid=braid,
            cameras=tabletop.cameras,
            rope_handles=rope_handles,
            tabletop=tabletop,
            particle_arclength=particle_arclength,
            free_end_connectors=connectors,
            rope_backend=backend,
        )
        rope_scene.table_friction = self._install_table_friction(rope_scene)
        return rope_scene

    def _install_table_friction(self, rope_scene: UntangleContinuousScene):
        """Install Coulomb friction against the tabletop, wrapping ``scene.step``.

        Installed here rather than handed to callers as a context manager: this is
        part of the task's physics, not a temporary intervention, and a demo that
        forgot to enter the context would silently run under different physics.
        """

        friction_cfg = getattr(self.task_cfg.rope, "tabletop_friction", None)
        if friction_cfg is None or not bool(getattr(friction_cfg, "enabled", False)):
            return None
        if self._rope_backend.name != "pbd":
            # The shim patches a PBD-specific failure (velocity-impulse tabletop
            # friction, useless at rest). FEM materials carry friction_mu and IPC
            # friction is variational -- the problem does not exist there.
            return None
        sim = self.env_cfg.sim
        return rope_prefab.TabletopParticleFriction(
            rope_scene.scene,
            list(rope_scene.strand_entities.values()),
            surface_z=rope_scene.layout.world_z(0.0),
            contact_band=float(friction_cfg.contact_band),
            static_mu=float(friction_cfg.static_mu),
            kinetic_mu=float(friction_cfg.kinetic_mu),
            dt=float(sim.dt),
            gravity=float(_list(sim.gravity)[2]),
            max_load_factor=float(friction_cfg.max_load_factor),
        ).install()

    def _robot_material(self):
        """Robot material, with rope<->robot PBD contact off by default.

        Unlike every other rope task in this repo, the gripper here closes around
        the *rope itself* rather than around a rigid handle that the rope is
        attached to -- there is no handle mid-rope to grab. That puts rigid finger
        geometry in direct contact with PBD particles, which this repo has
        repeatedly found to be the one thing that tears these ropes apart:

        - `untangle_connector_flyout_debug_zh.md` §2 A/B table: contact ON tore the
          rope mid-section (particles parked at the solver domain corner, the skin
          stretched into a beam); contact OFF ran clean end to end.
        - `PBDParticleAttachmentDragPrimitive`'s own docstring: rigid finger-to-PBD
          contact is "fragile in Genesis 1.1.0".
        - This task's design doc §5.2 lists it as a known risk and picks kinematic
          attachment specifically to sidestep it.

        The grasp is a kinematic weld by design (design doc §3.5) -- grasp success
        is held at 100% so the benchmark measures topological reasoning rather than
        low-level control. Finger contact therefore contributes no signal, only a
        fight with the weld. The fingers still visibly close around the rope; they
        just no longer push the particles the weld is holding.

        NOTE for whoever re-enables this: Genesis *does* support per-link coupling
        via `gs.materials.Rigid(needs_coup=True, coup_links=(...))`, which bakes a
        per-geom flag the legacy coupler honours -- that answers the "若 Genesis
        支持 per-link，待查" question left open in the flyout debug log. It is an
        include-list, so it means enumerating every arm link except the two
        fingers, and its docstring claims IPC-only support, so it needs its own
        validation run before being relied on.
        """

        if bool(getattr(self.task_cfg.pinch, "robot_rope_contact", False)):
            return None
        return gs.materials.Rigid(needs_coup=False)

    def _table_material(self):
        """Table material, with rope<->table grip raised above the Genesis default.

        `coup_friction` is what holds a PBD body against a rigid surface, and it
        is a different knob from the rope's own particle friction: the coupler
        reads the *rigid geom's* `coup_friction` for deformable-vs-rigid contact
        (`legacy_coupler._func_collide_in_rigid_geom`), while
        `rope.elastic.*_friction` only governs particle-to-particle contact.

        That separation is what this task needs. Rope-on-rope friction has to stay
        low -- the discrete variant found that raising it makes a moved rope drag
        whatever it is lying across along with it -- but rope-on-table friction
        wants to be high, or the ropes skate around on residual motion. Genesis'
        0.1 default is the slippery end of that.
        """

        if self._rope_backend.name != "pbd":
            # Under IPC the table is a static 'ipc_only' body; rope<->table
            # friction comes from the FEM material's friction_mu and IPC's
            # variational friction, not from coup_friction (a legacy-coupler
            # knob). Calibrate there if the ropes skate.
            return gs.materials.Rigid(coup_type="ipc_only")
        return gs.materials.Rigid(
            coup_friction=float(self.task_cfg.rope.table_friction),
        )

    def _static_kwargs(self) -> dict:
        """Material kwargs for the task's own fixed rigids (board, power strip).

        None from the PBD backend keeps the Genesis default (current behavior);
        the FEM backend supplies coup_type='ipc_only' so the IPC coupler accepts
        them as static contact bodies.
        """

        material = self._rope_backend.static_rigid_material()
        return {} if material is None else {"material": material}

    def _add_board(self, scene, manifest: EntityManifest, layout) -> None:
        if not box_entity_enabled(self.task_cfg.board):
            return
        manifest.add(
            self.task_cfg.board.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(layout.position_to_world(self.task_cfg.board.pos)),
                    size=tuple(self.task_cfg.board.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.board.color),
                name=self.task_cfg.board.name,
                **self._static_kwargs(),
            ),
        )

    def _add_power_strip(self, scene, manifest: EntityManifest, layout) -> None:
        strip = self.task_cfg.power_strip
        has_collision = bool(getattr(strip, "collision", False))
        # A collision-free strip must be a decoration under IPC (needs_coup=False);
        # with collision on it is a static contact body (ipc_only).
        material = (
            self._rope_backend.static_rigid_material()
            if has_collision
            else self._rope_backend.decoration_rigid_material()
        )
        material_kwargs = {} if material is None else {"material": material}
        manifest.add(
            strip.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(layout.position_to_world(strip.pos)),
                    size=tuple(_list(strip.size)),
                    fixed=True,
                    collision=has_collision,
                ),
                surface=materials.plastic("fixture", strip.color),
                name=strip.name,
                **material_kwargs,
            ),
        )

    def _add_free_end_connectors(
        self,
        scene,
        manifest: EntityManifest,
        layout: UntangleContinuousLayout,
        rope_specs,
    ) -> dict[int, Any]:
        """A rigid grip fitting on each rope's free end, for the gripper to hold.

        It plugs into nothing -- it exists only so the arm has a rigid body to
        grasp. That is what every other rope task in this repo does, and the
        reason is mechanical rather than cosmetic:

        - the gripper can close on a **rigid** body with the rigid solver's full
          contact handling, instead of crushing PBD particles through the
          coupler's soft velocity projection (which does not prevent penetration
          and flips its normal once a particle is deep enough -- see the
          blow-up debug log);
        - the rope follows via `fix_particles_to_link`, which carries the link's
          orientation. The hand-rolled weld it replaces held its particles at
          fixed *world-axis* offsets, so a band captured while the rope lay flat
          stayed forced-horizontal forever; lifting it then demanded a ~90 degree
          turn within a few mm at the band edge, kinking a 4 mm-radius rope to a
          5-7 mm bend radius. That was the blow-up.
        """

        connector_cfg = getattr(self.task_cfg.rope, "free_end_connector", None)
        if connector_cfg is None or not bool(getattr(connector_cfg, "enabled", False)):
            return {}

        connector_path = rope_prefab.connector_obj_path(
            connector_cfg,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
        )
        # Lying flat, the widest part (the flange) is what rests on the table, so
        # the plug's axis sits one flange radius up.
        axis_z = layout.world_z(0.0) + float(connector_cfg.flange_radius)

        connectors: dict[int, Any] = {}
        for strand_index, (_name, _entity, endpoint_centers, _centerline) in enumerate(rope_specs):
            free_end = np.asarray(endpoint_centers[1], dtype=float)
            name = f"free_end_connector_{strand_index}"
            connectors[strand_index] = manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Mesh(
                        file=str(connector_path),
                        pos=(float(free_end[0]), float(free_end[1]), axis_z),
                        # The mesh is a solid of revolution about its local +z, with
                        # the origin at the grasp column's center. -90 deg about y
                        # sends local +z to world -x, which lays the plug on its side
                        # pointing back down the rope: cap (where the cable enters)
                        # toward the anchor, pin sticking out into free space. The
                        # discrete variant stands the same part upright with the pin
                        # in a socket -- here it plugs into nothing, as asked.
                        euler=(0.0, -90.0, 0.0),
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
                        # The rope's own particles live inside this fitting by
                        # design; coupling them to it as well would have the
                        # attachment and the contact solver fighting over the same
                        # particles every step.
                        needs_coup=False,
                    ),
                    surface=materials.plastic("connector", connector_cfg.color),
                    name=name,
                ),
            )
        return connectors

    def _add_ropes(
        self,
        scene,
        manifest: EntityManifest,
        layout: UntangleContinuousLayout,
        braid: BraidSpec,
    ) -> list[tuple[str, Any, tuple[np.ndarray, np.ndarray], np.ndarray]]:
        model = str(self.task_cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported UntangleContinuous rope model: {model!r}.")

        rope_specs: list[tuple[str, Any, tuple[np.ndarray, np.ndarray], np.ndarray]] = []
        for strand_index in range(layout.n_strands):
            mesh = layout.rope_mesh(strand_index, braid.control_points[strand_index])
            _write_obj(mesh.path, mesh.vertices, mesh.faces)
            name = layout.strand_name(strand_index)
            rope_entity = scene.add_entity(
                rope_prefab.tube_morph(mesh.path, self.task_cfg.rope),
                material=self._rope_backend.material(),
                surface=materials.plastic(
                    "deformable",
                    layout.strand_color(strand_index),
                    vis_mode="visual",
                ),
                name=name,
            )
            manifest.add(name, rope_entity)
            rope_specs.append((name, rope_entity, mesh.endpoint_centers, mesh.centerline))
        return rope_specs


def settle_scene(
    rope_scene: UntangleContinuousScene,
    *,
    steps: int | None = None,
    max_particle_step: float | None = None,
    require_converged: bool | None = None,
) -> tuple[int, float]:
    """Step until the ropes stop moving, so crossings are counted on a resting state.

    Returns ``(steps_taken, final_max_particle_step)``, where the second value is
    the largest single-step particle displacement in meters. Displacement rather
    than velocity: it needs no solver internals, and the threshold reads directly
    as "no particle moved more than this in one step".

    The over-strand starts held clear of the under-strand by ``braid.over_lift``;
    gravity is what puts it down onto the rope below, so contact height and drape
    are decided by physics rather than by the generator guessing them.
    """

    cfg = rope_scene.layout.cfg
    limit = int(steps if steps is not None else cfg.settle.steps)
    step_eps = float(
        max_particle_step
        if max_particle_step is not None
        else cfg.settle.max_particle_step
    )
    trace_every = int(getattr(cfg.settle, "trace_every", 0))
    damp_every = int(getattr(cfg.settle, "damp_every", 0))
    entities = list(rope_scene.strand_entities.values())

    def _shapes() -> list[np.ndarray]:
        return [
            rope_scene.strand_centerline(index)
            for index in sorted(rope_scene.strand_entities)
        ]

    previous = _shapes()
    backend = rope_scene.rope_backend
    previous_particles = [_particles(backend, entity) for entity in entities]
    taken = 0
    busy = float("inf")
    peak = float("inf")
    rebound = float("nan")
    just_damped = False
    for _ in range(limit):
        rope_scene.scene.step()
        taken += 1
        # Gate on how far the rope's SHAPE moved, not on individual particles.
        # Two earlier versions of this metric failed in opposite directions: the
        # max over particles was vetoed by one jittering particle, and the 95th
        # percentile was blind -- most particles already rest on the table, so a
        # falling minority never reaches the 95th percentile and settling
        # "finished" after 26 steps with the crossings still in mid-air. Binned
        # centerline points average out per-particle noise while a whole falling
        # segment still registers at full size.
        current = _shapes()
        busy = max(
            float(np.linalg.norm(now - before, axis=1).max())
            for now, before in zip(current, previous)
        )
        current_particles = [_particles(backend, entity) for entity in entities]
        # Reported only, never gated on: useful for telling "the rope is moving"
        # apart from "one particle is exploding".
        peak = max(
            float(np.linalg.norm(now - before, axis=1).max())
            for now, before in zip(current_particles, previous_particles)
        )
        previous, previous_particles = current, current_particles
        if just_damped:
            # Motion in the step right after every velocity was zeroed. This is
            # the discriminator between the two kinds of energy source: leftover
            # momentum cannot survive the zeroing, so whatever moves here is being
            # created *this step* by constraint projection. A rebound that matches
            # the undamped motion means a permanently violated constraint (see
            # supervision.particle_spacing_reports); a near-zero value means the
            # motion was just momentum and more settling would fix it.
            rebound = busy
            just_damped = False
        if damp_every and taken % damp_every == 0:
            _damp_velocities(backend, entities)
            just_damped = True
        if trace_every and taken % trace_every == 0:
            print(
                f"  settle step={taken:>4} shape={busy * 1000:7.4f} mm/step "
                f"particle_max={peak * 1000:7.4f} mm/step "
                f"post_damp_rebound={rebound * 1000:7.4f} mm/step"
            )
        if busy <= step_eps:
            break
    else:
        strict = (
            bool(getattr(cfg.settle, "require_converged", False))
            if require_converged is None
            else bool(require_converged)
        )
        if strict:
            raise RuntimeError(
                f"UntangleContinuous settle did not converge: after {limit} steps the "
                f"rope shape still moves {busy * 1000:.4f} mm/step (limit "
                f"{step_eps * 1000:.4f}; noisiest single particle {peak * 1000:.4f}). "
                "Set settle.trace_every to watch the decay curve: still falling means "
                "raise settle.steps, flat means this is the solver's noise floor and the "
                "limit is below what PBD can reach."
            )
    return taken, busy


def _particles(backend, rope_entity) -> np.ndarray:
    return np.asarray(backend.nodes(rope_entity), dtype=float)


def _damp_velocities(backend, entities) -> None:
    """Bleed kinetic energy out of the ropes by zeroing particle velocities.

    Genesis' PBD elastic material exposes no velocity damping -- ``rho``,
    frictions, compliances, and the three ``*_relaxation`` factors (which are
    constraint solver relaxation, not damping). A 0.44 m rope welded at one end
    only, excited by the ~16 mm drop the braid spawns it with, therefore rings
    for a very long time: nothing removes the energy except table friction, and
    raising friction alone did not stop it.

    Positions are never touched, only velocities, so the rope always stays in a
    configuration physics actually produced. Applied during settling only -- it
    is the equivalent of letting a real rope come to rest before starting, and it
    must not run while the robot is manipulating.
    """

    for entity in entities:
        backend.zero_node_velocities(entity)


def _particle_arclength(backend, rope_entity, centerline: np.ndarray) -> np.ndarray:
    """Give every PBD particle its normalized position along the rope (0..1).

    The tube is tetrahedralized (``tube_morph`` uses ``force_retet=True``), so the
    particle cloud carries no ordering: index 0 is not the anchored tip and
    consecutive indices are not neighbours. Anything that needs a *curve* — the
    top-down crossing detector above all — must first recover that ordering.

    Particle identity is fixed for the life of the entity, and so is each
    particle's position within the rope's material. So the mapping is computed
    once here, at spawn, where the exact centerline is still known: each particle
    takes the arc length of its nearest centerline vertex. Afterwards the rope can
    deform arbitrarily and the mapping stays valid.
    """

    particles = _particles(backend, rope_entity)
    centerline = np.asarray(centerline, dtype=float)
    segment = np.linalg.norm(np.diff(centerline, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(segment)])
    total = float(cumulative[-1])
    if total <= 0.0:
        raise ValueError("Degenerate rope centerline: zero total length.")
    # (P, C) distances, then nearest centerline vertex per particle.
    nearest = np.argmin(
        np.linalg.norm(particles[:, None, :] - centerline[None, :, :], axis=2),
        axis=1,
    )
    return cumulative[nearest] / total
