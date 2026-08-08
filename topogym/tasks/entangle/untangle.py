from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world.rope import (
    RopeEndpointHandle,
    RopeMesh,
    connector_anchor_indices as _connector_anchor_indices,
    connector_cap_top as _connector_cap_top,
    connector_grasp_height as _connector_grasp_height,
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


def _point_spec(point) -> tuple[list[int], float, float, np.ndarray]:
    point = _list(point)
    if isinstance(point, dict):
        hole = _list(point["hole"])
        layer = float(point.get("layer", 0.0))
        z_offset = float(point.get("z_offset", 0.0))
        xy_offset = np.asarray(point.get("xy_offset", [0.0, 0.0]), dtype=float)
        if xy_offset.shape != (2,):
            raise ValueError(f"xy_offset must have shape (2,), got {xy_offset}.")
        return hole, layer, z_offset, xy_offset
    return point, 0.0, 0.0, np.zeros(2, dtype=float)


@dataclass(frozen=True)
class UntangleLayout:
    """Hole-board, optional peg, and rope geometry for Untangle."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        result = np.asarray(_list(position), dtype=float).copy()
        if result.shape != (3,):
            raise ValueError(f"Untangle position must have shape (3,), got {result}.")
        if self.coordinate_frame == "task":
            result += np.asarray(self.task_origin, dtype=float)
        elif self.coordinate_frame != "world":
            raise ValueError(
                f"Unsupported Untangle coordinate_frame={self.coordinate_frame!r}."
            )
        return result

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        if self.coordinate_frame == "world":
            return float(z)
        raise ValueError(
            f"Unsupported Untangle coordinate_frame={self.coordinate_frame!r}."
        )

    @property
    def rows(self) -> int:
        return int(self.cfg.holes.rows)

    @property
    def cols(self) -> int:
        return int(self.cfg.holes.cols)

    def hole_center(self, row: int, col: int, *, z: float | None = None) -> np.ndarray:
        top_left = np.asarray(_list(self.cfg.holes.top_left_pos), dtype=float)
        spacing = np.asarray(_list(self.cfg.holes.spacing), dtype=float)
        pos = np.array(
            [
                top_left[0] + int(col) * spacing[0],
                top_left[1] - int(row) * spacing[1],
                top_left[2],
            ],
            dtype=float,
        )
        if z is not None:
            pos[2] = z
        return self.position_to_world(pos)

    def hole_name(self, row: int, col: int) -> str:
        return f"hole_{int(row)}_{int(col)}"

    def peg_pos(self, peg) -> np.ndarray:
        if not hasattr(self.cfg, "peg"):
            raise ValueError("Untangle peg config is disabled.")
        row, col = _list(peg.hole)
        return self.hole_center(row, col, z=float(self.cfg.peg.z))

    def rope_point(self, point) -> np.ndarray:
        hole, layer, z_offset, xy_offset = _point_spec(point)
        row, col = hole
        pos = self.hole_center(row, col, z=float(self.cfg.rope.z))
        pos[:2] += xy_offset
        pos[2] += layer * float(self.cfg.rope.layer_height) + z_offset
        return pos

    def anchor_pin_pos(self, row: int, col: int) -> np.ndarray:
        return self.hole_center(row, col, z=float(self.cfg.rope.anchor_pins.z))

    def rope_polyline(self, points) -> np.ndarray:
        return np.stack([self.rope_point(point) for point in points], axis=0)

    def rope_mesh(self, strand) -> RopeMesh:
        polyline = self.rope_polyline(strand.points)
        connector_cfg = getattr(getattr(self.cfg.rope, "anchor_pins", None), "connector", None)
        if (
            connector_cfg is not None
            and bool(getattr(connector_cfg, "enabled", False))
            and bool(self.cfg.rope.anchor_endpoints)
            and len(polyline) >= 2
        ):
            polyline = self._with_connector_entries(polyline, connector_cfg)
        centerline = _sample_polyline(
            polyline,
            max_segment_length=float(self.cfg.rope.mesh.segment_length),
        )
        model = str(self.cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported Untangle rope model: {model!r}.")
        vertices, faces = _make_elastic_tube_mesh(
            centerline,
            radius=float(self.cfg.rope.radius),
            radial_segments=int(self.cfg.rope.mesh.radial_segments),
        )
        mesh_dir = _resolve_mesh_dir(self.cfg.rope.mesh.output_dir)
        path = mesh_dir / f"{_safe_asset_name(strand.name)}_{model}.obj"
        return RopeMesh(
            path=path,
            centerline=centerline,
            vertices=vertices,
            faces=faces,
            endpoint_centers=(centerline[0], centerline[-1]),
        )

    def _with_connector_entries(self, polyline: np.ndarray, connector_cfg) -> np.ndarray:
        return rope_prefab.with_connector_entries(
            polyline,
            connector_cfg,
            board_z=self.world_z(0.0),
            rope_radius=float(self.cfg.rope.radius),
        )


@dataclass
class UntangleScene:
    scene: Any
    manifest: EntityManifest
    layout: UntangleLayout
    cameras: dict = field(default_factory=dict)
    rope_handles: dict[str, RopeEndpointHandle] = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None
    # Solver backend (rope_backends protocol); node access goes through it.
    rope_backend: Any | None = None


class UntangleSceneBuilder:
    """Build the common table plus an Untangle hole board with rope strands."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = UntangleLayout(
            task_cfg,
            task_origin=frames.task_origin,
        )

    def build(self, *, show_viewer: bool = False, include_robot: bool = True) -> UntangleScene:
        backend = _make_rope_backend(self.task_cfg.rope)
        self._rope_backend = backend
        backend.pre_scene()

        connector_cfg = getattr(self.task_cfg.rope.anchor_pins, "connector", None)
        connector_enabled = bool(
            connector_cfg is not None and bool(getattr(connector_cfg, "enabled", False))
        )
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            scene_options=backend.scene_options(),
        )
        tabletop = tabletop_builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            # PBD: rope<->robot contact stays ON (physical realism experiment; if a
            # finger pad hooks the exit drape on retreat and tears the rope again,
            # see redesign plan §8 bullet 4, the fallback is needs_coup=False).
            # FEM: needs_coup=False is mandatory -- finger<->rope contact would
            # need the external_articulation IPC path this migration deliberately
            # avoids, and the grasp is a weld anyway (design doc §3.5).
            robot_material=(
                gs.materials.Rigid(needs_coup=False) if backend.name != "pbd" else None
            ),
            # The table too: with the Genesis default material the IPC coupler's
            # auto-select saw a fixed base with a joint and registered the TABLE
            # as an external articulation, which died in libuipc's first-frame
            # contact assembly (debug run 2026-08-07). None under PBD keeps the
            # default, exactly as before.
            table_material=backend.static_rigid_material(),
            static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material(),
        )
        scene = tabletop.scene
        manifest = tabletop.manifest
        layout = self.layout
        self._add_board(scene, manifest, layout)
        self._add_holes(scene, manifest, layout)
        self._add_pegs(scene, manifest, layout)
        self._add_static_anchor_pins(scene, manifest, layout)
        endpoint_pins = self._add_endpoint_anchor_pins(scene, manifest, layout)
        rope_specs = self._add_ropes(scene, manifest, layout, endpoint_pins)

        # End-constraint capacity is declared before finalize (= scene.build):
        # the FEM backend's coupler reads it during build; PBD just buffers.
        anchor_radius = float(self.task_cfg.rope.anchor_radius)
        attachment_mode = str(
            getattr(self.task_cfg.rope.anchor_pins, "attachment_mode", "fixed_particles")
        )
        follow_tokens: dict[str, tuple[int, int]] = {}
        if bool(self.task_cfg.rope.anchor_endpoints):
            for rope_name, rope_entity, endpoint_centers, _pins in rope_specs:
                if attachment_mode == "rigid_handles":
                    follow_tokens[rope_name] = (
                        backend.declare_follow(rope_entity, endpoint_centers[0], anchor_radius),
                        backend.declare_follow(rope_entity, endpoint_centers[1], anchor_radius),
                    )
                else:
                    backend.declare_anchor(rope_entity, tuple(endpoint_centers), anchor_radius)

        tabletop_builder.finalize(tabletop)
        rope_handles: dict[str, RopeEndpointHandle] = {}
        for rope_name, rope_entity, endpoint_centers, endpoint_pins in rope_specs:
            if connector_enabled:
                # Anchor the whole in-connector vertical run (see the helper's
                # docstring); the free rope then starts at the exit arc tangent.
                # The +margin must match exit_z in _with_connector_entries.
                anchor_z_top = layout.world_z(0.0) + _connector_cap_top(connector_cfg) + 0.003
                anchor_axis_radius = float(self.task_cfg.rope.radius) + 0.003
                node_positions = backend.nodes(rope_entity)
                start_indices = tuple(
                    _connector_anchor_indices(
                        rope_entity,
                        endpoint_centers[0],
                        axis_radius=anchor_axis_radius,
                        z_top=anchor_z_top,
                        positions=node_positions,
                    )
                )
                end_indices = tuple(
                    _connector_anchor_indices(
                        rope_entity,
                        endpoint_centers[1],
                        axis_radius=anchor_axis_radius,
                        z_top=anchor_z_top,
                        positions=node_positions,
                    )
                )
            else:
                start_indices = tuple(
                    backend.resolve_indices(rope_entity, (endpoint_centers[0],), anchor_radius)
                )
                end_indices = tuple(
                    backend.resolve_indices(rope_entity, (endpoint_centers[1],), anchor_radius)
                )
            if bool(self.task_cfg.rope.anchor_endpoints):
                if attachment_mode == "rigid_handles":
                    start_pin, end_pin = endpoint_pins
                    if start_pin is None or end_pin is None:
                        raise RuntimeError(
                            "rope.anchor_pins.attachment_mode=rigid_handles requires endpoint pins."
                        )
                    tokens = follow_tokens[rope_name]
                    start_indices = tuple(
                        backend.follow_link(
                            rope_entity,
                            start_pin.base_link,
                            band=tokens[0],
                            indices=start_indices,
                        )
                    )
                    end_indices = tuple(
                        backend.follow_link(
                            rope_entity,
                            end_pin.base_link,
                            band=tokens[1],
                            indices=end_indices,
                        )
                    )
                elif attachment_mode == "fixed_particles":
                    backend.anchor(
                        rope_entity, indices=sorted(set(start_indices + end_indices))
                    )
                else:
                    raise ValueError(
                        "rope.anchor_pins.attachment_mode must be "
                        "'fixed_particles' or 'rigid_handles'."
                    )
            rope_handles[rope_name] = RopeEndpointHandle(
                name=rope_name,
                entity=rope_entity,
                start_center=endpoint_centers[0],
                end_center=endpoint_centers[1],
                start_indices=start_indices,
                end_indices=end_indices,
                start_pin=endpoint_pins[0],
                end_pin=endpoint_pins[1],
            )
        return UntangleScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            rope_handles=rope_handles,
            tabletop=tabletop,
            rope_backend=backend,
        )

    def _add_board(
        self,
        scene,
        manifest: EntityManifest,
        layout: UntangleLayout,
    ) -> None:
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
                **self._fixture_kwargs(collision=True),
            ),
        )

    def _fixture_kwargs(self, *, collision: bool) -> dict:
        """Material kwargs for the task's fixed rigids, backend-appropriate.

        PBD keeps the Genesis default (None -> no kwargs, current behavior).
        Under IPC a collision fixture must be 'ipc_only' and a collision-free
        one must be needs_coup=False -- the coupler's auto-select rejects both
        otherwise (see rope_backend_migration doc).
        """

        material = (
            self._rope_backend.static_rigid_material()
            if collision
            else self._rope_backend.decoration_rigid_material()
        )
        return {} if material is None else {"material": material}

    def _add_holes(self, scene, manifest: EntityManifest, layout: UntangleLayout) -> None:
        target = tuple(_list(self.task_cfg.holes.target))
        for row in range(layout.rows):
            for col in range(layout.cols):
                color = self.task_cfg.holes.color
                if (row, col) == target:
                    color = self.task_cfg.holes.target_color
                name = layout.hole_name(row, col)
                manifest.add(
                    name,
                    scene.add_entity(
                        gs.morphs.Cylinder(
                            pos=tuple(layout.hole_center(row, col)),
                            radius=float(self.task_cfg.holes.radius),
                            height=float(self.task_cfg.holes.height),
                            fixed=True,
                            collision=bool(getattr(self.task_cfg.holes, "collision", False)),
                        ),
                        surface=materials.plastic("marker", color),
                        name=name,
                        **self._fixture_kwargs(
                            collision=bool(getattr(self.task_cfg.holes, "collision", False))
                        ),
                    ),
                )

    def _add_pegs(self, scene, manifest: EntityManifest, layout: UntangleLayout) -> None:
        if not hasattr(self.task_cfg, "peg") or not bool(getattr(self.task_cfg.peg, "enabled", False)):
            return
        collision = bool(getattr(self.task_cfg.peg, "collision", True))
        for peg in self.task_cfg.peg.pegs:
            if bool(peg.movable) and self._rope_backend.name != "pbd":
                # A movable peg the rope pushes needs two-way rigid<->IPC
                # coupling, which this migration has not wired. Fail loudly
                # rather than simulate a peg the rope cannot touch.
                raise NotImplementedError(
                    "movable pegs are not supported on the FEM+IPC backend yet."
                )
            color = tuple(self.task_cfg.peg.colors[peg.color])
            manifest.add(
                peg.name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(layout.peg_pos(peg)),
                        radius=float(self.task_cfg.peg.radius),
                        height=float(self.task_cfg.peg.height),
                        fixed=not bool(peg.movable),
                        collision=collision,
                    ),
                    surface=materials.plastic("fixture", color),
                    name=peg.name,
                    **self._fixture_kwargs(collision=collision),
                ),
            )

    def _add_static_anchor_pins(self, scene, manifest: EntityManifest, layout: UntangleLayout) -> None:
        pin_cfg = self.task_cfg.rope.anchor_pins
        if not bool(pin_cfg.enabled):
            return

        placement = str(getattr(pin_cfg, "placement", "endpoints"))
        if placement == "endpoints":
            return
        if placement != "all_holes":
            raise ValueError("rope.anchor_pins.placement must be 'all_holes' or 'endpoints'.")

        pin_holes = [(row, col) for row in range(layout.rows) for col in range(layout.cols)]
        for row, col in pin_holes:
            name = f"anchor_pin_{row}_{col}"
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Cylinder(
                        pos=tuple(layout.anchor_pin_pos(row, col)),
                        radius=float(pin_cfg.radius),
                        height=float(pin_cfg.height),
                        fixed=bool(getattr(pin_cfg, "fixed", True)),
                        collision=bool(pin_cfg.collision),
                    ),
                    surface=materials.plastic("fixture", pin_cfg.color),
                    name=name,
                    **self._fixture_kwargs(collision=bool(pin_cfg.collision)),
                ),
            )

    def _add_ropes(
        self,
        scene,
        manifest: EntityManifest,
        layout: UntangleLayout,
        endpoint_pins: dict[str, tuple[Any | None, Any | None]],
    ) -> list[tuple[str, Any, tuple[np.ndarray, np.ndarray], tuple[Any | None, Any | None]]]:
        model = str(self.task_cfg.rope.model)
        if model not in ("pbd_elastic_tube", "fem_ipc_tube"):
            raise ValueError(f"Unsupported Untangle rope model: {model!r}.")

        rope_specs = []
        for strand in self.task_cfg.rope.strands:
            mesh = layout.rope_mesh(strand)
            _write_obj(mesh.path, mesh.vertices, mesh.faces)
            rope_entity = scene.add_entity(
                rope_prefab.tube_morph(mesh.path, self.task_cfg.rope),
                material=self._rope_backend.material(),
                surface=materials.plastic("deformable", strand.color, vis_mode="visual"),
                name=strand.name,
            )
            manifest.add(strand.name, rope_entity)
            pins = endpoint_pins.get(str(strand.name), (None, None))
            rope_specs.append((str(strand.name), rope_entity, mesh.endpoint_centers, pins))
        return rope_specs

    def _add_endpoint_anchor_pins(
        self,
        scene,
        manifest: EntityManifest,
        layout: UntangleLayout,
    ) -> dict[str, tuple[Any | None, Any | None]]:
        pin_cfg = self.task_cfg.rope.anchor_pins
        if not bool(pin_cfg.enabled) or str(getattr(pin_cfg, "placement", "endpoints")) != "endpoints":
            return {}

        connector_cfg = getattr(pin_cfg, "connector", None)
        connector_path = self._connector_obj_path(connector_cfg) if connector_cfg is not None and bool(
            getattr(connector_cfg, "enabled", False)
        ) else None

        endpoint_pins: dict[str, tuple[Any | None, Any | None]] = {}
        for strand in self.task_cfg.rope.strands:
            pins = []
            for label, point in zip(("start", "end"), (strand.points[0], strand.points[-1])):
                name = f"anchor_pin_{strand.name}_{label}"
                pin_pos = layout.rope_point(point)
                pin_pos[2] += float(getattr(pin_cfg, "z_offset", 0.0))
                # Uniform plastic gray from config (industrial plug look, user call
                # 2026-07-11). Kept for the record — previous strand-tinted ferrule:
                # surface = gs.surfaces.Plastic(
                #     color=tuple(0.7 * float(channel) for channel in strand.color),
                #     roughness=0.85,
                # )
                surface = materials.plastic("connector", pin_cfg.color)
                material = gs.materials.Rigid(
                    rho=float(getattr(pin_cfg, "rho", 700.0)),
                    friction=float(getattr(pin_cfg, "friction", 2.0)),
                    # PBD: per the exclude_pbd_collision experiment flag. FEM: the
                    # rope end lives INSIDE this fitting by design, so it must stay
                    # out of IPC or the barrier would eject the rope from it.
                    needs_coup=(
                        False
                        if self._rope_backend.name != "pbd"
                        else not bool(getattr(pin_cfg, "exclude_pbd_collision", False))
                    ),
                )
                if connector_path is not None:
                    # Industrial plug connector: the flange base sits on the board, the
                    # mesh pin drops into the hole, the grip-ring column rises for grasping.
                    # The entity origin (= mesh local origin) is the grasp-column center;
                    # physical anchoring is the code-driven socket latch / grasp attachment
                    # (see untangle_redesign_plan_zh.md Phase B).
                    seat_z = layout.world_z(0.0) + _connector_grasp_height(connector_cfg)
                    morph = gs.morphs.Mesh(
                        file=str(connector_path),
                        pos=(float(pin_pos[0]), float(pin_pos[1]), float(seat_z)),
                        scale=1.0,
                        decimate=False,
                        convexify=True,
                        fixed=bool(getattr(pin_cfg, "fixed", True)),
                        collision=bool(pin_cfg.collision),
                        file_meshes_are_zup=True,
                    )
                else:
                    morph = gs.morphs.Cylinder(
                        pos=tuple(pin_pos),
                        radius=float(pin_cfg.radius),
                        height=float(pin_cfg.height),
                        fixed=bool(getattr(pin_cfg, "fixed", True)),
                        collision=bool(pin_cfg.collision),
                    )
                pin = scene.add_entity(morph, material=material, surface=surface, name=name)
                manifest.add(name, pin)
                pins.append(pin)
            endpoint_pins[str(strand.name)] = (pins[0], pins[1])
        return endpoint_pins

    def _connector_obj_path(self, connector_cfg) -> Path:
        return rope_prefab.connector_obj_path(
            connector_cfg,
            default_output_dir=self.task_cfg.rope.mesh.output_dir,
        )
