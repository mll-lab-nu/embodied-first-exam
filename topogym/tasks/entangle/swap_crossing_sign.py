"""docx 3.2 -- swap which of two cables lies on top at their crossing.

The scene is the continuous-untangle scene, unchanged. That is not a shortcut:
`untangle_continuous`'s frozen config is already `braid.n_strands: 2` /
`braid.length: 1`, i.e. exactly two cables crossing exactly once, anchored at one
end and free at the other. Nothing about this task's *scene* differs -- what
differs is the goal and the predicate:

    untangle_continuous   crossing count 1 -> 0        (take them apart)
    swap_crossing_sign    crossing count stays 1,
                          over/under swaps              (change who is on top)

So the scene classes here are aliases, not subclasses. Splitting the ~800 lines
of scene construction into a near-identical copy would buy nothing today; the
buildout plan says the same thing (`docs/develop/tasks/task_environment_buildout_zh.md`
§5.1: reuse the builder, split it out if and when the configs actually diverge).
The task still gets its own module because the task id has to resolve to a file
under `tasks/<category>/` -- that is how `core/taxonomy.py` classifies tasks.

What *is* task-specific lives in the two layers that own it:

    verification/swap_crossing_sign_verifier.py   the terminal predicate
    planning/swap_crossing_sign_planner.py        the two-move oracle
    configs/task_configs/swap_crossing_sign_topogym_tabletop_v1.yaml

**Deviation from the docx, recorded here because it is a design decision.** The
docx describes one action: lift the upper cable's free end and pass it back on
the other side of the lower one. On a flat table that is not realizable -- a rope
can be laid *onto* another rope, never threaded *underneath* it, so releasing the
upper cable always leaves it on top again and the sign never flips. This task
therefore uses two moves: take the upper cable off (the crossing goes to zero),
then lay the other one across it. The state change the docx asks for -- crossing
count 1 with the sign flipped -- is reached; what is lost is the docx's stricter
"start and end geometry are nearly identical" property, since the cable that was
moved aside stays where it was put. The verifier compensates by requiring that
the scene actually passed through a fully separated state (see
`SwapCrossingSignPuzzleState.separated_seen`), so the terminal predicate still
carries a path component instead of grading the final layout alone.
"""

from __future__ import annotations

from .untangle_continuous import (
    UntangleContinuousLayout as SwapCrossingSignLayout,
    UntangleContinuousScene as SwapCrossingSignScene,
    UntangleContinuousSceneBuilder as SwapCrossingSignSceneBuilder,
    settle_scene,
)


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled. The
    rows are the shared layout's ``checks()`` (see
    `_swap_crossing_sign_geometry.braid_checks`).
    """

    SwapCrossingSignLayout(task_cfg).validate()


__all__ = [
    "SwapCrossingSignLayout",
    "SwapCrossingSignScene",
    "SwapCrossingSignSceneBuilder",
    "settle_scene",
    "validate_task_cfg",
]
