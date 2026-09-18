from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.planning import (
    arc_route_points,
    helix_route_points,
    lead_in_route_point,
    plug_spawn_point,
    tail_arc_route_points,
)
from topogym.world.rope import (
    RopeEndpointHandle,
    RopeMesh,
    make_elastic_tube_mesh as _make_elastic_tube_mesh,
    resolve_mesh_dir as _resolve_mesh_dir,
    safe_asset_name as _safe_asset_name,
    sample_polyline as _sample_polyline,
    write_obj as _write_obj,
)
from topogym.tasks_legacy._visuals import box_entity_enabled
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


def _fixture_items(fixtures_cfg) -> list[tuple[str, Any]]:
    return [(str(name), fixture) for name, fixture in fixtures_cfg.items()]


def connector_pose(rope_cfg) -> str:
    """How the free-end plug sits: ``upright`` (in a socket) or ``flat``.

    ``upright`` is the cable_routing shape: the plug stands on its pin in a
    port, the rope climbs its bore and leaves through the cap on top. That puts
    the rope's last centimetres vertically between the gripper's pads.

    ``flat`` lays it on its side with nothing to plug into (the untangle
    variant's arrangement), so the rope enters horizontally along the plug's
    axis while the pads close across it. Chosen for rope_winding, where the
    gripper carries the plug through two full orbits and any rope in the pads'
    path gets wound onto them.
    """

    handle_cfg = getattr(rope_cfg, "endpoint_handle", None)
    connector_cfg = getattr(handle_cfg, "connector", None) if handle_cfg else None
    pose = str(getattr(connector_cfg, "pose", "upright") or "upright")
    if pose not in ("upright", "flat"):
        raise ValueError(
            f"rope.endpoint_handle.connector.pose must be 'upright' or 'flat', got {pose!r}."
        )
    return pose


def rope_axis_heading(mesh: RopeMesh) -> float:
    """Compass angle the rope arrives at its free end on, in radians.

    A flat-lying plug has to point back down the rope: the cap swallows the
    cable, the pin sticks out the far side. This is also the yaw the gripper
    wants, since its pads must close ACROSS the plug's axis rather than along
    it -- see the demo's grasp yaw.
    """

    tail = np.asarray(mesh.centerline[-1], dtype=float)
    before = np.asarray(mesh.centerline[-2], dtype=float)
    direction = tail[:2] - before[:2]
    if float(np.linalg.norm(direction)) <= 1e-9:
        return 0.0
    return float(np.arctan2(direction[1], direction[0]))


@dataclass(frozen=True)
class CableRoutingSignature:
    """Ordered routing target around fixtures."""

    entries: tuple[tuple[str, str], ...]

    def to_info(self) -> list[dict[str, str]]:
        return [{"fixture": fixture, "relation": relation} for fixture, relation in self.entries]


@dataclass(frozen=True)
class CableRoutingLayout:
    """Board, fixture, and route geometry for Cable Routing."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(f"Cable position must have shape (3,), got {result}.")
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported cable coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(
            f"Unsupported cable coordinate_frame={self.coordinate_frame!r}."
        )

    def fixture_pos(self, name: str, *, z: float | None = None) -> np.ndarray:
        fixture = self.cfg.fixtures[str(name)]
        # `pos: [x, y, z]`, or three scalar keys `x / y / z` for a fixture whose
        # position is a variation axis (the randomizer addresses leaves by
        # dotted path and cannot index a list; rope_unwinding).
        if "pos" in fixture:
            pos = np.asarray(_list(fixture.pos), dtype=float)
        else:
            pos = np.array([float(fixture.x), float(fixture.y), float(fixture.z)], dtype=float)
        if z is not None:
            pos[2] = float(z)
        return self.position_to_world(pos)

    def fixture_type(self, name: str) -> str:
        return str(self.cfg.fixtures[str(name)].type)

    def fixture_names(self) -> tuple[str, ...]:
        return tuple(str(name) for name in self.cfg.fixtures.keys())

    def route_point(self, point_spec) -> np.ndarray:
        point = _list(point_spec)
        if isinstance(point, str):
            return self.fixture_pos(point, z=float(self.cfg.rope.z))

        if "plug_spawn_from" in point:
            # rope_winding's plug spawn point as a rule of the post and the
            # anchor (`planning/waypoint.py::plug_spawn_point`); the numbers
            # live in `rope.spawn_arc` next to the arc's sweep.
            arc = self.cfg.rope.spawn_arc
            return plug_spawn_point(
                self.fixture_pos(str(point.get("anchor", "S")), z=0.0),
                self.fixture_pos(str(point["plug_spawn_from"]), z=0.0),
                float(arc.plug_distance),
                np.radians(float(arc.plug_bearing_deg)),
                np.radians(float(arc.anchor_lead_deg)),
                self.world_z(float(self.cfg.rope.z)),
            )

        if "pos" in point:
            pos = np.asarray(_list(point["pos"]), dtype=float)
            if pos.shape == (2,):
                pos = np.array([pos[0], pos[1], float(self.cfg.rope.z)], dtype=float)
            if pos.shape != (3,):
                raise ValueError(f"pos route point must have shape (2,) or (3,), got {pos}.")
            z_offset = float(point.get("z_offset", 0.0))
            xy_offset = np.asarray(point.get("xy_offset", [0.0, 0.0]), dtype=float)
            if xy_offset.shape != (2,):
                raise ValueError(f"xy_offset must have shape (2,), got {xy_offset}.")
            pos[:2] += xy_offset
            pos[2] += z_offset
            return self.position_to_world(pos)

        fixture_name = str(point["fixture"])
        pos = self.fixture_pos(fixture_name, z=float(self.cfg.rope.z))
        relation = str(point.get("relation", "center"))
        clearance = float(point.get("clearance", self.cfg.routing.side_clearance))
        z_offset = float(point.get("z_offset", 0.0))
        xy_offset = np.asarray(point.get("xy_offset", [0.0, 0.0]), dtype=float)
        if xy_offset.shape != (2,):
            raise ValueError(f"xy_offset must have shape (2,), got {xy_offset}.")

        if relation == "left":
            pos[0] -= clearance
        elif relation == "right":
            pos[0] += clearance
        elif relation == "above":
            pos[1] += clearance
        elif relation == "below":
            pos[1] -= clearance
        elif relation in ("center", "through", "endpoint"):
            pass
        else:
            raise ValueError(f"Unsupported cable routing relation: {relation!r}.")

        pos[:2] += xy_offset
        pos[2] += z_offset
        return pos

    def route_polyline(self, route_name: str) -> np.ndarray:
        routes = self.cfg.routes
        if route_name not in routes:
            available = ", ".join(sorted(routes.keys()))
            raise ValueError(f"Unknown route {route_name!r}; available: {available}.")
        points: list[np.ndarray] = []
        for point in routes[route_name]:
            # `arc_to` bends the leg from the previous point into a circular arc
            # of the given sweep, and so sets its LENGTH -- which for a rope's
            # spawn route is the whole point, because the length has to move with
            # `winding.turns`. Every other entry is one point, as before.
            if not isinstance(point, str) and "arc_to" in point:
                if not points:
                    raise ValueError(
                        f"route {route_name!r} starts with an `arc_to` point; an arc "
                        "needs a preceding point to bend away from."
                    )
                # `sweep_deg` defaults to `rope.spawn_arc.sweep_deg` (the leaf
                # the variation block derives), so the yaml needs no `${...}`
                # interpolation that a bare load of the task file cannot resolve.
                sweep_deg = point.get("sweep_deg", None)
                if sweep_deg is None:
                    sweep_deg = self.cfg.rope.spawn_arc.sweep_deg
                points.extend(
                    arc_route_points(
                        points[-1],
                        self.route_point(point["arc_to"]),
                        np.radians(float(sweep_deg)),
                        samples=point.get("samples"),
                    )
                )
            elif not isinstance(point, str) and "helix_around" in point:
                # `helix_around` spawns the rope ALREADY WOUND on a post
                # (rope_unwinding): from the previous point tangentially onto
                # the post, then `turns` times around it. The wrap radius is the
                # rope's settled radius plus a small standoff so the tube does
                # not spawn inside IPC's contact distance of the post.
                if not points:
                    raise ValueError(
                        f"route {route_name!r} starts with a `helix_around` point; "
                        "a helix needs a preceding point to approach from."
                    )
                # Turn count, sense, first-wrap height and climb default to the
                # task's `winding` block (the planner reads the same leaves), so
                # a variation axis on one of them moves the spawn too.
                winding = getattr(self.cfg, "winding", None)
                post = self.cfg.fixtures[str(point["helix_around"])]
                radius = (
                    float(post.radius)
                    + float(self.cfg.rope.radius)
                    + float(point.get("standoff", 0.002))
                )
                turns = point.get("turns", None if winding is None else winding.start_turns)
                direction = point.get("direction", "ccw" if winding is None else winding.direction)
                z_start = point.get("z_start", None if winding is None else winding.wind_z_start)
                climb = point.get("climb", None if winding is None else winding.climb_per_turn)
                points.extend(
                    helix_route_points(
                        points[-1],
                        self.fixture_pos(str(point["helix_around"]), z=0.0),
                        radius,
                        float(turns),
                        float(climb),
                        1.0 if str(direction).lower() == "ccw" else -1.0,
                        z_start=self.world_z(float(z_start)),
                    )
                )
            elif not isinstance(point, str) and "lead_in_toward" in point:
                # `lead_in_toward`: `length` metres from the previous point
                # straight toward a fixture, at the rope's board height
                # (rope_unwinding's level leg after the anchor).
                if not points:
                    raise ValueError(
                        f"route {route_name!r} starts with a `lead_in_toward` point; "
                        "it needs a preceding point to lead in from."
                    )
                points.append(
                    lead_in_route_point(
                        points[-1],
                        self.fixture_pos(str(point["lead_in_toward"]), z=0.0),
                        float(point["length"]),
                        self.world_z(float(self.cfg.rope.z)),
                    )
                )
            elif not isinstance(point, str) and "tail_arc" in point:
                # `tail_arc`: the free tail after a `helix_around`, leaving the
                # top wrap on its tangent and bending away from the post by
                # `rope.spawn_arc.sweep_deg` (a magnitude) with a chord of
                # `rope.spawn_arc.chord`; ends at the plug's spawn point.
                if not points:
                    raise ValueError(
                        f"route {route_name!r} starts with a `tail_arc` point; "
                        "it needs a helix to leave from."
                    )
                winding = self.cfg.winding
                points.extend(
                    tail_arc_route_points(
                        points[-1],
                        self.fixture_pos(str(point["tail_arc"]), z=0.0),
                        1.0 if str(winding.direction).lower() == "ccw" else -1.0,
                        float(self.cfg.rope.spawn_arc.chord),
                        np.radians(float(self.cfg.rope.spawn_arc.sweep_deg)),
                        self.world_z(float(self.cfg.rope.z)),
                    )
                )
            else:
                points.append(self.route_point(point))
        return np.stack(points, axis=0)

    def target_signature(self) -> CableRoutingSignature:
        entries = []
        for item in self.cfg.target_signature:
            entries.append((str(item.fixture), str(item.relation)))
        return CableRoutingSignature(tuple(entries))

    def rope_mesh(self, route_name: str) -> RopeMesh:
        polyline = self.route_polyline(route_name)
        connector_cfg = getattr(
            getattr(self.cfg.rope, "endpoint_handle", None), "connector", None
        )
        connector_on = connector_cfg is not None and bool(
            getattr(connector_cfg, "enabled", False)
        )
        if bool(getattr(self.cfg.rope, "centerline_spline", False)) and len(polyline) >= 3:
            # Smooth the hand-authored waypoint polyline (sharp 31-73deg corners
            # render as facets) with a centripetal Catmull-Rom through the same
            # control points, before the connector entries + tube skin. Route
            # ground truth reads the raw control points and is unaffected.
            rope_r = float(self.cfg.rope.radius)
            polyline = rope_prefab.catmull_rom_centerline(
                polyline, max_segment_length=float(self.cfg.rope.mesh.segment_length)
            )
            if connector_on:
                # Reserve each entry's footprint so with_end_entries' endpoint
                # displacement + landing does not overlap the now-dense body
                # points (self-intersection -> tetgen failure).
                #
                # Only the ends that actually get an entry below. The flat plug
                # pose takes no entry (its bore is horizontal, the rope runs
                # straight in), and reserving there just left a bare chord over
                # the last `reach` of rope -- a density step in the very stretch
                # the gripper closes on.
                reach = 2.0 * max(0.008, 2.0 * rope_r) + 2.0 * rope_r + 0.004
                ends = ("start",) if connector_pose(self.cfg.rope) == "flat" else ("start", "end")
                polyline = rope_prefab.reserve_endpoint_footprint(polyline, reach, ends=ends)
        if connector_on and len(polyline) >= 2:
            # Per-end entry arcs (cable_routing_element_design_zh.md): the S end
            # emerges from the fixed terminal's gland, the free end leaves the
            # plug seated on its spawn socket. Route ground truth reads the raw
            # route polyline and is unaffected.
            board_z = self.world_z(0.0)
            terminal_cfg = getattr(self.cfg.rope, "fixed_terminal", None)
            if terminal_cfg is not None and bool(getattr(terminal_cfg, "enabled", False)):
                tip_h, exit_h = rope_prefab.fixed_terminal_heights(terminal_cfg)
                start_entry = {"tip_z": board_z + tip_h, "exit_z": board_z + exit_h}
            else:
                start_entry = rope_prefab.connector_entry_heights(
                    connector_cfg, base_z=board_z
                )
            if connector_pose(self.cfg.rope) == "flat":
                # The plug lies on its side, so its bore is horizontal and the
                # rope runs straight in. No climb over a cap, and -- the reason
                # this pose exists -- no vertical rope run between the gripper's
                # pads: they close across the plug's axis, the rope leaves along
                # it. The rope's own end height is set by `rope.z`, and the plug
                # is placed to match in `_add_endpoint_handle`.
                end_entry = None
            else:
                port_cfg = getattr(
                    getattr(self.cfg.rope, "endpoint_handle", None), "spawn_port", None
                )
                end_base = board_z + (
                    float(getattr(port_cfg, "rim_height", 0.002))
                    if port_cfg is not None and bool(getattr(port_cfg, "enabled", False))
                    else 0.0
                )
                end_entry = rope_prefab.connector_entry_heights(
                    connector_cfg, base_z=end_base
                )
            polyline = rope_prefab.with_end_entries(
                polyline,
                rope_radius=float(self.cfg.rope.radius),
                start_entry=start_entry,
                end_entry=end_entry,
            )
        centerline = _sample_polyline(
            polyline,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        model = str(self.cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported CableRouting rope model: {model!r}.")
        if model == "fem_ipc_tube":
            # The IPC barrier must not span the rope's own skin; a mesh that is
            # finer than the contact distance makes the rope repel itself.
            rope_prefab.check_self_contact_clearance(
                radius=float(self.cfg.rope.radius),
                radial_segments=int(self.cfg.rope.mesh.radial_segments),
                ring_spacing=float(np.min(np.linalg.norm(np.diff(centerline, axis=0), axis=1))),
                contact_d_hat=float(self.cfg.rope.fem.contact_d_hat),
            )
        vertices, faces = _make_elastic_tube_mesh(
            centerline,
            radius=float(self.cfg.rope.radius),
            radial_segments=int(self.cfg.rope.mesh.radial_segments),
        )
        mesh_dir = _resolve_mesh_dir(self.cfg.rope.mesh.output_dir)
        path = mesh_dir / f"cable_routing_{_safe_asset_name(route_name)}_{model}.obj"
        return RopeMesh(
            path=path,
            centerline=centerline,
            vertices=vertices,
            faces=faces,
            endpoint_centers=(centerline[0], centerline[-1]),
        )


@dataclass
class CableRoutingScene:
    scene: Any
    manifest: EntityManifest
    layout: CableRoutingLayout
    route_mode: str
    rope_handle: RopeEndpointHandle
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None
    # Solver backend (rope_backends protocol); node access goes through it.
    rope_backend: Any | None = None
    # Compass angle the rope arrives at the free end on, when the plug lies flat.
    # It is both the plug's yaw and the yaw the gripper must grasp at (pads
    # across the plug axis). None when the plug stands upright, which is
    # rotationally symmetric about the approach and needs no such alignment.
    plug_heading: float | None = None


class CableRoutingSceneBuilder:
    """Build a four-fixture cable routing scene with one PBD rope."""

    # A task whose layout carries feasibility rows (rope_unwinding) swaps in its
    # own `CableRoutingLayout` subclass here.
    layout_cls = CableRoutingLayout

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, route_mode: str = "initial") -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.route_mode = str(route_mode)
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = self.layout_cls(
            task_cfg,
            task_origin=frames.task_origin,
        )

    def build(self, *, show_viewer: bool = False, include_robot: bool = True) -> CableRoutingScene:
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
            robot_material=self._robot_material(backend),
            table_material=backend.static_rigid_material(),
            static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material(),
        )
        scene = tabletop.scene
        manifest = tabletop.manifest
        self._add_board(scene, manifest)
        self._add_fixtures(scene, manifest)
        self._add_connector_target_marker(scene, manifest)
        self._add_oracle_waypoint_markers(scene, manifest)
        rope_entity, mesh = self._add_rope(scene, manifest)
        end_pin = self._add_endpoint_handle(scene, manifest, mesh)
        handle_cfg = getattr(self.task_cfg.rope, "endpoint_handle", None)
        connector_cfg = (
            getattr(handle_cfg, "connector", None) if handle_cfg is not None else None
        )
        connector_enabled = bool(
            connector_cfg is not None and bool(getattr(connector_cfg, "enabled", False))
        )
        start_plug = None
        board_z = self.layout.world_z(0.0)
        terminal_cfg = getattr(self.task_cfg.rope, "fixed_terminal", None)
        terminal_enabled = bool(
            terminal_cfg is not None and bool(getattr(terminal_cfg, "enabled", False))
        )
        spawn_port_cfg = (
            getattr(handle_cfg, "spawn_port", None) if handle_cfg is not None else None
        )
        spawn_port_enabled = bool(
            spawn_port_cfg is not None
            and bool(getattr(spawn_port_cfg, "enabled", False))
        )
        if connector_enabled:
            if terminal_enabled:
                # Fixed industrial terminal: the cable's non-movable end
                # permanently emerges from it (cable_routing_element_design_zh.md).
                start_plug = self._add_fixed_terminal(scene, manifest, mesh, terminal_cfg)
            else:
                start_plug = self._add_start_connector(scene, manifest, mesh, connector_cfg)
            if spawn_port_enabled:
                # Flush staging port the free-end plug starts plugged into — the
                # episode reads "unplug, route, plug into the target port".
                # Flush (rim 2mm) so the dragged rope can neither snag on it nor
                # visibly clip through it (raised housings did both).
                self._add_flush_port(
                    scene,
                    manifest,
                    base_name="port_spawn",
                    xy=(
                        float(mesh.endpoint_centers[1][0]),
                        float(mesh.endpoint_centers[1][1]),
                    ),
                    port_cfg=spawn_port_cfg,
                    ring_color=getattr(spawn_port_cfg, "color", [0.60, 0.61, 0.63]),
                )
        # End-constraint capacity is declared before finalize (= scene.build):
        # the FEM backend's coupler reads it during build; PBD just buffers.
        anchor_radius = float(self.task_cfg.rope.anchor_radius)
        attachment_mode = (
            str(getattr(handle_cfg, "attachment_mode", "none"))
            if handle_cfg is not None
            else "none"
        )
        start_token = end_token = None
        # `anchor_start` decides, and a terminal/plug at that end is only the
        # fallback. It used to be the other way round, which made the key dead
        # wherever a terminal existed -- both tasks that get here set it true and
        # neither was honouring it. Pinning while a terminal stands there is a
        # real configuration, and it is untangle_continuous' one
        # (`untangle_continuous.py` `declare_anchor` plus a separate power-strip
        # body): the body is scenery, the constraint is a pin, and the two are
        # not coupled. Following the link instead makes that end a soft,
        # orientation-carrying attachment, which is what `follow_swivel` acts on.
        if bool(self.task_cfg.rope.anchor_start):
            backend.declare_anchor(rope_entity, (mesh.endpoint_centers[0],), anchor_radius)
        elif start_plug is not None:
            start_token = backend.declare_follow(
                rope_entity, mesh.endpoint_centers[0], anchor_radius
            )
        if attachment_mode == "rigid_handle":
            end_token = backend.declare_follow(
                rope_entity, mesh.endpoint_centers[1], anchor_radius
            )
        elif bool(getattr(self.task_cfg.rope, "anchor_end", False)):
            backend.declare_anchor(rope_entity, (mesh.endpoint_centers[1],), anchor_radius)
        # rest_shape=straight: the rope's stress-free configuration is a straight
        # tube; the spawn route becomes genuine bending pre-stress (Kirchhoff-rod
        # helix fix -- a curved rest shape under end constraints is the phone-cord
        # recipe). "spawn" keeps rest = spawn mesh (PBD-parity default).
        rest_shape = str(
            getattr(getattr(self.task_cfg.rope, "fem", None), "rest_shape", None)
            or "spawn"
        )
        if rest_shape == "straight":
            backend.declare_rest_straight(rope_entity, mesh.centerline)
        elif rest_shape != "spawn":
            raise ValueError(
                f"rope.fem.rest_shape must be 'spawn' or 'straight', got {rest_shape!r}."
            )

        tabletop_builder.finalize(tabletop)
        if connector_enabled:
            # Cylindrical in-fixture anchor bands; tops must match the per-end
            # exit_z used in rope_mesh.
            anchor_axis_radius = float(self.task_cfg.rope.radius) + 0.003
            if terminal_enabled:
                _, start_exit_h = rope_prefab.fixed_terminal_heights(terminal_cfg)
                start_z_top = board_z + start_exit_h
            else:
                start_z_top = board_z + rope_prefab.connector_cap_top(connector_cfg) + 0.003
            end_base = board_z + (
                float(getattr(spawn_port_cfg, "rim_height", 0.002))
                if spawn_port_enabled
                else 0.0
            )
            end_z_top = end_base + rope_prefab.connector_cap_top(connector_cfg) + 0.003
            node_positions = backend.nodes(rope_entity)
            start_indices = tuple(
                rope_prefab.connector_anchor_indices(
                    rope_entity,
                    mesh.endpoint_centers[0],
                    axis_radius=anchor_axis_radius,
                    z_top=start_z_top,
                    positions=node_positions,
                )
            )
            if connector_pose(self.task_cfg.rope) == "flat":
                # `connector_anchor_indices` walks a VERTICAL cylinder up the
                # fitting's bore; a plug on its side has a horizontal one, so
                # the plain within-radius selection around the endpoint is both
                # correct and simpler here.
                end_indices = tuple(
                    backend.resolve_indices(
                        rope_entity, (mesh.endpoint_centers[1],), anchor_radius
                    )
                )
            else:
                end_indices = tuple(
                    rope_prefab.connector_anchor_indices(
                        rope_entity,
                        mesh.endpoint_centers[1],
                        axis_radius=anchor_axis_radius,
                        z_top=end_z_top,
                        positions=node_positions,
                    )
                )
        else:
            start_indices = tuple(
                backend.resolve_indices(
                    rope_entity, (mesh.endpoint_centers[0],), anchor_radius
                )
            )
            end_indices = tuple(
                backend.resolve_indices(
                    rope_entity, (mesh.endpoint_centers[1],), anchor_radius
                )
            )
        # Same order as the declaration above; the two must not disagree.
        if bool(self.task_cfg.rope.anchor_start):
            backend.anchor(rope_entity, indices=list(start_indices))
        elif start_plug is not None:
            start_indices = tuple(
                backend.follow_link(
                    rope_entity,
                    start_plug.base_link,
                    band=start_token,
                    indices=start_indices,
                )
            )
        if attachment_mode == "rigid_handle":
            if end_pin is None:
                raise RuntimeError(
                    "rope.endpoint_handle.attachment_mode=rigid_handle requires an endpoint handle."
                )
            end_indices = tuple(
                backend.follow_link(
                    rope_entity,
                    end_pin.base_link,
                    band=end_token,
                    indices=end_indices,
                )
            )
        elif bool(getattr(self.task_cfg.rope, "anchor_end", False)):
            backend.anchor(rope_entity, indices=list(end_indices))

        rope_handle = RopeEndpointHandle(
            name=str(self.task_cfg.rope.name),
            entity=rope_entity,
            start_center=mesh.endpoint_centers[0],
            end_center=mesh.endpoint_centers[1],
            start_indices=start_indices,
            end_indices=end_indices,
            start_pin=start_plug if start_plug is not None else manifest.get("fixture_S"),
            end_pin=end_pin,
        )
        return CableRoutingScene(
            scene=scene,
            manifest=manifest,
            layout=self.layout,
            route_mode=self.route_mode,
            rope_handle=rope_handle,
            cameras=tabletop.cameras,
            tabletop=tabletop,
            rope_backend=backend,
            plug_heading=(
                rope_axis_heading(mesh)
                if connector_enabled and connector_pose(self.task_cfg.rope) == "flat"
                else None
            ),
        )

    def _robot_material(self, backend):
        """Robot material, i.e. whether the rope can see the gripper at all.

        `physical_handle.robot_rope_contact` selects:

        - ``off`` (default) -- ``needs_coup=False``, which the IPC coupler reads
          as "skip this entity entirely" (`coupler.py:207`). The rope has no
          contact pair with the arm, so it passes straight through the fingers.
          This is what every task shipped with: the grasp is a kinematic weld
          (design doc §3.5), so finger contact carried no signal, and the PBD
          era had it tearing ropes apart -- a weld writing particle positions
          while rigid fingers pushed the same particles.
        - ``fingers`` -- only the finger links join IPC, as ABD bodies pinned
          each step to the pose Genesis' IK gives them. The rope then collides
          with the pads for real. The rest of the arm stays with the rigid
          solver, so IK keeps full control; that is the point of `coup_links`,
          which is an INCLUDE list for `two_way_soft_constraint`
          (`coupler.py:388-392`).

        Registering the WHOLE arm is the other Genesis path
        (`external_articulation`), and it is rejected here: it hands `qpos` to
        IPC and bans `set_qpos` (`rigid_entity.py:3764`), which is exactly the
        controller this repo drives the arm with.

        Known side effect of ``fingers``: the fingers stop colliding with any
        `ipc_only` static (the routing post). The rigid collider drops a pair
        once both geoms are IPC-delegated (`collider.py:405`), and this backend
        turns off `enable_rigid_rigid_contact` for the post's deliberately
        overlapping compound. The winding orbit keeps the pads clear of the post
        by geometry, but it is a visual check, not a guarantee.
        """

        if backend.name == "pbd":
            # Genesis defaults, exactly as before the FEM backend existed.
            return None
        physical = getattr(self.task_cfg, "physical_handle", None)
        mode = str(getattr(physical, "robot_rope_contact", "off") or "off")
        if mode == "off":
            return gs.materials.Rigid(needs_coup=False)
        if mode != "fingers":
            raise ValueError(
                "physical_handle.robot_rope_contact must be 'off' or 'fingers', "
                f"got {mode!r}."
            )
        finger_links = tuple(str(name) for name in (_list(physical.finger_links) or []))
        if not finger_links:
            raise ValueError(
                "physical_handle.robot_rope_contact='fingers' needs "
                "physical_handle.finger_links."
            )
        # IPC friction is per pair, combined as the geometric mean of the two
        # materials (`ipc_coupler/coupler.py:681`): the rope brings
        # `rope.fem.friction_mu`, the fingers bring this `coup_friction`. It is
        # therefore the one knob for how much the rope grips the pads, and it
        # touches nothing else -- `enable_rigid_rigid_contact=False` leaves the
        # fingers with no other IPC pair, and the rigid-solver friction that
        # actually holds the plug is set separately by
        # `configure_gripper_contact_friction`.
        return gs.materials.Rigid(
            coup_type="two_way_soft_constraint",
            coup_links=finger_links,
            coup_friction=float(getattr(physical, "robot_rope_friction", 0.1)),
        )

    def _fixture_kwargs(self, *, collision: bool) -> dict:
        """Material kwargs for fixed rigids, backend-appropriate. PBD keeps the
        Genesis default; under IPC a collision fixture must be 'ipc_only' and a
        collision-free one needs_coup=False (auto-select rejects both)."""

        material = (
            self._rope_backend.static_rigid_material()
            if collision
            else self._rope_backend.decoration_rigid_material()
        )
        return {} if material is None else {"material": material}

    def _add_board(self, scene, manifest: EntityManifest) -> None:
        if not box_entity_enabled(self.task_cfg.board):
            return
        manifest.add(
            self.task_cfg.board.name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(self.layout.position_to_world(self.task_cfg.board.pos)),
                    size=tuple(self.task_cfg.board.size),
                    fixed=True,
                ),
                surface=materials.plastic("board", self.task_cfg.board.color),
                name=self.task_cfg.board.name,
                **self._fixture_kwargs(collision=True),
            ),
        )

    def _add_fixtures(self, scene, manifest: EntityManifest) -> None:
        for name, fixture in _fixture_items(self.task_cfg.fixtures):
            if not bool(getattr(fixture, "enabled", True)):
                continue
            fixture_type = str(fixture.type)
            pos = tuple(self.layout.fixture_pos(name))
            surface = materials.plastic("fixture", fixture.color)
            entity_name = f"fixture_{name}"
            if fixture_type in ("start", "peg"):
                if fixture_type == "peg" and bool(
                    getattr(fixture, "routing_post_dress", False)
                ):
                    # Physical routing post: convex flared-base mesh is the
                    # collision body itself (iter-3 wedge fix); only the top
                    # cap stays decorative.
                    self._add_routing_post(
                        scene, manifest, name=entity_name, fixture=fixture, surface=surface
                    )
                else:
                    manifest.add(
                        entity_name,
                        scene.add_entity(
                            gs.morphs.Cylinder(
                                pos=pos,
                                radius=float(fixture.radius),
                                height=float(fixture.height),
                                fixed=True,
                                collision=bool(fixture.collision),
                            ),
                            surface=surface,
                            name=entity_name,
                            **self._fixture_kwargs(collision=bool(fixture.collision)),
                        ),
                    )
            elif fixture_type == "connector":
                if bool(getattr(fixture, "flush_port", False)):
                    # Destination port: flush rimmed recess (nothing tall enough
                    # for the rope to snag on or visibly clip through); the plug
                    # pin sinks below board level on seating. Latch capture is
                    # geometric, no collision anywhere. Dims shared with the
                    # spawn port (rope.endpoint_handle.spawn_port).
                    marker_cfg = getattr(self.task_cfg, "connector_target", None)
                    recess_height = None
                    if marker_cfg is None or bool(getattr(marker_cfg, "enabled", True)):
                        # The bullseye stack would bury the port; make the dark
                        # recess tall enough to poke ~0.6mm above its top ring
                        # (seat z chain untouched — it reads rim_height only).
                        ring_count = max(2, int(getattr(marker_cfg, "ring_count", 4) if marker_cfg is not None else 4))
                        z_gap = float(getattr(marker_cfg, "z_gap", 0.0008) if marker_cfg is not None else 0.0008)
                        z_off = float(getattr(marker_cfg, "z_offset", 0.0015) if marker_cfg is not None else 0.0015)
                        thickness = float(getattr(marker_cfg, "thickness", 0.002) if marker_cfg is not None else 0.002)
                        marker_top = z_off + (ring_count - 1) * z_gap + 0.5 * thickness
                        recess_height = marker_top + 0.0006
                    self._add_flush_port(
                        scene,
                        manifest,
                        base_name=entity_name,
                        xy=(float(pos[0]), float(pos[1])),
                        port_cfg=getattr(
                            getattr(self.task_cfg.rope, "endpoint_handle", None),
                            "spawn_port",
                            None,
                        ),
                        ring_color=fixture.color,
                        recess_height=recess_height,
                    )
                    continue
                manifest.add(
                    entity_name,
                    scene.add_entity(
                        gs.morphs.Box(
                            pos=pos,
                            size=tuple(fixture.size),
                            fixed=True,
                            collision=bool(fixture.collision),
                        ),
                        surface=surface,
                        name=entity_name,
                        **self._fixture_kwargs(collision=bool(fixture.collision)),
                    ),
                )
            else:
                raise ValueError(f"Unsupported cable fixture type: {fixture_type!r}.")

    def _add_connector_target_marker(self, scene, manifest: EntityManifest) -> None:
        """Draw a red/white concentric-square bullseye on the surface at the connector.

        Purely decorative (``collision=False``) so it never touches the rope or
        gripper; it just makes the routing endpoint stand out like a target.
        Tune or disable via ``task.connector_target`` in config.
        """

        marker_cfg = getattr(self.task_cfg, "connector_target", None)
        if marker_cfg is not None and not bool(getattr(marker_cfg, "enabled", True)):
            return

        connector_name = next(
            (name for name in self.layout.fixture_names() if self.layout.fixture_type(name) == "connector"),
            None,
        )
        if connector_name is None:
            return

        def _cfg(name: str, default):
            if marker_cfg is None:
                return default
            return getattr(marker_cfg, name, default)

        outer_size = float(_cfg("outer_size", 0.070))
        ring_count = max(2, int(_cfg("ring_count", 4)))
        thickness = float(_cfg("thickness", 0.002))
        z_gap = float(_cfg("z_gap", 0.0008))
        red = tuple(_list(_cfg("red_color", [0.85, 0.05, 0.05])))
        white = tuple(_list(_cfg("white_color", [0.97, 0.97, 0.97])))
        if outer_size <= 0.0 or thickness <= 0.0:
            return

        center = self.layout.fixture_pos(connector_name)
        base_z = self.layout.world_z(0.0) + float(_cfg("z_offset", 0.0015))
        step = outer_size / float(ring_count)
        for ring_index in range(ring_count):
            side = outer_size - ring_index * step
            if side <= 0.0:
                break
            color = red if ring_index % 2 == 0 else white
            name = f"connector_target_{connector_name}_{ring_index:02d}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=(float(center[0]), float(center[1]), base_z + ring_index * z_gap),
                        size=(side, side, thickness),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("deformable", color),
                    name=name,
                    **self._fixture_kwargs(collision=False),
                ),
            )

    def _add_oracle_waypoint_markers(self, scene, manifest: EntityManifest) -> None:
        debug_cfg = getattr(self.task_cfg, "debug", None)
        marker_cfg = getattr(debug_cfg, "oracle_waypoints", None) if debug_cfg is not None else None
        if marker_cfg is None or not bool(getattr(marker_cfg, "enabled", False)):
            return

        points = getattr(marker_cfg, "points", [])
        radius = float(getattr(marker_cfg, "radius", 0.006))
        height = float(getattr(marker_cfg, "height", 0.018))
        z_offset = float(getattr(marker_cfg, "z_offset", 0.055))
        for index, point_cfg in enumerate(points, start=1):
            point = _list(point_cfg)
            if not isinstance(point, dict) or "pos" not in point:
                continue
            pos = np.asarray(_list(point["pos"]), dtype=float)
            if pos.shape != (3,):
                continue
            pos = self.layout.position_to_world(pos)
            pos[2] += z_offset
            color = tuple(point.get("color", [1.0, 0.08, 0.08]))
            phase = str(point.get("phase", f"{index:02d}"))
            safe_phase = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in phase)[:48]
            name = f"oracle_waypoint_{index:02d}_{safe_phase}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(pos),
                        radius=radius,
                        height=height,
                        fixed=True,
                        collision=False,
                    ),
                    **self._fixture_kwargs(collision=False),
                    surface=materials.plastic("deformable", color),
                    name=name,
                ),
            )

    def _add_rope(self, scene, manifest: EntityManifest) -> tuple[Any, RopeMesh]:
        model = str(self.task_cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported CableRouting rope model: {model!r}.")

        mesh = self.layout.rope_mesh(self.route_mode)
        _write_obj(Path(mesh.path), mesh.vertices, mesh.faces)
        rope_entity = scene.add_entity(
            rope_prefab.tube_morph(mesh.path, self.task_cfg.rope),
            material=self._rope_backend.material(),
            surface=materials.plastic(
                "deformable", self.task_cfg.rope.color, vis_mode="visual"
            ),
            name=str(self.task_cfg.rope.name),
        )
        manifest.add(str(self.task_cfg.rope.name), rope_entity)
        return rope_entity, mesh

    def _add_endpoint_handle(self, scene, manifest: EntityManifest, mesh: RopeMesh):
        handle_cfg = getattr(self.task_cfg.rope, "endpoint_handle", None)
        if handle_cfg is None or not bool(getattr(handle_cfg, "enabled", False)):
            return None

        pos = np.asarray(mesh.endpoint_centers[1], dtype=float).copy()
        pos[2] += float(getattr(handle_cfg, "z_offset", 0.0))
        name = str(getattr(handle_cfg, "name", "cable_free_end_handle"))
        shape = str(getattr(handle_cfg, "shape", "cylinder"))
        fixed = bool(getattr(handle_cfg, "fixed", True))
        collision = bool(getattr(handle_cfg, "collision", False))
        connector_cfg = getattr(handle_cfg, "connector", None)
        if connector_cfg is not None and bool(getattr(connector_cfg, "enabled", False)):
            # Industrial plug free end (shared prefab, origin at the grasp-column
            # center). Mesh-only when collision=False: the demo's spawn latch /
            # assisted grasp drives it kinematically (same lifecycle as untangle).
            board_z = self.layout.world_z(0.0)
            path = rope_prefab.connector_obj_path(
                connector_cfg,
                default_output_dir=self.task_cfg.rope.mesh.output_dir,
            )
            if connector_pose(self.task_cfg.rope) == "flat":
                # Lying on its side, the widest part (the flange) rests on the
                # board, so the axis sits one flange radius up. The mesh is a
                # solid of revolution about local +z with the cap (where the
                # cable enters) at the top; -90 deg about y lays that axis into
                # the horizontal plane, and the extra yaw aims the cap back down
                # the rope so the cable runs straight in and the pin points out
                # into free space. Same arrangement as untangle_continuous.
                axis_z = board_z + float(connector_cfg.flange_radius)
                heading = rope_axis_heading(mesh)
                morph = gs.morphs.Mesh(
                    file=str(path),
                    pos=(float(pos[0]), float(pos[1]), axis_z),
                    euler=(0.0, -90.0, float(np.degrees(heading))),
                    scale=1.0,
                    decimate=False,
                    convexify=True,
                    fixed=fixed,
                    collision=collision,
                    file_meshes_are_zup=True,
                )
            else:
                spawn_port_cfg = getattr(handle_cfg, "spawn_port", None)
                seat_base = board_z + (
                    float(getattr(spawn_port_cfg, "rim_height", 0.002))
                    if spawn_port_cfg is not None
                    and bool(getattr(spawn_port_cfg, "enabled", False))
                    else 0.0
                )
                morph = gs.morphs.Mesh(
                    file=str(path),
                    pos=(
                        float(pos[0]),
                        float(pos[1]),
                        seat_base + rope_prefab.connector_grasp_height(connector_cfg),
                    ),
                    scale=1.0,
                    decimate=False,
                    convexify=True,
                    fixed=fixed,
                    collision=collision,
                    file_meshes_are_zup=True,
                )
        elif shape == "cylinder":
            morph = gs.morphs.Cylinder(
                pos=tuple(pos),
                radius=float(handle_cfg.radius),
                height=float(handle_cfg.height),
                fixed=fixed,
                collision=collision,
            )
        elif shape == "box":
            size = getattr(handle_cfg, "size", None)
            if size is None:
                size = [
                    2.0 * float(handle_cfg.radius),
                    2.0 * float(handle_cfg.radius),
                    float(handle_cfg.height),
                ]
            morph = gs.morphs.Box(
                pos=tuple(pos),
                size=tuple(float(value) for value in _list(size)),
                fixed=fixed,
                collision=collision,
            )
        else:
            raise ValueError(f"Unsupported cable endpoint_handle.shape={shape!r}.")
        handle = scene.add_entity(
            morph,
            material=gs.materials.Rigid(
                rho=float(getattr(handle_cfg, "rho", 700.0)),
                friction=float(getattr(handle_cfg, "friction", 2.0)),
                # FEM: the rope end lives INSIDE this fitting; it must stay out
                # of IPC or the barrier would eject the rope from it.
                needs_coup=(
                    False
                    if self._rope_backend.name != "pbd"
                    else not bool(getattr(handle_cfg, "exclude_pbd_collision", False))
                ),
            ),
            surface=materials.plastic("connector", handle_cfg.color),
            name=name,
        )
        manifest.add(name, handle)
        return handle

    def _add_start_connector(self, scene, manifest: EntityManifest, mesh: RopeMesh, connector_cfg):
        """Fixed source-port plug: the cable start is permanently plugged in.

        Same shared prefab mesh as the free end (SOCKETED for the whole
        episode), so both cable ends read as one connector family.
        """

        start = np.asarray(mesh.endpoint_centers[0], dtype=float)
        board_z = self.layout.world_z(0.0)
        path = rope_prefab.connector_obj_path(
            connector_cfg,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
        )
        name = "cable_start_connector"
        plug = scene.add_entity(
            gs.morphs.Mesh(
                file=str(path),
                pos=(
                    float(start[0]),
                    float(start[1]),
                    board_z + rope_prefab.connector_grasp_height(connector_cfg),
                ),
                scale=1.0,
                decimate=False,
                convexify=True,
                fixed=True,
                collision=False,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.Rigid(rho=700.0, needs_coup=False),
            surface=materials.plastic(
                "connector", self.task_cfg.rope.endpoint_handle.color
            ),
            name=name,
        )
        manifest.add(name, plug)
        return plug

    def _add_fixed_terminal(self, scene, manifest: EntityManifest, mesh: RopeMesh, terminal_cfg):
        """Fixed industrial terminal: the cable permanently emerges from its gland."""

        start = np.asarray(mesh.endpoint_centers[0], dtype=float)
        board_z = self.layout.world_z(0.0)
        path = rope_prefab.fixed_terminal_obj_path(
            terminal_cfg,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
        )
        name = "cable_fixed_terminal"
        terminal = scene.add_entity(
            gs.morphs.Mesh(
                file=str(path),
                pos=(float(start[0]), float(start[1]), board_z),
                scale=1.0,
                decimate=False,
                convexify=True,
                fixed=True,
                collision=False,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.Rigid(rho=700.0, needs_coup=False),
            surface=materials.plastic(
                "connector", getattr(terminal_cfg, "color", [0.45, 0.46, 0.48])
            ),
            name=name,
        )
        manifest.add(name, terminal)
        return terminal

    def _add_flush_port(self, scene, manifest: EntityManifest, *, base_name: str, xy, port_cfg, ring_color, recess_height: float | None = None) -> None:
        """Flush rimmed port (2mm ring + dark recess disc), fully collision-free.

        Replaces the raised socket housings: a body taller than the rope either
        snags the dragged rope (with collision) or gets clipped through
        (without). A flush port is below the rope's own radius, so neither can
        happen; the plug pin sinking below board level keeps the "plugged in"
        read together with the vertical insertion move.
        """

        board_z = self.layout.world_z(0.0)
        rim_radius = float(getattr(port_cfg, "rim_radius", 0.016))
        rim_height = float(getattr(port_cfg, "rim_height", 0.002))
        recess_radius = float(getattr(port_cfg, "recess_radius", 0.0067))
        recess_h = float(recess_height) if recess_height is not None else rim_height
        ring = scene.add_entity(
            gs.morphs.Cylinder(
                pos=(float(xy[0]), float(xy[1]), board_z + 0.5 * rim_height),
                radius=rim_radius,
                height=rim_height,
                fixed=True,
                collision=False,
            ),
            surface=materials.plastic("marker", ring_color),
            name=base_name,
            **self._fixture_kwargs(collision=False),
        )
        manifest.add(base_name, ring)
        recess = scene.add_entity(
            gs.morphs.Cylinder(
                pos=(float(xy[0]), float(xy[1]), board_z + 0.5 * recess_h + 0.0002),
                radius=recess_radius,
                height=recess_h,
                fixed=True,
                collision=False,
            ),
            surface=materials.plastic("marker", [0.05, 0.06, 0.08]),
            name=f"{base_name}_recess",
            **self._fixture_kwargs(collision=False),
        )
        manifest.add(f"{base_name}_recess", recess)

    def _add_routing_post(self, scene, manifest: EntityManifest, *, name: str, fixture, surface) -> None:
        """Physical routing post: shaft cylinder + separate convex base cone + cap.

        A single "flare+shaft" solid is not convex (its hull would fatten the
        wrap radius), so the collision body is compound: the original shaft
        cylinder keeps the wrap radius exactly, and a separate steep frustum
        (convex on its own) removes the post-by-table wedge that ejected a
        dragged rope (iter-3 diagnosis). The top cap stays collision-free.
        """

        board_z = self.layout.world_z(0.0)
        pos = self.layout.fixture_pos(name.removeprefix("fixture_"))
        shaft = scene.add_entity(
            gs.morphs.Cylinder(
                pos=(float(pos[0]), float(pos[1]), float(pos[2])),
                radius=float(fixture.radius),
                height=float(fixture.height),
                fixed=True,
                collision=bool(fixture.collision),
            ),
            surface=surface,
            name=name,
            **self._fixture_kwargs(collision=bool(fixture.collision)),
        )
        manifest.add(name, shaft)
        base_path = rope_prefab.routing_post_base_obj_path(
            fixture,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
            name=f"{name}_base",
        )
        base = scene.add_entity(
            gs.morphs.Mesh(
                file=str(base_path),
                pos=(float(pos[0]), float(pos[1]), board_z),
                scale=1.0,
                decimate=False,
                convexify=True,
                fixed=True,
                collision=bool(fixture.collision),
                file_meshes_are_zup=True,
            ),
            material=(
                gs.materials.Rigid(rho=700.0, coup_type="ipc_only")
                if self._rope_backend.name != "pbd"
                else gs.materials.Rigid(rho=700.0, needs_coup=True)
            ),
            surface=surface,
            name=f"{name}_base",
        )
        manifest.add(f"{name}_base", base)
        cap = scene.add_entity(
            gs.morphs.Cylinder(
                pos=(float(pos[0]), float(pos[1]), float(pos[2]) + 0.5 * float(fixture.height) + 0.0015),
                radius=float(fixture.radius) + 0.005,
                height=0.003,
                fixed=True,
                collision=False,
            ),
            surface=surface,
            name=f"{name}_cap",
            **self._fixture_kwargs(collision=False),
        )
        manifest.add(f"{name}_cap", cap)

