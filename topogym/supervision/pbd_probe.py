"""Per-step PBD diagnostic probes: the machinery, shared.

Both rope demos grew their own probe (``CableRoutingProbe``,
``UntangleProbe`` -- the latter's docstring says outright that it follows the
former's precedent), and both reimplemented the same skeleton: wrap
``scene.step``, sample every N steps, print one line, restore the original step
on the way out. That skeleton and the handful of PBD measurements every rope
probe wants live here; the fields worth printing stay with each task, because
those genuinely differ (cable watches pole wrap and hand stall, untangle watches
finger distance and endpoint compression).

Lives in supervision because this is runtime observation -- see
docs/develop/framework/module_boundaries_zh.md.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# `PBDOptions.upper_bound` default. A particle clamped here has already left the
# solver domain: the classic Genesis PBD blow-up signature is a particle parked
# at the corner with jump=0 afterwards, dragging its skinned triangles across the
# whole scene so the rope *renders* as one infinite straight beam. Detecting it
# by position is far more reliable than eyeballing the viewer.
DOMAIN_CORNER = np.array([100.0, 100.0, 100.0])


def probe_particles(entity: Any) -> np.ndarray:
    """``(P, 3)`` particle positions as plain NumPy, batch dimension dropped."""

    particles = entity.get_particles_pos()
    if hasattr(particles, "detach"):
        particles = particles.detach().cpu().numpy()
    particles = np.asarray(particles, dtype=float)
    if particles.ndim == 3:
        particles = particles[0]
    return particles


def probe_velocities(entity: Any) -> np.ndarray:
    """``(P, 3)`` particle velocities as plain NumPy, batch dimension dropped.

    The `probe_particles` counterpart. Split out because the velocity read was
    written inline without the `.cpu()` hop, so on a CUDA backend every call
    raised and the whole column read `nan` for a full run before anyone noticed.
    """

    velocities = entity.get_particles_vel()
    if hasattr(velocities, "detach"):
        velocities = velocities.detach().cpu().numpy()
    velocities = np.asarray(velocities, dtype=float)
    if velocities.ndim == 3:
        velocities = velocities[0]
    return velocities


def ejected_mask(positions: np.ndarray, *, tolerance: float = 1.0) -> np.ndarray:
    """Which particles have been parked at the solver domain corner."""

    return np.linalg.norm(np.asarray(positions, dtype=float) - DOMAIN_CORNER, axis=1) < tolerance


def max_particle_jump(previous: np.ndarray | None, current: np.ndarray, *, every: int) -> float:
    """Largest per-step particle displacement between two samples (m/step).

    NaN when the two samples are not comparable, which is what a caller should
    print rather than a fabricated zero.
    """

    if previous is None or previous.shape != current.shape:
        return float("nan")
    return float(np.max(np.linalg.norm(current - previous, axis=1))) / max(1, int(every))


class StepProbe:
    """Sample the scene every ``every`` physics steps by wrapping ``scene.step``.

    Subclasses implement ``_sample``. Installing on construction and restoring in
    ``uninstall`` mirrors what both existing probes did; keeping it in one place
    means a probe cannot leak a wrapped ``scene.step`` past its own lifetime.
    """

    #: Exposed on the class so subclasses can write ``self.DOMAIN_CORNER``.
    DOMAIN_CORNER = DOMAIN_CORNER

    def __init__(self, scene: Any, *, every: int) -> None:
        self.scene = scene
        self.every = max(1, int(every))
        self.count = 0
        self._orig_step = scene.step
        # Bind once and keep the reference. `self._wrapped_step` builds a *new*
        # bound-method object on every attribute access, so the identity test in
        # `uninstall` below would never match one taken later and the probe would
        # stay installed forever -- which is how a closed trace ended up still
        # being called from a keep-open loop.
        self._installed = self._wrapped_step
        scene.step = self._installed

    def _wrapped_step(self, *args, **kwargs):
        result = self._orig_step(*args, **kwargs)
        self.count += 1
        if self.count % self.every == 0:
            self._sample()
        return result

    def _sample(self) -> None:
        raise NotImplementedError

    def uninstall(self) -> None:
        # Only unwrap if nothing else wrapped on top of us; otherwise removing our
        # link would drop theirs too. Subclasses that hold resources should also
        # go inert on close so a probe left in the chain cannot fail.
        if self.scene.step is self._installed:
            self.scene.step = self._orig_step

    def __enter__(self) -> StepProbe:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.uninstall()
