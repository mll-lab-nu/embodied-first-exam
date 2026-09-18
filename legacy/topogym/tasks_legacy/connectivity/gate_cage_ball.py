"""Gate Cage Ball (docx 4.1): drop a gate into a chute and trap the rolling ball.

Scene: a straight walled channel lying along y, a ball that rolls into it from a
feed ramp outside, and a gate plate the robot slides down a pair of guide posts to
close the only opening. The robot never touches the ball -- the state change is on
the BALL's free space, not on any body the gripper holds.

**The two ends are deliberately different, and the task does not exist without
that.** Close both and the ball could never leave, so the gate changes no
topological state; open both and the ball rolls straight through and there is no
"inside". One closed end (a wall with a return ramp that sends the ball back under
gravity) plus one open end (the doorway, which the gate seals) is what turns "the
ball can leave" into "the ball cannot leave". It also makes inside and outside
readable from the geometry itself rather than from a label: the judge floods the
free space from the ball and asks whether it reaches the arena boundary, and the
doorway is the only route there.

The ball starts OUTSIDE, on the feed ramp, at rest -- gravity gives it its entry
speed, so no velocity is written at runtime. Starting outside is what makes "too
early" a real failure: seal the doorway before the ball is in and the ball is
locked out. Starting it inside would make "insert immediately" a winning script.

The ball is driven, not dropped: `_ball_drive.BallShuttle` holds its speed along
the lane and reverses it when something blocks the way. That is why there are no
ramps here. `tests/ball_roll_spike.py` measured rigid-vs-rigid restitution at
-0.001, so a ball has no way of its own to turn around -- gravity ramps were the
first answer and cost a slope shallow enough to be at the mercy of solver
stiction. Driving it instead makes every timing figure exact arithmetic and
reduces the whole family of tuning to one number, the speed.

The drive never overrules collision: only the along-lane velocity is written, so
a closed gate stops the ball and the shuttle reverses off it. That is what makes
success visible without reading a number -- a caged ball keeps shuttling inside
the box, an escaped one runs off the end of the rail.

Everything here is generated from config numbers -- opening width, channel length,
ramp rise and gate travel are difficulty and randomization knobs, so none of them
may be frozen into a mesh. Collision geometry is convex primitives; the industrial
scene carries no decoration at all -- see `_add_visual_details` for why both
attempts at it were withdrawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.tasks_legacy._visuals import box_entity_enabled
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class GateCageBallLayout:
    """Channel, ramps, gate and ball geometry for Gate Cage Ball."""

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
            f"Unsupported GateCageBall coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        return float(self.task_origin[2]) + float(z)

    # ----- channel ----------------------------------------------------------

    @property
    def center_x(self) -> float:
        return float(self.cfg.channel.center_x)

    @property
    def inner_width(self) -> float:
        return float(self.cfg.channel.inner_width)

    @property
    def floor_top_z(self) -> float:
        return float(self.cfg.channel.floor_top_z)

    @property
    def door_y(self) -> float:
        """The plane the gate seals. `depth()` says which side of it is 'inside'."""

        return float(self.cfg.channel.door_y)

    @property
    def inward(self) -> float:
        """+1 when the closed box lies at larger y, -1 when the channel is mirrored.

        The anti-shortcut axis `channel.open_end` (2026-09-09): with both ends
        otherwise identical, a policy that memorised "the ball comes from -y" has
        to look at which end carries the far wall instead.

        Every other leaf in `channel` is a DISTANCE from the doorway, not a
        position -- `entry_start_y = -0.550` reads "the lane starts 55 cm outside".
        That is why the mirror costs so little: every timing formula here is a
        difference of two such leaves and is therefore mirror-invariant, and only
        the handful of places that emit or read an actual task-frame y go through
        `lane_y` / `depth`.
        """

        return -1.0 if int(getattr(self.cfg.channel, "open_end", 0)) else 1.0

    def lane_y(self, canonical_y: float) -> float:
        """Task-frame y of a point the config names by its distance from the door."""

        return self.door_y + self.inward * (float(canonical_y) - self.door_y)

    def depth(self, y: float) -> float:
        """How far a task-frame y lies INSIDE the box. Negative outside, 0 at the door."""

        return self.inward * (float(y) - self.door_y)

    @property
    def flat_end_y(self) -> float:
        return float(self.cfg.channel.flat_end_y)

    def wall_inner_x(self) -> tuple[float, float]:
        half = 0.5 * self.inner_width
        return self.center_x - half, self.center_x + half

    def slot_y_extent(self) -> tuple[float, float]:
        """Outer faces of the near and far guide posts.

        The slot's four posts occupy this whole strip of y, so the side walls
        begin where it ends and the feed rails stop where it starts. Tiling them
        edge to edge rather than letting them overlap is the same rule
        `bar_through_hole._add_panel` follows: volumetric overlap renders as
        clipping, and there is no reason to accept it when the parts abut anyway.
        """

        slot = self.cfg.gate_slot
        reach = 0.5 * float(slot.guide_gap) + float(slot.post_thickness)
        return self.door_y - reach, self.door_y + reach

    # ----- ball -------------------------------------------------------------

    @property
    def ball_radius(self) -> float:
        return float(self.cfg.ball.radius)

    @property
    def entry_start_y(self) -> float:
        return float(self.cfg.channel.entry_start_y)

    @property
    def ball_speed(self) -> float:
        """Speed at the doorway. Commanded when driven; from the release height when free.

        Free: v = sqrt(2 a s) from rest over the slope run, which is the same
        number as sqrt(10 g h / 7) -- the release HEIGHT is what sets it, and
        neither the slope's length nor its angle enters on its own.
        """

        if self.drive:
            return float(self.cfg.ball.speed)
        a = self.entry_gravity_accel()
        run = self.ramp_run()
        if a <= 0.0 or run <= 0.0:
            return 0.0
        return float(np.sqrt(2.0 * a * run))

    def ball_release_center(self) -> np.ndarray:
        """Where the ball starts: on the flat, OUTSIDE the doorway.

        Outside is load-bearing. It is what makes sealing too early a failure
        rather than a free win; a ball starting inside would make "insert
        immediately" a winning script.
        """

        return self.position_to_world(
            (
                self.center_x,
                self.lane_y(float(self.cfg.ball.release_y)),
                self.floor_top_at(float(self.cfg.ball.release_y)) + self.ball_radius,
            )
        )

    # ----- entry ramp ---------------------------------------------------------
    # The entry lane's floor is a slope: high at the far end, level at the
    # doorway, so the ball rolls down it and speeds up. The slope is GEOMETRY and
    # the speed along it is the DRIVE's -- see `channel.slope_tier` in the yaml
    # for why the two cannot both be real at this ball speed.

    @property
    def entry_slope_rad(self) -> float:
        return float(np.deg2rad(float(getattr(self.cfg.channel, "entry_slope_deg", 0.0))))

    # ----- free-rolling probe (2026-09-10) ----------------------------------
    # `ball.drive: false` takes the shuttle off the lane: the ball rolls down the
    # entry slope under gravity and crosses the flat closed section at whatever
    # speed the release height gave it. The rigid solver has no restitution
    # (re-measured 2026-09-10: coup_restitution 0 and 1.0 both give a rebound
    # ratio of -0.001 on a 10 cm drop), so the one thing a stand-in still does is
    # the bounce: on impact with a wall the ball is sent back at
    # `ball.wall_restitution` times its impact speed, once, and left alone again.
    # Each bounce costs it energy, so it climbs the entry slope a little less each
    # time and every pass through the doorway is slower and longer than the last.
    # The planner picks the first pass long enough to seal.

    @property
    def drive(self) -> bool:
        return bool(getattr(self.cfg.ball, "drive", True))

    @property
    def wall_restitution(self) -> float:
        """Speed kept per wall bounce; 0 when the shuttle drives the ball."""

        return 0.0 if self.drive else float(getattr(self.cfg.ball, "wall_restitution", 0.0))

    @staticmethod
    def rolling_accel(slope_rad: float) -> float:
        """A solid sphere rolling without slipping: (5/7) g sin(slope)."""

        return float(5.0 / 7.0 * 9.81 * np.sin(float(slope_rad)))

    def entry_gravity_accel(self) -> float:
        return self.rolling_accel(self.entry_slope_rad)

    def pass_schedule(self, until: float) -> list[tuple[float, float, float]]:
        """``[(t_enter, v_in, dwell)]`` for every pass through the doorway before ``until``.

        Free ball only. Inside, the box is flat: over to the wall at v_in, back at
        e v_in. Outside, it climbs the entry slope to rest and returns at the same
        speed it left with (the slope is lossless in this solver), so the next
        pass enters at e v_in. The level strip by the posts is crossed twice per
        excursion.
        """

        if self.drive:
            return []
        e = self.wall_restitution
        a = self.entry_gravity_accel()
        v = self.ball_speed
        span = self.turn_y() - self.door_y
        level = self.door_y - self.ramp_end_y()
        if e <= 0.0 or a <= 0.0 or v <= 0.0 or span <= 0.0:
            return []
        t = self.entry_delay()
        rows = []
        while t < until and len(rows) < 200:
            dwell = span / v + span / (e * v)
            rows.append((float(t), float(v), float(dwell)))
            v_out = e * v
            t += dwell + 2.0 * v_out / a + 2.0 * level / v_out
            v = v_out
        return rows

    def sealable_pass(self) -> tuple[float, float, float] | None:
        """The first pass the arm can use: on station already, and long enough to seal."""

        need = self.seal_deadline() + float(self.cfg.timing.safety_margin)
        cap = int(self.cfg.motion.max_hover_steps) * self.sim_dt + self.t_ready()
        for t_enter, v_in, dwell in self.pass_schedule(cap):
            if t_enter >= self.t_ready() and dwell >= need:
                return (t_enter, v_in, dwell)
        return None

    def speed_at_cap(self) -> float:
        """How fast the ball still enters when the hover cap runs out.

        Read so that "hover until the ball has died against the wall, then seal"
        cannot be a winning script: a ball that has decayed to a crawl is inside
        the box for as long as anyone likes.
        """

        cap = int(self.cfg.motion.max_hover_steps) * self.sim_dt + self.t_ready()
        rows = self.pass_schedule(cap + 60.0)
        after = [v for t, v, _ in rows if t >= cap]
        if after:
            return float(after[0])
        return float(rows[-1][1] * self.wall_restitution) if rows else 0.0

    def ramp_end_y(self) -> float:
        """Canonical y where the ramp levels out: the guide posts' outer face.

        The last stretch to the doorway is flat, so the plate never has to seal
        against a tilted floor and the slot strip stays the shape the judge's
        floor plan assumes.
        """

        slot_near, _ = self.slot_y_extent()
        return slot_near

    def ramp_length(self) -> float:
        """Horizontal run of the slope, from the lane's far end to where it levels."""

        return float(self.ramp_end_y() - self.entry_start_y)

    def ramp_rise(self) -> float:
        """How much higher the lane's far end sits than the doorway."""

        return float(self.ramp_length() * np.tan(self.entry_slope_rad))

    def floor_top_at(self, canonical_y: float) -> float:
        """Top of the channel floor at a point named by its distance from the door."""

        y = float(canonical_y)
        climb = self.ramp_end_y() - y
        if climb > 0.0:
            return self.floor_top_z + min(climb, self.ramp_length()) * float(
                np.tan(self.entry_slope_rad)
            )
        return self.floor_top_z

    def entry_speed(self) -> float:
        """How fast the ball is moving when it is released, up on the slope."""

        ratio = float(getattr(self.cfg.ball, "entry_speed_ratio", 1.0))
        return float(ratio * self.ball_speed)

    def ramp_run(self) -> float:
        """Distance the ball covers on the slope, from its release to the level part."""

        return float(self.ramp_end_y() - float(self.cfg.ball.release_y))

    def ramp_sag(self) -> float:
        """Speed the drive has to give back on the slope, in m/s.

        The drive rewrites the ball's along-lane velocity once per step, so it
        owns the speed at every step boundary but not what happens INSIDE a step.
        On an incline gravity spends that interval pulling the ball further down
        the lane, and the surplus -- about half of g sin(t) cos(t) dt, a distance
        expressed as a speed -- is pure gain: the ball keeps arriving early while
        tracking the commanded speed exactly.

        Measured on the 5 degree tier (2026-09-09, `runs/gate_cage_ball_variation`
        probe on seed 3): the ball crossed the doorway at step 768 against a
        closed-form 819, an average 0.0677 m/s against a commanded 0.0635, which
        back-solves to 3.78 mm/s. Sliding predicts 4.26 and pure rolling 3.04, so
        the solver sits between them and the sliding form is used -- it is the
        upper bound, so subtracting it lands the ball a hair LATE rather than
        early, which is the safe side of condition B.

        Subtracted from the commanded speed, never added: a drive that could write
        a bigger velocity than its schedule is the shape of the bug `HeadingDrive`
        documents, where a state write beats a contact and walks the ball through
        a closed gate.
        """

        angle = self.entry_slope_rad
        return float(0.5 * 9.81 * np.sin(angle) * np.cos(angle) * self.sim_dt)

    def ramp_accel(self) -> float:
        """Commanded acceleration along the slope, from the release speed to the door speed.

        Set by where the ball starts rather than by the slope angle: the angle is
        what a policy READS, the door speed is what the timing arithmetic needs,
        and this is the number that joins them. It is one to two orders below what
        gravity on the same slope would give -- the honest cost of the fiction,
        written out in the yaml.
        """

        run = self.ramp_run()
        if run <= 0.0:
            return 0.0
        v0, v1 = self.entry_speed(), self.ball_speed
        return float((v1 * v1 - v0 * v0) / (2.0 * run))

    def turn_y(self) -> float:
        """Where the ball's centre reverses at the closed end."""

        return self.flat_end_y - self.ball_radius

    def predicted_window(self, *, dt: float = 0.01) -> float:
        """Seconds the ball spends inside, from crossing the doorway and back.

        Exact, not integrated: the drive holds the speed, so the round trip is a
        distance over a speed. The gate has to be committed and seated inside
        this, which is what `run.safety_margin` is checked against.
        """

        del dt  # the answer is continuous
        speed = self.ball_speed
        if speed <= 0.0:
            return 0.0
        if not self.drive:
            # The pass the arm will actually use; the first one is the fastest
            # and usually too short, and each bounce makes the next one longer.
            usable = self.sealable_pass()
            if usable is not None:
                return usable[2]
            rows = self.pass_schedule(int(self.cfg.motion.max_hover_steps) * self.sim_dt + self.t_ready())
            return max((d for _, _, d in rows), default=0.0)
        return float(2.0 * (self.turn_y() - self.door_y) / speed)

    def entry_delay(self) -> float:
        """Seconds from the episode's start until the ball first crosses the doorway.

        Two stretches, both closed form: uniform acceleration down the slope from
        the release speed to the door speed, then the level run-in at the door
        speed. With a flat lane the release speed equals the door speed and this
        collapses to the distance over the speed, which is what it used to be.
        """

        speed = self.ball_speed
        if speed <= 0.0:
            return float("inf")
        run = self.ramp_run()
        level = (self.door_y - self.ramp_end_y()) / speed
        if not self.drive:
            a = self.entry_gravity_accel()
            on_ramp = float(np.sqrt(2.0 * run / a)) if a > 0.0 else float("inf")
            return float(on_ramp + level)
        v0 = self.entry_speed()
        on_ramp = 2.0 * run / (v0 + speed) if (v0 + speed) > 0.0 else float("inf")
        return float(on_ramp + level)

    def lane_bounds(self) -> tuple[float, float]:
        """Where the drive applies, as an ordered task-frame (min, max).

        Past these the ball is off the rail and free. Mirrored and ordered here
        rather than at the call site: the drive compares against them with `<=`.
        """

        ends = (
            self.lane_y(self.entry_start_y - 2.0 * self.ball_radius),
            self.lane_y(self.flat_end_y),
        )
        return min(ends), max(ends)

    # ----- gate -------------------------------------------------------------

    def gate_seated_center(self) -> np.ndarray:
        """Gate centre when it is fully down in the slot."""

        gate = self.cfg.gate
        mid_z = 0.5 * (float(gate.seated_bottom_z) + float(gate.seated_top_z))
        return self.position_to_world((self.center_x, self.door_y, mid_z))

    def gate_parked_center(self) -> np.ndarray:
        rack = self.cfg.gate_rack
        gate = self.cfg.gate
        base_top = float(rack.base_size[2])
        height = float(gate.seated_top_z) - float(gate.seated_bottom_z)
        return self.position_to_world(
            (float(rack.center_x), float(rack.center_y), base_top + 0.5 * height)
        )

    def plate_top_on_rack(self) -> float:
        """Task z of the parked plate's top edge: rack base top + plate height."""

        rack = self.cfg.gate_rack
        gate = self.cfg.gate
        return float(rack.base_size[2]) + float(gate.seated_top_z) - float(gate.seated_bottom_z)

    # ----- timing -------------------------------------------------------------
    # The arm's side of the race, in seconds. Step counts live in `motion`, the
    # step length in `timing.sim_dt` (a copy of env.sim.dt the demo asserts
    # against), because the variation validator only ever sees the task config.
    # Same formulas as GatedInsertPrimitive.time_to_station / insert_duration;
    # the demo asserts the two agree at start-up.

    @property
    def sim_dt(self) -> float:
        return float(self.cfg.timing.sim_dt)

    def t_ready(self) -> float:
        """Seconds from the episode's start until the plate hovers over the slot."""

        motion = self.cfg.motion
        moves = 4  # descend, lift, carry, align; the approach has its own count
        approach = int(getattr(motion, "approach_steps", None) or motion.steps_per_phase)
        steps = (
            int(motion.gripper_steps)
            + approach
            + moves * int(motion.steps_per_phase)
            + int(motion.gripper_steps)
            + int(motion.close_hold_steps)
        )
        return steps * self.sim_dt

    def insert_duration(self) -> float:
        """Seconds from committing the descent until the slot is sealed."""

        motion = self.cfg.motion
        return (int(motion.insert_steps) + int(motion.insert_settle_steps)) * self.sim_dt

    def block_duration(self) -> float:
        """Seconds from committing the descent until the plate is IN THE BALL'S WAY.

        Not the seat time. The plate blocks the doorway as soon as its bottom is
        below the ball's crown -- the verifier's `gate_blocking` and the bounce
        stand-in's gate face both use that height -- and on the cosine descent
        `GatedInsertPrimitive._move` runs, that comes at about half the travel:
        0.49-0.61 s of the 1.00 s descent depending on the ball, against the
        1.30 s `insert_duration` counts to the seat. Measured 2026-09-10: with the
        seat time as the deadline the offline model put a fixed-delay policy at
        24%, and it scored 7/10 -- because a ball that reaches the door 0.6 s
        into the descent meets a wall, not a gap.
        """

        motion = self.cfg.motion
        gate = self.cfg.gate
        plate_h = float(gate.seated_top_z) - float(gate.seated_bottom_z)
        # Hand-to-plate-centre offset, the same one the carry uses: at the grasp
        # the hand is at grasp_z and the plate stands parked on the rack.
        hand_to_plate = float(motion.grasp_z) - (float(self.cfg.gate_rack.base_size[2]) + 0.5 * plate_h)
        hover_bottom = float(motion.hover_z) - hand_to_plate - 0.5 * plate_h
        seated_bottom = float(gate.seated_bottom_z)
        crown = self.floor_top_z + 2.0 * self.ball_radius
        travel = hover_bottom - seated_bottom
        if travel <= 0.0 or crown >= hover_bottom:
            return 0.0
        alpha = (hover_bottom - crown) / travel  # fraction of the descent at which it blocks
        alpha = min(max(alpha, 0.0), 1.0)
        frac = float(np.arccos(1.0 - 2.0 * alpha) / np.pi)  # invert alpha = 0.5 - 0.5 cos(pi s)
        return float(frac * int(motion.insert_steps) * self.sim_dt)

    def seal_deadline(self) -> float:
        """How long the ball has to stay away from the doorway once the descent is committed.

        Driven layout: the seat time (the drive can push a ball into a plate that
        is not yet seated). Free layout: the blocking time -- a free ball that
        meets the descending plate is turned back by it.
        """

        return self.insert_duration() if self.drive else self.block_duration()

    def window_margin(self) -> float:
        """Window minus the seal time minus the trigger rule's safety margin (>= 0 to be sealable)."""

        return (
            self.predicted_window()
            - self.seal_deadline()
            - float(self.cfg.timing.safety_margin)
        )

    def last_commit(self) -> float:
        """Latest second at which committing still seals before the ball is back out."""

        return self.entry_delay() + self.predicted_window() - self.insert_duration()

    def ready_margin(self) -> float:
        """How long after the arm is on station the last commit still is (>= 0 to be solvable).

        Free ball: there is no last commit -- the ball swings back through the
        doorway every period -- so the condition becomes that a whole period fits
        inside the hover cap, i.e. the arm is guaranteed to see one full pass.
        """

        if not self.drive:
            usable = self.sealable_pass()
            if usable is None:
                return float("-inf")
            cap = int(self.cfg.motion.max_hover_steps) * self.sim_dt + self.t_ready()
            return float(cap - usable[0] - float(self.cfg.timing.ready_margin))
        return self.last_commit() - self.t_ready() - float(self.cfg.timing.ready_margin)

    def hover_wait(self) -> float:
        """Seconds the arm waits on station before the ball first enters; negative = ball first.

        Reported, never constrained: its sign is what separates the trigger
        rules, and choosing geometry to fix it would write a baseline's score
        into the scene (configs/run_configs/gate_cage_ball_gate.yaml).
        """

        return self.entry_delay() - self.t_ready()

    # ----- variation: derived leaves ------------------------------------------
    # Three leaves have ranges that depend on other axes, so the yaml samples a
    # unit fraction for each and `derive_task_cfg` maps it onto the range the
    # drawn speed / geometry allows. Order matters: the closed section sets the
    # window, the window bounds the release, the channel bounds the rack.

    def flat_end_y_bounds(self) -> tuple[float, float]:
        """Closed-section end: long enough that the window fits the seal (condition A)."""

        channel = self.cfg.channel
        if not self.drive:
            # Free ball: the box's length only changes WHICH pass is the first
            # sealable one, never whether one exists (scanned 2026-09-10 over the
            # whole envelope), so the whole declared range is usable.
            return float(channel.flat_end_y_min), float(channel.flat_end_y_max)
        need = self.door_y + self.ball_radius + 0.5 * self.ball_speed * (
            self.insert_duration() + float(self.cfg.timing.safety_margin)
        )
        return float(max(float(channel.flat_end_y_min), need)), float(channel.flat_end_y_max)

    def flat_end_y_from_frac(self, frac: float) -> float:
        lo, hi = self.flat_end_y_bounds()
        if not hi >= lo:
            raise ValueError(
                f"No closed-section length seals a {self.ball_speed:.3f} m/s ball: needs "
                f"flat_end_y >= {lo:+.3f}, ceiling {hi:+.3f}."
            )
        return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))

    def release_y_bounds(self) -> tuple[float, float]:
        """Where the ball may start: on the rail, wholly outside the door, and far
        enough out that the arm is on station before the last commit (condition B)."""

        ball = self.cfg.ball
        lo = self.entry_start_y + float(ball.spawn_entry_margin)
        # Two separate things used to be carried by one number. `spawn_door_margin`
        # was set to 0.080 on 2026-09-08 to hold the SHORTEST roll the ball can be
        # given at about 1.2 s -- a distance standing in for a time, which stopped
        # working the moment the slope made the two stop being proportional (a
        # steep tier's ball starts slow, so the same distance buys more seconds).
        # So the floor is now stated as the time it always was, and the distance
        # is whatever that costs on this tier; the geometric part -- the whole ball
        # has to be outside the doorway -- stays a distance, because that is what
        # it is.
        outside = self.door_y - self.ball_radius - float(ball.spawn_geom_margin)
        if not self.drive:
            # Free ball: geometry, plus a floor on the slope run so the ball is
            # still moving when the hover cap runs out (`moving_at_cap`) -- a
            # ball released too close to the door arrives slow and dies against
            # the wall within the cap. Whether the arm can catch a sealable pass
            # is the `window_margin` / `ready_margin` rows' job; the ball keeps
            # coming back, so a spawn point is never "too late".
            far_enough = self.ramp_end_y() - float(ball.spawn_min_run)
            return float(lo), float(min(outside, far_enough))
        observe = self.door_y - self._distance_for_observe(
            float(ball.spawn_min_observe_s)
        )
        need = (
            self.t_ready()
            + self.insert_duration()
            - self.predicted_window()
            + float(self.cfg.timing.ready_margin)
        )
        # Invert `entry_delay` rather than assuming a constant speed. On a sloped
        # lane the ball takes LONGER than distance/speed, so the constant-speed
        # form would still be safe -- but it would demand run-up the ramp does not
        # need and narrow the spawn range for no reason.
        v0, speed = self.entry_speed(), self.ball_speed
        level = (self.door_y - self.ramp_end_y()) / speed
        on_ramp_needed = max(0.0, need - level)
        in_time = self.ramp_end_y() - 0.5 * on_ramp_needed * (v0 + speed)
        return float(lo), float(min(outside, observe, in_time))

    def _distance_for_observe(self, seconds: float) -> float:
        """How far out the ball must start to roll for at least this long.

        The inverse of `entry_delay`: the level run-in at the door speed, then
        whatever the slope has to add on top of it.
        """

        speed = self.ball_speed
        if speed <= 0.0:
            return float("inf")
        level = (self.door_y - self.ramp_end_y()) / speed
        on_ramp = max(0.0, float(seconds) - level)
        return float((self.door_y - self.ramp_end_y())
                     + 0.5 * on_ramp * (self.entry_speed() + speed))

    def release_y_from_frac(self, frac: float) -> float:
        lo, hi = self.release_y_bounds()
        if not hi >= lo:
            raise ValueError(
                f"The entry lane from {self.entry_start_y:+.3f} is too short for the arm "
                f"({self.t_ready():.2f} s to station) to beat a {self.ball_speed:.3f} m/s ball: "
                f"release_y would have to be <= {hi:+.3f}."
            )
        return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))

    def rack_x_bounds(self) -> tuple[float, float]:
        """Rack centre x: a fixed floor toward the arm, a ceiling clear of the guide posts."""

        rack = self.cfg.gate_rack
        slot = self.cfg.gate_slot
        inner_lo, _ = self.wall_inner_x()
        post_face = inner_lo - float(slot.post_width)  # the posts stand proud of the wall
        hi = post_face - float(rack.channel_gap) - 0.5 * float(rack.base_size[0])
        return float(rack.x_min), float(hi)

    def rack_x_from_frac(self, frac: float) -> float:
        lo, hi = self.rack_x_bounds()
        if not hi >= lo:
            raise ValueError(
                f"No rack position clears the channel: needs centre <= {hi:+.3f}, floor {lo:+.3f}."
            )
        return float(lo + min(max(float(frac), 0.0), 1.0) * (hi - lo))

    def rack_center_y(self) -> float:
        """Rack centre y: which side of the doorway, plus the drawn jitter.

        The side is the anti-shortcut mirror (`gate_rack.side`), the jitter is the
        diversity term it is laid on top of. Deliberately NOT routed through
        `lane_y`: the rack's side and the channel's open end are independent axes,
        so all four combinations have to occur.
        """

        rack = self.cfg.gate_rack
        sign = 1.0 if int(getattr(rack, "side", 0)) else -1.0
        return float(sign * float(rack.side_offset) + float(rack.y_jitter))

    def carry_span(self) -> float:
        """Horizontal distance the plate travels from the rack to the hover point.

        Read because the carry is a fixed `motion.steps_per_phase` whatever the
        distance, so lengthening it means moving faster per step, not for longer.
        """

        return float(np.hypot(self.center_x - float(self.cfg.gate_rack.center_x),
                              self.door_y - float(self.cfg.gate_rack.center_y)))

    def rack_reach(self) -> float:
        """Distance from the arm's base to the parked plate (task xy)."""

        base = np.asarray([float(v) for v in self.cfg.reach.base_xy], dtype=float)
        rack = self.cfg.gate_rack
        return float(np.hypot(float(rack.center_x) - base[0], float(rack.center_y) - base[1]))

    def rack_channel_gap(self) -> float:
        """Clear x between the rack's near edge and the guide posts' outer face."""

        rack = self.cfg.gate_rack
        inner_lo, _ = self.wall_inner_x()
        post_face = inner_lo - float(self.cfg.gate_slot.post_width)
        return float(post_face - (float(rack.center_x) + 0.5 * float(rack.base_size[0])))

    def hover_reach(self) -> float:
        """Distance from the arm's base to the hover point over the slot (task xy)."""

        base = np.asarray([float(v) for v in self.cfg.reach.base_xy], dtype=float)
        return float(np.hypot(self.center_x - base[0], self.door_y - base[1]))

    # ----- variation: checks -------------------------------------------------

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a solvable, buildable layout needs.

        One list for the randomizer's reject step, the offline gate and the
        demo's start-up print. Seconds for the three timing rows, metres otherwise.
        """

        window = self.window_margin()
        ready = self.ready_margin()
        spawn_lo, spawn_hi = self.release_y_bounds()
        release_y = float(self.cfg.ball.release_y)
        gap = self.rack_channel_gap()
        min_gap = float(self.cfg.gate_rack.channel_gap)
        reach = self.hover_reach()
        max_reach = float(self.cfg.reach.max_hover_dist)
        # The open gripper traverses to a point above the parked plate at
        # approach_z with its fingers hanging below the pads; 30 mm of pad-to-top
        # clearance is the linkbar / diverter gate. Constant across the envelope
        # (no axis moves approach_z or the plate), so it guards edits, not draws.
        approach_clearance = (
            float(self.cfg.motion.approach_z) - HAND_TO_PAD_Z - self.plate_top_on_rack()
        )
        # The ball's size is an axis (2026-09-08) while the channel is not, so
        # the two rows the channel used to satisfy by construction now have to be
        # read: the ball has to fit between the walls and stay under their top.
        side_clearance = 0.5 * self.inner_width - self.ball_radius
        wall_over_ball = float(self.cfg.channel.wall_height) - 2.0 * self.ball_radius
        # The arm reaches its station and then waits for the ball. Lengthening
        # the entry lane and slowing the ball down (2026-09-08) pushed that wait
        # towards the run's own cap, past which the episode is scored
        # `trigger_never_fired` -- a solvability limit like the other two, so it
        # is read here rather than left to chance.
        hover_cap = int(self.cfg.motion.max_hover_steps) * self.sim_dt
        return [
            ("window_margin", window, 0.0, window >= -1e-9),
            ("ready_margin", ready, 0.0, ready >= -1e-9),
            ("ball_spawn", release_y, spawn_lo, spawn_lo - 1e-9 <= release_y <= spawn_hi + 1e-9),
            ("rack_channel_gap", gap, min_gap, gap >= min_gap - 1e-9),
            ("hover_reach", reach, max_reach, reach <= max_reach + 1e-9),
            ("approach_clearance", approach_clearance, 0.030, approach_clearance >= 0.030),
            ("ball_fits_channel", side_clearance, 0.005, side_clearance >= 0.005 - 1e-9),
            ("wall_contains_ball", wall_over_ball, 0.010, wall_over_ball >= 0.010 - 1e-9),
            ("hover_within_cap", self.hover_wait(), hover_cap, self.hover_wait() <= hover_cap + 1e-9),
            # The rack moved to either side of the doorway (2026-09-09), so the two
            # readings that used to be constant now vary and have to be read.
            # Both are edit guards rather than draw filters -- the envelope's worst
            # case sits well inside each -- which is the same footing as
            # `approach_clearance` above. Whether the fixed 30-step carry actually
            # TRACKS the longer move is a measurement, not an envelope condition;
            # writing that into the envelope would freeze the shape of a bug
            # (2026-09-03, the grasp-pose defect the corner sweep found).
            ("rack_reach", self.rack_reach(), max_reach, self.rack_reach() <= max_reach + 1e-9),
            ("carry_span", self.carry_span(), 0.300, self.carry_span() <= 0.300 + 1e-9),
            # The ramp (2026-09-09) and the two readings it passes through.
            # `release_on_ramp`: the acceleration profile is defined from the
            # release point down to where the lane levels, so a ball spawned
            # inside the level run-in would have no ramp to accelerate on.
            # `entry_wall_over_center`: the entry walls tilt WITH the floor, so
            # what they guarantee is unchanged -- but the ball's size is an axis
            # and this row was until now held by "it happens to fit". The bar is
            # the ball's CENTRE, not its crown: the entry run only has to steer
            # the ball, and 45 mm of wall against a 36 mm ball is the yaml's own
            # stated criterion.
            ("release_on_ramp", self.ramp_run(), 0.0, self.ramp_run() >= -1e-9),
            # Free-rolling probe (2026-09-10). A free ball on a flat box needs the
            # wall to send it back, and the stand-in that does so has to leave it
            # still moving when the hover cap runs out -- otherwise "hover as long
            # as allowed, then seal" wins on every instance. Both inert when driven.
            (
                "bounce_when_free",
                self.wall_restitution,
                0.3,
                self.drive or self.wall_restitution >= 0.3,
            ),
            (
                "moving_at_cap",
                self.speed_at_cap(),
                0.10,
                self.drive or self.speed_at_cap() >= 0.10 - 1e-9,
            ),
            (
                "entry_wall_over_center",
                float(self.cfg.channel.entry_wall_height) - self.ball_radius,
                0.005,
                float(self.cfg.channel.entry_wall_height) - self.ball_radius >= 0.005 - 1e-9,
            ),
        ]

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"gate_cage_ball layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Order
    matters: the slope tier first (it sets the angle and the release run's
    floor), then for the driven layout the closed section (needs the speed) and
    the release (needs the window); the rack needs the channel's x. A
    ``ValueError`` (empty range) rejects the draw.

    The rack's y is derived rather than drawn directly so that this stays a pure
    function of the drawn leaves: `side` and `y_jitter` are what the randomizer
    writes, `center_y` is what the scene reads, and running this twice on the
    same draw gives the same answer.
    """

    # The slope tier first: it sets the angle and the floor on the release run
    # (tier 0 needs a long run so the ball's first arrival is after the arm's).
    tier = _list(task_cfg.channel.slope_tiers)[int(task_cfg.channel.slope_tier)]
    task_cfg.channel.entry_slope_deg = float(tier["deg"])
    task_cfg.ball.spawn_min_run = float(tier["min_run"])

    layout = GateCageBallLayout(task_cfg)
    task_cfg.channel.flat_end_y = layout.flat_end_y_from_frac(float(task_cfg.channel.flat_end_frac))
    task_cfg.ball.release_y = layout.release_y_from_frac(float(task_cfg.ball.release_frac))
    task_cfg.gate_rack.center_x = layout.rack_x_from_frac(float(task_cfg.gate_rack.x_frac))
    task_cfg.gate_rack.center_y = layout.rack_center_y()


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    GateCageBallLayout(task_cfg).validate()


@dataclass
class GateCageBallScene:

    scene: Any
    manifest: EntityManifest
    layout: GateCageBallLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None

    def ball_entity(self):
        return self.manifest.get("ball")

    def gate_entity(self):
        return self.manifest.get("gate")


class GateCageBallSceneBuilder:
    """Build the common table plus the chute, ramps, gate slot, gate and ball."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> GateCageBallScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg, self.robot_cfg, rigid_options=self.rigid_options
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = GateCageBallLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        layout.validate()
        self._add_channel(scene, manifest, layout)

        self._add_far_wall(scene, manifest, layout)
        self._add_gate_slot(scene, manifest, layout)
        self._add_gate_rack(scene, manifest, layout)
        self._add_gate(scene, manifest, layout)
        self._add_ball(scene, manifest, layout)
        self._add_visual_details(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        return GateCageBallScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    def _box(self, scene, manifest, name, center, size, color, *, role="fixture", euler=None):
        kwargs = {"pos": tuple(center), "size": tuple(float(v) for v in size), "fixed": True}
        if euler is not None:
            kwargs["euler"] = tuple(float(v) for v in euler)
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(**kwargs),
                surface=materials.plastic(role, _list(color)),
                name=name,
            ),
        )

    # ---------------------------------------------------------------- channel

    def _add_channel(self, scene, manifest, layout) -> None:
        """The floor slab and the side walls, in two segments per side.

        The walls run parallel to the ball's motion and are never struck head-on;
        the drive keeps the ball on the lane axis and only the far wall stops it.

        Two segments because the guide posts stand in the strip between them: the
        entry segment ends at the slot's near face and the box segment starts at
        its far face, so post and wall abut rather than sharing a volume. The floor
        runs the whole length underneath both, at inner width only -- at full outer
        width it would share a volume with the walls and the posts, all of which
        stand on the table.
        """

        channel = self.task_cfg.channel
        if not box_entity_enabled(channel):
            return
        color = _list(channel.color)
        floor_top = layout.floor_top_z
        thickness = float(channel.floor_thickness)
        wall_t = float(channel.wall_thickness)
        box_top = floor_top + float(channel.wall_height)
        # The entry run only has to keep the ball straight; the box has to keep it
        # in. Making the outside walls lower separates the two visually and keeps
        # them out of the front and wrist camera's line on the slot.
        entry_top = floor_top + float(
            getattr(channel, "entry_wall_height", channel.wall_height)
        )
        # `slot_y_extent` is symmetric about the doorway, so its two ends swap
        # roles under the mirror rather than moving; the lane's two ends do move.
        slot_near, slot_far = layout.slot_y_extent()

        # The entry assembly (sloped floor slab plus its two walls) is placed as
        # one rigid unit pivoted on the line where the slope meets the level
        # floor, so the two floors meet flush at any angle instead of each part
        # being fitted to its own z by hand.
        ramp_y0, ramp_y1 = layout.entry_start_y, layout.ramp_end_y()
        ramp_len = layout.ramp_length()
        stretch = 1.0 / max(np.cos(layout.entry_slope_rad), 1e-9)

        self._box(
            scene,
            manifest,
            "channel_floor_entry",
            self._ramp_pose(layout, 0.5 * (ramp_y0 + ramp_y1), floor_top - 0.5 * thickness),
            (layout.inner_width, ramp_len * stretch, thickness),
            _list(channel.floor_color),
            role="board",
            euler=self._ramp_euler(layout),
        )

        box_y0, box_y1 = layout.lane_y(ramp_y1), layout.lane_y(layout.flat_end_y)
        self._box(
            scene,
            manifest,
            "channel_floor_box",
            layout.position_to_world(
                (layout.center_x, 0.5 * (box_y0 + box_y1), floor_top - 0.5 * thickness)
            ),
            (layout.inner_width, abs(box_y1 - box_y0), thickness),
            _list(channel.floor_color),
            role="board",
        )

        inner_lo, inner_hi = layout.wall_inner_x()
        for sign, side, inner in ((-1.0, "l", inner_lo), (1.0, "r", inner_hi)):
            wall_x = inner + sign * 0.5 * wall_t
            self._box(
                scene,
                manifest,
                f"channel_wall_entry_{side}",
                self._ramp_pose(layout, 0.5 * (ramp_y0 + ramp_y1), 0.5 * entry_top, x=wall_x),
                (wall_t, ramp_len * stretch, entry_top),
                color,
                euler=self._ramp_euler(layout),
            )
            seg_y0, seg_y1 = layout.lane_y(slot_far), layout.lane_y(layout.flat_end_y)
            self._box(
                scene,
                manifest,
                f"channel_wall_box_{side}",
                layout.position_to_world(
                    (wall_x, 0.5 * (seg_y0 + seg_y1), 0.5 * box_top)
                ),
                (wall_t, abs(seg_y1 - seg_y0), box_top),
                color,
            )

        self._add_ramp_support(scene, manifest, layout)

    def _ramp_euler(self, layout) -> tuple[float, float, float]:
        """Tilt for the entry assembly, in the frame the scene is actually built in.

        Negative about x lifts the lane's far end in the canonical build; the
        `channel.open_end` mirror turns y around, which turns the sense of a
        rotation about x with it, hence the `inward` factor.
        """

        return (-float(self.task_cfg.channel.entry_slope_deg) * layout.inward, 0.0, 0.0)

    def _ramp_pose(self, layout, canonical_y: float, z: float, *, x: float | None = None):
        """World placement of a part of the entry assembly, given its untilted spot.

        Rotates the point about the pivot -- the lane's centreline where the slope
        levels out -- then mirrors, then lifts into world coordinates.
        """

        angle = -layout.entry_slope_rad
        pivot_y, pivot_z = layout.ramp_end_y(), layout.floor_top_z
        dy, dz = float(canonical_y) - pivot_y, float(z) - pivot_z
        cos, sin = float(np.cos(angle)), float(np.sin(angle))
        turned_y = pivot_y + dy * cos - dz * sin
        turned_z = pivot_z + dy * sin + dz * cos
        return layout.position_to_world(
            (layout.center_x if x is None else x, layout.lane_y(turned_y), turned_z)
        )

    def _add_ramp_support(self, scene, manifest, layout) -> None:
        """A leg under the raised end of the entry lane.

        Purely what the picture needs: every fixture here is `fixed=True`, so
        nothing would fall without it -- but a feed rail whose far end hangs in
        the air reads as a modelling slip rather than as an inclined rail. Sized
        to the slab's underside at the leg's INNER edge, so the millimetre the
        slope gains across the leg's own width is left as a gap: parts here abut,
        they never share volume (`_add_channel`'s note on the guide posts).
        """

        rise = layout.ramp_rise()
        if rise < 0.005:
            return
        channel = self.task_cfg.channel
        wall_t = float(channel.wall_thickness)
        depth = 0.030
        inner_edge = layout.entry_start_y + depth
        top = layout.floor_top_at(inner_edge) - float(channel.floor_thickness)
        if top <= 0.0:
            return
        self._box(
            scene,
            manifest,
            "channel_ramp_support",
            layout.position_to_world(
                (layout.center_x, layout.lane_y(layout.entry_start_y + 0.5 * depth), 0.5 * top)
            ),
            (layout.inner_width + 2.0 * wall_t, depth, top),
            _list(channel.color),
        )

    def _add_far_wall(self, scene, manifest, layout) -> None:
        """The closed end. A plain wall now: the drive reverses the ball, so this
        only has to stop it, and stopping is exactly what a zero-restitution
        contact does. The ramp that used to live here existed solely to turn the
        ball around under gravity.
        """

        wall = self.task_cfg.far_wall
        wall_t = float(wall.thickness)
        self._box(
            scene,
            manifest,
            "far_wall",
            layout.position_to_world(
                (
                    layout.center_x,
                    layout.lane_y(layout.flat_end_y + 0.5 * wall_t),
                    0.5 * float(wall.height),
                )
            ),
            (
                layout.inner_width + 2.0 * float(self.task_cfg.channel.wall_thickness),
                wall_t,
                float(wall.height),
            ),
            _list(self.task_cfg.channel.color),
        )

    # -------------------------------------------------------------- gate slot

    def _guide_post_stations(self, layout) -> tuple[tuple[str, float, float], ...]:
        """(tag, x, y) for the four posts that box in the gate's descent."""

        slot = self.task_cfg.gate_slot
        half_gap = 0.5 * float(slot.guide_gap)
        half_post = 0.5 * float(slot.post_thickness)
        inner_lo, inner_hi = layout.wall_inner_x()
        # Straddling the channel's inner face puts each post over the side wall's
        # footprint, so the pair reads as a continuation of the wall rather than as
        # two rods standing in front of it.
        x_lo = inner_lo - 0.5 * float(slot.post_width)
        x_hi = inner_hi + 0.5 * float(slot.post_width)
        stations = []
        for x_tag, x in (("l", x_lo), ("r", x_hi)):
            for y_tag, y in (
                ("n", layout.door_y - half_gap - half_post),
                ("f", layout.door_y + half_gap + half_post),
            ):
                stations.append((f"{x_tag}{y_tag}", x, y))
        return tuple(stations)

    def _add_gate_slot(self, scene, manifest, layout) -> None:
        """Four straight posts: two columns, each a pair boxing the plate in y.

        No lead-in funnel at the top. What captures the plate is its own width --
        it is wider than the gap between the two columns, so both ends drop into a
        slot at once and the pair holds it from both sides. A funnel would be a
        second, redundant way to find the same alignment.

        The cost is that the slot clearance is now the whole insertion budget:
        3 mm per side, against a measured IK tracking error of 7.5 mm on the
        comparable move in bar_through_hole. That is survivable only by aiming the
        PLATE from its measured pose rather than the hand from a precomputed one,
        the same correction that task needed. `guide_gap` is the knob if it turns
        out to be too tight in the scene.
        """

        slot = self.task_cfg.gate_slot
        color = _list(slot.color)
        height = float(slot.post_height)
        for tag, x, y in self._guide_post_stations(layout):
            self._box(
                scene,
                manifest,
                f"gate_post_{tag}",
                layout.position_to_world((x, y, 0.5 * height)),
                (float(slot.post_width), float(slot.post_thickness), height),
                color,
            )

    def _add_gate_rack(self, scene, manifest, layout) -> None:
        """Where the gate stands before the episode.

        The smallest thing that holds a plate upright: a thin base and two low
        jaws in the same grey as everything else. It is not a pedestal -- nothing
        is being raised, the gate simply has to start somewhere the gripper can
        take it from without first re-orienting it (which would put an object
        rotation in the episode that no arm motion explains).
        """

        rack = self.task_cfg.gate_rack
        base = np.asarray(_list(rack.base_size), dtype=float)
        self._box(
            scene,
            manifest,
            "gate_rack_base",
            layout.position_to_world(
                (float(rack.center_x), float(rack.center_y), 0.5 * float(base[2]))
            ),
            base,
            _list(rack.color),
        )
        slot = self.task_cfg.gate_slot
        half_gap = 0.5 * float(slot.guide_gap)
        half_post = 0.5 * float(slot.post_thickness)
        height = float(base[2]) + float(getattr(rack, "jaw_height", 0.022))
        for tag, sign in (("n", -1.0), ("f", 1.0)):
            self._box(
                scene,
                manifest,
                f"gate_rack_jaw_{tag}",
                layout.position_to_world(
                    (
                        float(rack.center_x),
                        float(rack.center_y) + sign * (half_gap + half_post),
                        0.5 * height,
                    )
                ),
                (float(base[0]), float(slot.post_thickness), height),
                _list(rack.color),
            )

    # -------------------------------------------------------------- gate/ball

    def _add_gate(self, scene, manifest, layout) -> None:
        """The plate: ONE body, spawned parked in the rack.

        It carried a separate handle block until it was checked: two free rigid
        bodies with nothing joining them do not make a handled plate, they make a
        block resting on a plate, and the first lift would leave one of them
        behind. Genesis has no compound primitive and the convex hull of a T is a
        wedge, so a real handle would have to be a welded second entity -- more
        machinery than the grasp needs. The plate is 12 mm across the axis the
        fingers close on, which is a perfectly ordinary pinch, and the 1.1 kg is
        carried by the same assisted attachment bar_through_hole uses.
        """

        gate = self.task_cfg.gate
        height = float(gate.seated_top_z) - float(gate.seated_bottom_z)
        manifest.add(
            "gate",
            scene.add_entity(
                gs.morphs.Box(
                    pos=tuple(layout.gate_parked_center()),
                    size=(float(gate.width), float(gate.thickness), height),
                    fixed=False,
                ),
                material=gs.materials.Rigid(
                    rho=float(getattr(gate, "rho", 7800.0)),
                    friction=float(getattr(gate, "friction", 0.8)),
                ),
                surface=materials.plastic("object", _list(gate.color)),
                name="gate",
            ),
        )

    def _add_ball(self, scene, manifest, layout) -> None:
        """The ball, at rest on the feed ramp OUTSIDE the arena.

        Outside is load-bearing: it is what makes sealing too early a failure
        rather than a free win. Its entry speed comes from the ramp height, so
        nothing has to write a velocity at run time -- the release point is the
        randomization axis and gravity does the rest.
        """

        ball = self.task_cfg.ball
        manifest.add(
            "ball",
            scene.add_entity(
                gs.morphs.Sphere(
                    pos=tuple(layout.ball_release_center()),
                    radius=float(ball.radius),
                    fixed=False,
                ),
                material=gs.materials.Rigid(
                    rho=float(ball.rho), friction=float(ball.friction)
                ),
                surface=materials.plastic("object", _list(ball.color)),
                name="ball",
            ),
        )

    # -------------------------------------------------------- visual dressing

    def _add_visual_details(self, scene, manifest, layout) -> None:
        """Nothing is drawn here, and that is the finding rather than an omission.

        Two dressing ideas were tried and both were wrong for this scene. The
        pedestal recipe from `_visuals.py` does not apply because nothing is held
        up. Banding on the gate does not work either: decoration is `fixed=True`
        and the gate is the one body that MOVES, so the stripes stayed at the rack
        the moment the arm lifted the plate. Anything marking a moving part would
        have to be re-synced every step, which is the class of thing that drifts
        out of agreement with the physics -- so the gate is told apart by colour
        instead, which costs nothing and cannot desynchronize.
        """

        return
