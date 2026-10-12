"""Grasp frames (link_6 pose in the wand body frame) and arm collision sampling.

Gripper (link_6) axes, measured from yam.usd: x = closing axis, y = finger-width axis
(+y = wrist-camera side), z = approach; finger tips at z = 0.1453; pad inner face at
x = +-(|q_finger| - 0.001).
"""
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from bw_geom import GRIP_XC, GRIP_X0, GRIP_X1, seg_point_dist, box_point_dist, TABLE_Z, TUBE_R, WIRE_R

TIP_Z = 0.1453


def T_from(R, p):
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = p
    return T


def topdown(kind, c=0.0541, tip_gap=0.001):
    """kind 'A': approach -wand z (picks a face-up wand); 'B': approach +wand z (places a face-down wand).
    c: wand-x of the gripper centre line; tip_gap: tips stop this far short of the handle mid-plane."""
    zc = TIP_Z + tip_gap
    if kind == "A":
        R = np.column_stack([[0, 1, 0], [1, 0, 0], [0, 0, -1]])
        p = np.array([c, 0.0, zc])
    else:
        R = np.column_stack([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        p = np.array([c, 0.0, -zc])
    return T_from(R, p)


def pen(kind, x_tip=0.033, y_c=-0.0265, tilt_deg=7.0):
    """Pen grip along the handle (approach -wand x). kind 'up': camera side = +wand z (face-up wand);
    'down': camera side = -wand z (face-down wand). y_c: link6-y of the handle centre line;
    tilt: fingertips pitched toward the deck (rotation about the closing axis at the tip point)."""
    if kind == "up":
        R = np.column_stack([[0, -1, 0], [0, 0, 1], [-1, 0, 0]])
        s = 1.0
    else:
        R = np.column_stack([[0, 1, 0], [0, 0, -1], [-1, 0, 0]])
        s = -1.0
    # link6 origin: tips (z=TIP_Z) at wand x = x_tip, handle centre line at link6 y = y_c
    p = np.array([x_tip + TIP_Z, 0.0, -s * y_c])
    T = T_from(R, p)
    # tilt about the closing axis through the tip point on the handle axis
    tip = np.array([x_tip, 0.0, 0.0])
    axis = R[:, 0]
    Rt = Rotation.from_rotvec(np.deg2rad(tilt_deg) * axis).as_matrix()  # tips toward the deck
    Tt = np.eye(4)
    Tt[:3, :3] = Rt
    Tt[:3, 3] = tip - Rt @ tip
    return Tt @ T


class ArmPoints:
    """Surface samples of each link's collision hulls (link frame)."""

    def __init__(self, arm, spacing=0.007):
        self.arm = arm
        self.pts = {}
        rng = np.random.default_rng(0)
        for link, hulls in arm.hulls.items():
            P = []
            for h in hulls:
                m = trimesh.convex.convex_hull(h)
                n = max(40, int(m.area / spacing ** 2))
                # area-weighted uniform surface samples (deterministic) + hull vertices
                tri = m.triangles
                w = m.area_faces / m.area_faces.sum()
                idx = rng.choice(len(tri), size=n, p=w)
                u, v = rng.random(n), rng.random(n)
                flip = u + v > 1
                u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
                t = tri[idx]
                P.append(np.r_[t[:, 0] + u[:, None] * (t[:, 1] - t[:, 0]) + v[:, None] * (t[:, 2] - t[:, 0]), m.vertices])
            self.pts[link] = np.concatenate(P)

    def world(self, q, finger, links=None):
        T = self.arm.fk_all(q, finger)
        out = {}
        for l in (links or self.pts):
            if l in self.pts and l != "arm":
                out[l] = (T[l][:3, :3] @ self.pts[l].T).T + T[l][:3, 3]
        return out


_WIRE_TREES = {}


def wire_tree(scene, step=0.0005):
    key = id(scene)
    if key not in _WIRE_TREES:
        from scipy.spatial import cKDTree
        pts = []
        for a, b in zip(scene.rail[:-1], scene.rail[1:]):
            n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
            pts.append(a + np.linspace(0, 1, n, endpoint=False)[:, None] * (b - a))
        pts.append(scene.rail[-1:])
        _WIRE_TREES[key] = cKDTree(np.concatenate(pts))
    return _WIRE_TREES[key]


_BOXCACHE = {}


def _boxes(key, boxes):
    if key not in _BOXCACHE:
        out = []
        for c, h, R in boxes:
            M = R.as_matrix() if hasattr(R, "as_matrix") else np.asarray(R)
            ext = np.abs(M) @ h
            out.append((np.asarray(c), np.asarray(h), M, c - ext, c + ext))
        _BOXCACHE[key] = out
    return _BOXCACHE[key]


def _min_box_dist(P, boxes, cap=0.1):
    best = cap
    for c, h, M, lo, hi in boxes:
        sel = np.all((P > lo - best) & (P < hi + best), axis=1)
        if not sel.any():
            continue
        L = (P[sel] - c) @ M
        q = np.abs(L) - h
        d = np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(axis=1), 0)
        best = min(best, float(d.min()))
    return best


def clearances(scene, W, wand_pose=None, skip_wand_links=()):
    """Min distances (m) of arm sample points to wire (surface), deck, stops, table, wand."""
    res = {}
    P = np.concatenate(list(W.values()))
    lo, hi = scene.rail.min(0) - 0.06, scene.rail.max(0) + 0.06
    near = P[np.all((P > lo) & (P < hi), axis=1)]
    if len(near):
        d, _ = wire_tree(scene).query(near, distance_upper_bound=0.06)
        res["wire"] = float(min(d.min(), 0.06) - WIRE_R - 0.0003)
    else:
        res["wire"] = 0.06
    from bw_geom import FRAME_BOXES
    res["deck"] = _min_box_dist(P, _boxes(("deck", id(scene)), scene.deck_boxes))
    res["stops"] = _min_box_dist(P, _boxes(("stops", id(scene)), scene.stops))
    res["frame"] = _min_box_dist(P, _boxes("frame", FRAME_BOXES))
    res["table"] = float(P[:, 2].min() - TABLE_Z)
    if wand_pose is not None:
        from bw_geom import wand_metal_points
        p, R = wand_pose
        Wm = R.apply(wand_metal_points()) + p
        Pn = np.concatenate([v for k, v in W.items() if k not in skip_wand_links]) if skip_wand_links else P
        res["wand_metal"] = float(np.min(np.linalg.norm(Pn[:, None, :] - Wm[None], axis=-1)) - TUBE_R)
    return res


def ring(x_tip=-0.012):
    """Ring grip R_g': clamps the ring tube (top/bottom) on the far side of the loop, opposite the handle.
    Approach = +wand x (toward the handle), closing axis = -wand z, camera side = +wand y.
    The finger tips stop x_tip from the loop centre (inside the ring, 10.5 mm from a centred wire)."""
    R = np.column_stack([[0, 0, -1], [0, 1, 0], [1, 0, 0]])
    p = np.array([x_tip - TIP_Z, 0.0, 0.0])
    return T_from(R, p)
