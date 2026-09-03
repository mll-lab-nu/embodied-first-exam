"""Fetch a plate, hold it over a slot, and drop it in when a caller says go.

`PickPlacePrimitive` and `AxialInsertPrimitive` both run start to finish once
called. This motion has a decision in the middle: the arm carries the plate to
the slot mouth and then *waits*, polling a condition every step, and only then
commits to the descent. That wait is the whole task in docx 4.1 -- everything
else is fixed -- so it needs a phase, a timeout, and a failure reason of its own.

The condition is injected as `trigger_fn` rather than computed here: what makes a
moment right is a property of the scene (where the ball is), and this module owns
motion only. `topogym/planning/gate_cage_ball_planner.py` owns the rule.

Three things carried over from `AxialInsertPrimitive`, each of which was a bug
there first:

- **The part is aimed, not the hand.** `slot_part_xy` is where the PLATE has to
  end up. The hand target is derived from the offset measured after the lift,
  because the plate is wherever the grasp actually left it. Aiming a precomputed
  hand pose spent 4.9 mm of a 7 mm budget in that task, and the slot here is
  tighter still at 3 mm a side.
- **The grip must be rigid in the hand's frame.** The caller's attachment needs
  `parent_quat_fn`; without it the plate keeps a fixed world orientation while
  the wrist turns under it.
- **Finger travel is the grasp evidence.** Under an assisted carry the plate
  rises whether or not the pads ever touched it, so `lift_delta` proves nothing
  and `min_finger_qpos` is what separates a grasp from closing on air.
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
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def _entity_quat(entity) -> np.ndarray:
    return _as_numpy(entity.get_quat()).reshape(-1, 4)[0].astype(float)


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


def _plate_yaw(quat) -> float:
    """How far the plate has turned about the vertical, in radians.

    Only yaw matters: the slot constrains the plate in y, so a rotation about z is
    what walks its ends out of the two guide columns. A 126 mm plate yawed by
    theta sweeps 63*sin(theta) at each end, which eats the 3 mm clearance at about
    2.7 degrees.
    """

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


@dataclass(frozen=True)
class GatedInsertResult:
    success: bool
    grasped: bool
    committed: bool
    inserted: bool
    failure_reason: str | None
    finger_qpos: float
    lift_delta: float
    plate_yaw_deg: float
    hover_steps: int
    trigger_reason: str | None
    completed_phases: tuple[str, ...]


@dataclass(frozen=True)
class GatedInsertPrimitive:
    """Pick a plate up, hold it over a slot, insert on a signal, let go, back off."""

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "descend",
        "close",
        "grasp_settle",
        "lift_test",
        "carry",
        "align",
        "hover",
        "insert",
        "insert_settle",
        "release",
        "release_settle",
        "clear",
        "retreat",
    )

    approach_z: float
    grasp_z: float
    carry_z: float
    hover_z: float
    seated_z: float
    clear_z: float
    steps_per_phase: int
    gripper_steps: int
    insert_steps: int
    grasp_qpos: float
    close_hold_steps: int = 30
    insert_settle_steps: int = 30
    release_hold_steps: int = 60
    min_lift_delta: float = 0.010
    min_finger_qpos: float | None = None
    max_plate_yaw: float = float(np.deg2rad(2.0))
    max_hover_steps: int = 900
    verbose: bool = False

    def time_to_station(self, dt: float) -> float:
        """Seconds from the episode's start until the hover phase begins.

        Everything before the wait: opening, reaching, descending, closing,
        settling, lifting, carrying and aligning. Published because the ball is
        released when the episode starts and is therefore already running -- the
        instance is only solvable if its window is still open at this moment.
        """

        moves = 5  # approach, descend, lift, carry, align
        steps = (
            int(self.gripper_steps)
            + moves * int(self.steps_per_phase)
            + int(self.gripper_steps)
            + int(self.close_hold_steps)
        )
        return steps * float(dt)

    def insert_duration(self, dt: float) -> float:
        """Seconds from committing to the descent until the slot is closed.

        Published because the trigger rule needs it and must not guess: the
        deadline it checks the ball against is exactly this number.
        """

        return (int(self.insert_steps) + int(self.insert_settle_steps)) * float(dt)

    def run(
        self,
        controller,
        *,
        plate: Any,
        grasp_xy,
        slot_part_xy,
        retreat_xy,
        ee_quat=None,
        attach_fn: Callable[[], Any] | None = None,
        release_fn: Callable[[], None] | None = None,
        trigger_fn: Callable[[], Any] | None = None,
    ) -> GatedInsertResult:
        grasp_xy = np.asarray(grasp_xy, dtype=float).reshape(2)
        slot_part_xy = np.asarray(slot_part_xy, dtype=float).reshape(2)
        retreat_xy = np.asarray(retreat_xy, dtype=float).reshape(2)
        completed: list[str] = []
        initial_pos = _entity_pos(plate)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")

        approach_target = np.array([grasp_xy[0], grasp_xy[1], self.approach_z], dtype=float)
        self._move(controller, approach_target, quat=ee_quat, start_quat=controller.hand_quat())
        completed.append("approach")

        self._move(
            controller,
            np.array([grasp_xy[0], grasp_xy[1], self.grasp_z], dtype=float),
            quat=ee_quat,
        )
        completed.append("descend")

        controller.set_gripper(float(self.grasp_qpos), steps=self.gripper_steps)
        completed.append("close")
        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        finger_qpos = float(np.min(_as_numpy(controller.gripper_qpos())))

        # Hand over before the lift: the plate is 1.1 kg gripped on a 12 mm edge,
        # which the finger gains do not hold on their own.
        if attach_fn is not None:
            attach_fn()

        self._move(
            controller,
            np.array([grasp_xy[0], grasp_xy[1], self.carry_z], dtype=float),
            quat=ee_quat,
        )
        lift_delta = float(_entity_pos(plate)[2] - initial_pos[2])
        plate_yaw = _plate_yaw(_entity_quat(plate))
        completed.append("lift_test")
        self._log(controller, "lift_test", plate)

        grasped = (
            lift_delta >= float(self.min_lift_delta)
            and abs(plate_yaw) <= float(self.max_plate_yaw)
            and (self.min_finger_qpos is None or finger_qpos >= float(self.min_finger_qpos))
        )
        if not grasped:
            reason = (
                f"grasp_check_failed: lift_delta={lift_delta:.4f} "
                f"plate_yaw={np.rad2deg(plate_yaw):.2f}deg finger_qpos={finger_qpos:.4f}"
            )
            return self._abort(
                controller, plate, reason, completed, finger_qpos, lift_delta, plate_yaw,
                release_fn, ee_quat, approach_target, grasped=False,
            )

        # Where the hand has to be for the PLATE to be over the slot.
        carry_offset_xy = (
            _entity_pos(plate)[:2] - np.asarray(controller.hand_pos(), dtype=float)[:2]
        )
        hand_slot_xy = slot_part_xy - carry_offset_xy

        self._move(
            controller,
            np.array([hand_slot_xy[0], hand_slot_xy[1], self.carry_z], dtype=float),
            quat=ee_quat,
        )
        completed.append("carry")
        self._log(controller, "carry", plate)

        self._move(
            controller,
            np.array([hand_slot_xy[0], hand_slot_xy[1], self.hover_z], dtype=float),
            quat=ee_quat,
        )
        completed.append("align")
        self._log(controller, "align", plate)

        # Hold station and poll. Stepping while stationary is the demonstration of
        # waiting -- the arm is tracking its hover pose, not frozen -- so the frames
        # are ordinary IK tracking rather than a gap in the episode.
        hover_steps = 0
        trigger_reason = None
        while True:
            decision = None if trigger_fn is None else trigger_fn()
            if decision is None or bool(getattr(decision, "commit", bool(decision))):
                trigger_reason = getattr(decision, "reason", "no_trigger_fn")
                break
            if hover_steps >= int(self.max_hover_steps):
                completed.append("hover")
                reason = f"trigger_never_fired: hovered {hover_steps} steps"
                return self._abort(
                    controller, plate, reason, completed, finger_qpos, lift_delta, plate_yaw,
                    release_fn, ee_quat, approach_target, grasped=True,
                )
            controller.move_ee_to(
                np.array([hand_slot_xy[0], hand_slot_xy[1], self.hover_z], dtype=float),
                quat=ee_quat,
                steps=1,
                continuous_ik=True,
            )
            hover_steps += 1
        completed.append("hover")

        self._move(
            controller,
            np.array([hand_slot_xy[0], hand_slot_xy[1], self.seated_z], dtype=float),
            quat=ee_quat,
            steps=self.insert_steps,
        )
        completed.append("insert")
        self._log(controller, "insert", plate)

        controller.step(max(0, int(self.insert_settle_steps)))
        completed.append("insert_settle")

        if release_fn is not None:
            release_fn()
        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        completed.append("release_settle")

        self._move(
            controller,
            np.array([hand_slot_xy[0], hand_slot_xy[1], self.clear_z], dtype=float),
            quat=ee_quat,
        )
        completed.append("clear")
        self._move(
            controller,
            np.array([retreat_xy[0], retreat_xy[1], self.approach_z], dtype=float),
            quat=ee_quat,
        )
        completed.append("retreat")
        self._log(controller, "retreat", plate)

        return GatedInsertResult(
            success=True,
            grasped=True,
            committed=True,
            inserted=True,
            failure_reason=None,
            finger_qpos=finger_qpos,
            lift_delta=lift_delta,
            plate_yaw_deg=float(np.rad2deg(plate_yaw)),
            hover_steps=hover_steps,
            trigger_reason=trigger_reason,
            completed_phases=tuple(completed),
        )

    def _abort(
        self, controller, plate, reason, completed, finger_qpos, lift_delta, plate_yaw,
        release_fn, ee_quat, approach_target, *, grasped: bool,
    ) -> GatedInsertResult:
        """Put the plate down where it will not foul the scene, then back off."""

        if release_fn is not None:
            release_fn()
        controller.open_gripper(self.gripper_steps)
        completed.append("recovery_open")
        self._move(controller, approach_target, quat=ee_quat)
        completed.append("recovery_retreat")
        return GatedInsertResult(
            success=False,
            grasped=grasped,
            committed=False,
            inserted=False,
            failure_reason=reason,
            finger_qpos=finger_qpos,
            lift_delta=lift_delta,
            plate_yaw_deg=float(np.rad2deg(plate_yaw)),
            hover_steps=0,
            trigger_reason=None,
            completed_phases=tuple(completed),
        )

    def _move(self, controller, target, *, quat, start_quat=None, steps=None) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        steps = max(1, int(self.steps_per_phase if steps is None else steps))
        for step in range(1, steps + 1):
            alpha = 0.5 - 0.5 * np.cos(np.pi * step / steps)
            # The orientation rides the same cosine as the position. Handing the
            # solver the final quat on step 1 (a 90 deg turn from home) makes it
            # trade position for orientation: measured 2026-09-03, the hand sank
            # 63 mm below the commanded approach height and tilted 17 deg mid-move,
            # dragging the fingertips through the plate on the rack. Interpolated,
            # the sag is 1.5 mm. Same as AxialInsertPrimitive._move_linear.
            waypoint_quat = quat
            if start_quat is not None and quat is not None:
                waypoint_quat = _quat_slerp(start_quat, quat, alpha)
            controller.move_ee_to(
                (1.0 - alpha) * start + alpha * target,
                quat=waypoint_quat,
                steps=1,
                continuous_ik=True,
            )

    def _log(self, controller, label: str, plate) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        pos = _entity_pos(plate)
        print(
            f"[gated_insert {label:<10}] "
            f"hand=({hand[0]:+.4f}, {hand[1]:+.4f}, {hand[2]:+.4f}) "
            f"plate=({pos[0]:+.4f}, {pos[1]:+.4f}, {pos[2]:+.4f})",
            flush=True,
        )
