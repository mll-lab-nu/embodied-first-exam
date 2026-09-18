"""Photo-informed two-horseshoe assembly, with real holes and free chain links.

The previous three-link fixture remains a separate contact regression. This
module builds the complete *initial assembly*, not a certified puzzle solution.
Dimensions are declared prototype values, not measurements of the user photo.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from topogym.tasks._rigid_geometry import cylinder_between, primitive, vector_text

ASSET_ROOT = Path(__file__).resolve().parents[3] / "assets/tasks/horseshoe_ring/photo_reference_v1"


def load_template(path=None):
    return json.loads(Path(path or ASSET_ROOT / "template.json").read_text())


def ellipse(a, b, count=128):
    theta = np.arange(count) * 2 * np.pi / count
    return np.column_stack((a*np.cos(theta), b*np.sin(theta), np.zeros(count)))


def tube_mesh(points, radius, radial_segments=16):
    """Closed, smooth tube around a planar convex loop, with no capped aperture."""
    points = np.asarray(points)
    tangent = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.cross(tangent, np.array([0., 0., 1.]))
    phi = np.arange(radial_segments)*2*np.pi/radial_segments
    vertices = (points[:, None, :] + radius * (
        normal[:, None, :]*np.cos(phi)[None, :, None]
        + np.array([0., 0., 1.])*np.sin(phi)[None, :, None])).reshape(-1, 3)
    faces = []
    for i in range(len(points)):
        for j in range(radial_segments):
            a = i*radial_segments+j
            b = ((i+1) % len(points))*radial_segments+j
            c = ((i+1) % len(points))*radial_segments+(j+1) % radial_segments
            d = i*radial_segments+(j+1) % radial_segments
            faces.extend(((a, b, c), (a, c, d)))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()
    return mesh


@dataclass
class Loop:
    name: str
    body: str
    center: np.ndarray
    rotation: Rotation
    radii: np.ndarray
    wire_radius: float
    segments: int

    def points(self, count=None):
        return self.rotation.apply(ellipse(*self.radii, count or self.segments)) + self.center

    def linking(self, other):
        """Oriented intersections with this planar ellipse's spanning disk."""
        p = self.rotation.inv().apply(other.points()-self.center)
        q = np.roll(p, -1, axis=0)
        crossing = ((p[:, 2] <= 0) & (q[:, 2] > 0)) | ((q[:, 2] <= 0) & (p[:, 2] > 0))
        p, q = p[crossing], q[crossing]
        if not len(p):
            return 0
        t = p[:, 2]/(p[:, 2]-q[:, 2])
        hit = p+t[:, None]*(q-p)
        inside = np.sum((hit[:, :2]/self.radii)**2, axis=1) < 1
        return int(np.sign(q[:, 2]-p[:, 2])[inside].sum())


@dataclass
class Body:
    name: str
    visual: trimesh.Trimesh
    # Convex pieces describe the open horseshoe band; loops use capsules.
    convex: list
    loops: list[Loop]
    color: tuple


def band_centerline(h, unit, angles):
    """Open oval, squared U-like outline, or inward-waisted outline in XY."""
    a, b = np.asarray(h["ellipse_radii"])*unit
    power = float(h.get("outline_power", 2.))
    depth = float(h.get("waist_depth", 0.))*unit
    if power == 2. and depth == 0. and "terminal_tip_mm" not in h:
        return np.column_stack((a*np.cos(angles), b*np.sin(angles), np.zeros(len(angles))))
    cs, sn = np.cos(angles), np.sin(angles)
    x = a*np.sign(cs)*np.abs(cs)**(2/power)
    y = b*np.sign(sn)*np.abs(sn)**(2/power)
    y -= sn*depth*np.exp(-(x/(.48*a))**2)
    if "terminal_tip_mm" in h:
        alpha = np.radians(h["mouth_half_angle_deg"])
        end_x = a*np.cos(alpha)**(2/power)
        end_y = b*np.sin(alpha)**(2/power)-np.sin(alpha)*depth*np.exp(-(end_x/(.48*a))**2)
        target = np.asarray(h["terminal_tip_mm"])*unit
        weight = ((cs+1)/(np.cos(alpha)+1))**4
        x += (target[0]-end_x)*weight
        y += np.sign(sn)*(target[1]-end_y)*weight
    return np.column_stack((x, y, np.zeros(len(angles))))


def horseshoe_band(h, unit):
    """Sweep a bevelled rectangular profile along an open elliptic arc."""
    a, b = np.asarray(h["ellipse_radii"])*unit
    width, thickness, bevel = np.array([h["band_width"], h["thickness"], h["edge_bevel"]])*unit
    w, t = width/2, thickness/2
    profile = np.array([(w-bevel, -t), (w, -t+bevel), (w, t-bevel), (w-bevel, t),
                        (-w+bevel, t), (-w, t-bevel), (-w, -t+bevel), (-w+bevel, -t)])
    alpha = np.radians(h["mouth_half_angle_deg"])
    angles = np.linspace(alpha, 2*np.pi-alpha, int(h["collision_segments"])+1)
    centers = band_centerline(h, unit, angles)
    if float(h.get("outline_power", 2.)) == 2. and float(h.get("waist_depth", 0.)) == 0. and "terminal_tip_mm" not in h:
        normals = np.column_stack((b*np.cos(angles), a*np.sin(angles), np.zeros(len(angles))))
    else:
        tangent = band_centerline(h, unit, angles+1e-5)-band_centerline(h, unit, angles-1e-5)
        normals = np.column_stack((tangent[:, 1], -tangent[:, 0], np.zeros(len(angles))))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    rings = centers[:, None, :] + normals[:, None, :]*profile[None, :, 0, None]
    rings[:, :, 2] += profile[None, :, 1]
    pieces = [trimesh.convex.convex_hull(np.concatenate((p, q))) for p, q in zip(rings[:-1], rings[1:])]
    faces = []
    for i in range(len(rings)-1):
        for j in range(8):
            a0, b0, c0, d0 = 8*i+j, 8*(i+1)+j, 8*(i+1)+(j+1)%8, 8*i+(j+1)%8
            faces.extend(((a0, b0, c0), (a0, c0, d0)))
    for base, reverse in ((0, True), (8*(len(rings)-1), False)):
        for j in range(1, 7):
            face = (base, base+j, base+j+1)
            faces.append(face[::-1] if reverse else face)
    mesh = trimesh.Trimesh(vertices=rings.reshape(-1, 3), faces=faces, process=True)
    mesh.fix_normals()
    return mesh, pieces


class HorseshoeAssembly:
    def __init__(self, template=None, scale=2.0):
        self.template = template or load_template()
        self.scale = float(scale)
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Scale must be positive and finite")
        t = self.template
        if t["units"] != "mm" or t["chain"]["spans"] != 2:
            raise ValueError("This template requires mm dimensions and two chain spans")
        h, c, r = t["horseshoe"], t["chain"], t["target_ring"]
        power, waist = float(h.get("outline_power", 2.)), float(h.get("waist_depth", 0.))
        if not np.isfinite([power, waist]).all() or not 1.5 <= power <= 4 or not 0 <= waist <= .2*min(h["ellipse_radii"]):
            raise ValueError("Outline power must lie in [1.5, 4], waist depth in [0, 0.2 * minimum shoe radius]")
        if "terminal_tip_mm" in h:
            tip = np.asarray(h["terminal_tip_mm"], dtype=float)
            if tip.shape != (2,) or not np.isfinite(tip).all() or (tip <= 0).any():
                raise ValueError("Terminal tip must contain two finite positive coordinates")
        ring_radii = np.asarray(r.get("centerline_radii", [r["centerline_radius"]]*2), dtype=float)
        if ring_radii.shape != (2,) or not np.isfinite(ring_radii).all() or (ring_radii <= r["wire_radius"]).any():
            raise ValueError("Target ellipse needs two finite radii larger than its wire radius")
        phase = float(r.get("initial_phase_deg", 0.))
        if not np.isfinite(phase):
            raise ValueError("Target ellipse phase must be finite")
        n = c["links_per_span"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1 or n % 2 != 1:
            raise ValueError("Coplanar terminal eyes require a positive odd number of alternating links")
        dims = [*h["ellipse_radii"], h["band_width"], h["thickness"], h["edge_bevel"],
                h["eye_offset_x"], *h["eye_radii"], h["eye_wire_radius"], *c["link_radii"],
                c["wire_radius"], c["center_spacing"], c["eye_to_link_center"],
                r["centerline_radius"], r["wire_radius"], t["density_kg_m3"]]
        if not np.isfinite(dims).all() or min(dims) <= 0:
            raise ValueError("All dimensions and density must be positive and finite")
        if not 0 < h["mouth_half_angle_deg"] < 90:
            raise ValueError("Horseshoe mouth angle must lie between 0 and 90 degrees")
        if not 0 < r["initial_tilt_deg"] <= 90:
            raise ValueError("Initial target tilt must lie in (0, 90] degrees")
        if not np.isfinite(float(h.get("eye_roll_deg", 0.))):
            raise ValueError("Terminal-eye roll must be finite")
        if h["edge_bevel"] >= min(h["band_width"], h["thickness"])/2:
            raise ValueError("Bevel removes the horseshoe cross-section")
        for p in (h, c, r):
            if not isinstance(p["collision_segments"], int) or p["collision_segments"] < 24:
                raise ValueError("Collision loops need at least 24 segments")
        if h["eye_wire_radius"] >= min(h["eye_radii"]) or c["wire_radius"] >= min(c["link_radii"]) or r["wire_radius"] >= r["centerline_radius"]:
            raise ValueError("Every loop must preserve its aperture")
        self.unit = u = scale/1000
        tip_x, tip_y = band_centerline(h, u, np.array([np.radians(h["mouth_half_angle_deg"])]))[0, :2]
        half_span = ((n-1)*c["center_spacing"]/2+c["eye_to_link_center"])*u
        shoe_center = half_span+h["eye_offset_x"]*u+tip_x
        self.bodies, self.loops, self.edges = [], {}, []
        band, pieces = horseshoe_band(h, u)
        for side, direction in (("left", -1), ("right", 1)):
            rotation = Rotation.from_euler("z", 0 if direction == -1 else np.pi)
            transform = np.eye(4)
            transform[:3, :3] = rotation.as_matrix()
            transform[:3, 3] = [direction*shoe_center, 0., 0.]
            visual = band.copy().apply_transform(transform)
            convex = [p.copy().apply_transform(transform) for p in pieces]
            loops = []
            for branch, sign in (("upper", 1), ("lower", -1)):
                name = f"{side}_{branch}_eye"
                loop = Loop(name, f"horseshoe_{side}", np.array([direction*half_span, sign*tip_y, 0.]),
                            Rotation.from_euler("x", float(h.get("eye_roll_deg", 0.)), degrees=True),
                            np.asarray(h["eye_radii"])*u, h["eye_wire_radius"]*u,
                            c["collision_segments"])
                loops.append(loop)
                eye = tube_mesh(ellipse(*loop.radii), loop.wire_radius)
                eye.vertices = loop.rotation.apply(eye.vertices)
                eye.apply_translation(loop.center)
                visual = trimesh.util.concatenate((visual, eye))
                self.loops[name] = loop
            self.bodies.append(Body(f"horseshoe_{side}", visual, convex, loops, (.58, .63, .69, 1.)))
        for branch, sign in (("upper", 1), ("lower", -1)):
            names = [f"left_{branch}_eye"]
            for i in range(n):
                name = f"chain_{branch}_{i+1}"
                rotation = Rotation.from_euler("x", (90 if i % 2 == 0 else 0)
                                               +float(h.get("eye_roll_deg", 0.)), degrees=True)
                center = np.array([(i-(n-1)/2)*c["center_spacing"]*u, sign*tip_y, 0.])
                loop = Loop(name, name, center, rotation, np.asarray(c["link_radii"])*u,
                            c["wire_radius"]*u, c["collision_segments"])
                visual = tube_mesh(ellipse(*loop.radii), loop.wire_radius)
                visual.vertices = rotation.apply(visual.vertices)+center
                self.bodies.append(Body(name, visual, [], [loop], (.52, .57, .62, 1.)))
                self.loops[name] = loop
                names.append(name)
            names.append(f"right_{branch}_eye")
            self.edges.extend(zip(names[:-1], names[1:]))
        target_rotation = Rotation.from_euler("y", r["initial_tilt_deg"], degrees=True)
        if phase:
            target_rotation = target_rotation*Rotation.from_euler("z", phase, degrees=True)
        target = Loop("target_ring", "target_ring", np.zeros(3), target_rotation,
                      ring_radii*u, r["wire_radius"]*u,
                      r["collision_segments"])
        visual = tube_mesh(ellipse(*target.radii, count=192), target.wire_radius, radial_segments=24)
        visual.vertices = target.rotation.apply(visual.vertices)
        self.bodies.append(Body("target_ring", visual, [], [target], (.72, .76, .80, 1.)))
        self.loops[target.name] = target

    def topology_report(self):
        adjacent = [{"a": a, "b": b, "linking_number": self.loops[a].linking(self.loops[b])}
                    for a, b in self.edges]
        target = self.loops["target_ring"]
        target_pairs = {n: target.linking(loop) for n, loop in self.loops.items() if n != target.name}
        expected = {frozenset(pair) for pair in self.edges}
        accidental = []
        loops = list(self.loops.values())
        for i, a in enumerate(loops):
            for b in loops[i+1:]:
                if frozenset((a.name, b.name)) not in expected and (v := a.linking(b)):
                    accidental.append(dict(a=a.name, b=b.name, linking_number=v))
        # A free ring placed off to the side also has zero pairwise linking.
        # Require both chain-span axes to pass through its *bore* initially.
        enclosed = []
        for branch in ("upper", "lower"):
            ends = np.array([self.loops[f"{side}_{branch}_eye"].center for side in ("left", "right")])
            p, q = target.rotation.inv().apply(ends-target.center)
            t = p[2]/(p[2]-q[2])
            hit = p+t*(q-p)
            # Uniform contraction by wire/minor_axis is a conservative bore
            # subset for an ellipse, and exactly radius-wire for a circle.
            bore = target.radii*(1-target.wire_radius/min(target.radii))
            enclosed.append(bool(0 < t < 1 and np.sum((hit[:2]/bore)**2) < 1))
        return dict(adjacent_pairs=adjacent, adjacent_pairs_linked=all(abs(p["linking_number"]) == 1 for p in adjacent),
                    target_pair_linking_numbers=target_pairs,
                    target_not_hopf_linked_to_any_single_loop=all(v == 0 for v in target_pairs.values()),
                    unexpected_linked_pairs=accidental, target_encloses_both_chain_spans=all(enclosed),
                    qualification="initial loop incidence only; zero pairwise linking does not certify extraction")


def sample_segments(points, max_step):
    samples = []
    for p, q in zip(points, np.roll(points, -1, axis=0)):
        n = max(1, int(np.ceil(np.linalg.norm(q-p)/max_step)))
        samples.append(p+(q-p)*np.arange(n)[:, None]/n)
    return np.concatenate(samples)


def point_segment_distance(points, segments):
    p = np.asarray(points)[:, None, :]
    a, b = segments[None, :, 0, :], segments[None, :, 1, :]
    v = b-a
    t = np.clip(np.sum((p-a)*v, axis=2)/np.sum(v*v, axis=2), 0., 1.)
    return np.linalg.norm(p-(a+t[:, :, None]*v), axis=2).min(axis=1)


def geometry_report(assembly):
    """Conservative capsule clearance bounds and direct mesh band checks.

    Each centerline sample is at most half a sample interval from an arbitrary
    point on its segment. Subtracting that interval gives a lower bound for
    capsule separation. This checks cross-body pairs, including terminal eyes.
    """
    step = .15*assembly.unit
    loops = list(assembly.loops.values())
    samples = {p.name: sample_segments(p.points(), step) for p in loops}
    results = []
    for i, a in enumerate(loops):
        for b in loops[i+1:]:
            if a.body == b.body:
                continue
            points = b.points()
            segments = np.stack((points, np.roll(points, -1, axis=0)), axis=1)
            distance = point_segment_distance(samples[a.name], segments).min()
            results.append(dict(a=a.name, b=b.name, lower_bound_m=float(distance-a.wire_radius-b.wire_radius-step/2)))
    for body in assembly.bodies:
        if not body.convex:
            continue
        band = trimesh.util.concatenate(body.convex)
        for loop in loops:
            if loop.body == body.name:
                continue
            pts = samples[loop.name]
            _, distances, _ = trimesh.proximity.closest_point(band, pts)
            clearance = distances.min()-loop.wire_radius-step/2
            # Signed occupancy catches a loop placed wholly inside a solid band.
            if any(piece.contains(pts).any() for piece in body.convex
                   if np.all(pts.max(axis=0) >= piece.bounds[0]) and np.all(pts.min(axis=0) <= piece.bounds[1])):
                clearance = -abs(clearance)-step
            results.append(dict(a=body.name+"_band", b=loop.name, lower_bound_m=float(clearance)))
    left, right = (b for b in assembly.bodies if b.convex)
    # In this initial layout, the two bands are separated along x.
    band_gap = min(p.bounds[0, 0] for p in right.convex)-max(p.bounds[1, 0] for p in left.convex)
    results.append(dict(a=left.name+"_band", b=right.name+"_band", lower_bound_m=float(band_gap)))
    topology = assembly.topology_report()
    minimum = min(p["lower_bound_m"] for p in results)
    bounds = trimesh.util.concatenate([b.visual for b in assembly.bodies]).bounds
    return dict(template_id=assembly.template["template_id"], scale=assembly.scale,
        geometry_status=assembly.template["geometry_status"], body_count=len(assembly.bodies),
        horseshoe_count=2, chain_spans=2, links_per_span=assembly.template["chain"]["links_per_span"],
        target_ring_count=1, bounds_m=bounds.tolist(), extent_m=(bounds[1]-bounds[0]).tolist(),
        minimum_clearance_lower_bound_m=minimum, clearance_pairs=results,
        no_initial_collision=minimum > 0, topology=topology,
        passed=minimum > 0 and topology["adjacent_pairs_linked"] and not topology["unexpected_linked_pairs"]
            and topology["target_not_hopf_linked_to_any_single_loop"] and topology["target_encloses_both_chain_spans"],
        extraction_route_verified=False,
        note="Sample bounds qualify the generated initial compound geometry; physical settling and puzzle solution are separate checks")


def write_body(folder, body, density):
    """One URDF link per physical body. All apertures survive collision loading."""
    folder.mkdir(parents=True, exist_ok=True)
    mesh = body.visual.copy()
    # Each body is authored in assembly coordinates, then centered at its COM.
    mesh.density = density
    props = mesh.mass_properties
    origin = props.center_mass
    mesh.apply_translation(-origin)
    mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
        baseColorFactor=body.color, metallicFactor=.8, roughnessFactor=.26))
    mesh.export(folder/f"{body.name}.glb", include_normals=True)
    root = ET.Element("robot", name=body.name)
    link = ET.SubElement(root, "link", name=body.name)
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz="0 0 0", rpy="0 0 0")
    ET.SubElement(inertial, "mass", value=str(props.mass))
    mat = props.inertia
    ET.SubElement(inertial, "inertia", **{f"i{a}{b}": str(mat[i, j]) for a, b, i, j in (
        ("x", "x", 0, 0), ("y", "y", 1, 1), ("z", "z", 2, 2),
        ("x", "y", 0, 1), ("x", "z", 0, 2), ("y", "z", 1, 2))})
    for loop in body.loops:
        points = loop.points()-origin
        for p, q in zip(points, np.roll(points, -1, axis=0)):
            cylinder_between(link, p, q, loop.wire_radius, body.color)
            primitive(link, "sphere", {"radius": loop.wire_radius}, p, color=body.color)
    # Shared primitive helper emits visuals too; retain only the smooth GLB.
    for node in list(link.findall("visual")):
        link.remove(node)
    for i, part in enumerate(body.convex):
        name = f"band_{i:03d}.obj"
        part.copy().apply_translation(-origin).export(folder/name)
        ET.SubElement(ET.SubElement(ET.SubElement(link, "collision"), "geometry"), "mesh", filename=name)
    node = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=f"{body.name}.glb")
    ET.SubElement(ET.SubElement(node, "material", name="steel"), "color", rgba=vector_text(body.color))
    ET.indent(root)
    ET.ElementTree(root).write(folder/f"{body.name}.urdf", encoding="unicode", xml_declaration=True)
    return dict(name=body.name, origin_m=origin.tolist(), mass_kg=float(props.mass),
                inertia_kg_m2=props.inertia.tolist(), collision_shapes=len(link.findall("collision")),
                physical_links=1, inter_body_joints=0, fixed=False,
                mass_model="density of smooth component meshes; overlap at welded eye roots retained")


def generate_assets(output, *, template=None, scale=2.0):
    output = Path(output)
    assembly = HorseshoeAssembly(template, scale)
    report = geometry_report(assembly)
    output.mkdir(parents=True, exist_ok=True)
    (output/"geometry_report.json").write_text(json.dumps(report, indent=2)+"\n")
    if not report["passed"]:
        bad = sorted(report["clearance_pairs"], key=lambda p: p["lower_bound_m"])[:3]
        raise ValueError(f"Invalid initial assembly: {bad}; topology={report['topology']}")
    report["bodies"] = [write_body(output/body.name, body, assembly.template["density_kg_m3"])
                        for body in assembly.bodies]
    scene = trimesh.Scene()
    for body in assembly.bodies:
        mesh = body.visual.copy()
        mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
            baseColorFactor=body.color, metallicFactor=.8, roughnessFactor=.26))
        scene.add_geometry(mesh, node_name=body.name, geom_name=body.name)
    scene.export(output/"assembly.glb")
    (output/"template.json").write_text(json.dumps(assembly.template, ensure_ascii=False, indent=2)+"\n")
    (output/"geometry_report.json").write_text(json.dumps(report, indent=2)+"\n")
    return assembly, report
