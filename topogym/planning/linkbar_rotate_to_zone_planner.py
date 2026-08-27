"""Which zone should the beam turn to? (docx 4.4, reworked)

Everything else in this task is one fixed motion: take the knob, sweep an arc, let
go. The only decision is which of the two zones to aim at, and the two are the
same paint at the same radius costing the same sweep. What separates them is
colour, and the pin carries one of the two colours -- so that is what has to be
READ, and it is the whole reason the task is not solvable by looking at the zones.

The decision is arithmetic on the layout, so this module needs no Genesis and is
unit-testable offline.

Two rules behind one interface, the shape `diverter_route_ball_planner` uses, so
the contrast baseline is a measurement rather than an assertion:

    LinkbarOracleRule   read the pin's colour, go to the zone painted the same
    NearestZoneRule     go to whichever zone is the shorter turn

`NearestZoneRule` wins exactly the instances where the nearer zone happens to be
the pin's colour -- half of them, once the two zone angles are drawn independently
on either side of the start and the target is drawn independently of both.

**The oracle does not know the answer by name.** It asks the layout which zone the
pin's colour names, which is exactly the fact the verifier tests. Hard-coding
`"left"` here would make the oracle right for a reason the verifier does not use.

**The turn never takes the long way round.** The joint is continuous, so both zones
are reachable in either direction, but the far way sweeps the pin across the other
zone, which is the picture of a wrong answer even if it ends on the right one. The
signed difference is used as-is rather than wrapped into (-180, 180], which for a
layout `LinkbarRotateLayout.validate` accepts is always the direct path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkbarRotateCommand:
    """What to do with the beam this episode."""

    target_zone: str
    start_angle: float
    target_angle: float
    sweep: float
    rotate: bool
    reason: str

    @property
    def sweep_sign(self) -> int:
        """+1 for a counter-clockwise turn, -1 for clockwise, 0 for no turn."""

        if self.sweep > 0.0:
            return 1
        if self.sweep < 0.0:
            return -1
        return 0


def _command(layout, current_angle: float, zone: str, reason: str) -> LinkbarRotateCommand:
    current_angle = float(current_angle)
    target = float(layout.target_angle(zone))
    sweep = target - current_angle
    return LinkbarRotateCommand(
        target_zone=str(zone),
        start_angle=current_angle,
        target_angle=target,
        sweep=sweep,
        # Already inside the zone: no turn needed.
        rotate=abs(sweep) > float(layout.zone_half_width),
        reason=reason,
    )


@dataclass(frozen=True)
class LinkbarOracleRule:
    """Turn to the zone painted the pin's colour."""

    def decide(self, layout, current_angle: float) -> LinkbarRotateCommand:
        return _command(layout, current_angle, layout.target_zone(), "match_pin_colour")


@dataclass(frozen=True)
class NearestZoneRule:
    """Go to whichever zone is the shorter turn, whatever its colour.

    The shortcut this task is built to catch. It is a property of the baseline,
    not of the scene: it never looks at colour, so drawing the target independently
    of the two zone angles leaves it right half the time.
    """

    def decide(self, layout, current_angle: float) -> LinkbarRotateCommand:
        zone = layout.nearest_zone(float(current_angle))
        return _command(layout, current_angle, zone, "nearest_zone")


def make_linkbar_rule(mode: str):
    """`run.oracle_mode` -> rule."""

    mode = str(mode)
    if mode == "oracle":
        return LinkbarOracleRule()
    if mode == "nearest_zone":
        return NearestZoneRule()
    raise ValueError(
        f"Unknown oracle_mode={mode!r}; expected 'oracle' or 'nearest_zone'."
    )
