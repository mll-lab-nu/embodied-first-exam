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
    #: Census of WHERE the material is, sampled rather than every step. The
    #: task metrics are all summaries -- a span, a grid occupancy, a layer count
    #: -- and every one of them can read healthy while the sheet is somewhere
    #: else entirely. Measured 2026-08-25 on `cloth_unroll`: `spread_mm=263.5`
    #: over `covered_cells=522` with `gates=all_pass`, and the oblique camera
    #: showed no band on the table at all.
    #:
    #: `worst_gap` is a TEAR detector that survives remeshing. `stretch_*` needs
    #: vertex correspondence and Genesis does not preserve it (control 595 ->
    #: sim 2283), which is why those read nan on every run. Nearest-neighbour
    #: spacing needs no correspondence: at rest it is the mesh spacing, and a
    #: sheet pulled thin has neighbours further apart wherever it thinned.
    census_every: int = 50
    rest_spacing: float | None = None
    n_particles: int = field(default=0, init=False)
    n_far: int = field(default=0, init=False)
    bbox_lo: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), init=False)
    bbox_hi: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), init=False)
    worst_gap: float = field(default=0.0, init=False)
    worst_gap_ratio: float = field(default=0.0, init=False)
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
    #: **How much cloth was under the table, and for how long.**
    #:
    #: `lowest_z` and `below_count` are both PEAKS -- the deepest single particle
    #: ever, and the worst single instant. Neither says anything about duration,
    #: and a visual artifact is almost entirely about duration: a wide patch
    #: sitting 0.5 mm under for six seconds never beats a 2 mm spike that lasted
    #: one step, yet it is the one a viewer sees. Measured 2026-08-24:
    #: `cloth_unpleat` and `cloth_unroll` had near-identical peaks (2.12 vs
    #: 1.95 mm, 16 vs 14 particles) while only one of them looked wrong.
    #:
    #: `below_steps` is how many steps had ANY particle under the table;
    #: `below_particle_steps` is the running sum of the counts, i.e. area times
    #: duration; `below_by_phase` splits the first by phase so a settling
    #: transient and a whole carry are never confused again.
    below_steps: int = field(default=0, init=False)
    below_particle_steps: int = field(default=0, init=False)
    below_by_phase: dict = field(default_factory=dict, init=False)
    steps_seen: int = field(default=0, init=False)
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

    def _census(self, current: np.ndarray) -> None:
        self.n_particles = int(current.shape[0])
        # The PBD solver parks particles that leave its domain at a far corner
        # rather than clamping them per axis, so material that escapes does NOT
        # lower `lowest_z` -- it vanishes from every metric while still counting
        # toward the totals. 10 m is far outside any tabletop scene.
        far = np.linalg.norm(current, axis=1) > 10.0
        self.n_far = int(np.count_nonzero(far))
        keep = current[~far]
        if keep.size == 0:
            return
        self.bbox_lo = tuple(float(v) for v in keep.min(axis=0))
        self.bbox_hi = tuple(float(v) for v in keep.max(axis=0))
        # Nearest-neighbour spacing, on a subsample so the cost stays flat.
        # O(m^2) on m=400 is 160k distances, which is nothing next to a step.
        if keep.shape[0] > 400:
            idx = np.linspace(0, keep.shape[0] - 1, 400).astype(int)
            sample = keep[idx]
        else:
            sample = keep
        d = np.linalg.norm(sample[:, None, :] - sample[None, :, :], axis=2)
        np.fill_diagonal(d, np.inf)
        gap = float(d.min(axis=1).max())
        self.worst_gap = max(self.worst_gap, gap)
        if self.rest_spacing:
            self.worst_gap_ratio = self.worst_gap / float(self.rest_spacing)

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
        under = int(np.count_nonzero(current[:, 2] < float(self.table_z)))
        self.below_count = max(self.below_count, under)
        self.steps_seen += 1
        if self.census_every and self.steps_seen % int(self.census_every) == 1:
            self._census(current)
        if under:
            self.below_steps += 1
            self.below_particle_steps += under
            phase = str(self.phase) or "?"
            self.below_by_phase[phase] = self.below_by_phase.get(phase, 0) + 1
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
            + f"particles={self.n_particles} parked_outside={self.n_far} "
            f"bbox_x=[{self.bbox_lo[0]:+.3f},{self.bbox_hi[0]:+.3f}] "
            f"bbox_y=[{self.bbox_lo[1]:+.3f},{self.bbox_hi[1]:+.3f}] "
            f"bbox_z=[{self.bbox_lo[2]:+.3f},{self.bbox_hi[2]:+.3f}] "
            f"worst_gap_mm={self.worst_gap * 1e3:.1f}"
            + ("" if not self.rest_spacing else f" worst_gap_ratio={self.worst_gap_ratio:.2f}")
            + " "
            + f"lowest_z_above_table={self.lowest_z:+.5f} "
            f"lowest_at=({self.lowest_xy[0]:+.3f},{self.lowest_xy[1]:+.3f})"
            f"@{self.lowest_step}/{self.lowest_phase or '?'} "
            f"worst_below_count={self.below_count} "
            f"below_steps={self.below_steps}/{self.steps_seen} "
            f"below_particle_steps={self.below_particle_steps} "
            f"below_by_phase={{{','.join(f'{k}:{v}' for k, v in sorted(self.below_by_phase.items(), key=lambda kv: -kv[1]))}}} "
            f"blowup={self.tripped or 'none'}"
            + ("" if self.tripped is None else f" blowup_phase={self.tripped_phase}")
        )


def watch_steps(watch: ClothFoldWatch, scene, steps: int, *, offset: int = 0) -> None:
    """Step the scene, checking after each one."""

    for index in range(1, max(0, int(steps)) + 1):
        scene.step()
        watch.check(offset + index)
