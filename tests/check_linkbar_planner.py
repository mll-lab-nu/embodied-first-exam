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

    def __init__(self, c1_deg: float, c2_deg: float, *, target: str):
        self.angles = {"color_1": math.radians(c1_deg), "color_2": math.radians(c2_deg)}
        self._target = target
        self.zone_half_width = math.radians(8.0)

    def target_angle(self, zone: str) -> float:
        return self.angles[zone]

    def target_zone(self) -> str:
        return self._target

    def nearest_zone(self, angle: float) -> str:
        return min(self.angles, key=lambda name: abs(self.angles[name] - float(angle)))


# (color_1 angle, color_2 angle, target zone, which zone is the shorter turn from
# 0 deg). Opposite-side and same-side pairs both appear, crossed with both answers
# to "is the target the nearer one" -- that crossing is the point: it makes the
# nearer zone's identity independent of the pin's colour, which is what drawing
# the target independently of the two positions buys. On the same-side cases the
# oracle's turn to the far zone passes over the near one; the verifier reads only
# where the pin rests, so that is not a wrong answer.
CASES = (
    (-45.0, 55.0, "color_2", "color_1"),
    (-60.0, 35.0, "color_2", "color_2"),
    (30.0, 60.0, "color_2", "color_1"),
    (30.0, 60.0, "color_1", "color_1"),
    (-60.0, -30.0, "color_1", "color_2"),
    (-60.0, -30.0, "color_2", "color_2"),
)


def main() -> int:
    oracle = LinkbarOracleRule()
    baseline = NearestZoneRule()
    failures = []
    baseline_wins = 0

    for c1_deg, c2_deg, target, expected_nearest in CASES:
        layout = StubLayout(c1_deg, c2_deg, target=target)
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
            f"color_1={c1_deg:+6.1f} color_2={c2_deg:+6.1f} target={target:7s} | oracle -> "
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
        f"({100.0 * baseline_wins / len(CASES):.0f}%), oracle on {len(CASES)}/{len(CASES)}",
        flush=True,
    )
    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
