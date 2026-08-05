"""Bar Through Hole (docx 2.3): push a rigid shaft through a bulkhead aperture.

Scene: a vertical bulkhead panel standing on the table with a rectangular
aperture, a round shaft resting in a near cradle, and a far cradle whose top is
level with the aperture sill so the threaded shaft lands on two supports.

The panel's aperture is built from four separate convex boxes (posts, sill,
lintel) rather than a mesh with a hole: `gs.morphs.Mesh(convexify=True)` fills
holes in, so the repo's standing answer for a non-convex fixture is a compound
of convex parts -- see `_add_routing_post` in `../routing/cable_routing.py`.

The panel is deliberately short (top 0.150) so two things hold at once: the
default home pose's fingertips (task z 0.1608) clear it without a task-local
robot config, and lifting the shaft *over* the top stays physically available --
that bypass is the task's anti-shortcut, and it must remain reachable to be
judged a failure.

STAGING (intentional, not an oversight): this is stage 1 -- scene, verifier,
primitive, demo. There is no `generation/bar_through_hole_generator.py` and no
rollout contrast pair yet, so per `docs/develop/framework/task_taxonomy_zh.md`
Section 4.0 this task does NOT yet qualify for benchmark artifacts. Stage 2 adds
the generator and the over-the-top contrast episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._visuals import box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class BarThroughHoleLayout:
    """Panel, aperture, shaft, and cradle geometry for Bar Through Hole."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        pos = np.asarray(_list(position), dtype=float)
        if pos.shape != (3,):
            raise ValueError(f"Position must have shape (3,), got {pos}.")
        if self.coordinate_frame == "world":
            return pos
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        raise ValueError(
            f"Unsupported BarThroughHole coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        raise ValueError(
            f"Unsupported BarThroughHole coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    # ----- panel / aperture -------------------------------------------------

    @property
    def panel_x(self) -> float:
        return float(self.cfg.panel.x)

    @property
    def panel_thickness(self) -> float:
        return float(self.cfg.panel.thickness)

    def panel_plane(self) -> tuple[np.ndarray, np.ndarray]:
        """The panel's mid-plane as (point, unit normal) in world coordinates.

        The verifier's threading count is defined against this plane, so it is
        published here rather than recomputed there -- the reference surface and
        the collision geometry must not be able to drift apart.
        """

        point = self.position_to_world((self.panel_x, 0.0, 0.0))
        return point, np.array([1.0, 0.0, 0.0], dtype=float)

    def aperture_center(self) -> np.ndarray:
        return self.position_to_world((self.panel_x, 0.0, float(self.cfg.aperture.center_z)))

    def aperture_rect(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Aperture bounds as ((y_min, y_max), (z_min, z_max)) in world coordinates."""

        half_y = 0.5 * float(self.cfg.aperture.width)
        half_z = 0.5 * float(self.cfg.aperture.height)
        center = self.aperture_center()
        return (
            (float(center[1] - half_y), float(center[1] + half_y)),
            (float(center[2] - half_z), float(center[2] + half_z)),
        )

    def sill_top_z(self) -> float:
        """World z of the aperture's lower edge -- what a threaded shaft rests on."""

        return float(self.aperture_rect()[1][0])

    # ----- shaft ------------------------------------------------------------

    @property
    def bar_length(self) -> float:
        return float(self.cfg.bar.length)

    @property
    def bar_radius(self) -> float:
        return float(self.cfg.bar.radius)

    def bar_rest_center(self) -> np.ndarray:
        return self.position_to_world(self.cfg.bar.rest_pos)

    def grasp_offset(self) -> float:
        """Signed x distance from the grasp point to the shaft centre.

        Positive: the hand grips *behind* the centre, so the hand can stop short
        of the panel while the shaft's leading half is already through. Sized in
        the config from the hand's own half-depth plus the panel half-thickness.
        """

        return float(self.cfg.bar.grasp_offset)

    def grasp_xy(self) -> np.ndarray:
        """World xy the gripper descends on to pick the shaft up."""

        center = self.bar_rest_center()
        return np.array([center[0] - self.grasp_offset(), center[1]], dtype=float)

    def insert_hand_xy(self) -> np.ndarray:
        """World xy of the hand when the shaft is centred in the aperture."""

        center = self.aperture_center()
        return np.array([center[0] - self.grasp_offset(), center[1]], dtype=float)

    # The anti-shortcut rollout reuses `insert_hand_xy` unchanged and differs only
    # in carry height: identical start and end xy, different trajectory homotopy.
    # That is what docx asks a contrast pair to be, and it keeps the hand behind
    # the panel plane -- carrying the shaft to the far side would drag the forearm
    # across the panel, which is the failure cable_routing documented.

    # ----- cradles ----------------------------------------------------------

    def cradle_specs(self) -> tuple[tuple[str, Any], ...]:
        cradles = getattr(self.cfg, "cradles", None)
        if cradles is None:
            return ()
        return tuple((str(name), spec) for name, spec in cradles.items())


@dataclass
class BarThroughHoleScene:
    scene: Any
    manifest: EntityManifest
    layout: BarThroughHoleLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def bar_entity(self):
        return self.manifest.get("bar")


class BarThroughHoleSceneBuilder:
    """Build the common table plus the bulkhead panel, shaft, and cradles."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> BarThroughHoleScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = BarThroughHoleLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        self._add_panel(scene, manifest, layout)
        self._add_cradles(scene, manifest, layout)
        self._add_bar(scene, manifest, layout)
        self._add_visual_details(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        return BarThroughHoleScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    # ------------------------------------------------------------------ panel

    def _add_panel(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """Four convex boxes whose union is a wall with a rectangular aperture.

        Faces are tiled edge-to-edge, never overlapped: coincident faces on two
        boxes z-fight in the rasterizer.
        """

        panel = self.task_cfg.panel
        if not box_entity_enabled(panel):
            return

        color = _list(panel.color)
        thickness = float(panel.thickness)
        width = float(panel.width)
        top = float(panel.top_z)
        # Lay the parts out in task-frame numbers straight from the config and
        # convert only the finished centres, rather than round-tripping the
        # aperture through world coordinates and back.
        ap_y_max = 0.5 * float(self.task_cfg.aperture.width)
        ap_y_min = -ap_y_max
        ap_half_h = 0.5 * float(self.task_cfg.aperture.height)
        ap_z_min = float(self.task_cfg.aperture.center_z) - ap_half_h
        ap_z_max = float(self.task_cfg.aperture.center_z) + ap_half_h

        post_width = 0.5 * (width - (ap_y_max - ap_y_min))
        if post_width <= 0.0:
            raise ValueError(
                f"Panel width {width} is not wider than the aperture {(ap_y_max - ap_y_min)}."
            )
        if ap_z_max >= top:
            raise ValueError(
                f"Aperture top {ap_z_max} must sit below the panel top {top}."
            )
        # Inner face flush with the aperture edge -- overlapping the two would
        # silently narrow the opening.
        post_center_y = ap_y_max + 0.5 * post_width
        parts = (
            # name, task-frame centre, full size
            ("panel_post_left", (layout.panel_x, +post_center_y, 0.5 * ap_z_max), (thickness, post_width, ap_z_max)),
            ("panel_post_right", (layout.panel_x, -post_center_y, 0.5 * ap_z_max), (thickness, post_width, ap_z_max)),
            (
                "panel_sill",
                (layout.panel_x, 0.0, 0.5 * ap_z_min),
                (thickness, ap_y_max - ap_y_min, ap_z_min),
            ),
            (
                "panel_lintel",
                (layout.panel_x, 0.0, 0.5 * (ap_z_max + top)),
                (thickness, width, top - ap_z_max),
            ),
        )
        for name, center, size in parts:
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.position_to_world(center)),
                        size=tuple(float(v) for v in size),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", color),
                    name=name,
                ),
            )

    # ---------------------------------------------------------------- cradles

    def _add_cradles(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """U-shaped shaft rests: a base plus two side chocks.

        A round shaft on a flat surface is in neutral equilibrium about its own
        axis, so it drifts sideways under any numerical asymmetry. The chocks
        bound that drift. They are placed away from the grasp x so the fingers
        close on bare shaft.
        """

        for name, spec in layout.cradle_specs():
            if not bool(getattr(spec, "enabled", True)):
                continue
            color = _list(getattr(spec, "color", self.task_cfg.panel.color))
            base_size = tuple(float(v) for v in _list(spec.base_size))
            base_top = float(spec.base_top_z)
            center_x = float(spec.x)
            manifest.add(
                f"{name}_base",
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world((center_x, 0.0, base_top - 0.5 * base_size[2]))
                        ),
                        size=base_size,
                        fixed=True,
                    ),
                    surface=materials.plastic("fixture", color),
                    name=f"{name}_base",
                ),
            )
            chock = tuple(float(v) for v in _list(spec.chock_size))
            chock_gap = float(spec.chock_gap)
            for sign, tag in ((1.0, "l"), (-1.0, "r")):
                manifest.add(
                    f"{name}_chock_{tag}",
                    scene.add_entity(
                        gs.morphs.Box(
                            pos=tuple(
                                layout.position_to_world(
                                    (
                                        center_x,
                                        sign * (0.5 * chock_gap + 0.5 * chock[1]),
                                        base_top + 0.5 * chock[2],
                                    )
                                )
                            ),
                            size=chock,
                            fixed=True,
                        ),
                        surface=materials.plastic("fixture", color),
                        name=f"{name}_chock_{tag}",
                    ),
                )

    # -------------------------------------------------------------------- bar

    def _add_bar(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """The shaft: a free rigid cylinder with its axis along +x.

        `gs.morphs.Cylinder`'s local axis is z (see `_write_disk_urdf`'s
        `euler=(90,0,0)` for a y axis in stacked_plate), so a +90 degree turn
        about y points it along x.
        """

        bar = self.task_cfg.bar
        manifest.add(
            "bar",
            scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(layout.bar_rest_center()),
                    radius=float(bar.radius),
                    height=float(bar.length),
                    euler=(0.0, 90.0, 0.0),
                ),
                material=gs.materials.Rigid(rho=float(getattr(bar, "rho", 2700.0))),
                surface=materials.plastic("object", _list(bar.color)),
                name="bar",
            ),
        )

    # -------------------------------------------------------- visual dressing

    def _add_visual_details(
        self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout
    ) -> None:
        """Collision-free industrial dressing, each item independently switchable.

        Same recipe as stacked_plate's visual upgrade: decoration never touches
        the collision geometry, so turning any of it off cannot change physics.
        Only static parts are dressed -- a decorative collar on the moving shaft
        would need per-step syncing, which is not worth a cosmetic gain.
        """

        details = getattr(self.task_cfg, "visual_details", None)
        if details is None:
            return

        flange = getattr(details, "flange", None)
        if flange is not None and bool(getattr(flange, "enabled", True)):
            self._add_flange(scene, manifest, layout, flange)

        bolts = getattr(details, "bolts", None)
        if bolts is not None and bool(getattr(bolts, "enabled", True)):
            self._add_bolts(scene, manifest, layout, bolts)

    def _add_flange(self, scene, manifest, layout, flange) -> None:
        """A bolted border framing the aperture on the panel's near face."""

        band = float(flange.band)
        depth = float(flange.depth)
        color = _list(flange.color)
        face_x = layout.panel_x - 0.5 * layout.panel_thickness - 0.5 * depth
        ay1 = 0.5 * float(self.task_cfg.aperture.width)
        ay0 = -ay1
        ap_half_h = 0.5 * float(self.task_cfg.aperture.height)
        az0 = float(self.task_cfg.aperture.center_z) - ap_half_h
        az1 = float(self.task_cfg.aperture.center_z) + ap_half_h
        outer_width = (ay1 - ay0) + 2.0 * band
        parts = (
            ("flange_top", (face_x, 0.0, az1 + 0.5 * band), (depth, outer_width, band)),
            ("flange_bottom", (face_x, 0.0, az0 - 0.5 * band), (depth, outer_width, band)),
            ("flange_left", (face_x, ay1 + 0.5 * band, 0.5 * (az0 + az1)), (depth, band, az1 - az0)),
            ("flange_right", (face_x, ay0 - 0.5 * band, 0.5 * (az0 + az1)), (depth, band, az1 - az0)),
        )
        for name, center, size in parts:
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.position_to_world(center)),
                        size=tuple(float(v) for v in size),
                        fixed=True,
                        collision=False,
                    ),
                    surface=materials.plastic("frame", color),
                    name=name,
                ),
            )

    def _add_bolts(self, scene, manifest, layout, bolts) -> None:
        """Bolt heads at the panel's corners."""

        radius = float(bolts.radius)
        height = float(bolts.height)
        color = _list(bolts.color)
        inset = float(bolts.inset)
        half_width = 0.5 * float(self.task_cfg.panel.width)
        top = float(self.task_cfg.panel.top_z)
        face_x = layout.panel_x - 0.5 * layout.panel_thickness - 0.5 * height
        for y_sign, y_tag in ((1.0, "l"), (-1.0, "r")):
            for z_value, z_tag in ((top - inset, "t"), (inset, "b")):
                name = f"panel_bolt_{y_tag}{z_tag}"
                manifest.add(
                    name,
                    scene.add_entity(
                        gs.morphs.Cylinder(
                            pos=tuple(
                                layout.position_to_world(
                                    (face_x, y_sign * (half_width - inset), z_value)
                                )
                            ),
                            radius=radius,
                            height=height,
                            euler=(0.0, 90.0, 0.0),
                            fixed=True,
                            collision=False,
                        ),
                        surface=materials.plastic("frame", color),
                        name=name,
                    ),
                )
