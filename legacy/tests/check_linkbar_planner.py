"""Does the linkbar planner pin its shortcut baseline at chance? (docx 4.4, reworked)

Headless check, no Genesis and no GPU: `planning/linkbar_rotate_to_zone_planner.py`
is arithmetic on a layout, so the claim the task rests on -- "turn to the nearest
zone" is right half the time -- can be settled here instead of in a 20-seed sweep.

Two shortcuts have been retired from this file rather than merely renamed. Until
2026-09-08 the pin carried the target zone's colour and matching it WAS the answer;
that was replaced by a third colour on the pin, and a `NearestColourRule` control
lived here to show the score falling to chance. On 2026-09-09 the beam lost every
colour, so that rule has no input at all and is gone. What is left is the oracle's
two-step read -- the sentence names a colour, the picture says which zone wears it
-- checked here by giving the stub a paint assignment that moves independently of
which zone is the target.

The layout is stubbed rather than built. The rules only ever ask it five things,
and stubbing them is what lets the instance combinations be written down
explicitly; the real `LinkbarRotateLayout`'s own arithmetic is checked by
`tests/check_linkbar_zone_geometry.py`.

    python tests/check_linkbar_planner.py

Prints one line per case and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from topogym.planning.linkbar_rotate_to_zone_planner import (  # noqa: E402
    LinkbarOracleRule,
    NearestZoneRule,
    make_linkbar_rule,
)


class StubLayout:
    """The five things a rule asks a layout, and nothing else."""

    def __init__(self, c1_deg: float, c2_deg: float, *, target: str, c1_paint: str = "red"):
        self.angles = {"color_1": math.radians(c1_deg), "color_2": math.radians(c2_deg)}
        self._target = target
        # Which zone wears which paint. Two colours, one each, so the oracle's
        # lookup from the instruction's colour word back to a zone is a real step
        # here and not an identity.
        self.paint = {
            "color_1": c1_paint,
            "color_2": "blue" if c1_paint == "red" else "red",
        }
        self.zone_half_width = math.radians(8.0)

    def target_angle(self, zone: str) -> float:
        return self.angles[zone]

    def target_zone(self) -> str:
        return self._target

    def target_colour(self) -> str:
        return self.paint[self._target]

    def zone_for_colour(self, colour: str) -> str:
        return next(zone for zone, paint in self.paint.items() if paint == colour)

    def nearest_zone(self, angle: float) -> str:
        return min(self.angles, key=lambda name: abs(self.angles[name] - float(angle)))


# (color_1 angle, color_2 angle, target zone, which zone is the shorter turn from
# 0 deg, which colour color_1 wears). Opposite-side and same-side pairs both
# appear, crossed with both answers to "is the target the nearer one" -- that
# crossing is the point: it makes the nearer zone's identity independent of which
# zone is the target, so the baseline is right exactly half the time. On the
# same-side cases the oracle's turn to the far zone passes over the near one; the
# verifier reads only where the pin rests, so that is not a wrong answer.
# The fifth entry crosses the paint assignment against everything else, the way
# the yaml's two independent axes do: the oracle has to land on the target zone
# whether the target is the red one or the blue one.
CASES = (
    (-45.0, 55.0, "color_2", "color_1", "red"),
    (-60.0, 35.0, "color_2", "color_2", "blue"),
    (30.0, 60.0, "color_2", "color_1", "red"),
    (30.0, 60.0, "color_1", "color_1", "blue"),
    (-60.0, -30.0, "color_1", "color_2", "red"),
    (-60.0, -30.0, "color_2", "color_2", "blue"),
)


def main() -> int:
    oracle = LinkbarOracleRule()
    baseline = NearestZoneRule()
    failures = []
    baseline_wins = 0

    for c1_deg, c2_deg, target, expected_nearest, c1_paint in CASES:
        layout = StubLayout(c1_deg, c2_deg, target=target, c1_paint=c1_paint)
        got_oracle = oracle.decide(layout, 0.0)
        got_baseline = baseline.decide(layout, 0.0)

        if got_oracle.target_zone != target:
            failures.append(f"oracle chose {got_oracle.target_zone!r} for target={target}")
        if got_baseline.target_zone != expected_nearest:
            failures.append(
                f"baseline chose {got_baseline.target_zone!r}, expected "
                f"{expected_nearest!r} for color_1={c1_deg} color_2={c2_deg}"
            )
        # The turn must be the direct one, never the long way round the circle.
        if abs(got_oracle.sweep) > math.radians(180.0):
            failures.append(f"oracle swept the long way for target={target}")
        target_deg = c1_deg if target == "color_1" else c2_deg
        if got_oracle.sweep_sign != (1 if target_deg > 0 else -1):
            failures.append(f"oracle turned the wrong way for target={target}")
        if not got_oracle.rotate:
            failures.append(f"oracle reported no turn needed for target={target}")

        baseline_right = got_baseline.target_zone == target
        baseline_wins += int(baseline_right)
        print(
            f"color_1={c1_deg:+6.1f}/{layout.paint['color_1']:4s} "
            f"color_2={c2_deg:+6.1f}/{layout.paint['color_2']:4s} target={target:7s} "
            f"({layout.target_colour()}) | oracle -> "
            f"{got_oracle.target_zone} ({math.degrees(got_oracle.sweep):+6.1f}deg) | "
            f"nearest_zone -> {got_baseline.target_zone} "
            f"({'right zone' if baseline_right else 'wrong zone, fails'})",
            flush=True,
        )

    if baseline_wins != len(CASES) // 2:
        failures.append(
            f"nearest_zone succeeded on {baseline_wins}/{len(CASES)} cases; the "
            "contrast pair only pins it at chance if it is exactly half"
        )
    # Both paint assignments have to appear, or the oracle's colour lookup was
    # never asked to do anything: with red always on color_1, "go to red" and
    # "go to color_1" cannot be told apart.
    if len({c1_paint for *_, c1_paint in CASES}) != 2:
        failures.append("every case paints color_1 the same colour; the lookup is untested")

    # Already inside the target zone: the oracle must say "no turn" rather than
    # command a sweep smaller than the zone.
    parked = oracle.decide(StubLayout(-45.0, 55.0, target="color_2"), math.radians(52.0))
    if parked.rotate:
        failures.append("oracle asked for a turn from inside the target zone")

    try:
        make_linkbar_rule("nearest_socket")
    except ValueError:
        pass
    else:
        failures.append("make_linkbar_rule accepted an unknown mode")

    print(
        f"\nnearest_zone succeeded on {baseline_wins}/{len(CASES)} "
        f"({100.0 * baseline_wins / len(CASES):.0f}%), "
        f"oracle on {len(CASES)}/{len(CASES)}",
        flush=True,
    )
    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
