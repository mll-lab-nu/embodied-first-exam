"""SiamMandalay Orbits: zero to four fixed rings and a trapped cord bight.

Metres; authored proportions from B-EB9Q-JqXA, not measured CAD. The reference
is a rendered solution demonstration. This module qualifies initial geometry
only, not the solver, terminal attachments, or a robot solution.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from shapely import affinity
from shapely.geometry import Point
import trimesh

from topogym.assets.library import resource_path
SOURCE_URL = "https://www.youtube.com/watch?v=B-EB9Q-JqXA"


@dataclass(frozen=True)
class OrbitsLayout:
    template_scale: float = 1.0
    ring_count: int = 4
    base_length_m: float = .47
    base_width_m: float = .18
    base_height_m: float = .024
    ring_radius_m: float = .066
    ring_tube_radius_m: float = .008
    post_spacing_m: float = .082
    lowest_ring_z_m: float = .126
    ring_step_m: float = .068
    post_radius_m: float = .0048
    ball_radius_m: float = .024
    ball_gap_m: float = .021
    cord_radius_m: float = .0022
    bight_radius_m: float = .016
    clearance_m: float = .0018
    handle_x_m: float = .43
    handle_length_m: float = .066
    handle_width_m: float = .037
    handle_height_m: float = .014
    handle_eye_radius_m: float = .0038
    handle_bend_radius_m: float = .006

    @property
    def post_x(self):
        return (np.arange(self.ring_count+1)-self.ring_count/2)*self.post_spacing_m

    @property
    def ring_x(self):
        return self.post_x[1:]-self.ring_radius_m

    @property
    def ring_z(self):
        return self.lowest_ring_z_m+np.arange(self.ring_count-1, -1, -1)*self.ring_step_m

    @property
    def ball_z(self):
        # The single-post teaching fixture retains the one-ring fixture's ball
        # height. lowest_ring_z_m is a height datum when no ring is present.
        top_ring_z = self.ring_z[0] if self.ring_count else self.lowest_ring_z_m
        return top_ring_z+self.ring_tube_radius_m+self.ball_gap_m+self.ball_radius_m

    @property
    def eyes(self):
        return np.array([[self.handle_x_m-.020*self.template_scale, -.007*self.template_scale],
                         [self.handle_x_m-.020*self.template_scale, .007*self.template_scale]])

    def scaled(self, factor):
        """Scale every length, including cord elbows, terminal eyes and joints."""
        if isinstance(factor, bool) or not np.isfinite(factor) or factor <= 0:
            raise ValueError("Uniform scale must be positive and finite")
        values = asdict(self)
        for name in values:
            if name.endswith("_m") or name == "template_scale":
                values[name] *= float(factor)
        return OrbitsLayout(**values).validate()

    def validate(self):
        if type(self.ring_count) is not int or self.ring_count not in (0, 1, 2, 3, 4):
            raise ValueError("Orbits supports zero to four rings; the video reference has four")
        values = np.asarray([v for k, v in asdict(self).items() if k != "ring_count"], dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Dimensions must be positive and finite")
        r, t = self.ring_radius_m, self.ring_tube_radius_m
        if self.ring_count and r <= t+self.ball_radius_m+abs(self.post_spacing_m-r)+self.clearance_m:
            raise ValueError("Ring aperture must admit the top ball")
        if self.ring_step_m <= 2*t+2*self.cord_radius_m:
            raise ValueError("Adjacent rings need vertical cord clearance")
        if self.lowest_ring_z_m <= self.base_height_m+t+2*self.cord_radius_m+self.clearance_m:
            raise ValueError("Lowest ring needs a clear underpass")
        if self.post_radius_m >= t or self.ball_radius_m <= self.post_radius_m:
            raise ValueError("Posts must join ring rims and fit under the stopper ball")
        if self.bight_radius_m <= self.post_radius_m+self.cord_radius_m+self.clearance_m:
            raise ValueError("Cord bight intersects the last post")
        if self.bight_radius_m+self.post_radius_m+self.cord_radius_m >= r:
            raise ValueError("Bight must surround only the last post")
        if not r+t+self.post_radius_m < 2*self.post_spacing_m-r:
            raise ValueError("Lower ring must clear the earlier taller post")
        if self.ring_count and self.base_length_m/2 <= abs(self.ring_x[0])+r+t:
            raise ValueError("Base must extend beyond the top ring")
        if not self.ring_count and self.base_length_m/2 <= self.ball_radius_m:
            raise ValueError("Base must extend beyond the single-post ball")
        if self.base_width_m/2 <= r+t:
            raise ValueError("Base too narrow for rings")
        if self.handle_x_m-self.handle_length_m/2 <= self.base_length_m/2+.03*self.template_scale:
            raise ValueError("Handle must lie beyond the base")
        if not self.cord_radius_m < self.handle_eye_radius_m < .006*self.template_scale:
            raise ValueError("Each authored terminal eye must admit cord and remain separate")
        if self.handle_height_m <= 2*self.cord_radius_m:
            raise ValueError("Handle too thin for terminal routing")
        return self


def tube_mesh(points, radius, sides=16):
    """One capped, connected tube, with a parallel-transport normal frame."""
    tangent = np.gradient(points, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.empty_like(tangent)
    normal[0] = np.cross(tangent[0], np.eye(3)[np.argmin(np.abs(tangent[0]))])
    normal[0] /= np.linalg.norm(normal[0])
    for i in range(1, len(points)):
        normal[i] = normal[i-1]-tangent[i]*np.dot(normal[i-1], tangent[i])
        normal[i] /= np.linalg.norm(normal[i])
    binormal = np.cross(tangent, normal)
    theta = np.arange(sides)*2*np.pi/sides
    vertices = (points[:, None]+radius*(np.cos(theta)[None, :, None]*normal[:, None]
                + np.sin(theta)[None, :, None]*binormal[:, None])).reshape(-1, 3)
    faces = []
    for i in range(len(points)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.extend([[a, b, b+sides], [a, b+sides, a+sides]])
    vertices = np.vstack([vertices, points[0], points[-1]])
    for j in range(sides):
        faces.append([len(vertices)-2, (j+1)%sides, j])
        a = (len(points)-1)*sides
        faces.append([len(vertices)-1, a+j, a+(j+1)%sides])
    return trimesh.Trimesh(vertices, faces, process=False)


def cord_centerline(layout):
    """Initial bight wraps the last post BELOW the lowest ring (video ~10 s).

    Two exposed legs lead to the handle. Exact hidden attachment construction
    is not visible; two small vertical eyes are an explicit authored convention.
    """
    l = layout
    s = l.template_scale
    xb = l.post_x[-1]
    z_base = l.base_height_m+l.cord_radius_m+l.clearance_m
    z_table = l.cord_radius_m+l.clearance_m
    elbow_radius = l.handle_bend_radius_m
    x = np.array([xb, xb+.025*s, l.base_length_m/2+.009*s, l.base_length_m/2+.038*s,
                  l.handle_x_m-.075*s, l.handle_x_m-.047*s, l.eyes[0, 0]-elbow_radius])
    ys = np.array([l.bight_radius_m, l.bight_radius_m, .020*s, .020*s, .010*s, .007*s, .007*s])
    zs = np.array([z_base, z_base, z_base, z_table, z_table,
                   l.handle_height_m+.010*s+elbow_radius, l.handle_height_m+.010*s+elbow_radius])
    if elbow_radius > .006*s + 1e-12:
        # Start the approach rise earlier; a large elbow alone merely moves
        # the high-curvature corner into the last short leg interpolation span.
        zs[4] = z_table+.85*(zs[-1]-z_table)
    sx = np.linspace(x[0], x[-1], 300)
    leg = np.column_stack([sx, PchipInterpolator(x, ys)(sx), PchipInterpolator(x, zs)(sx)])
    # Finish vertically through each actual eye; use a smooth elbow above wood.
    angle = np.linspace(0, np.pi/2, 24)
    elbow = np.column_stack([l.eyes[1, 0]-elbow_radius+elbow_radius*np.sin(angle), np.full(24, .007*s),
                             l.handle_height_m+.010*s+elbow_radius*np.cos(angle)])
    end = np.linspace(elbow[-1], [*l.eyes[1], l.clearance_m+.006*s], 40)
    positive = np.vstack([leg[:-1], elbow[:-1], end])
    negative = positive.copy(); negative[:, 1] *= -1
    theta = np.linspace(-np.pi/2, -3*np.pi/2, 80)
    bend = np.column_stack([xb+l.bight_radius_m*np.cos(theta),
                           l.bight_radius_m*np.sin(theta), np.full(len(theta), z_base)])
    return np.vstack([negative[::-1], bend[1:-1], positive])


def make_meshes(layout, *, initial_cord=None):
    l = layout.validate()
    base = trimesh.creation.box([l.base_length_m, l.base_width_m, l.base_height_m])
    base.apply_translation([0, 0, l.base_height_m/2])
    parts = {"base": base}
    for i, z in enumerate(l.ring_z):
        ring = trimesh.creation.torus(major_radius=l.ring_radius_m, minor_radius=l.ring_tube_radius_m,
                                     major_sections=128, minor_sections=24)
        ring.apply_translation([l.ring_x[i], 0, z])
        parts[f"ring_{i+1}"] = ring
    for i, x in enumerate(l.post_x):
        top = l.ball_z if i == 0 else l.ring_z[i-1]
        post = trimesh.creation.cylinder(radius=l.post_radius_m, height=top-l.base_height_m+.001*l.template_scale, sections=32)
        post.apply_translation([x, 0, (top+l.base_height_m-.001*l.template_scale)/2])
        parts[f"post_{i+1}"] = post
    ball = trimesh.creation.icosphere(subdivisions=3, radius=l.ball_radius_m)
    ball.apply_translation([l.post_x[0], 0, l.ball_z]); parts["stopper_ball"] = ball
    outline = affinity.scale(Point(l.handle_x_m, 0).buffer(1, quad_segs=48),
                             xfact=l.handle_length_m/2, yfact=l.handle_width_m/2)
    for eye in l.eyes:
        outline = outline.difference(Point(*eye).buffer(l.handle_eye_radius_m, quad_segs=24))
    handle = trimesh.creation.extrude_polygon(outline, l.handle_height_m, engine="earcut")
    handle.apply_translation([0, 0, l.clearance_m]); parts["handle"] = handle
    cord = cord_centerline(l) if initial_cord is None else np.asarray(initial_cord, dtype=float)
    parts["cord"] = tube_mesh(cord, l.cord_radius_m)
    return parts, cord


def winding_numbers(cord, post_x):
    """Close the two terminal points inside the handle for a planar winding audit."""
    closed = np.vstack([cord[:, :2], cord[0, :2]])
    result = []
    for x in post_x:
        p = closed-np.array([x, 0])
        a, b = p[:-1], p[1:]
        result.append(float(np.arctan2(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0],
                                      np.sum(a*b, axis=1)).sum()/(2*np.pi)))
    return result


def geometry_report(layout, parts, cord):
    l = layout
    statuses = {n: dict(watertight=bool(m.is_watertight), volume_positive=bool(m.volume > 0),
                       euler_number=int(m.euler_number), components=len(m.split()),
                       vertices=len(m.vertices), faces=len(m.faces)) for n, m in parts.items()}
    # Conservatively bound curve-to-solid surface distance by half sampling step.
    half = float(np.linalg.norm(np.diff(cord, axis=0), axis=1).max()/2)
    clearance = {}
    for name, mesh in parts.items():
        if name == "cord":
            continue
        distances = []
        for chunk in np.array_split(cord, 48):
            distances.extend(trimesh.proximity.closest_point_naive(mesh, chunk)[1])
        # Surface distance alone would accept a cord wholly inside a solid.
        inside = bool(mesh.contains(cord).any())
        clearance[name] = -1.0 if inside else float(min(distances)-l.cord_radius_m-half)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    distance = np.linalg.norm(cord[:, None]-cord[None], axis=2)
    distance[np.abs(arc[:, None]-arc[None]) < 6*l.cord_radius_m] = np.inf
    self_clear = float(distance.min()-2*l.cord_radius_m-2*half)
    wind = winding_numbers(cord, l.post_x)
    manager = trimesh.collision.CollisionManager()
    for n, m in parts.items():
        if n != "cord": manager.add_object(n, m)
    _, pairs = manager.in_collision_internal(return_names=True)
    allowed = {frozenset(("base", f"post_{i+1}")) for i in range(l.ring_count+1)}
    allowed |= {frozenset((f"ring_{i+1}", f"post_{i+2}")) for i in range(l.ring_count)}
    allowed.add(frozenset(("post_1", "stopper_ball")))
    unexpected = [sorted(p) for p in pairs if frozenset(p) not in allowed]
    missing = [sorted(p) for p in allowed if p not in {frozenset(pair) for pair in pairs}]
    centers = [parts[f"ring_{i+1}"].bounds.mean(axis=0) for i in range(l.ring_count)]
    checks = dict(
        meshes_closed_positive_connected=all(s["watertight"] and s["volume_positive"] and s["components"] == 1 for s in statuses.values()),
        ring_apertures_match_count=(sum(n.startswith("ring_") for n in parts) == l.ring_count
            and all(statuses[f"ring_{i+1}"]["euler_number"] == 0 for i in range(l.ring_count))),
        handle_has_two_authored_eyes=statuses["handle"]["euler_number"] == -2,
        post_count_matches_layout=sum(n.startswith("post_") for n in parts) == l.ring_count+1,
        ring_layout_matches_reference=all(np.allclose(c, [l.ring_x[i], 0, l.ring_z[i]], atol=1e-8) for i, c in enumerate(centers)),
        preceding_post_inside_each_ring=abs(l.post_spacing_m-l.ring_radius_m)+l.post_radius_m < l.ring_radius_m-l.ring_tube_radius_m,
        required_fixed_joints_present=not missing,
        no_unintended_rigid_intersections=not unexpected,
        cord_clear_of_solids=min(clearance.values()) > 0,
        cord_clear_of_table=float(cord[:, 2].min()-l.cord_radius_m) > 0,
        cord_no_nonlocal_overlap=self_clear > 0,
        bight_encircles_only_last_post=np.allclose(np.abs(wind), [0]*l.ring_count+[1], atol=1e-6),
        bight_below_lowest_ring=(float(cord[:, 2].max()+l.cord_radius_m) < l.ring_z[-1]-l.ring_tube_radius_m
                                if l.ring_count else True),
        endpoints_in_handle_eyes=np.allclose(cord[[0, -1], :2], l.eyes, atol=1e-8),
    )
    if not l.ring_count:
        checks.pop("preceding_post_inside_each_ring")
        checks.pop("bight_below_lowest_ring")
        checks["bight_below_stopper_ball"] = float(cord[:, 2].max()+l.cord_radius_m) < l.ball_z-l.ball_radius_m
    if l.ring_count == 4:
        # Retain reference-report keys for existing consumers, never label a
        # reduced fixture as having four apertures or five posts.
        checks["four_real_ring_apertures"] = checks["ring_apertures_match_count"]
        checks["five_posts_present"] = checks["post_count_matches_layout"]
    return dict(scope="static_initial_geometry_only", passed=bool(all(checks.values())),
                checks={k:bool(v) for k,v in checks.items()}, dimensions=asdict(l), meshes=statuses,
                cord_clearance_lower_bounds_m=clearance, cord_self_clearance_bound_m=self_clear,
                cord_length_m=float(arc[-1]), winding_about_posts=wind,
                intentional_fixed_joints=[sorted(p) for p in sorted(allowed, key=lambda v: sorted(v))],
                unexpected_rigid_intersections=unexpected, missing_fixed_joints=missing,
                terminal_model="Two authored eyes; frozen cord endpoints, no attachment solver",
                physics_qualified=False, solution_verified=False, robot_reachability_verified=False)


def finish(mesh, name):
    from PIL import Image
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals
    if name == "cord":
        result = mesh.copy()
        result.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
            name="orbits_yellow_cord", baseColorFactor=[.98, .78, .015, 1], roughnessFactor=.65, metallicFactor=0))
        return result
    vertices = mesh.vertices[mesh.faces].reshape(-1, 3)
    normals = mesh.vertex_normals[mesh.faces].reshape(-1, 3)
    dominant = np.repeat(np.argmax(np.abs(mesh.face_normals), axis=1), 3)
    u, v = np.where(dominant == 0, 1, 0), np.where(dominant == 2, 1, 2)
    rows = np.arange(len(vertices))
    uv = np.column_stack([vertices[rows, u], vertices[rows, v]])/.14+.5
    path = resource_path("hedgehog_in_cage/materials/" + (
        "dark_wood.png" if name == "base" or name.startswith("post_") else "light_wood.png"))
    with Image.open(path) as source: texture = source.convert("RGB")
    result = trimesh.Trimesh(vertices, np.arange(len(vertices)).reshape(-1, 3), vertex_normals=normals, process=False)
    result.visual = TextureVisuals(uv=uv, material=PBRMaterial(name=f"orbits_{name}",
        baseColorFactor=[1., .85, .65, 1.], baseColorTexture=texture, roughnessFactor=.40, metallicFactor=0))
    return result


def generate_assets(output, layout=None, *, initial_cord=None):
    folder = Path(output); folder.mkdir(parents=True, exist_ok=True)
    layout = (layout or OrbitsLayout()).validate()
    parts, cord = make_meshes(layout, initial_cord=initial_cord)
    report = geometry_report(layout, parts, cord)
    if not report["passed"]:
        raise ValueError(f"Invalid Orbits initial geometry: {json.dumps(report, indent=2)}")
    scene = trimesh.Scene()
    for name, mesh in parts.items():
        mesh.export(folder/f"{name}.obj")
        visual = finish(mesh, name); visual.export(folder/f"{name}.glb")
        scene.add_geometry(visual, node_name=name)
    scene.export(folder/"scene.glb")
    np.save(folder/"cord_centerline.npy", cord)
    (folder/"layout.json").write_text(json.dumps(asdict(layout), indent=2)+"\n")
    (folder/"geometry_report.json").write_text(json.dumps(report, indent=2)+"\n")
    (folder/"sha256.json").write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.iterdir()) if p.is_file() and p.name != "sha256.json"}, indent=2)+"\n")
    return layout, report
