"""Genesis FEM materials, explicit volume assets and bounded state queries."""

from pathlib import Path
import numpy as np
from topogym.assets.materials import MaterialSpec
from topogym.utils.arrays import to_numpy


def material(parameters):
    MaterialSpec("fem_elastic", parameters)
    import genesis as gs

    return gs.materials.FEM.Elastic(**dict(parameters))


def read_vertices(entity):
    state = entity.get_state()
    try:
        return dict(
            position_m=to_numpy(state.pos).reshape(-1, 3),
            velocity_m_s=to_numpy(state.vel).reshape(-1, 3),
            active=to_numpy(state.active),
            material_s_m=entity.material_coordinates[:, 0].copy(),
            vertex_indices=np.arange(entity.n_vertices, dtype=np.int32),
        )
    finally:
        entity._queried_states.discard(state)


def add_volume(scene, spec, morph, physical_material, surface):
    """Scoped Genesis 1.2.1 entity factory; never alters global engine classes.

    Genesis' public Mesh path always invokes a tetrahedralizer. The supplied
    NPZ already has conforming elements and material coordinates, so only the
    sampling step is overridden. All registration still uses Scene.add_entity.
    """
    from genesis.engine.entities.fem_entity import FEMEntity

    with np.load(Path(spec.volume_path), allow_pickle=False) as data:
        rest, spawn, elements = (
            data[key].copy() for key in ("rest", "spawn", "elements")
        )
        elastic_rest = data["elastic_rest"].copy() if "elastic_rest" in data else rest.copy()
    if rest.ndim != 2 or rest.shape[1] != 3 or spawn.shape != rest.shape:
        raise ValueError(
            "FEM rest and spawn coordinates must have matching (N, 3) shapes"
        )
    if (
        elements.ndim != 2
        or elements.shape[1] != 4
        or not len(elements)
        or elements.dtype.kind not in "iu"
        or elements.min() < 0
        or elements.max() >= len(rest)
    ):
        raise ValueError("FEM elements must contain four valid integer vertex indices")
    if tuple(spec.quaternion_wxyz) != (1.0, 0.0, 0.0, 0.0):
        raise ValueError("Explicit FEM volume currently requires identity orientation")
    spawn += np.asarray(spec.position_m)
    if elastic_rest.shape != rest.shape:
        raise ValueError("Elastic rest coordinates must match material coordinates")
    if not all(np.isfinite(v).all() for v in (rest, spawn, elastic_rest)):
        raise ValueError("FEM volume must be finite")
    for vertices in (rest, spawn, elastic_rest):
        corners = vertices[elements]
        if np.any(np.linalg.det(corners[:, 1:] - corners[:, :1]) <= 0):
            raise ValueError("FEM tetrahedra must have strictly positive volume")

    class VolumeEntity(FEMEntity):
        def sample(self):
            self._uvs = None
            self.instantiate(spawn, elements)
            self.material_coordinates = rest.copy()
            self.elastic_reference_coordinates = elastic_rest.copy()

    solver = scene.sim.fem_solver
    original = solver.add_entity

    def factory(idx, material, morph, surface, name=None):
        # Pinned upstream FEMSolver.add_entity registration, with the entity
        # type as the only difference. Restore the bound method in finally.
        existing = next((mat for mat in solver._mats if material == mat), None)
        solver._mats.append(material)
        if existing is not None:
            material.idx = existing.idx
        else:
            material.idx = len(solver._mats_idx)
            solver._mats_idx.append(material.idx)
            solver._mats_update_stress.append(material.update_stress)
            solver._mats_compute_energy_gradient_hessian.append(
                material.compute_energy_gradient_hessian
            )
            solver._mats_compute_energy.append(material.compute_energy)
        entity = VolumeEntity(
            scene=scene,
            solver=solver,
            material=material,
            morph=morph,
            surface=surface,
            idx=idx,
            v_start=solver.n_vertices,
            el_start=solver.n_elements,
            s_start=solver.n_surfaces,
            name=name,
        )
        solver._entities.append(entity)
        return entity

    solver.add_entity = factory
    try:
        return scene.add_entity(
            morph, material=physical_material, surface=surface, name=spec.name
        )
    finally:
        solver.add_entity = original
