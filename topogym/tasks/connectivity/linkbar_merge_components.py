"""Linkbar Merge Components (docx 4.4): swing the beam into the socket that belongs to the OTHER frame.

Scene: two sections of machine frame stand on the table. Component A is bolted
down -- its base spine, its pivot column and an outrigger rail are all world-fixed.
Component B is a carriage on a radial rail. A connecting beam
is hinged to A's pivot column on a single vertical joint, so its end pin travels a
horizontal circle. Two catches sit on that circle: B1 on B's inboard end, A2 on the
end of A's own outrigger. The arm turns the beam by a knob and drops the pin into
one of them, where a latch welds it.

**The two catches are the same part.** `_socket_shapes` is called once and its
result is used for both, so "identical socket" is a property of the code rather
than of two config blocks that happen to agree. They sit at the same radius, cost
the same sweep to reach, and differ only in which body they are bolted to. That
is the whole task: `component_count` goes 2 -> 1 for B1, because the new edge joins
two components, and stays 2 for A2, because both its ends were already A (the beam
is hinged to A, so beam and A are one component from the start -- an A2 latch is a
cycle edge). Randomising the two catch angles per episode is what stops "turn to
the nearer one" or "always turn the same way" from being a policy.

Sign conventions, used by the planner and the verifier as well:

- The joint angle is 0 with the beam pointing +x (away from the arm, toward the
  front camera) and grows counter-clockwise about +z. The front camera looks down
  -x with +z up, so its screen-right is +y and a positive angle swings the beam to
  screen-right.
- The two catches sit on opposite sides of the beam's initial angle. That is not
  decoration: the pin would otherwise have to sweep THROUGH one catch to reach the
  other, and a jaw at pin height is a hard stop. `LinkbarMergeLayout.validate`
  refuses a layout that breaks it, rather than letting an unsolvable instance be
  generated silently.
- A catch's mouth faces the side the pin arrives from, so its yaw is
  ``angle -/+ 90`` depending on which way the beam turns to reach it, and its slot
  curves along the pin's circle rather than running straight. One generator builds
  both, mirrored for the catch the beam reaches clockwise: a handedness, not a
  difference -- both curve toward the pivot and both open toward the beam's start.

Heights are stacked so that only the pin ever touches a catch: A's base plates and
the catch pads are 8 mm thick, the pin hangs to 12 mm, the beam's underside is at
75 mm and clears every jaw, and the knob starts above the beam so the fingers stay
clear of the mechanism. The arm never reaches inside a frame.

Everything is generated from config numbers, and the layout is derived rather than
tabulated: the catch positions, B's whole pose, A's outrigger direction and the
beam's length all follow from the pivot, the arm radius and the two catch angles,
so changing any of them keeps the scene consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks._fixtures import (
    HingeShape,
    add_hinge_mechanism,
    add_rigid_assembly,
    hinge_joint_dof,
)
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir

LINKBAR_SOCKETS = ("b1", "a2")

# Which component each catch is part of. This is the fact the policy has to read
# off the scene and the only thing that separates the two, so it is written once
# here rather than inferred from a name at each use.
SOCKET_OWNER = {"b1": "component_b", "a2": "component_a"}


def _list(value):
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    return [float(v) for v in OmegaConf.to_container(value, resolve=True)]


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def direction(angle: float) -> np.ndarray:
    """Unit vector at ``angle`` radians in the xy plane."""

    return np.array([np.cos(float(angle)), np.sin(float(angle))], dtype=float)


def tangent(angle: float) -> np.ndarray:
    """Unit vector 90 degrees counter-clockwise of `direction`, i.e. the pin's travel."""

    return np.array([-np.sin(float(angle)), np.cos(float(angle))], dtype=float)


@dataclass(frozen=True)
class LinkbarMergeLayout:
    """Every position in the scene, derived from a handful of config numbers."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ frame

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    def position_to_world(self, position) -> np.ndarray:
        point = np.asarray([float(v) for v in position], dtype=float)
        if self.coordinate_frame != "task":
            return point
        return point + np.asarray(self.task_origin, dtype=float)

    def world_z(self, z: float) -> float:
        if self.coordinate_frame != "task":
            return float(z)
        return float(z) + float(self.task_origin[2])

    # ------------------------------------------------------------------ pivot

    @property
    def pivot_xy(self) -> np.ndarray:
        return np.array([float(self.cfg.pivot.x), float(self.cfg.pivot.y)], dtype=float)

    @property
    def arm_radius(self) -> float:
        """Radius of the circle the end pin travels on -- and every catch sits on."""

        return float(self.cfg.linkbar.arm_radius)

    @property
    def init_angle(self) -> float:
        return float(np.deg2rad(float(self.cfg.linkbar.init_angle_deg)))

    # ---------------------------------------------------------------- catches

    def socket_angle(self, socket: str) -> float:
        key = {"b1": "b1_angle_deg", "a2": "a2_angle_deg"}[str(socket)]
        return float(np.deg2rad(float(getattr(self.cfg.sockets, key))))

    def socket_center_xy(self, socket: str) -> np.ndarray:
        """Where the pin sits when seated: on the arm circle, at the catch's angle."""

        return self.pivot_xy + self.arm_radius * direction(self.socket_angle(socket))

    def approach_sign(self, socket: str) -> float:
        """+1 when the beam turns counter-clockwise to reach this catch, -1 otherwise."""

        delta = self.socket_angle(socket) - self.init_angle
        return 1.0 if delta >= 0.0 else -1.0

    def socket_yaw_deg(self, socket: str) -> float:
        """Installed yaw, so the catch's mouth faces the side the pin arrives from.

        The catch's local +x points out through its mouth. A pin arriving counter-
        clockwise travels along +tangent, so it comes from -tangent and the mouth
        must face -tangent, which is the direction at ``angle - 90``. Reaching a
        catch clockwise mirrors that to ``angle + 90``.
        """

        angle_deg = float(np.rad2deg(self.socket_angle(socket)))
        return angle_deg - 90.0 * self.approach_sign(socket)

    def socket_owner(self, socket: str) -> str:
        return SOCKET_OWNER[str(socket)]

    def merging_socket(self) -> str:
        """The catch whose latch actually joins the two components."""

        return "b1"

    def target_angle(self, socket: str) -> float:
        return self.socket_angle(socket)

    def nearest_socket(self, angle: float) -> str:
        """Whichever catch is the shorter turn from ``angle``. The baseline's rule."""

        return min(LINKBAR_SOCKETS, key=lambda name: abs(self.socket_angle(name) - float(angle)))

    # ------------------------------------------------------------------- beam

    @property
    def beam_bottom_z(self) -> float:
        return float(self.cfg.linkbar.beam.bottom_z)

    @property
    def beam_top_z(self) -> float:
        return self.beam_bottom_z + float(self.cfg.linkbar.beam.height)

    @property
    def axle_bottom_z(self) -> float:
        """Where the turning shaft starts: just above A's fixed pivot column.

        The shaft cannot run down to the table, because A's column is already
        there. Two solid cylinders on the same axis, overlapping over the column's
        whole height, is a permanent contact between a world-fixed body and the one
        part that has to turn freely -- and Genesis does not know they are meant to
        be a bearing. Measured 2026-08-20 with the shaft starting at z=0: a driven
        sweep stalled up to 22 degrees short of its target, and the servo pushing
        against the jam shoved component B 9 mm out of place.

        ``axle.clearance`` keeps the shaft's underside off the column's top face as
        well. Coplanar faces would be a thrust bearing, which is a smaller version
        of the same mistake.
        """

        column = self.cfg.component_a.pivot_column
        return float(column.height) + float(self.cfg.linkbar.axle.clearance)

    @property
    def pin_radius(self) -> float:
        return float(self.cfg.linkbar.pin.radius)

    @property
    def pin_bottom_z(self) -> float:
        return float(self.cfg.linkbar.pin.bottom_z)

    def pin_center_xy(self, angle: float) -> np.ndarray:
        return self.pivot_xy + self.arm_radius * direction(float(angle))

    @property
    def knob_station(self) -> float:
        """Radius the gripper takes the beam at -- inboard of the pin, clear of it."""

        return float(self.cfg.linkbar.knob.station)

    @property
    def knob_bottom_z(self) -> float:
        return self.beam_top_z + float(self.cfg.linkbar.knob.boss_height)

    @property
    def knob_top_z(self) -> float:
        return self.knob_bottom_z + float(self.cfg.linkbar.knob.height)

    def knob_center_xy(self, angle: float) -> np.ndarray:
        return self.pivot_xy + self.knob_station * direction(float(angle))

    def knob_grasp_z(self) -> float:
        """Finger-pad height on the knob, in the task frame."""

        return self.knob_bottom_z + float(self.cfg.linkbar.knob.grasp_height)

    def knob_grasp_world(self, angle: float) -> np.ndarray:
        xy = self.knob_center_xy(angle)
        return self.position_to_world((xy[0], xy[1], self.knob_grasp_z()))

    # ---------------------------------------------------------------- capture

    @property
    def socket_pad_half_width(self) -> float:
        """Half the catch's footprint ACROSS the slot, i.e. its radial half-extent.

        B's frame starts here, so the plates butt instead of overlapping and two
        coplanar top faces never z-fight. A's outrigger uses `socket_inner_reach`
        instead, which is the larger number on that side.
        """

        sock = self.cfg.socket
        return (
            float(self.cfg.linkbar.pin.radius)
            + float(sock.pin_clearance)
            + float(sock.jaw_thickness)
        )

    @property
    def socket_arc_span(self) -> float:
        """Arc length from the seat to whichever end of the catch is further."""

        sock = self.cfg.socket
        return max(float(sock.jaw_arc_back), float(sock.jaw_arc_mouth))

    @property
    def socket_sagitta(self) -> float:
        """How far the catch's far end sits inboard of its seat.

        The slot follows the pin's circle, so the catch curves toward the pivot,
        and its ends are nearer the pivot than its middle by this much.
        """

        radius = self.arm_radius
        return float(radius * (1.0 - np.cos(self.socket_arc_span / radius)))

    @property
    def socket_inner_reach(self) -> float:
        """How far a catch reaches radially INWARD from its seat.

        More than half its width, because of the curve. A's outrigger stops here,
        so the outrigger plate and the catch pad butt instead of overlapping.
        """

        return self.socket_pad_half_width + self.socket_sagitta

    @property
    def capture_tolerance_xy(self) -> float:
        return float(self.cfg.socket.capture_tolerance_xy)

    def capture_tolerance_deg(self) -> float:
        """The same window read as a joint angle, which is what the arm controls."""

        return float(np.rad2deg(self.capture_tolerance_xy / self.arm_radius))

    @property
    def max_travel(self) -> float:
        """How far a merged carriage may run under the travel test."""

        return float(self.cfg.success.max_travel)

    @property
    def min_free_travel(self) -> float:
        """How far an UNMERGED carriage must run, for the probe to judge anything."""

        return float(self.cfg.success.min_free_travel)

    def seated(self, angle: float, socket: str) -> bool:
        """Is the pin inside this catch's capture window at joint angle ``angle``?"""

        offset = self.pin_center_xy(float(angle)) - self.socket_center_xy(socket)
        return bool(float(np.linalg.norm(offset)) <= self.capture_tolerance_xy)

    def seated_socket(self, angle: float) -> str | None:
        for socket in LINKBAR_SOCKETS:
            if self.seated(angle, socket):
                return socket
        return None

    # ------------------------------------------------------------ component B

    @property
    def b_axis_angle(self) -> float:
        """B's rail: radially outward from the pivot, through its own catch.

        Radial and not tangential, and that is a load-bearing choice rather than a
        tidy one. Latched, the carriage is held by two constraints at once: the
        beam pins its catch to a circle about A's pivot, and the rail pins it to a
        straight line. A radial rail crosses that circle head-on, so the two meet
        at a point and the carriage cannot move at all -- at the seat the beam even
        lies ALONG the rail, taking the load as a straight push or pull. A rail
        laid along the tangent would instead touch the circle, and the carriage
        could slide with the beam's angle changing only to second order: a lock
        that is soft exactly where it needs to be stiff.
        """

        return self.socket_angle("b1")

    @property
    def rail_travel(self) -> float:
        """How far the carriage can run from its seated position, outward only.

        Outward only, because inward is where the beam is: a carriage free to run
        toward the pivot could be stopped by fouling the beam, which would read as
        a merge without being one.
        """

        return float(self.cfg.component_b.rail.travel)

    def rail_direction_world(self) -> np.ndarray:
        """Unit vector the carriage travels along, in world xy, pointing outward."""

        return direction(self.b_axis_angle)

    def b_station_xy(self, station: float, offset: float = 0.0) -> np.ndarray:
        """A point ``station`` further out along B's axis, ``offset`` across it.

        Stations are measured from B's catch seat, so B's geometry is written the
        way it is built: the catch first, then the frame hanging off it.
        """

        angle = self.b_axis_angle
        return (
            self.socket_center_xy("b1")
            + float(station) * direction(angle)
            + float(offset) * tangent(angle)
        )

    # ------------------------------------------------------------ component A

    @property
    def a_outrigger_angle(self) -> float:
        """A's outrigger runs from the pivot out to A's own catch."""

        return self.socket_angle("a2")

    @property
    def spine_angle(self) -> float:
        """A's base spine points back toward the arm, opposite the beam's start."""

        return self.init_angle + np.pi

    # ------------------------------------------------------------- validation

    def validate(self) -> None:
        """Refuse a layout that cannot be solved, instead of building it anyway.

        Three conditions, all of them load-bearing for the anti-shortcut design:
        the catches must be on opposite sides of the start angle (otherwise the pin
        sweeps through one to reach the other and the instance has no solution),
        each must be far enough from the start that reaching it is a real turn, and
        neither may be so far round that the knob leaves the arm's working area.
        """

        init_deg = float(self.cfg.linkbar.init_angle_deg)
        angles = {name: float(np.rad2deg(self.socket_angle(name))) for name in LINKBAR_SOCKETS}
        low = float(self.cfg.sockets.min_sweep_deg)
        high = float(self.cfg.sockets.max_sweep_deg)

        sweeps = {name: angle - init_deg for name, angle in angles.items()}
        if sweeps["b1"] * sweeps["a2"] >= 0.0:
            raise ValueError(
                "The two catches must sit on opposite sides of the beam's initial "
                f"angle, or the pin has to sweep through one to reach the other. "
                f"init={init_deg:.1f} deg, b1={angles['b1']:.1f} deg, "
                f"a2={angles['a2']:.1f} deg."
            )
        for name, sweep in sweeps.items():
            if not low <= abs(sweep) <= high:
                raise ValueError(
                    f"Catch {name} is {abs(sweep):.1f} deg from the beam's initial "
                    f"angle, outside the allowed [{low:.1f}, {high:.1f}] deg. Below "
                    "the floor the turn is too small to be a decision; above the "
                    "ceiling the knob leaves the arm's working area."
                )


@dataclass
class LinkbarMergeScene:
    scene: Any
    manifest: EntityManifest
    layout: LinkbarMergeLayout
    joint_name: str = "linkbar_joint"
    joint_dof: int = 0
    carriage_joint_name: str = "carriage_joint"
    carriage_dof: int = 0
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    # ----------------------------------------------------------- entity access

    def linkbar_entity(self):
        return self.manifest.get("linkbar")

    def component_b_entity(self):
        return self.manifest.get("component_b")

    def socket_entity(self, socket: str):
        """The entity a catch belongs to: component B, or A's fixed outrigger catch."""

        return self.manifest.get(
            "component_b" if str(socket) == "b1" else "socket_a2"
        )

    def socket_link(self, socket: str):
        """The link a latch at this catch welds to -- and whose pose IS its seat.

        For B1 that is the CARRIAGE, not the rail it runs on. Component B's entity
        is a two-link mechanism whose base is the rail, bolted to the table; a weld
        to that base would tie the beam to the table and leave the carriage free to
        travel, which is the exact opposite of merging. For A2 the assembly has one
        link and the distinction does not arise.

        Reading the seat off this link rather than off the layout also keeps the
        latch honest about a catch that moves: the carriage runs when it is not
        held, so a capture window measured against where it was BUILT would fire on
        a seat that had already left.
        """

        entity = self.socket_entity(socket)
        if str(socket) == "b1":
            return entity.get_link(name="hinge_arm")
        return entity.base_link

    def socket_seat_xy(self, socket: str):
        """Where this catch's seat is NOW, in world xy."""

        value = self.socket_link(socket).get_pos(relative=False)
        return _as_numpy(value).reshape(-1, 3)[0][:2].astype(float)

    # ------------------------------------------------------------------ joint

    def arm_angle(self) -> float:
        value = self.linkbar_entity().get_dofs_position(dofs_idx_local=[int(self.joint_dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    def set_arm_angle(self, angle: float) -> None:
        """Write the joint directly. Episode reset and inspection only.

        Never during an episode: a beam that moved without the arm moving is a
        state change no action explains (`rigid_first_track_zh.md` section 3.1).
        """

        self.linkbar_entity().set_dofs_position(
            [float(angle)], dofs_idx_local=[int(self.joint_dof)], zero_velocity=True
        )

    def pin_xy(self) -> np.ndarray:
        """Where the beam's end pin is now, from the measured joint angle."""

        return self.layout.pin_center_xy(self.arm_angle())

    # ------------------------------------------------------------- the carriage

    def carriage_link_idx(self) -> int:
        """Global link index of the moving half of B -- what a push has to land on."""

        return self.socket_link_idx("b1")

    def carriage_travel(self) -> float:
        """How far the carriage has run from its seat, read off its own joint.

        The joint's coordinate, not a world displacement: it is exactly the
        quantity the rail bounds, so it needs no frame conversion and no threshold
        beyond "did it move".
        """

        value = self.component_b_entity().get_dofs_position(
            dofs_idx_local=[int(self.carriage_dof)]
        )
        return float(_as_numpy(value).reshape(-1)[0])

    def set_carriage_travel(self, travel: float) -> None:
        """Write the carriage's position. Episode reset and inspection only."""

        self.component_b_entity().set_dofs_position(
            [float(travel)], dofs_idx_local=[int(self.carriage_dof)], zero_velocity=True
        )

    # --------------------------------------------------------- constraint graph

    def beam_link_idx(self) -> int:
        """Global link index of the rotating link -- one end of any latch weld."""

        return int(self.linkbar_entity().get_link(name="hinge_arm").idx)

    def socket_link_idx(self, socket: str) -> int:
        return int(self.socket_link(socket).idx)

    def weld_pairs(self) -> set[tuple[int, int]]:
        """The live weld set, as normalised link-index pairs.

        The arrays come back padded with -1 up to the widest environment and in
        whatever order the solver stored, so entries are normalised and padding
        dropped. This is the raw material of the verifier's union-find.
        """

        info = self.scene.rigid_solver.get_weld_constraints(as_tensor=True, to_torch=False)
        link_a = np.asarray(info["link_a"]).reshape(-1)
        link_b = np.asarray(info["link_b"]).reshape(-1)
        pairs = set()
        for first, second in zip(link_a, link_b):
            first, second = int(first), int(second)
            if first < 0 or second < 0:
                continue
            pairs.add((min(first, second), max(first, second)))
        return pairs

    def latched_socket(self) -> str | None:
        """Which catch the beam is welded into, read from the solver, not from a flag."""

        beam = self.beam_link_idx()
        pairs = self.weld_pairs()
        for socket in LINKBAR_SOCKETS:
            other = self.socket_link_idx(socket)
            if (min(beam, other), max(beam, other)) in pairs:
                return socket
        return None


class LinkbarMergeSceneBuilder:
    """Build the common table plus component A, the hinged beam, both catches and component B."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> LinkbarMergeScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = LinkbarMergeLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        layout.validate()

        self._add_component_a(scene, manifest, layout)
        self._add_socket_a2(scene, manifest, layout)
        self._add_rail(scene, manifest, layout)
        carriage, carriage_joint = self._add_component_b(scene, manifest, layout)
        entity, joint_name = self._add_linkbar(scene, manifest, layout)
        self._add_swing_arc(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        merge_scene = LinkbarMergeScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            joint_name=joint_name,
            joint_dof=hinge_joint_dof(entity, joint_name),
            carriage_joint_name=carriage_joint,
            carriage_dof=hinge_joint_dof(carriage, carriage_joint),
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        merge_scene.set_arm_angle(layout.init_angle)
        # The carriage starts seated, which is where its catch sits on the pin's
        # circle. Everything downstream measures travel from there.
        merge_scene.set_carriage_travel(0.0)
        return merge_scene

    # ------------------------------------------------------------------ boxes

    def _box(self, scene, manifest, name, center, size, color, *, role="fixture",
             yaw_deg=0.0, collision=True):
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(float(v) for v in center),
                    size=tuple(float(v) for v in size),
                    euler=(0.0, 0.0, float(yaw_deg)),
                    fixed=True,
                    collision=bool(collision),
                ),
                surface=materials.plastic(role, _list(color)),
                name=name,
            ),
        )

    def _rail(self, scene, manifest, layout, name, angle, length, width, thickness,
              color, *, start_station=0.0):
        """A flat base rail running out from the pivot along ``angle``.

        Rails are 8 mm plate rather than 30 mm beam because the beam's end pin hangs
        to 12 mm: anything taller on the pin's circle is something the pin can hit.
        """

        centre_station = float(start_station) + 0.5 * float(length)
        xy = layout.pivot_xy + centre_station * direction(angle)
        self._box(
            scene,
            manifest,
            name,
            layout.position_to_world((xy[0], xy[1], 0.5 * float(thickness))),
            (float(length), float(width), float(thickness)),
            color,
            yaw_deg=float(np.rad2deg(angle)),
        )

    # ------------------------------------------------------------ component A

    def _add_component_a(self, scene, manifest, layout) -> None:
        """A's bolted-down frame: base spine back toward the arm, outrigger out to A2.

        Both rails start at the pivot, so the pivot column, the spine and the
        outrigger read as one welded frame -- which is exactly the claim the task
        makes about A2 belonging to A.
        """

        comp = self.task_cfg.component_a
        spine = comp.spine
        self._rail(
            scene, manifest, layout, "a_spine",
            layout.spine_angle,
            float(spine.length), float(spine.width), float(spine.thickness),
            spine.color,
        )
        # The outrigger stops where the catch pad starts, so the two plates butt
        # rather than overlap: two coplanar top faces would z-fight.
        outrigger = comp.outrigger
        self._rail(
            scene, manifest, layout, "a_outrigger",
            layout.a_outrigger_angle,
            layout.arm_radius - layout.socket_inner_reach,
            float(outrigger.width), float(outrigger.thickness),
            outrigger.color,
        )
        # The fixed column the beam turns on. Its top stops just under the beam, so
        # the rotating shaft above it is visibly the moving half of the joint --
        # and the load path from beam to table is a real one.
        column = comp.pivot_column
        manifest.add(
            "a_pivot_column",
            scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(layout.position_to_world(
                        (layout.pivot_xy[0], layout.pivot_xy[1], 0.5 * float(column.height))
                    )),
                    radius=float(column.radius),
                    height=float(column.height),
                    fixed=True,
                ),
                surface=materials.plastic("fixture", _list(column.color)),
                name="a_pivot_column",
            ),
        )
        # An upright at the spine's far end. It stands outside the pin's circle, so
        # it dresses the frame without ever being in the beam's way, and it is what
        # makes A read as a frame section rather than as a plate on the table.
        station = float(spine.length) - float(spine.post_inset)
        xy = layout.pivot_xy + station * direction(layout.spine_angle)
        manifest.add(
            "a_spine_post",
            scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(layout.position_to_world(
                        (xy[0], xy[1], 0.5 * float(spine.post_height))
                    )),
                    radius=float(spine.post_radius),
                    height=float(spine.post_height),
                    fixed=True,
                ),
                surface=materials.plastic("fixture", _list(spine.color)),
                name="a_spine_post",
            ),
        )

    # --------------------------------------------------------------- catches

    def _socket_shapes(self, layout, approach_sign: float) -> list[HingeShape]:
        """The catch, in its own frame: +x out through the mouth, +y across the slot.

        **The slot follows the pin's circle, because the pin does.** A straight slot
        cannot guide a pin swinging on an arm: over the 55 mm from the mouth to the
        seat, a 170 mm arc departs from the chord by 12.9 mm, which is three times
        the side clearance. Measured 2026-08-20 with straight jaws -- the pin jammed
        against A2's jaw 22 degrees short of the seat at 13 N, and on B, whose catch
        is free to move, it shoved the whole assembly 14.5 mm aside instead. Both
        symptoms, one cause.

        So the pad and the jaws are cut into `jaw_segments` short pieces laid along
        the arc, each yawed to its own midpoint tangent. The residual error inside a
        segment is the sagitta of that segment alone -- under a millimetre at three
        segments, against 4 mm of clearance.

        One generator, called once per catch, because docx 4.4's anti-shortcut
        argument only holds if the two really are the same part. ``approach_sign``
        mirrors it for the catch the beam reaches clockwise. That is a handedness,
        not a difference: both curve toward the pivot and both open toward the
        beam's start, so in the scene they are the same object installed two ways.

        Load path: the pin enters at +x, runs down the slot to the origin where the
        latch fires, and is stopped by the back plate if it overshoots. The jaws
        take the sideways load; nothing here has to hold the pin down, because the
        beam's hinge already refuses to move it vertically.
        """

        sock = self.task_cfg.socket
        radius = layout.arm_radius
        sign = float(approach_sign)
        pin_radius = float(self.task_cfg.linkbar.pin.radius)
        slot_half = pin_radius + float(sock.pin_clearance)
        jaw_thickness = float(sock.jaw_thickness)
        jaw_height = float(sock.jaw_height)
        pad_thickness = float(sock.pad_thickness)
        jaw_offset = slot_half + 0.5 * jaw_thickness
        pad_width = 2.0 * jaw_offset + jaw_thickness
        back = float(sock.jaw_arc_back)
        mouth = float(sock.jaw_arc_mouth)
        segments = max(1, int(sock.jaw_segments))

        def arc_point(angle: float) -> np.ndarray:
            """Where the slot centreline is, ``angle`` radians round from the seat."""

            return np.array(
                [radius * np.sin(angle), sign * radius * (np.cos(angle) - 1.0)],
                dtype=float,
            )

        def arc_normal(angle: float) -> np.ndarray:
            """Across the slot at that point, pointing away from the pivot."""

            return np.array([np.sin(angle), sign * np.cos(angle)], dtype=float)

        shapes: list[HingeShape] = []
        edges = np.linspace(-back, mouth, segments + 1) / radius
        for low, high in zip(edges[:-1], edges[1:]):
            middle = 0.5 * (low + high)
            centre = arc_point(middle)
            normal = arc_normal(middle)
            yaw = -sign * middle
            length = radius * (high - low)
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(length, pad_width, pad_thickness),
                    origin=(centre[0], centre[1], 0.5 * pad_thickness),
                    rpy=(0.0, 0.0, yaw),
                    color=_list(sock.color),
                )
            )
            for side in (1.0, -1.0):
                jaw = centre + side * jaw_offset * normal
                shapes.append(
                    HingeShape(
                        kind="box",
                        size=(length, jaw_thickness, jaw_height),
                        origin=(jaw[0], jaw[1], pad_thickness + 0.5 * jaw_height),
                        rpy=(0.0, 0.0, yaw),
                        color=_list(sock.color),
                    )
                )

        # The back plate closes the deep end of the slot, and is what bounds an
        # overshoot: the joint has no limits, so this is the only hard stop.
        stop_angle = -float(sock.back_stop_arc) / radius
        stop_centre = arc_point(stop_angle)
        shapes.append(
            HingeShape(
                kind="box",
                size=(float(sock.back_stop_thickness), pad_width, jaw_height),
                origin=(stop_centre[0], stop_centre[1], pad_thickness + 0.5 * jaw_height),
                rpy=(0.0, 0.0, -sign * stop_angle),
                color=_list(sock.accent_color),
            )
        )

        # A chamfer on each jaw's lip, so the mouth reads as a mouth. Visual only:
        # widening the entry in physics would change how much misalignment the
        # catch forgives, and that budget belongs to `capture_tolerance_xy`.
        lip_length = float(sock.lip_length)
        lip_angle = (mouth + 0.5 * lip_length) / radius
        lip_centre = arc_point(lip_angle)
        lip_normal = arc_normal(lip_angle)
        for side in (1.0, -1.0):
            lip = lip_centre + side * (jaw_offset + 0.5 * jaw_thickness) * lip_normal
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(lip_length, jaw_thickness, jaw_height),
                    origin=(lip[0], lip[1], pad_thickness + 0.5 * jaw_height),
                    rpy=(0.0, 0.0, -sign * lip_angle
                         + side * float(np.deg2rad(float(sock.lip_flare_deg)))),
                    color=_list(sock.accent_color),
                    collide=False,
                )
            )
        return shapes

    def _add_socket_a2(self, scene, manifest, layout) -> None:
        """A's own catch. Bolted down, because everything about A is."""

        centre = layout.socket_center_xy("a2")
        asset_root = resolve_mesh_dir("runs/generated_meshes/linkbar_merge_components")
        add_rigid_assembly(
            scene,
            manifest,
            name="socket_a2",
            urdf_path=asset_root / "socket_a2.urdf",
            world_pos=layout.position_to_world((centre[0], centre[1], 0.0)),
            yaw_deg=layout.socket_yaw_deg("a2"),
            shapes=self._socket_shapes(layout, layout.approach_sign("a2")),
            mass=float(self.task_cfg.socket.mass),
            color=_list(self.task_cfg.socket.color),
            fixed=True,
            contact_friction=float(self.task_cfg.socket.contact_friction),
        )

    # ------------------------------------------------------------ component B

    def _add_component_b(self, scene, manifest, layout) -> tuple[Any, str]:
        """B: the same catch, plus a frame section, riding on a rail as ONE carriage.

        A carriage on a prismatic joint rather than a free body, and that is what
        the physical recheck rests on. As a free body B had six degrees of freedom
        and nothing but friction and a pair of cleats holding it: measured
        2026-08-20, the pin brushing a jaw walked it 12.8 mm and then 14.5 mm out
        of place, far enough that the latch was testing a seat that had moved. A
        carriage has one degree of freedom and cannot be nudged out of any other.

        It also turns the judge into a bounded reading. "Merged" now means the
        carriage cannot travel, and "not merged" means it runs to its stop -- a
        fixed distance, not a displacement whose size depends on how hard the probe
        pushed. See `_travel_probe.py`.

        The frame is written in the catch's local frame, which is why the station
        arithmetic runs along local +/-y: the catch's own axes are set by which way
        it faces round the circle, and the rail runs radially outward either way.
        """

        comp = self.task_cfg.component_b
        base = comp.base
        mech = comp.mechanism
        # In the catch's frame, radially outward is +y when the beam reaches B1
        # counter-clockwise and -y when it reaches it clockwise -- the same mirror
        # `socket_yaw_deg` applies. The carriage is built, and travels, that way.
        out = layout.approach_sign("b1")
        start = layout.socket_pad_half_width + float(base.gap)
        base_length = float(base.length)
        base_centre = start + 0.5 * base_length

        shapes = list(self._socket_shapes(layout, out))
        shapes.append(
            HingeShape(
                kind="box",
                size=(float(base.width), base_length, float(base.thickness)),
                origin=(0.0, out * base_centre, 0.5 * float(base.thickness)),
                color=_list(comp.color),
            )
        )
        post = comp.post
        post_height = float(post.height)
        stations = _list(post.stations)
        for station in stations:
            for sign in (1.0, -1.0):
                shapes.append(
                    HingeShape(
                        kind="box",
                        size=(float(post.size), float(post.size), post_height),
                        origin=(sign * float(post.spacing), out * (start + station),
                                float(base.thickness) + 0.5 * post_height),
                        color=_list(comp.color),
                    )
                )
        rail = comp.top_rail
        rail_top_z = float(base.thickness) + post_height
        rail_length = abs(stations[-1] - stations[0]) + float(post.size)
        rail_centre = start + 0.5 * (stations[0] + stations[-1])
        for sign in (1.0, -1.0):
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(float(rail.thickness), rail_length, float(rail.height)),
                    origin=(sign * float(post.spacing), out * rail_centre,
                            rail_top_z + 0.5 * float(rail.height)),
                    color=_list(rail.color),
                )
            )
        # Cross brace between the two side frames, at the outboard end only: an
        # inboard one would sit over the pin's approach. Visual, like all dressing.
        shapes.append(
            HingeShape(
                kind="box",
                size=(2.0 * float(post.spacing), float(rail.thickness), float(rail.height)),
                origin=(0.0, out * (start + stations[-1]),
                        rail_top_z + 0.5 * float(rail.height)),
                color=_list(rail.color),
                collide=False,
            )
        )

        centre = layout.socket_center_xy("b1")
        asset_root = resolve_mesh_dir("runs/generated_meshes/linkbar_merge_components")
        return add_hinge_mechanism(
            scene,
            manifest,
            name="component_b",
            urdf_path=asset_root / "component_b.urdf",
            world_pos=layout.position_to_world((centre[0], centre[1], 0.0)),
            yaw_deg=layout.socket_yaw_deg("b1"),
            # Local +y is radially outward for this catch's handedness, and the
            # travel runs from the seat (0) outward only.
            axis=(0.0, out, 0.0),
            sliding=True,
            joint_limit=(0.0, layout.rail_travel),
            shapes=shapes,
            mass=float(comp.mass),
            color=_list(comp.color),
            joint_name=str(mech.joint_name),
            damping=float(mech.joint_damping),
            friction=float(mech.joint_friction),
            armature=float(mech.joint_armature),
            contact_friction=float(comp.contact_friction),
        )

    def _add_rail(self, scene, manifest, layout) -> None:
        """The rail the carriage rides, and its end stop.

        Visual only, like `stacked_plate`'s rod: the real constraint is the
        prismatic joint, and rail beams that also collided would fight it. What
        they are for is making the carriage's one degree of freedom legible --
        without them a frame that slides along an invisible line reads as a bug.
        """

        rail = self.task_cfg.component_b.rail
        if not bool(rail.enabled):
            return
        angle = layout.b_axis_angle
        yaw = float(np.rad2deg(angle))
        base = self.task_cfg.component_b.base
        inner = layout.socket_pad_half_width + float(base.gap)
        length = float(base.length) + layout.rail_travel + 2.0 * float(rail.overhang)
        centre_station = inner - float(rail.overhang) + 0.5 * length
        beam_size = _list(rail.beam_size)
        for sign, tag in ((1.0, "left"), (-1.0, "right")):
            xy = layout.b_station_xy(centre_station, sign * float(rail.spacing))
            self._box(
                scene, manifest, f"b_rail_{tag}",
                layout.position_to_world((xy[0], xy[1], 0.5 * beam_size[2])),
                (length, beam_size[1], beam_size[2]),
                rail.color,
                yaw_deg=yaw,
                collision=False,
            )
        stop_size = _list(rail.stop_size)
        stop_station = inner + float(base.length) + layout.rail_travel + 0.5 * stop_size[0]
        xy = layout.b_station_xy(stop_station)
        self._box(
            scene, manifest, "b_rail_stop",
            layout.position_to_world((xy[0], xy[1], 0.5 * stop_size[2])),
            stop_size,
            rail.stop_color,
            yaw_deg=yaw,
            collision=False,
        )

    # --------------------------------------------------------------- the beam

    def _add_linkbar(self, scene, manifest, layout) -> tuple[Any, str]:
        """The connecting beam: axle, hub, beam, end pin and knob on one rotating link.

        One link, because they are one part. The joint is CONTINUOUS and has no
        limits: with two seats on the circle a limit could only ever describe one of
        them, and "turn until it stops" would remove the aiming this task is about.
        What bounds an overshoot is the catch's back plate, which is a stop in the
        place where a stop belongs.
        """

        bar = self.task_cfg.linkbar
        beam = bar.beam
        pin = bar.pin
        knob = bar.knob
        mech = bar.mechanism

        radius = layout.arm_radius
        beam_height = float(beam.height)
        beam_mid_z = layout.beam_bottom_z + 0.5 * beam_height
        pin_height = layout.beam_bottom_z - layout.pin_bottom_z
        axle_bottom = layout.axle_bottom_z
        axle_height = layout.beam_top_z + float(bar.axle.rise) - axle_bottom
        knob_bottom = layout.knob_bottom_z

        shapes = [
            # The beam runs from the pivot out to the pin, so its box is centred at
            # half the arm radius. Everything else hangs off that line.
            HingeShape(
                kind="box",
                size=(radius, float(beam.width), beam_height),
                origin=(0.5 * radius, 0.0, beam_mid_z),
                color=_list(beam.color),
            ),
            HingeShape(
                kind="cylinder",
                size=(float(bar.axle.radius), axle_height),
                origin=(0.0, 0.0, axle_bottom + 0.5 * axle_height),
                color=_list(bar.axle.color),
            ),
            # The thickening where the beam meets the shaft. A bare bar butted onto
            # a rod reads as unfinished; every real swing arm has this boss.
            HingeShape(
                kind="cylinder",
                size=(float(bar.hub.radius), float(bar.hub.height)),
                origin=(0.0, 0.0, beam_mid_z),
                color=_list(bar.axle.color),
            ),
            HingeShape(
                kind="cylinder",
                size=(float(pin.radius), pin_height),
                origin=(radius, 0.0, layout.pin_bottom_z + 0.5 * pin_height),
                color=_list(pin.color),
            ),
            # A collar where the pin passes through the beam: it is what makes the
            # pin read as a separate hardened part rather than as a spigot.
            HingeShape(
                kind="cylinder",
                size=(float(pin.collar_radius), float(pin.collar_height)),
                origin=(radius, 0.0, layout.beam_top_z + 0.5 * float(pin.collar_height)),
                color=_list(pin.color),
                collide=False,
            ),
            HingeShape(
                kind="cylinder",
                size=(float(knob.boss_radius), float(knob.boss_height)),
                origin=(layout.knob_station, 0.0,
                        layout.beam_top_z + 0.5 * float(knob.boss_height)),
                color=_list(bar.axle.color),
            ),
            # A round grip rather than a square one: a square post cams the finger
            # pads apart as it turns, because its diagonal is wider than its face.
            HingeShape(
                kind="cylinder",
                size=(float(knob.radius), float(knob.height)),
                origin=(layout.knob_station, 0.0, knob_bottom + 0.5 * float(knob.height)),
                color=_list(knob.color),
            ),
            HingeShape(
                kind="cylinder",
                size=(float(knob.cap_radius), float(knob.cap_height)),
                origin=(layout.knob_station, 0.0,
                        layout.knob_top_z + 0.5 * float(knob.cap_height)),
                color=_list(knob.cap_color),
                collide=False,
            ),
        ]

        asset_root = resolve_mesh_dir("runs/generated_meshes/linkbar_merge_components")
        return add_hinge_mechanism(
            scene,
            manifest,
            name="linkbar",
            urdf_path=asset_root / "linkbar.urdf",
            world_pos=layout.position_to_world((layout.pivot_xy[0], layout.pivot_xy[1], 0.0)),
            axis=(0.0, 0.0, 1.0),
            shapes=shapes,
            mass=float(mech.mass),
            color=_list(beam.color),
            joint_name=str(mech.joint_name),
            joint_limit=None,
            damping=float(mech.joint_damping),
            friction=float(mech.joint_friction),
            armature=float(mech.joint_armature),
            contact_friction=float(mech.contact_friction),
        )

    # ----------------------------------------------------------- swing arc

    def _add_swing_arc(self, scene, manifest, layout) -> None:
        """Dashes on the table under the pin's circle, and a mark at each seat.

        The dashed circle in docx 4.4's figure, drawn for the same reason: it is
        what shows that both catches are the same turn away. Visual only.
        """

        arc = self.task_cfg.swing_arc
        if not bool(arc.enabled):
            return
        segments = int(arc.segments)
        low = min(layout.socket_angle(name) for name in LINKBAR_SOCKETS)
        high = max(layout.socket_angle(name) for name in LINKBAR_SOCKETS)
        for index in range(segments):
            angle = low + (high - low) * (index + 0.5) / segments
            xy = layout.pin_center_xy(angle)
            self._box(
                scene, manifest, f"arc_tick_{index:02d}",
                layout.position_to_world((xy[0], xy[1], float(arc.z_offset))),
                _list(arc.tick_size),
                arc.color,
                role="marker",
                yaw_deg=float(np.rad2deg(angle)),
                collision=False,
            )
        for socket in LINKBAR_SOCKETS:
            xy = layout.socket_center_xy(socket)
            self._box(
                scene, manifest, f"arc_seat_{socket}",
                layout.position_to_world((xy[0], xy[1], float(arc.z_offset))),
                _list(arc.seat_tick_size),
                arc.seat_color,
                role="marker",
                yaw_deg=float(np.rad2deg(layout.socket_angle(socket))),
                collision=False,
            )
