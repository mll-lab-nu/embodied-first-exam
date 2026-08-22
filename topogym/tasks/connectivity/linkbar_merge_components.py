"""Linkbar Merge Components (docx 4.4): swing the beam into the socket that belongs to the OTHER frame.

Scene: a bolted-down swing-arm station, and a cart parked on a straight rail
beside it. Component A is a pivot column and one plate reaching out to its own
socket, A2, and none of it moves. Component B is the cart: it rides the rail on a
single sliding joint and carries socket B1 at its front. A connecting beam is hinged
to A's pivot column on a vertical joint, so its end pin travels a horizontal circle,
and both catches sit on that circle. The arm turns the beam by a knob and drops the
pin into one of them, where a latch welds it. Into B1, the cart can no longer roll.

**The two interfaces are the same part.** `_socket_shapes` is called once and its
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
  other, and a plate at pin height is a hard stop. `LinkbarMergeLayout.validate`
  refuses a layout that breaks it, rather than letting an unsolvable instance be
  generated silently.
- A pocket opens toward the side the pin arrives from, so its yaw is
  ``angle -/+ 90`` depending on which way the beam turns to reach it. The part
  itself is the same either way: two jambs and a back stop, 24 mm deep.

Heights are stacked off the CART'S DECK rather than off the table, and only the pin
ever touches a pocket. Rail 0-12 mm, wheels to 32 mm, deck 32-44 mm, both pockets
44-84 mm, the pin hanging from the beam down to 52 mm, the beam's underside at
95 mm clearing both. B1 projects forward from the cart's headstock with nothing
under it, the way a coupler does; A2 is held to the same height by a stand on A's
outrigger. A pocket sitting near the table instead read as bolted to the ground,
which is a different mounting story from a chassis on wheels -- no amount of
matching their colour or width made the two look like one object.

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
    _to_container,
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


def shape_span_z(shapes) -> tuple[float, float]:
    """Lowest and highest z the given parts actually occupy, in their link's frame.

    Measured off the shapes rather than read back out of config, because the two
    can disagree: a skirt whose height was written as a span from zero kept
    reporting the intended 0.044 floor while standing on the table (2026-08-22).
    A number taken from the same place the geometry comes from cannot catch that.
    """

    low, high = float("inf"), float("-inf")
    for shape in shapes:
        origin_z = float(_to_container(shape.origin)[2])
        half = float(shape.half_extent()[2])
        low = min(low, origin_z - half)
        high = max(high, origin_z + half)
    return low, high


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
    def socket_half_width(self) -> float:
        """Half the pocket's width across the slot, i.e. its radial half-extent.

        Both neighbours are placed off this: A's outrigger runs out to it and the
        cart's deck starts at it, each overlapping by `socket_neighbour_overlap` so
        the pocket reads as bolted on rather than floating beside them.
        """

        sock = self.cfg.socket
        return (
            float(self.cfg.linkbar.pin.radius)
            + float(sock.pin_clearance)
            + float(sock.jamb_thickness)
        )

    @property
    def socket_neighbour_overlap(self) -> float:
        """How far a plate's neighbour reaches into it.

        A little overlap rather than a flush butt: two exactly coplanar faces
        z-fight, while overlapping volume is invisible.
        """

        return float(self.cfg.socket.neighbour_overlap)

    @property
    def capture_tolerance_xy(self) -> float:
        """How close the pin has to get to a seat before the latch fires."""

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
    def socket_floor_z(self) -> float:
        """Height of a pocket's underside: the cart's deck top.

        The whole coupling chain hangs off this one number, and it is deck height
        rather than floor height on purpose. A pocket whose underside sat near the
        table read as bolted to the ground, which is a different mounting story from
        a chassis carried on wheels -- the two never looked like one object however
        their colour or width was matched.

        At deck height, B1 projects forward from the cart's headstock with nothing
        under it, the way a coupler does, and A2 is held up to the same height by a
        stand on A's outrigger. Both pockets still present their mouth at exactly the
        same height, which they must, since there is one pin and it is at one height.
        What differs is what CARRIES each: a wheeled cart, or a fixed stand. That is
        the ownership cue, and raising the chain made it stronger rather than weaker.
        """

        return float(self.cfg.socket.floor_z)

    @property
    def rail_top_z(self) -> float:
        """Top of the rails: what the cart's wheels run on."""

        return float(_list(self.cfg.component_b.rail.section)[1])

    @property
    def wheel_centre_z(self) -> float:
        """Wheel axle height: one radius above the rail the wheel sits on."""

        return self.rail_top_z + float(self.cfg.component_b.cart.wheel_radius)

    @property
    def deck_bottom_z(self) -> float:
        """Cart deck underside: clear of the wheels it rides on."""

        return self.wheel_centre_z + float(self.cfg.component_b.cart.wheel_radius)

    @property
    def cart_start(self) -> float:
        """Where the cart's deck begins, measured outward from its plate's seat."""

        return self.socket_half_width - self.socket_neighbour_overlap

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
    shape_spans: dict = field(default_factory=dict)
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

    def touching(self) -> str:
        """What the beam is in contact with right now, and how hard.

        A beam that moves when nothing commanded it has either been pushed or is
        drifting, and the two want opposite fixes. Reading the contact set says
        which -- the same diagnostic that found the parked arm fouling the sweep on
        2026-08-20, where reasoning from the angle alone had been wrong twice.
        """

        contacts = self.linkbar_entity().get_contacts(exclude_self_contact=True)
        if not contacts:
            return "none"
        owners = {}
        for name, entity in self.manifest.as_dict().items():
            for link in getattr(entity, "links", None) or ():
                owners[int(link.idx)] = name
        link_a = _as_numpy(contacts["link_a"]).reshape(-1)
        link_b = _as_numpy(contacts["link_b"]).reshape(-1)
        force = _as_numpy(contacts["force_a"]).reshape(-1, 3)
        beam = self.beam_link_idx()
        totals: dict[str, float] = {}
        for index, (first, second) in enumerate(zip(link_a, link_b)):
            other = int(second) if int(first) == beam else int(first)
            name = owners.get(other, f"link{other}")
            totals[name] = totals.get(name, 0.0) + float(np.linalg.norm(force[index]))
        if not totals:
            return "none"
        return ",".join(f"{name}:{value:.2f}N"
                        for name, value in sorted(totals.items(), key=lambda kv: -kv[1]))

    def height_chain(self) -> str:
        """The stack the whole coupling hangs off, as one line.

        Printed at setup because "did my config change reach this machine" is a
        question that has cost two runs already, and every number here moves when
        the coupling height does.
        """

        layout = self.layout
        cart = layout.cfg.component_b.cart
        spans = " ".join(
            f"{name}_built={low:.4f}..{high:.4f}"
            for name, (low, high) in sorted(self.shape_spans.items())
        )
        return (
            f"rail_top={layout.rail_top_z:.4f} deck={layout.deck_bottom_z:.4f}.."
            f"{layout.deck_bottom_z + float(cart.deck_thickness):.4f} "
            f"socket={layout.socket_floor_z:.4f}.."
            f"{layout.socket_floor_z + float(layout.cfg.socket.jamb_height):.4f} "
            f"pin_bottom={layout.pin_bottom_z:.4f} "
            f"beam_bottom={layout.beam_bottom_z:.4f} "
            f"knob={layout.knob_bottom_z:.4f}..{layout.knob_top_z:.4f} "
            + spans
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
        self._spans: dict = {}

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
            shape_spans=dict(self._spans),
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
        """A: a pivot column, a plate reaching out to A2, and the stand under it.

        Three pieces plus the socket, and that is the whole fixed assembly. The plate
        runs from the pivot to A2 because that is what makes A2 visibly part of A --
        the claim the task turns on. The stand on its end lifts A2 to
        `socket_floor_z`, the height B1 reaches by riding on the cart, and it is the
        fixed counterpart to the cart's wheels: same socket, visibly different thing
        holding it up.
        """

        comp = self.task_cfg.component_a
        outrigger = comp.outrigger
        # The plate stops where the catch pad starts, so the two butt rather than
        # overlap: two coplanar top faces would z-fight.
        self._rail(
            scene, manifest, layout, "a_outrigger",
            layout.a_outrigger_angle,
            layout.arm_radius - layout.socket_half_width
            + layout.socket_neighbour_overlap,
            float(outrigger.width), float(outrigger.thickness),
            outrigger.color,
        )
        # The stand that lifts A2 to the coupling height. It is not only packing:
        # it is the visible answer to "what holds A2 up", and the fixed counterpart
        # to the cart's wheels.
        stand = comp.socket_stand
        stand_bottom = float(outrigger.thickness)
        stand_height = layout.socket_floor_z - stand_bottom
        centre = layout.socket_center_xy("a2")
        self._box(
            scene, manifest, "a_socket_stand",
            layout.position_to_world(
                (centre[0], centre[1], stand_bottom + 0.5 * stand_height)
            ),
            (float(stand.depth), float(stand.width), stand_height),
            stand.color,
            yaw_deg=layout.socket_yaw_deg("a2"),
        )

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

    # --------------------------------------------------------------- catches

    def _socket_shapes(self, layout) -> list[HingeShape]:
        """The pocket, in its own frame: +x toward the pin, +y across the slot.

        Two jambs and a back plate. The beam's pin hangs down from its end and
        slides in tangentially; the jambs take it radially, the back plate stops it
        at depth. That engagement is real: the pin is captured radially and can only
        travel on a circle, so a radial push on the cart has nowhere to go, and the
        travel test holds on mechanics alone. The weld is then what docx calls it --
        the latch that locks once seated -- rather than the only thing carrying load.

        **The pocket is shallow, and that is what makes it a straight one.** A slot
        long enough to guide a swinging pin has to BE an arc: over 103 mm a 170 mm
        arc departs from the chord by 12.9 mm against 4 mm of clearance, which
        jammed the pin 22 degrees short of the seat (measured 2026-08-20). Over the
        24 mm entry here the departure is 1.7 mm, so a straight pocket clears it
        with 2.3 mm to spare and the whole arc-segmentation machinery is unnecessary.

        Open on top on purpose: the pin comes down from the beam, so a roof over the
        slot would be something the pin's own arm runs into. The cap behind the back
        plate is decoration -- the pin never reaches past the stop.

        Nothing here reaches below `socket_floor_z`: the pocket sits at deck height
        and projects forward from its host like a coupler, so there is no skirt down
        to the table. An earlier version had one, to bridge a pocket that hung near
        the floor -- once the coupling height moved up to the deck it had nothing
        left to bridge, and its z span was still being measured from zero, which put
        a slab from the table to the pocket's roof.

        One generator, called once per socket, with no handedness: the pocket always
        opens toward the side the pin arrives from, so the same shape serves both
        installations. docx 4.4's anti-shortcut argument needs the two interfaces to
        be the same part, and here they are the same part in the literal sense.
        """

        sock = self.task_cfg.socket
        pin_radius = float(self.task_cfg.linkbar.pin.radius)
        jamb_thickness = float(sock.jamb_thickness)
        jamb_height = float(sock.jamb_height)
        back_thickness = float(sock.back_thickness)
        entry = float(sock.entry_depth)
        lift = layout.socket_floor_z
        jamb_offset = pin_radius + float(sock.pin_clearance) + 0.5 * jamb_thickness
        width = 2.0 * jamb_offset + jamb_thickness
        # The slot runs from the back plate's face out to the mouth. The pin seats
        # at the local origin, so the stop sits one pin radius behind it.
        back_face = -pin_radius
        length = entry - back_face
        centre = 0.5 * (back_face + entry)

        shapes = [
            HingeShape(
                kind="box",
                size=(back_thickness, width, jamb_height),
                origin=(back_face - 0.5 * back_thickness, 0.0, lift + 0.5 * jamb_height),
                color=_list(sock.color),
            )
        ]
        for side in (1.0, -1.0):
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(length, jamb_thickness, jamb_height),
                    origin=(centre, side * jamb_offset, lift + 0.5 * jamb_height),
                    color=_list(sock.color),
                )
            )
        return shapes

    def _add_socket_a2(self, scene, manifest, layout) -> None:
        """A's own catch. Bolted down, because everything about A is."""

        centre = layout.socket_center_xy("a2")
        asset_root = resolve_mesh_dir("runs/generated_meshes/linkbar_merge_components")
        shapes = self._socket_shapes(layout)
        self._spans["socket"] = shape_span_z(shapes)
        add_rigid_assembly(
            scene,
            manifest,
            name="socket_a2",
            urdf_path=asset_root / "socket_a2.urdf",
            world_pos=layout.position_to_world((centre[0], centre[1], 0.0)),
            yaw_deg=layout.socket_yaw_deg("a2"),
            shapes=shapes,
            mass=float(self.task_cfg.socket.mass),
            color=_list(self.task_cfg.socket.color),
            fixed=True,
            contact_friction=float(self.task_cfg.socket.contact_friction),
        )

    # ------------------------------------------------------------ component B

    def _add_component_b(self, scene, manifest, layout) -> tuple[Any, str]:
        """B: a cart on a rail, carrying its catch at the front. One rigid body.

        A carriage on a prismatic joint rather than a free body, and that is what
        the physical recheck rests on. As a free body B had six degrees of freedom
        and nothing but friction and a pair of cleats holding it: measured
        2026-08-20, the pin brushing a jaw walked it 12.8 mm and then 14.5 mm out of
        place, far enough that the latch was testing a seat that had moved. A cart
        has one degree of freedom and cannot be nudged out of any other -- measured
        after the change, 0.00 mm.

        It also turns the judge into a bounded reading: "merged" means the cart
        cannot roll, "not merged" means it runs to its stop, a fixed distance rather
        than a displacement whose size depends on how hard the probe pushed
        (measured 0.0000 m against 0.1002 m). See `_travel_probe.py`.

        Three shapes plus the catch. The catch sits at the front at table height,
        the deck spans the rails just above it, and the body sits on the deck -- so
        in side view the cart is one continuous stack from rail top upward, which is
        what makes "it rides the rail" readable rather than something to be inferred.

        Everything is written in the catch's local frame, which is why the station
        arithmetic runs along local +/-y: the catch's own axes are set by which way
        it faces round the circle, and the rail runs radially outward either way.
        """

        comp = self.task_cfg.component_b
        cart = comp.cart
        mech = comp.mechanism
        # In the catch's frame, radially outward is +y when the beam reaches B1
        # counter-clockwise and -y when it reaches it clockwise -- the same mirror
        # `socket_yaw_deg` applies. The cart is built, and travels, that way.
        out = layout.approach_sign("b1")
        start = layout.cart_start
        deck_length = float(cart.deck_length)
        deck_thickness = float(cart.deck_thickness)
        deck_bottom = layout.deck_bottom_z
        body_inset = float(cart.body_inset)

        shapes = list(self._socket_shapes(layout))
        shapes.append(
            HingeShape(
                kind="box",
                size=(float(cart.deck_width), deck_length, deck_thickness),
                origin=(0.0, out * (start + 0.5 * deck_length),
                        deck_bottom + 0.5 * deck_thickness),
                color=_list(comp.color),
            )
        )
        body_height = float(cart.body_height)
        shapes.append(
            HingeShape(
                kind="box",
                size=(float(cart.deck_width) - 2.0 * body_inset,
                      deck_length - 2.0 * body_inset,
                      body_height),
                origin=(0.0, out * (start + 0.5 * deck_length),
                        deck_bottom + deck_thickness + 0.5 * body_height),
                color=_list(cart.body_color),
            )
        )

        # Wheels, on the rails the deck spans. Visual only, like the rails: the
        # prismatic joint is the constraint, and wheels that also collided would
        # fight it. They are here so that "a cart, rolling on a track" is something
        # the picture says rather than something the reader has to infer.
        wheel_radius = float(cart.wheel_radius)
        half_gauge = 0.5 * float(comp.rail.gauge)
        for index, station in enumerate(_list(cart.wheel_stations)):
            for side in (1.0, -1.0):
                shapes.append(
                    HingeShape(
                        kind="cylinder",
                        size=(wheel_radius, float(cart.wheel_width)),
                        origin=(side * half_gauge, out * (start + station),
                                layout.wheel_centre_z),
                        # A cylinder's axis is its local z, so this lays it across
                        # the track, which is the way an axle runs.
                        rpy=(0.0, 0.5 * np.pi, 0.0),
                        color=_list(cart.wheel_color),
                        collide=False,
                    )
                )
            del index

        self._spans["cart"] = shape_span_z(shapes)

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
        """Two straight rails under the cart, and a stop at the far end.

        Visual only, like `stacked_plate`'s rod: the real constraint is the
        prismatic joint, and rails that also collided would fight it. What they are
        for is making the cart's one degree of freedom legible -- a body sliding
        along an invisible line reads as a bug rather than as a mechanism.

        They start at the cart's own front, not further in: reaching under the catch
        would put a rail through it.
        """

        rail = self.task_cfg.component_b.rail
        if not bool(rail.enabled):
            return
        cart = self.task_cfg.component_b.cart
        angle = layout.b_axis_angle
        yaw = float(np.rad2deg(angle))
        width, height = _list(rail.section)
        inner = layout.cart_start
        length = float(cart.deck_length) + layout.rail_travel + float(rail.overhang)
        centre_station = inner + 0.5 * length
        half_gauge = 0.5 * float(rail.gauge)
        for sign, tag in ((1.0, "left"), (-1.0, "right")):
            xy = layout.b_station_xy(centre_station, sign * half_gauge)
            self._box(
                scene, manifest, f"b_rail_{tag}",
                layout.position_to_world((xy[0], xy[1], 0.5 * height)),
                (length, width, height),
                rail.color,
                yaw_deg=yaw,
                collision=False,
            )
        stop_size = _list(rail.stop_size)
        stop_station = inner + length + 0.5 * stop_size[0]
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
