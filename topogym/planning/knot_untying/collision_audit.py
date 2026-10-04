"""Read-only geometric checks on measured FEM meshes, independent of task success.

These are checks at supplied sample times, not a continuous swept-volume proof.
Surface self-intersection excludes incident triangles (shared vertex/edge), whose
ordinary contact is part of a conforming mesh. Positive cell volume is checked
separately; neither check may be replaced by a crossing count on the centre line.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

# Separation must exceed roundoff; this expands the excluded region rather than
# permitting penetration. A cover overlap is inconclusive, never a clearance pass.
SEPARATION_MARGIN_M = 1e-9


def rigid_cover_vertices(kind, data, vertices):
    """Cover the native primitive, not just its inscribed display triangulation.

    Genesis uses analytic spheres for rigid contact. Expanding their tessellation
    until every support plane is outside the analytic radius prevents a false
    clearance certificate between a sphere and a nearby FEM cell. Mesh hulls and
    box corners already cover their native geometry. Unknown primitives fail closed.
    """
    points = _vertices(vertices)
    data = np.asarray(data, float).reshape(-1)
    if kind == 'MESH':
        return points.copy(), 'convex_hull_of_native_mesh'
    if kind == 'BOX':
        if len(data) < 3 or not np.isfinite(data[:3]).all() or np.any(data[:3] <= 0):
            raise ValueError('Invalid native box dimensions')
        half = data[:3]/2
        return np.array([[x, y, z] for x in (-half[0], half[0]) for y in (-half[1], half[1])
                         for z in (-half[2], half[2])]), 'analytic_box_corners'
    if kind == 'SPHERE':
        if not len(data) or not np.isfinite(data[0]) or data[0] <= 0:
            raise ValueError('Invalid native sphere radius')
        hull = ConvexHull(points)
        distances = -hull.equations[:, 3]
        if np.any(distances <= 0):
            raise ValueError('Native sphere mesh does not enclose its geometric origin')
        factor = max(1., float((data[0]+SEPARATION_MARGIN_M)/distances.min()))
        return points*factor, 'circumscribed_native_sphere_mesh'
    raise ValueError(f'Unsupported native collision primitive: {kind}')


def _vertices(points):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("Invalid measured mesh vertices")
    return points


def _indices(values, width, count):
    values = np.asarray(values)
    if (values.ndim != 2 or values.shape[1] != width or not len(values) or values.dtype.kind not in 'iu'
            or values.min() < 0 or values.max() >= count
            or np.any(np.diff(np.sort(values, axis=1), axis=1) == 0)):
        raise ValueError("Invalid measured mesh connectivity")
    return values


def determinants(points, elements):
    p = points[elements]
    return np.einsum('ij,ij->i', p[:, 1]-p[:, 0], np.cross(p[:, 2]-p[:, 0], p[:, 3]-p[:, 0]))


class VolumeCheck:
    def __init__(self, rest, elements):
        self.rest = _vertices(rest).copy()
        self.elements = _indices(elements, 4, len(self.rest)).copy()
        self.reference = determinants(self.rest, self.elements)
        if np.any(self.reference <= 0):
            raise ValueError("Rest tetrahedra must have positive oriented volume")

    def measure(self, points):
        points = _vertices(points)
        if points.shape != self.rest.shape:
            raise ValueError("Measured/rest vertex counts differ")
        ratios = determinants(points, self.elements)/self.reference
        return dict(minimum_volume_ratio=float(ratios.min()), maximum_volume_ratio=float(ratios.max()),
                    nonpositive_cells=int(np.count_nonzero(ratios <= 0)))


def triangle_intersections(a, b):
    """Closed triangle intersection by separating axes, including coplanar pairs.

    Inputs are N pairs of triangles in one coordinate frame. Additional in-plane
    edge normals handle coplanar triangles. An exact touch counts as intersection;
    this function introduces no allowed penetration depth.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 3 or a.shape[1:] != (3, 3) or not np.isfinite([a, b]).all():
        raise ValueError("Expected finite paired triangles")
    origin = a[:, :1]
    a, b = a-origin, b-origin  # reduce cancellation when the table is far from the origin
    ea, eb = np.roll(a, -1, axis=1)-a, np.roll(b, -1, axis=1)-b
    na, nb = np.cross(ea[:, 0], ea[:, 1]), np.cross(eb[:, 0], eb[:, 1])
    if np.any(np.linalg.norm(na, axis=1) <= 1e-18) or np.any(np.linalg.norm(nb, axis=1) <= 1e-18):
        raise ValueError("Degenerate measured surface triangle")
    axes = np.concatenate((na[:, None], nb[:, None],
        np.cross(ea[:, :, None], eb[:, None, :]).reshape(-1, 9, 3),
        np.cross(na[:, None], ea), np.cross(nb[:, None], eb)), axis=1)
    lengths = np.linalg.norm(axes, axis=2)
    # Parallel edges yield zero axes, which cannot separate the triangles.
    axes = np.divide(axes, lengths[:, :, None], out=np.zeros_like(axes), where=lengths[:, :, None] > 0)
    pa, pb = np.einsum('nvc,nac->nav', a, axes), np.einsum('nvc,nac->nav', b, axes)
    separated = (pa.max(axis=2) < pb.min(axis=2)) | (pb.max(axis=2) < pa.min(axis=2))
    return ~separated.any(axis=1)


def surface_self_intersection(points, faces, *, batch_size=256, pair_limit=2_000_000):
    """Return the first intersecting nonincident face pair, or None after coverage.

    A ball tree is only a broad phase: every candidate also receives an AABB and
    full triangle test. Pair limits fail closed; they never skip unseen geometry.
    """
    points = _vertices(points)
    faces = _indices(faces, 3, len(points))
    if type(batch_size) is not int or batch_size < 1 or type(pair_limit) is not int or pair_limit < 1:
        raise ValueError("Invalid self-intersection work limits")
    triangles = points[faces]
    centers = triangles.mean(axis=1)
    radii = np.linalg.norm(triangles-centers[:, None], axis=2).max(axis=1)
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    if np.any(np.linalg.norm(normals, axis=1) <= 1e-18):
        raise ValueError("Degenerate measured surface triangle")
    lo, hi = triangles.min(axis=1), triangles.max(axis=1)
    tree = cKDTree(centers)
    for start in range(0, len(faces), batch_size):
        stop = min(start+batch_size, len(faces))
        # Round the enclosing radii outwards; broad-phase tolerance cannot itself accept a pair.
        neighborhoods = tree.query_ball_point(centers[start:stop], radii[start:stop]+radii.max()+1e-12)
        if sum(map(len, neighborhoods)) > pair_limit:
            raise RuntimeError("Self-intersection broad phase exceeded its pair budget; evidence incomplete")
        pairs = [(i, j) for i, neighbors in enumerate(neighborhoods, start) for j in neighbors if j > i]
        if not pairs:
            continue
        pairs = np.asarray(pairs, dtype=np.int64)
        i, j = pairs.T
        keep = np.all(lo[i] <= hi[j], axis=1) & np.all(lo[j] <= hi[i], axis=1)
        pairs = pairs[keep]
        if not len(pairs):
            continue
        i, j = pairs.T
        keep = np.all(faces[i, :, None] != faces[j, None, :], axis=(1, 2))
        pairs = pairs[keep]
        if not len(pairs):
            continue
        hits = triangle_intersections(triangles[pairs[:, 0]], triangles[pairs[:, 1]])
        if np.any(hits):
            return pairs[np.flatnonzero(hits)[0]].tolist()
    return None


def _unit_directions(values):
    values = np.asarray(values, float).reshape(-1, 3)
    norms = np.linalg.norm(values, axis=1)
    values = values[norms > 1e-15] / norms[norms > 1e-15, None]
    # Duplicates cost time but do not change the separating-axis certificate.
    return np.unique(values, axis=0)


def _separated(a, b, axes):
    """A positive certificate: one unit direction strictly separates whole volumes."""
    axes = _unit_directions(axes)
    for start in range(0, len(axes), 256):
        directions = axes[start:start+256]
        pa, pb = a @ directions.T, b @ directions.T
        if np.any((pa.min(axis=0)-pb.max(axis=0) > SEPARATION_MARGIN_M)
                  | (pb.min(axis=0)-pa.max(axis=0) > SEPARATION_MARGIN_M)):
            return True
    return False


class ConvexCover:
    """A closed outer cover, so containment cannot evade the volume test.

    This covers every supplied collider vertex and its triangles, even when the
    native mesh is concave. Non-overlap proves separation; overlap can instead be
    caused by a concavity and must not be described as proven mesh penetration.
    No physics mesh is changed. Transformations only place the audit's copy.
    """
    def __init__(self, vertices):
        points = _vertices(vertices)
        hull = ConvexHull(points)
        if not hull.volume > 0:
            raise ValueError('Collider must enclose a finite volume')
        self.vertices = points[hull.vertices].copy()
        self.normals = _unit_directions(hull.equations[:, :3])
        edges = np.concatenate([hull.simplices[:, [i, j]] for i, j in ((0, 1), (1, 2), (2, 0))])
        self.edges = _unit_directions(points[edges[:, 1]]-points[edges[:, 0]])
        self._bounds()

    def _bounds(self):
        self.lo, self.hi = self.vertices.min(axis=0), self.vertices.max(axis=0)
        self.support = (self.vertices @ self.normals.T).max(axis=0)

    def placed(self, rotation, translation):
        rotation, translation = np.asarray(rotation, float), np.asarray(translation, float)
        if (rotation.shape != (3, 3) or translation.shape != (3,) or not np.isfinite(rotation).all()
                or not np.isfinite(translation).all() or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10)
                or not np.isclose(np.linalg.det(rotation), 1., atol=1e-10)):
            raise ValueError('Invalid measured rigid transform')
        out = object.__new__(ConvexCover)
        out.vertices = self.vertices @ rotation.T + translation
        out.normals, out.edges = self.normals @ rotation.T, self.edges @ rotation.T
        out._bounds()
        return out

    def overlap(self, other):
        """True means contact or possible overlap; False certifies separation."""
        if np.any(np.maximum(self.lo-other.hi, other.lo-self.hi) > SEPARATION_MARGIN_M):
            return False
        if _separated(self.vertices, other.vertices, np.vstack((self.normals, other.normals))):
            return False
        for start in range(0, len(self.edges), 32):
            axes = np.cross(self.edges[start:start+32, None], other.edges[None])
            if _separated(self.vertices, other.vertices, axes):
                return False
        return True

    def first_overlapping_tet(self, corners, bounds=None):
        """Check filled FEM tetrahedra, including either object's complete containment.

        Face normals reject most distant cells in batches; the remaining cells
        receive their own face and edge/edge separating axes. No cell is skipped
        merely because no surface triangle crosses the collider.
        """
        corners = np.asarray(corners, float)
        if corners.ndim != 3 or corners.shape[1:] != (4, 3) or not np.isfinite(corners).all():
            raise ValueError('Invalid measured tetrahedra')
        lo, hi = (corners.min(axis=1), corners.max(axis=1)) if bounds is None else bounds
        candidates = np.flatnonzero(np.all((lo-self.hi <= SEPARATION_MARGIN_M)
                                           & (self.lo-hi <= SEPARATION_MARGIN_M), axis=1))
        tet_faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
        tet_edges = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]])
        for start in range(0, len(candidates), 64):
            indices = candidates[start:start+64]
            p = corners[indices]
            # All four corners outside one supporting plane certify the entire cell.
            rejected = np.zeros(len(p), bool)
            for plane_start in range(0, len(self.normals), 256):
                normal = self.normals[plane_start:plane_start+256]
                distance = np.einsum('tvc,pc->tvp', p, normal)-self.support[plane_start:plane_start+256]
                rejected |= np.any(distance.min(axis=1) > SEPARATION_MARGIN_M, axis=1)
            for index in indices[~rejected]:
                tet = corners[index]
                f = tet[tet_faces]
                if _separated(tet, self.vertices, np.cross(f[:, 1]-f[:, 0], f[:, 2]-f[:, 0])):
                    continue
                edges = tet[tet_edges[:, 1]]-tet[tet_edges[:, 0]]
                if _separated(tet, self.vertices, np.cross(edges[:, None], self.edges[None])):
                    continue
                return int(index)
        return None
