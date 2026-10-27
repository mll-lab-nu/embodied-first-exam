"""Pink task-space inverse kinematics for the X-Trainer arms.

Controller:

* two frame tasks on ``J1_6`` (right) and ``J2_6`` (left), position cost 8,
  orientation cost 2, Levenberg-Marquardt damping 10, gain 0.5;
* a null-space posture task (cost 0.5, gain 0.3) pulling the twelve arm joints
  toward the posture captured at reset;
* a damping task (cost 0.8);
* QP solver ``daqp``; the joint target is ``q + v * dt * amplify`` with
  ``dt = 1/120`` and ``amplify = 2``, solved once per physics substep.

Targets are given in the **robot base frame** (``base_link``), which is the root of
the kinematic model; the scene converts env-frame poses with the robot base pose.
A NaN target for an arm means *hold*: the arm keeps the target it had when it turned
NaN (anchored at its current pose on the first NaN tick).

Requires ``pin`` (Pinocchio), ``pin-pink`` and ``daqp``. The model is built from the
URDF only (no meshes are loaded).
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Sequence

import numpy as np

from ..core import math as m
from ..core.types import EE_LINKS, JOINT_NAMES

try:
    import pinocchio as pin
    from pink import Configuration, solve_ik
    from pink.tasks import DampingTask, FrameTask, Task

    PINK_AVAILABLE = True
    _IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - depends on the environment
    pin = None
    PINK_AVAILABLE = False
    _IMPORT_ERROR = exc
    Task = object  # type: ignore

ARM_JOINTS = tuple(JOINT_NAMES[:12])
"""The twelve controlled joints (right arm then left arm)."""

ASSET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "robots", "xtrainer_gsmini"
)
DEFAULT_URDF = os.path.join(ASSET_DIR, "urdf", "xtrainer_pink.urdf")


class NullSpacePostureTask(Task):
    """Posture objective projected into the null space of the frame tasks.

    ``e(q) = M (q* - q)`` with ``M`` the mask of controlled joints, and the task
    Jacobian ``N = I - J^+ J`` where ``J`` stacks the frame Jacobians of the
    controlled frames; so the posture pull never fights the end-effector tasks.
    """

    def __init__(
        self,
        cost: float,
        controlled_frames: Sequence[str],
        controlled_joints: Sequence[str],
        lm_damping: float = 1.0,
        gain: float = 1.0,
    ):
        super().__init__(cost=cost, gain=gain, lm_damping=lm_damping)
        self.controlled_frames = list(controlled_frames)
        self.controlled_joints = set(controlled_joints)
        self.target_q: Optional[np.ndarray] = None
        self._mask: Optional[np.ndarray] = None

    def set_target(self, target_q: np.ndarray) -> None:
        self.target_q = np.asarray(target_q, dtype=np.float64).copy()

    def set_target_from_configuration(self, configuration) -> None:
        self.set_target(configuration.q)

    def _build_mask(self, configuration) -> None:
        names = list(configuration.model.names)[1:]
        self._mask = np.array([1.0 if n in self.controlled_joints else 0.0 for n in names])

    def compute_error(self, configuration) -> np.ndarray:
        if self.target_q is None:
            raise ValueError("posture target not set")
        if self._mask is None:
            self._build_mask(configuration)
        return self._mask * pin.difference(configuration.model, self.target_q, configuration.q)

    def compute_jacobian(self, configuration) -> np.ndarray:
        n = configuration.model.nv
        if not self.controlled_frames:
            return np.eye(n)
        J = np.concatenate([configuration.get_frame_jacobian(f) for f in self.controlled_frames], axis=0)
        JJt = J @ J.T + 1e-18 * np.eye(J.shape[0])
        try:
            X = np.linalg.solve(JJt, J)
            return np.eye(n) - J.T @ X
        except np.linalg.LinAlgError:
            return np.eye(n) - np.linalg.pinv(J) @ J

    def __repr__(self) -> str:
        return f"NullSpacePostureTask(cost={self.cost}, gain={self.gain}, frames={self.controlled_frames})"


class PinkIK:
    """Differential IK for both arms with fixed task weights.

    Args:
        urdf_path: pink URDF (defaults to the packaged ``xtrainer_pink.urdf``).
        dt: integration step (physics substep, 1/120 s).
        amplify: multiplier on ``v * dt`` (2).
        position_cost / orientation_cost / lm_damping / frame_gain: frame tasks.
        posture_cost / posture_gain: null-space posture task.
        damping_cost: damping task.
        solver: QP backend name for pink (``daqp``).
    """

    def __init__(
        self,
        urdf_path: str = DEFAULT_URDF,
        dt: float = 1.0 / 120.0,
        amplify: float = 2.0,
        position_cost: float = 8.0,
        orientation_cost: float = 2.0,
        lm_damping: float = 10.0,
        frame_gain: float = 0.5,
        posture_cost: float = 0.5,
        posture_gain: float = 0.3,
        posture_lm_damping: float = 1.0,
        damping_cost: float = 0.8,
        solver: str = "daqp",
        safety_break: bool = False,
        verbose: bool = False,
    ):
        if not PINK_AVAILABLE:
            raise ImportError(
                f"tactilelab_tasks.backends.ik_pink needs pinocchio, pin-pink and daqp: {_IMPORT_ERROR!r}"
            )
        if not os.path.exists(urdf_path):
            raise FileNotFoundError(urdf_path)
        self.dt = float(dt)
        self.amplify = float(amplify)
        self.solver = solver
        self.safety_break = bool(safety_break)
        self.verbose = verbose

        full = pin.buildModelFromUrdf(urdf_path)
        all_names = list(full.names)[1:]
        lock = [full.getJointId(n) for n in all_names if n not in ARM_JOINTS]
        q_full0 = pin.neutral(full)
        self.model = pin.buildReducedModel(full, lock, q_full0)
        self.data = self.model.createData()
        model_names = list(self.model.names)[1:]
        if model_names != list(ARM_JOINTS):
            # pinocchio keeps URDF order; map canonical <-> model order explicitly
            self._to_model = np.array([model_names.index(n) for n in ARM_JOINTS])
        else:
            self._to_model = np.arange(12)
        self._from_model = np.argsort(self._to_model)
        for link in EE_LINKS:
            if not self.model.existFrame(link):
                raise ValueError(f"frame {link} missing from {urdf_path}")

        self.configuration = Configuration(self.model, self.data, pin.neutral(self.model))
        self.frame_tasks = [
            FrameTask(
                link,
                position_cost=position_cost,
                orientation_cost=orientation_cost,
                lm_damping=lm_damping,
                gain=frame_gain,
            )
            for link in EE_LINKS
        ]
        self.posture_task = NullSpacePostureTask(
            posture_cost, EE_LINKS, ARM_JOINTS, lm_damping=posture_lm_damping, gain=posture_gain
        )
        self.damping_task = DampingTask(cost=damping_cost)
        self.tasks = [*self.frame_tasks, self.posture_task, self.damping_task]
        self._anchors: Dict[int, Optional[np.ndarray]] = {0: None, 1: None}
        self.last_targets: Dict[int, Optional[np.ndarray]] = {0: None, 1: None}
        self.reset(np.zeros(12))

    # ------------------------------------------------------------------ state
    def _q_model(self, q_arm12: np.ndarray) -> np.ndarray:
        return np.asarray(q_arm12, dtype=np.float64).reshape(12)[self._to_model]

    def reset(self, q_arm12: np.ndarray) -> None:
        """Set the posture target to ``q_arm12`` and clear the hold anchors."""
        qm = self._q_model(q_arm12)
        self.configuration.update(qm)
        self.posture_task.set_target(qm)
        for task in self.frame_tasks:
            task.set_target_from_configuration(self.configuration)
        self._anchors = {0: None, 1: None}
        self.last_targets = {0: None, 1: None}

    def set_posture(self, q_arm12: np.ndarray) -> None:
        self.posture_task.set_target(self._q_model(q_arm12))

    # ------------------------------------------------------------------ kinematics
    def fk(self, q_arm12: np.ndarray, link: str) -> np.ndarray:
        """Pose7 of ``link`` in the base frame for the given arm joints."""
        qm = self._q_model(q_arm12)
        pin.forwardKinematics(self.model, self.data, qm)
        pin.updateFramePlacements(self.model, self.data)
        T = self.data.oMf[self.model.getFrameId(link)]
        return m.pose_from_matrix(T.homogeneous)

    def ee_poses(self, q_arm12: np.ndarray) -> Dict[int, np.ndarray]:
        return {i: self.fk(q_arm12, link) for i, link in enumerate(EE_LINKS)}

    # ------------------------------------------------------------------ solve
    def solve(self, q_arm12: np.ndarray, targets_base: Sequence[Optional[np.ndarray]]) -> np.ndarray:
        """One IK step.

        Args:
            q_arm12: current arm joints (right, left) in the canonical order.
            targets_base: two pose7 targets (right, left) in the base frame; ``None``
                or a NaN pose means hold.

        Returns:
            ``(12,)`` joint position targets in the canonical order.
        """
        qm = self._q_model(q_arm12)
        self.configuration.update(qm)
        for i, task in enumerate(self.frame_tasks):
            tgt = targets_base[i] if i < len(targets_base) else None
            if tgt is None or m.is_nan_pose(tgt):
                if self._anchors[i] is None:
                    self._anchors[i] = m.pose_from_matrix(
                        self.configuration.get_transform_frame_to_world(task.frame).homogeneous
                    )
                tgt = self._anchors[i]
            else:
                self._anchors[i] = None
                tgt = np.asarray(tgt, dtype=np.float64).reshape(7)
            self.last_targets[i] = tgt
            task.set_target(pin.SE3(m.quat_to_matrix(tgt[3:7]), np.asarray(tgt[:3], dtype=np.float64)))
        try:
            v = solve_ik(self.configuration, self.tasks, self.dt, solver=self.solver, safety_break=self.safety_break)
        except Exception as exc:  # QP failure: hold the current configuration
            if self.verbose:
                print(f"[ik_pink] QP failed, holding: {exc!r}")
            return np.asarray(q_arm12, dtype=np.float64).reshape(12).copy()
        q_next = qm + v * self.dt * self.amplify
        q_next = np.clip(q_next, self.model.lowerPositionLimit, self.model.upperPositionLimit)
        return q_next[self._from_model]

    def errors(self, q_arm12: np.ndarray) -> Dict[int, tuple]:
        """``(translation, rotation)`` error of each arm against its last target."""
        out = {}
        for i, link in enumerate(EE_LINKS):
            tgt = self.last_targets[i]
            if tgt is None:
                continue
            out[i] = m.pose_error(self.fk(q_arm12, link), tgt)
        return out


__all__ = ["PinkIK", "NullSpacePostureTask", "PINK_AVAILABLE", "ARM_JOINTS", "DEFAULT_URDF"]
