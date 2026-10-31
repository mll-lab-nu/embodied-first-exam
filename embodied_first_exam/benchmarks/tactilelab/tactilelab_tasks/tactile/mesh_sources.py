"""Triangle meshes for the tactile raycaster: USD prims and procedural shapes.

All functions return ``(vertices (N, 3) float32, faces (M, 3) int32)``. ``pxr``
(the USD Python bindings that ship with Isaac Sim) is imported lazily, so the
procedural helpers work without it.

Typical use for a rigid task object in Isaac Lab::

    verts, faces = usd_mesh_in_frame(stage, "/World/Object", frame_path="/World/Object")
    target = MeshTarget(verts, faces, device)
    ...
    target.set_pose(rigid_object.data.root_link_pose_w[0])   # every tick (wxyz)

The vertices are expressed in the frame of ``frame_path`` (the rigid body) with
any USD scale baked in, so only the body pose has to be updated at run time.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np

__all__ = [
    "box_mesh",
    "sphere_mesh",
    "cylinder_mesh",
    "transform_vertices",
    "usd_mesh_triangles",
    "usd_mesh_in_frame",
    "usd_world_pose7",
    "iter_usd_meshes",
]


# --------------------------------------------------------------------------- procedural


def box_mesh(size=(0.02, 0.02, 0.02), center=(0.0, 0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned box: 8 vertices, 12 triangles (outward winding)."""
    sx, sy, sz = (float(s) / 2.0 for s in size)
    cx, cy, cz = (float(c) for c in center)
    v = np.array(
        [
            [-sx, -sy, -sz],
            [sx, -sy, -sz],
            [sx, sy, -sz],
            [-sx, sy, -sz],
            [-sx, -sy, sz],
            [sx, -sy, sz],
            [sx, sy, sz],
            [-sx, sy, sz],
        ],
        dtype=np.float32,
    ) + np.array([cx, cy, cz], dtype=np.float32)
    f = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],  # -z
            [4, 5, 6],
            [4, 6, 7],  # +z
            [0, 1, 5],
            [0, 5, 4],  # -y
            [2, 3, 7],
            [2, 7, 6],  # +y
            [1, 2, 6],
            [1, 6, 5],  # +x
            [3, 0, 4],
            [3, 4, 7],  # -x
        ],
        dtype=np.int32,
    )
    return v, f


def sphere_mesh(radius=0.01, center=(0.0, 0.0, 0.0), n_lat=24, n_lon=48) -> tuple[np.ndarray, np.ndarray]:
    """UV sphere."""
    verts = [[0.0, 0.0, radius]]
    for i in range(1, n_lat):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2.0 * math.pi * j / n_lon
            verts.append(
                [radius * math.sin(th) * math.cos(ph), radius * math.sin(th) * math.sin(ph), radius * math.cos(th)]
            )
    verts.append([0.0, 0.0, -radius])
    top, bot = 0, len(verts) - 1
    ring = lambda i, j: 1 + (i - 1) * n_lon + (j % n_lon)  # noqa: E731
    faces = []
    for j in range(n_lon):
        faces.append([top, ring(1, j), ring(1, j + 1)])
    for i in range(1, n_lat - 1):
        for j in range(n_lon):
            a, b, c, d = ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)
            faces.append([a, d, c])
            faces.append([a, c, b])
    for j in range(n_lon):
        faces.append([bot, ring(n_lat - 1, j + 1), ring(n_lat - 1, j)])
    v = np.asarray(verts, dtype=np.float32) + np.asarray(center, dtype=np.float32)
    return v, np.asarray(faces, dtype=np.int32)


def cylinder_mesh(radius=0.01, height=0.02, center=(0.0, 0.0, 0.0), n=48, axis=2) -> tuple[np.ndarray, np.ndarray]:
    """Closed cylinder along ``axis`` (0, 1 or 2)."""
    h = height / 2.0
    ring_lo, ring_hi = [], []
    for j in range(n):
        ph = 2.0 * math.pi * j / n
        c, s = radius * math.cos(ph), radius * math.sin(ph)
        ring_lo.append([c, s, -h])
        ring_hi.append([c, s, h])
    verts = ring_lo + ring_hi + [[0.0, 0.0, -h], [0.0, 0.0, h]]
    clo, chi = 2 * n, 2 * n + 1
    faces = []
    for j in range(n):
        a, b = j, (j + 1) % n
        faces.append([a, b, n + b])
        faces.append([a, n + b, n + a])
        faces.append([clo, b, a])
        faces.append([chi, n + a, n + b])
    v = np.asarray(verts, dtype=np.float32)
    if axis != 2:
        order = [1, 2, 0] if axis == 0 else [2, 0, 1]
        v = v[:, order]
    return v + np.asarray(center, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def transform_vertices(vertices: np.ndarray, matrix4: np.ndarray) -> np.ndarray:
    """Apply a row-vector 4x4 matrix (USD ``Gf.Matrix4d`` convention, ``p' = p @ M``)."""
    v = np.asarray(vertices, dtype=np.float64)
    m = np.asarray(matrix4, dtype=np.float64).reshape(4, 4)
    out = np.concatenate([v, np.ones((len(v), 1))], axis=1) @ m
    return (out[:, :3] / out[:, 3:4]).astype(np.float32)


# --------------------------------------------------------------------------- USD


def _pxr():
    try:
        from pxr import Gf, Usd, UsdGeom  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError("pxr (USD) is not available; run inside Isaac Sim / Isaac Lab") from e
    return Gf, Usd, UsdGeom


def _get_prim(stage_or_prim, path: Optional[str]):
    if path is None:
        return stage_or_prim
    prim = stage_or_prim.GetPrimAtPath(path)
    if not prim.IsValid():
        raise ValueError(f"invalid USD prim path: {path}")
    return prim


def _triangulate(counts: np.ndarray, indices: np.ndarray, left_handed: bool) -> np.ndarray:
    faces = []
    k = 0
    for c in counts:
        poly = indices[k : k + c]
        k += c
        for t in range(1, c - 1):
            tri = [poly[0], poly[t], poly[t + 1]]
            faces.append(tri[::-1] if left_handed else tri)
    return np.asarray(faces, dtype=np.int32).reshape(-1, 3)


def iter_usd_meshes(root_prim, skip_guides: bool = True) -> Iterable:
    """Yield every ``UsdGeom.Mesh`` prim under ``root_prim`` (inclusive)."""
    Gf, Usd, UsdGeom = _pxr()
    for prim in Usd.PrimRange(root_prim):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        if skip_guides and UsdGeom.Imageable(prim).ComputePurpose() == UsdGeom.Tokens.guide:
            continue
        yield prim


def usd_mesh_triangles(mesh_prim, time_code=None) -> tuple[np.ndarray, np.ndarray]:
    """Points and triangulated faces of one ``UsdGeom.Mesh`` in its own (local) frame."""
    Gf, Usd, UsdGeom = _pxr()
    tc = Usd.TimeCode.Default() if time_code is None else time_code
    mesh = UsdGeom.Mesh(mesh_prim)
    pts = np.asarray(mesh.GetPointsAttr().Get(tc), dtype=np.float32).reshape(-1, 3)
    counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(tc), dtype=np.int64)
    idx = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(tc), dtype=np.int64)
    left = mesh.GetOrientationAttr().Get(tc) == UsdGeom.Tokens.leftHanded
    return pts, _triangulate(counts, idx, left)


def usd_world_pose7(stage_or_prim, path: Optional[str] = None, time_code=None) -> np.ndarray:
    """World pose ``[x y z qw qx qy qz]`` of a prim (scale and shear dropped)."""
    Gf, Usd, UsdGeom = _pxr()
    prim = _get_prim(stage_or_prim, path)
    tc = Usd.TimeCode.Default() if time_code is None else time_code
    m = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(tc)
    t = m.ExtractTranslation()
    q = m.RemoveScaleShear().ExtractRotationQuat()
    im = q.GetImaginary()
    return np.array([t[0], t[1], t[2], q.GetReal(), im[0], im[1], im[2]], dtype=np.float64)


def usd_mesh_in_frame(
    stage_or_prim,
    path: Optional[str] = None,
    frame_path: Optional[str] = None,
    time_code=None,
    skip_guides: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """All meshes under a prim, merged, expressed in the frame of ``frame_path``.

    Args:
        stage_or_prim: a ``Usd.Stage`` (then ``path`` is required) or a ``Usd.Prim``.
        path: prim whose mesh descendants are collected.
        frame_path: prim whose world transform defines the output frame; ``None``
            returns world-frame vertices. Pass the rigid body prim to get body-frame
            vertices (scale baked in) for ``MeshTarget.set_pose``.
    """
    Gf, Usd, UsdGeom = _pxr()
    root = _get_prim(stage_or_prim, path)
    tc = Usd.TimeCode.Default() if time_code is None else time_code
    if frame_path is None:
        inv = Gf.Matrix4d(1.0)
    else:
        frame = _get_prim(root.GetStage(), frame_path)
        inv = UsdGeom.Xformable(frame).ComputeLocalToWorldTransform(tc).GetInverse()
    verts, faces = [], []
    n = 0
    for mp in iter_usd_meshes(root, skip_guides=skip_guides):
        v, f = usd_mesh_triangles(mp, tc)
        m = UsdGeom.Xformable(mp).ComputeLocalToWorldTransform(tc) * inv
        verts.append(transform_vertices(v, np.array(m)))
        faces.append(f + n)
        n += len(v)
    if not verts:
        raise ValueError(f"no UsdGeom.Mesh under {root.GetPath()}")
    return np.concatenate(verts, axis=0).astype(np.float32), np.concatenate(faces, axis=0).astype(np.int32)
