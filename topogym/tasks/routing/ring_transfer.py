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
carries it over A's top. The default `carry` route (2026-08-25) is a single
PINCH of the near cap: the clamp holds ~20 mm of rope straight, the rope leaves
it horizontally and only then bends down, so the hanging loop stays open wide
enough to lasso B from the side. `_ring_transfer_geometry.py` derives every number and
`tests/check_ring_transfer_geometry.py` gates the layout without a GPU.

Variation (2026-09-04): the two posts are derived from `task.pair` (midpoint,
spacing, heading) and share `task.post_shape`; `ring.on_post` / `goal.on_post`
name the start and goal posts. The loop's long axis, the pinch side and point,
and the three carry heights are Layout rules (`_ring_transfer_geometry.py`'s
constants), so the post-height axis moves them together. `derive_task_cfg` and
`validate_task_cfg` are the hooks the yaml's `variation:` block names. The
multi-post enclosures of docx 2.7 that the 2026-08-24 lists reserved were
dropped: sampled leaves must be scalars.

Coupling under IPC: the table, both posts' shafts, bases and heads are
`ipc_only` statics; the arm's hand and fingers join IPC as pinned ABD bodies
(`physical.robot_rope_contact=fingers`) so the pinch is a real contact; the
rest of the arm stays with the rigid solver. All four `create()` materials are passed --
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

HOOK_BANDS = ("hook_left", "hook_right")  # transfer route: fingers spread inside the far cap
NEAR_BAND = "near"  # carry route (pinch) and transfer's lift-off: the near cap apex


@dataclass
class RingTransferLayout:
    """Task-frame layout; world conversion goes through `to_world` only."""

    task_cfg: Any
    # The variation harness builds a Layout from the task config alone.
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Evaluate the same pair at another midpoint (the mid windows are measured
    # with the pair at the origin). None = the yaml's `pair.mid_x / mid_y`.
    pair_mid: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        cfg = self.task_cfg
        # The pair (midpoint, spacing, heading) is the truth; `posts.A/B.x,y` are
        # its derived positions (written by `derive_task_cfg`, and read here so
        # a fixed layout composes the same way). They must agree.
        if self.pair_mid is not None:
            self.posts = geo.posts_from_config(cfg.posts, cfg.post_shape, centers=geo.pair_centers(cfg.pair, self.pair_mid))
        else:
            self.posts = geo.posts_from_config(cfg.posts, cfg.post_shape)
            for name, center in geo.pair_centers(cfg.pair).items():
                if float(np.linalg.norm(center - self.posts[name].center)) > 1e-6:
                    raise ValueError(
                        f"ring_transfer: posts.{name} ({self.posts[name].center.tolist()}) does not match the pair "
                        f"(mid {float(cfg.pair.mid_x):+.4f},{float(cfg.pair.mid_y):+.4f} spacing {float(cfg.pair.spacing):.4f} "
                        f"heading {float(cfg.pair.heading_deg):+.1f} deg -> {center.tolist()})."
                    )
        on_post = str(cfg.ring.on_post)
        goal_post = str(cfg.goal.on_post)
        if goal_post != geo.other_post(on_post):
            raise ValueError(f"ring_transfer: goal.on_post {goal_post!r} must be the other post of ring.on_post {on_post!r}.")
        self.long_axis = geo.long_axis_from_heading(cfg.pair)
        self.ring = geo.ring_from_config(cfg.ring, cfg.rope, long_axis=self.long_axis, on_post=on_post)
        self.spawn = geo.spawn_centerline(self.ring, self.posts)
        self.anchor = self.posts[on_post]
        self.target = self.posts[goal_post]
        self.pinch_side = geo.pinch_side_for(self.ring, self.anchor, self.target)
        self.pinch_along = geo.pinch_along_for(self.ring, self.anchor, cfg.physical)
        heights = geo.carry_heights(
            anchor=self.anchor, target=self.target, base_height=float(cfg.post_shape.base_height), physical_cfg=cfg.physical
        )
        self.lift_low_z = heights["lift_low_z"]
        self.hang_bottom_z = heights["hang_bottom_z"]
        self.drop_z = heights["drop_z"]

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

    def pinch_point(self) -> np.ndarray:
        """The carry oracle's grasp: on a straight, clear of both posts (see geometry)."""

        return geo.pinch_point(self.spawn, self.ring, self.anchor, along=self.pinch_along, side=self.pinch_side)

    def strand_tangent(self, point) -> np.ndarray:
        """Unit xy tangent of the spawn loop nearest `point` (sets the pinch yaw)."""

        return geo.strand_tangent(self.spawn, point)

    def carry_path(self, start_xy=None) -> list[tuple[str, np.ndarray]]:
        if start_xy is None:
            start_xy = self.pinch_point()
        return geo.carry_path(
            ring=self.ring,
            anchor=self.anchor,
            target=self.target,
            start_xy=start_xy,
            carry_cfg=self.task_cfg.carry,
            lift_low_z=self.lift_low_z,
            hang_bottom_z=self.hang_bottom_z,
            drop_z=self.drop_z,
        )

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

    # The transfer / lift-only routes' remaining `task.transfer` reads, so the
    # planner asks the Layout and nothing else (variation_and_difficulty_plan §2.5).
    def transfer_carry_z(self) -> float:
        return float(self.task_cfg.transfer.carry_z)

    def off_shift(self) -> float:
        return float(self.task_cfg.transfer.shift)

    def near_side_landing(self) -> np.ndarray:
        """Where a draped cap stops short of the target (the `drape_outside` control)."""

        direction = self.target.center - self.anchor.center
        direction = direction / float(np.linalg.norm(direction))
        offset = self.target.head_radius + self.ring.tube_radius + float(self.task_cfg.transfer.landing_clearance)
        return self.target.center - offset * direction

    def instruction(self) -> str:
        """`goal.instruction` with the start and goal post names filled in."""

        return str(self.task_cfg.goal.instruction).format(start=self.anchor.name, goal=self.target.name)

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

    # ----- variation: derived windows + checks -------------------------------

    def mid_windows(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Feasible `pair.mid_y` and `pair.mid_x` windows, from THIS layout's pair
        evaluated at the origin (the carry path and the spawn loop translate with
        the pair). x is solved at the layout's own `mid_y`, so derive y first."""

        cfg = self.task_cfg
        origin = _layout_at_origin(cfg)
        path = origin.carry_path()
        hands = geo.carry_hand_positions(path, float(cfg.physical.hand_above))
        points = np.vstack([hands[:, :2], origin.spawn[:, :2]])
        y_window = geo.mid_y_window(points, workspace_y=cfg.workspace.y, y_range=cfg.pair.mid_y_range)
        x_window = geo.mid_x_window(
            points,
            hands[:, :2],
            mid_y=float(cfg.pair.mid_y),
            workspace_x=cfg.workspace.x,
            x_range=cfg.pair.mid_x_range,
            base_xy=cfg.reach.base_xy,
            max_hand_dist=float(cfg.reach.max_hand_dist),
        )
        return y_window, x_window

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, carry-solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres throughout.
        """

        return geo.ring_transfer_checks(self)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"ring_transfer layout check {name} failed: measured {measured:+.4f} against {limit:+.4f}."
                )


def _layout_at_origin(task_cfg) -> "RingTransferLayout":
    """The same pair with its midpoint at (0, 0): what the mid windows are measured on."""

    return RingTransferLayout(task_cfg, pair_mid=(0.0, 0.0))


def _write_posts(task_cfg) -> None:
    for name, center in geo.pair_centers(task_cfg.pair).items():
        task_cfg.posts[name].x = float(center[0])
        task_cfg.posts[name].y = float(center[1])


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Only
    scalar leaves are written (the instruction text is `Layout.instruction()`:
    a string with spaces cannot ride the corner sweep's Hydra overrides). Order
    matters: the goal post (the other post of the drawn `ring.on_post`), then
    the pair's midpoint y from its window (needs spacing and heading), then x
    (needs y: the reach disc is solved at the hands' own y), then both posts'
    positions. A ``ValueError`` (empty window) rejects the draw.
    """

    task_cfg.goal.on_post = geo.other_post(str(task_cfg.ring.on_post))
    _write_posts(task_cfg)
    layout = RingTransferLayout(task_cfg)
    y_window, _ = layout.mid_windows()
    task_cfg.pair.mid_y = geo.value_from_frac(y_window, float(task_cfg.pair.mid_y_frac), what="pair.mid_y")
    _write_posts(task_cfg)
    layout = RingTransferLayout(task_cfg)
    _, x_window = layout.mid_windows()
    task_cfg.pair.mid_x = geo.value_from_frac(x_window, float(task_cfg.pair.mid_x_frac), what="pair.mid_x")
    _write_posts(task_cfg)


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    RingTransferLayout(task_cfg).validate()


def _assert_literal_copies(task_cfg) -> None:
    """The yaml's literal copies of prefab / common values must still match them.

    `checks()` reads `rope.radius`, `rope.fem.contact_d_hat` and `workspace`, and the variation harness
    loads the task yaml alone, where `${prefabs...}` and `${common...}` cannot
    resolve -- so the task yaml carries literals, and the one place with both in
    hand asserts they agree.
    """

    root = task_cfg._get_root() if hasattr(task_cfg, "_get_root") else None
    prefabs = getattr(root, "prefabs", None) if root is not None else None
    common = getattr(root, "common", None) if root is not None else None
    if prefabs is not None:
        for got, want, what in (
            (float(task_cfg.rope.radius), float(prefabs.rope_pbd.radius), "rope.radius / prefabs.rope_pbd.radius"),
            (
                float(task_cfg.rope.fem.contact_d_hat),
                float(prefabs.rope_fem.contact_d_hat),
                "rope.fem.contact_d_hat / prefabs.rope_fem.contact_d_hat",
            ),
        ):
            if abs(want - got) > 1e-9:
                raise ValueError(f"ring_transfer: {what}: {got} != {want}")
    if common is not None:
        ws = common.manipulation_space.workspace
        for axis in ("x", "y", "z"):
            want = [float(v) for v in ws[axis]]
            got = [float(v) for v in task_cfg.workspace[axis]]
            if want != got:
                raise ValueError(
                    f"ring_transfer: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
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

        _assert_literal_copies(self.task_cfg)
        self.layout.validate()
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
            robot_material=self._robot_material(),
            table_material=backend.static_rigid_material(),
            static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material(),
        )
        scene, manifest = tabletop.scene, tabletop.manifest
        layout = self.layout

        self._add_board(scene, manifest)
        for post_name, post_cfg in self.task_cfg.posts.items():
            self._add_post(scene, manifest, str(post_name), post_cfg, self.task_cfg.post_shape)

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
            # The carry oracle's pinch band. (transfer's lift-off phase uses it
            # too; that route is unavailable in the default layout.)
            NEAR_BAND: FEMRopeAttachment(entity, layout.to_world(layout.pinch_point()), band_radius, strength=strength),
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

    def _robot_material(self):
        """Whether the rope can see the gripper: `physical.robot_rope_contact`.

        ``off``: the arm stays outside IPC (needs_coup=False) and the rope passes
        through the fingers -- the grasp is then the assist alone.
        ``fingers``: the links in `physical.finger_links` (hand + both fingers
        here) join IPC as ABD bodies pinned to their IK pose, so the pads really
        squeeze the rope and the palm cannot pass through it (user requirement,
        2026-08-25). Same mechanism and caveats as
        `cable_routing.CableRoutingSceneBuilder._robot_material`; the friction
        is HIGH here (a pinch has to hold), unlike rope_winding's 0.004 where the
        pads were only meant to brush past the rope.
        """

        physical = self.task_cfg.physical
        mode = str(getattr(physical, "robot_rope_contact", "off") or "off")
        if mode == "off":
            return gs.materials.Rigid(needs_coup=False)
        if mode != "fingers":
            raise ValueError(f"physical.robot_rope_contact must be 'off' or 'fingers', got {mode!r}.")
        links = tuple(str(name) for name in physical.finger_links)
        return gs.materials.Rigid(
            coup_type="two_way_soft_constraint",
            coup_links=links,
            coup_friction=float(physical.robot_rope_friction),
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

    def _add_post(self, scene, manifest: EntityManifest, post_name: str, post_cfg, shape_cfg) -> None:
        """Routing post as in cable_routing: shaft cylinder (exact wrap radius) +
        separate convex base cone, plus a retaining head that DOES collide. A single
        flare+shaft solid is not convex and its hull would fatten the wrap radius.
        `post_cfg` is the post's position and colours; `shape_cfg` (`task.post_shape`)
        the geometry both posts share."""

        name = f"post_{post_name}"
        spec = self.layout.posts[post_name]
        radius, height = spec.radius, spec.height
        xy = (float(post_cfg.x), float(post_cfg.y))
        surface = materials.plastic("fixture", tuple(post_cfg.color))
        trim = materials.plastic("fixture", tuple(getattr(post_cfg, "trim_color", post_cfg.color)))
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
            shape_cfg, default_output_dir=self.task_cfg.rope.mesh.output_dir, name=f"{name}_base"
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
            surface=trim,
            name=f"{name}_base",
        )
        manifest.add(f"{name}_base", base)
        # Retaining head: a COLLISION body (ipc_only), unlike cable_routing's
        # decorative cap. Without it the loop slides up and off the anchor as
        # soon as the far cap is lifted (_ring_transfer_geometry.py module doc).
        head_radius, head_height = spec.head_radius, spec.head_height
        head = scene.add_entity(
            gs.morphs.Cylinder(
                pos=tuple(self.layout.to_world((xy[0], xy[1], height + 0.5 * head_height))),
                radius=head_radius,
                height=head_height,
                fixed=True,
                collision=True,
            ),
            surface=trim,
            name=f"{name}_head",
            **self._static(),
        )
        manifest.add(f"{name}_head", head)

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
    "derive_task_cfg",
    "validate_task_cfg",
]
