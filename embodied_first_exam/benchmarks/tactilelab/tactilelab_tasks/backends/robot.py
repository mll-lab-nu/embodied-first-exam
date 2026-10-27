"""X-Trainer + GelSight-Mini robot wrapper over an Isaac Lab ``Articulation``.

Owns everything robot-specific : the canonical joint
order, joint limits, the implicit PD gains, gripper open/close targets, forward
kinematics of the end-effector links and gel pad bodies read from the articulation
body states, the compliant gel contact material and the parked-arm defaults.

Isaac Lab is imported lazily inside :func:`articulation_cfg` / :class:`XTrainerGsmini`
so this module can be imported (for the constants) without a simulator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from ..core import math as m
from ..core.types import (
    EE_LINKS,
    GEL_BODIES,
    GRIPPER_CLOSE,
    GRIPPER_CLOSE_Q,
    GRIPPER_OPEN_Q,
    GRIPPER_WIDTH_OFFSET,
    JOINT_NAMES,
    PARKED_LEFT_ARM,
    ROBOT_BASE_POS,
)

ASSET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "robots", "xtrainer_gsmini"
)
DEFAULT_USD = os.path.join(ASSET_DIR, "usd", "xtrainer_gsmini.usd")

# stiffness, damping, effort limit per joint group (implicit PD)
ARM_GAINS: Dict[str, Tuple[float, float, float]] = {
    "1": (600.0, 60.0, 67.0),
    "2": (600.0, 20.0, 67.0),
    "3": (300.0, 12.0, 34.2),
    "4": (180.0, 8.0, 18.6),
    "5": (180.0, 8.0, 18.6),
    "6": (180.0, 8.0, 18.6),
}
FINGER_GAINS: Tuple[float, float, float] = (200.0, 40.0, 20.0)

JOINT_LIMITS: Dict[str, Tuple[float, float]] = {
    **{f"J{a}_{j}_joint": (-6.230825, 6.230825) for a in (1, 2) for j in (1, 4, 5, 6)},
    **{f"J{a}_2_joint": (-3.1067, 3.1067) for a in (1, 2)},
    **{f"J{a}_3_joint": (-2.7925, 2.7925) for a in (1, 2)},
    **{f"J{a}_7_joint": (-0.041, 0.010) for a in (1, 2)},
    **{f"J{a}_8_joint": (-0.010, 0.041) for a in (1, 2)},
}
"""Position limits (rad / m) as authored in the URDF / USD (fingers widened to 0.041)."""
ARM_VEL_LIMIT = 3.0


@dataclass
class RobotCfg:
    """Spawn-time configuration of the robot."""

    usd_path: str = DEFAULT_USD
    prim_path: str = "/World/Robot"
    base_pos: Tuple[float, float, float] = ROBOT_BASE_POS
    base_quat: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    gel_stiffness: float = 650.0
    gel_damping: float = 0.5
    gel_friction: float = 1.5
    close_magnitude: float = GRIPPER_CLOSE_Q
    """Finger close target magnitude (0.038; the drawer task uses 0.041)."""
    open_magnitude: float = GRIPPER_OPEN_Q
    right_arm_q0: Tuple[float, ...] = (0.0,) * 6
    left_arm_q0: Tuple[float, ...] = PARKED_LEFT_ARM
    solver_position_iterations: int = 8
    solver_velocity_iterations: int = 0
    self_collisions: bool = True
    max_depenetration_velocity: float = 5.0

    def q0(self) -> np.ndarray:
        """Initial 16-vector: arms at their defaults, fingers open."""
        q = np.zeros(16)
        q[0:6] = self.right_arm_q0
        q[6:12] = self.left_arm_q0
        q[12:16] = [self.open_magnitude, -self.open_magnitude, self.open_magnitude, -self.open_magnitude]
        return q

    def base_pose(self) -> np.ndarray:
        return m.pose_from_pos_quat(self.base_pos, self.base_quat)


def gripper_targets(
    command: int,
    magnitude_close: float = GRIPPER_CLOSE_Q,
    magnitude_open: float = GRIPPER_OPEN_Q,
    gap: Optional[float] = None,
) -> np.ndarray:
    """``(q7, q8)`` finger targets for a binary command or an explicit gap (m).

    The gap model is ``width = 0.082 + q7 - q8`` with the two fingers moving
    symmetrically (``q8 = -q7``), clipped to the joint limits.
    """
    if gap is not None and np.isfinite(gap):
        q7 = 0.5 * (float(gap) - GRIPPER_WIDTH_OFFSET)
        q7 = float(np.clip(q7, -0.041, 0.010))
        return np.array([q7, -q7])
    if int(command) == GRIPPER_CLOSE:
        return np.array([-magnitude_close, magnitude_close])
    return np.array([magnitude_open, -magnitude_open])


def articulation_cfg(cfg: RobotCfg):
    """Build the Isaac Lab ``ArticulationCfg`` (imports Isaac Lab)."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import ArticulationCfg

    actuators = {}
    for arm in ("1", "2"):
        for j, (k, d, e) in ARM_GAINS.items():
            actuators[f"j{arm}_{j}"] = ImplicitActuatorCfg(
                joint_names_expr=[f"J{arm}_{j}_joint"], effort_limit_sim=e, stiffness=k, damping=d
            )
        k, d, e = FINGER_GAINS
        actuators[f"j{arm}_gripper"] = ImplicitActuatorCfg(
            joint_names_expr=[f"J{arm}_7_joint", f"J{arm}_8_joint"], effort_limit_sim=e, stiffness=k, damping=d
        )
    q0 = cfg.q0()
    return ArticulationCfg(
        prim_path=cfg.prim_path,
        spawn=sim_utils.UsdFileWithCompliantContactCfg(
            usd_path=cfg.usd_path,
            activate_contact_sensors=False,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=True, max_depenetration_velocity=cfg.max_depenetration_velocity
            ),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=cfg.self_collisions,
                solver_position_iteration_count=cfg.solver_position_iterations,
                solver_velocity_iteration_count=cfg.solver_velocity_iterations,
                fix_root_link=True,
            ),
            compliant_contact_stiffness=cfg.gel_stiffness,
            compliant_contact_damping=cfg.gel_damping,
            physics_material_prim_path=list(GEL_BODIES),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=tuple(cfg.base_pos),
            rot=tuple(cfg.base_quat),
            joint_pos={name: float(q0[i]) for i, name in enumerate(JOINT_NAMES)},
        ),
        actuators=actuators,
        soft_joint_pos_limit_factor=1.0,
    )


def apply_gel_friction(prim_path: str, friction: float, gel_bodies: Sequence[str] = GEL_BODIES) -> int:
    """Set static = dynamic friction on the gel compliant materials (USD API). Returns the count touched."""
    from isaaclab.sim.utils.stage import get_current_stage
    from pxr import UsdPhysics

    stage = get_current_stage()
    n = 0
    for gel in gel_bodies:
        prim = stage.GetPrimAtPath(f"{prim_path}/{gel}/compliant_material")
        if not prim.IsValid():
            continue
        api = UsdPhysics.MaterialAPI.Apply(prim)
        api.CreateStaticFrictionAttr().Set(float(friction))
        api.CreateDynamicFrictionAttr().Set(float(friction))
        n += 1
    return n


class XTrainerGsmini:
    """Runtime wrapper around the spawned articulation (single env).

    Create it after the simulation context exists and before ``sim.reset()``; call
    :meth:`initialize` after ``sim.reset()``. All joint vectors use the canonical
    order of :data:`tactilelab_tasks.core.types.JOINT_NAMES`; poses are env-frame pose7.
    """

    def __init__(self, cfg: Optional[RobotCfg] = None):
        from isaaclab.assets import Articulation

        self.cfg = cfg or RobotCfg()
        self.articulation = Articulation(articulation_cfg(self.cfg))
        self._gel_mats = apply_gel_friction(self.cfg.prim_path, self.cfg.gel_friction)
        self._joint_ids: Optional[np.ndarray] = None
        self._body_ids: Dict[str, int] = {}
        self._gripper_cmd = np.zeros(2, dtype=np.int64)
        self._gripper_gap: Optional[np.ndarray] = None
        self.device = None

    # ------------------------------------------------------------------ setup
    def initialize(self) -> None:
        """Resolve joint/body indices (after ``sim.reset()``)."""
        import torch

        art = self.articulation
        self.device = art.device
        ids, names = art.find_joints(list(JOINT_NAMES), preserve_order=True)
        if list(names) != list(JOINT_NAMES):
            raise RuntimeError(f"joint resolution mismatch: {names}")
        self._joint_ids = np.asarray(ids, dtype=np.int64)
        self._joint_ids_t = torch.as_tensor(self._joint_ids, device=self.device, dtype=torch.long)
        self._arm_ids_t = self._joint_ids_t[:12]
        self._finger_ids_t = self._joint_ids_t[12:]
        for name in (*EE_LINKS, *GEL_BODIES, "base_link"):
            idx, _ = art.find_bodies(name)
            if len(idx) != 1:
                raise RuntimeError(f"body {name} not found in the articulation")
            self._body_ids[name] = int(idx[0])

    @property
    def gel_material_count(self) -> int:
        return self._gel_mats

    # ------------------------------------------------------------------ reads
    def joint_pos(self) -> np.ndarray:
        return self.articulation.data.joint_pos[0, self._joint_ids_t].cpu().numpy().astype(np.float64)

    def joint_vel(self) -> np.ndarray:
        return self.articulation.data.joint_vel[0, self._joint_ids_t].cpu().numpy().astype(np.float64)

    def joint_pos_target(self) -> np.ndarray:
        return self.articulation.data.joint_pos_target[0, self._joint_ids_t].cpu().numpy().astype(np.float64)

    def body_pose(self, name: str) -> np.ndarray:
        """Env-frame pose7 of a body (link frame, not centre of mass)."""
        st = self.articulation.data.body_link_pose_w[0, self._body_ids[name]].cpu().numpy().astype(np.float64)
        return m.pose_from_pos_quat(st[:3], st[3:7])

    def ee_pose(self, arm: int) -> np.ndarray:
        return self.body_pose(EE_LINKS[int(arm)])

    def gel_poses(self) -> Dict[str, np.ndarray]:
        return {g: self.body_pose(g) for g in GEL_BODIES}

    def base_pose(self) -> np.ndarray:
        return self.body_pose("base_link")

    def gripper_width(self, arm: int) -> float:
        q = self.joint_pos()
        s = slice(12, 14) if int(arm) == 0 else slice(14, 16)
        return float(GRIPPER_WIDTH_OFFSET + q[s][0] - q[s][1])

    def obs(self) -> Dict[str, np.ndarray]:
        """The robot part of ``obs["policy"]``."""
        r, l = self.ee_pose(0), self.ee_pose(1)
        return {
            "joint_pos": self.joint_pos().astype(np.float32),
            "joint_vel": self.joint_vel().astype(np.float32),
            "ee_pos_right": r[:3].astype(np.float32),
            "ee_quat_right": r[3:7].astype(np.float32),
            "ee_pos_left": l[:3].astype(np.float32),
            "ee_quat_left": l[3:7].astype(np.float32),
            "gripper_width_right": np.array([self.gripper_width(0)], dtype=np.float32),
            "gripper_width_left": np.array([self.gripper_width(1)], dtype=np.float32),
        }

    # ------------------------------------------------------------------ writes
    def set_arm_targets(self, q_arm12: np.ndarray) -> None:
        import torch

        t = torch.as_tensor(np.asarray(q_arm12, dtype=np.float32).reshape(1, 12), device=self.device)
        self.articulation.set_joint_position_target(t, joint_ids=self._arm_ids_t)

    def set_gripper(self, command: Sequence[int], gap: Optional[Sequence[float]] = None) -> None:
        """Binary ``[right, left]`` command (0 open / 1 close) with an optional gap override."""
        import torch

        self._gripper_cmd = np.asarray(command, dtype=np.int64).reshape(2)
        self._gripper_gap = None if gap is None else np.asarray(gap, dtype=np.float64).reshape(2)
        q = np.concatenate(
            [
                gripper_targets(
                    self._gripper_cmd[i],
                    self.cfg.close_magnitude,
                    self.cfg.open_magnitude,
                    None if self._gripper_gap is None else self._gripper_gap[i],
                )
                for i in range(2)
            ]
        )
        t = torch.as_tensor(q.astype(np.float32).reshape(1, 4), device=self.device)
        self.articulation.set_joint_position_target(t, joint_ids=self._finger_ids_t)

    def set_finger_effort_limit(self, arm: int, effort: float) -> None:
        """Change the finger drive effort limit (N) of one gripper (the press-effort knob)."""
        import torch

        ids = self._finger_ids_t[0:2] if int(arm) == 0 else self._finger_ids_t[2:4]
        self.articulation.write_joint_effort_limit_to_sim(
            torch.full((1, 2), float(effort), device=self.device), joint_ids=ids
        )

    def write_joint_state(self, q: np.ndarray, qd: Optional[np.ndarray] = None) -> None:
        """Teleport the joints (reset): positions, velocities and the position targets."""
        import torch

        q = np.asarray(q, dtype=np.float32).reshape(1, 16)
        qd = np.zeros((1, 16), dtype=np.float32) if qd is None else np.asarray(qd, dtype=np.float32).reshape(1, 16)
        qt = torch.as_tensor(q, device=self.device)
        self.articulation.write_joint_state_to_sim(
            qt, torch.as_tensor(qd, device=self.device), joint_ids=self._joint_ids_t
        )
        self.articulation.set_joint_position_target(qt, joint_ids=self._joint_ids_t)
        self.articulation.set_joint_velocity_target(torch.zeros_like(qt), joint_ids=self._joint_ids_t)
        self.articulation.set_joint_effort_target(torch.zeros_like(qt), joint_ids=self._joint_ids_t)
        self.articulation.write_data_to_sim()

    def reset(self, q: Optional[np.ndarray] = None) -> None:
        self.articulation.reset()
        self.write_joint_state(self.cfg.q0() if q is None else q)
        self._gripper_cmd = np.zeros(2, dtype=np.int64)
        self._gripper_gap = None

    def write_data_to_sim(self) -> None:
        self.articulation.write_data_to_sim()

    def update(self, dt: float) -> None:
        self.articulation.update(dt)

    # ------------------------------------------------------------------ state
    def get_state(self) -> Dict[str, np.ndarray]:
        return {
            "robot_q": self.joint_pos(),
            "robot_qd": self.joint_vel(),
            "robot_q_target": self.joint_pos_target(),
            "gripper_cmd": self._gripper_cmd.copy(),
        }

    def set_state(self, state: Dict[str, np.ndarray]) -> None:
        import torch

        self.write_joint_state(np.asarray(state["robot_q"]), np.asarray(state.get("robot_qd", np.zeros(16))))
        if "robot_q_target" in state:
            t = torch.as_tensor(
                np.asarray(state["robot_q_target"], dtype=np.float32).reshape(1, 16), device=self.device
            )
            self.articulation.set_joint_position_target(t, joint_ids=self._joint_ids_t)
        if "gripper_cmd" in state:
            self._gripper_cmd = np.asarray(state["gripper_cmd"], dtype=np.int64).reshape(2)


__all__ = [
    "RobotCfg",
    "XTrainerGsmini",
    "articulation_cfg",
    "apply_gel_friction",
    "gripper_targets",
    "ARM_GAINS",
    "FINGER_GAINS",
    "JOINT_LIMITS",
    "DEFAULT_USD",
]
