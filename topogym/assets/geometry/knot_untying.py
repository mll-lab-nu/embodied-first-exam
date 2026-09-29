"""Deterministic open knot templates with two free tails, in metres.

Cut the outer, crossing-free arc of a Fourier trefoil and extend its two ends
smoothly into the exterior. The diagnostic closure is never a physical strand.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


FAMILY_KNOTS = {
    'two_overlap_loop': ('open_two_overlap_loop', 'not_a_knot_invariant', 2),
    'overhand_trefoil': ('open_overhand', 'trefoil_3_1', 3),
    'figure_eight': ('open_figure_eight', 'figure_eight_4_1', 4),
    'double_overhand': ('open_double_overhand', 'cinquefoil_5_1', 5),
}


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
    family: str = "overhand_trefoil"

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key in ("handedness", "family"):
                continue
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if self.handedness not in ("left", "right"):
            raise ValueError("handedness must be left or right")
        if self.family not in FAMILY_KNOTS:
            raise ValueError(f"Unknown knot family: {self.family}")
        if not .2 <= self.cut_angle_rad <= .6:
            raise ValueError("Cut must remain within the crossing-free outer arc")
        if isinstance(self.radial_segments, bool) or int(self.radial_segments) != self.radial_segments or self.radial_segments < 8:
            raise ValueError("radial_segments must be an integer >= 8")
        if self.segment_length_m > self.rope_radius_m:
            raise ValueError("Axial mesh spacing must not exceed rope radius")
        if self.tail_length_m < 3*self.planar_scale_m:
            raise ValueError("Free tails must extend outside the knot")

    def centerline(self):
        if self.family == 'two_overlap_loop':
            return two_overlap_centerline(self)
        a, h = self.planar_scale_m, self.crossing_height_m
        if self.family == 'overhand_trefoil':
            # Preserve the original v9 template exactly.
            t = np.linspace(np.pi+self.cut_angle_rad, 3*np.pi-self.cut_angle_rad, 2401)
            core = np.column_stack((a*(np.sin(t)+2*np.sin(2*t)),
                                    a*(np.cos(t)-2*np.cos(2*t)), h*np.sin(3*t)))
            tangent = np.column_stack((a*(np.cos(t)+4*np.cos(2*t)),
                                       a*(-np.sin(t)+4*np.sin(2*t)), 3*h*np.cos(3*t)))
        else:
            # Cut the exterior bottom arc, leaving the complete knot diagram.
            # Figure eight: ((2+cos 2t)cos 3t, (2+cos 2t)sin 3t, sin 4t).
            # Double overhand: a (2,5) torus curve, NOT the 5_2 twist knot.
            t = np.linspace(self.cut_angle_rad, 2*np.pi-self.cut_angle_rad, 4001)
            radial_frequency, turns, major, vertical_frequency = (
                (2, 3, 2, 4) if self.family == 'figure_eight' else (5, 2, 3, 5))
            radius = major+np.cos(radial_frequency*t)
            derivative = -radial_frequency*np.sin(radial_frequency*t)
            core = np.column_stack((a*radius*np.sin(turns*t), -a*radius*np.cos(turns*t),
                                    h*np.sin(vertical_frequency*t)))
            tangent = np.column_stack((a*(derivative*np.sin(turns*t)+turns*radius*np.cos(turns*t)),
                                       a*(-derivative*np.cos(turns*t)+turns*radius*np.sin(turns*t)),
                                       vertical_frequency*h*np.cos(vertical_frequency*t)))
        core[:, 2] += h+self.rope_radius_m+self.table_clearance_m

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
        if (self.handedness == "left") != (self.family == 'double_overhand'):
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


def template_diagram_matches(crossings, family):
    """Recognize these authored projections; not a general knot invariant."""
    count = FAMILY_KNOTS[family][2]
    visits = sorted((hit['segments'][side]+hit['parameters'][side], idx,
                     hit['first_over'] if side == 0 else not hit['first_over'])
                    for idx, hit in enumerate(crossings) for side in (0, 1))
    word = [idx for _, idx, _ in visits]
    over = [over for _, _, over in visits]
    alternating = all(a != b for a, b in zip(over, over[1:]))
    if family == 'two_overlap_loop':
        # A single bight whose two tails cross twice (a removable R-II pair).
        # Both crossings put the same tail above the other; no closed-knot claim.
        return (len(crossings) == 2 and word == [0, 1, 1, 0]
                and over == [True, True, False, False]
                and sum(hit['sign'] for hit in crossings) == 0)
    return len(crossings) == count and alternating and (
        (word == [0, 1, 2, 0, 3, 2, 1, 3] and sum(hit['sign'] for hit in crossings) == 0)
        if family == 'figure_eight' else
        (word == list(range(count))*2 and abs(sum(hit['sign'] for hit in crossings)) == count))


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
    count = FAMILY_KNOTS[layout.family][2]
    is_family = len(closed_crossing) == count and template_diagram_matches(crossing, layout.family)
    report = dict(rope_length_m=float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()),
                  bounds_m=[(p.min(axis=0)-r).tolist(), (p.max(axis=0)+r).tolist()],
                  endpoints_m=p[[0, -1]].tolist(), centerline_points=len(p),
                  crossings=crossing, crossing_count=len(crossing), over_under=over_under,
                  gauss_unsigned=[idx+1 for _, idx, _ in visits],
                  projected_writhe=sum(hit["sign"] for hit in crossing),
                  diagnostic_closure_crossings=len(closed_crossing),
                  trefoil_diagram_verified=is_trefoil,
                  family=layout.family, authored_projection_verified=is_family,
                  knot_diagram_verified=is_family and layout.family != "two_overlap_loop",
                  minimum_nonlocal_centerline_distance_m=distance,
                  minimum_nonlocal_surface_gap_m=distance-2*r,
                  nearest_nonlocal_segments=pair, material_neighbour_exclusion_m=float(np.pi*r),
                  minimum_bend_radius_m=float(radius.min()),
                  table_surface_clearance_m=float(p[:, 2].min()-r))
    if not is_family:
        raise ValueError(f"Expected the {layout.family} template diagram: {report}")
    if distance <= 2*r or radius.min() <= 2*r or report["table_surface_clearance_m"] < 0:
        raise ValueError(f"Tube intersects itself/table or bends too sharply: {report}")
    return report


def two_overlap_centerline(layout):
    """One broad loop and two separated over/under overlaps at its neck."""
    from scipy.interpolate import CubicSpline
    scale = layout.planar_scale_m/.032
    theta = np.linspace(np.deg2rad(-117), np.deg2rad(-423), 1001)
    floor = layout.rope_radius_m+layout.table_clearance_m
    circle = np.column_stack((.08*np.cos(theta), .08*np.sin(theta), np.zeros(len(theta))))
    control = np.array([circle[0], [-.018, -.103, .006], [.035, -.145, .022],
                        [-.01, -.195, .008], [-.10, -.255, 0.], [-.145, -.278, 0.]])
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(control, axis=0), axis=1))]
    direction = [-np.sin(theta[0]), np.cos(theta[0]), 0.]
    left = CubicSpline(arc, control, bc_type=((1, direction), (1, [-.89, -.455, 0.])))(
        np.linspace(0, arc[-1], 1001))
    right = left.copy(); right[:, 0] *= -1; right[:, 2] = 0.
    raw = np.vstack((left[:0:-1], circle, right[1:]))*scale
    raw[:, 2] += floor-raw[:, 2].min()
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))]
    samples = np.linspace(0, arc[-1], int(np.ceil(arc[-1]/layout.segment_length_m))+1)
    points = np.column_stack([np.interp(samples, arc, raw[:, k]) for k in range(3)])
    if layout.handedness == 'left':
        points[:, 0] *= -1
    return points


def generate_assets(output, layout=None):
    from topogym.utils.geometry.rope import make_elastic_tube_mesh, write_obj

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
    knot_type, closure_knot, _ = FAMILY_KNOTS[layout.family]
    report.update(parameters=asdict(layout), knot_type=knot_type, closure_knot=closure_knot,
                  physical_components=1, physical_endpoints=2, rest_shape="straight",
                  geometry_verified=True, physics_qualified=False, watertight=True,
                  mesh_vertices=len(vertices), mesh_faces=len(faces),
                  scope="initial_geometry_only", source={
                      'two_overlap_loop': 'authored_single_bight_two_overlaps',
                      'overhand_trefoil': 'https://katlas.org/wiki/3_1',
                      'figure_eight': 'https://katlas.org/wiki/4_1',
                      'double_overhand': 'https://katlas.org/wiki/T(5,2)',
                  }[layout.family])
    (folder/"centerline.json").write_text(json.dumps(dict(points_m=points.tolist(),
        coordinate_frame="local table surface; z up", physical_closed=False), indent=2)+"\n")
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    files = ("rope.obj", "rope_initial.glb", "centerline.json", "asset_report.json")
    (folder/"sha256.json").write_text(json.dumps({name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                                                for name in files}, indent=2)+"\n")
    return layout, report
