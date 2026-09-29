"""Per-scene rigid substep evidence; no IPC or continuous-time coverage claim."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from scipy.spatial import cKDTree
from topogym.utils.arrays import to_numpy


def resolve_roles(entity, spec):
    """Match pre-build shape, link and authored transform, never array order.

    Mesh decomposition may create several geoms from one collision; they all
    receive the same role. Conflicting or absent matches remain explicitly unknown.
    """
    if spec.morph_type == "mjcf":
        return _resolve_mjcf_roles(entity, spec)
    root = ET.parse(spec.asset_path).getroot()
    roles, complete, covered = {}, True, set()
    for link in entity.links:
        source = root.find(f"./link[@name='{link.name}']")
        candidates = []
        for node in (() if source is None else source.findall("collision")):
            origin = node.find("origin")
            p = np.fromstring(origin.get("xyz", "0 0 0") if origin is not None else "0 0 0", sep=" ")
            r = Rotation.from_euler("xyz", np.fromstring(origin.get("rpy", "0 0 0") if origin is not None else "0 0 0", sep=" ")).as_matrix()
            shape = list(node.find("geometry"))[0]
            candidates.append((p, r, shape, spec.contact_roles.get(node.get("name")), node.get("name")))
        # Dense wires contain thousands of primitives on a single link. Avoid
        # quadratic allclose calls while retaining exactly the same final
        # type/pose/dimension checks and ambiguous-role rejection.
        primitive_candidates, mesh_candidates = {}, {}
        for candidate in candidates:
            shape = candidate[2]
            if shape.tag == "mesh":
                path = (Path(spec.asset_path).parent / shape.get("filename")).resolve()
                mesh_candidates.setdefault(path, []).append(candidate)
            else:
                primitive_candidates.setdefault(shape.tag.upper(), []).append(candidate)
        trees = {kind:cKDTree(np.array([item[0] for item in values]))
                 for kind, values in primitive_candidates.items()}
        for geom in link.geoms:
            q = np.asarray(geom.init_quat)
            rotation = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
            matched = set()
            kind = geom.type.name
            if kind == "MESH":
                imported = geom.mesh.metadata.get("mesh_path")
                nearby = mesh_candidates.get(Path(imported).resolve(), ()) if imported is not None else ()
            elif kind in trees:
                nearby = [primitive_candidates[kind][i]
                          for i in trees[kind].query_ball_point(geom.init_pos, 2e-7)]
            else:
                nearby = ()
            for p, r, shape, role, name in nearby:
                if shape.tag.upper() != geom.type.name:
                    continue
                if shape.tag == "mesh":
                    # Genesis recenters/rotates convex meshes into principal
                    # frames before build. The original asset path survives;
                    # init_pos/init_quat no longer equal the URDF origin. Match
                    # all uses of that asset on this link and fail closed when
                    # their roles conflict (never use import order or names).
                    authored = Path(spec.asset_path).parent / shape.get("filename")
                    imported = geom.mesh.metadata.get("mesh_path")
                    same = imported is not None and Path(imported).resolve() == authored.resolve()
                else:
                    if (not np.allclose(p, geom.init_pos, atol=1e-7, rtol=0)
                            or not np.allclose(r, rotation, atol=1e-7, rtol=0)):
                        continue
                    data = (np.fromstring(shape.get("size"), sep=" ") if shape.tag == "box" else
                            [float(shape.get("radius"))] if shape.tag == "sphere" else
                            [float(shape.get("radius")), float(shape.get("length"))])
                    # Genesis RigidGeom stores primitive parameters in a
                    # seven-element zero-padded buffer (URDF has 1/2/3 values).
                    actual = np.asarray(geom.data)
                    count = len(data)
                    same = (actual.ndim == 1 and actual.size >= count
                            and np.allclose(data, actual[:count], atol=1e-7, rtol=0)
                            and np.allclose(actual[count:], 0, atol=1e-7, rtol=0))
                if same:
                    matched.add(role)
                    covered.add(name)
            role = next(iter(matched)) if len(matched) == 1 else None
            roles[int(geom.idx)] = role or "unknown"
            complete &= role is not None
    return roles, bool(complete and roles and set(spec.contact_roles) <= covered)


def _resolve_mjcf_roles(entity, spec):
    """Match authored primitive geometry before Genesis recenters link frames.

    Genesis caches identical primitive meshes, including their metadata: the
    native geom name may therefore belong to another link. Neither that name
    nor import order is an identity. Unsupported MJCF forms remain uncovered.
    """
    root = ET.parse(spec.asset_path).getroot()
    if root.tag != "mujoco":
        raise ValueError("Expected MJCF for contact roles")
    default = root.find("default/geom")
    defaults = {} if default is None else default.attrib
    compiler = root.find("compiler")
    scale = np.asarray(spec.morph_options.get("scale", 1.), float)
    if scale.shape != () or not np.isfinite(scale) or scale <= 0:
        return {int(g.idx):"unknown" for link in entity.links for g in link.geoms}, False
    # Current task assets use one default geom class and explicit local frames.
    unsupported = (bool(root.findall("default/default")) or root.find("include") is not None
                   or (compiler is not None and compiler.get("coordinate", "local") != "local"))
    roles, covered, complete = {}, set(), not unsupported
    for link in entity.links:
        body = root.find(f".//worldbody//body[@name='{link.name}']")
        candidates = []
        if body is not None and not unsupported and "childclass" not in body.attrib:
            for geom in body.findall("geom"):
                attrs = {**defaults, **geom.attrib}
                if not (int(attrs.get("contype", "1")) or int(attrs.get("conaffinity", "1"))):
                    continue
                primitive = _mjcf_primitive(attrs, float(scale))
                if primitive is not None:
                    candidates.append((attrs.get("name"), primitive))
        for geom in link.geoms:
            rotation = Rotation.from_quat(np.asarray(geom.init_quat)[[1,2,3,0]]).as_matrix()
            matched = set()
            for name, (kind, position, authored_rotation, data) in candidates:
                if kind != geom.type.name or not np.allclose(position,geom.init_pos,atol=1e-7,rtol=0):
                    continue
                if kind in {"CAPSULE","CYLINDER"}:
                    aligned = abs(np.dot(rotation[:,2],authored_rotation[:,2])) >= 1-1e-10
                else:
                    aligned = kind == "SPHERE" or np.allclose(rotation,authored_rotation,atol=1e-7,rtol=0)
                actual = np.asarray(geom.data)
                count = len(data)
                if (aligned and actual.ndim == 1 and actual.size >= count
                        and np.allclose(actual[:count],data,atol=1e-7,rtol=0)
                        and np.allclose(actual[count:],0,atol=1e-7,rtol=0)):
                    matched.add(spec.contact_roles.get(name))
                    covered.add(name)
            role = next(iter(matched)) if len(matched) == 1 else None
            roles[int(geom.idx)] = role or "unknown"
            complete &= role is not None
    return roles, bool(complete and roles and set(spec.contact_roles) <= covered)


def _mjcf_primitive(attrs, scale):
    kind = attrs.get("type", "sphere").upper()
    if kind not in {"BOX","SPHERE","CAPSULE","CYLINDER"} or any(
            name in attrs for name in ("class","axisangle","xyaxes","zaxis","euler")):
        return None
    size = np.fromstring(attrs.get("size", ""), sep=" ")
    position = np.fromstring(attrs.get("pos", "0 0 0"), sep=" ")
    rotation = np.eye(3)
    if "fromto" in attrs:
        ends = np.fromstring(attrs["fromto"], sep=" ")
        if ends.shape != (6,) or kind not in {"CAPSULE","CYLINDER"}:
            return None
        a,b = ends.reshape(2,3)
        height = np.linalg.norm(b-a)
        if height <= 0:
            return None
        position = (a+b)/2
        # These primitives are axially symmetric; only the local z axis matters.
        rotation[:,2] = (b-a)/height
    else:
        if "quat" in attrs:
            quat = np.fromstring(attrs["quat"], sep=" ")
            if quat.shape != (4,) or np.linalg.norm(quat) == 0:
                return None
            rotation = Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()
        height = 2*size[1] if size.size >= 2 else None
    needed = 3 if kind == "BOX" else 1
    if size.size < needed or position.shape != (3,):
        return None
    if kind == "BOX":
        data = 2*size[:3]
    elif kind == "SPHERE":
        data = size[:1]
    elif height is not None:
        data = np.array([size[0],height])
    else:
        return None
    if not np.isfinite(np.r_[position,rotation.ravel(),data]).all() or np.any(data <= 0):
        return None
    return kind,position*scale,rotation,data*scale


def resolve_robot_parts(robot, description):
    """Classify full declared gripper subtrees without changing robot roles."""
    if robot is None or description is None or not description.groups:
        return {}, False
    links = {link.name: link for link in robot.links}
    gripper_ids = set()
    complete = True
    for group in description.groups:
        grasp = group.grasp
        root = links.get(grasp.contact_root_link) if grasp is not None else None
        if root is None:
            complete = False
            continue
        subtree = {int(root.idx)}
        while True:
            children = {int(link.idx) for link in robot.links if int(link.parent_idx) in subtree}
            if children <= subtree:
                break
            subtree.update(children)
        complete &= all(name in links and int(links[name].idx) in subtree
                        and bool(links[name].geoms) for name in grasp.finger_links)
        gripper_ids.update(subtree)
    parts = {int(geom.idx): "gripper" if int(link.idx) in gripper_ids else "arm"
             for link in robot.links for geom in link.geoms}
    return parts, bool(complete and parts and gripper_ids)


class RigidContactCollector:
    """Observe the existing rigid solver method on this instance only.

    Genesis calls rigid.substep both on the rigid fast path and the legacy
    mixed-solver path. IPC owns different contacts and is deliberately rejected.
    """
    def __init__(self, scene, roles, *, geometry_complete, robot_parts=None,
                 robot_geometry_complete=False):
        self.scene, self.solver = scene, scene.sim.rigid_solver
        self.roles, self.geometry_complete = dict(roles), bool(geometry_complete)
        self.robot_parts = dict(robot_parts or {})
        self.robot_geometry_complete = bool(robot_geometry_complete)
        if not self.solver.is_active or hasattr(scene.sim.coupler, "checkpoint_store"):
            raise ValueError("Rigid contact collector does not cover IPC")
        self.expected = int(scene.sim.substeps)
        self.original = self.solver.substep
        self.active = False
        self.summary = self._empty(0)
        self.wrapper = self._substep
        self.solver.substep = self.wrapper

    def _empty(self, tick):
        return dict(schema_version=1, physics_step=int(tick), source="genesis_rigid_narrowphase",
            substeps_complete=False, geometry_roles_complete=self.geometry_complete,
            robot_geometry_complete=self.robot_geometry_complete,
            expected_substeps=self.expected, sampled_substeps=0, events=[],
            ipc_contact_coverage=False, continuous_time_coverage=False)

    def begin(self, tick):
        self.summary = self._empty(tick)
        self.active = True

    def _substep(self, f):
        result = self.original(f)
        if self.active:
            self._sample(self.summary["sampled_substeps"])
            self.summary["sampled_substeps"] += 1
        return result

    def _sample(self, substep):
        self.solver.collider._contact_data_cache.clear()
        values = {k: to_numpy(v) for k, v in self.solver.collider.get_contacts().items()}
        for i, (a, b, penetration) in enumerate(zip(values["geom_a"], values["geom_b"], values["penetration"], strict=True)):
            # Narrowphase can include separated speculative candidates.
            if float(penetration) < 0:
                continue
            a, b = int(a), int(b)
            self.summary["events"].append(dict(geom_a=a, geom_b=b,
                role_a=self.roles.get(a, "other"), role_b=self.roles.get(b, "other"),
                robot_part_a=self.robot_parts.get(a), robot_part_b=self.robot_parts.get(b),
                touching=True, substep=int(substep), penetration_m=float(penetration),
                force_n=float(np.linalg.norm(values["force"][i]))))

    def end(self):
        self.active = False
        self.summary["substeps_complete"] = self.summary["sampled_substeps"] == self.expected

    def birth(self):
        # Refresh collision geometry at the initialized pose without integration.
        self.summary = self._empty(0)
        self.solver.detect_collision()
        self._sample(-1)
        self.summary.update(substeps_complete=True, expected_substeps=0, sampled_substeps=0,
                            sampling_scope="initial_pose")

    def read(self):
        return deepcopy(self.summary)

    def restore(self, value):
        self.active = False
        self.summary = deepcopy(value)
        self.solver.collider._contact_data_cache.clear()

    def close(self):
        if self.solver.substep == self.wrapper:
            self.solver.substep = self.original
