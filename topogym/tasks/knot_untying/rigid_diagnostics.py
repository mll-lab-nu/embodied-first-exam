"""Audit FEM contacts against the actual native IPC affine-body surfaces.

Rigid/rigid pairs are intentionally outside this monitor: their contact model
is Genesis' rigid solver. Every FEM/FEM and FEM/rigid candidate remains enabled.
"""
import numpy as np

from .diagnostics import SurfaceCCD


def swept_aabbs_overlap(a0, a1, b0, b1):
    """Conservative for exactly the linear vertex sweeps used by IPC CCD."""
    amin, amax = np.minimum(a0.min(0), a1.min(0)), np.maximum(a0.max(0), a1.max(0))
    bmin, bmax = np.minimum(b0.min(0), b1.min(0)), np.maximum(b0.max(0), b1.max(0))
    return bool(np.all(np.minimum(amax, bmax)+1e-12 >= np.maximum(amin, bmin)))


class NativeRigidSurfaceCCD:
    def __init__(self, task, fem_vertices, fem_faces):
        import uipc
        self.coupler = task.scene.sim.coupler
        self.parts = []
        self.fem_faces = fem_faces
        self.previous_fem = fem_vertices.copy()
        self.checker = SurfaceCCD(fem_vertices, fem_faces)
        self.initial_intersections = self.checker.initial_intersections
        self.checks = self.failures = self.rigid_queries = self.separated_pairs = 0
        # This is the same insertion order used by Genesis' ABD accessor.
        for body_index, (link, slots) in enumerate(self.coupler._abd_slots_by_link.items()):
            if len(slots) != 1:
                raise ValueError('Rigid contact audit currently supports one environment')
            geometry = slots[0].geometry()
            points = np.asarray(geometry.positions().view()).reshape(-1, 3).copy()
            triangles = np.asarray(geometry.triangles().topo().view()).reshape(-1, 3).copy()
            transform = np.asarray(geometry.transforms().view()).reshape(-1, 4, 4)[0].copy()
            self.parts.append(dict(name=link.name, body_index=body_index, local=points,
                                   faces=triangles, transform=transform,
                                   previous=points@transform[:3, :3].T+transform[:3, 3], checker=None))
            part = self.parts[-1]
            if swept_aabbs_overlap(fem_vertices, fem_vertices, part['previous'], part['previous']):
                self._create_checker(part, fem_vertices)
                self.initial_intersections |= part['checker'].initial_intersections
        self.transforms_attribute = self.coupler._abd_state_geom.instances().find(uipc.builtin.transform)
        self.method = ('ipctk 1.6.0; FEM self CCD and native rigid/FEM CCD at every substep; '
                       'conservative swept-body AABB rejection; rigid/rigid excluded')

    def __getattr__(self, name):
        return getattr(self.checker, name)

    def _create_checker(self, part, fem_vertices):
        vertices = np.vstack((fem_vertices, part['previous']))
        faces = np.vstack((self.fem_faces, part['faces']+len(fem_vertices)))
        part['checker'] = SurfaceCCD(vertices, faces, primary_vertices=np.arange(len(vertices)) < len(fem_vertices),
                                     cross_only=True)

    def step(self, fem_vertices):
        transforms = np.asarray(self.transforms_attribute.view()).reshape(-1, 4, 4)
        valid = self.checker.step(fem_vertices)
        self.checks += 1
        for part in self.parts:
            transform = transforms[part['body_index']]
            if not np.isfinite(transform).all() or np.linalg.det(transform[:3, :3]) <= 0.:
                raise RuntimeError(f"Invalid native rigid transform: {part['name']}")
            part['transform'] = transform.copy()
            current = part['local']@transform[:3, :3].T+transform[:3, 3]
            if swept_aabbs_overlap(self.previous_fem, fem_vertices, part['previous'], current):
                if part['checker'] is None:
                    self._create_checker(part, self.previous_fem)
                    valid &= not part['checker'].initial_intersections
                valid &= part['checker'].step_between(np.vstack((self.previous_fem, part['previous'])),
                                                      np.vstack((fem_vertices, current)))
                self.rigid_queries += 1
            else:
                self.separated_pairs += 1
            part['previous'] = current
        self.previous_fem = fem_vertices.copy()
        self.failures += int(not valid)
        return valid

    def close(self):
        self.checker.close()
        for part in self.parts:
            if part['checker'] is not None:
                part['checker'].close()

    def surface(self, link_name):
        import trimesh
        part = next(p for p in self.parts if p['name'] == link_name)
        transform = part['transform']
        return trimesh.Trimesh(part['local']@transform[:3, :3].T+transform[:3, 3], part['faces'], process=False)
