"""Push the freed C ring in every direction and report whether it actually leaves.

docx 3.4's physical recheck is "分离后 C 环可沿任意方向平移离开" -- after separation the
C ring can be translated away in any direction. That is a different question from the
topology reading, and it is the one the category contract
(`docs/develop/framework/task_taxonomy_zh.md` section 4.3) makes mandatory for C3.

**A force, not a written pose.** Writing a velocity, or carrying the ring with an
`AttachmentManager`, imposes the motion instead of asking for it: the ring would move
whether or not the closed ring still held it, and the probe would pass on every
episode. Genesis clears external forces each step, so the push is re-applied every
step. Same reasoning, and the same shape, as `tasks/connectivity/_travel_probe.py`.

**Every direction, because one is not evidence.** While the two rings are linked,
`tests/check_c_ring_clearance.py` measures each of these directions jamming on the
interlock by around 9 mm. Once unlinked they should all run free, and probing the same
set is what makes the before/after an actual comparison rather than two unrelated
numbers.

**Down is not in the set.** A ring that has been set down rests on the table, so
pushing it down moves it nowhere whether or not it is still linked -- the reading
carries no information about the interlock and only ever produces a false "blocked".
Measured 2026-08-22: 0.03 mm of travel down against 1-4 mm every other way, on a ring
the geometry agreed was free.

This lives in `tasks/` rather than `verification/` for the reason
`linkbar_merge_components_verifier.py:25` gives: only the caller can step physics, and
the verification package stays free of side effects. Nothing here belongs to the
episode -- the arm is clear and no action explains the ring moving.
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


def _pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def _quat(entity) -> np.ndarray:
    return _as_numpy(entity.get_quat()).reshape(-1, 4)[0].astype(float)


@dataclass(frozen=True)
class DirectionTravel:
    """How far the ring ran when pushed one way."""

    name: str
    travel: float
    peak_travel: float
    free_travel: float

    @property
    def free(self) -> bool:
        return bool(self.peak_travel >= self.free_travel)

    def to_info(self) -> dict[str, Any]:
        return {
            "direction": self.name,
            "travel": float(self.travel),
            "peak_travel": float(self.peak_travel),
            "free": self.free,
        }


@dataclass(frozen=True)
class FreeTranslationResult:
    """The whole probe: one push per direction, plus what it was pushed with."""

    directions: tuple[DirectionTravel, ...]
    force: float
    steps: int
    free_travel: float

    @property
    def all_free(self) -> bool:
        return bool(self.directions) and all(d.free for d in self.directions)

    @property
    def blocked(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.directions if not d.free)

    @property
    def min_peak_travel(self) -> float:
        return min((d.peak_travel for d in self.directions), default=0.0)

    def to_info(self) -> dict[str, Any]:
        return {
            "travel_force": float(self.force),
            "travel_steps": int(self.steps),
            "free_travel_threshold": float(self.free_travel),
            "all_free": self.all_free,
            "blocked_directions": list(self.blocked),
            "min_peak_travel": float(self.min_peak_travel),
            "directions": [d.to_info() for d in self.directions],
        }


def probe_directions(geometry) -> tuple[tuple[str, np.ndarray], ...]:
    """The six directions, named as the offline gate names them.

    Built from the layout rather than from world axes so they follow
    ``stand.hang_yaw_deg`` the way everything else in this task does.
    """

    along = np.asarray(geometry.tube_direction, dtype=float)
    across = np.cross(along, [0.0, 0.0, 1.0])
    return (
        ("along_bar", along),
        ("back_along_bar", -along),
        ("across_bar", across),
        ("back_across_bar", -across),
        ("up", np.array([0.0, 0.0, 1.0])),
    )


def free_translation_probe(
    scene,
    entity,
    *,
    link_idx: int,
    geometry,
    mass: float,
    force_scale: float,
    steps: int,
    free_travel: float,
    settle_steps: int = 0,
    on_step=None,
) -> FreeTranslationResult:
    """Push the ring once per direction, restoring its pose between pushes.

    ``force_scale`` is a multiple of the ring's own weight so the probe means the
    same thing if the ring's mass changes. It only has to be enough to move a free
    ring ``free_travel`` within ``steps``.

    ``peak_travel`` is reported next to the final displacement because a ring that is
    still caught gives a little under load before it stops, and the peak is the
    honest reading of how much.

    The pose is captured before the first push and written back between directions.
    That write is bookkeeping between measurements, not part of the demonstration --
    without it the six pushes compound and the ring is off the table by the fourth.
    The probe runs after the episode's manipulation is over, which is why the demo
    still declares ``runtime_set_pose=False``.

    ``on_step(force, travel)`` is called every step. A ring that is still held does
    not move, so without a live readout the probe looks exactly like nothing
    happening; the callback is how the applied force reaches the viewer.
    """

    force = float(force_scale) * float(mass) * GRAVITY
    for _ in range(int(settle_steps)):
        scene.step()

    home_pos, home_quat = _pos(entity), _quat(entity)
    results: list[DirectionTravel] = []

    for name, direction in probe_directions(geometry):
        entity.set_pos(tuple(float(v) for v in home_pos), zero_velocity=True)
        entity.set_quat(tuple(float(v) for v in home_quat), zero_velocity=True)
        push = (force * np.asarray(direction, dtype=float).reshape(3)).reshape(1, 3)
        start = _pos(entity)
        peak = 0.0
        for _ in range(int(steps)):
            scene.rigid_solver.apply_links_external_force(push, links_idx=[int(link_idx)])
            scene.step()
            moved = float(np.linalg.norm(_pos(entity) - start))
            peak = max(peak, moved)
            if on_step is not None:
                on_step(force, moved)
            # Stop pushing the moment the question is answered. Left to run the full
            # budget the push keeps accelerating a ring that is already free: measured
            # 2026-08-22 at force_scale 3.0, 3.6 METRES of travel in 60 steps, which is
            # 36 mm per step against a 5 mm tube. At that speed a still-linked ring
            # tunnels straight through the interlock and the probe reports it free --
            # which is exactly the `probe_uninformative` warning that fired. Cutting
            # out at the threshold bounds travel to roughly the threshold itself, so
            # the reading no longer depends on getting the force exactly right.
            if peak >= float(free_travel):
                break
        results.append(
            DirectionTravel(
                name=name,
                travel=float(np.linalg.norm(_pos(entity) - start)),
                peak_travel=peak,
                free_travel=float(free_travel),
            )
        )

    entity.set_pos(tuple(float(v) for v in home_pos), zero_velocity=True)
    entity.set_quat(tuple(float(v) for v in home_quat), zero_velocity=True)
    return FreeTranslationResult(
        directions=tuple(results),
        force=force,
        steps=int(steps),
        free_travel=float(free_travel),
    )
