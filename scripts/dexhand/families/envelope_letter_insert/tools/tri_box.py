"""Exact triangle-vs-oriented-box overlap (separating axis test), vectorised over triangles. Authoring only."""
import numpy as np


def tris_overlap_box(tri, center, rot, half, margin=0.0):
    """tri: (n, 3, 3) world triangles; box: centre (3,), rotation (3, 3) columns = box axes, half sizes (3,).
    Returns a boolean (n,) mask of triangles that overlap the box (inflated by ``margin``)."""
    h = np.asarray(half, float) + margin
    v = (tri - center) @ rot  # into the box frame
    e = [v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]]
    ok = np.ones(len(v), bool)
    # 1) box face normals
    for i in range(3):
        ok &= (v[:, :, i].min(1) <= h[i]) & (v[:, :, i].max(1) >= -h[i])
    # 2) triangle normal
    n = np.cross(e[0], -e[2])
    d = np.einsum("ij,ij->i", n, v[:, 0])
    r = np.abs(n) @ h
    ok &= np.abs(d) <= r
    # 3) 9 edge cross products
    for i in range(3):
        a = np.zeros(3)
        a[i] = 1.0
        for ed in e:
            ax = np.cross(np.broadcast_to(a, ed.shape), ed)
            p = np.einsum("nkj,nj->nk", v, ax)
            rr = np.abs(ax) @ h
            ok &= (p.min(1) <= rr) & (p.max(1) >= -rr)
    return ok


def mesh_triangles(model, data, g):
    mid = model.geom_dataid[g]
    va, vn = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
    fa, fn = model.mesh_faceadr[mid], model.mesh_facenum[mid]
    verts = model.mesh_vert[va:va + vn] @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]
    faces = model.mesh_face[fa:fa + fn]
    return verts[faces]
