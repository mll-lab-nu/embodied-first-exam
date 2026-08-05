"""Runtime health reporting for the continuous Untangle task.

Task-specific metrics and log lines, per
docs/develop/framework/module_boundaries_zh.md (`supervision/<task>.py`). Shared
by the inspect demo and the pinch demo so a full run and an isolated look report
the same numbers in the same words.
"""

from __future__ import annotations

from .rope_stability import particle_spacing_reports


def rope_health_lines(rope_scene, *, particle_size: float) -> list[str]:
    """Whether each rope's own particle spacing can satisfy PBD self-collision.

    Worth printing before anything else: if the spacing is finer than the
    collision diameter, the solver is fighting itself on every step and the
    numbers that follow -- settling, crossing separation -- are all downstream of
    that. See `ParticleSpacingReport`.
    """

    lines = []
    for report in particle_spacing_reports(rope_scene, particle_size=particle_size):
        flag = "" if report.is_consistent else "   <<< SELF-COLLISION ALWAYS VIOLATED"
        lines.append(f"  spacing {report}{flag}")
    return lines


def crossing_lines(state, *, rope_radius: float, particle_size: float) -> list[str]:
    """One line per measured crossing, flagging interpenetration.

    Two ropes resting on each other settle at ``2 * radius + particle_size``
    between centrelines, not at ``2 * radius``: PBD collision separates particle
    *centres* by ``particle_size``, and each rope's surface particles already sit
    one radius out from its centreline. So a particle-diameter of daylight between
    the tubes is the correct resting state, not a defect.

    Closer than that means the tubes overlap, which is what makes lifting one rope
    drag the other along: overlapping ropes are permanently in contact, so the
    collision solver transmits every motion between them. That is geometric
    interlock, not friction -- worth stating in the log, because the instinct is
    to reach for the friction coefficients.
    """

    # NOTE: this is the separation collision *would* enforce if the particle
    # barrier were gap-free. It is not, at the mesh density this task has to run
    # at (see `rope.mesh.segment_length`'s comment for why it cannot be raised),
    # so a few mm below this is expected rather than alarming. What matters is
    # that the sign of the gap still reads which rope is on top.
    resting_apart = 2.0 * float(rope_radius) + float(particle_size)
    lines = []
    for crossing in state.crossings:
        overlap = resting_apart - crossing.z_gap
        flag = f"   <<< INTERPENETRATING by {overlap * 1000:.1f}mm" if overlap > 0 else ""
        lines.append(
            f"  crossing strand{crossing.over_strand} over strand{crossing.under_strand} "
            f"at xy=({crossing.position[0]:+.4f}, {crossing.position[1]:+.4f}) "
            f"z_gap={crossing.z_gap * 1000:.1f}mm (resting apart = "
            f"{resting_apart * 1000:.1f}mm){flag}"
        )
    return lines
