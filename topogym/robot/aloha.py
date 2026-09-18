"""Named left/right ALOHA control on one shared Genesis articulation.

Targets for both arms can be submitted with steps=0 before one shared step().
IK is per arm; it does not provide collision-aware bimanual motion planning.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


def _numpy(value):
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


class AlohaArmController:
    def __init__(self, scene, robot, cfg, side):
        self.scene, self.robot, self.cfg, self.side = scene, robot, cfg, side
        names = [f"{side}/{name}" for name in cfg.robot.arm_joint_names]
        names += [f"{side}/{name}" for name in cfg.robot.finger_joint_names]
        joints = [robot.get_joint(name) for name in names]
        self.dofs_idx = [joint.dofs_idx_local[0] for joint in joints]
        self.qs_idx = [joint.qs_idx_local[0] for joint in joints]
        self.arm_dofs = self.dofs_idx[:6]
        # Only the first finger is actuated; its partner follows MJCF equality.
        self.actuated_dofs = self.dofs_idx[:7]
        self.ee_link = robot.get_link(f"{side}/{cfg.robot.ee_link}")
        self.current_gripper_qpos = float(cfg.home[side][-1])

    def configure(self):
        self.robot.set_dofs_kp(np.asarray(self.cfg.controller.kp), self.actuated_dofs)
        self.robot.set_dofs_kv(np.asarray(self.cfg.controller.kv), self.actuated_dofs)
        limits = np.asarray(self.cfg.controller.force_limit)
        self.robot.set_dofs_force_range(-limits, limits, self.actuated_dofs)

    def reset_home(self, *, settle_steps=0):
        home = np.asarray(self.cfg.home[self.side], dtype=float)
        self.robot.set_dofs_position(home, self.dofs_idx, zero_velocity=True)
        self.current_gripper_qpos = float(home[6])
        self.robot.control_dofs_position(home[:7], self.actuated_dofs)
        self.step(settle_steps)

    def step(self, steps):
        for _ in range(int(steps)):
            self.scene.step()

    def set_arm_qpos(self, qpos, *, steps=0):
        target = np.asarray(qpos, dtype=float)
        if target.shape != (6,) or not np.isfinite(target).all():
            raise ValueError("ALOHA arm target must contain six finite joint angles.")
        limits = np.asarray(self.cfg.robot.arm_joint_limits)
        if np.any(target < limits[:, 0]) or np.any(target > limits[:, 1]):
            raise ValueError("ALOHA arm target is outside the model joint limits.")
        self.robot.control_dofs_position(target, self.arm_dofs)
        self.step(steps)

    def set_gripper(self, qpos, *, steps=0):
        if not np.isfinite(qpos):
            raise ValueError("ALOHA finger displacement must be finite.")
        self.current_gripper_qpos = float(np.clip(
            qpos, self.cfg.gripper.closed_qpos, self.cfg.gripper.open_qpos))
        self.robot.control_dofs_position([self.current_gripper_qpos], self.dofs_idx[6:7])
        self.step(steps)

    def open_gripper(self, *, steps=0):
        self.set_gripper(float(self.cfg.gripper.open_qpos), steps=steps)

    def close_gripper(self, *, steps=0):
        self.set_gripper(float(self.cfg.gripper.closed_qpos), steps=steps)

    def move_ee_to(self, pos, *, quat=None, steps=0):
        """Command this arm's gripper_link in world coordinates (wxyz rotation)."""
        qpos = self.robot.inverse_kinematics(
            link=self.ee_link, pos=np.asarray(pos),
            quat=self.hand_quat() if quat is None else np.asarray(quat),
            init_qpos=self.robot.get_qpos(), dofs_idx_local=self.arm_dofs,
            max_samples=int(self.cfg.ik.max_samples),
            max_solver_iters=int(self.cfg.ik.max_solver_iters),
        )
        target = _numpy(qpos).reshape(-1, int(self.robot.n_qs))[0][self.qs_idx[:6]]
        self.set_arm_qpos(target, steps=steps)
        return target

    def arm_qpos(self):
        return self._qpos()[:6]

    def gripper_qpos(self):
        """Both finger rail displacements in metres, not the pad opening."""
        return self._qpos()[6:]

    def _qpos(self):
        return _numpy(self.robot.get_qpos()).reshape(-1, int(self.robot.n_qs))[0][self.qs_idx].copy()

    def hand_pos(self):
        return _numpy(self.ee_link.get_pos()).reshape(-1, 3)[0].copy()

    def hand_quat(self):
        return _numpy(self.ee_link.get_quat()).reshape(-1, 4)[0].copy()

    def grasp_center_pos(self):
        quat = self.hand_quat()
        return self.hand_pos() + Rotation.from_quat(quat[[1, 2, 3, 0]]).apply([0.13, 0, -0.003])


class AlohaDualArmController:
    def __init__(self, scene, robot, cfg):
        self.scene, self.robot, self.cfg = scene, robot, cfg
        self.arms = {side: AlohaArmController(scene, robot, cfg, side)
                     for side in ("left", "right")}
        self.left, self.right = self.arms.values()

    def configure(self):
        for arm in self.arms.values():
            arm.configure()

    def reset_home(self, settle_steps=None):
        # Set BOTH arms before advancing the shared scene clock.
        for arm in self.arms.values():
            arm.reset_home(settle_steps=0)
        self.step(int(self.cfg.home.settle_steps) if settle_steps is None else settle_steps)

    def step(self, steps):
        for _ in range(int(steps)):
            self.scene.step()

    def state(self):
        return {side: dict(arm_qpos=arm.arm_qpos().tolist(),
                           finger_qpos=arm.gripper_qpos().tolist(),
                           hand_pos=arm.hand_pos().tolist(),
                           hand_quat_wxyz=arm.hand_quat().tolist(),
                           grasp_center_pos=arm.grasp_center_pos().tolist())
                for side, arm in self.arms.items()}
