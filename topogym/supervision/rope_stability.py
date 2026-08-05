"""Runtime blow-up detection for PBD ropes.

A diverging PBD body is easy to miss in a log and easy to misread in the viewer:
the render mesh is skinned onto the particles, so a handful of escaped particles
drag their triangles across the whole domain and the rope *looks* like one
infinite straight line while most of it is still fine. This measures the thing
directly instead -- how far each particle is from where its own rope actually is.

Lives in supervision because it is a runtime health monitor, not a task-node
judgement (see docs/develop/framework/module_boundaries_zh.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParticleSpacingReport:
    """How the rope's particle spacing compares to the PBD collision diameter.

    PBD keeps particle centres at least ``particle_size`` apart. A tetrahedralized
    tube, though, has its own built-in spacing: the ring of vertices around the
    centreline sits at a chord of ``2 * radius * sin(pi / radial_segments)``. When
    that chord is smaller than ``particle_size``, every ring violates the collision
    constraint from step zero, and can never stop violating it -- the stretch
    constraints hold the ring together at the mesh spacing while collision pushes
    the same particles apart. The two fight every step, forever.

    That makes it a *continuous* energy source rather than a transient one, which
    is the thing worth knowing: transient energy (a spawn drop) decays and can be
    damped away, this cannot.
    """

    strand_index: int
    particle_count: int
    min_spacing: float
    median_spacing: float
    particle_size: float
    violating_fraction: float

    @property
    def is_consistent(self) -> bool:
        return self.violating_fraction < 0.01

    def __str__(self) -> str:
        return (
            f"strand{self.strand_index} n={self.particle_count} "
            f"spacing min={self.min_spacing * 1000:.2f}mm "
            f"median={self.median_spacing * 1000:.2f}mm "
            f"vs particle_size={self.particle_size * 1000:.2f}mm "
            f"violating={self.violating_fraction * 100:.0f}%"
        )


def particle_spacing_reports(rope_scene, *, particle_size: float) -> tuple[ParticleSpacingReport, ...]:
    """Measure nearest-neighbour spacing per strand against the collision diameter."""

    out: list[ParticleSpacingReport] = []
    for strand_index in sorted(rope_scene.strand_entities):
        positions = rope_scene.strand_particles(strand_index)
        # O(n^2) on ~1k particles is a few milliseconds and this runs once.
        delta = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
        np.fill_diagonal(delta, np.inf)
        nearest = delta.min(axis=1)
        out.append(
            ParticleSpacingReport(
                strand_index=int(strand_index),
                particle_count=int(len(positions)),
                min_spacing=float(nearest.min()),
                median_spacing=float(np.median(nearest)),
                particle_size=float(particle_size),
                violating_fraction=float((nearest < float(particle_size)).mean()),
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class RopeBlowUp:
    """How far one strand's particles have strayed from its own centerline."""

    strand_index: int
    max_offset: float  # metres from the fitted centerline
    outlier_count: int  # particles beyond `tolerance`
    at_arclength: float  # normalised position along the rope of the worst one

    def __str__(self) -> str:
        return (
            f"strand{self.strand_index} max_offset={self.max_offset * 1000:.1f}mm "
            f"outliers={self.outlier_count} at_s={self.at_arclength:.2f}"
        )


def rope_blow_ups(rope_scene, *, tolerance: float, samples: int = 80) -> tuple[RopeBlowUp, ...]:
    """Report strands with particles further than ``tolerance`` from their centerline.

    A healthy particle sits within about the tube radius of the centerline. One
    that is centimetres away has been given an impulse the solver could not
    resolve. Reporting the arc length of the worst offender is the useful part:
    it says *where* the rope is being torn -- at the welded grasp band, at the
    anchor, or somewhere the gripper touched it.
    """

    out: list[RopeBlowUp] = []
    for strand_index in sorted(rope_scene.strand_entities):
        centerline = rope_scene.strand_centerline(strand_index, samples=samples)
        positions = rope_scene.strand_particles(strand_index)
        arclength = rope_scene.particle_arclength[strand_index]
        # Each particle's expected place is the centerline point at its own arc
        # length; the centerline is itself a mean of particles, so a single wild
        # particle barely moves the reference it is being compared against.
        expected = centerline[
            np.clip(
                (arclength * (len(centerline) - 1)).round().astype(int),
                0,
                len(centerline) - 1,
            )
        ]
        offset = np.linalg.norm(positions - expected, axis=1)
        worst = int(np.argmax(offset))
        if float(offset[worst]) > float(tolerance):
            out.append(
                RopeBlowUp(
                    strand_index=int(strand_index),
                    max_offset=float(offset[worst]),
                    outlier_count=int((offset > float(tolerance)).sum()),
                    at_arclength=float(arclength[worst]),
                )
            )
    return tuple(out)
