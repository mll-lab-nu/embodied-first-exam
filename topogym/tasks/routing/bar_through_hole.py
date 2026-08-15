"""Bar Through Hole (docx 2.3): push a rigid shaft through a bulkhead aperture.

Scene: a vertical bulkhead panel standing on the table with a **hexagonal**
aperture, a hex shaft resting on two open cradles, and a far cradle whose top is
level with the aperture sill so the threaded shaft lands on two supports.

Both the shaft and the bore are regular hexagonal prisms, sized by their
across-flats dimension -- the way hex stock and hex broaches are actually
specified. The profile is oriented flat-side-down, which is why the cradles are
plain open blocks: a hex bar rests on a face and cannot roll, so the anti-roll
chocks an earlier round shaft needed are gone.

The panel's aperture is a compound of convex boxes rather than a mesh with a
hole: `gs.morphs.Mesh(convexify=True)` fills holes in, so the repo's standing
answer for a non-convex fixture is a compound of convex parts -- see
`_add_routing_post` in `./cable_routing.py`. Four boxes give a rectangular
opening at the hexagon's bounding box, and four more, each rotated onto one
slanted hex edge, cut the remaining corner triangles away.

The shaft itself IS convex, so it is a generated mesh loaded with
`convexify=True`: the convex hull of a hex prism is the prism, i.e. collision is
exact rather than approximated.

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
from topogym.tasks._fixtures import add_v_block, v_block_seat_drop
from topogym.tasks._visuals import (
    add_aperture_ring,
    add_industrial_pedestal,
    add_panel_bolts,
    box_entity_enabled,
)
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir, write_obj


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def hexagon_vertices(across_flats: float) -> np.ndarray:
    """The 6 corners of a regular hexagon in the (y, z) plane, flat side down.

    Vertices sit at 0, 60, ... 300 degrees, which puts a horizontal edge at the
    bottom and another at the top and leaves the left/right extremes as corners.
    Flat-side-down is the orientation that lets the shaft rest without rolling
    and lets it seat on the aperture's lower edge.

    ``across_flats`` is the inscribed diameter (2 * inradius) -- the dimension
    hex stock is sold by. The circumradius is ``across_flats / sqrt(3)``.
    """

    inradius = 0.5 * float(across_flats)
    circumradius = inradius * 2.0 / np.sqrt(3.0)
    angles = np.deg2rad(np.arange(6) * 60.0)
    return np.stack([circumradius * np.cos(angles), circumradius * np.sin(angles)], axis=1)


def hex_prism_mesh(across_flats: float, length: float) -> tuple[np.ndarray, np.ndarray]:
    """A regular hexagonal prism with its axis along local +X.

    Local frame: cross-section in the YZ plane (flat side down, see
    `hexagon_vertices`), extruded along X and centred on the origin. Axis-along-X
    is chosen so the entity needs no spawn rotation and the verifier can read the
    shaft direction as ``R @ (1, 0, 0)``.

    Faces are 0-indexed triangles for `topogym.world.rope.write_obj`.
    """

    half = 0.5 * float(length)
    corners = hexagon_vertices(across_flats)
    verts = [[-half, y, z] for y, z in corners] + [[half, y, z] for y, z in corners]
    faces: list[list[int]] = []
    for i in range(6):
        j = (i + 1) % 6
        # side quad, split into two triangles, wound outward
        faces.append([i, j, j + 6])
        faces.append([i, j + 6, i + 6])
    for k in range(1, 5):  # fan each cap from its first corner
        faces.append([0, k + 1, k])
        faces.append([6, 6 + k, 6 + k + 1])
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=int)


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

    @property
    def aperture_across_flats(self) -> float:
        return float(self.cfg.aperture.across_flats)

    @property
    def aperture_inradius(self) -> float:
        return 0.5 * self.aperture_across_flats

    @property
    def aperture_circumradius(self) -> float:
        return self.aperture_inradius * 2.0 / np.sqrt(3.0)

    def aperture_bbox(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The hexagon's bounding box as ((y_min, y_max), (z_min, z_max)), world.

        This is the rectangular opening the four frame boxes leave; the four
        corner boxes then trim it down to the hexagon itself.
        """

        center = self.aperture_center()
        half_y = self.aperture_circumradius
        half_z = self.aperture_inradius
        return (
            (float(center[1] - half_y), float(center[1] + half_y)),
            (float(center[2] - half_z), float(center[2] + half_z)),
        )

    def sill_top_z(self) -> float:
        """World z of the aperture's flat lower edge -- what a threaded shaft rests on."""

        return float(self.aperture_center()[2] - self.aperture_inradius)

    # ----- shaft ------------------------------------------------------------

    @property
    def bar_length(self) -> float:
        return float(self.cfg.bar.length)

    @property
    def bar_across_flats(self) -> float:
        return float(self.cfg.bar.across_flats)

    @property
    def bar_inradius(self) -> float:
        """Half the across-flats size: how far the flat bottom sits below the axis."""

        return 0.5 * self.bar_across_flats

    @property
    def bar_circumradius(self) -> float:
        return self.bar_inradius * 2.0 / np.sqrt(3.0)

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

    # Where the hand goes is not published here: it is the shaft's target minus the
    # offset the pair actually ends up with, which only the primitive can measure
    # after the lift. A precomputed hand xy assumes the shaft is exactly on its
    # nominal spot, and every millimetre it is not comes straight out of the bore's
    # clearance.

    # The anti-shortcut rollout aims at the same aperture centre and differs only
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

    def bar_profile(self) -> np.ndarray:
        """The shaft's cross-section, as the V-blocks and the bore both read it."""

        return hexagon_vertices(self.bar_across_flats)

    def cradle_apex_z(self, spec) -> float:
        """Groove bottom for a cradle, from the axis height its config asks for.

        Config states `seat_axis_z` -- where the shaft's AXIS ends up -- because
        that is the number the rest of the task is written against: the rest pose,
        the grasp height, and the far cradle's agreement with the aperture sill.
        The apex is derived from it and the shaft's profile, so changing the
        shaft's size moves the grooves instead of silently changing where it sits.
        """

        half_angle = np.deg2rad(float(getattr(spec, "half_angle_deg", 45.0)))
        return float(spec.seat_axis_z) - v_block_seat_drop(self.bar_profile(), half_angle)


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
        """Convex boxes whose union is a wall with a hexagonal aperture.

        Two groups. The frame (posts, sill, lintel) leaves a rectangular opening
        at the hexagon's bounding box; its faces are tiled edge-to-edge, never
        overlapped, because coincident faces z-fight in the rasterizer. The four
        corner pieces then each lie along one slanted hex edge and cut away the
        triangle between that edge and the rectangle's corner. Those DO overlap
        the frame -- volumetric overlap is fine, it is only coplanar faces that
        z-fight.
        """

        panel = self.task_cfg.panel
        if not box_entity_enabled(panel):
            return

        color = _list(panel.color)
        thickness = float(panel.thickness)
        width = float(panel.width)
        top = float(panel.top_z)
        # Lay the parts out in task-frame numbers straight from the config and
        # convert only the finished centres.
        across_flats = float(self.task_cfg.aperture.across_flats)
        inradius = 0.5 * across_flats
        circumradius = inradius * 2.0 / np.sqrt(3.0)
        center_z = float(self.task_cfg.aperture.center_z)
        ap_y_max, ap_y_min = circumradius, -circumradius
        ap_z_min, ap_z_max = center_z - inradius, center_z + inradius

        post_width = 0.5 * (width - (ap_y_max - ap_y_min))
        if post_width <= 0.0:
            raise ValueError(
                f"Panel width {width} is not wider than the aperture {(ap_y_max - ap_y_min)}."
            )
        if ap_z_max >= top:
            raise ValueError(f"Aperture top {ap_z_max} must sit below the panel top {top}.")
        # Inner face flush with the aperture edge -- overlapping the two would
        # silently narrow the opening.
        post_center_y = ap_y_max + 0.5 * post_width
        frame = (
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
        for name, center, size in frame:
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
        self._add_aperture_corners(scene, manifest, layout, thickness, color)

    def _add_aperture_corners(self, scene, manifest, layout, thickness, color) -> None:
        """One box per slanted hex edge, trimming the rectangle down to a hexagon."""

        across_flats = float(self.task_cfg.aperture.across_flats)
        inradius = 0.5 * across_flats
        center_z = float(self.task_cfg.aperture.center_z)
        corners = hexagon_vertices(across_flats)
        # Each corner triangle's depth measured perpendicular to its slant edge is
        # inradius/2; overlapping past that just buries the piece in the frame.
        depth = 0.5 * inradius + float(getattr(self.task_cfg.aperture, "corner_overlap", 0.004))
        edge_len = float(np.linalg.norm(corners[1] - corners[0]))
        length = edge_len + 2.0 * float(getattr(self.task_cfg.aperture, "corner_overlap", 0.004))

        index = 0
        for k in range(6):
            p, q = corners[k], corners[(k + 1) % 6]
            delta = q - p
            if abs(delta[1]) < 1e-12:
                continue  # the horizontal top/bottom edges are the lintel and sill
            mid = 0.5 * (p + q)
            outward = np.array([delta[1], -delta[0]], dtype=float)
            outward /= np.linalg.norm(outward)
            if float(np.dot(outward, mid)) < 0.0:
                outward = -outward
            seat = mid + outward * (0.5 * depth)
            name = f"panel_chamfer_{index}"
            index += 1
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(
                            layout.position_to_world(
                                (layout.panel_x, float(seat[0]), center_z + float(seat[1]))
                            )
                        ),
                        size=(thickness, length, depth),
                        # A rotation about x turns the box within the YZ plane; the
                        # box's length axis is y, so this lays it along the edge.
                        euler=(float(np.degrees(np.arctan2(delta[1], delta[0]))), 0.0, 0.0),
                        fixed=True,
                    ),
                    surface=materials.plastic("board", color),
                    name=name,
                ),
            )

    # ---------------------------------------------------------------- cradles

    def _add_cradles(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """V-blocks the shaft rests in, from the shared `_fixtures` builder.

        These were flat-top pads until 2026-08-16. A pad locates the shaft
        vertically and in nothing else, so it crept 5.2 mm sideways just settling
        under gravity and the closing pads turned it a further 3.3 degrees --
        both spent out of the bore's 7 mm of clearance before the arm had done
        anything. A groove takes the sideways freedom away, which is the whole
        reason the oracle's own alignment correction can stay small.

        Grooves sit away from the grasp x, same as the pads did, so the fingers
        still close on bare shaft.
        """

        for name, spec in layout.cradle_specs():
            if not bool(getattr(spec, "enabled", True)):
                continue
            add_v_block(
                scene,
                manifest,
                prefix=name,
                center_x=float(spec.x),
                center_y=0.0,
                apex_z=layout.cradle_apex_z(spec),
                length_x=float(spec.length_x),
                half_angle_rad=float(np.deg2rad(float(spec.half_angle_deg))),
                jaw_width=float(spec.jaw_width),
                jaw_thickness=float(spec.jaw_thickness),
                post_width=float(spec.post_width),
                base_z=0.0,
                color=_list(getattr(spec, "color", self.task_cfg.panel.color)),
                to_world=layout.position_to_world,
            )

    # -------------------------------------------------------------------- bar

    def _add_bar(self, scene, manifest: EntityManifest, layout: BarThroughHoleLayout) -> None:
        """The shaft: a free rigid hexagonal prism with its axis along +x.

        Genesis has no hex primitive, so the prism is generated and loaded as a
        mesh. `convexify=True` is exact here rather than an approximation: a
        prism is convex, so its convex hull is itself. `hex_prism_mesh` already
        builds it axis-along-X, so no spawn rotation is needed and the verifier
        reads the shaft direction as ``R @ (1, 0, 0)``.
        """

        bar = self.task_cfg.bar
        verts, faces = hex_prism_mesh(float(bar.across_flats), float(bar.length))
        mesh_dir = resolve_mesh_dir(
            getattr(bar, "mesh_output_dir", "runs/generated_meshes/bar_through_hole")
        )
        mesh_path = mesh_dir / "bar_hex_prism.obj"
        write_obj(mesh_path, verts, faces)
        manifest.add(
            "bar",
            scene.add_entity(
                gs.morphs.Mesh(
                    file=str(mesh_path.resolve()).replace("\\", "/"),
                    pos=tuple(layout.bar_rest_center()),
                    scale=1.0,
                    decimate=False,
                    convexify=True,
                    fixed=False,
                    file_meshes_are_zup=False,
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

        pedestal = getattr(details, "pedestal", None)
        if pedestal is not None and bool(getattr(pedestal, "enabled", True)):
            self._add_cradle_pedestals(scene, manifest, layout, pedestal)

    def _add_cradle_pedestals(self, scene, manifest, layout, pedestal) -> None:
        """Dress each V-block's post as a bolted pedestal.

        The post and the jaws are untouched -- same groove, same footprint, so
        the shaft rests where it did. `add_industrial_pedestal` gives the tall
        far post a foot plate, anchor bolts, knee braces and a cap collar, and
        the two short near posts just the plate and bolts, since a brace does not
        read at that height. The collar is what visually joins post to jaws.
        """

        for name, spec in layout.cradle_specs():
            if not bool(getattr(spec, "enabled", True)):
                continue
            apex_z = layout.cradle_apex_z(spec)
            add_industrial_pedestal(
                scene,
                manifest,
                prefix=name,
                spec=pedestal,
                center_x=float(spec.x),
                center_y=0.0,
                top_z=apex_z,
                block_size=(float(spec.length_x), float(spec.post_width), apex_z),
                to_world=layout.position_to_world,
            )

    def _add_flange(self, scene, manifest, layout, flange) -> None:
        """A hexagonal bolted collar around the bore, on both panel faces.

        Both faces are dressed identically: the panel is a bulkhead, and a bore
        collar that exists only on the robot's side gives the far half of the
        insertion -- the half the shaft is actually in when it seats -- a
        visibly different wall to sit in. `faces` in config can drop back to one
        side if a camera only ever sees one.
        """

        add_aperture_ring(
            scene,
            manifest,
            prefix="flange",
            corners=hexagon_vertices(float(self.task_cfg.aperture.across_flats)),
            panel_x=layout.panel_x,
            panel_thickness=layout.panel_thickness,
            center_z=float(self.task_cfg.aperture.center_z),
            band=float(flange.band),
            depth=float(flange.depth),
            color=_list(flange.color),
            to_world=layout.position_to_world,
            faces=tuple(_list(getattr(flange, "faces", ("near", "far")))),
        )

    def _add_bolts(self, scene, manifest, layout, bolts) -> None:
        """Bolt heads at the panel's four corners, on both faces."""

        inset = float(bolts.inset)
        half_width = 0.5 * float(self.task_cfg.panel.width)
        top = float(self.task_cfg.panel.top_z)
        stations = [
            (f"{y_tag}{z_tag}", (y_sign * (half_width - inset), z_value))
            for y_sign, y_tag in ((1.0, "l"), (-1.0, "r"))
            for z_value, z_tag in ((top - inset, "t"), (inset, "b"))
        ]
        add_panel_bolts(
            scene,
            manifest,
            prefix="panel_bolt",
            stations=stations,
            panel_x=layout.panel_x,
            panel_thickness=layout.panel_thickness,
            radius=float(bolts.radius),
            height=float(bolts.height),
            color=_list(bolts.color),
            to_world=layout.position_to_world,
            faces=tuple(_list(getattr(bolts, "faces", ("near", "far")))),
        )
