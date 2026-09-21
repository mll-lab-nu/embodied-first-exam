"""Control-frame audit of measured robot geometry, including self intersections.

The native rope CCD covers FEM/rigid pairs. This supplements the rigid solver
with measured-joint FK and original collision triangles for robot mesh pairs.
It is sampled at control frames, not a certificate of continuous robot CCD.
"""
import mujoco
import numpy as np
import multiprocessing as mp


def _triangle_worker(connection):
    """Keep ipctk out of the uipc process: their pybind enums conflict."""
    try:
        import ipctk
        ipctk.set_num_threads(2)
        cache = {}
        while True:
            request = connection.recv()
            if request is None:
                break
            ids, vertices, faces, first = request
            vertices = np.asfortranarray(vertices)
            if ids not in cache:
                edges = np.unique(np.sort(np.vstack([faces[:, :2], faces[:, 1:], faces[:, [0, 2]]]), axis=1), axis=0)
                mesh = ipctk.CollisionMesh(vertices, np.asfortranarray(edges), np.asfortranarray(faces))
                mesh.can_collide = ipctk.make_vertex_patches_filter(np.r_[np.zeros(first, dtype=np.int32),
                    np.ones(len(vertices)-first, dtype=np.int32)])
                cache[ids] = mesh
            connection.send(dict(intersects=bool(ipctk.has_intersections(cache[ids], vertices, None))))
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as exc:
        connection.send(dict(error=f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


class MeasuredRobotMeshGuard:
    def __init__(self, model):
        self.model, self.data = model, mujoco.MjData(model)
        self.cache = set()
        self.process = self.connection = None
        self.frames = self.convex_candidates = self.triangle_checks = self.convex_false_positives = 0
        self.failures = []

    def _triangle_intersection(self, ids):
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
        if self.process is None:
            context = mp.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=_triangle_worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        self.triangle_checks += 1
        faces = None if ids in self.cache else np.vstack(faces).astype(np.int32)
        try:
            self.connection.send((ids, vertices, faces, first))
            if not self.connection.poll(30):
                raise RuntimeError("Independent robot triangle worker timed out")
            result = self.connection.recv()
        except (EOFError, BrokenPipeError) as exc:
            raise RuntimeError("Independent robot triangle worker disconnected") from exc
        if "error" in result:
            raise RuntimeError("Independent robot triangle worker failed: "+result["error"])
        self.cache.add(ids)
        return result["intersects"]

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                try:
                    self.connection.send(None)
                except (EOFError, BrokenPipeError):
                    pass
                self.process.join(5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(5)
            self.connection.close()
            self.process = self.connection = None
            self.cache.clear()

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
                try:
                    failure = self._triangle_intersection(ids)
                except RuntimeError as exc:
                    self.failures.append(dict(time_s=float(t), kind="triangle_worker_error", error=str(exc)))
                    raise
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
            failures=self.failures, triangle_checker_process="isolated CPU worker (uipc/ipctk enum separation)",
            scope="measured-joint control-frame geometry; not continuous robot CCD")
