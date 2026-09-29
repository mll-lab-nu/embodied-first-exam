"""Read-only management adapter for Genesis 1.2.1 PBD birth visual bindings.

No engine import/initialization, stepping, rebinding or state writes. Private
field access stays here. Unknown buffer layouts fail rather than reconstructing
an approximate nearest-neighbour table. Birth XYZ is deliberately kept separate
from current particle state: a post-step read must not mix the two.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from topogym.utils.arrays import to_numpy


@dataclass(frozen=True)
class PBDVisualBinding:
    particle_birth_positions_m: np.ndarray
    visual_birth_positions_m: np.ndarray
    support_indices: np.ndarray
    support_weights: np.ndarray
    particle_start: int
    vvert_start: int
    backend_schema: str = "genesis_1.2.1_pbd_vverts_info_v1"

    @property
    def sha256(self):
        """Entity-local identity, independent of other entities' global offsets."""
        digest = hashlib.sha256(self.backend_schema.encode("ascii"))
        for array in (self.particle_birth_positions_m, self.visual_birth_positions_m,
                      self.support_indices, self.support_weights):
            digest.update(str((array.shape, array.dtype.str)).encode("ascii"))
            digest.update(array.tobytes(order="C"))
        return digest.hexdigest()


def read_birth_visual_binding(entity):
    """Capture copied entity-local birth buffers after scene.build().

    Supported schema: flat global VxK support tables, entity-local birth Nx3
    particles and Vx3 visual vertices. Batched *live* positions are not consumed.
    This helper is not exposed through the operator interaction API.
    """
    try:
        ps, vs = entity.particle_start, entity.vvert_start
        npart, nvis = entity.n_particles, entity.n_vverts
        info = entity.solver.vverts_info
        indices = to_numpy(info.support_idxs.to_numpy())
        weights = to_numpy(info.support_weights.to_numpy())
        particles = to_numpy(entity._particles)
        visual = to_numpy(entity._vverts)
    except AttributeError as exc:
        raise RuntimeError("Unsupported/unbuilt Genesis PBD visual-binding schema") from exc
    offsets = (ps, vs, npart, nvis)
    if (any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)) for x in offsets)
            or min(ps, vs) < 0 or min(npart, nvis) <= 0):
        raise RuntimeError("Invalid PBD entity ranges or no visual binding")
    if (indices.ndim != 2 or indices.dtype.kind not in "iu" or not indices.shape[1]
            or weights.shape != indices.shape or vs+nvis > len(indices)
            or particles.shape != (npart, 3) or visual.shape != (nvis, 3)):
        raise RuntimeError("Unsupported Genesis PBD visual-binding buffer shapes")
    indices = indices[vs:vs+nvis]
    if (indices < ps).any() or (indices >= ps+npart).any():
        raise ValueError("Visual support references a particle outside this entity")
    # Cast before subtraction so unsigned buffers cannot silently wrap around.
    indices = indices.astype(np.int64)-ps
    weights = weights[vs:vs+nvis].copy()
    if not all(np.isfinite(a).all() for a in (particles, visual, weights)):
        raise ValueError("Nonfinite PBD birth visual-binding data")
    for array in (particles, visual, indices, weights):
        array.setflags(write=False)
    return PBDVisualBinding(particles, visual, indices, weights, int(ps), int(vs))
