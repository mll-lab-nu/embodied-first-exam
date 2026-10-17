"""Keep human and standing-dog evidence selectors on their textured mesh surfaces.

Faces are partitioned, never moved or resampled. Each triangle belongs to the
nearest native anatomical primitive at its centroid. This is a visual label
mapping to the benchmark's existing coarse anatomy, not a new injury model.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def _distance(points, shape, size):
    import mujoco

    if shape == mujoco.mjtGeom.mjGEOM_BOX:
        q = np.abs(points) - size
        return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(np.max(q, axis=1), 0)
    if shape == mujoco.mjtGeom.mjGEOM_SPHERE:
        return np.linalg.norm(points, axis=1) - size[0]
    if shape == mujoco.mjtGeom.mjGEOM_CAPSULE:
        q = points.copy()
        q[:, 2] -= np.clip(q[:, 2], -size[1], size[1])
        return np.linalg.norm(q, axis=1) - size[0]
    if shape == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
        # The original figures use ellipsoids only for drawn detail; their
        # collision anatomy is boxes, spheres and capsules. Keep this fallback
        # for future native anatomical declarations.
        return (np.linalg.norm(points / size, axis=1) - 1) * np.min(size)
    raise ValueError(f"Unsupported anatomical primitive {shape}")


def _write_faces(lines, faces, target):
    """Write exact source coordinate records and faces with compact OBJ indices."""
    records = {key: [line for line in lines if line.startswith(key + " ")] for key in ("v", "vt", "vn")}
    used = [set(), set(), set()]
    parsed = []
    for face in faces:
        corners = []
        for token in face.split()[1:]:
            indices = []
            for i, value in enumerate(token.split("/")):
                index = int(value) if value else None
                if index is not None:
                    total = len(records[("v", "vt", "vn")[i]])
                    index = index - 1 if index > 0 else total + index
                    used[i].add(index)
                indices.append(index)
            corners.append(indices)
        parsed.append(corners)
    # MuJoCo requires four OBJ vertices even for a non-colliding triangle.
    # Retain an existing, unreferenced source vertex for such tiny partitions.
    # No triangle is added, moved or discarded, so the rendered surface and
    # anatomical assignment remain exactly those of the selected source faces.
    if len(used[0]) < 4:
        vertices = np.asarray([[float(v) for v in line.split()[1:4]] for line in records["v"]])
        selected = sorted(used[0])
        a, b, c = vertices[selected[:3]]
        normal = np.cross(b - a, c - a)
        candidates = [i for i in range(len(vertices)) if i not in used[0]]
        if not candidates:
            raise ValueError("Registered source mesh has fewer than four vertices")
        height = np.abs((vertices[candidates] - a) @ normal)
        span = float(np.max(np.ptp(vertices, axis=0)))
        nonplanar = [i for i, value in zip(candidates, height)
                     if value > max(1e-12, 1e-6 * span * np.linalg.norm(normal))]
        nearby = nonplanar or candidates
        centroid = (a + b + c) / 3
        extra = min(nearby, key=lambda i: float(np.linalg.norm(vertices[i] - centroid)))
        used[0].add(extra)
    maps = [{index: i + 1 for i, index in enumerate(sorted(indices))} for indices in used]
    result = []
    for key, indices in zip(("v", "vt", "vn"), used):
        result.extend(records[key][index] for index in sorted(indices))
    for face in parsed:
        result.append("f " + " ".join("/".join(str(maps[i][index]) if index is not None else ""
                                                for i, index in enumerate(corner)) for corner in face))
    target.write_text("\n".join(result) + "\n", encoding="ascii")


def partition(source, prop, scale, pos, quat):
    """Return (native part, OBJ) partitions, preserving the complete face multiset."""
    import mujoco

    regions = prop.meta.get("regions", {})
    # The crossing family requires the standing dog's existing head/neck cue.
    # Other animal poses have no keyed-evidence contract and keep their original
    # complete visual meshes; their scans are not all aligned to native anatomy.
    keyed_dog = prop.kind == "dog" and prop.meta.get("params", {}).get("pose", "standing") == "standing"
    if not regions or not ("human" in prop.meta.get("tags", ()) or keyed_dog):
        return [(None, str(source))]
    source = Path(source)
    lines = source.read_text(encoding="ascii").splitlines()
    vertices = np.asarray([[float(v) for v in line.split()[1:4]] for line in lines if line.startswith("v ")])
    faces = [line for line in lines if line.startswith("f ")]
    indices = [[int(token.split("/")[0]) for token in face.split()[1:]] for face in faces]
    if any(len(face) != 3 for face in indices):
        raise ValueError(f"Anatomical partition requires the registered triangulated OBJ: {source}")
    triangles = np.asarray(indices, dtype=np.int64)
    triangles = np.where(triangles > 0, triangles - 1, triangles + len(vertices))
    rotation = np.empty(9)
    mujoco.mju_quat2Mat(rotation, np.asarray(quat, dtype=float))
    points = vertices[triangles].mean(axis=1) * np.asarray(scale)
    points = points @ rotation.reshape(3, 3).T + np.asarray(pos)
    model = mujoco.MjModel.from_xml_path(prop.path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    anatomy = [(name, model.geom(name).id) for name in regions]
    scores = []
    for name, index in anatomy:
        local = (points - data.geom_xpos[index]) @ data.geom_xmat[index].reshape(3, 3)
        scores.append(_distance(local, model.geom_type[index], model.geom_size[index]))
    assigned = np.argmin(np.asarray(scores), axis=0)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    output = []
    for i, (name, _) in enumerate(anatomy):
        selected = np.flatnonzero(assigned == i)
        if not len(selected):
            continue
        target = Path(prop.path).parent / f"visual_{source.stem}_{digest}_{name}.obj"
        _write_faces(lines, [faces[index] for index in selected], target)
        output.append((name, str(target)))
    assert sum(np.count_nonzero(assigned == i) for i in range(len(anatomy))) == len(faces)
    return output
