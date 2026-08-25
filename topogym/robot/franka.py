from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from omegaconf import OmegaConf


def _array(value) -> np.ndarray:
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return np.array(value)


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _xyz(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 3)[0]


def _quat(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 4)[0]


@dataclass
class FrankaPositionIKController:
    """Tiny Franka controller: home reset, EE IK moves, and gripper commands."""

    scene: Any
    robot: Any
    cfg: Any

    def __post_init__(self) -> None:
        self.dofs_idx = [self.robot.get_joint(name).dofs_idx_local[0] for name in self.cfg.robot.joint_names]
        self.arm_joint_count = int(self.cfg.robot.arm_joint_count)
        self.gripper_joint_count = int(self.cfg.robot.gripper_joint_count)
        self.arm_dofs = self.dofs_idx[: self.arm_joint_count]
        self.gripper_dofs = self.dofs_idx[self.arm_joint_count :]
        self.ee_link = self.robot.get_link(self.cfg.robot.ee_link)
        self.default_ee_quat = _array(self.cfg.ik.default_ee_quat)
        self.current_gripper_qpos = float(self.cfg.gripper.open_qpos)

    def configure(self) -> None:
        self.robot.set_dofs_kp(_array(self.cfg.controller.kp), self.dofs_idx)
        self.robot.set_dofs_kv(_array(self.cfg.controller.kv), self.dofs_idx)
        self.robot.set_dofs_force_range(
            _array(self.cfg.controller.force_lower),
            _array(self.cfg.controller.force_upper),
            self.dofs_idx,
        )

    def reset_home(self, settle_steps: int | None = None) -> None:
        home_qpos = _array(self.cfg.home.qpos)
        self.current_gripper_qpos = float(home_qpos[-1])
        self.robot.set_dofs_position(home_qpos, self.dofs_idx, zero_velocity=True)
        self.robot.control_dofs_position(home_qpos, self.dofs_idx)
        self.step(settle_steps if settle_steps is not None else int(self.cfg.home.settle_steps))

    def step(self, steps: int) -> None:
        for _ in range(int(steps)):
            self.scene.step()

    def open_gripper(self, steps: int | None = None) -> None:
        self.current_gripper_qpos = float(self.cfg.gripper.open_qpos)
        self._control_gripper()
        self.step(steps if steps is not None else int(self.cfg.control_loop.steps_per_action))

    def close_gripper(self, steps: int | None = None) -> None:
        self.current_gripper_qpos = float(self.cfg.gripper.closed_qpos)
        self._control_gripper()
        self.step(steps if steps is not None else int(self.cfg.control_loop.steps_per_action))

    def set_gripper(self, qpos: float, steps: int | None = None) -> None:
        open_qpos = float(self.cfg.gripper.open_qpos)
        closed_qpos = float(self.cfg.gripper.closed_qpos)
        lo = min(open_qpos, closed_qpos)
        hi = max(open_qpos, closed_qpos)
        self.current_gripper_qpos = float(np.clip(qpos, lo, hi))
        self._control_gripper()
        if steps is not None:
            self.step(steps)

    def move_ee_to(
        self,
        pos,
        *,
        quat=None,
        steps: int | None = None,
        continuous_ik: bool = False,
    ) -> np.ndarray:
        target_pos = _array(pos)
        target_quat = self.default_ee_quat if quat is None else _array(quat)
        ik_kwargs = {}
        if continuous_ik:
            # Seeded from the current pose, so a swept arc carries its elbow
            # configuration instead of re-solving from scratch each step.
            #
            # The three budgets are the SOLVER's, and they are what decides
            # whether the returned joints actually put the hand on the target.
            # Measured 2026-08-24 on `cloth_unroll`: raising the commanded height
            # by 4 mm left the hand 4.5 mm BELOW it, while the controller tracked
            # the returned joints to within half a degree -- the same half-degree
            # it managed at the lower pose, where the hand arrived to 1.0 mm. The
            # controller is not the problem; the solve is stopping short.
            #
            # They read from config now (same defaults) so that can be swept
            # without editing a file every physical demo in the repo shares.
            ik_cfg = getattr(self.cfg, "ik", None)

            def budget(name: str, fallback):
                if ik_cfg is None:
                    return fallback
                value = getattr(ik_cfg, name, None)
                return fallback if value is None else value

            ik_kwargs = {
                "init_qpos": self.robot.get_qpos(),
                "dofs_idx_local": self.arm_dofs,
                "max_samples": int(budget("max_samples", 1)),
                "max_solver_iters": int(budget("max_solver_iters", 50)),
                "max_step_size": float(budget("max_step_size", 0.15)),
            }
            # Echoed once, because a sweep that returns identical readings has
            # two explanations -- the parameter does nothing, or the override
            # never arrived -- and the numbers alone cannot separate them. The
            # same trap cost a run on `cloth_unpleat`'s material sweep, whose
            # spike prints its material line for exactly this reason. Measured
            # 2026-08-24: max_solver_iters 50/200/800 gave byte-identical
            # readings, which is why this line exists.
            if not getattr(self, "_ik_budget_logged", False):
                self._ik_budget_logged = True
                print(
                    f"franka ik_budget max_samples={ik_kwargs['max_samples']} "
                    f"max_solver_iters={ik_kwargs['max_solver_iters']} "
                    f"max_step_size={ik_kwargs['max_step_size']} "
                    f"ee_quat_commanded={quat is not None}",
                    flush=True,
                )
        qpos = _as_numpy(
            self.robot.inverse_kinematics(
                link=self.ee_link,
                pos=target_pos,
                quat=target_quat,
                **ik_kwargs,
            )
        )
        qpos = qpos.reshape(-1, self.arm_joint_count + self.gripper_joint_count)[0]
        qpos[-self.gripper_joint_count :] = self.current_gripper_qpos
        self.robot.control_dofs_position(qpos[: self.arm_joint_count], self.arm_dofs)
        self._control_gripper()

        self.step(steps if steps is not None else int(self.cfg.control_loop.steps_per_action))
        return qpos

    def hand_pos(self) -> np.ndarray:
        return _xyz(self.ee_link.get_pos())

    def hand_quat(self) -> np.ndarray:
        return _quat(self.ee_link.get_quat())

    def gripper_qpos(self) -> np.ndarray:
        qpos = _as_numpy(self.robot.get_qpos())
        total_joint_count = self.arm_joint_count + self.gripper_joint_count
        return qpos.reshape(-1, total_joint_count)[0, -self.gripper_joint_count :].copy()

    def _control_gripper(self) -> None:
        target = np.full(self.gripper_joint_count, self.current_gripper_qpos)
        self.robot.control_dofs_position(target, self.gripper_dofs)
