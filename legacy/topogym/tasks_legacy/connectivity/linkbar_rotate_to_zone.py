"""Linkbar Rotate To Zone (docx 4.4, reworked): turn the beam so its pin rests on the zone the instruction names.

Scene: a fixed pivot column with a connecting beam hinged to it on a vertical
joint, so the beam's end pin travels a horizontal circle. A fixed span of that
circle is marked on the table as a dashed rail, and somewhere on the rail lie two
zones that do not overlap -- on the same side of the beam or on opposite sides,
far apart or touching. One is painted red and the other blue. The arm turns the
beam by its knob and lets go; the beam stays where the joint's friction parks it.
Success is the pin resting inside the zone whose colour the instruction named.

This replaced the cart-and-sockets version on 2026-08-27. That version judged
success by pushing a rail cart and reading that it did not move, which is a fact
the physics can measure but a viewer cannot see. Here the verdict is in one frame:
the pin is on the named colour, or it is not. The rail, the cart, both sockets, the
weld latch and the travel test are gone; the pivot, the beam and the knob primitive
are unchanged, including every height that was measured for the grasp.

**Nothing on the beam says which zone is the target (2026-09-09).** The pin, its
collar and the knob's cap are the same grey as the shaft, so the whole beam is grey,
blue-grey and charcoal -- no bright colour anywhere on it. Until 2026-09-08 the pin
was painted the target zone's colour, so "turn to the zone that matches the pin" was
the whole task, a colour match needing no reading of what was asked. That was fixed
by giving the pin a third colour, but a bright marker colour on the beam is still the
most eye-catching thing in the frame and invites a policy to track it. Now the target
reaches the policy two ways and no other: the sentence (`instruction`, which names
red or blue) and, for baselines with no language input, the integer `goal_id`.

**The two zones are the same thing.** `_add_zones` draws both from one routine,
at the same radius and the same size. They differ only in colour. Drawing
`zones.target` and the colour assignment as two independent axes is what keeps
both "the target is the left one" and "the target is red" a coin flip: a policy
has to read the sentence AND find that colour in the picture. Drawing the two
rail positions independently as well stops "turn to the nearer one" and "always
turn the same way". The zone keys `color_1` / `color_2` are labels and nothing
more (they replaced `left` / `right` on 2026-09-01, when the zones stopped being
one per side); after randomization `color_1` is the one at the smaller angle.

Sign conventions, used by the planner and the verifier as well:

- The joint angle is 0 with the beam pointing +x (away from the arm, toward the
  front camera) and grows counter-clockwise about +z. The front camera looks down
  -x with +z up, so its screen-right is +y and a positive angle swings the beam to
  screen-right.
- Both zones lie wholly on the rail, do not overlap (touching is allowed), and
  neither contains the pin at the beam's initial angle. `LinkbarRotateLayout.validate`
  refuses a layout that breaks any of these, rather than letting an ambiguous or
  already-solved instance be generated silently.
- "In a zone" is an angle test: the joint angle is within `zones.half_width_deg`
  of the zone's centre angle. The painted block is drawn to exactly that span, so
  what the judge reads and what the camera shows are one number.

Everything is generated from config numbers, and the layout is derived rather than
tabulated: zone positions and the beam's length follow from the pivot, the arm
radius and the two zone angles, so changing any of them keeps the scene consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.tasks_legacy._fixtures import HingeShape, add_hinge_mechanism, hinge_joint_dof
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials
from topogym.world.rope import resolve_mesh_dir

LINKBAR_ZONES = ("color_1", "color_2")


def _list(value):
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    return [float(v) for v in OmegaConf.to_container(value, resolve=True)]


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def wrap_angle(angle: float) -> float:
    """Fold ``angle`` (radians) into (-pi, pi]."""

    return float((float(angle) + np.pi) % (2.0 * np.pi) - np.pi)


def direction(angle: float) -> np.ndarray:
    """Unit vector at ``angle`` radians in the xy plane."""

    return np.array([np.cos(float(angle)), np.sin(float(angle))], dtype=float)


def tangent(angle: float) -> np.ndarray:
    """Unit vector 90 degrees counter-clockwise of `direction`, i.e. the pin's travel."""

    return np.array([-np.sin(float(angle)), np.cos(float(angle))], dtype=float)


@dataclass(frozen=True)
class LinkbarRotateLayout:
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
        """Radius of the circle the end pin travels on -- and both zones sit on."""

        return float(self.cfg.linkbar.arm_radius)

    @property
    def init_angle(self) -> float:
        return float(np.deg2rad(float(self.cfg.linkbar.init_angle_deg)))

    # ------------------------------------------------------------------- rail

    def rail_span(self) -> tuple[float, float]:
        """The fixed arc the zones may sit on, radians (start, end)."""

        rail = self.cfg.rail
        return float(np.deg2rad(float(rail.start_deg))), float(np.deg2rad(float(rail.end_deg)))

    # ------------------------------------------------------------------ zones

    def zone_angle(self, zone: str) -> float:
        return float(np.deg2rad(float(getattr(self.cfg.zones, str(zone)).angle_deg)))

    def zone_center_xy(self, zone: str) -> np.ndarray:
        """Where the pin sits when centred on this zone: on the arm circle."""

        return self.pivot_xy + self.arm_radius * direction(self.zone_angle(zone))

    @property
    def zone_half_width(self) -> float:
        """Half the zone's angular span, radians. The judge's window and the paint's."""

        return float(np.deg2rad(float(self.cfg.zones.half_width_deg)))

    def zone_color_name(self, zone: str) -> str:
        return str(getattr(self.cfg.zones.assignment, str(zone)))

    def zone_color(self, zone: str) -> list[float]:
        return _list(getattr(self.cfg.zones.colors, self.zone_color_name(zone)))

    def target_zone(self) -> str:
        """Which zone the bar has to reach. The one fact the policy has to read."""

        zone = str(self.cfg.zones.target)
        if zone not in LINKBAR_ZONES:
            raise ValueError(f"zones.target={zone!r}; expected one of {LINKBAR_ZONES}.")
        return zone

    def target_colour(self) -> str:
        """The colour the target zone is painted. The word the instruction uses.

        This, not the zone key, is what reaches a policy: the sentence names a
        colour and the picture says where that colour is. `zones.target` is the
        config's way of writing the same fact down.
        """

        return self.zone_color_name(self.target_zone())

    def zone_for_colour(self, colour: str) -> str:
        """Which zone is painted ``colour``. The lookup the oracle makes.

        The answer is unique because `validate` refuses a layout whose two zones
        share a colour.
        """

        colour = str(colour)
        for zone in LINKBAR_ZONES:
            if self.zone_color_name(zone) == colour:
                return zone
        painted = {zone: self.zone_color_name(zone) for zone in LINKBAR_ZONES}
        raise ValueError(f"No zone is painted {colour!r}; the zones are {painted}.")

    def goal_id(self) -> int:
        """The target colour as an integer, for baselines with no language input.

        Its index in `zones.colors`, so the yaml's key order IS the numbering
        (red 0, blue 1). A COLOUR index and not a zone index: handing over the
        zone would say "turn left" or "turn right" outright, and a policy could
        then solve the task without looking at the table at all -- the same
        shortcut painting the pin used to hand out.
        """

        keys = [str(name) for name in self.cfg.zones.colors.keys()]
        return keys.index(self.target_colour())

    def instruction(self) -> str:
        """`goal.instruction` with the target zone's colour filled in."""

        return str(self.cfg.goal.instruction).format(target_colour=self.target_colour())

    def target_angle(self, zone: str) -> float:
        return self.zone_angle(zone)

    def nearest_zone(self, angle: float) -> str:
        """Whichever zone is the shorter turn from ``angle``. The baseline's rule."""

        return min(LINKBAR_ZONES, key=lambda name: abs(self.zone_angle(name) - float(angle)))

    def in_zone(self, angle: float, zone: str) -> bool:
        """Is the pin inside this zone at joint angle ``angle``?"""

        return abs(wrap_angle(float(angle) - self.zone_angle(zone))) <= self.zone_half_width

    def zone_at(self, angle: float) -> str | None:
        for zone in LINKBAR_ZONES:
            if self.in_zone(angle, zone):
                return zone
        return None

    # ------------------------------------------------------------------- beam

    @property
    def beam_bottom_z(self) -> float:
        return float(self.cfg.linkbar.beam.bottom_z)

    @property
    def beam_top_z(self) -> float:
        return self.beam_bottom_z + float(self.cfg.linkbar.beam.height)

    @property
    def axle_bottom_z(self) -> float:
        """Where the turning shaft starts: just above the fixed pivot column.

        The shaft cannot run down to the table, because the column is already
        there. Two solid cylinders on the same axis, overlapping over the column's
        whole height, is a permanent contact between a world-fixed body and the one
        part that has to turn freely -- and Genesis does not know they are meant to
        be a bearing. Measured 2026-08-20 with the shaft starting at z=0: a driven
        sweep stalled up to 22 degrees short of its target.

        ``axle.clearance`` keeps the shaft's underside off the column's top face as
        well. Coplanar faces would be a thrust bearing, which is a smaller version
        of the same mistake.
        """

        column = self.cfg.pivot_column
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

    @property
    def knob_cap_top_z(self) -> float:
        """Top of the knob's end cap: the highest thing the beam carries.

        What the gripper has to clear on its way to the knob. The approach happens
        at a fixed height and ends directly over the knob, so this is the number
        that decides whether the traverse brushes the beam.
        """

        return self.knob_top_z + float(self.cfg.linkbar.knob.cap_height)

    def knob_center_xy(self, angle: float) -> np.ndarray:
        return self.pivot_xy + self.knob_station * direction(float(angle))

    def knob_grasp_z(self) -> float:
        """Finger-pad height on the knob, in the task frame."""

        return self.knob_bottom_z + float(self.cfg.linkbar.knob.grasp_height)

    def knob_grasp_world(self, angle: float) -> np.ndarray:
        xy = self.knob_center_xy(angle)
        return self.position_to_world((xy[0], xy[1], self.knob_grasp_z()))

    def steps_arc(self, sweep: float) -> int:
        """Sim steps for a sweep of ``sweep`` radians, at the configured angular rate.

        What is held constant is the angular speed, not the step count: with a
        fixed count the speed scaled with the sweep, and so did the joint's lag
        behind the hand (2026-09-01 sweep: ~0.05 deg of lag per degree of sweep).
        """

        motion = self.cfg.motion
        per_step = float(motion.arc_deg_per_step)
        needed = int(np.ceil(abs(float(np.rad2deg(float(sweep)))) / per_step))
        return max(int(motion.min_steps_arc), needed)

    # ------------------------------------------------------------ init angle

    def init_angle_segments(self) -> list[tuple[float, float]]:
        """Degrees the beam may start at: the init span minus each zone's keep-out.

        The zones are drawn first, so where the pin may start is a function of
        where they landed. Cutting the keep-outs (``half_width + pin_start_margin``
        either side of a centre) out of ``linkbar.init_span_deg`` leaves one to
        three intervals; ``init_angle_from_frac`` maps a unit draw onto their
        union, so no draw ever puts the pin on a zone. Empty only when the two
        zones cover the whole span (about 0.25% of pairs) -- that one is rejected.
        """

        lo, hi = (float(v) for v in self.cfg.linkbar.init_span_deg)
        keep_out = float(self.cfg.zones.half_width_deg) + float(
            self.cfg.zones.pin_start_margin_deg
        )
        segments = [(lo, hi)]
        for name in LINKBAR_ZONES:
            centre = float(np.rad2deg(self.zone_angle(name)))
            ko_lo, ko_hi = centre - keep_out, centre + keep_out
            cut: list[tuple[float, float]] = []
            for start, end in segments:
                if ko_hi <= start or ko_lo >= end:
                    cut.append((start, end))
                    continue
                if ko_lo > start:
                    cut.append((start, ko_lo))
                if ko_hi < end:
                    cut.append((ko_hi, end))
            # Two keep-outs meeting at one angle leave a float-rounding sliver.
            segments = [(s, e) for s, e in cut if e - s > 1e-6]
        return segments


    def init_angle_from_frac(self, frac: float) -> float:
        """The beam's initial angle (deg) at unit position ``frac`` along the allowed set."""

        segments = self.init_angle_segments()
        total = sum(end - start for start, end in segments)
        if total <= 0.0:
            raise ValueError(
                "The two zones' keep-outs cover the whole initial-angle span "
                f"{list(self.cfg.linkbar.init_span_deg)} deg; nowhere for the pin to start."
            )
        t = min(max(float(frac), 0.0), 1.0) * total
        for start, end in segments:
            if t <= end - start:
                return start + t
            t -= end - start
        return segments[-1][1]

    # ------------------------------------------------------------- validation

    def validate(self) -> None:
        """Refuse a layout that cannot be solved, instead of building it anyway.

        Each zone must lie wholly on the rail (the rail's ends are where the knob
        leaves the arm's working area), the two painted spans must not overlap --
        a pin on both zones at once has no verdict; touching is fine -- the pin
        must not start inside either zone, or there is nothing to do, and the two
        zones must be different colours, or the instruction names both.
        """

        self.target_zone()
        init_deg = float(self.cfg.linkbar.init_angle_deg)
        angles = {name: float(np.rad2deg(self.zone_angle(name))) for name in LINKBAR_ZONES}
        half = float(self.cfg.zones.half_width_deg)
        rail_lo = float(self.cfg.rail.start_deg)
        rail_hi = float(self.cfg.rail.end_deg)
        keep_out = half + float(self.cfg.zones.pin_start_margin_deg)

        if not rail_lo <= init_deg <= rail_hi:
            raise ValueError(
                f"The beam's initial angle {init_deg:.1f} deg is off the rail "
                f"[{rail_lo:.1f}, {rail_hi:.1f}] deg."
            )
        for name, angle in angles.items():
            if not rail_lo + half <= angle <= rail_hi - half:
                raise ValueError(
                    f"Zone {name} at {angle:.1f} deg (+/-{half:.1f}) is not wholly on "
                    f"the rail [{rail_lo:.1f}, {rail_hi:.1f}] deg; beyond its ends the "
                    "knob leaves the arm's working area."
                )
            if abs(angle - init_deg) < keep_out:
                raise ValueError(
                    f"Zone {name} at {angle:.1f} deg is within {keep_out:.1f} deg of the "
                    f"beam's initial angle {init_deg:.1f} deg: the pin would start on "
                    "it, and there would be nothing to do."
                )
        separation = abs(angles["color_1"] - angles["color_2"])
        if separation < 2.0 * half:
            raise ValueError(
                f"The two zones are {separation:.1f} deg apart, but each spans "
                f"+/-{half:.1f} deg; they need at least {2.0 * half:.1f} deg between "
                "centres so the pin can never be on both."
            )
        # Two colours, not one. The instruction names a colour and `goal_id` is a
        # colour index, so two zones sharing a paint would leave both the sentence
        # and the integer pointing at two places at once, and `zone_for_colour`
        # with nothing to choose between them. The yaml's `distinct_choice` draws
        # without replacement, so this only fires on a hand-written layout.
        if self.zone_color_name("color_1") == self.zone_color_name("color_2"):
            raise ValueError(
                "Both zones are painted "
                f"{self.zone_color_name('color_1')!r}; the instruction would name both."
            )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``: turns the
    sampled ``linkbar.init_frac`` into ``linkbar.init_angle_deg`` on the set the
    drawn zones leave free. A ``ValueError`` (empty set) rejects the draw.
    """

    layout = LinkbarRotateLayout(task_cfg)
    task_cfg.linkbar.init_angle_deg = layout.init_angle_from_frac(
        float(task_cfg.linkbar.init_frac)
    )


def render_instruction(task_cfg) -> str:
    """Instruction hook named by the task yaml's ``goal.instruction_fn``.

    The sentence is assembled at read time rather than written into a leaf:
    `derive_task_cfg` may only write scalar, space-free leaves (a sentence cannot
    ride the corner sweep's Hydra overrides), so the yaml holds the template and
    this fills it.
    """

    return LinkbarRotateLayout(task_cfg).instruction()


def render_goal_id(task_cfg) -> int:
    """Goal-id hook named by the task yaml's ``goal.goal_id_fn``.

    The same fact as `render_instruction` in the form a policy with no language
    input can take: which colour the sentence names, as an index into
    ``zones.colors``. See `LinkbarRotateLayout.goal_id`.
    """

    return LinkbarRotateLayout(task_cfg).goal_id()


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    LinkbarRotateLayout(task_cfg).validate()


@dataclass
class LinkbarRotateScene:
    scene: Any
    manifest: EntityManifest
    layout: LinkbarRotateLayout
    joint_name: str = "linkbar_joint"
    joint_dof: int = 0
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    # ----------------------------------------------------------- entity access

    def linkbar_entity(self):
        return self.manifest.get("linkbar")

    # ------------------------------------------------------------------ joint

    def arm_angle(self) -> float:
        value = self.linkbar_entity().get_dofs_position(dofs_idx_local=[int(self.joint_dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    def arm_velocity(self) -> float:
        """Joint angular velocity, rad/s. The "has it stopped" reading."""

        value = self.linkbar_entity().get_dofs_velocity(dofs_idx_local=[int(self.joint_dof)])
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

    def pin_zone(self) -> str | None:
        """Which zone the pin is on right now, or None."""

        return self.layout.zone_at(self.arm_angle())

    def beam_link_idx(self) -> int:
        """Global link index of the rotating link."""

        return int(self.linkbar_entity().get_link(name="hinge_arm").idx)

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
            links = getattr(entity, "links", None) or ()
            for link in links:
                # A multi-link entity is named down to the link: "robot" says the arm
                # touched something, "robot/panda_hand" says which part of it did, and
                # only the second one tells a wrist sweep from a finger brush.
                label = name if len(links) == 1 else f"{name}/{getattr(link, 'name', link.idx)}"
                owners[int(link.idx)] = label
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


class LinkbarRotateSceneBuilder:
    """Build the common table plus the pivot column, the hinged beam and the two zones."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> LinkbarRotateScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = LinkbarRotateLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        layout.validate()

        self._add_pivot_column(scene, manifest, layout)
        entity, joint_name = self._add_linkbar(scene, manifest, layout)
        self._add_zones(scene, manifest, layout)
        self._add_rail(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        rotate_scene = LinkbarRotateScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            joint_name=joint_name,
            joint_dof=hinge_joint_dof(entity, joint_name),
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )
        rotate_scene.set_arm_angle(layout.init_angle)
        return rotate_scene

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

    # ----------------------------------------------------------- pivot column

    def _add_pivot_column(self, scene, manifest, layout) -> None:
        """The fixed column the beam turns on. The whole of the fixed structure."""

        column = self.task_cfg.pivot_column
        manifest.add(
            "pivot_column",
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
                name="pivot_column",
            ),
        )

    # ---------------------------------------------------------------- linkbar

    def _add_linkbar(self, scene, manifest, layout) -> tuple[Any, str]:
        """The connecting beam: axle, hub, beam, end pin and knob on one rotating link.

        One link, because they are one part. The joint is CONTINUOUS and has no
        limits: with two zones on the circle a limit could only ever describe one of
        them, and "turn until it stops" would remove the aiming this task is about.

        The pin, its collar and the knob's cap take the shaft's grey (2026-09-09).
        They are the three places a marker colour used to go -- the pin is the
        smallest part on the beam and sits under it, so the collar and cap put the
        same colour where the oblique and wrist cameras can see it -- which is
        exactly why none of them may carry one now. Grey, and not a colour of their
        own, because the beam must offer a policy nothing to track: no part of it
        should look like it was painted to be read.
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
        hardware = _list(bar.axle.color)

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
                color=hardware,
            ),
            # A collar where the pin passes through the beam: it is what makes the
            # pin read as a separate hardened part rather than as a spigot.
            HingeShape(
                kind="cylinder",
                size=(float(pin.collar_radius), float(pin.collar_height)),
                origin=(radius, 0.0, layout.beam_top_z + 0.5 * float(pin.collar_height)),
                color=hardware,
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
                color=hardware,
                collide=False,
            ),
        ]

        asset_root = resolve_mesh_dir("runs/generated_meshes/linkbar_rotate_to_zone")
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

    # ------------------------------------------------------------------ zones

    def _add_zones(self, scene, manifest, layout) -> None:
        """Two coloured bands on the table, one across each zone's span of the circle.

        A band does not enclose the zone -- it MARKS it. The zone is the whole
        sector `half_width_deg` either side of the band's centre angle, which is
        exactly the window the verifier tests; the band is the part of that sector
        painted on the table, laid across the circle the pin travels on so that a
        viewer can see where the sector is. The instruction says as much ("the
        sector marked by the red band"), because radius is not a degree of freedom
        here: the pin is fixed to the beam at `arm_radius`, so being inside the
        sector and being over the band are the same event.

        Each band is a run of flat boxes along the arc, `radial_width` across it.
        Visual only (`collision=False`): the pin hangs 52 mm above the table and
        never touches them, and switching them off must not move a single contact.
        Both bands come from this one loop, so they are the same part in everything
        but colour.
        """

        zones = self.task_cfg.zones
        segments = max(1, int(zones.segments))
        half = layout.zone_half_width
        span = 2.0 * half / segments
        # Chord of one segment, plus a hair so neighbouring boxes overlap rather
        # than leave a seam.
        length = 2.0 * layout.arm_radius * np.sin(0.5 * span) + 0.0005
        # `_box` yaws the box by the segment's own angle, which puts the box's
        # FIRST size component along the radius and the second along the tangent
        # (the rail's ticks use the same convention). So the radial width comes
        # first and the chord second. Until 2026-09-10 these two were the other
        # way round, which drew each band 7.2 mm across the circle instead of 40
        # and stretched it to +/-13.71 deg instead of +/-8: the paint claimed a
        # sector nearly twice the one the judge reads, and was narrower than the
        # 20 mm pin, so a viewer could not tell the verdict from the frame.
        size = (float(zones.radial_width), length, float(zones.thickness))
        z = float(zones.z_offset)
        for zone in LINKBAR_ZONES:
            color = layout.zone_color(zone)
            centre = layout.zone_angle(zone)
            for index in range(segments):
                angle = centre - half + span * (index + 0.5)
                xy = layout.pin_center_xy(angle)
                self._box(
                    scene, manifest, f"zone_{zone}_{index:02d}",
                    layout.position_to_world((xy[0], xy[1], z)),
                    size, color,
                    role="marker",
                    yaw_deg=float(np.rad2deg(angle)),
                    collision=False,
                )

    # ----------------------------------------------------------------- rail

    def _add_rail(self, scene, manifest, layout) -> None:
        """Dashes on the table along a fixed span of the pin's circle.

        The dashed circle in docx 4.4's figure, drawn for the same reason: it is
        what shows that both zones are reached by the same turn. The span is fixed
        by config, not by where the zones happen to be. A dash whose centre falls
        inside a zone's span is skipped: the painted block covers that stretch, and
        two markers at one height would fight for the pixel. Visual only.
        """

        rail = self.task_cfg.rail
        if not bool(rail.enabled):
            return
        segments = int(rail.segments)
        low, high = layout.rail_span()
        for index in range(segments):
            angle = low + (high - low) * (index + 0.5) / segments
            if layout.zone_at(angle) is not None:
                continue
            xy = layout.pin_center_xy(angle)
            self._box(
                scene, manifest, f"rail_tick_{index:02d}",
                layout.position_to_world((xy[0], xy[1], float(rail.z_offset))),
                _list(rail.tick_size),
                rail.color,
                role="marker",
                yaw_deg=float(np.rad2deg(angle)),
                collision=False,
            )
