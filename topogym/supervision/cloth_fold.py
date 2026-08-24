"""Did the cloth solver diverge during a fold? Runtime watch, not success judging.

Success lives in `verification/cloth_fold_verifier.py`. This answers a different
question: is what the solver produced physics at all. A diverged episode has to
be dropped rather than scored, because its readings are meaningless in either
direction.

**The ceiling is set by gravity, not by how fast the hand moves.** That is the
whole design, and it was learned the expensive way. Deriving the limit from the
commanded rate looks obviously right and is wrong: measured across three carry
durations, the cloth's peak speed did not fall when the hand slowed down, it ROSE
(0.41 / 0.79 / 0.99 m/s at 240 / 600 / 1200 steps), because a slower carry leaves
the unsupported part of the sheet falling for longer. A hand-derived ceiling
therefore tightens exactly where the cloth is legitimately moving fastest, and
2026-08-20 it aborted two folds that were 99% complete and both of the deliberate
wrong-motion runs.

What a sheet may honestly do in one step is fall: a point released at the arc's
apex reaches sqrt(2*g*h), about 1.6 m/s from 138 mm, so roughly 16 mm a step. A
real divergence is nothing like that -- PBD blow-ups reach tens or hundreds of
m/s, park particles at the solver's domain corner, or produce NaN.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from topogym.supervision.pbd_probe import probe_particles
from topogym.verification.cloth_fold_verifier import grid_neighbours, stretch_report


@dataclass
class ClothFoldWatch:
    """Per-step divergence check over a PBD cloth.

    Records the FIRST trip and the phase it happened in. Later trips are ignored:
    once a solve has diverged everything after it is downstream of the same
    event, and overwriting left the 2026-08-19 summary reporting step 1201 when
    things first went wrong at 1191.
    """

    cloth: object
    table_z: float
    dt: float
    #: Height the carried material can fall from -- the arc's radius.
    fall_height: float
    gravity: float = 9.81
    #: Multiple of the free-fall step the sheet may exceed before this counts.
    disp_ratio: float = 3.0
    max_speed: float = 3.0
    min_z_below: float = -0.005
    phase: str = "start"
    #: Rest positions. Given, the watch also tracks how far the material gets
    #: from inextensible WHILE IT IS BEING CARRIED, which is where a cloth that
    #: stretches is most visible and where the end-state reading cannot see it
    #: (by then the crease dominates the maximum).
    rest_nodes: object = None
    #: Neighbour index pairs for the stretch reading. ``None`` derives them from
    #: the particle count, which only works on a square sheet; a band has to hand
    #: its own in (`cloth_unpleat_verifier.rect_grid_neighbours`).
    pairs: object = None

    _previous: np.ndarray = field(init=False)
    worst_step_disp: float = field(default=0.0, init=False)
    worst_speed: float = field(default=0.0, init=False)
    lowest_z: float = field(default=float("inf"), init=False)
    #: Where and when the deepest particle was, recorded alongside `lowest_z`.
    #: A single worst-case number cannot say whether material dips as it lands,
    #: as it is dragged, or only under the gripper, and those want different
    #: answers -- so the position and the step are kept with it.
    lowest_xy: tuple[float, float] = field(default=(float("nan"), float("nan")), init=False)
    lowest_step: int = field(default=-1, init=False)
    lowest_phase: str = field(default="", init=False)
    #: How many particles were below the table at the worst moment for it.
    below_count: int = field(default=0, init=False)
    tripped: str | None = field(default=None, init=False)
    tripped_phase: str | None = field(default=None, init=False)
    worst_stretch_mean: float = field(default=float("nan"), init=False)
    worst_stretch_max: float = field(default=float("nan"), init=False)
    _pairs: object = field(default=None, init=False)

    def __post_init__(self) -> None:
        # Copied: `probe_particles` may hand back a view, and a view would track
        # the live state and make every step's displacement read zero.
        self._previous = np.array(probe_particles(self.cloth), copy=True)
        if self.rest_nodes is not None:
            self._pairs = (
                grid_neighbours(len(np.asarray(self.rest_nodes)))
                if self.pairs is None
                else self.pairs
            )
            self.worst_stretch_mean = 0.0
            self.worst_stretch_max = 0.0

    @property
    def limit(self) -> float:
        """Metres a particle may move in one step before this counts as broken."""

        free_fall = float(
            np.sqrt(2.0 * abs(self.gravity) * max(self.fall_height, 1e-9))
        ) * float(self.dt)
        return float(self.disp_ratio) * free_fall

    def check(self, step: int) -> str | None:
        current = probe_particles(self.cloth)
        if not np.all(np.isfinite(current)):
            self._record(f"nan_at_step={step}")
            return self.tripped
        displacement = float(np.linalg.norm(current - self._previous, axis=1).max())
        speed = displacement / max(float(self.dt), 1e-9)
        lowest = float(current[:, 2].min()) - float(self.table_z)
        self._previous = np.array(current, copy=True)
        self.worst_step_disp = max(self.worst_step_disp, displacement)
        self.worst_speed = max(self.worst_speed, speed)
        if lowest < self.lowest_z:
            self.lowest_z = lowest
            deepest = int(np.argmin(current[:, 2]))
            self.lowest_xy = (float(current[deepest, 0]), float(current[deepest, 1]))
            self.lowest_step = int(step)
            self.lowest_phase = str(self.phase)
        self.below_count = max(
            self.below_count, int(np.count_nonzero(current[:, 2] < float(self.table_z)))
        )
        if self._pairs is not None:
            stretch = stretch_report(self.rest_nodes, current, self._pairs)
            self.worst_stretch_mean = max(self.worst_stretch_mean, stretch["mean"])
            self.worst_stretch_max = max(self.worst_stretch_max, stretch["max"])

        if self.tripped is not None:
            return self.tripped
        if displacement > self.limit:
            self._record(f"step_disp={displacement:.4f}>{self.limit:.4f}@{step}")
        elif speed > float(self.max_speed):
            self._record(f"speed={speed:.3f}>{float(self.max_speed):.3f}@{step}")
        elif lowest < float(self.min_z_below):
            self._record(f"below_table={lowest:.4f}<{float(self.min_z_below):.4f}@{step}")
        return self.tripped

    def _record(self, message: str) -> None:
        if self.tripped is None:
            self.tripped = message
            self.tripped_phase = self.phase

    @property
    def diverged(self) -> bool:
        return self.tripped is not None

    def summary(self) -> str:
        return (
            f"worst_step_disp={self.worst_step_disp:.5f} "
            f"disp_limit={self.limit:.5f} "
            f"worst_speed={self.worst_speed:.3f} "
            + (
                ""
                if self._pairs is None
                else f"carry_stretch_mean={self.worst_stretch_mean:.3f} "
                f"carry_stretch_max={self.worst_stretch_max:.3f} "
            )
            + f"lowest_z_above_table={self.lowest_z:+.5f} "
            f"lowest_at=({self.lowest_xy[0]:+.3f},{self.lowest_xy[1]:+.3f})"
            f"@{self.lowest_step}/{self.lowest_phase or '?'} "
            f"worst_below_count={self.below_count} "
            f"blowup={self.tripped or 'none'}"
            + ("" if self.tripped is None else f" blowup_phase={self.tripped_phase}")
        )


def watch_steps(watch: ClothFoldWatch, scene, steps: int, *, offset: int = 0) -> None:
    """Step the scene, checking after each one."""

    for index in range(1, max(0, int(steps)) + 1):
        scene.step()
        watch.check(offset + index)
