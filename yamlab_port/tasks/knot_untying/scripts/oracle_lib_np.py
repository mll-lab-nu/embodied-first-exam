"""Pure numpy/scipy kinematics helpers for the YAM oracle (no Isaac imports)."""
import numpy as np


def quat_to_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def rot_err(R_cur, R_des):
    """Axis-angle vector (world) rotating R_cur onto R_des."""
    from scipy.spatial.transform import Rotation as Rot
    return Rot.from_matrix(R_des @ R_cur.T).as_rotvec()


def triad(a_loc, b_loc, a_w, b_w):
    """Rotation R with R a_loc = a_w and R b_loc ~ b_w (b orthogonalised)."""
    def frame(a, b):
        a = a / np.linalg.norm(a)
        b = b - a * (a @ b)
        b = b / np.linalg.norm(b)
        return np.column_stack((a, b, np.cross(a, b)))
    return frame(a_w, b_w) @ frame(a_loc, b_loc).T



def down_rotation(tool_l6, close_l6, close_dir_xy_angle):
    """link_6 rotation: tool axis -> -Z world, jaw closing axis -> (cos a, sin a, 0)."""
    a = close_dir_xy_angle
    return triad(np.asarray(tool_l6), np.asarray(close_l6), np.array([0, 0, -1.0]), np.array([np.cos(a), np.sin(a), 0.0]))


# ------------------------------------------------------------------ offline kinematics from the USD
class YamKin:
    """FK/IK of one YAM arm from its USD revolute joints (frames, axes, limits) + the base pose.
    Pure numpy after construction; used to plan joint targets without touching the sim state."""

    def __init__(self, stage, arm_root_path, base_pos, base_R, tcp_l6):
        from pxr import UsdPhysics
        joints = {}
        for prim in stage.Traverse():
            ps = str(prim.GetPath())
            if not ps.startswith(arm_root_path + "/") or not prim.IsA(UsdPhysics.RevoluteJoint):
                continue
            j = UsdPhysics.RevoluteJoint(prim)
            name = prim.GetName()
            if not name.startswith("joint"):
                continue
            b0 = str(j.GetBody0Rel().GetTargets()[0]).split("/")[-1]
            b1 = str(j.GetBody1Rel().GetTargets()[0]).split("/")[-1]
            lp0 = np.array(j.GetLocalPos0Attr().Get(), float); lp1 = np.array(j.GetLocalPos1Attr().Get(), float)
            q0 = j.GetLocalRot0Attr().Get(); q1 = j.GetLocalRot1Attr().Get()
            R0 = quat_to_mat([q0.GetReal(), *q0.GetImaginary()]); R1 = quat_to_mat([q1.GetReal(), *q1.GetImaginary()])
            ax = {"X": 0, "Y": 1, "Z": 2}[j.GetAxisAttr().Get()]
            lo, hi = j.GetLowerLimitAttr().Get(), j.GetUpperLimitAttr().Get()
            joints[name] = dict(b0=b0, b1=b1, T0=self._T(R0, lp0), T1inv=np.linalg.inv(self._T(R1, lp1)), ax=ax,
                                lo=np.radians(lo), hi=np.radians(hi))
        self.joints = [joints[f"joint{i}"] for i in range(1, 7)]
        self.base = self._T(base_R, base_pos)
        self.tcp_l6 = np.asarray(tcp_l6, float)
        self.lo = np.array([j["lo"] for j in self.joints]); self.hi = np.array([j["hi"] for j in self.joints])

    def to_json(self):
        return dict(joints=[dict(T0=j["T0"].tolist(), T1inv=j["T1inv"].tolist(), ax=j["ax"], lo=float(j["lo"]), hi=float(j["hi"]),
                                 b0=j["b0"], b1=j["b1"]) for j in self.joints], base=self.base.tolist(), tcp_l6=self.tcp_l6.tolist())

    @classmethod
    def from_json(cls, d):
        self = cls.__new__(cls)
        self.joints = [dict(T0=np.array(j["T0"]), T1inv=np.array(j["T1inv"]), ax=j["ax"], lo=j["lo"], hi=j["hi"]) for j in d["joints"]]
        self.base = np.array(d["base"]); self.tcp_l6 = np.array(d["tcp_l6"])
        self.lo = np.array([j["lo"] for j in self.joints]); self.hi = np.array([j["hi"] for j in self.joints])
        return self

    @staticmethod
    def _T(R, p):
        T = np.eye(4); T[:3, :3] = R; T[:3, 3] = p
        return T

    @staticmethod
    def _rot(ax, a):
        c, s = np.cos(a), np.sin(a)
        R = np.eye(4)
        if ax == 0: R[1, 1], R[1, 2], R[2, 1], R[2, 2] = c, -s, s, c
        elif ax == 1: R[0, 0], R[0, 2], R[2, 0], R[2, 2] = c, s, -s, c
        else: R[0, 0], R[0, 1], R[1, 0], R[1, 1] = c, -s, s, c
        return R

    def fk_link6(self, q):
        T = self.base
        for j, qi in zip(self.joints, q):
            T = T @ j["T0"] @ self._rot(j["ax"], qi) @ j["T1inv"]
        return T

    def fk_tcp(self, q):
        T = self.fk_link6(q)
        return T[:3, :3] @ self.tcp_l6 + T[:3, 3], T[:3, :3]

    def ik(self, p_des, R_des, q_seed, w_rot=0.3, extra_seeds=(), tol=1e-4, early=False):
        from scipy.optimize import least_squares
        lo, hi = self.lo + 1e-3, self.hi - 1e-3

        def res(q):
            p, R = self.fk_tcp(q)
            return np.r_[p - p_des, w_rot * rot_err(R, R_des)]
        best = None
        for seed in [q_seed, *extra_seeds]:
            s0 = np.clip(np.asarray(seed, float), lo, hi)
            r = least_squares(res, s0, bounds=(lo, hi), xtol=1e-10, ftol=1e-12, gtol=1e-12, max_nfev=400)
            cost = np.linalg.norm(r.fun)
            key = (cost > tol, np.linalg.norm(r.x - q_seed))
            if best is None or key < best[0]:
                best = (key, r.x, cost)
            if early and cost <= tol:
                break
        q = best[1]
        p, R = self.fk_tcp(q)
        return q, float(np.linalg.norm(p - p_des)), float(np.linalg.norm(rot_err(R, R_des)))


YamKinNP = YamKin
