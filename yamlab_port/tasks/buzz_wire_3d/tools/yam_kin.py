"""Numpy kinematics of one YAM arm (product of exponentials), extracted from yam.usd.

Source data: data/yam_kin.npz written by tools/extract_yam_kin.py (rest pose = all joints 0,
frames relative to the arm root prim). Read-only model of the unchanged YAMLab robot; used
for offline reach / IK planning. Verified against Isaac body poses (see STATUS.md).
"""
import json
import os
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT = os.path.join(_HERE, "..", "data", "yam_kin.npz")


def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def exp_rot(w, th):
    K = skew(w)
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def quat_wxyz_to_mat(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def mat_to_quat_wxyz(R):
    from scipy.spatial.transform import Rotation
    x, y, z, w = Rotation.from_matrix(R).as_quat()
    q = np.array([w, x, y, z])
    return q if q[0] >= 0 else -q


class YamArm:
    LINKS = ["arm", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6", "left_finger", "right_finger",
             "camera_mount", "camera_d405"]
    FIXED_TO_LINK6 = ("camera_mount", "camera_d405")

    def __init__(self, base_pos=(0.2525, -0.305, 0.76), path=_DEFAULT):
        d = np.load(path, allow_pickle=False)
        names = [str(x) for x in d["links"]]
        self.T0 = {l: d["T"][i] for i, l in enumerate(names)}
        self.joints = json.loads(str(d["joints"]))
        self.base = np.eye(4)
        self.base[:3, 3] = base_pos
        self.lo = np.array([j["lo"] for j in self.joints[:6]])
        self.hi = np.array([j["hi"] for j in self.joints[:6]])
        self.hulls = {}
        for k in d.files:
            if k.startswith("hull_"):
                link, i = k[5:].rsplit("_", 1)
                self.hulls.setdefault(link, []).append(d[k])

    def _joint_T(self, j, q):
        T = np.eye(4)
        a = np.array(j["axis"]); a /= np.linalg.norm(a)
        p = np.array(j["point"])
        if j["type"] == "revolute":
            R = exp_rot(a, q)
            T[:3, :3] = R
            T[:3, 3] = p - R @ p
        else:
            T[:3, 3] = a * q
        return T

    def fk_all(self, q, finger=0.0):
        """World transforms of all links. q: 6 arm joints, finger: finger joint value (both)."""
        out = {"arm": self.base @ self.T0["arm"]}
        G = np.eye(4)
        for i in range(6):
            G = G @ self._joint_T(self.joints[i], q[i])
            out[self.joints[i]["child"]] = self.base @ G @ self.T0[self.joints[i]["child"]]
        for j in self.joints[6:]:
            out[j["child"]] = self.base @ G @ self._joint_T(j, finger) @ self.T0[j["child"]]
        for l in self.FIXED_TO_LINK6:
            if l in self.T0:
                out[l] = self.base @ G @ self.T0[l]
        return out

    def link6(self, q):
        G = np.eye(4)
        for i in range(6):
            G = G @ self._joint_T(self.joints[i], q[i])
        return self.base @ G @ self.T0["link_6"]

    def jacobian_space(self, q, point_world):
        """6x6 geometric Jacobian [v; w] of a point fixed to link_6 (world frame)."""
        G = np.eye(4)
        J = np.zeros((6, 6))
        for i in range(6):
            j = self.joints[i]
            a = np.array(j["axis"]); a /= np.linalg.norm(a)
            p = np.array(j["point"])
            Gw = self.base @ G
            aw = Gw[:3, :3] @ a
            pw = Gw[:3, :3] @ p + Gw[:3, 3]
            J[:3, i] = np.cross(aw, point_world - pw)
            J[3:, i] = aw
            G = G @ self._joint_T(j, q[i])
        return J

    def hull_points_world(self, q, finger=0.0, links=None):
        T = self.fk_all(q, finger)
        pts = {}
        for l in (links or self.LINKS):
            if l not in self.hulls:
                continue
            P = np.concatenate(self.hulls[l])
            pts[l] = (T[l][:3, :3] @ P.T).T + T[l][:3, 3]
        return pts
