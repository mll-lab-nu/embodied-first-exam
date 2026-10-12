"""Oracle helpers for the YAM arms: TCP frame from the finger keypoints, closed-loop
differential IK on the PhysX Jacobian (privileged state), gripper widths.

Gripper: action value q in [-0.0475 (open), 0 (closed)]; jaw opening = -2 q (95 mm stroke).
"""
import numpy as np
import torch

from oracle_lib_np import quat_to_mat, rot_err, triad, down_rotation, YamKin

from yamlab.robot.yam import ROBOT
from yamlab.robot.yam.action import YamActionLayout as AL

OPEN = -0.0475


class Arm:
    def __init__(self, env, name):
        self.env, self.name = env, name
        self.art = env.scene[name]
        self.bn = list(self.art.body_names)
        self.l6 = self.bn.index("link_6")
        self.lf = self.bn.index("left_finger")
        self.rf = self.bn.index("right_finger")
        self.jids = [self.art.joint_names.index(f"joint{i}") for i in range(1, 7)]
        self.fid = self.art.joint_names.index("left_finger")
        kp = ROBOT.fingers if hasattr(ROBOT, "fingers") else None
        self.tip_lf = np.array([-0.088, 0.025, -0.045])   # configs/robot/yam.yaml fingers.lf.keypoints[0]
        self.tip_rf = np.array([-0.025, -0.088, -0.045])  # fingers.rf.keypoints[0]
        self.base1_lf = np.array([-0.02, 0.058, -0.048]); self.base2_lf = np.array([-0.02, -0.008, -0.048])
        self.base1_rf = np.array([-0.058, -0.02, -0.048]); self.base2_rf = np.array([0.008, -0.02, -0.048])
        self.tcp_l6 = None   # TCP in link_6 frame, measured once (calibrate)
        self.close_l6 = None  # closing direction (lf tip -> rf tip) in link_6 frame
        self.tool_l6 = None   # approach direction (link_6 -> TCP) in link_6 frame

    def body_pose(self, idx):
        p = self.art.data.body_link_pos_w[0, idx].cpu().numpy().astype(float) - self.env.scene.env_origins[0].cpu().numpy()
        q = self.art.data.body_link_quat_w[0, idx].cpu().numpy().astype(float)
        return p, quat_to_mat(q)

    def finger_points(self, along=0.35):
        """World tip points of both fingers and a pad point `along` of the way tip->base."""
        pl, Rl = self.body_pose(self.lf)
        pr, Rr = self.body_pose(self.rf)
        tl = pl + Rl @ self.tip_lf
        tr = pr + Rr @ self.tip_rf
        bl = pl + Rl @ (0.5 * (self.base1_lf + self.base2_lf))
        br = pr + Rr @ (0.5 * (self.base1_rf + self.base2_rf))
        padl = tl + along * (bl - tl)
        padr = tr + along * (br - tr)
        return tl, tr, padl, padr

    def calibrate(self, pad_along=0.12):
        """TCP = midpoint of the two finger pads at `pad_along` (0 = tip) -> fixed in link_6 frame."""
        p6, R6 = self.body_pose(self.l6)
        tl, tr, padl, padr = self.finger_points(pad_along)
        tcp = 0.5 * (padl + padr)
        self.tcp_l6 = R6.T @ (tcp - p6)
        c = tr - tl
        self.close_l6 = R6.T @ (c / np.linalg.norm(c))
        t = tcp - p6
        self.tool_l6 = R6.T @ (t / np.linalg.norm(t))
        return dict(tcp_l6=self.tcp_l6.tolist(), close_l6=self.close_l6.tolist(), tool_l6=self.tool_l6.tolist(),
                    jaw_mm=float(np.linalg.norm(tr - tl) * 1000))

    def tcp(self):
        p6, R6 = self.body_pose(self.l6)
        return p6 + R6 @ self.tcp_l6, R6

    def q(self):
        return self.art.data.joint_pos[0, self.jids].cpu().numpy().astype(float)

    def jacobian_tcp(self):
        J = self.art.root_physx_view.get_jacobians()[0, self.l6 - 1].cpu().numpy().astype(float)  # fixed base
        J = J[:, self.jids]
        p6, R6 = self.body_pose(self.l6)
        r = R6 @ self.tcp_l6
        rx = np.array([[0, -r[2], r[1]], [r[2], 0, -r[0]], [-r[1], r[0], 0]])
        Jl = J[:3] - rx @ J[3:]
        return np.vstack((Jl, J[3:]))

    def down_rotation(self, close_dir_xy_angle):
        """Gripper pointing down (tool axis -Z), jaw closing along (cos a, sin a, 0)."""
        a = close_dir_xy_angle
        return triad(self.tool_l6, self.close_l6, np.array([0, 0, -1.0]), np.array([np.cos(a), np.sin(a), 0.0]))

    def ik_step(self, p_des, R_des, q_ref=None, lam=0.02, max_dq=0.08, w_rot=0.5):
        """One damped-least-squares step from the measured state -> absolute 6-joint target."""
        p, R6 = self.tcp()
        e = np.r_[p_des - p, w_rot * rot_err(R6, R_des)]
        J = self.jacobian_tcp()
        J[3:] *= w_rot
        dq = J.T @ np.linalg.solve(J @ J.T + lam ** 2 * np.eye(6), e)
        m = np.abs(dq).max()
        if m > max_dq:
            dq *= max_dq / m
        q0 = self.q() if q_ref is None else q_ref
        return q0 + dq, float(np.linalg.norm(p_des - p)), float(np.linalg.norm(rot_err(R6, R_des)))


