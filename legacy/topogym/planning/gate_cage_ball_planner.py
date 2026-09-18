"""When should the gate go down?

Everything else in docx 4.1 is a fixed motion. The arm takes the plate off its
rack, carries it over the slot and holds there; the only decision in the episode
is the instant it commits to the descent. That decision is this module, and it is
arithmetic on the ball's state -- no Genesis, no scene, so it is unit-testable.

The window is two-sided and both bounds are real failures:

- Seal before the ball is in and the ball is locked OUT. This is why the ball
  starts outside; without it "insert immediately" would be a winning script.
- Seal after the ball has come back out and there is nothing to cage.

Between them the ball is inside, so the rule is: commit when the ball is in AND
the seal will finish before the ball can reach the doorway again.

Constant-velocity extrapolation is exact here rather than approximate.
`tests/ball_roll_spike.py` measured no rolling resistance at all in the Genesis
rigid solver -- 0.3997 m/s held to four figures over 2.4 s -- so a ball on the
flat section keeps its speed, and time-to-doorway is a division. On the return
ramp it decelerates, but that only ever makes the true time LONGER than this
estimate, so treating the ramp as flat is conservative in the safe direction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateTriggerDecision:
    """Why the planner did or did not commit on this tick."""

    commit: bool
    reason: str
    inside: bool
    time_to_door: float  # seconds, inf when the ball is not closing on the door
    margin: float  # time_to_door - insert_duration, negative means too late


@dataclass(frozen=True)
class GateTriggerRule:
    """Commit the descent when the ball is inside and will stay in long enough.

    ``insert_duration`` is how long the seal takes once committed -- the descent
    plus whatever settling the caller counts as part of it. ``safety_margin`` is
    the slack demanded on top; it absorbs the difference between the commanded
    descent and what IK actually tracks, which on the comparable move in
    bar_through_hole ran to 7.5 mm.

    ``door_y`` and the sign convention: ``inward`` is +1 when inside is larger y
    and -1 when the `channel.open_end` mirror puts the closed box at smaller y
    (2026-09-09). A ball moving AWAY from the doorway is receding and has no
    deadline at all; which sign of ``ball_vy`` that is depends on the mirror,
    which is the only reason this rule needs to know about it.
    """

    door_y: float
    insert_duration: float
    safety_margin: float = 0.15
    inward: float = 1.0
    # Free-rolling probe (2026-09-10): the ball bounces off the far wall at
    # ``restitution`` times its speed instead of being turned round by a drive,
    # so a ball heading AWAY from the door is on a deadline after all -- over to
    # the wall at v, back at e v. ``turn_depth`` is how far in that wall is.
    restitution: float = 0.0
    turn_depth: float = 0.0
    # Below this the reading is a contact artefact, not a speed (see `decide`).
    velocity_floor: float = 0.05

    def decide(self, ball_y: float, ball_vy: float, elapsed_s: float = 0.0,
               ball_vy_prev: float | None = None) -> GateTriggerDecision:
        del elapsed_s  # the oracle reads the ball, not the clock
        depth = self.inward * (float(ball_y) - float(self.door_y))
        inside = depth > 0.0
        # A speed that fell by more than half since the last sample is a wall
        # impact being resolved, not a speed (measured 2026-09-10: three free-
        # rolling cells sealed on such a sample -- 0.06-0.1 m/s read at the far
        # wall, above a fixed floor, and distance / speed made a 2 s margin out
        # of a 0.5 s one). Same discriminator the bounce stand-in uses.
        if (inside and ball_vy_prev is not None
                and abs(float(ball_vy_prev)) >= self.velocity_floor
                and abs(float(ball_vy)) < 0.5 * abs(float(ball_vy_prev))):
            return GateTriggerDecision(commit=False, reason="inside_velocity_unreadable",
                                       inside=True, time_to_door=float("inf"),
                                       margin=float("-inf"))

        if not inside:
            return GateTriggerDecision(
                commit=False,
                reason="ball_outside",
                inside=False,
                time_to_door=float("inf"),
                margin=float("inf"),
            )

        distance = depth
        v_in = self.inward * float(ball_vy)
        if self.restitution > 0.0 and self.turn_depth > 0.0:
            # Wall bounce instead of a drive: exact kinematics on a flat box.
            if v_in > self.velocity_floor:
                time_to_door = (self.turn_depth - distance) / v_in + self.turn_depth / (
                    self.restitution * v_in
                )
                reason = "inside_returns_in_time"
            elif v_in < -self.velocity_floor:
                time_to_door = distance / -v_in
                reason = "inside_with_margin"
            else:
                # Stopped, or as good as: the ball is mid-impact against the
                # wall (the solver reports a step or two of near-zero velocity
                # while the contact resolves, before the bounce is written) --
                # or it has died there, which `moving_at_cap` rules out. Either
                # way distance / speed says nothing; wait for a real velocity.
                return GateTriggerDecision(commit=False, reason="inside_velocity_unreadable",
                                           inside=True, time_to_door=float("inf"),
                                           margin=float("-inf"))
            margin = time_to_door - float(self.insert_duration)
            if margin >= float(self.safety_margin):
                return GateTriggerDecision(commit=True, reason=reason, inside=True,
                                           time_to_door=time_to_door, margin=margin)
            return GateTriggerDecision(commit=False, reason="too_late_to_seal", inside=True,
                                       time_to_door=time_to_door, margin=margin)
        if v_in >= 0.0:
            # Receding, or momentarily at rest at the top of the return ramp.
            # There is no deadline until it turns around, and by then it has to
            # cross this whole distance again -- so commit now, with the most
            # margin the episode will ever offer.
            return GateTriggerDecision(
                commit=True,
                reason="inside_and_receding",
                inside=True,
                time_to_door=float("inf"),
                margin=float("inf"),
            )

        time_to_door = distance / abs(float(ball_vy))
        margin = time_to_door - float(self.insert_duration)
        if margin >= float(self.safety_margin):
            return GateTriggerDecision(
                commit=True,
                reason="inside_with_margin",
                inside=True,
                time_to_door=time_to_door,
                margin=margin,
            )
        return GateTriggerDecision(
            commit=False,
            reason="too_late_to_seal",
            inside=True,
            time_to_door=time_to_door,
            margin=margin,
        )


@dataclass(frozen=True)
class GreedyTriggerRule:
    """The scripted baseline: commit as soon as the arm is in position.

    Kept here beside the oracle rather than written into a demo, because a
    contrast pair is only meaningful if both sides come from the same place and
    are held to the same interface. This one ignores the ball entirely, which is
    the point: it fails whenever the arm arrives before the ball does, and the
    randomized release makes that half the episodes.
    """

    def decide(self, ball_y: float, ball_vy: float, elapsed_s: float = 0.0,
               ball_vy_prev: float | None = None) -> GateTriggerDecision:
        del ball_vy_prev  # the contrast rules do not read the ball's speed at all
        del ball_y, ball_vy, elapsed_s
        return GateTriggerDecision(
            commit=True,
            reason="greedy_no_wait",
            inside=False,
            time_to_door=float("inf"),
            margin=float("inf"),
        )


@dataclass(frozen=True)
class FixedDelayRule:
    """The other scripted baseline: commit at a fixed time after the episode starts.

    What a policy that memorised one instance's timeline would do. With the
    release point and the ball's speed drawn per episode this constant is right
    on some instances and wrong on the rest, which is what the timing axis is
    for. ``elapsed_s`` is the caller's clock from the episode's start (the arm's
    time to station plus the hover so far).
    """

    delay_s: float

    def decide(self, ball_y: float, ball_vy: float, elapsed_s: float = 0.0,
               ball_vy_prev: float | None = None) -> GateTriggerDecision:
        del ball_vy_prev  # the contrast rules do not read the ball's speed at all
        del ball_y, ball_vy
        due = float(elapsed_s) >= float(self.delay_s)
        return GateTriggerDecision(
            commit=due,
            reason="fixed_delay_due" if due else "fixed_delay_waiting",
            inside=False,
            time_to_door=float("inf"),
            margin=float("inf"),
        )


def make_trigger_rule(mode: str, *, door_y: float, insert_duration: float,
                      safety_margin: float, fixed_delay_s: float, inward: float = 1.0,
                      restitution: float = 0.0, turn_depth: float = 0.0):
    """The three trigger rules by their ``run.trigger`` names."""

    if mode == "oracle":
        return GateTriggerRule(door_y=door_y, insert_duration=insert_duration,
                               safety_margin=safety_margin, inward=inward,
                               restitution=restitution, turn_depth=turn_depth)
    if mode == "greedy":
        return GreedyTriggerRule()
    if mode == "fixed_delay":
        return FixedDelayRule(delay_s=fixed_delay_s)
    raise ValueError(f"run.trigger={mode!r}; expected oracle, greedy or fixed_delay")

