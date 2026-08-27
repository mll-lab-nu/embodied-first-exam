"""Runtime health reporting for band_untwist.

Task-specific log lines, per
docs/develop/framework/module_boundaries_zh.md (`supervision/<task>.py`). Shared
by the inspect demo and the pinch demo so a full run and an isolated look report
the same numbers in the same words.
"""

from __future__ import annotations


def crossing_lines(state, *, rope_radius: float, d_hat: float) -> list[str]:
    """One line per measured self-crossing, flagging interpenetration.

    Under IPC two tubes resting on each other sit ``2 * radius + d_hat`` apart
    between centrelines; closer than that means the tubes overlap, which is what
    makes lifting one strand drag the other along.
    """

    resting_apart = 2.0 * float(rope_radius) + float(d_hat)
    lines = []
    for crossing in state.crossings:
        overlap = resting_apart - crossing.z_gap
        flag = f"   <<< INTERPENETRATING by {overlap * 1000:.1f}mm" if overlap > 0 else ""
        lines.append(
            f"  self-crossing over_end={crossing.over_end} (over_at={crossing.over_at:.2f} "
            f"under_at={crossing.under_at:.2f}) at xy=({crossing.position[0]:+.4f}, "
            f"{crossing.position[1]:+.4f}) z_gap={crossing.z_gap * 1000:.1f}mm "
            f"(resting apart = {resting_apart * 1000:.1f}mm) sign={crossing.sign:+d}{flag}"
        )
    return lines
