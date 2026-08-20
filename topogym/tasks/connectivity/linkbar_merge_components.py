"""Linkbar Merge Components (docx 4.4): swing the beam into the socket that belongs to the OTHER frame.

Scene: two sections of machine frame stand on the table. Component A is bolted
down -- its base spine, its pivot column and an outrigger rail are all world-fixed.
Component B is a free body resting in a pair of locating cleats. A connecting beam
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
  ``angle -/+ 90`` depending on which way the beam turns to reach it. The part is
  symmetric across its own slot, so both installations use the same shape list.

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

        Both neighbours are placed off this number -- A's outrigger stops here and
        B's frame starts here -- so the plates butt instead of overlapping, and two
        coplanar top faces never z-fight.
        """

        sock = self.cfg.socket
        return (
            float(self.cfg.linkbar.pin.radius)
            + float(sock.pin_clearance)
            + float(sock.jaw_thickness)
        )

    @property
    def capture_tolerance_xy(self) -> float:
        return float(self.cfg.socket.capture_tolerance_xy)

    def capture_tolerance_deg(self) -> float:
        """The same window read as a joint angle, which is what the arm controls."""

        return float(np.rad2deg(self.capture_tolerance_xy / self.arm_radius))

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
        """B's long axis: radially outward from the pivot, through its own catch."""

        return self.socket_angle("b1")

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
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    # ----------------------------------------------------------- entity access

    def linkbar_entity(self):
        return self.manifest.get("linkbar")

    def component_b_entity(self):
        return self.manifest.get("component_b")

    def socket_entity(self, socket: str):
        """The body a latch at ``socket`` welds the beam to.

        For B1 that is component B itself; for A2 it is the catch bolted to A's
        outrigger, which is world-fixed. Both are single-link assemblies, so each
        has exactly one link index to name in a weld.
        """

        return self.manifest.get(
            "component_b" if str(socket) == "b1" else "socket_a2"
        )

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

    # --------------------------------------------------------- constraint graph

    def beam_link_idx(self) -> int:
        """Global link index of the rotating link -- one end of any latch weld."""

        return int(self.linkbar_entity().get_link(name="hinge_arm").idx)

    def socket_link_idx(self, socket: str) -> int:
        return int(self.socket_entity(socket).base_link.idx)

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
        self._add_component_b(scene, manifest, layout)
        self._add_locators(scene, manifest, layout)
        entity, joint_name = self._add_linkbar(scene, manifest, layout)
        self._add_swing_arc(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        joint_dof = hinge_joint_dof(entity, joint_name)
        merge_scene = LinkbarMergeScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            joint_name=joint_name,
            joint_dof=joint_dof,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        merge_scene.set_arm_angle(layout.init_angle)
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
            layout.arm_radius - layout.socket_pad_half_width,
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

    def _socket_shapes(self) -> list[HingeShape]:
        """The catch, in its own frame: +x out through the mouth, +y across the slot.

        One list, used for A2 and for B1 both, because docx 4.4's anti-shortcut
        argument only holds if the two really are the same part. The shape is
        symmetric across the slot, which is what lets one part be installed facing
        either way round the circle (see `LinkbarMergeLayout.socket_yaw_deg`).

        Load path: the pin enters at +x, runs down the slot to the origin where the
        latch fires, and is stopped by the back plate if it overshoots. The jaws
        take the sideways load; nothing here has to hold the pin down, because the
        beam's hinge already refuses to move it vertically.
        """

        sock = self.task_cfg.socket
        pin_radius = float(self.task_cfg.linkbar.pin.radius)
        slot_half = pin_radius + float(sock.pin_clearance)
        jaw_thickness = float(sock.jaw_thickness)
        jaw_length = float(sock.jaw_length)
        jaw_height = float(sock.jaw_height)
        pad_thickness = float(sock.pad_thickness)
        jaw_offset = slot_half + 0.5 * jaw_thickness
        pad_width = 2.0 * jaw_offset + jaw_thickness
        stop_station = float(sock.back_stop_station)
        stop_thickness = float(sock.back_stop_thickness)

        shapes = [
            HingeShape(
                kind="box",
                size=(float(sock.pad_length), pad_width, pad_thickness),
                origin=(float(sock.pad_station), 0.0, 0.5 * pad_thickness),
                color=_list(sock.color),
            ),
        ]
        for sign in (1.0, -1.0):
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(jaw_length, jaw_thickness, jaw_height),
                    origin=(float(sock.jaw_station), sign * jaw_offset,
                            pad_thickness + 0.5 * jaw_height),
                    color=_list(sock.color),
                )
            )
        shapes.append(
            HingeShape(
                kind="box",
                size=(stop_thickness, pad_width, jaw_height),
                origin=(stop_station, 0.0, pad_thickness + 0.5 * jaw_height),
                color=_list(sock.accent_color),
            )
        )
        # A chamfer on each jaw's lip, so the mouth reads as a mouth. Visual only:
        # widening the entry in physics would change how much misalignment the
        # catch forgives, and that budget belongs to `capture_tolerance_xy`.
        lip_length = float(sock.lip_length)
        for sign in (1.0, -1.0):
            shapes.append(
                HingeShape(
                    kind="box",
                    size=(lip_length, jaw_thickness, jaw_height),
                    origin=(float(sock.jaw_station) + 0.5 * jaw_length + 0.5 * lip_length,
                            sign * (jaw_offset + 0.5 * jaw_thickness),
                            pad_thickness + 0.5 * jaw_height),
                    rpy=(0.0, 0.0, sign * float(np.deg2rad(float(sock.lip_flare_deg)))),
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
            shapes=self._socket_shapes(),
            mass=float(self.task_cfg.socket.mass),
            color=_list(self.task_cfg.socket.color),
            fixed=True,
            contact_friction=float(self.task_cfg.socket.contact_friction),
        )

    # ------------------------------------------------------------ component B

    def _add_component_b(self, scene, manifest, layout) -> None:
        """B: the same catch, plus a frame section hanging off it, as ONE rigid body.

        One body and not an assembly of entities, because the lift test asks whether
        B as a whole is held down. Separate entities would each answer for
        themselves and the ones that were never welded would simply rise.

        B's frame is written in the catch's local frame, which is why the station
        arithmetic below runs along local +/-y: the catch's own axes are set by
        which way it faces round the circle, and B hangs off its radially outward
        side either way.
        """

        comp = self.task_cfg.component_b
        base = comp.base
        # In the catch's frame, radially outward is +y when the beam reaches B1
        # counter-clockwise and -y when it reaches it clockwise -- the same mirror
        # `socket_yaw_deg` applies. B is built along that direction.
        out = layout.approach_sign("b1")
        start = layout.socket_pad_half_width + float(base.gap)
        base_length = float(base.length)
        base_centre = start + 0.5 * base_length

        shapes = list(self._socket_shapes())
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
        add_rigid_assembly(
            scene,
            manifest,
            name="component_b",
            urdf_path=asset_root / "component_b.urdf",
            world_pos=layout.position_to_world((centre[0], centre[1], 0.0)),
            yaw_deg=layout.socket_yaw_deg("b1"),
            shapes=shapes,
            mass=float(comp.mass),
            color=_list(comp.color),
            fixed=False,
            contact_friction=float(comp.contact_friction),
        )

    def _add_locators(self, scene, manifest, layout) -> None:
        """Two fixed cleats against B's outboard end.

        A workstation locates a part it expects to be lifted out again; these do the
        same job here and are the reason a glancing contact from the pin does not
        walk B out of reach of its own catch. They constrain B sideways ONLY -- the
        lift test still has a clear path straight up, which is the whole point of
        judging by lifting.
        """

        locators = self.task_cfg.component_b.locators
        if not bool(locators.enabled):
            return
        base = self.task_cfg.component_b.base
        outboard = (
            layout.socket_pad_half_width
            + float(base.gap)
            + float(base.length)
            + 0.5 * float(locators.size[0])
            + float(locators.clearance)
        )
        angle = layout.b_axis_angle
        for sign, name in ((1.0, "b_locator_left"), (-1.0, "b_locator_right")):
            xy = layout.b_station_xy(outboard, sign * float(locators.spacing))
            self._box(
                scene,
                manifest,
                name,
                layout.position_to_world((xy[0], xy[1], 0.5 * float(locators.size[2]))),
                _list(locators.size),
                locators.color,
                yaw_deg=float(np.rad2deg(angle)),
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
        axle_height = layout.beam_top_z + float(bar.axle.rise)
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
                origin=(0.0, 0.0, 0.5 * axle_height),
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
            limit_rad=None,
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
