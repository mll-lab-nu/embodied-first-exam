"""Does the linkbar planner pin its shortcut baseline at chance? (docx 4.4)

Headless check, no Genesis and no GPU: `planning/linkbar_merge_components_planner.py`
is arithmetic on a layout, so the claim docx 4.4 rests on -- "turn to the nearest
catch" is right half the time -- can be settled here instead of in a 20-seed sweep.

The layout is stubbed rather than built. The rules only ever ask it four things,
and stubbing them is what lets the four instance combinations be written down
explicitly; the real `LinkbarMergeLayout`'s own arithmetic is checked against the
scene by the inspect demo, which is where it can be checked against physics.

    python tests/check_linkbar_planner.py

Prints one line per case and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from topogym.planning.linkbar_merge_components_planner import (  # noqa: E402
    LinkbarOracleRule,
    NearestSocketRule,
    make_linkbar_rule,
)


class StubLayout:
    """The four things a rule asks a layout, and nothing else."""

    def __init__(self, b1_deg: float, a2_deg: float, *, merging: str = "b1"):
        self.angles = {"b1": math.radians(b1_deg), "a2": math.radians(a2_deg)}
        self.owners = {"b1": "component_b", "a2": "component_a"}
        self._merging = merging
        self.arm_radius = 0.170
        self.capture_tolerance_xy = 0.015

    def target_angle(self, socket: str) -> float:
        return self.angles[socket]

    def merging_socket(self) -> str:
        return self._merging

    def socket_owner(self, socket: str) -> str:
        return self.owners[socket]

    def nearest_socket(self, angle: float) -> str:
        return min(self.angles, key=lambda name: abs(self.angles[name] - float(angle)))


# (b1 angle, a2 angle, which catch is the shorter turn from 0 degrees).
# Both signs of "which side B sits on" appear, crossed with both answers to "is B's
# catch the nearer one" -- that crossing is the point: it makes the nearer catch's
# identity independent of B's, which is what randomising the two angles buys.
CASES = (
    (55.0, -45.0, "a2"),
    (35.0, -60.0, "b1"),
    (-55.0, 45.0, "a2"),
    (-35.0, 60.0, "b1"),
)


def main() -> int:
    oracle = LinkbarOracleRule()
    baseline = NearestSocketRule()
    failures = []
    baseline_wins = 0

    for b1_deg, a2_deg, expected_nearest in CASES:
        layout = StubLayout(b1_deg, a2_deg)
        got_oracle = oracle.decide(layout, 0.0)
        got_baseline = baseline.decide(layout, 0.0)

        if got_oracle.target_socket != "b1":
            failures.append(f"oracle chose {got_oracle.target_socket!r} for b1={b1_deg}")
        if got_baseline.target_socket != expected_nearest:
            failures.append(
                f"baseline chose {got_baseline.target_socket!r}, expected "
                f"{expected_nearest!r} for b1={b1_deg} a2={a2_deg}"
            )
        # The turn must be the direct one. Sweeping the long way round would take
        # the pin through the other catch, and a jaw at pin height is a hard stop.
        if abs(got_oracle.sweep) > math.radians(180.0):
            failures.append(f"oracle swept the long way for b1={b1_deg}")
        if got_oracle.sweep_sign != (1 if b1_deg > 0 else -1):
            failures.append(f"oracle turned the wrong way for b1={b1_deg}")
        if not got_oracle.rotate:
            failures.append(f"oracle reported no turn needed for b1={b1_deg}")

        baseline_right = got_baseline.target_socket == "b1"
        baseline_wins += int(baseline_right)
        print(
            f"b1={b1_deg:+6.1f} a2={a2_deg:+6.1f} | oracle -> "
            f"{got_oracle.target_socket} ({math.degrees(got_oracle.sweep):+6.1f}deg) | "
            f"nearest_socket -> {got_baseline.target_socket} "
            f"({'merges' if baseline_right else 'cycle edge, fails'})",
            flush=True,
        )

    if baseline_wins != len(CASES) // 2:
        failures.append(
            f"nearest_socket succeeded on {baseline_wins}/{len(CASES)} cases; the "
            "contrast pair only pins it at chance if it is exactly half"
        )

    # An ownership map with no merging catch is a broken layout, not a hard episode.
    # The oracle has to say so rather than pick something.
    broken = StubLayout(55.0, -45.0)
    broken.owners["b1"] = "component_a"
    try:
        oracle.decide(broken, 0.0)
    except ValueError:
        pass
    else:
        failures.append("oracle accepted a layout whose merging catch belongs to A")

    try:
        make_linkbar_rule("fixed_direction")
    except ValueError:
        pass
    else:
        failures.append("make_linkbar_rule accepted an unknown mode")

    print(
        f"\nnearest_socket succeeded on {baseline_wins}/{len(CASES)} "
        f"({100.0 * baseline_wins / len(CASES):.0f}%), oracle on {len(CASES)}/{len(CASES)}",
        flush=True,
    )
    if failures:
        print("\n== failures ==", flush=True)
        for line in failures:
            print(f"  {line}", flush=True)
        return 1
    print("== pass ==", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
