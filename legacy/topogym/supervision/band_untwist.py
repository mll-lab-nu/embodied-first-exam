"""Runtime health reporting for band_untwist.

Task-specific log lines, per
docs/develop/framework/module_boundaries_zh.md (`supervision/<task>.py`). Shared
by the inspect demo and the pinch demo so a full run and an isolated look report
the same numbers in the same words.
"""

from __future__ import annotations

#: The leaves each shape reads from its own ``band.<shape>`` block, in print order.
_SHAPE_LEAVES = {
    "eight": ("over_end", "half_angle_deg", "closed_lobe_radius", "open_lobe_radius", "end_gap"),
    "six": ("short_over", "half_angle_deg", "loop_radius", "short_len", "stem_len"),
    "twist": ("over_end_x1", "over_end_x2", "half_angle_deg", "closed_lobe_radius", "middle_lobe_radius",
              "open_lobe_radius", "end_gap"),
    "curls": ("stub_side", "half_angle_deg", "loop_radius", "stub_len", "middle_len"),
}


def variant_line(task_cfg, layout, *, seed: int) -> str:
    """One parseable line with the drawn shape and every leaf it reads, plus
    the plan's length and highest hand. The variation sweep parses it from both
    demos; the other shapes' blocks are drawn too but not read, so not printed."""

    band = task_cfg.band
    shape = str(band.shape)
    block = band[shape]
    leaves = " ".join(f"{name}={block[name]}" for name in _SHAPE_LEAVES[shape])
    plan = layout.plan()
    moves = len(plan.moves) if plan is not None else 0
    lift = plan.max_hand_height if plan is not None and plan.moves else float("nan")
    return (
        f"band_untwist variant seed={int(seed)} shape={shape} heading={float(band.heading_deg):+.1f} "
        f"cx={float(band.center_x):+.4f} cy={float(band.center_y):+.4f} {leaves} "
        f"crossings={len(layout.declared_sequence()) // 2} planned={moves} lift_pred={lift:.3f}"
    )


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
