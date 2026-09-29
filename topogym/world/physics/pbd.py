"""Genesis PBD material construction; integration belongs to GenesisWorld."""

from topogym.assets.materials import MaterialSpec


def material(model, parameters):
    MaterialSpec(model, parameters)
    import genesis as gs

    constructors = {
        "pbd_cloth": gs.materials.PBD.Cloth,
        "pbd_elastic": gs.materials.PBD.Elastic,
    }
    if model not in constructors:
        raise ValueError(f"Not a PBD material: {model}")
    return constructors[model](**dict(parameters))


def bind_material_map(entity, path):
    """Bind actual birth particles to an explicit authored surface/UV archive.

    Coordinates in the archive are world-space birth vertices. This is done
    once immediately after build, never inferred from a later folded state.
    """
    import hashlib
    from pathlib import Path
    import numpy as np
    import trimesh
    from topogym.utils.arrays import to_numpy
    with np.load(path, allow_pickle=False) as data:
        vertices, faces, uv = (data[k].copy() for k in ("vertices", "faces", "uv"))
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or uv.shape != (len(vertices), 2)
            or not len(vertices)):
        raise ValueError("Material map requires matching authored vertices and UV")
    if (faces.ndim != 2 or faces.shape[1] != 3 or not len(faces)
            or faces.dtype.kind not in 'iu' or faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError("Material map faces must contain valid integer vertex indices")
    if not np.isfinite(vertices).all() or not np.isfinite(uv).all():
        raise ValueError("Nonfinite material map")
    triangles = vertices[faces]
    if np.any(np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                     triangles[:, 2]-triangles[:, 0]), axis=1) <= 1e-16):
        raise ValueError("Degenerate material map triangles")
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    particles = to_numpy(entity.get_particles_pos()).reshape(-1, 3)
    closest, distance, triangle = trimesh.proximity.closest_point_naive(mesh, particles)
    if np.max(distance) > 1e-5:
        raise ValueError("PBD particles do not lie on the declared birth material surface")
    weights = trimesh.triangles.points_to_barycentric(vertices[faces[triangle]], closest)
    mapped = np.einsum('ni,nij->nj', weights, uv[faces[triangle]])
    if not np.isfinite(mapped).all():
        raise ValueError("Nonfinite mapped material coordinates")
    # Coincident birth layers cannot be assigned by an arbitrary nearest face.
    for i, point in enumerate(particles):
        candidates = trimesh.triangles.closest_point(vertices[faces], np.broadcast_to(point, (len(faces), 3)))
        near = np.linalg.norm(candidates-point, axis=1) < 1e-7
        if near.sum() > 1:
            w = trimesh.triangles.points_to_barycentric(vertices[faces[near]], candidates[near])
            values = np.einsum('ni,nij->nj', w, uv[faces[near]])
            if np.max(np.linalg.norm(values-mapped[i], axis=1)) > 1e-5:
                raise ValueError("Ambiguous coincident PBD material layers")
    entity.grasp_material_coordinates = mapped
    entity.grasp_material_identity = hashlib.sha256(Path(path).read_bytes()).hexdigest()
