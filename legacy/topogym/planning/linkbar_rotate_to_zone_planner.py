"""Which zone should the beam turn to? (docx 4.4, reworked)

Everything else in this task is one fixed motion: take the knob, sweep an arc, let
go. The only decision is which of the two zones to aim at, and the two are the
same paint at the same radius. What separates them is colour -- one red, one blue
-- and the SENTENCE names that colour. Nothing in the picture says which zone is
the target: since 2026-09-09 the beam carries no marker colour at all.

The decision is arithmetic on the layout, so this module needs no Genesis and is
unit-testable offline.

Two rules behind one interface, the shape `diverter_route_ball_planner` uses, so
the contrast baseline is a measurement rather than an assertion:

    LinkbarOracleRule   go to the zone painted the colour the instruction names
    NearestZoneRule     go to whichever zone is the shorter turn

`NearestZoneRule` wins exactly the instances where the nearer zone happens to be
the target -- half of them, once the two zone positions on the rail are drawn
independently of which one is the target. A `NearestColourRule` ("go to whichever
zone's paint is closest to the pin's") lived here until 2026-09-09; it was the
ORACLE until 2026-09-08, when the pin still carried the target zone's colour, and
was kept as a control while the pin had a third colour. The pin has no colour of
its own any more, so the rule has no input and is gone.

**The oracle reads a colour, not a zone key.** It asks the layout which colour the
instruction names and then looks up which zone is painted that colour -- the same
two steps a policy has to make. Reading `zones.target` directly would skip the
lookup, and hard-coding `"color_1"` would make the oracle right for a reason the
verifier does not use.

**The turn is the direct one.** The joint is continuous, so both zones are
reachable in either direction; the signed difference is used as-is rather than
wrapped into (-180, 180], which on a rail of +/-90 deg is always the short way.
When both zones sit on the same side of the beam and the target is the far one,
the pin does pass over the other zone on its way -- unavoidable, and harmless: the
verifier reads only where the pin rests after the release.
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
    """Turn to the zone painted the colour the instruction names."""

    def decide(self, layout, current_angle: float) -> LinkbarRotateCommand:
        zone = layout.zone_for_colour(layout.target_colour())
        return _command(layout, current_angle, zone, "read_instruction")


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
