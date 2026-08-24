"""ring_transfer (docx 2.6): a closed elastic loop is moved from post A onto post B.

Scene: the standard tabletop, two industrial routing posts (the cable_routing
prefab -- shaft, flared base, cap), and one closed elastic loop lying flat
around post A with its long axis pointing away from B. The loop is a periodic
FEM+IPC tube from `topogym/world/closed_band.py`, the capability that
`docs/develop/tasks/task_environment_buildout_zh.md` listed as blocking this
task and that `tests/closed_band_spike.py` proved on 2026-08-21.

What the robot has to do, and why the grasp is modelled the way it is: the
loop leaves A only over A's top and lands on B only over B's top (docx: "two
crossings of a post top"). A loop pulled from a single pinched point collapses
to a doubled strand and cannot be put around anything -- the strands pass B
12.5 mm from its axis against 14 mm of shaft plus tube (offline gate, first
version). So the stretch phase HOOKS the far cap over both open fingers: two
follow bands at the cap's shoulders, `grasp.spread` apart, hold the cap open
wider than B. The lift-off phase pinches the near cap where it hugs A and
carries it over A's top. `_ring_transfer_geometry.py` derives every number and
`tests/check_ring_transfer_geometry.py` gates the layout without a GPU.

Posts are a list and the initial / goal enclosures are subsets (`ring.enclosure`,
`goal.enclosure`), so the multi-post variants of docx 2.7 are config edits; only
the single-post spawn is generated so far.

Coupling under IPC: the table, both posts' shafts and bases are `ipc_only`
statics, the caps are outside IPC, the arm is outside IPC (`needs_coup=False`,
as in every migrated rope task). All four `create()` materials are passed --
leaving the table on Genesis' default makes the coupler pick
`external_articulation` for a fixed box and libuipc dies with an unattributable
cudaErrorInvalidDevice (2026-08-21).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np

from topogym.core import EntityManifest
from topogym.primitives.fem_attachment import FEMRopeAttachment
from topogym.tasks._visuals import box_entity_enabled
from topogym.tasks.routing import _ring_transfer_geometry as geo
from topogym.world import (
    StandardTabletopSceneBuilder,
    TabletopBaseScene,
    materials,
    tabletop_frames_from_config,
)
from topogym.world.rope import (
    check_self_contact_clearance,
    resolve_mesh_dir,
    routing_post_base_obj_path,
    tube_material_coords,
    tube_morph,
    write_obj,
)
from topogym.world.rope_backends import rope_backend

HOOK_BANDS = ("hook_left", "hook_right")
NEAR_BAND = "near"


@dataclass
class RingTransferLayout:
    """Task-frame layout; world conversion goes through `to_world` only."""

    task_cfg: Any
    task_origin: tuple[float, float, float]

    def __post_init__(self) -> None:
        self.posts = geo.posts_from_config(self.task_cfg.posts)
        self.ring = geo.ring_from_config(self.task_cfg.ring, self.task_cfg.rope)
        self.spawn = geo.spawn_centerline(self.ring, self.posts)
        self.anchor = self.posts[self.ring.enclosure[0]]
        goal = [str(name) for name in self.task_cfg.goal.enclosure]
        if len(goal) != 1:
            raise NotImplementedError("goal.enclosure with more than one post is the reserved variant axis.")
        self.target = self.posts[goal[0]]
        if self.target.name == self.anchor.name:
            raise ValueError("goal.enclosure equals ring.enclosure: nothing to transfer.")

    @property
    def coordinate_frame(self) -> str:
        return "task"

    def to_world(self, position) -> np.ndarray:
        return np.asarray(self.task_origin, dtype=float) + np.asarray(position, dtype=float)

    def to_task(self, position) -> np.ndarray:
        return np.asarray(position, dtype=float) - np.asarray(self.task_origin, dtype=float)

    def world_z(self, z: float) -> float:
        return float(self.task_origin[2]) + float(z)

    def post_center(self, name: str) -> np.ndarray:
        return self.posts[name].center

    def post_top_z(self, name: str) -> float:
        return self.posts[name].top_z

    def hook_points(self) -> tuple[np.ndarray, np.ndarray]:
        return geo.hook_points(self.spawn, self.ring, self.anchor, float(self.task_cfg.grasp.spread))

    def near_cap_point(self) -> np.ndarray:
        return geo.near_cap_point(self.spawn, self.ring, self.anchor)

    def far_cap_path(self) -> list[tuple[str, np.ndarray]]:
        return geo.far_cap_path(
            ring=self.ring,
            anchor=self.anchor,
            target=self.target,
            spawn_line=self.spawn,
            transfer_cfg=self.task_cfg.transfer,
        )

    def lift_z(self) -> float:
        return self.anchor.top_z + self.ring.tube_radius + float(self.task_cfg.transfer.lift_margin)

    def crossings(self) -> list[tuple[str, str]]:
        """Gateway sequence the goal implies: put on the new posts, take off the old."""

        start = set(self.ring.enclosure)
        goal = {self.target.name}
        return [(name, "on") for name in sorted(goal - start)] + [(name, "off") for name in sorted(start - goal)]

    def stretch_ratio_at(self, held_xyz) -> float:
        return geo.stretched_length(
            ring=self.ring,
            anchor=self.anchor,
            held_xyz=held_xyz,
            held_half_width=0.5 * float(self.task_cfg.grasp.spread),
        ) / self.ring.perimeter

    def summary(self) -> str:
        return (
            f"ring_transfer layout: posts {', '.join(f'{p.name}@{np.round(p.center * 1000).astype(int).tolist()}mm' for p in self.posts.values())}, "
            f"loop perimeter {self.ring.perimeter * 1000:.0f}mm reach {geo.loop_reach(self.spawn, self.ring, self.anchor) * 1000:.1f}mm "
            f"from {self.anchor.name}, crossings {self.crossings()}"
        )


@dataclass
class RingTransferScene:
    scene: Any
    manifest: EntityManifest
    layout: RingTransferLayout
    ring: Any  # the FEM entity
    bands: dict[str, FEMRopeAttachment]
    members: list[np.ndarray]  # FEM vertex indices per arc-length bin (spawn order)
    frames: Any  # closed_band.BandFrames of the spawn
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None
    rope_backend: Any | None = None

    def nodes_world(self) -> np.ndarray:
        return self.rope_backend.nodes(self.ring)

    def nodes(self) -> np.ndarray:
        """FEM vertex positions in the task frame."""

        return self.layout.to_task(self.nodes_world())


class RingTransferSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        frames = tabletop_frames_from_config(env_cfg)
        self.layout = RingTransferLayout(task_cfg, task_origin=frames.task_origin)

    def build(
        self, *, show_viewer: bool = False, include_robot: bool = True, extra_cameras: dict | None = None
    ) -> RingTransferScene:
        """``extra_cameras``: name -> {pos, lookat, fov, res} in the TASK frame, added
        before the scene is built (Genesis refuses cameras afterwards). Names must
        not shadow the env cameras."""

        rope_cfg = self.task_cfg.rope
        fem_cfg = rope_cfg.fem
        if str(fem_cfg.rest_shape) != "spawn":
            raise ValueError(
                "ring_transfer: rope.fem.rest_shape must be 'spawn'. 'straight' unrolls the tet "
                "mesh along an OPEN arc length; on a closed loop the seam's tets invert and the "
                "declaration is silently dropped (closed_band_spike, 2026-08-21)."
            )
        backend = rope_backend(rope_cfg)
        self._rope_backend = backend
        backend.pre_scene()

        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, scene_options=backend.scene_options()
        )
        tabletop = tabletop_builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            robot_material=gs.materials.Rigid(needs_coup=False),
            table_material=backend.static_rigid_material(),
            static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material(),
        )
        scene, manifest = tabletop.scene, tabletop.manifest
        layout = self.layout

        self._add_board(scene, manifest)
        for post_cfg in self.task_cfg.posts:
            self._add_post(scene, manifest, post_cfg)

        # --- the loop ------------------------------------------------------
        ring = layout.ring
        frames, vertices, faces = geo.spawn_mesh(ring, layout.spawn)
        check_self_contact_clearance(
            radius=ring.tube_radius,
            radial_segments=ring.radial_segments,
            ring_spacing=ring.segment_length,
            contact_d_hat=float(fem_cfg.contact_d_hat),
        )
        mesh_path = resolve_mesh_dir(rope_cfg.mesh.output_dir) / "ring.obj"
        write_obj(mesh_path, vertices + np.asarray(layout.task_origin, dtype=float)[None, :], faces)
        entity = scene.add_entity(
            tube_morph(mesh_path, rope_cfg),
            material=backend.material(),
            surface=materials.plastic("deformable", tuple(self.task_cfg.ring.color), vis_mode="visual"),
            name="ring",
        )
        manifest.add("ring", entity)

        # --- grasp bands, declared pre-build --------------------------------
        band_radius = float(self.task_cfg.grasp.band_radius)
        strength = float(fem_cfg.follow_strength)
        left, right = layout.hook_points()
        bands = {
            HOOK_BANDS[0]: FEMRopeAttachment(entity, layout.to_world(left), band_radius, strength=strength),
            HOOK_BANDS[1]: FEMRopeAttachment(entity, layout.to_world(right), band_radius, strength=strength),
            NEAR_BAND: FEMRopeAttachment(entity, layout.to_world(layout.near_cap_point()), band_radius, strength=strength),
        }

        cameras = dict(tabletop.cameras)
        for cam_name, cam in (extra_cameras or {}).items():
            if str(cam_name) in cameras:
                raise ValueError(f"ring_transfer: extra camera {cam_name!r} shadows an env camera.")
            cameras[str(cam_name)] = scene.add_camera(
                res=tuple(int(v) for v in cam["res"]),
                pos=tuple(layout.to_world(cam["pos"])),
                lookat=tuple(layout.to_world(cam["lookat"])),
                up=(0.0, 0.0, 1.0),
                fov=float(cam["fov"]),
                GUI=False,
            )

        self._print_coupling_audit(scene)
        tabletop_builder.finalize(tabletop)

        # --- material bins for the centerline read-back --------------------
        spawn_world = layout.spawn + np.asarray(layout.task_origin, dtype=float)[None, :]
        positions = backend.nodes(entity)
        arclength = np.mod(tube_material_coords(positions, spawn_world)[:, 0], frames.perimeter)
        bins = int(self.task_cfg.success.centerline_bins)
        index = np.clip((arclength / frames.perimeter * bins).astype(int), 0, bins - 1)
        members = [np.flatnonzero(index == i) for i in range(bins)]
        empty = sum(1 for group in members if len(group) == 0)
        if empty:
            raise RuntimeError(
                f"ring_transfer: {empty} of {bins} arc-length bins are empty; the centerline "
                "cannot be read back. Lower success.centerline_bins or refine the tet mesh."
            )
        print(
            f"ring_transfer build: {entity.n_vertices} FEM vertices, {entity.n_elements} tets, "
            f"Lk {frames.self_linking} at Tw {frames.twist_turns:+.4f}, {len(layout.spawn)} rings x "
            f"{ring.radial_segments}, bands {[f'{k}:{len(v.indices)}' for k, v in bands.items()]}; "
            f"{layout.summary()}",
            flush=True,
        )
        return RingTransferScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            ring=entity,
            bands=bands,
            members=members,
            frames=frames,
            cameras=cameras,
            tabletop=tabletop,
            rope_backend=backend,
        )

    # -- fixtures ------------------------------------------------------------

    def _static(self):
        return {"material": self._rope_backend.static_rigid_material()}

    def _decoration(self):
        return {"material": self._rope_backend.decoration_rigid_material()}

    def _add_board(self, scene, manifest: EntityManifest) -> None:
        board = self.task_cfg.board
        if not box_entity_enabled(board):
            return
        manifest.add(
            board.name,
            scene.add_entity(
                gs.morphs.Box(pos=tuple(self.layout.to_world(board.pos)), size=tuple(board.size), fixed=True),
                surface=materials.plastic("board", board.color),
                name=board.name,
                **self._static(),
            ),
        )

    def _add_post(self, scene, manifest: EntityManifest, post_cfg) -> None:
        """Routing post as in cable_routing: shaft cylinder (exact wrap radius) +
        separate convex base cone + collision-free cap. A single flare+shaft solid
        is not convex and its hull would fatten the wrap radius."""

        name = f"post_{post_cfg.name}"
        radius, height = float(post_cfg.radius), float(post_cfg.height)
        xy = (float(post_cfg.pos[0]), float(post_cfg.pos[1]))
        surface = materials.plastic("fixture", tuple(post_cfg.color))
        shaft = scene.add_entity(
            gs.morphs.Cylinder(
                pos=tuple(self.layout.to_world((xy[0], xy[1], 0.5 * height))),
                radius=radius,
                height=height,
                fixed=True,
                collision=True,
            ),
            surface=surface,
            name=name,
            **self._static(),
        )
        manifest.add(name, shaft)
        base_path = routing_post_base_obj_path(
            post_cfg, default_output_dir=self.task_cfg.rope.mesh.output_dir, name=f"{name}_base"
        )
        base = scene.add_entity(
            gs.morphs.Mesh(
                file=str(base_path),
                pos=tuple(self.layout.to_world((xy[0], xy[1], 0.0))),
                scale=1.0,
                decimate=False,
                convexify=True,
                fixed=True,
                collision=True,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.Rigid(rho=700.0, coup_type="ipc_only"),
            surface=surface,
            name=f"{name}_base",
        )
        manifest.add(f"{name}_base", base)
        cap = scene.add_entity(
            gs.morphs.Cylinder(
                pos=tuple(self.layout.to_world((xy[0], xy[1], height + 0.0015))),
                radius=radius + 0.005,
                height=0.003,
                fixed=True,
                collision=False,
            ),
            surface=surface,
            name=f"{name}_cap",
            **self._decoration(),
        )
        manifest.add(f"{name}_cap", cap)

    @staticmethod
    def _print_coupling_audit(scene) -> None:
        """Coupling type every rigid will get, by the coupler's own rule, BEFORE
        build: libuipc reports every setup problem as the same cudaErrorInvalidDevice."""

        print("ring_transfer coupling:", flush=True)
        for item in getattr(scene, "entities", []):
            material = getattr(item, "material", None)
            if material is None or not hasattr(material, "needs_coup"):
                continue
            joints = int(getattr(item, "n_joints", 0) or 0)
            base_fixed = bool(getattr(getattr(item, "base_link", None), "is_fixed", False))
            declared = getattr(material, "coup_type", None)
            if not material.needs_coup:
                chosen = "(outside IPC)"
            elif declared is not None:
                chosen = str(declared)
            elif joints > 0:
                chosen = "external_articulation" if base_fixed else "two_way_soft_constraint"
            else:
                chosen = "ipc_only"
            print(
                f"  {str(getattr(item, 'name', type(item).__name__)):22s} {type(item).__name__:12s} "
                f"joints={joints} base_fixed={base_fixed} -> {chosen}",
                flush=True,
            )


__all__ = [
    "HOOK_BANDS",
    "NEAR_BAND",
    "RingTransferLayout",
    "RingTransferScene",
    "RingTransferSceneBuilder",
]
