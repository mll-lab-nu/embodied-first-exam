"""Frozen rigid geometry and bounded SE(3) edge checks, without an engine.

Native spheres/cylinders are enclosed by circumscribed meshes. Collision and
visual surfaces are both included. Certificates cover these rigid surfaces,
not robot reachability or the engine's SDF approximation.
"""
from dataclasses import asdict
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

import fcl
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose
from topogym.solvers.collision.triangle_meshes import TriangleMeshPair


def matrix(p, r):
    t = np.eye(4)
    t[:3, :3], t[:3, 3] = r.as_matrix(), p
    return t


def interpolate(a, b, u):
    return (a[0]+u*(b[0]-a[0]), Rotation.from_rotvec(u*(b[1]*a[1].inv()).as_rotvec())*a[1])


def pose_dict(p):
    return dict(position_m=p[0].tolist(), quaternion_wxyz=p[1].as_quat()[[3, 0, 1, 2]].tolist())


def _origin(node):
    if node is None:
        return np.eye(4)
    return matrix(np.fromstring(node.get("xyz", "0 0 0"), sep=" "),
                  Rotation.from_euler("xyz", np.fromstring(node.get("rpy", "0 0 0"), sep=" ")))


def combine_meshes(meshes):
    result = trimesh.util.concatenate(meshes)
    components, offset = [], 0
    for mesh in meshes:
        for row in mesh.metadata.get("components", [dict(name="unnamed", first_face=0, face_count=len(mesh.faces))]):
            components.append(dict(row, first_face=row["first_face"]+offset))
        offset += len(mesh.faces)
    result.metadata["components"] = components
    return result


def entity_mesh(entity):
    """Union represented as separate closed cells; retain concave meshes."""
    if entity.morph_type == "box":
        mesh = trimesh.creation.box(entity.morph_options["size"])
        mesh.metadata["components"] = [dict(name=entity.name, first_face=0, face_count=len(mesh.faces))]
        return mesh
    if entity.morph_type != "urdf":
        raise ValueError("Rigid route search only supports boxes and fixed-link URDFs")
    path = Path(entity.asset_path)
    root = ET.parse(path).getroot()
    joints = root.findall("joint")
    if any(j.get("type") != "fixed" for j in joints):
        raise ValueError("Articulated geometry needs per-link queries")
    children = {j.find("child").get("link") for j in joints}
    frames = {n.get("name"): np.eye(4) for n in root.findall("link") if n.get("name") not in children}
    pending = list(joints)
    while pending:
        ready = [j for j in pending if j.find("parent").get("link") in frames]
        if not ready:
            raise ValueError("Invalid fixed-link URDF tree")
        for j in ready:
            frames[j.find("child").get("link")] = frames[j.find("parent").get("link")]@_origin(j.find("origin"))
            pending.remove(j)
    meshes = []
    for link in root.findall("link"):
        for category in ("visual", "collision"):
            for index, part in enumerate(link.findall(category)):
                shape = list(part.find("geometry"))[0]
                if shape.tag == "mesh":
                    source = Path(shape.get("filename"))
                    source = source if source.is_absolute() else path.parent/source
                    mesh = trimesh.load(source, force="mesh", process=False)
                    # OBJ texture seams duplicate vertices without opening the
                    # actual solid. Weld coincident vertices before splitting.
                    mesh.merge_vertices(merge_tex=True, merge_norm=True)
                    mesh.apply_scale(np.fromstring(shape.get("scale", "1 1 1"), sep=" "))
                    if category == "collision" and entity.morph_options.get("convexify", False):
                        mesh = mesh.convex_hull
                elif shape.tag == "box":
                    mesh = trimesh.creation.box(np.fromstring(shape.get("size"), sep=" "))
                elif shape.tag == "cylinder":
                    mesh = trimesh.creation.cylinder(radius=float(shape.get("radius"))/np.cos(np.pi/64),
                                                     height=float(shape.get("length")), sections=64)
                elif shape.tag == "sphere":
                    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.)
                    inradius = np.min(np.einsum("ij,ij->i", mesh.face_normals, mesh.triangles[:, 0]))
                    mesh.apply_scale(float(shape.get("radius"))/inradius)
                else:
                    raise ValueError("Unsupported geometry: "+shape.tag)
                mesh.apply_transform(frames[link.get("name")]@_origin(part.find("origin")))
                mesh.metadata["components"] = [dict(name=f"{entity.name}/{link.get('name')}/{category}_{index}_{shape.tag}",
                    first_face=0, face_count=len(mesh.faces))]
                meshes.append(mesh)
    if not meshes:
        raise ValueError("Asset has no complete geometry")
    return combine_meshes(meshes)


class RigidPathChecker:
    def __init__(self, fixed, moving, *, margin_m=.00005, distance_error_m=.000001, max_depth=18):
        if (not np.isfinite([margin_m, distance_error_m]).all() or margin_m <= 0
                or distance_error_m < 0 or type(max_depth) is not int or max_depth < 1):
            raise ValueError("Invalid geometric checking budget")
        self.fixed, self.moving = fixed, moving
        self.pair = TriangleMeshPair((fixed, moving))
        self.radius = float(np.linalg.norm(moving.vertices, axis=1).max())
        self.margin, self.error, self.max_depth = margin_m, distance_error_m, max_depth
        self.queries = 0

    def clearance(self, p):
        self.queries += 1
        return self.pair.clearance((np.eye(4), matrix(*p)))

    def obstruction(self, p, gap):
        result = dict(pose=pose_dict(p), surface_clearance_m=None if gap < 0 else gap,
                      surface_intersection=gap < 0, witness_frame="fixed-geometry frame")
        if gap < 0:
            contacts = fcl.CollisionResult()
            fcl.collide(*self.pair.objects, fcl.CollisionRequest(num_max_contacts=1, enable_contact=True), contacts)
            if contacts.contacts:
                contact = contacts.contacts[0]
                def component(mesh, triangle):
                    return next((row["name"] for row in mesh.metadata.get("components", [])
                        if row["first_face"] <= triangle < row["first_face"]+row["face_count"]), "unlabelled triangle")
                result.update(fixed_component=component(self.fixed, contact.b1),
                              moving_component=component(self.moving, contact.b2),
                              contact_position_m=np.asarray(contact.pos).tolist())
        return result

    def initial_free(self, p):
        """Surface BVHs alone cannot detect one closed solid inside another.

        Test a representative on every connected cell in both directions.
        Along a subsequently certified positive-clearance path, containment
        cannot change without crossing a surface.
        """
        if self.clearance(p) <= self.margin+self.error:
            return False
        moving = self.moving.copy()
        moving.apply_transform(matrix(*p))
        for a, b in ((self.fixed, moving), (moving, self.fixed)):
            parts = a.split(only_watertight=False)
            points = np.array([c.vertices[0] for c in b.split(only_watertight=False)])
            for part in parts:
                if not part.is_watertight:
                    raise ValueError("Solid containment requires closed geometry")
                if part.contains(points).any():
                    return False
        return True

    def edge(self, start, end):
        """Lipschitz lower bound for linear translation and shortest SLERP.

        Unresolved leaves fail closed. A few nonintersecting samples never
        become a continuous certificate, even when both endpoints are free.
        """
        motion = float(np.linalg.norm(end[0]-start[0]) + self.radius*(end[1]*start[1].inv()).magnitude())
        stack, leaves, minimum = [(0., 1., 0)], 0, float("inf")
        before = self.queries
        while stack:
            lo, hi, depth = stack.pop()
            u = (lo+hi)/2
            gap = self.clearance(interpolate(start, end, u))
            if gap <= self.margin+self.error:
                return dict(passed=False, reason="surface_blocked", progress=u,
                            obstruction=self.obstruction(interpolate(start, end, u), gap),
                            queries=self.queries-before)
            lower = gap-self.error-motion*(hi-lo)/2
            if lower > self.margin:
                minimum = min(minimum, lower)
                leaves += 1
            elif depth >= self.max_depth:
                return dict(passed=False, reason="subdivision_budget_exhausted", progress=u,
                            clearance_m=gap, queries=self.queries-before)
            else:
                stack += [(u, hi, depth+1), (lo, u, depth+1)]
        return dict(passed=True, clearance_lower_bound_m=minimum, leaves=leaves,
                    queries=self.queries-before, distance_error_m=self.error,
                    coverage="bounded rigid surface motion; no robot/SDF qualification")


def freeze_scene(task_id, variant, seed, directory):
    """P0 declaration and assets, identical public configuration, no physics."""
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    config = SimulatorConfig(task_id=task_id, variation_id=variant, enable_rgb=False, compute_backend="cpu")
    scene = load_scene_config(config)
    task = task_definition(task_id, variant)(seed=seed)
    table = scene.env.world.table
    height = float(table.pos[2]+table.size[2]/2)
    spec = task.declare(directory, height)
    spec = task.finalize_spec(spec, asset_dir=directory, scene_config=scene)
    names = (*task.placement_targets, *task.placement_remainder)
    entities = {e.name: e for e in spec.entities if e.name in names}
    meshes = {name: entity_mesh(e) for name, e in entities.items()}
    poses = {name: pose_dict(body_pose(asdict(e))) for name, e in entities.items()}
    assets = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(directory.rglob("*")) if p.is_file()}
    metadata = dict(task_id=task_id, variation_id=task.variation_id, seed=seed,
        model_revision=task.model_revision, terminal_revision=task.terminal_revision,
        instance_id=task.instance_id, targets=task.placement_targets, remainder=task.placement_remainder,
        initial_poses=poses, goal_region=asdict(task.goal_region), asset_sha256=assets,
        geometry_scope="visible surfaces plus authored collision shapes; convexification respected",
        native_primitive_enclosure="64-sided circumscribed cylinders; circumscribed subdivision-3 spheres",
        robot_execution_verified=False, task_success=False, process_quality_passed=None)
    return task, spec, scene, meshes, metadata
