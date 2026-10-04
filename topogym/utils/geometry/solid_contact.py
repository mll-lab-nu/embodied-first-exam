"""Measured solid geometry: distinguish boundary contact from interior overlap.

The 1 nm comparison resolution is numerical, not a millimetre penetration
allowance. Native convex meshes and boxes use their exact convex solid; spheres
use their analytic radius. Concave mesh covers only select narrow-phase work.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from .volume_geometry import ConvexCover, _unit_directions, triangle_intersections

RESOLUTION_M = 1e-9
FACES = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
EDGES = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]])


def classify_gap(gap):
    return 'separated' if gap > RESOLUTION_M else 'penetrating' if gap < -RESOLUTION_M else 'contact'


def convex_relation(a, b):
    axes = _unit_directions(np.vstack((a.normals, b.normals,
        np.cross(a.edges[:, None], b.edges[None]).reshape(-1, 3))))
    maximum = -np.inf
    origin = a.vertices[0]
    for start in range(0, len(axes), 128):
        directions = axes[start:start+128]
        pa, pb = (a.vertices-origin) @ directions.T, (b.vertices-origin) @ directions.T
        maximum = max(maximum, float(np.maximum(pa.min(0)-pb.max(0), pb.min(0)-pa.max(0)).max()))
        if maximum > RESOLUTION_M:
            break
    return classify_gap(maximum)


def tet_relations(a, b):
    """Batch solid SAT, including containment and shared boundary contact."""
    origin = a[:, :1]
    a, b = a-origin, b-origin
    fa, fb = a[:, FACES], b[:, FACES]
    ea, eb = a[:, EDGES[:, 1]]-a[:, EDGES[:, 0]], b[:, EDGES[:, 1]]-b[:, EDGES[:, 0]]
    axes = np.concatenate((np.cross(fa[:, :, 1]-fa[:, :, 0], fa[:, :, 2]-fa[:, :, 0]),
        np.cross(fb[:, :, 1]-fb[:, :, 0], fb[:, :, 2]-fb[:, :, 0]),
        np.cross(ea[:, :, None], eb[:, None]).reshape(-1, 36, 3)), axis=1)
    lengths = np.linalg.norm(axes, axis=2)
    axes = np.divide(axes, lengths[:, :, None], out=np.zeros_like(axes), where=lengths[:, :, None] > 1e-18)
    pa, pb = np.einsum('nvc,nac->nav', a, axes), np.einsum('nvc,nac->nav', b, axes)
    gap = np.maximum(pa.min(2)-pb.max(2), pb.min(2)-pa.max(2))
    gap[lengths <= 1e-18] = -np.inf
    return gap.max(1)


def self_volume_contacts(points, elements):
    cells = np.asarray(points)[elements]
    centers = cells.mean(1)
    radii = np.linalg.norm(cells-centers[:, None], axis=2).max(1)
    lo, hi = cells.min(1), cells.max(1)
    tree = cKDTree(centers)
    contacts = 0
    for start in range(0, len(cells), 128):
        neighbors = tree.query_ball_point(centers[start:start+128], radii[start:start+128]+radii.max()+RESOLUTION_M)
        pairs = np.asarray([(i, j) for i, js in enumerate(neighbors, start) for j in js if j > i], dtype=int).reshape(-1, 2)
        if not len(pairs):
            continue
        i, j = pairs.T
        keep = np.all(lo[i] <= hi[j]+RESOLUTION_M, axis=1) & np.all(lo[j] <= hi[i]+RESOLUTION_M, axis=1)
        pairs = pairs[keep]
        for offset in range(0, len(pairs), 128):
            batch = pairs[offset:offset+128]
            gap = tet_relations(cells[batch[:, 0]], cells[batch[:, 1]])
            contacts += int(np.count_nonzero(abs(gap) <= RESOLUTION_M))
            hit = np.flatnonzero(gap < -RESOLUTION_M)
            if len(hit):
                return dict(penetrating_cells=batch[hit[0]].tolist(), boundary_contacts=contacts)
    return dict(penetrating_cells=None, boundary_contacts=contacts)


def surface_cell_owners(elements, faces):
    """Map each measured surface face to its adjacent filled tetrahedron once."""
    triples = np.ascontiguousarray(np.sort(elements[:, FACES].reshape(-1, 3), axis=1), dtype=np.int64)
    dtype = np.dtype((np.void, 3*triples.dtype.itemsize))
    keys = triples.view(dtype).ravel()
    wanted = np.ascontiguousarray(np.sort(faces, axis=1), dtype=np.int64).view(dtype).ravel()
    order = np.argsort(keys)
    where = np.searchsorted(keys[order], wanted)
    if np.any(where >= len(order)) or np.any(keys[order[where]] != wanted):
        raise ValueError('Surface face is not part of the recorded FEM tetrahedra')
    return order[where]//4


def surface_solid_contacts(points, elements, faces, owners):
    """Refine nonincident surface contacts with their actual adjacent cell solids.

    Avoids testing millions of ordinary interior mesh neighbours on every tick.
    Does not certify incident-face folds or complete self-containment without a
    surface contact. These exclusions remain explicit in the audit report.
    """
    triangles = points[faces]
    centers = triangles.mean(1)
    radii = np.linalg.norm(triangles-centers[:, None], axis=2).max(1)
    lo, hi = triangles.min(1), triangles.max(1)
    tree = cKDTree(centers)
    contacts = 0
    for start in range(0, len(faces), 256):
        neighbors = tree.query_ball_point(centers[start:start+256], radii[start:start+256]+radii.max()+RESOLUTION_M)
        pairs = np.asarray([(i, j) for i, js in enumerate(neighbors, start) for j in js if j > i], dtype=int).reshape(-1, 2)
        if not len(pairs):
            continue
        i, j = pairs.T
        keep = np.all(lo[i] <= hi[j]+RESOLUTION_M, axis=1) & np.all(lo[j] <= hi[i]+RESOLUTION_M, axis=1)
        keep &= np.all(faces[i, :, None] != faces[j, None, :], axis=(1, 2))
        pairs = pairs[keep]
        for offset in range(0, len(pairs), 128):
            batch = pairs[offset:offset+128]
            hits = triangle_intersections(triangles[batch[:, 0]], triangles[batch[:, 1]])
            selected = batch[hits]
            if not len(selected):
                continue
            cells = owners[selected]
            gap = tet_relations(points[elements[cells[:, 0]]], points[elements[cells[:, 1]]])
            contacts += int(np.count_nonzero(abs(gap) <= RESOLUTION_M))
            hit = np.flatnonzero(gap < -RESOLUTION_M)
            if len(hit):
                return dict(penetrating_cells=cells[hit[0]].tolist(), boundary_contacts=contacts)
    return dict(penetrating_cells=None, boundary_contacts=contacts)


def _clip_triangle(triangle, normals, support, inset=0.):
    polygon = list(triangle)
    for normal, limit in zip(normals, support-inset, strict=True):
        if not polygon:
            break
        result = []
        for a, b in zip(polygon, polygon[1:]+polygon[:1], strict=True):
            da, db = a @ normal-limit, b @ normal-limit
            if da <= 0:
                result.append(a)
            if (da < 0 < db) or (db < 0 < da):
                result.append(a+(b-a)*da/(da-db))
        polygon = result
    return polygon


def _inside_mesh(point, triangles):
    vectors = triangles-point
    lengths = np.linalg.norm(vectors, axis=2)
    if np.any(lengths < RESOLUTION_M):
        return False  # a boundary vertex, not an interior witness
    a, b, c = vectors[:, 0], vectors[:, 1], vectors[:, 2]
    numerator = np.einsum('ij,ij->i', a, np.cross(b, c))
    denominator = lengths.prod(1)+np.einsum('ij,ij->i', a, b)*lengths[:, 2]
    denominator += np.einsum('ij,ij->i', b, c)*lengths[:, 0]+np.einsum('ij,ij->i', c, a)*lengths[:, 1]
    return bool(abs(np.sum(2*np.arctan2(numerator, denominator))) > 2*np.pi)


def triangle_pair_distances(a, b):
    """Euclidean boundary distance for disjoint paired triangles.

    Vertex/face and all nine edge/edge pairs cover closest features. Callers
    must first exclude solid overlap; positive surface distance alone does not
    exclude containment.
    """
    from trimesh.triangles import closest_point
    minimum = np.full(len(a), np.inf)
    for i in range(3):
        minimum = np.minimum(minimum, np.linalg.norm(closest_point(a, b[:, i])-b[:, i], axis=1))
        minimum = np.minimum(minimum, np.linalg.norm(closest_point(b, a[:, i])-a[:, i], axis=1))
    for i in range(3):
        p, u = a[:, i], a[:, (i+1) % 3]-a[:, i]
        uu = np.einsum('ij,ij->i', u, u)
        for j in range(3):
            q, v = b[:, j], b[:, (j+1) % 3]-b[:, j]
            vv = np.einsum('ij,ij->i', v, v)
            uv = np.einsum('ij,ij->i', u, v)
            w = p-q
            uw, vw = np.einsum('ij,ij->i', u, w), np.einsum('ij,ij->i', v, w)
            denominator = uu*vv-uv*uv
            valid = denominator > np.finfo(float).eps*uu*vv
            s = np.divide(uv*vw-vv*uw, denominator, out=np.zeros_like(uu), where=valid)
            t = np.divide(uu*vw-uv*uw, denominator, out=np.zeros_like(uu), where=valid)
            interior = valid & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
            distance = np.linalg.norm(w+s[:, None]*u-t[:, None]*v, axis=1)
            minimum = np.minimum(minimum, np.where(interior, distance, np.inf))
            # Segment-boundary optima include parallel and endpoint cases.
            for endpoint in (p, p+u):
                t = np.clip(np.einsum('ij,ij->i', endpoint-q, v)/vv, 0., 1.)
                minimum = np.minimum(minimum, np.linalg.norm(endpoint-q-t[:, None]*v, axis=1))
            for endpoint in (q, q+v):
                s = np.clip(np.einsum('ij,ij->i', endpoint-p, u)/uu, 0., 1.)
                minimum = np.minimum(minimum, np.linalg.norm(endpoint-p-s[:, None]*u, axis=1))
    return minimum


class MeasuredCollider:
    def __init__(self, entry, vertices, faces, cover_vertices):
        self.entry, self.kind = entry, entry['native_type']
        self.cover = ConvexCover(cover_vertices)
        self.vertices = np.asarray(vertices, float)
        self.faces = None if faces is None else np.asarray(faces, int)
        self.exact_convex = self.kind == 'BOX' or (self.kind == 'MESH' and entry.get('native_convex') is True)
        self.center = np.asarray(entry.get('primitive_position_in_link_m', [np.nan]*3), float)
        self.radius = float(entry['native_data'][0]) if self.kind == 'SPHERE' else None
        self.closed = False
        self.convex_faces = ConvexHull(self.cover.vertices).simplices if self.exact_convex else None
        if self.faces is not None and self.kind == 'MESH' and not self.exact_convex:
            directed = np.concatenate([self.faces[:, [a, b]] for a, b in ((0, 1), (1, 2), (2, 0))])
            edges, counts = np.unique(np.sort(directed, axis=1), axis=0, return_counts=True)
            self.closed = bool(len(edges) and np.all(counts == 2))
            if self.closed:
                # Winding classification requires consistently oriented faces.
                _, multiplicity = np.unique(directed, axis=0, return_counts=True)
                self.closed = bool(np.all(multiplicity == 1))

    def placed(self, rotation, translation):
        import copy
        out = copy.copy(self)
        out.cover = self.cover.placed(rotation, translation)
        out.vertices = self.vertices @ rotation.T+translation
        out.center = self.center @ rotation.T+translation
        return out

    def against_convex(self, volume):
        if not self.cover.overlap(volume):
            return 'separated'
        if self.exact_convex:
            return convex_relation(self.cover, volume)
        if self.kind == 'SPHERE':
            if not np.isfinite(self.center).all():
                return 'unresolved'
            if np.all(self.center @ volume.normals.T <= volume.support):
                return 'penetrating'
            from trimesh.triangles import closest_point
            faces = ConvexHull(volume.vertices).simplices
            triangles = volume.vertices[faces]
            nearest = closest_point(triangles, np.broadcast_to(self.center, (len(triangles), 3)))
            gap = np.linalg.norm(nearest-self.center, axis=1).min()-self.radius
            return classify_gap(gap)
        if not self.closed:
            return 'unresolved'
        triangles = self.vertices[self.faces]
        keep = np.all(triangles.min(1) <= volume.hi+RESOLUTION_M, axis=1) & np.all(
            triangles.max(1) >= volume.lo-RESOLUTION_M, axis=1)
        contact = False
        for triangle in triangles[keep]:
            if _clip_triangle(triangle, volume.normals, volume.support, inset=RESOLUTION_M):
                return 'penetrating'
            contact |= bool(_clip_triangle(triangle, volume.normals, volume.support))
        # Also catches a convex solid entirely contained by the closed mesh.
        if _inside_mesh(volume.vertices.mean(0), triangles):
            return 'penetrating'
        return 'contact' if contact else 'separated'

    def against(self, other):
        if not self.cover.overlap(other.cover):
            return 'separated'
        if other.exact_convex:
            return self.against_convex(other.cover)
        if self.exact_convex:
            return other.against_convex(self.cover)
        if self.kind == other.kind == 'SPHERE' and np.isfinite([self.center, other.center]).all():
            return classify_gap(np.linalg.norm(self.center-other.center)-self.radius-other.radius)
        # Concave/concave and sphere/concave pairs need a separate exact query.
        # Never turn an unimplemented narrow phase into a penetration or pass.
        return 'unresolved'

    def clearance_from_tet(self, corners, required):
        """Classify the filled cell first, then refine a positive gap if needed.

        Returns a certified distance capped at ``required``. No mesh-surface
        distance can override containment, interior overlap or an open mesh.
        """
        volume = ConvexCover(corners)
        relation = self.against_convex(volume)
        if relation != 'separated':
            return relation, 0.
        if required <= 0:
            return relation, 0.
        if self.kind == 'SPHERE':
            from trimesh.triangles import closest_point
            triangles = corners[FACES]
            nearest = closest_point(triangles, np.broadcast_to(self.center, (4, 3)))
            return relation, min(required, float(np.linalg.norm(nearest-self.center, axis=1).min()-self.radius))
        if self.exact_convex:
            triangles = self.cover.vertices[self.convex_faces]
        elif self.closed:
            triangles = self.vertices[self.faces]
        else:
            return 'unresolved', 0.
        target = corners[FACES]
        gaps = np.maximum(np.maximum(triangles.min(1)[:, None]-target.max(1)[None],
                                     target.min(1)[None]-triangles.max(1)[:, None]), 0.)
        pairs = np.argwhere(np.linalg.norm(gaps, axis=2) < required+RESOLUTION_M)
        minimum = required
        for start in range(0, len(pairs), 128):
            batch = pairs[start:start+128]
            minimum = min(minimum, float(triangle_pair_distances(triangles[batch[:, 0]], target[batch[:, 1]]).min()))
        return relation, minimum

    def against_tets(self, corners, bounds=None):
        lo, hi = (corners.min(1), corners.max(1)) if bounds is None else bounds
        indices = np.flatnonzero(np.all(lo <= self.cover.hi+RESOLUTION_M, axis=1)
                                  & np.all(hi >= self.cover.lo-RESOLUTION_M, axis=1))
        result = dict(penetrating_cell=None, contacts=0, unresolved=0)
        for index in indices:
            try:
                relation = self.against_convex(ConvexCover(corners[index]))
            except ValueError:
                relation = 'unresolved'
            if relation == 'penetrating':
                result['penetrating_cell'] = int(index)
                break
            if relation == 'contact':
                result['contacts'] += 1
            if relation == 'unresolved':
                result['unresolved'] += 1
        return result
