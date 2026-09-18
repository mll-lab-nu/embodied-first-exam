"""Import exact reference triangles, metric coordinates, and initial ALOHA FK.

No remeshing, hole filling, decimation, or whole-object convex hull is used.
Welding coincident OBJ seam vertices changes indexing only, not triangle positions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

ASSET_ROOT = Path(__file__).resolve().parents[3] / "assets/tasks/interlocked_claws/cspace_claw_wang_v1"


def load_reference():
    return json.loads((ASSET_ROOT / "reference_scene.json").read_text())


def reference_body_poses(reference, qpos=None):
    """Same parent/local/joint order as the upstream Three.js viewer (Z up)."""
    q = np.asarray(reference["initial_qpos"] if qpos is None else qpos, dtype=float)
    if q.shape != (16,) or not np.isfinite(q).all():
        raise ValueError("Expected 16 finite ALOHA joint positions")
    poses = {0: np.eye(4)}
    for body in reference["bodies"][1:]:
        local = np.eye(4)
        local[:3, :3] = Rotation.from_quat(np.asarray(body["quaternion_wxyz"])[[1, 2, 3, 0]]).as_matrix()
        local[:3, 3] = body["position"]
        for joint in body["joints"]:
            motion = np.eye(4)
            value = q[joint["qpos"]] - joint["reference"]
            axis = np.asarray(joint["axis"])
            if joint["type"] == 2:
                motion[:3, 3] = axis * value
            elif joint["type"] == 3:
                motion[:3, :3] = Rotation.from_rotvec(axis * value).as_matrix()
                pivot = np.asarray(joint["position"])
                motion[:3, 3] = pivot - motion[:3, :3] @ pivot
            else:
                raise ValueError("Unsupported reference joint")
            local = local @ motion
        poses[body["id"]] = poses[body["parent"]] @ local
    return poses


@dataclass
class ClawBody:
    name: str
    mesh: trimesh.Trimesh
    pose: np.ndarray
    color: tuple
    source: dict


class ClawAssembly:
    def __init__(self):
        self.reference = reference = load_reference()
        frames = reference_body_poses(reference)
        self.bodies = []
        for source, color in zip(reference["pieces"], reference["colors_srgb"]):
            path = ASSET_ROOT / f"piece-{source['id']}.obj"
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError(f"Original mesh checksum mismatch: {path.name}")
            mesh = trimesh.load(path, force="mesh", process=False)
            triangles = np.asarray(mesh.triangles).copy()
            mesh.merge_vertices(merge_tex=True, merge_norm=True)
            if len(mesh.faces) != source["triangles"] or not np.array_equal(mesh.triangles, triangles):
                raise ValueError("OBJ import changed reference triangle positions")
            mesh.vertices = (mesh.vertices - source["source_origin"]) * source["scale"]
            mesh.density = reference["density_kg_m3"]
            mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
                baseColorFactor=color, metallicFactor=.22, roughnessFactor=.45))
            inverse_grasp = np.asarray(source["inverse_grasp_column_major"]).reshape(4, 4, order="F")
            pose = frames[source["gripper_body"]] @ inverse_grasp
            self.bodies.append(ClawBody(f"claw_{source['id']}", mesh, pose, tuple(color), source))

    def world_meshes(self):
        return [b.mesh.copy().apply_transform(b.pose) for b in self.bodies]


def geometry_report(assembly):
    meshes = assembly.world_meshes()
    manager = trimesh.collision.CollisionManager()
    manager.add_object("claw_0", meshes[0])
    collision = bool(manager.in_collision_single(meshes[1]))
    # Reject full containment too; disjoint triangle surfaces alone are insufficient.
    containment = bool(meshes[0].contains(meshes[1].vertices[:1]).any()
                       or meshes[1].contains(meshes[0].vertices[:1]).any()) if not collision else False
    gap = float(manager.min_distance_single(meshes[1]))
    pieces = []
    for b in assembly.bodies:
        pieces.append(dict(name=b.name, source_sha256=b.source["sha256"],
            triangles=len(b.mesh.faces), vertices=len(b.mesh.vertices),
            watertight=bool(b.mesh.is_watertight), winding_consistent=bool(b.mesh.is_winding_consistent),
            components=len(b.mesh.split(only_watertight=False)), euler_number=int(b.mesh.euler_number),
            local_extents_m=b.mesh.extents.tolist(), volume_m3=float(b.mesh.volume),
            mass_kg=float(b.mesh.mass), initial_pose=b.pose.tolist()))
    pose_error = float(np.max(np.abs(np.array([b.pose for b in assembly.bodies])
                                    - assembly.reference["initial_piece_poses"])))
    passed = (not collision and not containment and gap > 0 and pose_error < 1e-10
              and all(p["watertight"] and p["winding_consistent"] and p["components"] == 1
                      and p["volume_m3"] > 0 for p in pieces))
    return dict(asset_id=assembly.reference["asset_id"], passed=bool(passed), pieces=pieces,
        triangle_positions_preserved=True, source_scale_m_per_unit=.1,
        initial_surface_clearance_m=gap, initial_surface_collision=collision,
        initial_containment=containment, source_pose_max_error=pose_error,
        assembly_bounds_m=np.array([np.min([m.bounds[0] for m in meshes], axis=0),
                                   np.max([m.bounds[1] for m in meshes], axis=0)]).tolist(),
        collision_representation="original nonconvex triangles; Genesis contact queries use a sampled SDF",
        dynamics_qualified=False, full_path_verified=False)


def generate_assets(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    assembly = ClawAssembly()
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError("Reference geometry/initial pose audit failed")
    assembled, separated = trimesh.Scene(), trimesh.Scene()
    for i, body in enumerate(assembly.bodies):
        folder = output / body.name
        folder.mkdir(exist_ok=True)
        # OBJ float64 export retains sub-micrometre fidelity. Both visual and
        # collision refer to this same file; no approximate proxy replaces it.
        body.mesh.export(folder / "mesh.obj", digits=12, include_texture=False)
        root = ET.Element("robot", name=body.name)
        link = ET.SubElement(root, "link", name=body.name)
        inertial = ET.SubElement(link, "inertial")
        props = body.mesh.mass_properties
        ET.SubElement(inertial, "origin", xyz=" ".join(map(str, props.center_mass)), rpy="0 0 0")
        ET.SubElement(inertial, "mass", value=str(props.mass))
        ET.SubElement(inertial, "inertia", **{f"i{a}{b}": str(props.inertia[j, k]) for a, b, j, k in
            (("x", "x", 0, 0), ("y", "y", 1, 1), ("z", "z", 2, 2),
             ("x", "y", 0, 1), ("x", "z", 0, 2), ("y", "z", 1, 2))})
        for kind in ("visual", "collision"):
            node = ET.SubElement(link, kind)
            ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename="mesh.obj")
            if kind == "visual":
                material = ET.SubElement(node, "material", name=body.name)
                ET.SubElement(material, "color", rgba=" ".join(map(str, body.color)))
        ET.indent(root)
        ET.ElementTree(root).write(folder / f"{body.name}.urdf", encoding="unicode")
        assembled.add_geometry(body.mesh, node_name=body.name, transform=body.pose)
        transform = body.pose.copy()
        center = body.mesh.copy().apply_transform(transform).bounds.mean(axis=0)
        transform[:3, 3] += np.array([(i-.5)*.38, 0, 0]) - center
        separated.add_geometry(body.mesh, node_name=body.name, transform=transform)
    assembled.export(output / "assembly.glb")
    separated.export(output / "separated_inspection.glb")
    (output / "geometry_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "reference_scene.json").write_text(json.dumps(assembly.reference, indent=2) + "\n")
    return assembly, report
