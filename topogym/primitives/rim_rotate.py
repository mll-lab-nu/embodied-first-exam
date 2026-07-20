from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from .physical_contact import ee_quat_for_yaw
from .pick_place import HAND_TO_PAD_Z


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _wrap_angle(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    return float((float(angle) + np.pi) % (2.0 * np.pi) - np.pi)


def rim_point_world(center, radius: float, azimuth: float) -> np.ndarray:
    """World point on a vertical coin's rim at ``azimuth`` about the Y rod.

    ``azimuth`` is measured from the disk top (+Z) toward +X, so ``azimuth=0``
    is the topmost rim point and a positive azimuth rolls the point down toward
    the +X front. The coin's face lies in the XZ plane (normal along Y), so the
    rim point shares the disk-center Y.
    """
    center = np.asarray(center, dtype=float)
    return center + float(radius) * np.array(
        [np.sin(float(azimuth)), 0.0, np.cos(float(azimuth))], dtype=float
    )


def signed_rotation(start_angle: float, target_angle: float, roll_sign: int) -> float:
    """Signed joint rotation from ``start`` to ``target`` in the ``roll_sign`` sense.

    ``roll_sign`` (+1/-1) selects which way around the continuous rod the disk
    turns; the hand-tracked rim point rolls up for one sign and down for the
    other. ``roll_sign=0`` takes the shortest path.
    """
    shortest = _wrap_angle(float(target_angle) - float(start_angle))
    if roll_sign > 0:
        return shortest if shortest >= 0.0 else shortest + 2.0 * np.pi
    if roll_sign < 0:
        return shortest if shortest <= 0.0 else shortest - 2.0 * np.pi
    return shortest


@dataclass(frozen=True)
class RimRotateResult:
    """Outcome and physical checkpoints from one rim-pinch rotation attempt."""

    success: bool
    driven: bool
    disk_name: str
    start_angle: float
    target_angle: float
    final_disk_angle: float
    rotation_achieved: float
    target_error: float
    max_follow_error: float
    release_drift: float
    completed_phases: tuple[str, ...]
    failure_reason: str | None = None


@dataclass(frozen=True)
class RimRotatePrimitive:
    """Rotate a vertical revolute disk by pinching its rim and rolling it down.

    Pure physics: the gripper straddles the two coin faces at a rim point and the
    disk turns only from finger friction as the hand sweeps the ideal rim arc.
    No ``set_dofs_position`` / teleport during execution -- the disk's revolute
    joint is driven entirely by contact, matching the collision-based IL contract.
    """

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "descend",
        "close",
        "grasp_settle",
        "rotate",
        "arc_settle",
        "release",
        "release_settle",
        "retreat",
    )

    approach_z: float
    steps_move: int
    steps_arc: int
    gripper_steps: int
    grasp_qpos: float | None = None
    grasp_yaw_offset: float = 0.0
    approach_clearance: float = 0.035
    retreat_clearance: float = 0.035
    close_hold_steps: int = 30
    arc_settle_steps: int = 40
    release_hold_steps: int = 30
    rotation_tolerance: float = np.deg2rad(8.0)
    min_rotation: float = np.deg2rad(20.0)
    max_follow_error: float = 0.05
    max_release_drift: float = np.deg2rad(5.0)
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        disk_entity: Any,
        dof: int,
        disk_name: str,
        center,
        radius: float,
        target_angle: float,
        grasp_azimuth: float = 0.0,
        roll_sign: int = 0,
        grasp_radius_scale: float = 1.0,
    ) -> RimRotateResult:
        center = np.asarray(center, dtype=float)
        radius = float(radius)
        # Pinch (and roll) at a fraction of the radius so the pads land on the broad
        # face, not the thin rim edge; the disk-top clearance below still uses full R.
        grip_radius = radius * float(grasp_radius_scale)
        completed: list[str] = []

        start = self._disk_angle(disk_entity, dof)
        sweep = signed_rotation(start, float(target_angle), int(roll_sign))
        quat = ee_quat_for_yaw(controller.default_ee_quat, float(self.grasp_yaw_offset))

        grasp_rim = rim_point_world(center, grip_radius, grasp_azimuth)
        grasp_hand = grasp_rim + np.array([0.0, 0.0, HAND_TO_PAD_Z], dtype=float)
        # The disk is a tall vertical "wall"; the fingers hang ~HAND_TO_PAD_Z below the
        # hand, so the hand must ride above the disk top (center_z + radius) before it
        # moves laterally over the grasp column, or the descending fingers sweep into
        # the disk. Approach = lift straight up -> traverse at safe height -> descend.
        disk_top_z = float(center[2]) + radius
        safe_z = max(
            float(self.approach_z),
            float(grasp_hand[2]),
            disk_top_z + HAND_TO_PAD_Z + float(self.approach_clearance),
        )

        controller.open_gripper(self.gripper_steps)
        completed.append("open")
        self._log("after_open", controller, disk_entity, dof, disk_name)

        cur = controller.hand_pos()
        self._move_linear(
            controller,
            np.array([cur[0], cur[1], safe_z], dtype=float),
            quat=quat,
            start_quat=controller.hand_quat(),
        )
        self._move_linear(
            controller,
            np.array([grasp_hand[0], grasp_hand[1], safe_z], dtype=float),
            quat=quat,
        )
        completed.append("approach")
        self._log("after_approach", controller, disk_entity, dof, disk_name)

        self._move_linear(controller, grasp_hand, quat=quat, steps=max(1, self.steps_move // 2))
        completed.append("descend")
        self._log("after_descend", controller, disk_entity, dof, disk_name)

        grasp_qpos = (
            float(controller.cfg.gripper.closed_qpos)
            if self.grasp_qpos is None
            else float(self.grasp_qpos)
        )
        controller.set_gripper(grasp_qpos, steps=self.gripper_steps)
        completed.append("close")
        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        self._log("after_grasp_settle", controller, disk_entity, dof, disk_name)

        # Sweep the hand along the ideal rim arc; the disk follows from friction.
        max_follow_error = 0.0
        steps_arc = max(1, int(self.steps_arc))
        for step in range(1, steps_arc + 1):
            alpha = 0.5 - 0.5 * np.cos(np.pi * step / steps_arc)
            azimuth = alpha * sweep + float(grasp_azimuth)
            rim = rim_point_world(center, grip_radius, azimuth)
            hand = rim + np.array([0.0, 0.0, HAND_TO_PAD_Z], dtype=float)
            controller.move_ee_to(hand, quat=quat, steps=1, continuous_ik=True)
            pad = controller.hand_pos() - np.array([0.0, 0.0, HAND_TO_PAD_Z], dtype=float)
            max_follow_error = max(max_follow_error, float(np.linalg.norm(rim - pad)))
        completed.append("rotate")
        controller.step(max(0, int(self.arc_settle_steps)))
        completed.append("arc_settle")
        angle_before_release = self._disk_angle(disk_entity, dof)
        self._log("after_arc_settle", controller, disk_entity, dof, disk_name)

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        completed.append("release_settle")

        # Disengage radially OUTWARD along the final grip azimuth first: the open pads
        # slide off past the rim (radial motion applies no torque about the rod), so
        # they don't scrape the disk backward the way a straight-up lift did. Only then
        # lift straight up (now outboard of the disk) to clear the wall.
        theta_end = float(grasp_azimuth) + sweep
        disengage_rim = rim_point_world(center, radius + float(self.retreat_clearance), theta_end)
        disengage_hand = disengage_rim + np.array([0.0, 0.0, HAND_TO_PAD_Z], dtype=float)
        self._move_linear(controller, disengage_hand, quat=quat, steps=max(1, self.steps_move // 2))
        cur = controller.hand_pos()
        self._move_linear(
            controller,
            np.array([cur[0], cur[1], max(safe_z, float(cur[2]) + float(self.retreat_clearance))], dtype=float),
            quat=quat,
            steps=max(1, self.steps_move // 2),
        )
        completed.append("retreat")
        # Read the angle AFTER the full retreat so success reflects the released state
        # (the old pre-retreat read hid the lift-induced drift that broke alignment).
        final_angle = self._disk_angle(disk_entity, dof)
        self._log("after_retreat", controller, disk_entity, dof, disk_name)

        rotation_achieved = float(final_angle - start)
        target_error = abs(_wrap_angle(final_angle - float(target_angle)))
        release_drift = abs(float(final_angle - angle_before_release))
        driven = abs(rotation_achieved) >= float(self.min_rotation)
        success = (
            target_error <= float(self.rotation_tolerance)
            and max_follow_error <= float(self.max_follow_error)
            and release_drift <= float(self.max_release_drift)
        )
        failure_reason = None
        if not success:
            failure_reason = (
                "rim_rotate_check_failed:"
                f" target_error={np.rad2deg(target_error):.2f}deg"
                f" follow_error={max_follow_error:.4f}"
                f" release_drift={np.rad2deg(release_drift):.2f}deg"
                f" driven={driven}"
            )
        return RimRotateResult(
            success=success,
            driven=driven,
            disk_name=str(disk_name),
            start_angle=start,
            target_angle=float(target_angle),
            final_disk_angle=final_angle,
            rotation_achieved=rotation_achieved,
            target_error=target_error,
            max_follow_error=max_follow_error,
            release_drift=release_drift,
            completed_phases=tuple(completed),
            failure_reason=failure_reason,
        )

    def _move_linear(self, controller, target, *, quat, start_quat=None, steps=None) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        steps = max(1, int(self.steps_move if steps is None else steps))
        for step in range(1, steps + 1):
            alpha = 0.5 - 0.5 * np.cos(np.pi * step / steps)
            waypoint = (1.0 - alpha) * start + alpha * target
            waypoint_quat = quat
            if start_quat is not None and quat is not None:
                waypoint_quat = _quat_slerp(start_quat, quat, alpha)
            controller.move_ee_to(waypoint, quat=waypoint_quat, steps=1, continuous_ik=True)

    def _disk_angle(self, entity, dof: int) -> float:
        value = entity.get_dofs_position(dofs_idx_local=[int(dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    def _log(self, label: str, controller, entity, dof, disk_name) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        angle = self._disk_angle(entity, dof)
        print(
            f"[rim_rotate {label:<18}] disk={disk_name}"
            f" hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" disk_angle={np.rad2deg(angle):+.1f}deg",
            flush=True,
        )


def _quat_slerp(start, end, alpha: float) -> np.ndarray:
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    start = start / np.linalg.norm(start)
    end = end / np.linalg.norm(end)
    dot = float(np.dot(start, end))
    if dot < 0.0:
        end = -end
        dot = -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        result = start + float(alpha) * (end - start)
        return result / np.linalg.norm(result)
    theta = float(np.arccos(dot))
    sin_theta = float(np.sin(theta))
    a = float(np.sin((1.0 - float(alpha)) * theta) / sin_theta)
    b = float(np.sin(float(alpha) * theta) / sin_theta)
    return a * start + b * end
