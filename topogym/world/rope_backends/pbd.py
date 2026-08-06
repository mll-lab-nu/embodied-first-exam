"""PBD rope backend: the existing behavior, unchanged, behind the protocol.

Implementation bodies stay where they have always lived (``topogym/world/rope.py``);
this class is the protocol adapter over them. Behavior parity with the
pre-seam code is the whole point -- the phase-1 regression gate is that the
contact test still penetrates at step 1176 (run11) after the call sites switch
to this object.
"""

from __future__ import annotations

import numpy as np

from topogym.world.rope import (
    elastic_material,
    endpoint_particle_indices,
    pbd_options,
    tensor_to_numpy,
)


class PBDRopeBackend:
    name = "pbd"

    def __init__(self, rope_cfg) -> None:
        self.rope_cfg = rope_cfg
        # Pre-build declarations, keyed by entity uid; resolved post-build.
        self._anchors: dict[str, list[tuple[np.ndarray, float]]] = {}
        self._follows: dict[str, tuple[np.ndarray, float]] = {}

    # -- scene-level -----------------------------------------------------------

    def pre_scene(self) -> None:
        pass

    def scene_options(self) -> dict:
        return {"pbd_options": pbd_options(self.rope_cfg)}

    def material(self):
        return elastic_material(self.rope_cfg)

    def static_rigid_material(self):
        """None -> keep the Genesis default for fixed rigids (current behavior)."""

        return None

    def decoration_rigid_material(self):
        """None -> keep the Genesis default for collision-free fixtures."""

        return None

    # -- pre-build declarations ------------------------------------------------

    def declare_anchor(self, entity, centers, radius: float) -> None:
        store = self._anchors.setdefault(str(entity.uid), [])
        for center in np.atleast_2d(np.asarray(centers, dtype=float)):
            store.append((center.copy(), float(radius)))

    def declare_follow(self, entity, center, radius: float) -> None:
        self._follows[str(entity.uid)] = (
            np.asarray(center, dtype=float).copy(),
            float(radius),
        )

    # -- post-build ------------------------------------------------------------

    def resolve_indices(self, entity, centers, radius: float) -> list[int]:
        return endpoint_particle_indices(
            entity, np.atleast_2d(np.asarray(centers, dtype=float)), radius=radius
        )

    def anchor(self, entity) -> list[int]:
        selectors = self._anchors.get(str(entity.uid), [])
        indices: set[int] = set()
        for center, radius in selectors:
            indices.update(self.resolve_indices(entity, (center,), radius))
        indices = sorted(indices)
        if indices:
            entity.fix_particles(particles_idx_local=list(indices))
        return indices

    def follow_link(self, entity, link) -> list[int]:
        selector = self._follows.get(str(entity.uid))
        if selector is None:
            raise RuntimeError("declare_follow() was not called for this entity.")
        center, radius = selector
        indices = self.resolve_indices(entity, (center,), radius)
        entity.fix_particles_to_link(link.idx, particles_idx_local=list(indices))
        return indices

    # -- probes ----------------------------------------------------------------

    def nodes(self, entity) -> np.ndarray:
        positions = tensor_to_numpy(entity.get_particles_pos())
        return positions[0] if positions.ndim == 3 else positions

    def node_velocities(self, entity) -> np.ndarray:
        velocities = tensor_to_numpy(entity.get_particles_vel())
        return velocities[0] if velocities.ndim == 3 else velocities

    def zero_node_velocities(self, entity) -> None:
        count = len(self.nodes(entity))
        entity.set_particles_vel(
            np.zeros((count, 3), dtype=float),
            particles_idx_local=list(range(count)),
        )
