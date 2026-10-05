"""Read conservative collision covers for final release confirmation.

Cache only immutable local geometry; every read uses current native world poses.
No contact-force inference, history, robot commands or physics integration.
"""
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.utils.arrays import to_numpy
from topogym.evaluation.terminal.clearance import convex_cover_planes, validate_elements


class ReleaseGeometry:
    def __init__(self, world, rigid_targets, *, exact_robot_contact=False):
        self.world = world
        self.robot_present = "robot" in world.entities
        self.targets = tuple(rigid_targets)
        self.entries = []
        self.complete = True
        self.fem_elements = {}
        self.exact_robot_contact = exact_robot_contact
        self.robot_solids = []
        for name, entity in world.entities.items():
            if hasattr(entity, "material_coordinates"):
                elements = validate_elements(entity.elems, entity.n_vertices).copy()
                elements.setflags(write=False)
                self.fem_elements[name] = elements
        names = (("robot",) if self.robot_present else ()) + self.targets
        for name in names:
            entity = world.entities[name]
            count = 0
            for link in entity.links:
                for geom in link.geoms:
                    kind, data = geom.type.name, np.asarray(geom.data)
                    if kind == "SPHERE":
                        half = np.repeat(data[0], 3)
                        center = np.zeros(3)
                    elif kind in {"BOX", "CYLINDER"}:
                        half = data[:3]/2 if kind == "BOX" else np.array([data[0], data[0], data[1]/2])
                        center = np.zeros(3)
                    elif kind == "MESH":
                        vertices = np.asarray(geom.init_verts)
                        center = (vertices.min(0)+vertices.max(0))/2
                        half = (vertices.max(0)-vertices.min(0))/2
                    else:
                        self.complete = False
                        continue
                    if not np.isfinite(np.r_[center, half]).all() or np.any(half < 0):
                        raise ValueError("Invalid release collision geometry")
                    planes = (convex_cover_planes(vertices) if kind == "MESH" and name == "robot"
                              else np.empty((0, 4)))
                    self.entries.append((name, int(geom.idx), center, half, planes))
                    if name == "robot" and exact_robot_contact:
                        # Genesis is_fixed follows the whole ancestor chain: a
                        # fixed joint attached to a moving wrist is still active.
                        self.robot_solids.append(dict(link=link.name, geom_index=int(geom.idx),
                            fixed_to_world=bool(link.is_fixed), native_type=kind,
                            native_convex=bool(geom.is_convex), native_data=data.copy(),
                            vertices_m=np.asarray(geom.init_verts, float).copy(),
                            faces=np.asarray(geom.init_faces, np.int64).copy()))
                        for key in ('native_data', 'vertices_m', 'faces'):
                            self.robot_solids[-1][key].setflags(write=False)
                    count += 1
            self.complete &= count > 0

    def _batches(self):
        """The entries as arrays, built once (entries are fixed at construction): local centers / half extents, row
        indices per name, and the robot entries grouped by their plane count (one stacked matmul per group)."""
        cached = getattr(self, "_batch", None)
        if cached is not None and cached["entries"] is self.entries and cached["count"] == len(self.entries):
            return cached
        names = [e[0] for e in self.entries]
        robot = [i for i, name in enumerate(names) if name == "robot"]
        groups = {}
        for i in robot:
            groups.setdefault(len(self.entries[i][4]), []).append(i)
        self._batch = dict(
            entries=self.entries, count=len(self.entries), robot=robot,
            centers=np.array([np.asarray(e[2], dtype=float) for e in self.entries]).reshape(-1, 3),
            halves=np.array([np.asarray(e[3], dtype=float) for e in self.entries]).reshape(-1, 3),
            rows={name: [i for i, n in enumerate(names) if n == name] for name in (*self.targets, "robot")},
            groups=[(np.asarray(rows), np.array([self.entries[i][4] for i in rows], dtype=float).reshape(len(rows), k, 4))
                    for k, rows in groups.items()])
        return self._batch

    def read(self):
        boxes = {name: np.empty((0, 2, 3)) for name in (*self.targets, "robot")}
        robot_planes, robot_poses = [], []
        if self.entries:
            indices = [e[1] for e in self.entries]
            solver = self.world.scene.sim.rigid_solver
            p = to_numpy(solver.get_geoms_pos(indices, relative=False)).reshape(-1, 3)
            q = to_numpy(solver.get_geoms_quat(indices, relative=False)).reshape(-1, 4)
            r = Rotation.from_quat(q[:, [1, 2, 3, 0]]).as_matrix()
            # Every entry's numbers as before (position + turn @ center, abs(turn) @ half; per robot entry planes @
            # turn.T and normals @ position), as stacked matmuls over equal shapes: numpy evaluates each stacked product
            # with the kernel of the single product, bit for bit (scripts/check_release_geometry_batched.py).
            batch = self._batches()
            centers = p + (r @ batch["centers"][:, :, None])[:, :, 0]
            halves = (np.abs(r) @ batch["halves"][:, :, None])[:, :, 0]
            bounds = np.stack([centers-halves, centers+halves], axis=1)
            boxes = {name: bounds[rows] for name, rows in batch["rows"].items()}
            planes = {}
            for rows, local in batch["groups"]:
                normals = local[:, :, :3] @ np.swapaxes(r[rows], 1, 2)
                offsets = local[:, :, 3]-(normals @ p[rows][:, :, None])[:, :, 0]
                for j, i in enumerate(rows):
                    planes[int(i)] = np.concatenate([normals[j], offsets[j][:, None]], axis=1)
            robot_planes = [planes[i] for i in batch["robot"]]
            if self.exact_robot_contact:
                robot_poses = [dict(position_m=p[i].copy(), rotation=r[i].copy()) for i in batch["robot"]]
        result = dict(schema_version=3 if self.exact_robot_contact else 2, physics_step=self.world.physics_step,
            complete=bool(self.complete), robot_present=self.robot_present,
            robot_bounds_m=np.asarray(boxes["robot"]).reshape(-1, 2, 3),
            target_bounds_m={name: np.asarray(boxes[name]).reshape(-1, 2, 3) for name in self.targets},
            robot_convex_planes_m=robot_planes, fem_elements=dict(self.fem_elements))
        if self.exact_robot_contact:
            result.update(robot_solids=self.robot_solids, robot_solid_poses=robot_poses)
        return result
