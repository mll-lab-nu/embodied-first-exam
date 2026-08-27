"""Does the linkbar planner pin its shortcut baseline at chance? (docx 4.4, reworked)

Headless check, no Genesis and no GPU: `planning/linkbar_rotate_to_zone_planner.py`
is arithmetic on a layout, so the claim the task rests on -- "turn to the nearest
zone" is right half the time -- can be settled here instead of in a 20-seed sweep.

The layout is stubbed rather than built. The rules only ever ask it four things,
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
    """The four things a rule asks a layout, and nothing else."""

    def __init__(self, left_deg: float, right_deg: float, *, target: str):
        self.angles = {"left": math.radians(left_deg), "right": math.radians(right_deg)}
        self._target = target
        self.zone_half_width = math.radians(8.0)

    def target_angle(self, zone: str) -> float:
        return self.angles[zone]

    def target_zone(self) -> str:
        return self._target

    def nearest_zone(self, angle: float) -> str:
        return min(self.angles, key=lambda name: abs(self.angles[name] - float(angle)))


# (left angle, right angle, target zone, which zone is the shorter turn from 0 deg).
# Both signs of "which side is left" appear, crossed with both answers to "is the
# target the nearer one" -- that crossing is the point: it makes the nearer zone's
# identity independent of the pin's colour, which is what drawing the target
# independently of the two angles buys.
CASES = (
    (55.0, -45.0, "left", "right"),
    (35.0, -60.0, "left", "left"),
    (-55.0, 45.0, "right", "right"),
    (-35.0, 60.0, "right", "left"),
)


def main() -> int:
    oracle = LinkbarOracleRule()
    baseline = NearestZoneRule()
    failures = []
    baseline_wins = 0

    for left_deg, right_deg, target, expected_nearest in CASES:
        layout = StubLayout(left_deg, right_deg, target=target)
        got_oracle = oracle.decide(layout, 0.0)
        got_baseline = baseline.decide(layout, 0.0)

        if got_oracle.target_zone != target:
            failures.append(f"oracle chose {got_oracle.target_zone!r} for target={target}")
        if got_baseline.target_zone != expected_nearest:
            failures.append(
                f"baseline chose {got_baseline.target_zone!r}, expected "
                f"{expected_nearest!r} for left={left_deg} right={right_deg}"
            )
        # The turn must be the direct one. Sweeping the long way round would take
        # the pin across the other zone.
        if abs(got_oracle.sweep) > math.radians(180.0):
            failures.append(f"oracle swept the long way for target={target}")
        target_deg = left_deg if target == "left" else right_deg
        if got_oracle.sweep_sign != (1 if target_deg > 0 else -1):
            failures.append(f"oracle turned the wrong way for target={target}")
        if not got_oracle.rotate:
            failures.append(f"oracle reported no turn needed for target={target}")

        baseline_right = got_baseline.target_zone == target
        baseline_wins += int(baseline_right)
        print(
            f"left={left_deg:+6.1f} right={right_deg:+6.1f} target={target:5s} | oracle -> "
            f"{got_oracle.target_zone} ({math.degrees(got_oracle.sweep):+6.1f}deg) | "
            f"nearest_zone -> {got_baseline.target_zone} "
            f"({'right colour' if baseline_right else 'wrong colour, fails'})",
            flush=True,
        )

    if baseline_wins != len(CASES) // 2:
        failures.append(
            f"nearest_zone succeeded on {baseline_wins}/{len(CASES)} cases; the "
            "contrast pair only pins it at chance if it is exactly half"
        )

    # Already inside the target zone: the oracle must say "no turn" rather than
    # command a sweep smaller than the zone.
    parked = oracle.decide(StubLayout(55.0, -45.0, target="left"), math.radians(52.0))
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
        f"({100.0 * baseline_wins / len(CASES):.0f}%), oracle on {len(CASES)}/{len(CASES)}",
        flush=True,
    )
    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
