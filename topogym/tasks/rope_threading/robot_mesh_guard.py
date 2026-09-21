"""Control-frame audit of measured robot geometry, including self intersections.

The native rope CCD covers FEM/rigid pairs. This supplements the rigid solver
with measured-joint FK and original collision triangles for robot mesh pairs.
It is sampled at control frames, not a certificate of continuous robot CCD.
"""
import mujoco
import numpy as np


class MeasuredRobotMeshGuard:
    def __init__(self, model):
        self.model, self.data = model, mujoco.MjData(model)
        self.cache = {}
        self.frames = self.convex_candidates = self.triangle_checks = self.convex_false_positives = 0
        self.failures = []

    def _triangle_intersection(self, ids):
        import ipctk
        ipctk.set_num_threads(2)
        model, data = self.model, self.data
        vertices, faces, count, first = [], [], 0, 0
        for g in ids:
            mesh = int(model.geom_dataid[g])
            v = model.mesh_vert[model.mesh_vertadr[mesh]:model.mesh_vertadr[mesh]+model.mesh_vertnum[mesh]].astype(float)
            f = model.mesh_face[model.mesh_faceadr[mesh]:model.mesh_faceadr[mesh]+model.mesh_facenum[mesh]]
            vertices.append(v@data.geom_xmat[g].reshape(3, 3).T+data.geom_xpos[g])
            faces.append(f+count)
            count += len(v)
            if not first:
                first = count
        vertices = np.asfortranarray(np.vstack(vertices))
        if ids not in self.cache:
            f = np.vstack(faces).astype(np.int32)
            edges = np.unique(np.sort(np.vstack([f[:, :2], f[:, 1:], f[:, [0, 2]]]), axis=1), axis=0)
            mesh = ipctk.CollisionMesh(vertices, np.asfortranarray(edges), np.asfortranarray(f))
            mesh.can_collide = ipctk.make_vertex_patches_filter(np.r_[np.zeros(first, dtype=np.int32),
                                                                    np.ones(count-first, dtype=np.int32)])
            self.cache[ids] = mesh
        self.triangle_checks += 1
        return bool(ipctk.has_intersections(self.cache[ids], vertices, None))

    def check(self, qpos, t):
        self.frames += 1
        self.data.qpos[:] = qpos
        mujoco.mj_forward(self.model, self.data)
        checked = set()
        for contact in self.data.contact:
            if contact.dist >= -1e-7:
                continue
            ids = tuple(sorted((int(contact.geom1), int(contact.geom2))))
            if ids in checked:
                continue
            checked.add(ids)
            self.convex_candidates += 1
            meshes = all(self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH for g in ids)
            if meshes:
                failure = self._triangle_intersection(ids)
                if not failure:
                    self.convex_false_positives += 1
            else:
                # Same penetration tolerance as the existing rigid-contact gate;
                # do not promote a capsule fixture proxy to an exact mesh claim.
                failure = contact.dist < -.0005
            if failure:
                item = dict(time_s=float(t), convex_distance_m=float(contact.dist),
                    pair=[self.model.geom(g).name or self.model.body(self.model.geom_bodyid[g]).name for g in ids],
                    kind="robot_triangle_intersection" if meshes else "robot_fixture_proxy_penetration")
                self.failures.append(item)
                raise RuntimeError(f"Measured robot mesh audit rejected a contact: {item}")

    def report(self):
        return dict(passed=not self.failures, control_frames=self.frames, convex_candidates=self.convex_candidates,
            exact_triangle_pair_checks=self.triangle_checks, convex_false_positives=self.convex_false_positives,
            failures=self.failures, scope="measured-joint control-frame geometry; not continuous robot CCD")
