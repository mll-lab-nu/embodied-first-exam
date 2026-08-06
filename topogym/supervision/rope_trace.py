"""Per-step rope state trace, written to a file for post-mortem reading.

A PBD blow-up is only *visible* several steps after it starts, and by then the
scene tells you nothing about the cause -- a few escaped particles have dragged
their skinned triangles across the domain and everything looks equally broken.
Reproducing it in a viewer to watch more carefully costs a full GPU run each
time, which is a slow way to test a hypothesis.

So this streams the metrics that discriminate between the known failure modes to
a text file, one line per sample, **flushed every write** so a hard solver crash
still leaves the history on disk. The interesting part is always the handful of
lines *before* the first EVENT line.

Columns are chosen to separate the mechanisms this repo has actually hit:

- ``bend_r``  smallest local bend radius of the rope's centreline. Genesis
  excludes same-body neighbours from self-collision by rest distance only
  (``rest_dist > particle_size``), so a rope bent tighter than a threshold set by
  its own mesh spacing starts pushing its own inner side apart and fights the
  stretch constraints. If ``bend_r`` dives below that threshold just before an
  EVENT, that is the mechanism.
- ``max_v`` / ``jump``  a kinematic weld writing positions produces a velocity
  spike through PBD's ``vel = (pos - ipos)/dt`` reconstruction. A jump that
  appears in the same step as a hand motion points there instead.
- ``offset``  how far the worst particle has strayed from its own centreline:
  the blow-up itself, and what triggers the EVENT.
- ``parked``  particles clamped at the solver domain corner, i.e. already gone.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from .pbd_probe import DOMAIN_CORNER, StepProbe, probe_particles, probe_velocities


def min_bend_radius(polyline: np.ndarray) -> tuple[float, float]:
    """Tightest bend on a centreline: ``(radius_m, position)``.

    ``position`` is normalised arc length in [0, 1], and it is the more useful
    half. A tight bend at the grasp point, at the anchored end, and where the rope
    lifts off the table are three different problems with three different fixes,
    and the radius alone cannot tell them apart -- which is exactly the mistake of
    assuming where it was.
    """

    points = np.asarray(polyline, dtype=float)
    if len(points) < 3:
        return float("inf"), float("nan")
    a, b, c = points[:-2], points[1:-1], points[2:]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(c - a, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        radius = np.where(area > 1e-14, (ab * bc * ca) / (4.0 * np.maximum(area, 1e-14)), np.inf)
    worst = int(np.argmin(radius))
    return float(radius[worst]), float((worst + 1) / max(len(points) - 1, 1))


def _points_to_segments(points: np.ndarray, polyline: np.ndarray) -> float:
    """Smallest distance from any of ``points`` to any segment of ``polyline``."""

    start = polyline[:-1]
    direction = polyline[1:] - start
    length_sq = np.maximum(np.einsum("mj,mj->m", direction, direction), 1e-18)
    offset = points[:, None, :] - start[None, :, :]
    t = np.clip(np.einsum("nmj,mj->nm", offset, direction) / length_sq, 0.0, 1.0)
    closest = start[None, :, :] + t[:, :, None] * direction[None, :, :]
    return float(np.linalg.norm(points[:, None, :] - closest, axis=2).min())


def polyline_gap(a: np.ndarray, b: np.ndarray) -> float:
    """Smallest distance between two centreline polylines.

    Point-to-segment in both directions rather than point-to-point: the
    centrelines are sampled every ~7.5 mm, and the distances that matter here are
    8-12 mm, so nearest-sample would overstate the gap by a large fraction of the
    quantity being measured.
    """

    if len(a) < 2 or len(b) < 2:
        return float("nan")
    return min(_points_to_segments(a, b), _points_to_segments(b, a))


def height_over(a: np.ndarray, b: np.ndarray) -> float:
    """How far ``a`` sits above ``b`` where the two centrelines come closest.

    The sign is the whole point: it says which rope is on top at the place they
    are actually interacting. Watching it across a run answers "did the two ropes
    stay in the same over/under relationship" directly, without re-running the
    crossing detector every step -- a sign flip is a rope having passed through
    the other one.
    """

    if len(a) < 1 or len(b) < 2:
        return float("nan")
    start = b[:-1]
    direction = b[1:] - start
    length_sq = np.maximum(np.einsum("mj,mj->m", direction, direction), 1e-18)
    offset = a[:, None, :] - start[None, :, :]
    t = np.clip(np.einsum("nmj,mj->nm", offset, direction) / length_sq, 0.0, 1.0)
    closest = start[None, :, :] + t[:, :, None] * direction[None, :, :]
    distance = np.linalg.norm(a[:, None, :] - closest, axis=2)
    i, j = np.unravel_index(int(np.argmin(distance)), distance.shape)
    return float(a[i, 2] - closest[i, j, 2])


class RopeTrace(StepProbe):
    """Stream per-strand rope health to a file, flagging the first blow-up."""

    # A tightening bend is the signal; the absolute minimum is not. Measured on
    # run #8: `bend_r` sat at 4.6-4.9mm for 380 steps without incident, then fell
    # monotonically to 3.8mm over 136 steps and the solver lost half the strand in
    # a single step. A run that blew up at 6.1mm minimum and one that survived
    # 4.4mm are both in the log, so no fixed floor separates them.
    #
    # Hence: warn when the bend is both tight *and* still closing, comparing
    # against a window rather than the previous sample -- consecutive-decreasing
    # never fires, because the per-sample values jitter (4.1, 4.2, 4.1, 4.0, ...).
    WARN_BEND_R = 0.008
    WARN_WINDOW = 40
    WARN_DROP = 0.95

    def __init__(
        self,
        rope_scene,
        path: Path | str,
        *,
        every: int = 1,
        offset_tolerance: float = 0.030,
        fixed_band: float = 0.0,
        rope_radius: float = 0.0,
        particle_size: float = 0.0,
        status: dict | None = None,
        notes: str = "",
    ) -> None:
        super().__init__(rope_scene.scene, every=every)
        self.rope_scene = rope_scene
        self.offset_tolerance = float(offset_tolerance)
        self.fixed_band = float(fixed_band)
        self.rope_radius = float(rope_radius)
        self.particle_size = float(particle_size)
        self.status = status if status is not None else {}
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        self._previous: dict[int, np.ndarray] = {}
        self._baseline: dict[int, float] = {}
        self._bend_history: dict[int, deque] = {}
        self._bend_warned: set[int] = set()
        self._vel_failed: set[int] = set()
        self._trim: dict[int, int] = {}
        self._event_reported = False
        self._write(f"# untangle_continuous rope trace   every={every} steps")
        if notes:
            for line in notes.splitlines():
                self._write(f"# {line}")
        for line in self._centerline_scale_lines():
            self._write(f"# {line}")
        self._write(
            "# step phase strand max_v(m/s) jump(mm/step) offset(mm) bend_r(mm) "
            "bend_at(s) bend_free(mm) pair_gap(mm) over_z(mm) minz(mm) parked"
        )
        self._write(
            "# over_z = this strand's height above the nearest other one, at the point "
            "they come closest. Its SIGN is the over/under relationship; a sign flip "
            "means one rope passed through the other."
        )
        self._write(
            f"# pair_gap = smallest centreline distance to another strand. "
            f"{(2 * self.rope_radius + self.particle_size) * 1000:.0f}mm is the correct "
            f"resting value (2*radius + particle_size); {2 * self.rope_radius * 1000:.0f}mm is "
            f"surfaces just touching; below that the tubes overlap"
            if self.rope_radius > 0.0
            else "# pair_gap = smallest centreline distance to another strand"
        )

    def _centerline_scale_lines(self) -> list[str]:
        """What one `bend_r` reading means in degrees, recorded up front.

        `bend_r` is the circumradius of three consecutive centreline samples, so
        it only means something relative to how far apart those samples are:
        three points spaced L with a turn of theta between them give
        ``bend_r = L / (2 sin(theta/2))``. Reading run #8 cost an evening spent
        reverse-engineering L out of the `bend_at` column (it is neither the bin
        width nor the mesh segment length -- `strand_centerline` bins by arc
        length and drops empty bins). Writing it down turns that into a lookup.

        Also fixes how many samples `bend_free` drops from each end. Both ends of
        the rope are held: the anchored end by `fix_particles`, the free end by
        `fix_particles_to_link`. A centreline sample that averages held particles
        together with free ones sits on the seam between two different kinematic
        regimes, and its circumradius describes neither. `bend_free` is the same
        measurement restricted to samples that are entirely free, which is what
        separates a real kink in the rope from a reading produced by the seam.
        """

        lines = [
            "bend_r -> turn angle at that point: theta = 2*asin(L / (2*bend_r)), "
            "L = the centreline sample spacing below",
            "bend_free = the same minimum with the held bands at both ends dropped",
        ]
        for strand in sorted(self.rope_scene.strand_entities):
            centerline = self.rope_scene.strand_centerline(strand)
            spacing = np.linalg.norm(np.diff(centerline, axis=0), axis=1)
            median = float(np.median(spacing))
            trim = int(np.ceil(self.fixed_band / median)) if self.fixed_band > 0.0 else 0
            self._trim[strand] = trim
            lines.append(
                f"centreline s{strand}: {len(centerline)} samples over "
                f"{float(spacing.sum()) * 1000:.0f}mm, L={median * 1000:.2f}mm (median) "
                f"-> a right-angle corner reads as bend_r={median / np.sqrt(2.0) * 1000:.1f}mm; "
                f"bend_free drops {trim} sample(s) per end "
                f"(held band {self.fixed_band * 1000:.0f}mm)"
            )
        return lines

    def note(self, text: str) -> None:
        """Record a comment line, e.g. what the planner just decided to do."""

        for line in str(text).splitlines():
            self._write(f"# {line}")

    def _write(self, line: str) -> None:
        if self._file.closed:
            return
        self._file.write(line + "\n")
        # Flushed every line: a Genesis solver crash takes the process down with
        # it, and a buffered tail is exactly the part worth having.
        self._file.flush()

    def _sample(self) -> None:
        # Inert once closed: unwrapping can legitimately fail when something else
        # wrapped `scene.step` on top of us, and a stale probe must not take the
        # run down with it.
        if self._file.closed:
            return
        phase = str(self.status.get("phase", "-"))
        worst_offset = 0.0
        # Up front, so every row can report how close this strand is to the
        # nearest other one. Two tubes resting on each other belong at
        # `2 * radius + particle_size` between centrelines; anything less means
        # they overlap, and overlapping tubes are permanently in contact, so the
        # collision solver hands every motion of one straight to the other.
        centerlines: dict[int, np.ndarray] = {}
        for strand in sorted(self.rope_scene.strand_entities):
            try:
                centerlines[strand] = self.rope_scene.strand_centerline(strand)
            except Exception:
                continue

        # Node access goes through the scene's rope backend when it has one
        # (rope_backends protocol); scenes that have not been migrated keep the
        # direct PBD probe.
        backend = getattr(self.rope_scene, "rope_backend", None)
        for strand in sorted(self.rope_scene.strand_entities):
            entity = self.rope_scene.strand_entities[strand]
            positions = (
                np.asarray(backend.nodes(entity), dtype=float)
                if backend is not None
                else probe_particles(entity)
            )
            parked = int(
                (np.linalg.norm(positions - DOMAIN_CORNER, axis=1) < 1.0).sum()
            )
            previous = self._previous.get(strand)
            jump = (
                float(np.linalg.norm(positions - previous, axis=1).max())
                if previous is not None and previous.shape == positions.shape
                else float("nan")
            )
            self._previous[strand] = positions

            try:
                velocities = (
                    backend.node_velocities(entity)
                    if backend is not None
                    else probe_velocities(entity)
                )
                max_v = float(np.linalg.norm(velocities, axis=1).max())
            except Exception as error:
                # Say so once, in the file. Run #8 has `max_v` as `nan` for all
                # 2453 lines and nobody noticed until the column was needed --
                # and it is the column that would have shown the position-write
                # velocity amplification directly instead of via `jump`.
                max_v = float("nan")
                if strand not in self._vel_failed:
                    self._vel_failed.add(strand)
                    self._write(
                        f"# NOTE s{strand}: get_particles_vel() raised "
                        f"{type(error).__name__}: {error} -- the max_v column is nan for this strand"
                    )

            # Live particles only: a parked particle sits at (100,100,100) and
            # would swamp every geometric statistic below.
            live = positions[np.linalg.norm(positions - DOMAIN_CORNER, axis=1) >= 1.0]
            if len(live) < 3:
                self._write(
                    f"{self.count:6d} {phase:<14} s{strand} PARKED_ALL parked={parked}"
                )
                continue

            centerline = centerlines.get(strand)
            if centerline is None:
                continue
            others = [(polyline_gap(centerline, other), index)
                      for index, other in centerlines.items() if index != strand]
            if others:
                pair_gap, nearest_strand = min(others)
                over_z = height_over(centerline, centerlines[nearest_strand])
            else:
                pair_gap = over_z = float("nan")
            expected = centerline[
                np.clip(
                    (self.rope_scene.particle_arclength[strand] * (len(centerline) - 1))
                    .round()
                    .astype(int),
                    0,
                    len(centerline) - 1,
                )
            ]
            offset = float(np.linalg.norm(positions - expected, axis=1).max())
            # Compare against this strand's own first sample, not against zero. A
            # healthy rope already sits tens of mm off its binned centreline
            # (tube radius, plus how coarsely 80 bins fit an arching crossing), so
            # an absolute threshold fires on step 1 and marks the spawn state as a
            # blow-up. What identifies a real one is the *growth*.
            baseline = self._baseline.setdefault(strand, offset)
            worst_offset = max(worst_offset, offset - baseline)
            bend, bend_at = min_bend_radius(centerline)
            trim = self._trim.get(strand, 0)
            free = centerline[trim : len(centerline) - trim] if trim else centerline
            bend_free = min_bend_radius(free)[0] if len(free) >= 3 else float("nan")

            # `bend_at` is the column that stops the guessing: compare it to the
            # grasp arc length in the header. Near it -> the weld band. Near 0 ->
            # the anchored end, which is clamped hard and cannot be softened the
            # same way. Elsewhere -> the rope lifting off the table.
            self._write(
                f"{self.count:6d} {phase:<14} s{strand} "
                f"{max_v:9.4f} {jump * 1000:10.4f} {offset * 1000:9.2f} "
                f"{bend * 1000:9.1f} {bend_at:8.3f} {bend_free * 1000:10.1f} "
                f"{pair_gap * 1000:9.2f} {over_z * 1000:+8.2f} "
                f"{float(live[:, 2].min()) * 1000:8.2f} {parked:4d}"
            )
            self._check_tightening(strand, bend, bend_at, phase)

        if worst_offset > self.offset_tolerance and not self._event_reported:
            self._event_reported = True
            self._write(
                f"# EVENT step={self.count} phase={phase} "
                f"offset grew {worst_offset * 1000:.1f}mm above its spawn baseline, "
                f"tolerance={self.offset_tolerance * 1000:.1f}mm"
            )
            self._write("# ^^ read the lines above this one: the cause precedes the symptom")

    def _check_tightening(self, strand: int, bend: float, bend_at: float, phase: str) -> None:
        """Flag a bend that is both tight and still closing. Once per strand."""

        history = self._bend_history.setdefault(strand, deque(maxlen=self.WARN_WINDOW))
        was = max(history) if history else None
        history.append(bend)
        if strand in self._bend_warned or was is None:
            return
        if bend >= self.WARN_BEND_R or bend >= self.WARN_DROP * was:
            return
        self._bend_warned.add(strand)
        self._write(
            f"# WARN step={self.count} phase={phase} s{strand}: bend_r fell from "
            f"{was * 1000:.1f}mm to {bend * 1000:.1f}mm over the last {len(history)} samples, "
            f"at bend_at={bend_at:.3f}. In run #8 this preceded solver divergence by 387 steps."
        )

    def close(self) -> None:
        self.uninstall()
        if not self._file.closed:
            self._write("# trace ended")
            self._file.close()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
