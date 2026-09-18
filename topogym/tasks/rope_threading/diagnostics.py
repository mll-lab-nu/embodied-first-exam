"""Conservative clearance certificates between full swept-surface CCD queries.

Each IPC substep is still observed. A feature-pair gap can shrink by at most
twice the greatest vertex displacement from the last measured configuration.
This bounds the ENTIRE linear substep, not just its endpoint. When that proof
does not apply, ipctk checks the explicit immediately preceding interval.
"""
import numpy as np

from topogym.tasks.knot_untying.diagnostics import SurfaceCCD
from topogym.tasks.knot_untying.rigid_diagnostics import NativeRigidSurfaceCCD


def displacement_certificate(reference, previous, current, clearance):
    if not np.isfinite(clearance) or clearance <= 1e-9:
        return False
    displacement = max(float(np.linalg.norm(previous-reference, axis=1).max()),
                       float(np.linalg.norm(current-reference, axis=1).max()))
    return 2*displacement+1e-9 < clearance


class ClearanceSurfaceCCD(SurfaceCCD):
    def __init__(self, vertices, faces, **kwargs):
        super().__init__(vertices, faces, **kwargs)
        self.reference = np.asarray(vertices).copy()
        self.previous = self.reference.copy()
        self.certified_intervals = self.full_ccd_queries = self.distance_queries = 0
        self.clearance = self._clearance(vertices)

    def _clearance(self, vertices):
        radius = .0008
        distance = self.minimum_distance(vertices, radius)
        self.distance_queries += 1
        return radius if distance is None else distance

    def step(self, vertices):
        return self.step_between(self.previous, vertices)

    def step_between(self, previous, current):
        if displacement_certificate(self.reference, previous, current, self.clearance):
            self.certified_intervals += 1
            self.checks += 1
            valid = True
        else:
            valid = super().step_between(previous, current)
            self.full_ccd_queries += 1
            self.clearance = self._clearance(current) if valid else 0.
            self.reference = np.asarray(current).copy()
        self.previous = np.asarray(current).copy()
        return valid


class CertifiedRigidSurfaceCCD(NativeRigidSurfaceCCD):
    def __init__(self, task, fem_vertices, fem_faces):
        super().__init__(task, fem_vertices, fem_faces)
        self.checker.close()
        self.checker = ClearanceSurfaceCCD(fem_vertices, fem_faces)
        self.method = ("ipctk 1.6.0 native FEM/rigid surfaces; every IPC substep certified either by "
                       "gap > 2*maximum vertex displacement from measured checkpoint (plus 1 nm margin), "
                       "or by full swept-surface CCD; conservative swept-body AABB rejection; rigid/rigid excluded")

    def _create_checker(self, part, fem_vertices):
        vertices = np.vstack((fem_vertices, part["previous"]))
        faces = np.vstack((self.fem_faces, part["faces"]+len(fem_vertices)))
        part["checker"] = ClearanceSurfaceCCD(vertices, faces,
            primary_vertices=np.arange(len(vertices)) < len(fem_vertices), cross_only=True)

    def statistics(self):
        checkers = [self.checker]+[p["checker"] for p in self.parts if p["checker"] is not None]
        return {key: sum(getattr(checker, key) for checker in checkers)
                for key in ("certified_intervals", "full_ccd_queries", "distance_queries")}
