"""Native SAPIEN Pinocchio IK with bounded numerical fallback; no scene writes."""

import numpy as np
import sapien
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from .panda_limits import LOWER, UPPER


class Kinematics:
    def __init__(self, articulation, tcp_name="panda_hand_tcp"):
        self.robot = articulation
        self.pin = articulation.create_pinocchio_model()
        self.index = next(
            i for i, l in enumerate(articulation.links) if l.entity.name == tcp_name
        )

    def solve(self, target: sapien.Pose, initial=None) -> np.ndarray:
        q = self.robot.qpos.copy() if initial is None else np.asarray(initial).copy()
        local = self.robot.pose.inv() * target
        seeds = [
            q,
            np.array([0, 0.3, 0, -2.4, 0, 3.1, 0.7854, q[7], q[8]]),
            np.array([0, 0.6, 0, -1.8, 0, 2.4, 0.7854, q[7], q[8]]),
        ]
        for seed in seeds:
            result, success, error = self.pin.compute_inverse_kinematics(
                self.index,
                local,
                initial_qpos=seed,
                active_qmask=np.array([1] * 7 + [0] * 2),
                max_iterations=500,
            )
            for i in range(7):
                legal = [
                    result[i] + 2 * np.pi * k
                    for k in range(-2, 3)
                    if LOWER[i] <= result[i] + 2 * np.pi * k <= UPPER[i]
                ]
                if legal:
                    result[i] = min(legal, key=lambda a: abs(a - q[i]))
            if (
                np.linalg.norm(error) < 0.0015
                and np.all(result[:7] >= LOWER)
                and np.all(result[:7] <= UPPER)
            ):
                return result
        target_matrix = local.to_transformation_matrix()

        def residual(arm):
            candidate = np.r_[arm, q[7:]]
            self.pin.compute_forward_kinematics(candidate)
            current = self.pin.get_link_pose(self.index).to_transformation_matrix()
            rotation = Rotation.from_matrix(
                target_matrix[:3, :3] @ current[:3, :3].T
            ).as_rotvec()
            return np.r_[
                5 * (current[:3, 3] - target_matrix[:3, 3]),
                rotation,
                0.0002 * (arm - q[:7]),
            ]

        result = least_squares(
            residual,
            np.clip(q[:7], LOWER + 0.005, UPPER - 0.005),
            bounds=(LOWER + 0.001, UPPER - 0.001),
            diff_step=1e-4,
            max_nfev=120,
        )
        error = residual(result.x)
        if np.linalg.norm(error[:3]) / 5 > 0.0015 or np.linalg.norm(error[3:6]) > 0.005:
            raise ValueError(
                f"Unreachable constrained TCP pose {target.p}: position residual {np.linalg.norm(error[:3]) / 5:.6f} m, orientation {np.linalg.norm(error[3:6]):.6f} rad"
            )
        return np.r_[result.x, q[7:]]
