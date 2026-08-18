"""Which way should the flap go?

Everything else in docx 4.3 is a fixed motion: the arm takes the lever, sweeps
an arc, lets go. The only decision is the target angle, and it depends on two
things -- the instruction, and where the flap currently is. That decision is this
module, and it is arithmetic on those two, so it needs no Genesis and is
unit-testable.

Two rules with one interface, so the contrast pair is honest, the same shape
`gate_cage_ball_planner` uses for its trigger rules:

    DiverterOracleRule    read the instruction and the flap, seal the other side
    FixedDirectionRule    always drive to the same seat, ignoring the instruction

`FixedDirectionRule` is the scripted baseline docx 4.3's anti-shortcut is aimed
at. It wins exactly the instances where its fixed seat happens to be the one
asked for -- half of them, once the instruction and the initial phase are drawn
independently. Keeping it beside the oracle rather than in a demo is what makes
that a measurement instead of an assertion.

**Not rotating is a real decision, not a no-op.** When the flap already routes to
the commanded side the correct action is to leave it alone, and half the 2x2
instances are like that. A rule that always rotates gets those wrong, which is
the point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiverterRotateCommand:
    """What to do with the flap this episode."""

    commanded_side: str
    start_angle: float
    target_angle: float
    rotate: bool
    reason: str


@dataclass(frozen=True)
class DiverterOracleRule:
    """Seal whichever branch is not the one asked for."""

    def decide(self, layout, current_angle: float, commanded_side: str) -> DiverterRotateCommand:
        current_angle = float(current_angle)
        side = str(commanded_side)
        target = float(layout.target_angle(side))
        already = layout.open_side_at(current_angle)
        return DiverterRotateCommand(
            commanded_side=side,
            start_angle=current_angle,
            target_angle=current_angle if already == side else target,
            rotate=already != side,
            reason="already_open" if already == side else "rotate_to_seal_other",
        )


@dataclass(frozen=True)
class FixedDirectionRule:
    """Always drive to the same seat, whatever the instruction says.

    ``seal_side`` is the branch this rule always seals, so it always feeds the
    other one. It is a property of the baseline, not of the scene.
    """

    seal_side: str = "right"

    def decide(self, layout, current_angle: float, commanded_side: str) -> DiverterRotateCommand:
        current_angle = float(current_angle)
        target = float(layout.seat_angle(self.seal_side))
        sealed = layout.sealed_side_at(current_angle)
        return DiverterRotateCommand(
            commanded_side=str(commanded_side),
            start_angle=current_angle,
            target_angle=target,
            rotate=sealed != self.seal_side,
            reason="fixed_seat_already" if sealed == self.seal_side else "fixed_seat_rotate",
        )


def make_rule(mode: str):
    """`run.oracle_mode` -> rule."""

    mode = str(mode)
    if mode == "oracle":
        return DiverterOracleRule()
    if mode == "fixed_direction":
        return FixedDirectionRule()
    raise ValueError(f"Unknown oracle_mode={mode!r}; expected 'oracle' or 'fixed_direction'.")
