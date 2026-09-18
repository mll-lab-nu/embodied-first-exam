"""Independent separating-axis checks on the authored convex collision solids."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation


def directions(vectors):
    vectors = np.asarray(vectors, dtype=float)
    lengths = np.linalg.norm(vectors, axis=1)
    vectors = vectors[lengths > 1e-10]/lengths[lengths > 1e-10, None]
    return np.unique(np.round(vectors, 10), axis=0)


class CompoundCollision:
    """Exact convex overlap test; positive gaps are separation lower bounds.

    World-axis AABB bounds reject distant pairs. Remaining pairs use face normals
    and crossed edge directions. This also catches full containment, which a
    triangle-surface intersection query alone cannot detect.
    """
    def __init__(self, fixed, moving):
        self.fixed = [self._data(m) for m in fixed]
        self.moving = [self._data(m) for m in moving]
        self.fixed_bounds = np.array([m.bounds for m in fixed])
        self.moving_corners = np.concatenate([m.vertices for m in moving])

    @staticmethod
    def _data(mesh):
        if not mesh.is_convex or not mesh.is_watertight:
            raise ValueError("Expected closed convex collision cells")
        edges = mesh.vertices[mesh.edges_unique[:,1]]-mesh.vertices[mesh.edges_unique[:,0]]
        return mesh.vertices.copy(), directions(mesh.face_normals), directions(edges)

    def gap(self, rotation, translation):
        R, t = np.asarray(rotation, dtype=float), np.asarray(translation, dtype=float)
        if R.shape != (3,3) or t.shape != (3,) or not np.isfinite(np.r_[R.ravel(),t]).all():
            raise ValueError("Invalid pose")
        transformed = [(v@R.T+t, n@R.T, e@R.T) for v,n,e in self.moving]
        bounds = np.array([[v.min(axis=0),v.max(axis=0)] for v,_,_ in transformed])
        delta = np.maximum(self.fixed_bounds[:,None,0]-bounds[None,:,1],
                           bounds[None,:,0]-self.fixed_bounds[:,None,1])
        broad = delta.max(axis=-1)
        best = float("inf")
        for flat in np.argsort(broad, axis=None):
            i,j = np.unravel_index(flat, broad.shape)
            if broad[i,j] >= best:
                break
            av,an,ae = self.fixed[i]
            bv,bn,be = transformed[j]
            cross = np.cross(ae[:,None],be[None]).reshape(-1,3)
            lengths = np.linalg.norm(cross,axis=1)
            axes = np.concatenate((np.eye(3),an,bn,cross[lengths>1e-8]/lengths[lengths>1e-8,None]))
            ap,bp = av@axes.T,bv@axes.T
            gap = np.maximum(ap.min(axis=0)-bp.max(axis=0),bp.min(axis=0)-ap.max(axis=0)).max()
            best = min(best,float(gap))
        return best


@dataclass
class Motion:
    name: str
    rotation: np.ndarray
    translation: np.ndarray
    end_translation: np.ndarray | None = None
    axis: np.ndarray | None = None
    angle_rad: float = 0.
    pivot: np.ndarray | None = None

    def pose(self,u):
        if self.axis is None:
            return self.rotation, self.translation+(self.end_translation-self.translation)*u
        delta = Rotation.from_rotvec(self.axis*self.angle_rad*u).as_matrix()
        return delta@self.rotation,self.pivot+delta@(self.translation-self.pivot)

    def speed_bound(self,points):
        if self.axis is None:
            return float(np.linalg.norm(self.end_translation-self.translation))
        q = points@self.rotation.T+self.translation-self.pivot
        return float(abs(self.angle_rad)*np.linalg.norm(np.cross(q,self.axis),axis=1).max())


def certify_motion(collision,motion,margin_m=.00005,max_depth=20):
    if not np.isfinite(margin_m) or margin_m <= 0:
        raise ValueError("A positive finite margin is required")
    bound = motion.speed_bound(collision.moving_corners)
    pending = [(0.,1.,0)]
    queries = 0
    minimum = float("inf")
    certified = float("inf")
    for u in (0.,1.):
        gap = collision.gap(*motion.pose(u))
        queries += 1
        minimum = min(minimum,gap)
        if gap < margin_m:
            return dict(name=motion.name,passed=False,queries=queries,witness_u=u,gap_m=gap,
                        reason="endpoint violates required clearance")
    while pending:
        a,b,depth = pending.pop()
        u = (a+b)/2
        gap = collision.gap(*motion.pose(u))
        queries += 1
        minimum = min(minimum,gap)
        lower = gap-bound*(b-a)/2
        if lower >= margin_m:
            certified = min(certified,lower)
        elif gap < margin_m or depth >= max_depth:
            return dict(name=motion.name,passed=False,queries=queries,witness_u=u,gap_m=gap,
                        reason="collision/clearance failure" if gap < margin_m else "unresolved interval")
        else:
            pending.extend(((a,u,depth+1),(u,b,depth+1)))
    return dict(name=motion.name,passed=True,queries=queries,minimum_sample_gap_m=minimum,
                continuous_gap_lower_bound_m=certified,margin_m=margin_m)
