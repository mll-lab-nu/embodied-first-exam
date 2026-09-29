"""Conservative separation certificates for filled FEM tetrahedra.

For a unit outward supporting plane n.x+d<=0 enclosing a robot collider,
min(n.x+d) over all four tetrahedron corners is a lower bound on the distance
from that entire tetrahedron to the collider. Taking the best plane per cell,
then the minimum over every cell/collider, covers the full material volume.
It also rejects containment, where a surface-only distance could be positive.
"""
import numpy as np
from scipy.spatial import ConvexHull, QhullError

_ROUNDING_MARGIN_M = 1e-9


def convex_cover_planes(vertices):
    """Cache a convex outer cover of a mesh, including concave mesh interiors."""
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("Invalid convex collision vertices")
    try:
        normals = ConvexHull(points).equations[:, :3]
    except QhullError:
        # Flat or otherwise degenerate meshes retain their coarse box cover.
        return np.empty((0, 4))
    # Deduplicate coplanar facets. Recompute support after rounding normals so
    # every supplied collision vertex remains inside the resulting halfspaces.
    normals = np.unique(np.round(normals, 12), axis=0)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    offsets = -np.einsum('vc,pc->vp', points, normals).max(axis=0)-_ROUNDING_MARGIN_M
    return np.c_[normals, offsets]


def validate_robot_planes(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError("Release convex cover count differs from robot bounds")
    result = []
    for value in values:
        planes = np.asarray(value, dtype=float)
        if (planes.ndim != 2 or planes.shape[1] != 4 or not np.isfinite(planes).all()
                or not np.allclose(np.linalg.norm(planes[:, :3], axis=1), 1., rtol=0., atol=1e-8)):
            raise ValueError("Invalid release convex planes")
        result.append(planes)
    return result


def validate_elements(value, vertex_count):
    elements = np.asarray(value)
    if (elements.ndim != 2 or elements.shape[1] != 4 or not len(elements)
            or elements.dtype.kind not in 'iu' or elements.min() < 0
            or elements.max() >= vertex_count
            or not np.array_equal(np.unique(elements), np.arange(vertex_count))):
        raise ValueError("Release FEM elements must cover every current vertex with valid tetrahedra")
    return elements


def fem_clearance_lower_bound(points, elements, robot_boxes, robot_planes, required):
    """Refine only close cell/robot pairs; boxes remain the inexpensive cover."""
    corners = points[elements]
    lo, hi = corners.min(axis=1), corners.max(axis=1)
    whole_lo, whole_hi = points.min(axis=0), points.max(axis=0)
    minimum = float('inf')
    for box, planes in zip(robot_boxes, robot_planes, strict=True):
        coarse = float(np.linalg.norm(np.maximum(np.maximum(whole_lo-box[1], box[0]-whole_hi), 0.)))
        if coarse >= required:
            minimum = min(minimum, coarse)
            continue
        gaps = np.maximum(np.maximum(lo-box[1], box[0]-hi), 0.)
        distances = np.linalg.norm(gaps, axis=1)
        close = np.flatnonzero(distances < required)
        if len(close) and len(planes):
            for start in range(0, len(close), 256):
                indices = close[start:start+256]
                signed = np.einsum('tvc,pc->tvp', corners[indices], planes[:, :3])+planes[:, 3]
                lower = signed.min(axis=1).max(axis=1)-_ROUNDING_MARGIN_M
                distances[indices] = np.maximum(distances[indices], lower)
        minimum = min(minimum, float(distances.min()))
    return minimum
