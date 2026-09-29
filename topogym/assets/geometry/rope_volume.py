"""FEM ropes with straight rest coordinates and an authored curved spawn.

The default reuses the validated v13 material/mesh recipe. The old single-fan
mesh remains an explicit diagnostic profile, never a production fallback.
"""

from pathlib import Path
import numpy as np
from topogym.utils.geometry.rope import parallel_transport_frames, make_elastic_tube_mesh

AXIAL_SPACING_M = 0.001375
RADIAL_SEGMENTS = 24
MAX_TET_VOLUME_M3 = 2.5e-9


def write_rope_volume(
    path, centerline, radius, *, spacing=None, sides=None, end_stops=False,
    profile="v13_material_mesh",
):
    if profile not in {"v13_material_mesh", "structured_baseline"}:
        raise ValueError(f"Unknown rope mesh profile: {profile}")
    if sides is None:
        sides = RADIAL_SEGMENTS if profile == "v13_material_mesh" else 8
    points = np.asarray(centerline, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or len(points) < 2
        or not np.isfinite(points).all()
        or not np.isfinite(radius)
        or radius <= 0
    ):
        raise ValueError("A finite centerline and positive radius are required")
    if isinstance(sides, bool) or not isinstance(sides, int) or sides < 3:
        raise ValueError("Tube cross-section needs at least three sides")
    if spacing is not None and (not np.isfinite(spacing) or spacing <= 0):
        raise ValueError("Volume spacing must be finite and positive")
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    points = points[np.r_[True, lengths > 1e-10]]
    if len(points) < 2:
        raise ValueError("Centerline must contain at least two distinct points")
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    default_spacing = AXIAL_SPACING_M if profile == "v13_material_mesh" else radius * 1.5
    count = max(2, int(np.ceil(arc[-1] / (spacing or default_spacing))) + 1)
    stations = np.linspace(0, arc[-1], count)
    points = np.column_stack(
        [np.interp(stations, arc, points[:, axis]) for axis in range(3)]
    )
    _, normals, binormals = parallel_transport_frames(points)
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    theta = np.arange(sides) * 2 * np.pi / sides
    cross = np.vstack([np.zeros(2), np.column_stack([np.cos(theta), np.sin(theta)])])
    radii = np.full(count, radius)
    if end_stops:
        distance = np.minimum(arc, arc[-1] - arc)
        radii *= 1 + 0.6 * np.maximum(0, 1 - distance / (radius * 3)) ** 2
    if profile == "v13_material_mesh":
        return _write_fine_volume(path, points, arc, normals, binormals, radii,
                                  radius, sides, end_stops)
    offsets = radii[:, None, None] * cross[None]
    rest = np.concatenate(
        [
            np.column_stack([np.full(sides + 1, s), offset])
            for s, offset in zip(arc, offsets)
        ]
    )
    spawn = (
        points[:, None]
        + offsets[:, :, :1] * normals[:, None]
        + offsets[:, :, 1:] * binormals[:, None]
    ).reshape(-1, 3)
    elements = []
    stride = sides + 1
    for i in range(count - 1):
        for j in range(sides):
            a, b, c = sorted(
                [i * stride, i * stride + j + 1, i * stride + (j + 1) % sides + 1]
            )
            aa, bb, cc = np.array([a, b, c]) + stride
            elements.extend([[a, b, c, cc], [a, b, bb, cc], [a, aa, bb, cc]])
    elements = np.array(elements, dtype=np.int32)

    def determinants(v):
        p = v[elements]
        return np.linalg.det(p[:, 1:] - p[:, :1])

    negative = determinants(rest) < 0
    elements[negative, 1], elements[negative, 2] = (
        elements[negative, 2].copy(),
        elements[negative, 1].copy(),
    )
    if np.any(determinants(spawn) <= 0):
        raise ValueError(
            "Curved rope contains inverted tetrahedra; refine its initial route"
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        rest=rest,
        spawn=spawn,
        elements=elements,
        material_s_m=rest[:, 0],
        centerline=points,
        end_stops=bool(end_stops),
        radius_m=float(radius),
        mesh_profile=profile,
    )
    return path


def _write_fine_volume(path, points, arc, normals, binormals, radii,
                       radius, sides, end_stops):
    import tetgen

    line = np.column_stack((arc, np.zeros((len(arc), 2))))
    skin, faces = make_elastic_tube_mesh(line, radius=radius, radial_segments=sides)
    rings = np.arange(len(arc)*sides).reshape(-1, sides)
    skin[rings, 1:] *= (radii/radius)[:, None, None]
    switches = f"pq1.1/10a{MAX_TET_VOLUME_M3}YQ"
    rest, elements, *_ = tetgen.TetGen(skin, faces.astype(np.int32)).tetrahedralize(switches=switches)
    rest, elements = np.asarray(rest), np.asarray(elements, dtype=np.int32)
    if not np.allclose(rest[:len(skin)], skin, atol=1e-12, rtol=0):
        raise ValueError("TetGen changed authored surface vertex ordering")
    # Interpolate the complete material-to-world map for interior Steiner
    # vertices too. A straight reference avoids baking the initial knot in.
    def interpolate(values):
        return np.column_stack([np.interp(rest[:, 0], arc, values[:, i]) for i in range(3)])

    spawn = (interpolate(points) + rest[:, 1:2]*interpolate(normals)
             + rest[:, 2:3]*interpolate(binormals))
    corners = rest[elements]
    det = np.linalg.det(corners[:, 1:]-corners[:, :1])
    negative = det < 0
    elements[negative, 1], elements[negative, 2] = elements[negative, 2].copy(), elements[negative, 1].copy()
    corners = spawn[elements]
    spawn_det = np.linalg.det(corners[:, 1:]-corners[:, :1])
    if (not np.isfinite(rest).all() or not np.isfinite(spawn).all()
            or np.any(abs(det) <= 1e-18) or np.any(spawn_det <= 1e-18)):
        raise ValueError("Fine rope contains degenerate or inverted tetrahedra; refine its initial route")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, rest=rest, spawn=spawn, elements=elements,
                        material_s_m=rest[:, 0], centerline=points,
                        surface_ring_indices=rings, surface_faces=faces,
                        end_stops=bool(end_stops), radius_m=float(radius),
                        mesh_profile="v13_material_mesh", tetgen_switches=switches)
    return path
