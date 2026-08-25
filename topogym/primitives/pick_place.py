from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np


# Vertical offset from the Franka `hand` link origin down to the fingertip pad
# center, derived from the MJCF (left_finger z=0.0584 + pad_z=0.0445).
HAND_TO_PAD_Z: float = 0.1029

# Same origin down to the pad's TIP -- the surface that actually meets the
# object. The fingertip pad is a box of half-height 0.0085 centred at 0.0445 in
# the finger frame (MJCF `fingertip_pad_collision_1`), so the tip is 8.5 mm
# BELOW the centre `HAND_TO_PAD_Z` names. Aiming the centre at a surface buries
# the tip 8.5 mm inside it, which is what put cloth under the table on
# `cloth_unpleat` and `cloth_unroll` before 2026-08-25.
HAND_TO_PAD_TIP_Z: float = 0.1114


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _entity_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


@dataclass(frozen=True)
class PickPlaceResult:
    """Outcome and physical checkpoints from one pick-and-place attempt."""

    success: bool
    grasped: bool
    placed: bool
    failure_reason: str | None
    initial_block_pos: np.ndarray
    lifted_block_pos: np.ndarray
    final_block_pos: np.ndarray
    completed_phases: tuple[str, ...]
    final_object_yaw: float | None = None
    place_yaw_error: float | None = None
    final_object_tilt: float | None = None
    place_tilt_error: float | None = None


@dataclass(frozen=True)
class PickPlacePrimitive:
    """Scripted tabletop pick-and-place built on a FrankaPositionIKController.

    Pure physics: the gripper is the only thing that can move the block. No
    teleport/set_pos shortcuts; whether the grasp succeeds is entirely up to
    contact, friction, and PD-driven gripper force.
    """

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "descend",
        "close",
        "grasp_settle",
        "lift_test",
        "lift_clear",
        "translate",
        "place",
        "place_settle",
        "release",
        "release_settle",
        "retreat",
    )

    approach_z: float
    grasp_z: float
    lift_z: float
    place_z: float
    steps_per_phase: int
    gripper_steps: int
    grasp_qpos: float | None = None
    close_hold_steps: int = 30
    release_hold_steps: int = 20
    release_lift_clearance: float = 0.0
    release_lift_steps: int = 0
    lift_check_delta: float = 0.05
    min_lift_delta: float = 0.025
    max_grasp_xy_error: float = 0.025
    motion_settle_steps: int = 0
    lift_hold_steps: int = 0
    max_lift_drift: float = float("inf")
    place_hold_steps: int = 0
    place_tolerance_xy: float = 0.045
    place_tolerance_z: float = 0.03
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        block: Any,
        source_xy,
        target_xy,
        ee_quat=None,
        target_ee_quat=None,
        target_object_yaw: float | None = None,
        target_object_z: float | None = None,
        place_tolerance_yaw: float | None = None,
        place_tolerance_tilt: float | None = None,
        place_yaw_period: float = 2.0 * np.pi,
        placement_target_xy=None,
    ) -> PickPlaceResult:
        source_xy = np.asarray(source_xy, dtype=float)
        target_xy = np.asarray(target_xy, dtype=float)
        placement_target_xy = (
            target_xy
            if placement_target_xy is None
            else np.asarray(placement_target_xy, dtype=float)
        )
        target_ee_quat = ee_quat if target_ee_quat is None else target_ee_quat
        completed: list[str] = []
        initial_block_pos = _entity_pos(block)

        self._log("start", controller, block, target=None)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")
        self._log("after_open", controller, block, target=None)

        approach_target = [source_xy[0], source_xy[1], self.approach_z]
        self._move_linear(
            controller,
            approach_target,
            start_quat=controller.hand_quat(),
            quat=ee_quat,
        )
        completed.append("approach")
        self._log("after_approach", controller, block, target=approach_target)

        grasp_target = [source_xy[0], source_xy[1], self.grasp_z]
        self._move_linear(controller, grasp_target, quat=ee_quat)
        completed.append("descend")
        self._log("after_descend", controller, block, target=grasp_target)

        grasp_qpos = (
            float(controller.cfg.gripper.closed_qpos)
            if self.grasp_qpos is None
            else float(self.grasp_qpos)
        )
        controller.set_gripper(grasp_qpos, steps=self.gripper_steps)
        completed.append("close")
        self._log("after_close", controller, block, target=None)

        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        self._log("after_grasp_settle", controller, block, target=None)

        lift_check_z = min(
            float(self.lift_z),
            float(self.grasp_z) + max(float(self.lift_check_delta), float(self.min_lift_delta)),
        )
        lift_check_target = [source_xy[0], source_xy[1], lift_check_z]
        self._move_linear(controller, lift_check_target, quat=ee_quat)
        completed.append("lift_test")
        lifted_block_pos = _entity_pos(block)
        self._log("after_lift_test", controller, block, target=lift_check_target)

        lift_delta = float(lifted_block_pos[2] - initial_block_pos[2])
        grasp_xy_error = float(np.linalg.norm(lifted_block_pos[:2] - source_xy[:2]))
        controller.step(max(0, int(self.lift_hold_steps)))
        stable_block_pos = _entity_pos(block)
        lift_drift = float(np.linalg.norm(stable_block_pos - lifted_block_pos))
        lifted_block_pos = stable_block_pos
        grasped = (
            lift_delta >= float(self.min_lift_delta)
            and grasp_xy_error <= float(self.max_grasp_xy_error)
            and lift_drift <= float(self.max_lift_drift)
        )
        if not grasped:
            failure_reason = (
                "lift_check_failed:"
                f" lift_delta={lift_delta:.4f}"
                f" grasp_xy_error={grasp_xy_error:.4f}"
                f" lift_drift={lift_drift:.4f}"
            )
            controller.open_gripper(self.gripper_steps)
            completed.append("recovery_open")
            self._move_linear(controller, approach_target, quat=ee_quat)
            completed.append("recovery_retreat")
            final_block_pos = _entity_pos(block)
            self._log("grasp_failed", controller, block, target=None)
            return PickPlaceResult(
                success=False,
                grasped=False,
                placed=False,
                failure_reason=failure_reason,
                initial_block_pos=initial_block_pos,
                lifted_block_pos=lifted_block_pos,
                final_block_pos=final_block_pos,
                completed_phases=tuple(completed),
            )

        lift_source_target = [source_xy[0], source_xy[1], self.lift_z]
        self._move_linear(controller, lift_source_target, quat=ee_quat)
        completed.append("lift_clear")
        self._log("after_lift_source", controller, block, target=lift_source_target)

        lift_target_target = [target_xy[0], target_xy[1], self.lift_z]
        self._move_linear(
            controller,
            lift_target_target,
            start_quat=ee_quat,
            quat=target_ee_quat,
        )
        completed.append("translate")
        self._log("after_translate", controller, block, target=lift_target_target)

        place_target = [target_xy[0], target_xy[1], self.place_z]
        self._move_linear(controller, place_target, quat=target_ee_quat)
        completed.append("place")
        self._log("after_place", controller, block, target=place_target)

        controller.step(max(0, int(self.place_hold_steps)))
        completed.append("place_settle")
        self._log("after_place_settle", controller, block, target=place_target)

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        self._log("after_release", controller, block, target=None)

        controller.step(max(0, int(self.release_hold_steps)))
        completed.append("release_settle")

        if float(self.release_lift_clearance) > 0.0:
            release_lift_target = [
                target_xy[0],
                target_xy[1],
                min(float(self.lift_z), float(self.place_z) + float(self.release_lift_clearance)),
            ]
            self._move_linear(
                controller,
                release_lift_target,
                quat=target_ee_quat,
                steps=max(1, int(self.release_lift_steps)),
            )
            completed.append("release_lift")
            self._log("after_release_lift", controller, block, target=release_lift_target)

        retreat_target = [target_xy[0], target_xy[1], self.lift_z]
        self._move_linear(controller, retreat_target, quat=target_ee_quat)
        completed.append("retreat")
        self._log("after_retreat", controller, block, target=retreat_target)

        final_block_pos = _entity_pos(block)
        place_xy_error = float(
            np.linalg.norm(final_block_pos[:2] - placement_target_xy[:2])
        )
        expected_object_z = (
            float(initial_block_pos[2])
            if target_object_z is None
            else float(target_object_z)
        )
        place_z_error = abs(float(final_block_pos[2] - expected_object_z))
        final_object_yaw = _entity_yaw(block)
        final_object_tilt = _entity_tilt(block)
        place_yaw_error = None
        place_tilt_error = None
        yaw_ok = True
        tilt_ok = True
        if (
            target_object_yaw is not None
            and place_tolerance_yaw is not None
            and final_object_yaw is not None
        ):
            place_yaw_error = abs(
                _periodic_angle_delta(
                    final_object_yaw,
                    float(target_object_yaw),
                    float(place_yaw_period),
                )
            )
            yaw_ok = place_yaw_error <= float(place_tolerance_yaw)
        if place_tolerance_tilt is not None and final_object_tilt is not None:
            place_tilt_error = abs(float(final_object_tilt))
            tilt_ok = place_tilt_error <= float(place_tolerance_tilt)
        placed = (
            place_xy_error <= float(self.place_tolerance_xy)
            and place_z_error <= float(self.place_tolerance_z)
            and yaw_ok
            and tilt_ok
        )
        failure_reason = None
        if not placed:
            failure_reason = (
                "placement_check_failed:"
                f" place_xy_error={place_xy_error:.4f}"
                f" place_z_error={place_z_error:.4f}"
                f" place_yaw_error={place_yaw_error}"
                f" place_tilt_error={place_tilt_error}"
            )
        return PickPlaceResult(
            success=placed,
            grasped=True,
            placed=placed,
            failure_reason=failure_reason,
            initial_block_pos=initial_block_pos,
            lifted_block_pos=lifted_block_pos,
            final_block_pos=final_block_pos,
            completed_phases=tuple(completed),
            final_object_yaw=final_object_yaw,
            place_yaw_error=place_yaw_error,
            final_object_tilt=final_object_tilt,
            place_tilt_error=place_tilt_error,
        )

    def _move_linear(self, controller, target, *, quat, start_quat=None, steps=None) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        steps = max(1, int(self.steps_per_phase if steps is None else steps))
        for step in range(1, steps + 1):
            progress = step / steps
            alpha = 0.5 - 0.5 * np.cos(np.pi * progress)
            waypoint = (1.0 - alpha) * start + alpha * target
            waypoint_quat = quat
            if start_quat is not None and quat is not None:
                waypoint_quat = _quat_slerp(start_quat, quat, alpha)
            controller.move_ee_to(
                waypoint,
                quat=waypoint_quat,
                steps=1,
                continuous_ik=True,
            )
        controller.step(max(0, int(self.motion_settle_steps)))

    def _log(self, label: str, controller, block, *, target) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        gripper_qpos = controller.gripper_qpos()
        block_pos = _entity_pos(block)
        pad_z = float(hand[2]) - HAND_TO_PAD_Z
        target_str = (
            f" target=({target[0]:+.3f},{target[1]:+.3f},{target[2]:+.3f})"
            if target is not None
            else ""
        )
        print(
            f"[pick_place {label:<18}]{target_str}"
            f" hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" pad_z={pad_z:+.3f}"
            f" finger_q=({gripper_qpos[0]:.4f},{gripper_qpos[1]:.4f})"
            f" block=({block_pos[0]:+.3f},{block_pos[1]:+.3f},{block_pos[2]:+.3f})",
            flush=True,
        )


def _entity_yaw(entity) -> float | None:
    get_quat = getattr(entity, "get_quat", None)
    if get_quat is None:
        return None
    quat = _as_numpy(get_quat()).reshape(-1, 4)[0].astype(float)
    w, x, y, z = quat
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def _entity_tilt(entity) -> float | None:
    get_quat = getattr(entity, "get_quat", None)
    if get_quat is None:
        return None
    quat = _as_numpy(get_quat()).reshape(-1, 4)[0].astype(float)
    norm = float(np.linalg.norm(quat))
    if norm <= 1e-8:
        return None
    _, x, y, _ = quat / norm
    local_z_world_z = 1.0 - 2.0 * (x * x + y * y)
    return float(np.arccos(np.clip(local_z_world_z, -1.0, 1.0)))


def _periodic_angle_delta(angle: float, target: float, period: float) -> float:
    period = float(period)
    if period <= 0.0:
        raise ValueError(f"period must be positive, got {period}.")
    return float((float(angle) - float(target) + 0.5 * period) % period - 0.5 * period)


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
