"""Grasp-band attachment for FEM ropes under the IPC coupler.

The FEM analog of ``ParticleAttachment`` (primitives/attachment.py), with a
deliberately smaller surface. ParticleAttachment writes particle positions into
the PBD solver every step and then patches around the fallout -- taper weights,
``ramp_to``, ``zero_velocity`` all exist because a position write manufactures
velocity (``v = (pos - ipos)/dt``) and overrides contact. Here the band is
driven through IPC's ``SoftPositionConstraint``: targets are a *goal* in the
Newton solve, alongside elasticity and the contact barrier, so none of those
patches apply. If the target is unreachable without penetration, the rope
stops -- that difference is the point of the migration.

Contract: constraint capacity is declared pre-build (``FEMRopeAttachment`` must
be constructed before ``scene.build()``); attach / drive / release are runtime.
Translation-only drive, like ParticleAttachment's ``drive_to``; orientation
ramps are not carried over until a task needs them.
"""

from __future__ import annotations

import numpy as np

from topogym.world.genesis_ipc_vertex_constraints import follow_near
from topogym.world.rope import tensor_to_numpy


def _positions(entity) -> np.ndarray:
    pos = tensor_to_numpy(entity.get_state().pos)
    return pos[0] if pos.ndim == 3 else pos


class FEMRopeAttachment:
    """Drive a band of FEM rope vertices toward a moving grasp point.

    ``center`` / ``radius`` select the band (resolved against the tet mesh's
    spawn positions at build time -- surface-mesh indices do not carry over to
    the FEM vertex set, tetgen inserts Steiner points).
    """

    def __init__(self, entity, center, radius: float, *, strength: float = 100.0) -> None:
        self.entity = entity
        self._handle = follow_near(entity, center, radius, strength=strength)
        self._offsets: np.ndarray | None = None
        self.active = False

    @property
    def indices(self) -> np.ndarray:
        return self._handle.verts

    def attach(self, center=None) -> np.ndarray:
        """Capture the band's current shape; start driving. Returns the center used.

        ``center`` defaults to the band centroid. Offsets captured here are held
        rigidly (translation-only) for the life of the grasp, same as
        ``ParticleAttachment``'s anchor offsets.
        """

        positions = _positions(self.entity)[self.indices]
        center = positions.mean(axis=0) if center is None else np.asarray(center, dtype=float)
        self._offsets = positions - center[None, :]
        self._handle.engage(positions.astype(np.float64))
        self.active = True
        return center

    def drive_to(self, center) -> None:
        if not self.active or self._offsets is None:
            raise RuntimeError("attach() before drive_to().")
        center = np.asarray(center, dtype=np.float64)
        self._handle.update_targets(center[None, :] + self._offsets)

    def band_center(self) -> np.ndarray:
        return _positions(self.entity)[self.indices].mean(axis=0)

    def release(self) -> None:
        self._handle.release()
        self.active = False
