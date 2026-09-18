"""Deterministic open trefoil with two free tails, in metres above a tabletop.

Cut the outer, crossing-free arc of a Fourier trefoil and extend its two ends
smoothly into the exterior. The diagnostic closure is never a physical strand.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


@dataclass(frozen=True)
class KnotLayout:
    rope_radius_m: float = .004
    planar_scale_m: float = .032
    crossing_height_m: float = .008
    cut_angle_rad: float = .5
    tail_length_m: float = .18
    table_clearance_m: float = .001
    segment_length_m: float = .0025
    radial_segments: int = 12
    handedness: str = "right"

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key == "handedness":
                continue
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if self.handedness not in ("left", "right"):
            raise ValueError("handedness must be left or right")
        if not .2 <= self.cut_angle_rad <= .6:
            raise ValueError("Cut must remain within the crossing-free outer arc")
        if isinstance(self.radial_segments, bool) or int(self.radial_segments) != self.radial_segments or self.radial_segments < 8:
            raise ValueError("radial_segments must be an integer >= 8")
        if self.segment_length_m > self.rope_radius_m:
            raise ValueError("Axial mesh spacing must not exceed rope radius")
        if self.tail_length_m < 3*self.planar_scale_m:
            raise ValueError("Free tails must extend outside the knot")

    def centerline(self):
        t = np.linspace(np.pi+self.cut_angle_rad, 3*np.pi-self.cut_angle_rad, 2401)
        a, h = self.planar_scale_m, self.crossing_height_m
        core = np.column_stack((a*(np.sin(t)+2*np.sin(2*t)),
                                a*(np.cos(t)-2*np.cos(2*t)), h*np.sin(3*t)))
        core[:, 2] += h+self.rope_radius_m+self.table_clearance_m
        tangent = np.column_stack((a*(np.cos(t)+4*np.cos(2*t)),
                                   a*(-np.sin(t)+4*np.sin(2*t)), 3*h*np.cos(3*t)))

        def tail(point, direction):
            # A short C1 cubic turn, followed by a straight, graspable free end.
            direction = direction/np.linalg.norm(direction)
            side = np.sign(point[0])
            end_direction = np.array([side, -.35, 0.])
            end_direction /= np.linalg.norm(end_direction)
            end = point + a*np.array([side*1.3, -2.2, 0.])
            end[2] = self.rope_radius_m+self.table_clearance_m
            controls = np.array([point, point+direction*a*.8, end-end_direction*a*.8, end])
            u = np.linspace(0, 1, 401)[:, None]
            turn = ((1-u)**3*controls[0]+3*(1-u)**2*u*controls[1]
                    +3*(1-u)*u**2*controls[2]+u**3*controls[3])
            turn_length = np.linalg.norm(np.diff(turn, axis=0), axis=1).sum()
            remaining = self.tail_length_m-turn_length
            if remaining <= 0:
                raise ValueError("Tail is too short for its smooth exterior turn")
            return np.vstack((turn, end+end_direction*remaining))

        first, last = tail(core[0], -tangent[0]), tail(core[-1], tangent[-1])
        raw = np.vstack((first[:0:-1], core, last[1:]))
        s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))]
        samples = np.linspace(0, s[-1], int(np.ceil(s[-1]/self.segment_length_m))+1)
        points = np.column_stack([np.interp(samples, s, raw[:, k]) for k in range(3)])
        # This convention gives positive projected writhe for the right hand.
        if self.handedness == "left":
            points[:, 0] *= -1
        return points


def projected_crossings(points):
    """All transverse XY crossings, with interpolated height and oriented sign."""
    p = np.asarray(points, dtype=float)
    def cross(a, b):
        return a[..., 0]*b[..., 1]-a[..., 1]*b[..., 0]
    hits = []
    for i in range(len(p)-3):
        a, u = p[i], p[i+1]-p[i]
        j = np.arange(i+2, len(p)-1)
        b, v = p[j], p[j+1]-p[j]
        delta, divisor = b-a, cross(u, v)
        valid = np.abs(divisor) > 1e-14
        s = np.divide(cross(delta, v), divisor, out=np.full_like(divisor, -1), where=valid)
        t = np.divide(cross(delta, u), divisor, out=np.full_like(divisor, -1), where=valid)
        for k in np.flatnonzero((s >= 0) & (s < 1) & (t >= 0) & (t < 1)):
            pa, pb = a+s[k]*u, b[k]+t[k]*v[k]
            over = bool(pa[2] > pb[2])
            hits.append(dict(segments=[i, int(j[k])], parameters=[float(s[k]), float(t[k])],
                             xy_m=pa[:2].tolist(), height_gap_m=float(abs(pa[2]-pb[2])),
                             first_over=over, sign=int(np.sign(divisor[k])*(1 if over else -1))))
    return hits


def minimum_nonlocal_distance(points, exclusion_m):
    """Exact line-segment distances after excluding nearby material neighbours."""
    p = np.asarray(points)
    edges = np.diff(p, axis=0)
    lengths = np.linalg.norm(edges, axis=1)
    arc = np.r_[0., np.cumsum(lengths)]
    best, pair = np.inf, None
    for i, u in enumerate(edges):
        j = np.flatnonzero(arc[:-1]-arc[i+1] > exclusion_m)
        if not len(j):
            continue
        v, w = edges[j], p[i]-p[j]
        aa, bb = u@u, v@u
        cc, dd, ee = np.einsum("ij,ij->i", v, v), w@u, np.einsum("ij,ij->i", v, w)
        distances = []
        for s in (0., 1.):
            t = np.clip((ee+s*bb)/cc, 0, 1)
            distances.append(np.linalg.norm(w+s*u-t[:, None]*v, axis=1))
        for t in (0., 1.):
            s = np.clip((t*bb-dd)/aa, 0, 1)
            distances.append(np.linalg.norm(w+s[:, None]*u-t*v, axis=1))
        determinant = aa*cc-bb*bb
        valid = determinant > 1e-20
        s = np.divide(bb*ee-cc*dd, determinant, out=np.zeros_like(dd), where=valid)
        t = np.divide(aa*ee-bb*dd, determinant, out=np.zeros_like(dd), where=valid)
        interior = np.linalg.norm(w+s[:, None]*u-t[:, None]*v, axis=1)
        interior[~(valid & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1))] = np.inf
        distance = np.minimum(np.min(distances, axis=0), interior)
        k = np.argmin(distance)
        if distance[k] < best:
            best, pair = float(distance[k]), [i, int(j[k])]
    return best, pair


def inspect_geometry(points, layout):
    p = np.asarray(points)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 4 or not np.isfinite(p).all():
        raise ValueError("Expected a finite Nx3 open centerline")
    r = layout.rope_radius_m
    crossing = projected_crossings(p)
    visits = sorted((hit["segments"][side]+hit["parameters"][side], idx,
                     hit["first_over"] if side == 0 else not hit["first_over"])
                    for idx, hit in enumerate(crossing) for side in (0, 1))
    over_under = ["O" if over else "U" for _, _, over in visits]
    alternating = all(a != b for a, b in zip(over_under, over_under[1:]))
    # Close below the entire physical rope, with two vertical legs outside it.
    y = float(p[:, 1].min()-2*layout.planar_scale_m)
    closure = np.vstack((p, [p[-1, 0], y, p[-1, 2]], [p[0, 0], y, p[0, 2]], p[0]))
    closed_crossing = projected_crossings(closure)
    distance, pair = minimum_nonlocal_distance(p, np.pi*r)
    a, b = np.diff(p, axis=0)[:-1], np.diff(p, axis=0)[1:]
    denom = 2*np.linalg.norm(np.cross(a, b), axis=1)
    radius = np.divide(np.linalg.norm(a, axis=1)*np.linalg.norm(b, axis=1)*np.linalg.norm(a+b, axis=1),
                       denom, out=np.full_like(denom, np.inf), where=denom > 1e-14)
    is_trefoil = (len(crossing) == len(closed_crossing) == 3 and alternating
                  and abs(sum(hit["sign"] for hit in crossing)) == 3
                  and [idx for _, idx, _ in visits] == [0, 1, 2, 0, 1, 2])
    report = dict(rope_length_m=float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()),
                  bounds_m=[(p.min(axis=0)-r).tolist(), (p.max(axis=0)+r).tolist()],
                  endpoints_m=p[[0, -1]].tolist(), centerline_points=len(p),
                  crossings=crossing, crossing_count=len(crossing), over_under=over_under,
                  gauss_unsigned=[idx+1 for _, idx, _ in visits],
                  projected_writhe=sum(hit["sign"] for hit in crossing),
                  diagnostic_closure_crossings=len(closed_crossing),
                  trefoil_diagram_verified=is_trefoil,
                  minimum_nonlocal_centerline_distance_m=distance,
                  minimum_nonlocal_surface_gap_m=distance-2*r,
                  nearest_nonlocal_segments=pair, material_neighbour_exclusion_m=float(np.pi*r),
                  minimum_bend_radius_m=float(radius.min()),
                  table_surface_clearance_m=float(p[:, 2].min()-r))
    if not is_trefoil:
        raise ValueError(f"Expected one alternating trefoil diagram: {report}")
    if distance <= 2*r or radius.min() <= 2*r or report["table_surface_clearance_m"] < 0:
        raise ValueError(f"Tube intersects itself/table or bends too sharply: {report}")
    return report


def generate_assets(output, layout=None):
    from topogym.world.rope import make_elastic_tube_mesh, write_obj

    layout = layout or KnotLayout()
    points = layout.centerline()
    report = inspect_geometry(points, layout)
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    vertices, faces = make_elastic_tube_mesh(points, radius=layout.rope_radius_m,
                                            radial_segments=layout.radial_segments)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError("Rope skin must be watertight with positive oriented volume")
    write_obj(folder/"rope.obj", vertices, faces)
    # Color the last 25 mm of each tail for inspection, without extra bodies.
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    vertex_arc = np.r_[np.repeat(arc, layout.radial_segments), arc[0], arc[-1]]
    color = np.tile([220, 135, 48, 255], (len(vertices), 1))
    color[vertex_arc < .025] = [44, 115, 194, 255]
    color[vertex_arc > arc[-1]-.025] = [203, 60, 65, 255]
    mesh.visual.vertex_colors = color
    mesh.export(folder/"rope_initial.glb")
    report.update(parameters=asdict(layout), knot_type="open_overhand", closure_knot="trefoil_3_1",
                  physical_components=1, physical_endpoints=2, rest_shape="straight",
                  geometry_verified=True, physics_qualified=False, watertight=True,
                  mesh_vertices=len(vertices), mesh_faces=len(faces),
                  scope="initial_geometry_only", source="https://mathworld.wolfram.com/TrefoilKnot.html")
    (folder/"centerline.json").write_text(json.dumps(dict(points_m=points.tolist(),
        coordinate_frame="local table surface; z up", physical_closed=False), indent=2)+"\n")
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    files = ("rope.obj", "rope_initial.glb", "centerline.json", "asset_report.json")
    (folder/"sha256.json").write_text(json.dumps({name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                                                for name in files}, indent=2)+"\n")
    return layout, report
