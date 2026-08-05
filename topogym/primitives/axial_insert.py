"""Grasp a held part and push it along a fixed axis into a receptacle.

`PickPlacePrimitive` does not cover this motion: its `translate` happens at
carry height *before* `place`, and `place` is a pure vertical descend, so there
is no horizontal insertion phase; and it has no post-release horizontal
withdraw, so an episode would end with the open gripper still in the aperture.

Assisted grasp: this primitive carries the part with the repo's existing
`topogym/primitives/attachment.py` rather than relying on finger friction. The
part is gripped well behind its centre of mass (the hand has to stop short of
the receptacle), so the pads see a pure moment that the Franka's finger gains
(kp=100) cannot hold. Attaching is a declared kinematic event under
`docs/develop/visual/physical_realism_guidelines_zh.md` P1/P4 -- the caller MUST
print `runtime_attachment=True` in its IL contract line.

The attachment is injected as two callbacks rather than constructed here, so
this module owns motion only and the caller owns the `AttachmentManager`
lifetime (it wraps `scene.step`, so it has to span the whole episode).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ClassVar

import numpy as np


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _entity_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0]


def _entity_quat(entity) -> np.ndarray:
    return _as_numpy(entity.get_quat()).reshape(-1, 4)[0]


def _quat_slerp(start, end, alpha: float) -> np.ndarray:
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    start = start / np.linalg.norm(start)
    end = end / np.linalg.norm(end)
    dot = float(np.dot(start, end))
    if dot < 0.0:
        end = -end
        dot = -dot
    if dot > 0.9995:
        result = start + float(alpha) * (end - start)
        return result / np.linalg.norm(result)
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    sin_theta = np.sin(theta)
    return (
        np.sin((1.0 - float(alpha)) * theta) / sin_theta * start
        + np.sin(float(alpha) * theta) / sin_theta * end
    )


def _axis_tilt(quat, reference) -> float:
    """Angle between a cylinder's local +z axis and ``reference``."""

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    axis = np.array(
        [2.0 * (x * z + w * y), 2.0 * (y * z - w * x), 1.0 - 2.0 * (x * x + y * y)],
        dtype=float,
    )
    norm = float(np.linalg.norm(axis))
    if norm < 1e-12:
        return 0.0
    axis = axis / norm
    reference = np.asarray(reference, dtype=float)
    reference = reference / np.linalg.norm(reference)
    return float(np.arccos(np.clip(abs(float(np.dot(axis, reference))), -1.0, 1.0)))


@dataclass(frozen=True)
class AxialInsertResult:
    success: bool
    grasped: bool
    inserted: bool
    failure_reason: str | None
    initial_part_pos: np.ndarray
    lifted_part_pos: np.ndarray
    final_part_pos: np.ndarray
    lift_delta: float
    lift_tilt: float
    align_tilt: float
    completed_phases: tuple[str, ...]


@dataclass(frozen=True)
class AxialInsertPrimitive:
    """Pick a part up, carry it to an insertion axis, push it in, let go, back off."""

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "descend",
        "close",
        "grasp_settle",
        "lift_test",
        "align",
        "insert",
        "insert_settle",
        "seat",
        "release",
        "release_settle",
        "clear",
        "withdraw",
        "retreat",
    )

    approach_z: float
    grasp_z: float
    lift_z: float
    insert_z: float
    seat_z: float
    clear_z: float
    steps_per_phase: int
    gripper_steps: int
    grasp_qpos: float | None = None
    close_hold_steps: int = 30
    insert_settle_steps: int = 30
    release_hold_steps: int = 100
    motion_settle_steps: int = 0
    min_lift_delta: float = 0.025
    # The dominant failure here is rotational, not translational: a part that
    # droops in the pads still lifts, then jams the receptacle mouth. So the
    # grasp gate reads tilt as well as rise.
    max_grasp_tilt: float = float(np.deg2rad(2.0))
    max_grasp_xy_error: float = 0.025
    insert_steps: int | None = None
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        part: Any,
        grasp_xy,
        insert_xy,
        retreat_xy,
        part_axis=(1.0, 0.0, 0.0),
        ee_quat=None,
        attach_fn: Callable[[], Any] | None = None,
        release_fn: Callable[[], None] | None = None,
    ) -> AxialInsertResult:
        grasp_xy = np.asarray(grasp_xy, dtype=float).reshape(2)
        insert_xy = np.asarray(insert_xy, dtype=float).reshape(2)
        retreat_xy = np.asarray(retreat_xy, dtype=float).reshape(2)
        part_axis = np.asarray(part_axis, dtype=float).reshape(3)
        completed: list[str] = []
        initial_part_pos = _entity_pos(part)
        grasp_offset_xy = initial_part_pos[:2] - grasp_xy

        controller.open_gripper(self.gripper_steps)
        completed.append("open")

        approach_target = np.array([grasp_xy[0], grasp_xy[1], self.approach_z], dtype=float)
        self._move_linear(
            controller, approach_target, quat=ee_quat, start_quat=controller.hand_quat()
        )
        completed.append("approach")
        self._log(controller, "approach", approach_target, part)

        grasp_target = np.array([grasp_xy[0], grasp_xy[1], self.grasp_z], dtype=float)
        self._move_linear(controller, grasp_target, quat=ee_quat)
        completed.append("descend")

        grasp_qpos = (
            float(controller.cfg.gripper.closed_qpos)
            if self.grasp_qpos is None
            else float(self.grasp_qpos)
        )
        controller.set_gripper(grasp_qpos, steps=self.gripper_steps)
        completed.append("close")

        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")

        # Hand the part over before the lift: the pads cannot hold the moment on
        # their own, so the attachment has to be live for the very first move
        # that carries weight.
        attachment = attach_fn() if attach_fn is not None else None

        lift_target = np.array([grasp_xy[0], grasp_xy[1], self.lift_z], dtype=float)
        self._move_linear(controller, lift_target, quat=ee_quat)
        lifted_part_pos = _entity_pos(part)
        lift_delta = float(lifted_part_pos[2] - initial_part_pos[2])
        lift_tilt = _axis_tilt(_entity_quat(part), part_axis)
        grasp_xy_error = float(
            np.linalg.norm(lifted_part_pos[:2] - (grasp_xy + grasp_offset_xy))
        )
        completed.append("lift_test")
        self._log(controller, "lift_test", lift_target, part)

        grasped = (
            lift_delta >= float(self.min_lift_delta)
            and lift_tilt <= float(self.max_grasp_tilt)
            and grasp_xy_error <= float(self.max_grasp_xy_error)
        )
        if not grasped:
            reason = (
                f"grasp_check_failed: lift_delta={lift_delta:.4f} "
                f"lift_tilt={np.rad2deg(lift_tilt):.2f}deg "
                f"grasp_xy_error={grasp_xy_error:.4f}"
            )
            if release_fn is not None:
                release_fn()
            controller.open_gripper(self.gripper_steps)
            completed.append("recovery_open")
            self._move_linear(controller, approach_target, quat=ee_quat)
            completed.append("recovery_retreat")
            return AxialInsertResult(
                success=False,
                grasped=False,
                inserted=False,
                failure_reason=reason,
                initial_part_pos=initial_part_pos,
                lifted_part_pos=lifted_part_pos,
                final_part_pos=_entity_pos(part),
                lift_delta=lift_delta,
                lift_tilt=lift_tilt,
                align_tilt=lift_tilt,
                completed_phases=tuple(completed),
            )

        # Align laterally and to the insertion height while still clear of the
        # receptacle, so `insert` stays a single-axis push.
        align_target = np.array([grasp_xy[0], insert_xy[1], self.insert_z], dtype=float)
        self._move_linear(controller, align_target, quat=ee_quat)
        align_tilt = _axis_tilt(_entity_quat(part), part_axis)
        completed.append("align")
        self._log(controller, "align", align_target, part)

        insert_target = np.array([insert_xy[0], insert_xy[1], self.insert_z], dtype=float)
        self._move_linear(
            controller,
            insert_target,
            quat=ee_quat,
            steps=self.insert_steps if self.insert_steps is not None else self.steps_per_phase,
        )
        completed.append("insert")
        self._log(controller, "insert", insert_target, part)

        controller.step(max(0, int(self.insert_settle_steps)))
        completed.append("insert_settle")

        seat_target = np.array([insert_xy[0], insert_xy[1], self.seat_z], dtype=float)
        self._move_linear(controller, seat_target, quat=ee_quat)
        completed.append("seat")

        if release_fn is not None:
            release_fn()
        controller.open_gripper(self.gripper_steps)
        completed.append("release")

        controller.step(max(0, int(self.release_hold_steps)))
        completed.append("release_settle")

        clear_target = np.array([insert_xy[0], insert_xy[1], self.clear_z], dtype=float)
        self._move_linear(controller, clear_target, quat=ee_quat)
        completed.append("clear")

        withdraw_target = np.array([retreat_xy[0], retreat_xy[1], self.clear_z], dtype=float)
        self._move_linear(controller, withdraw_target, quat=ee_quat)
        completed.append("withdraw")

        retreat_target = np.array([retreat_xy[0], retreat_xy[1], self.approach_z], dtype=float)
        self._move_linear(controller, retreat_target, quat=ee_quat)
        completed.append("retreat")

        final_part_pos = _entity_pos(part)
        self._log(controller, "retreat", retreat_target, part)
        del attachment  # lifetime belongs to the caller's AttachmentManager

        return AxialInsertResult(
            success=True,
            grasped=True,
            inserted=True,
            failure_reason=None,
            initial_part_pos=initial_part_pos,
            lifted_part_pos=lifted_part_pos,
            final_part_pos=final_part_pos,
            lift_delta=lift_delta,
            lift_tilt=lift_tilt,
            align_tilt=align_tilt,
            completed_phases=tuple(completed),
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
            controller.move_ee_to(waypoint, quat=waypoint_quat, steps=1, continuous_ik=True)
        controller.step(max(0, int(self.motion_settle_steps)))

    def _log(self, controller, label: str, target, part) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        part_pos = _entity_pos(part)
        print(
            f"[axial_insert {label}] "
            f"target=({target[0]:.4f}, {target[1]:.4f}, {target[2]:.4f}) "
            f"hand=({hand[0]:.4f}, {hand[1]:.4f}, {hand[2]:.4f}) "
            f"part=({part_pos[0]:.4f}, {part_pos[1]:.4f}, {part_pos[2]:.4f})",
            flush=True,
        )
