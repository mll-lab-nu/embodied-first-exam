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

    ``door_y`` and the sign convention: inside is larger y. A ball at larger y
    moving in +y is receding from the doorway and has no deadline at all.
    """

    door_y: float
    insert_duration: float
    safety_margin: float = 0.15

    def decide(self, ball_y: float, ball_vy: float) -> GateTriggerDecision:
        inside = float(ball_y) > float(self.door_y)
        if not inside:
            return GateTriggerDecision(
                commit=False,
                reason="ball_outside",
                inside=False,
                time_to_door=float("inf"),
                margin=float("inf"),
            )

        distance = float(ball_y) - float(self.door_y)
        if float(ball_vy) >= 0.0:
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

    def decide(self, ball_y: float, ball_vy: float) -> GateTriggerDecision:
        del ball_y, ball_vy
        return GateTriggerDecision(
            commit=True,
            reason="greedy_no_wait",
            inside=False,
            time_to_door=float("inf"),
            margin=float("inf"),
        )
