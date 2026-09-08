"""Cloth Unroll (docx 1.3「展开自身卷曲的布带」): a roll on a bar, pulled flat.

The scene is a washroom paper dispenser: two posts carrying a horizontal bar,
with a cloth band wound twice around the bar, hanging off it and lying on the
table. The gripper takes the flat end and drags it along the table; the roll pays
out material and the band ends up flat, one layer, at its full length.

**Why a dispenser and not docx 1.3's loose roll.** docx has the roll lying on the
table, held by nothing, unrolling as it is pulled. Two measurements say that will
not work here:

- The roll is the heaviest part of the band and touches the table along a line,
  so pulling the free end is at least as likely to tow the whole thing as to
  unroll it. In `cloth_unpleat` the anchor was a long flat run BEYOND the
  feature; a roll at the end of the band has nothing beyond it. The bar replaces
  a friction anchor with a rigid one.
- Nothing holds the roll's shape. Genesis 1.2.1 ignores `bending_compliance`
  entirely -- measured 2026-08-23 across seven orders of magnitude with no change
  in any reading -- so this cloth has no crease stiffness at all, and
  `cloth_unpleat`'s authored pleat lay down inside 25 steps. The bar supports the
  innermost turn, which is the part a free roll has nothing to stand on.

It also settles a material conflict. `cloth_unpleat` raised cloth-against-cloth
friction to 0.4 to stop its three layers coming apart; unrolling needs those
layers to slide over each other, which is the opposite. With the bar there is no
conflict: low friction lets the outer wrap peel off the one beneath it, high
friction turns the whole roll about the bar, and either pays material out.

**The gripper pulls in a straight line and never rotates.** Orbiting the roll
would force the wrist to follow through two full turns, which no arm's last joint
can do in one grasp. Pulling straight puts all of the rotation in the roll, so
the held end keeps its orientation for free -- which is what "the gripper's pose
relative to the cloth stays fixed" actually asks for. The travel fits in one
reach, so as shipped that is one continuous stroke; the multi-stroke machinery
below is kept for a larger `turns`, which is the only thing that puts the travel
past what the arm can reach.

Judging lives in `topogym/verification/cloth_unroll_verifier.py`; the strokes live
in `topogym/planning/cloth_unroll_planner.py`; the roll's control mesh comes from
`cloth_profile_mesh.spiral_profile`. This file only says what the scene contains
and where its landmarks are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np

from topogym.core import EntityManifest
from topogym.supervision.pbd_probe import probe_particles
from topogym.tasks._fixtures import HingeShape, add_hinge_mechanism, hinge_joint_dof
from topogym.world import StandardTabletopSceneBuilder, materials, textures
from topogym.world.rope import TabletopParticleFriction

from ._cloth_unroll_geometry import (
    along_leaf,
    center_along_from_frac,
    cloth_unroll_checks,
    hang_height,
    pitch_from_frac,
    pull_sign,
    spool_angle,
    spool_cfg,
    spool_plan,
    start_spread_limit,
    tail_radius,
    taut_length,
    taut_reach,
)
from .cloth_fold import remesh_report
from .cloth_profile_mesh import (
    edge_report,
    resample_polyline,
    spiral_landmarks,
    spiral_profile,
    sweep_profile_mesh,
    texture_size_m,
)


@dataclass
class ClothUnrollLayout:
    """Where the dispenser is and where the band's landmarks are, in world metres."""

    task_cfg: Any
    #: World position of the task frame's origin. Zero when the layout is built
    #: from the task config alone (offline gate, corner harness): every
    #: feasibility row is task-frame arithmetic and never needs it.
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    _profile: np.ndarray | None = field(default=None, init=False, repr=False)
    #: The free end as measured after settling, and again after every stroke.
    _grasp: np.ndarray | None = field(default=None, init=False, repr=False)

    def coordinate_frame(self) -> str:
        return str(self.task_cfg.coordinate_frame)

    @property
    def material_axis(self) -> int:
        """World axis the band pays out along: 0 for x, 1 for y.

        The bar runs along the OTHER horizontal axis, so this also fixes the
        dispenser's orientation. y as shipped, which puts the bar along x and the
        band paying out toward the arm -- the same axis `cloth_unpleat` pulls
        along, and the one its reach was measured on.
        """

        axis = str(self.task_cfg.cloth.material_axis).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        return 0 if axis == "x" else 1

    @property
    def bar_axis(self) -> int:
        """The horizontal axis the bar runs along, which the band's width follows."""

        return 1 - self.material_axis

    @property
    def pull_sign(self) -> float:
        """+1 when the band leaves the roll toward +axis and is pulled that way, -1 mirrored.

        `cloth.pull_side: -1` is the mirror layout: the profile is reflected in
        the band's own axis, the flat run lies on the negative side of the bar
        and the pull runs toward negative coordinates. The profile and its
        landmarks stay unsigned (they are lengths); the sign is applied where a
        material offset becomes a point (`_plan_point`), in `pull_direction`,
        in `observe` and when the mesh is swept.
        """

        return pull_sign(self.task_cfg)

    @property
    def table_z(self) -> float:
        return float(self.origin[2])

    def world_z(self, z: float) -> float:
        return float(self.origin[2]) + float(z)

    def rest_z(self) -> float:
        return self.world_z(float(self.task_cfg.cloth.z))

    def bar_centre(self) -> np.ndarray:
        """World (x, y) of the bar's axis. Every profile offset is from here."""

        cloth = self.task_cfg.cloth
        return np.asarray(self.origin, dtype=float)[:2] + np.array(
            [float(cloth.center_x), float(cloth.center_y)], dtype=float
        )

    def bar_height(self) -> float:
        return self.world_z(float(self.task_cfg.dispenser.bar_height))

    def _plan_point(self, material: float, height: float) -> np.ndarray:
        """A world point from a (material-offset, height) pair on the band's axes.

        ``material`` is an unsigned offset from the bar's axis; the mirror
        layout puts it on the other side.
        """

        centre = self.bar_centre()
        point = np.zeros(3, dtype=float)
        point[self.material_axis] = centre[self.material_axis] + self.pull_sign * float(material)
        point[self.bar_axis] = centre[self.bar_axis]
        point[2] = self.world_z(height)
        return point

    def profile(self) -> np.ndarray:
        if self._profile is None:
            cloth = self.task_cfg.cloth
            dispenser = self.task_cfg.dispenser
            self._profile = spiral_profile(
                material_length=float(cloth.material_length),
                bar_radius=float(dispenser.bar_radius),
                clearance=float(cloth.roll.clearance),
                pitch=float(cloth.roll.pitch),
                turns=float(cloth.roll.turns),
                bar_height=float(dispenser.bar_height),
                rest_z=float(cloth.z),
                spacing=float(cloth.mesh.spacing),
            )
        return self._profile

    def landmarks(self) -> dict:
        return spiral_landmarks(
            self.profile(),
            bar_height=float(self.task_cfg.dispenser.bar_height),
            rest_z=float(self.task_cfg.cloth.z),
        )

    def tail_point(self) -> np.ndarray:
        """World position of the glued tail's outer end once the roll is paid out.

        The inner `spool.anchor_arc` of band stays glued to the spool (real
        dispensers fix the last turn to the core too). When the spool has
        turned the whole roll out, that glued arc's outer end -- the point the
        free band leaves from -- sits at the exit direction, `tail_radius` from
        the axis, level with it. Everything the oracle and the tear rule
        measure runs from here.
        """

        return self._plan_point(tail_radius(self.task_cfg), float(self.task_cfg.dispenser.bar_height))

    def taut_end_point(self) -> np.ndarray:
        """Where the grasp point sits when the band is straight from the tail with `pull_slack` to spare.

        The band between the tail's end and the grasp is `taut_length`; from
        `hang_height` up, a straight band of that length minus the slack reaches
        `taut_reach` along the table. This is the oracle's end point: pulled
        further the band is taut, `tear_allowance` further the glue lets go.
        """

        cfg = self.task_cfg
        return self._plan_point(
            tail_radius(cfg) + taut_reach(cfg, spool_cfg(cfg)["pull_slack"]), float(cfg.cloth.z)
        )

    def material_length(self) -> float:
        return float(self.task_cfg.cloth.material_length)

    def rolled_length(self) -> float:
        """Material wound on the bar. The pull has to pay out exactly this."""

        return float(self.landmarks()["rolled"])

    # ------------------------------------------------------------------ grasp

    def design_grasp_point(self) -> np.ndarray:
        """Where the mesh puts the band's free end, inset for the disc."""

        marks = self.landmarks()
        end = marks["free_end_s"] - float(self.task_cfg.grasp.edge_inset)
        return self._plan_point(end, float(self.task_cfg.cloth.z))

    def grasp_point(self) -> np.ndarray:
        """The free end: observed once settled, design before."""

        return self._grasp if self._grasp is not None else self.design_grasp_point()

    def observe(self, nodes) -> np.ndarray:
        """Find the band's current free end and use it until the next call.

        Called before EVERY stroke, not just the first. The end moves the length
        of each pull, so a stroke planned from the previous stroke's grasp point
        reaches into cloth that has already gone past -- and reaching for a
        position the cloth has left is how `cloth_unpleat`'s first run failed.

        Taken as the material furthest along the pay-out axis, on the band's
        centre line, then pulled back in by `edge_inset`. Restricted to material
        lying on the table so the roll itself can never be mistaken for the end.
        """

        nodes = np.asarray(nodes, dtype=float)
        centre = self.bar_centre()
        material, across = self.material_axis, self.bar_axis
        band = float(self.task_cfg.grasp.attach_radius)
        flat = self.rest_z() + 2.0 * float(self.task_cfg.cloth.particle_size)
        near = np.flatnonzero(
            (np.abs(nodes[:, across] - centre[across]) <= band) & (nodes[:, 2] <= flat)
        )
        if near.size == 0:
            raise ValueError(
                f"no material lying on the table within {band:.3f} m of the band's "
                f"centre line at {centre[across]:+.4f}; nothing to grasp."
            )
        sign = self.pull_sign
        along = nodes[near, material]
        end = float(along.max() if sign > 0 else along.min())
        point = self._plan_point(0.0, float(self.task_cfg.cloth.z))
        point[material] = end - sign * float(self.task_cfg.grasp.edge_inset)
        # Height of the material AT the grasp, not the highest particle anywhere
        # on the centre line. Those differ, and the second one is useless: the
        # `flat` filter above is an upper bound, so its max is that bound
        # whenever ANY particle in the strip is near it. Measured 2026-08-24:
        # the grasp came back at 0.9295 against a ceiling of 0.9296 while the
        # band rested at 0.9216 -- 7.9 mm high, nearly the whole
        # `touch_clearance`. `attach_radius` covered for it, but the pads were
        # descending to the wrong place.
        at = near[
            np.abs(nodes[near, material] - point[material])
            <= float(self.task_cfg.grasp.attach_radius)
        ]
        point[2] = float(nodes[at, 2].max()) if at.size else self.rest_z()
        self._grasp = point
        return self._grasp

    # ------------------------------------------------------------------ pull

    def pull_direction(self) -> np.ndarray:
        """Unit vector the hand pulls along: away from the bar, in plane."""

        direction = np.zeros(3, dtype=float)
        direction[self.material_axis] = self.pull_sign
        return direction

    def pull_total(self) -> float:
        """Total travel: from the grasp point (observed once settled) to `taut_end_point`.

        Until 2026-09-06 this was ``flat_travel x pull_scale`` -- the free end's
        travel for a band that ends up flat on the table with its inner end
        dropped from the bar, plus a measured overshoot for where that end
        actually landed. With the tail glued to the spool the end of the pull is
        a geometric fact instead: the band runs straight from the tail's end to
        the grasp, and the hand stops `pull_slack` short of taut.
        """

        end = self.taut_end_point()
        return float(self.pull_sign * (end[self.material_axis] - self.grasp_point()[self.material_axis]))

    def final_grasp_position(self) -> float:
        """Where the hand finishes, along the pay-out axis.

        Worth having as its own reading because of what it does NOT depend on.
        The finish is

            centre + tail_radius + sqrt((material - anchor_arc - edge_inset - pull_slack)^2 - hang^2)

        so the roll's pitch and turn count cancel completely (they only move
        `tail_radius` by a few millimetres): winding tighter or adding a turn
        changes where the pull STARTS, never where it ends. The dispenser's
        position and height, the material's length and the grasp inset are the
        levers when the finish is out of the arm's reach.
        """

        return float(self.final_grasp_point()[self.material_axis])

    def stroke_count(self) -> int:
        """How many grasps the travel is split into.

        `stroke_m` is a CEILING on one stroke, not its length, and the shipped
        config sets it ABOVE the total so there is exactly one continuous stroke.

        Splitting is not a reach device and it is worth saying so, because that is
        what it was mistaken for until 2026-08-24: the hand ends up at the start
        plus the TOTAL however the travel is cut, so cutting it buys nothing in
        reach and costs a release-retreat-reapproach-regrasp cycle per cut. What
        splitting is for is a single stroke's tracking residual, and the machinery
        earns its place when a larger `turns` pushes the travel past what the arm
        can reach at all.

        When it does split, it splits EVENLY rather than taking full-length
        strokes and a short remainder -- a remainder left for last lands exactly
        where the arm is weakest.
        """

        return max(1, int(np.ceil(self.pull_total() / float(self.task_cfg.physical.stroke_m))))

    def stroke_distance(self) -> float:
        """How far one grasp pulls: the total, divided evenly."""

        return self.pull_total() / self.stroke_count()

    def final_grasp_point(self) -> np.ndarray:
        """Where the hand ends up after the last stroke.

        Exposed so the offline check can assert it against the arm's measured
        envelope rather than trusting the arithmetic in a comment.
        """

        return self.taut_end_point()

    def stroke_steps(self) -> int:
        """Steps for one stroke, from the calibrated hand SPEED, as in 1.2."""

        return max(
            4,
            int(round(self.stroke_distance() / float(self.task_cfg.physical.pull_step_m))),
        )

    def grasp_yaw(self) -> float | None:
        """Which way the wrist faces, or None to leave the arm's own orientation.

        Same knob and the same reason as `cloth_unpleat`: which setting the arm
        can hold out at the end of a pull is a measured question, and holding an
        orientation it cannot quite reach costs position silently.
        """

        mode = str(self.task_cfg.grasp.finger_axis)
        if mode == "arm_default":
            return None
        direction = self.pull_direction()
        yaw = float(np.arctan2(direction[1], direction[0]))
        if mode == "across":
            return yaw
        if mode == "along":
            return yaw + 0.5 * float(np.pi)
        raise ValueError(
            f"grasp.finger_axis must be 'across', 'along' or 'arm_default', "
            f"got {mode!r}."
        )

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres; task frame.
        """

        return cloth_unroll_checks(self.task_cfg)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"cloth_unroll layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )

    def summary(self) -> str:
        marks = self.landmarks()
        grasp = self.grasp_point()
        return (
            f"axis={'xy'[self.material_axis]} side={self.pull_sign:+.0f} "
            f"bar=({self.bar_centre()[0]:+.3f},{self.bar_centre()[1]:+.3f},"
            f"{self.bar_height():.3f}) "
            f"grasp=({grasp[0]:+.3f},{grasp[1]:+.3f},{grasp[2]:+.3f}) "
            f"material_mm={marks['material_length'] * 1e3:.0f} "
            f"rolled_mm={marks['rolled'] * 1e3:.1f} "
            f"roll_dia_mm={2 * marks['roll_radius'] * 1e3:.1f} "
            f"flat_run_mm={marks['flat_run'] * 1e3:.1f} "
            f"plan_span_mm={marks['plan_span'] * 1e3:.1f} "
            f"stored_mm={marks['stored'] * 1e3:.1f} "
            f"strokes={self.stroke_count()}x{self.stroke_distance() * 1e3:.0f}mm "
            f"steps_per_stroke={self.stroke_steps()}"
        )


@dataclass
class ClothUnrollScene:
    scene: Any
    manifest: EntityManifest
    cameras: dict[str, Any]
    frames: Any
    layout: ClothUnrollLayout
    cloth: Any
    control_vertices: np.ndarray
    grid: tuple[int, int]
    table_friction: Any = None
    rest_nodes: np.ndarray | None = field(default=None)
    #: The spool (the bar as a hinge entity) and its joint's name; `Spool`
    #: resolves the link and dof once the scene is built.
    bar_entity: Any = None
    bar_joint: str = ""


def band_particles(band: ClothUnrollScene) -> np.ndarray:
    """Current ``(P, 3)`` particle positions of the band."""

    return probe_particles(band.cloth)


def settle_band(band: ClothUnrollScene, steps: int) -> np.ndarray:
    """Let the band settle onto the bar and the table, then record the rest state.

    Load-bearing here for the same reason as in `cloth_unpleat`: the roll is
    authored into the mesh rather than wound by anything, so whether it stays on
    the bar at all is decided during this settle. `tests/roll_settle_spike.py`
    asks that question on its own, before any arm exists.
    """

    for _ in range(max(0, int(steps))):
        band.scene.step()
    band.rest_nodes = band_particles(band)
    return band.rest_nodes


def _spool_sense(layout) -> float:
    """+1 or -1: the joint angle per radian of turn measured in the band's profile plane.

    The profile plane has ``m`` (the pull side of the band's axis) as its first
    axis and height as its second; the spool's joint turns about the bar's own
    axis. Rotating the ``m`` direction by a small positive joint angle moves it
    toward +height or toward -height depending on which way the bar's axis and
    the pull direction point, and that is the sign here. Computed, not written:
    the mirror layout (`pull_side` -1) flips it, and the offline gate pins it.
    """

    across = layout.bar_axis
    axis = np.zeros(3, dtype=float)
    axis[across] = 1.0
    e_m = np.asarray(layout.pull_direction(), dtype=float)
    e_z = np.array([0.0, 0.0, 1.0])
    return 1.0 if float(np.dot(np.cross(axis, e_m), e_z)) > 0.0 else -1.0


class Spool:
    """The bar as a spool: the wound band rides on it, it turns as the band is paid out, the tail is glued.

    The scene: the band is wound `turns` times round the bar and leaves it at
    the exit tangent on the pull side, drops to the table and lies flat to the
    free end. Along the band's profile each particle sits at an arc ``a`` from
    the inner end; ``rolled`` is the arc at the exit tangent, ``b = rolled - a``
    the band between a particle and the exit. At birth only the inner
    `anchor_arc` of band -- the glued tail -- is bound to the spool's link
    (`fix_particles_to_link`); the rest of the roll is left to the solver.
    As the hand pulls the free end along the table by ``d``, the band between
    the exit and the hand is taut, so ``d`` of band has passed the exit: the
    spool is turned so that the particle at arc ``rolled - d`` (the peel front)
    sits at the exit direction (`spool_angle`). ``held``, ``remaining`` and
    ``glued`` are the arc bookkeeping the turn and `tear_check` read; only
    ``glued`` says what is actually pinned. The spool stops turning when the
    front reaches the tail, and the pull never frees it.

    Pulled just enough, the band then runs straight from the glued tail's end
    down to the table and flat to the hand (`ClothUnrollLayout.taut_end_point`,
    `pull_slack` short of taut). Pulled past taut by more than
    `tear_allowance`, the glue lets go: `tear_check` frees the tail, which is
    the failure the judge reads as no band left on the bar (`on_bar_min`).

    Why the environment turns the spool: Genesis 1.2.1's PBD-rigid coupling is
    one-way (the bar pushes cloth, cloth never pushes the bar), so the band's
    tension cannot drive a passive spool. The turn is keyed to the length paid
    out, never to time, so the pull speed stays free; a shove (hand toward the
    bar) pays out nothing, turns nothing and frees nothing. Before 2026-09-06
    the bar was fixed and the wound band was pinned in place and peeled
    around it (the "tape"); the last particle freed was the inner end, which
    fell from the bar's height onto the band and folded -- the doubled 40 mm
    every run carried. The glued tail removes that: it never leaves the bar.

    Why only the tail is pinned (2026-09-07): binding the whole wound body as
    well froze it in the analytic spiral, so the roll never settled and read as
    a loose coil floating around the bar. On the tail alone gravity closes the
    turns -- the start state's ``on_bar`` goes 198 -> 537 and ``spread_ratio``
    0.405 -> 0.382, i.e. the roll settles TIGHTER. That is the opposite of the
    2026-08-25 roll, which spread 0.392 -> 0.457 because nothing anchored it at
    all; the tail is what stops the free end's weight peeling the outer turn
    off. The roll still turns with the spool, carried round by the tail through
    cloth-on-cloth contact (Genesis gives no cloth-rigid friction at all --
    `legacy_coupler._func_pbd_collide_with_rigid_geom` leaves its tangential
    block commented out), measured at 84% of the commanded angle with no other
    coupling and 93% with a velocity nudge that was dropped as unnecessary.
    Readings are unchanged: baseline `single_layer_frac` 0.949 against 0.948
    pinned, c002 `recovered_frac` 0.984 against 1.019, c042 0.929 against
    0.934, and both `overpull` and `shove` are still judged failures. The two
    corners that motivated pinning the body pass on the tail alone -- c002 read
    0.56 on 2026-09-06 morning, when there was no glued tail yet.
    """

    def __init__(self, band, layout, nodes, *, lead: float, anchor_arc: float, tear_allowance: float):
        self.cloth = band.cloth
        self.entity = band.bar_entity
        self.link_idx = int(self.entity.get_link(name="hinge_arm").idx)
        self.dof = hinge_joint_dof(self.entity, band.bar_joint)
        self.layout = layout
        self.lead = float(lead)
        self.anchor_arc = float(anchor_arc)
        self.tear_allowance = float(tear_allowance)
        self._direction = np.asarray(layout.pull_direction(), dtype=float)
        self._sense = _spool_sense(layout)
        centre = layout.bar_centre()
        material = layout.material_axis
        nodes = np.asarray(nodes, dtype=float)
        m = layout.pull_sign * (nodes[:, material] - float(centre[material]))
        z = nodes[:, 2] - float(layout.table_z)
        marks = layout.landmarks()
        held, remaining, glued = spool_plan(
            np.stack([m, z], axis=1), layout.profile(), marks, self.lead, self.anchor_arc
        )
        self.held = held
        self.remaining = remaining
        self.glued = glued
        self.rolled = float(marks["rolled"])
        self.taut = taut_length(layout.task_cfg)
        self.hang = hang_height(layout.task_cfg)
        self.tail = layout.tail_point()
        self.released = np.zeros(held.size, dtype=bool)
        self.torn_at = None
        self.angle = 0.0
        self._start = None
        self._paid_before = 0.0
        self._paid = 0.0
        if held.size == 0 or not np.any(glued):
            raise ValueError(
                f"spool holds {held.size} particles, {int(glued.sum())} glued: rolled arc {self.rolled:.4f} m, "
                f"lead {self.lead:.4f}, anchor_arc {self.anchor_arc:.4f}; the band is not on the bar."
            )
        self.cloth.fix_particles_to_link(
            self.link_idx, particles_idx_local=[int(i) for i in held[glued]]
        )

    def begin_stroke(self, hand_pos) -> None:
        """Mark where the hand is as this pull starts; earlier strokes' pay-out is kept."""

        self._paid_before = self._paid
        self._start = np.asarray(hand_pos, dtype=float).copy()

    @property
    def paid_out(self) -> float:
        return float(self._paid)

    @property
    def exhausted(self) -> bool:
        """The peel front has reached the glued tail: nothing wound is left to pay out."""

        return self._paid >= self.rolled - self.anchor_arc - 1e-9

    def advance(self, hand_pos) -> int:
        """Turn the spool and mark the band past the peel front for this hand position. Returns how many are past it, total.

        Nothing is unpinned here: only the glued tail is ever bound to the link,
        and the pull never frees it. ``released`` is the bookkeeping that says
        how much of the roll the front has passed, which `summary` reports and
        `exhausted` reads.
        """

        if self._start is None:
            return int(self.released.sum())
        travel = float(np.dot(np.asarray(hand_pos, dtype=float) - self._start, self._direction))
        self._paid = self._paid_before + max(0.0, travel)
        self.angle = spool_angle(self.layout.task_cfg, self._paid)
        self.entity.set_dofs_position(
            np.array([self._sense * self.angle], dtype=float), dofs_idx_local=[int(self.dof)]
        )
        self.released |= (self.remaining <= self._paid + self.lead) & ~self.glued
        return int(self.released.sum())

    def tear_check(self, hand_pos) -> bool:
        """Let the glued tail go once the hand has pulled the band past taut by `tear_allowance`.

        The band between the tail's end and the grasp is `taut_length`; the
        hand's plan position and the tail's end are `hang_height` apart in
        height, so the band is taut when their distance reaches that length.
        Geometric rather than force-based: the pin cannot break on its own, and
        a distance rule is the same at any pull speed and can be checked offline.
        Returns True on the step the tail is torn off.
        """

        if self.torn_at is not None or not self.exhausted:
            return False
        hand = np.asarray(hand_pos, dtype=float)
        flat = float(np.hypot(hand[0] - self.tail[0], hand[1] - self.tail[1]))
        distance = float(np.hypot(flat, self.hang))
        if distance <= self.taut + self.tear_allowance:
            return False
        tail = self.held[self.glued]
        self.cloth.release_particle(particles_idx_local=[int(i) for i in tail])
        self.released |= self.glued
        self.torn_at = self._paid
        return True

    def summary(self) -> str:
        torn = "no" if self.torn_at is None else f"at_paid_out_mm={self.torn_at * 1e3:.1f}"
        return (
            f"spool held={self.held.size} glued={int(self.glued.sum())} released={int(self.released.sum())} "
            f"paid_out_mm={self._paid * 1e3:.1f} angle_deg={np.degrees(self.angle):+.1f} "
            f"lead_mm={self.lead * 1e3:.1f} rolled_mm={self.rolled * 1e3:.1f} "
            f"taut_mm={self.taut * 1e3:.1f} torn={torn}"
        )


class ClothUnrollSceneBuilder:
    """Standard tabletop, a two-post dispenser, one PBD cloth band wound on it."""

    def __init__(self, env_cfg, task_cfg, robot_cfg) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg

    def build(
        self, *, show_viewer: bool = False, include_robot: bool = True
    ) -> ClothUnrollScene:
        cloth_cfg = self.task_cfg.cloth
        # Solver iteration counts, when the config asks for them.
        #
        # PBD does not guarantee zero penetration: each substep PREDICTS a
        # position from velocity and gravity, then ITERATES corrections toward
        # the constraints -- stretch, bending, and contact with rigid bodies.
        # Those corrections fight each other, the iteration budget is finite, and
        # what is left over is a residual. IPC is different in kind: contact is a
        # barrier energy that goes to infinity as the gap closes, so a
        # penetrating state is unreachable rather than merely discouraged.
        #
        # The residual is therefore bounded by the iteration budget, and the rope
        # path has always set it (16/12/6 in the prefab) while every cloth task
        # has run on whatever Genesis defaults to. Left absent here so nothing
        # changes until a sweep says what to use.
        pbd_cfg = getattr(cloth_cfg, "pbd", None)
        iterations = (
            {}
            if pbd_cfg is None
            else {
                key: int(getattr(pbd_cfg, key))
                for key in (
                    "max_stretch_solver_iterations",
                    "max_bending_solver_iterations",
                    "max_volume_solver_iterations",
                )
                if getattr(pbd_cfg, key, None) is not None
            }
        )
        if iterations:
            print(f"cloth_unroll pbd_iterations {iterations}", flush=True)
        builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            pbd_options=gs.options.PBDOptions(
                particle_size=float(cloth_cfg.particle_size), **iterations
            ),
        )
        tabletop = builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            # The arm is outside the soft-body coupler, as it is in every rope
            # task (`ring_transfer.py:215`, `closed_band_spike.py:318`). All
            # manipulation here goes through the kinematic bind, so finger
            # contact carries no signal -- and with the coupler on it carried
            # the OPPOSITE of signal: the pads pressed cloth through the table
            # and the bind froze it there.
            #
            # PBD's stable standoff is 5-9 mm (measured 2026-08-25) while a real
            # pinch on a 2 mm sheet needs the pads at the surface, so no clearance
            # exists that is both penetration-free and reachable on hardware.
            # Leaving the coupler on forces that choice; taking the arm out of it
            # removes the choice.
            #
            # The cost is that nothing stops the arm passing THROUGH the cloth:
            # trajectory correctness is now the script's job, not the solver's.
            robot_material=gs.materials.Rigid(needs_coup=False),
        )
        scene = tabletop.scene
        layout = ClothUnrollLayout(
            self.task_cfg, np.asarray(tabletop.frames.task_origin, dtype=float)
        )
        _assert_literal_copies(self.task_cfg)
        layout.validate()

        bar_entity, bar_joint = self._add_dispenser(scene, tabletop.manifest, layout)

        spacing = float(cloth_cfg.mesh.spacing)
        samples = resample_polyline(layout.profile(), spacing)
        # The mirror layout: reflect the material offset about the bar's axis.
        # Material ORDER is kept (index 0 is still the inner end on the bar), so
        # the mesh's column order and every reading that walks it are unchanged.
        samples[:, 0] *= layout.pull_sign
        path = Path(str(cloth_cfg.mesh.output_dir)) / "cloth_unroll_band.obj"
        vertices, _faces, cols, rows = sweep_profile_mesh(
            samples,
            width=float(cloth_cfg.width),
            spacing=spacing,
            centre=layout.bar_centre(),
            table_z=layout.table_z,
            path=path,
            material_axis=layout.material_axis,
        )
        cloth = scene.add_entity(
            gs.morphs.Mesh(
                file=str(path),
                pos=(0.0, 0.0, 0.0),
                scale=1.0,
                decimate=False,
                convexify=False,
                fixed=False,
                file_meshes_are_zup=True,
            ),
            material=gs.materials.PBD.Cloth(
                rho=float(cloth_cfg.rho),
                static_friction=float(cloth_cfg.static_friction),
                kinetic_friction=float(cloth_cfg.kinetic_friction),
                stretch_compliance=float(cloth_cfg.stretch_compliance),
                bending_compliance=float(cloth_cfg.bending_compliance),
                stretch_relaxation=float(cloth_cfg.stretch_relaxation),
                bending_relaxation=float(cloth_cfg.bending_relaxation),
                air_resistance=float(cloth_cfg.air_resistance),
            ),
            surface=self._cloth_surface(cloth_cfg),
            name=str(cloth_cfg.name),
        )
        tabletop.manifest.add(str(cloth_cfg.name), cloth)
        builder.finalize(tabletop)

        band = ClothUnrollScene(
            scene=scene,
            manifest=tabletop.manifest,
            cameras=tabletop.cameras,
            frames=tabletop.frames,
            layout=layout,
            cloth=cloth,
            control_vertices=vertices,
            grid=(cols, rows),
            table_friction=self._install_table_friction(scene, cloth, layout),
            bar_entity=bar_entity,
            bar_joint=bar_joint,
        )

        print(
            f"cloth_unroll scene particles={len(band_particles(band))} "
            f"{remesh_report(vertices, band_particles(band))} "
            f"{edge_report(vertices, cols, rows)} "
            f"{layout.summary()}",
            flush=True,
        )
        return band

    def _add_dispenser(self, scene, manifest: EntityManifest, layout) -> tuple[Any, str]:
        """Two fixed posts and the spool between them; returns ``(bar entity, joint name)``.

        The bar is the task's anchor: it is what makes the pull unroll the band
        instead of towing it, and what holds the innermost turn up. The posts do
        one job beyond holding the bar -- they stop the roll sliding off along the
        bar's axis, which a band with a free inner end can otherwise do.

        Plain cylinders rather than the flared `routing_post_mesh`: that shape
        exists because a post meeting the table at a right angle ejected rope
        being dragged against it, and nothing here is dragged along the posts.
        """

        cfg = self.task_cfg.dispenser
        centre = layout.bar_centre()
        across, along = layout.bar_axis, layout.material_axis
        half = 0.5 * float(cfg.span)

        for side in (-1.0, 1.0):
            pos = np.zeros(3, dtype=float)
            pos[across] = centre[across] + side * half
            pos[along] = centre[along]
            pos[2] = layout.table_z + 0.5 * float(cfg.post_height)
            post = scene.add_entity(
                gs.morphs.Cylinder(
                    pos=tuple(float(v) for v in pos),
                    radius=float(cfg.post_radius),
                    height=float(cfg.post_height),
                    fixed=True,
                    collision=True,
                ),
                surface=materials.plastic("fixture", list(cfg.color), vis_mode="visual"),
                name=f"{cfg.name}_post_{'lo' if side < 0 else 'hi'}",
            )
            manifest.add(f"{cfg.name}_post_{'lo' if side < 0 else 'hi'}", post)

        # The bar is a spool (2026-09-06): a hinge entity with one continuous
        # joint on its own axis, turned by `Spool` as the band is paid out. A
        # URDF cylinder stands on its local z, so it is rolled a quarter turn to
        # lie along the posts' axis: `(0, 90, 0)` sends it to world x, `(90, 0, 0)`
        # to world y. The joint axis is that same direction.
        axis = np.zeros(3, dtype=float)
        axis[across] = 1.0
        rpy = (0.0, 0.5 * np.pi, 0.0) if across == 0 else (0.5 * np.pi, 0.0, 0.0)
        bar_pos = np.zeros(3, dtype=float)
        bar_pos[across] = centre[across]
        bar_pos[along] = centre[along]
        bar_pos[2] = layout.bar_height()
        return add_hinge_mechanism(
            scene,
            manifest,
            name=f"{cfg.name}_bar",
            urdf_path=Path(str(self.task_cfg.cloth.mesh.output_dir)) / "cloth_unroll_bar.urdf",
            world_pos=bar_pos,
            axis=axis,
            shapes=[
                HingeShape(
                    "cylinder",
                    (float(cfg.bar_radius), float(cfg.span)),
                    rpy=rpy,
                    color=list(cfg.bar_color),
                )
            ],
            mass=float(cfg.get("bar_mass", 0.02)),
            color=list(cfg.bar_color),
            joint_name="spool_joint",
            damping=0.0,
            friction=0.0,
        )

    def _cloth_surface(self, cloth_cfg):
        """The band's surface, with a woven diffuse image when one is asked for.

        Same reasoning as `cloth_fold` and `cloth_unpleat`: the rasterizer keeps a
        surface's diffuse colour and texture and drops everything else. ``size_m``
        comes from `texture_size_m` so the stripes stay across the material and
        the roll's turns read as separate layers on camera.
        """

        texture_cfg = getattr(cloth_cfg, "texture", None)
        image = None
        if texture_cfg is not None and bool(texture_cfg.enabled):
            image = textures.fabric_weave(
                color=list(cloth_cfg.color),
                size_m=texture_size_m(
                    float(cloth_cfg.material_length), float(cloth_cfg.width)
                ),
                pattern=str(texture_cfg.pattern),
                accent_color=list(texture_cfg.accent_color),
                stripe_pitch_m=float(texture_cfg.stripe_pitch),
                thread_pitch_m=float(texture_cfg.thread_pitch),
                pixels_per_thread=int(texture_cfg.pixels_per_thread),
                thread_shading=float(texture_cfg.thread_shading),
                weft_tint=float(texture_cfg.weft_tint),
                fibre_noise=float(texture_cfg.fibre_noise),
                cloud_noise=float(texture_cfg.cloud_noise),
                seed=int(texture_cfg.seed),
            )
        # "visual" skins the ORIGINAL swept mesh onto the simulated particles
        # through a binding map. That map is the suspect for the band rendering
        # torn while every particle reading is healthy: the roll is born as a
        # spiral whose turns sit `roll.pitch` apart (4.5 mm) while the solver's
        # own particle spacing is 3.7 mm (measured 2026-08-25), so a vertex on
        # one turn is barely further from the NEXT turn than from its own
        # neighbours. Cross-bound vertices get dragged across the sheet as the
        # band pays out. "particle" draws the solver state directly, with no map
        # in between, which is the diagnostic that separates the two.
        surface = materials.plastic(
            "deformable",
            list(cloth_cfg.color),
            vis_mode=str(getattr(cloth_cfg, "vis_mode", "visual") or "visual"),
            texture=image,
        )
        if image is not None:
            print(
                "cloth_unroll texture "
                f"{materials.texture_reaches_renderer(surface)} "
                f"thread_pitch_mm={float(texture_cfg.thread_pitch) * 1e3:.1f}",
                flush=True,
            )
        return surface

    def _install_table_friction(self, scene, cloth, layout: ClothUnrollLayout):
        """Cloth against the table: friction, and here also the normal constraint.

        The tangential half matters less than in `cloth_unpleat` -- the bar is
        the anchor, not the table -- but the paid-out band still has to stay
        where it is put rather than sliding back.

        There is no normal half. The band DOES sink into the table -- Genesis'
        PBD contact is not a barrier -- and the one thing this module could do
        about it was measured on 2026-08-24 to leave the penetration unchanged
        while making the band billow. See `TabletopParticleFriction`'s docstring.

        Two other routes were ruled out the same day. Raising the PBD solver's
        `lower_bound` to the table would not clamp a sinking particle, it would
        PARK it at the domain corner (100, 100, 100) and drag its triangles
        across the scene -- see `supervision/pbd_probe.py`. And a rigid riser
        that lifts the cloth clear of the visible table hides the dip rather
        than fixing it, at the cost of a floating band.
        """

        friction_cfg = getattr(self.task_cfg.cloth, "tabletop_friction", None)
        if friction_cfg is None or not bool(friction_cfg.enabled):
            return None
        return TabletopParticleFriction(
            scene,
            [cloth],
            surface_z=layout.table_z,
            contact_band=float(friction_cfg.contact_band),
            static_mu=float(friction_cfg.static_mu),
            kinetic_mu=float(friction_cfg.kinetic_mu),
            dt=float(self.env_cfg.sim.dt),
            gravity=abs(float(self.env_cfg.sim.gravity[2])),
            max_load_factor=float(friction_cfg.max_load_factor),
        ).install()


def _assert_literal_copies(task_cfg) -> None:
    """The yaml's literal copy of the workspace box must still match `common`.

    `checks()` reads `workspace.x / y`, and the variation harness loads the task
    yaml alone, where `${common...}` cannot resolve -- so the task yaml carries
    literals, and the one place with both in hand asserts they agree.
    """

    root = task_cfg._get_root() if hasattr(task_cfg, "_get_root") else None
    common = getattr(root, "common", None) if root is not None else None
    if common is None:
        return
    ws = common.manipulation_space.workspace
    for axis in ("x", "y"):
        want = [float(v) for v in ws[axis]]
        got = [float(v) for v in task_cfg.workspace[axis]]
        if want != got:
            raise ValueError(
                f"cloth_unroll: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
            )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Order
    matters: the layer pitch first (its window needs the drawn turns and bar
    height), then the bar's along-axis position (its window needs the flat
    run and the pull the pitch fixes), then the start-state guard (the
    designed spread depends on the pitch). A ``ValueError`` (empty window)
    rejects the draw. Plain floats are written: OmegaConf refuses numpy scalars.
    """

    task_cfg.cloth.roll.pitch = pitch_from_frac(task_cfg, float(task_cfg.cloth.roll.pitch_frac))
    leaf = along_leaf(task_cfg)
    task_cfg.cloth[leaf] = center_along_from_frac(task_cfg, float(task_cfg.cloth[f"{leaf}_frac"]))
    task_cfg.grasp.max_start_spread_ratio = start_spread_limit(task_cfg)


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block."""

    ClothUnrollLayout(task_cfg).validate()
