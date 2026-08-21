"""Push the carriage along its rail and report how far it got.

docx 4.4's physical recheck asks whether the two assemblies really became one.
Component B is a carriage on a rail, so that question has a direct reading: can
it still travel? Merged, it cannot -- the beam is pinned to A at one end and
welded to the carriage at the other, and at the seat the beam lies along the rail,
so moving the carriage outward by d would need the beam's end to move outward by
d, and the beam's end can only travel on a circle. Not merged, the carriage runs
to the far end of its travel.

The reading is the prismatic joint's own position, which is exact and needs no
frame conversion, and it is bounded by the rail: "went nowhere" against "ran to
the stop" rather than a displacement whose size depends on how hard the probe
pushed. The rail must not lie along the tangent of the pin's circle, or the two
constraints meet at a shallow angle and the lock is soft -- `LinkbarMergeLayout`
derives the rail from the catch's angle so it is always radial.

A force rather than a written velocity or an `AttachmentManager` carry: both of
those impose the motion instead of asking for it, so they would move the carriage
whether or not anything held it, and the probe would always report failure to
merge. Genesis clears external forces every step, so the push is re-applied each
step.

Nothing here belongs to an episode: the arm is clear and no action explains the
carriage moving. Same status as `gate_cage_ball`'s shake test.
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


@dataclass(frozen=True)
class TravelResult:
    """One travel test: how hard the carriage was pushed, and how far it moved."""

    force: float
    steps: int
    travel: float
    peak_travel: float
    limit: float

    @property
    def reached_stop(self) -> bool:
        """Did it run out the whole rail? The unambiguous "not merged" reading."""

        return bool(self.peak_travel >= 0.95 * self.limit)

    def to_info(self) -> dict[str, Any]:
        return {
            "travel_force": float(self.force),
            "travel_steps": int(self.steps),
            "travel": float(self.travel),
            "peak_travel": float(self.peak_travel),
            "travel_limit": float(self.limit),
            "reached_stop": bool(self.reached_stop),
        }


def travel_probe(scene, entity, *, dof: int, link_idx: int, direction, mass: float,
                 force_scale: float, steps: int, limit: float,
                 settle_steps: int = 0) -> TravelResult:
    """Push ``entity``'s carriage along ``direction`` at ``force_scale`` times its weight.

    ``force_scale`` is written as a multiple of weight so the probe means the same
    thing when the carriage's mass changes. It only has to be enough to run a free
    carriage to its stop inside ``steps``; past that, more force changes nothing,
    because the rail bounds the answer.

    ``link_idx`` is the CARRIAGE's link, not the entity's base: the base is the
    rail and it is bolted to the table, so a push there goes into the ground.

    ``peak_travel`` is reported alongside the final position because a carriage
    that is held still gives a little under load, and the peak is the honest
    reading of how much.
    """

    force = float(force_scale) * float(mass) * GRAVITY
    push = force * np.asarray(direction, dtype=float).reshape(3)
    push = push.reshape(1, 3)

    for _ in range(int(settle_steps)):
        scene.step()

    def position() -> float:
        value = entity.get_dofs_position(dofs_idx_local=[int(dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    start = position()
    peak = 0.0
    for _ in range(int(steps)):
        scene.rigid_solver.apply_links_external_force(push, links_idx=[int(link_idx)])
        scene.step()
        peak = max(peak, abs(position() - start))
    return TravelResult(
        force=force,
        steps=int(steps),
        travel=float(abs(position() - start)),
        peak_travel=float(peak),
        limit=float(limit),
    )
