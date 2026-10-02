"""Photo-proportion Keyhole plates with an open fork and a closed stepped bore.

Horizontal polygon slabs give disjoint convex collision prisms. The visual uses
the same slabs, with shared-edge subdivisions, so the bore cannot be silently
filled by a whole-piece convex hull. Dimensions are authored, not measured CAD.
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

from topogym.utils.geometry.rigid_geometry import vector_text

from topogym.assets.library import resource_path


def load_template():
    return json.loads((resource_path("cast_keyhole/template.json")).read_text())


def arc(spec, segments, reverse=False):
    angles = np.linspace(np.pi, 0, segments+1)
    points = np.asarray(spec["center"]) + spec["radius"]*np.c_[np.cos(angles), np.sin(angles)]
    # Exact endpoints prevent nearly duplicate horizontal slab coordinates.
    points[[0, -1], 1] = spec["center"][1]
    return points[::-1] if reverse else points


def outlines(template, name):
    p, n = template[name], template["arc_segments"]
    outside = arc(p["outer_arc"], n)
    inside = arc(p["inner_arc"], n)
    if name == "gold":
        return [np.concatenate((outside, p["right_to_inner_arc"], inside[::-1], p["inner_arc_to_left"]))]
    return [np.concatenate((outside, p["outer_bottom"])),
            np.concatenate((inside, p["inner_right_to_left"]))]


def polygon_slabs(rings):
    """Even/odd polygon fill, including holes, cut into convex trapezoids."""
    rings = [np.round(ring, 8) for ring in rings]
    edges = [(a, b) for ring in rings for a, b in zip(ring, np.roll(ring, -1, axis=0))]
    ys = np.unique(np.concatenate(rings)[:, 1])
    cells = []
    for lo, hi in zip(ys[:-1], ys[1:]):
        mid = (lo+hi)/2
        hits = []
        for a, b in edges:
            if min(a[1], b[1]) < mid < max(a[1], b[1]):
                x = lambda y: a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
                hits.append((x(mid), x(lo), x(hi)))
        hits.sort()
        if len(hits) % 2:
            raise ValueError("Invalid outline scanline")
        for left, right in zip(hits[::2], hits[1::2]):
            cell = np.round([[left[1], lo], [right[1], lo], [right[2], hi], [left[2], hi]], 8)
            if right[0]-left[0] <= 1e-9:
                raise ValueError("Degenerate or crossed outline")
            cells.append(cell)
    return cells


def extrude_slabs(cells, thickness):
    """Weld a watertight exterior and export exact, nonoverlapping convex cells."""
    row_points = {}
    for cell in cells:
        for x, y in cell:
            row_points.setdefault(y, set()).add(x)
    vertices, faces = [], []
    perimeter_edges = {}
    collision = []
    for cell in cells:
        # Include other slabs' endpoints on shared horizontal edges; no T joints.
        outline = []
        for a, b in zip(cell, np.roll(cell, -1, axis=0)):
            if np.linalg.norm(b-a) < 1e-9:
                continue
            outline.append(a)
            if a[1] == b[1]:
                xs = sorted(x for x in row_points[a[1]] if min(a[0], b[0])+1e-9 < x < max(a[0], b[0])-1e-9)
                if b[0] < a[0]:
                    xs.reverse()
                outline.extend(np.array([x, a[1]]) for x in xs)
        outline = np.asarray(outline)
        center = outline.mean(axis=0)
        for side in (-1, 1):
            for a, b in zip(outline, np.roll(outline, -1, axis=0)):
                tri = np.c_[np.vstack((center, a, b)), np.full(3, side*thickness/2)]
                if side < 0:
                    tri = tri[::-1]
                index = len(vertices)
                vertices.extend(tri)
                faces.append([index, index+1, index+2])
        for a, b in zip(outline, np.roll(outline, -1, axis=0)):
            key = tuple(sorted((tuple(a), tuple(b))))
            if key in perimeter_edges:
                del perimeter_edges[key]
            else:
                perimeter_edges[key] = (a, b)
        collision.append(trimesh.convex.convex_hull(np.vstack((
            np.c_[cell, np.full(4, -thickness/2)], np.c_[cell, np.full(4, thickness/2)]))))
    for a, b in perimeter_edges.values():
        index = len(vertices)
        vertices.extend([[*a, -thickness/2], [*b, -thickness/2], [*b, thickness/2], [*a, thickness/2]])
        faces.extend([[index, index+1, index+2], [index, index+2, index+3]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True), collision


@dataclass
class KeyholeBody:
    name: str
    visual: trimesh.Trimesh
    collision: list
    color: tuple
    rings_mm: list


class KeyholeAssembly:
    def __init__(self, template=None, scale=3.0):
        self.template = t = load_template() if template is None else template
        self.scale = float(scale)
        dims = [self.scale, t["thickness"], t["density_kg_m3"], t["nominal_width"], t["nominal_length"]]
        if t["units"] != "mm" or not np.isfinite(dims).all() or min(dims) <= 0:
            raise ValueError("Positive finite scale and metric dimensions required")
        if isinstance(t["arc_segments"], bool) or not isinstance(t["arc_segments"], int) or not 8 <= t["arc_segments"] <= 128:
            raise ValueError("arc_segments must be an integer in [8,128]")
        if not np.isfinite(t["gold_offset_z"]):
            raise ValueError("Invalid initial pose")
        self.unit = self.scale/1000
        self.bodies = []
        for name in ("gold", "silver"):
            rings = outlines(t, name)
            if not np.isfinite(np.concatenate(rings)).all():
                raise ValueError("Non-finite outline")
            mesh, cells = extrude_slabs(polygon_slabs(rings), float(t["thickness"]))
            # Authored planar x/y -> assembly x/z, preserving handedness.
            transform = np.eye(4)
            transform[:3, :3] = Rotation.from_euler("x", 90, degrees=True).as_matrix()
            if name == "gold":
                transform[:3, :3] = Rotation.from_euler("z", 90, degrees=True).as_matrix() @ transform[:3, :3]
                transform[2, 3] = t["gold_offset_z"]
            for part in [mesh, *cells]:
                part.apply_transform(transform)
                part.apply_scale(self.unit)
            color = tuple(t["colors"][f"keyhole_{name}"])
            mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
                baseColorFactor=color, metallicFactor=.8, roughnessFactor=.3))
            self.bodies.append(KeyholeBody(f"keyhole_{name}", mesh, cells, color, rings))


def mesh_clearance(first, second):
    """Triangle-surface distance plus containment rejection for closed solids."""
    a, b = trimesh.collision.CollisionManager(), trimesh.collision.CollisionManager()
    a.add_object("a", first)
    b.add_object("b", second)
    if a.in_collision_other(b):
        return 0.0
    if first.contains(second.vertices).any() or second.contains(first.vertices).any():
        return -1.0
    return float(a.min_distance_other(b))


def geometry_report(assembly):
    parts = []
    for body in assembly.bodies:
        mesh = body.visual
        collision_volume = sum(c.volume for c in body.collision)
        parts.append(dict(name=body.name, watertight=bool(mesh.is_watertight),
            winding_consistent=bool(mesh.is_winding_consistent), components=len(mesh.split()),
            euler_number=int(mesh.euler_number), volume_m3=float(mesh.volume),
            collision_prisms=len(body.collision), all_prisms_convex=all(c.is_convex for c in body.collision),
            collision_volume_error_m3=float(abs(collision_volume-mesh.volume))))
    gap = mesh_clearance(*(b.visual for b in assembly.bodies))
    expected_euler = [2, 0]  # Open gold fork; silver has exactly one through-hole.
    passed = gap > 1e-8 and all(p["watertight"] and p["winding_consistent"] and p["components"] == 1
        and p["euler_number"] == e and p["volume_m3"] > 0 and p["all_prisms_convex"]
        and p["collision_volume_error_m3"] < p["volume_m3"]*1e-8 for p, e in zip(parts, expected_euler))
    bounds = np.array([np.min([b.visual.bounds[0] for b in assembly.bodies], axis=0),
                       np.max([b.visual.bounds[1] for b in assembly.bodies], axis=0)])
    return dict(template_id=assembly.template["template_id"], scale=assembly.scale, body_count=2,
        geometry_status=assembly.template["geometry_status"], pieces=parts, bounds_m=bounds.tolist(),
        minimum_initial_surface_clearance_m=gap, no_initial_collision=gap > 1e-8,
        passed=bool(passed), human_reference_solution_documented=True, measured_replica=False,
        initial_pose_is_authored=True, extraction_route_verified=False, turning_windows_verified=False,
        qualification="authored initial geometry only; commercial solution does not certify this reconstruction")


def write_body(folder, body, density):
    folder.mkdir(parents=True, exist_ok=True)
    visual = body.visual.copy()
    visual.density = density
    props = visual.mass_properties
    center = props.center_mass
    visual.apply_translation(-center)
    visual.unmerge_vertices()
    visual.export(folder / "visual.glb", include_normals=True)
    root = ET.Element("robot", name=body.name)
    link = ET.SubElement(root, "link", name=body.name)
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz="0 0 0", rpy="0 0 0")
    ET.SubElement(inertial, "mass", value=str(props.mass))
    ET.SubElement(inertial, "inertia", **{f"i{a}{b}": str(props.inertia[i,j]) for a,b,i,j in
        (("x","x",0,0),("y","y",1,1),("z","z",2,2),("x","y",0,1),("x","z",0,2),("y","z",1,2))})
    for i, source in enumerate(body.collision):
        filename = f"collision_{i:03d}.obj"
        source.copy().apply_translation(-center).export(folder / filename)
        node = ET.SubElement(link, "collision", name=f"prism_{i:03d}")
        ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=filename)
    node = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename="visual.glb")
    ET.SubElement(ET.SubElement(node, "material", name=body.name), "color", rgba=vector_text(body.color))
    ET.indent(root)
    ET.ElementTree(root).write(folder / f"{body.name}.urdf", encoding="unicode", xml_declaration=True)
    return dict(name=body.name, origin_m=center.tolist(), mass_kg=float(props.mass),
        inertia_kg_m2=props.inertia.tolist(), collision_prisms=len(body.collision), physical_links=1,
        fixed=False, mass_model="volume integral of the authored plate at uniform declared density")


def generate_assets(output, *, template=None, scale=3.0):
    output = Path(output)
    assembly = KeyholeAssembly(template, scale)
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError(f"Invalid Keyhole initial geometry: {report}")
    output.mkdir(parents=True, exist_ok=True)
    report["bodies"] = [write_body(output/b.name, b, assembly.template["density_kg_m3"]) for b in assembly.bodies]
    scene = trimesh.Scene()
    for body in assembly.bodies:
        scene.add_geometry(body.visual, node_name=body.name, geom_name=body.name)
    scene.export(output / "assembly.glb")
    (output / "template.json").write_text(json.dumps(assembly.template, indent=2)+"\n")
    (output / "sources.json").write_text((resource_path("cast_keyhole/sources.json")).read_text())
    (output / "geometry_report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return assembly, report


def plate_assembly_transforms(record):
    """Plate-local to authored assembly transforms, shared by assets and grasps."""
    rx = Rotation.from_euler("x", 90, degrees=True).as_matrix()
    rz = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    result = {name: np.eye(4) for name in ("gold", "silver")}
    result["gold"][:3, :3] = rz @ rx
    result["gold"][2, 3] = record.get("gold_offset_z_mm", load_template()["gold_offset_z"])*(record["scale"]/1000.)
    result["silver"][:3, :3] = rx
    if "silver_pose" in record:
        pose = record["silver_pose"]
        angles, position = np.asarray(pose["rotation_xyz_deg"]), np.asarray(pose["position_mm"])
        if angles.shape != (3,) or position.shape != (3,) or not np.isfinite(np.r_[angles, position]).all():
            raise ValueError("Invalid silver plate assembly pose")
        result["silver"][:3, :3] = Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
        result["silver"][:3, 3] = position*record["scale"]/1000.
    return result


def generate_variant_assets(output, geometry_resource):
    """Rebuild frozen F1/F2/F3 slabs; old motion certificates are not transferred.

    Geometry conversion follows the archived seed_generator_v2 variant_assets
    and inverse_variants implementations. Inputs are now catalog resources.
    """
    from copy import deepcopy
    from topogym.assets.variation_resources import read_json
    record = read_json(geometry_resource)
    assembly = KeyholeAssembly(scale=record["scale"])
    assembly.template = deepcopy(assembly.template)
    assembly.template.update(template_id=record["id"],
                             geometry_status="frozen_inverse_geometry_simulator_rebuild")
    if "gold_offset_z_mm" in record:
        offset = float(record["gold_offset_z_mm"])
        if not np.isfinite(offset):
            raise ValueError("Invalid gold_offset_z_mm")
        assembly.template["gold_offset_z"] = offset
    if "geometry_status" in record:
        assembly.template["geometry_status"] = record["geometry_status"]
    assembly.bodies = []
    transforms = plate_assembly_transforms(record)
    for name in ("gold", "silver"):
        layers = record.get("layers", {}).get(name, [dict(
            z_min_mm=-record["thickness_mm"]/2, z_max_mm=record["thickness_mm"]/2,
            rings_mm=record["rings_mm"][name])])
        layer_meshes, cells = [], []
        for layer in layers:
            lo, hi = layer["z_min_mm"], layer["z_max_mm"]
            mesh, parts = extrude_slabs(polygon_slabs(
                [np.asarray(r) for r in layer["rings_mm"]]), hi-lo)
            for part in [mesh, *parts]:
                part.apply_translation([0, 0, (hi+lo)/2])
                part.apply_scale(assembly.unit)
            layer_meshes.append(mesh)
            cells.extend(parts)
        mesh = (layer_meshes[0] if len(layer_meshes) == 1 else
                trimesh.boolean.union(layer_meshes, engine="manifold"))
        transform = transforms[name]
        for part in [mesh, *cells]:
            part.apply_transform(transform)
        material = record.get("visual_material", {})
        color = tuple(material.get(name, assembly.template["colors"][f"keyhole_{name}"]))
        mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
            baseColorFactor=color, metallicFactor=material.get("metallic", .8),
            roughnessFactor=material.get("roughness", .3)))
        assembly.bodies.append(KeyholeBody(f"keyhole_{name}", mesh, cells, color,
                                          record["rings_mm"][name]))
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError(f"Invalid frozen Keyhole geometry: {report}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report["bodies"] = [write_body(output/b.name, b, record["density_kg_m3"])
                        for b in assembly.bodies]
    report.update(source_resource=geometry_resource, historical_certificate_transferred=False)
    for name, data in (("template.json", assembly.template), ("inverse_geometry.json", record),
                       ("geometry_report.json", report)):
        (output/name).write_text(json.dumps(data, indent=2)+"\n")
    trimesh.Scene([b.visual for b in assembly.bodies]).export(output/"assembly.glb")
    return assembly, report
