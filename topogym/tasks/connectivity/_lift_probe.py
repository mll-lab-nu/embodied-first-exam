"""Pull a body straight up and report how far it got.

docx 4.4's physical recheck is a lift test: with the beam latched into component
B's catch, B is part of one rigid assembly with a hinge that has no vertical
freedom, so it cannot rise; latched into A's own catch, or not latched at all, B
is a loose object and rises freely. The two outcomes differ by orders of
magnitude, which is what makes this a judge rather than a threshold to tune.

A force rather than a written velocity, and a force rather than an
`AttachmentManager` carry: both of those impose the motion instead of asking for
it, so they would lift B whether or not anything was holding it -- the probe would
always report success. Genesis clears external forces every step
(`RigidSolver.clear_external_force`), so the pull is re-applied each step.

Nothing here belongs to an episode: the arm is clear, no action explains B moving,
and the recording is expected to show the probe as a post-episode check. It is the
same status as `gate_cage_ball`'s shake test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

GRAVITY = 9.81


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _height(entity) -> float:
    return float(_as_numpy(entity.get_pos()).reshape(-1, 3)[0][2])


@dataclass(frozen=True)
class LiftResult:
    """One lift test: what was pulled, how hard, and how far it moved."""

    force: float
    steps: int
    delta_z: float
    peak_delta_z: float

    def to_info(self) -> dict[str, Any]:
        return {
            "lift_force": float(self.force),
            "lift_steps": int(self.steps),
            "lift_delta": float(self.delta_z),
            "lift_peak_delta": float(self.peak_delta_z),
        }


def lift_probe(scene, entity, *, mass: float, force_scale: float, steps: int,
               settle_steps: int = 0, link_idx: int | None = None) -> LiftResult:
    """Pull ``entity`` up at ``force_scale`` times its own weight for ``steps`` steps.

    ``force_scale`` is written as a multiple of weight so the probe means the same
    thing when the body's mass changes: 1.0 exactly cancels gravity and 3.0 gives a
    net 2 g upward, which clears a loose body off the table well inside 0.2 s.

    ``peak_delta_z`` is reported alongside the final height because a body that is
    held will still flex a little under load, and the peak is the honest reading of
    how much it gave.
    """

    if link_idx is None:
        link_idx = int(entity.base_link.idx)
    force = float(force_scale) * float(mass) * GRAVITY
    pull = np.array([[0.0, 0.0, force]], dtype=float)

    for _ in range(int(settle_steps)):
        scene.step()

    start = _height(entity)
    peak = 0.0
    for _ in range(int(steps)):
        scene.rigid_solver.apply_links_external_force(pull, links_idx=[int(link_idx)])
        scene.step()
        peak = max(peak, _height(entity) - start)
    return LiftResult(
        force=force,
        steps=int(steps),
        delta_z=float(_height(entity) - start),
        peak_delta_z=float(peak),
    )
