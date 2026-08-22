"""Turn a vertical-axis lever by pinching its knob and sweeping the arc.

The rotate primitive for `diverter_route_ball` (docx 4.3). Pure physics: the
gripper closes on the knob and the joint turns only from finger friction as the
hand follows the knob's ideal arc. No `set_dofs_position` during execution --
the same collision-based contract `RimRotatePrimitive` holds for
`stacked_plate`.

**The joint has no limit, and that is the point.** `stacked_plate`'s disks spin
on a continuous joint too, but there the target is an alignment that the arm can
approach from either side; here the flap's angle decides which branch the ball
can reach, and a limit at the seats would make "turn until it stops" land it
perfectly every time. So `target_error` is a hard check rather than something a
mechanical stop guarantees, and overshoot is a real failure mode.

Why not reuse `RimRotatePrimitive`: its `rim_point_world` puts the disk's face in
the XZ plane with the axis along Y, and its approach rides up over the disk's top
before descending. A knob on a vertical axis is the other orientation entirely --
the hand comes straight down onto it and sweeps a HORIZONTAL arc, and the wrist
has to yaw with the knob because the knob turns with the joint. Sharing the
phase list and the three checks (target error, follow error, release drift) is
worth more than sharing the geometry, which does not transfer.
"""

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


def _wrap_angle(angle: float) -> float:
    """Wrap to (-pi, pi]."""

    return float((float(angle) + np.pi) % (2.0 * np.pi) - np.pi)


def knob_point_world(pivot_xy, radius: float, angle: float, z: float) -> np.ndarray:
    """World point of a lever knob at joint ``angle``.

    The lever arm points along the rotating link's local +x, so the knob sits at
    ``radius`` from the pivot in the direction of the joint angle.
    """

    pivot_xy = np.asarray(pivot_xy, dtype=float).reshape(2)
    return np.array(
        [
            pivot_xy[0] + float(radius) * np.cos(float(angle)),
            pivot_xy[1] + float(radius) * np.sin(float(angle)),
            float(z),
        ],
        dtype=float,
    )


@dataclass(frozen=True)
class PivotLeverResult:
    """Outcome and physical checkpoints from one lever sweep."""

    success: bool
    rotated: bool
    start_angle: float
    target_angle: float
    final_angle: float
    target_error: float
    max_follow_error: float
    max_lag: float
    release_drift: float
    finger_qpos: float
    completed_phases: tuple[str, ...]
    failure_reason: str | None = None


@dataclass(frozen=True)
class PivotLeverPrimitive:
    """Pinch a lever knob and sweep it to a target joint angle."""

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
    retreat_z: float
    steps_per_phase: int
    steps_arc: int
    gripper_steps: int
    grasp_qpos: float
    close_hold_steps: int = 30
    arc_settle_steps: int = 40
    release_hold_steps: int = 30
    target_tolerance: float = np.deg2rad(8.0)
    max_follow_error: float = 0.030
    # How far the joint may lag the hand DURING the sweep. This is the reading
    # that tells carrying from pushing: if the pads hold, the joint tracks the
    # hand's commanded angle; if they slip, the hand runs ahead and the lever is
    # being shoved along rather than carried. The endpoint error cannot see it --
    # a lever that slipped and then caught up ends in the right place.
    max_lag: float = np.deg2rad(6.0)
    max_release_drift: float = np.deg2rad(5.0)
    min_rotation: float = np.deg2rad(2.0)
    min_finger_qpos: float | None = None
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        entity: Any,
        dof: int,
        pivot_xy,
        radius: float,
        grasp_z: float,
        target_angle: float,
    ) -> PivotLeverResult:
        pivot_xy = np.asarray(pivot_xy, dtype=float).reshape(2)
        radius = float(radius)
        grasp_z = float(grasp_z)
        target = float(target_angle)
        completed: list[str] = []

        start = self._angle(entity, dof)
        sweep = _wrap_angle(target - start)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")
        self._log("after_open", controller, entity, dof)

        # Straight down onto the knob: lift to the safe height first, traverse
        # over the knob, then descend. The wrist yaws with the knob, because the
        # knob turns with the joint and the pads have to stay square to its faces.
        quat_at = lambda angle: ee_quat_for_yaw(controller.default_ee_quat, float(angle))
        grasp_hand = knob_point_world(pivot_xy, radius, start, grasp_z + HAND_TO_PAD_Z)
        current = controller.hand_pos()
        self._move(
            controller,
            np.array([current[0], current[1], self.approach_z], dtype=float),
            quat=quat_at(start),
            start_quat=controller.hand_quat(),
        )
        self._move(
            controller,
            np.array([grasp_hand[0], grasp_hand[1], self.approach_z], dtype=float),
            quat=quat_at(start),
        )
        completed.append("approach")
        self._log("after_approach", controller, entity, dof)

        self._move(controller, grasp_hand, quat=quat_at(start),
                   steps=max(1, self.steps_per_phase // 2))
        completed.append("descend")
        self._log("after_descend", controller, entity, dof)

        controller.set_gripper(float(self.grasp_qpos), steps=self.gripper_steps)
        completed.append("close")
        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        finger_qpos = self._finger_qpos(controller)
        self._log("after_grasp_settle", controller, entity, dof)

        # Confirm the grip BEFORE moving the lever. Fingers that stopped short of
        # their command are resting on the handle; fingers that reached it closed
        # on air. Sweeping without checking is what turns a failed grasp into a
        # run that looks like the arm pushing the lever around.
        if self.min_finger_qpos is not None and finger_qpos < float(self.min_finger_qpos):
            controller.open_gripper(self.gripper_steps)
            return PivotLeverResult(
                success=False,
                rotated=False,
                start_angle=start,
                target_angle=target,
                final_angle=self._angle(entity, dof),
                target_error=abs(_wrap_angle(self._angle(entity, dof) - target)),
                max_follow_error=0.0,
                max_lag=0.0,
                release_drift=0.0,
                finger_qpos=finger_qpos,
                completed_phases=tuple(completed),
                failure_reason=(
                    f"grip_not_confirmed: finger_qpos={finger_qpos:.4f} < "
                    f"{float(self.min_finger_qpos):.4f}; not sweeping"
                ),
            )

        # Sweep the hand along the knob's ideal arc; the joint follows from finger
        # friction. Cosine easing so the knob is not jerked at either end.
        follow_error = 0.0
        lag = 0.0
        steps = max(1, int(self.steps_arc))
        for step in range(1, steps + 1):
            alpha = 0.5 - 0.5 * np.cos(np.pi * step / steps)
            angle = start + alpha * sweep
            ideal = knob_point_world(pivot_xy, radius, angle, grasp_z + HAND_TO_PAD_Z)
            controller.move_ee_to(ideal, quat=quat_at(angle), steps=1, continuous_ik=True)
            pad = controller.hand_pos()
            follow_error = max(follow_error, float(np.linalg.norm(ideal - pad)))
            # The joint against where the hand has got to. Growing lag is the pads
            # slipping on the handle.
            lag = max(lag, abs(_wrap_angle(self._angle(entity, dof) - angle)))
        completed.append("rotate")
        controller.step(max(0, int(self.arc_settle_steps)))
        completed.append("arc_settle")
        before_release = self._angle(entity, dof)
        self._log("after_arc_settle", controller, entity, dof)

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        completed.append("release_settle")

        # Straight up and away. The arm must end clear of every camera's line on
        # the fork, because the marble test is what gets watched afterwards.
        current = controller.hand_pos()
        self._move(
            controller,
            np.array([current[0], current[1], self.retreat_z], dtype=float),
            quat=quat_at(target),
            steps=max(1, self.steps_per_phase // 2),
        )
        completed.append("retreat")
        final = self._angle(entity, dof)
        self._log("after_retreat", controller, entity, dof)

        target_error = abs(_wrap_angle(final - target))
        release_drift = abs(_wrap_angle(final - before_release))
        rotated = abs(_wrap_angle(final - start)) >= float(self.min_rotation)
        checks = [
            target_error <= float(self.target_tolerance),
            follow_error <= float(self.max_follow_error),
            lag <= float(self.max_lag),
            release_drift <= float(self.max_release_drift),
        ]
        if self.min_finger_qpos is not None:
            checks.append(finger_qpos >= float(self.min_finger_qpos))
        success = all(checks)
        reason = None
        if not success:
            reason = (
                "pivot_lever_check_failed:"
                f" target_error={np.rad2deg(target_error):.2f}deg"
                f" follow_error={follow_error:.4f}"
                f" max_lag={np.rad2deg(lag):.2f}deg"
                f" release_drift={np.rad2deg(release_drift):.2f}deg"
                f" finger_qpos={finger_qpos:.4f}"
            )
        return PivotLeverResult(
            success=success,
            rotated=rotated,
            start_angle=start,
            target_angle=target,
            final_angle=final,
            target_error=target_error,
            max_follow_error=follow_error,
            max_lag=lag,
            release_drift=release_drift,
            finger_qpos=finger_qpos,
            completed_phases=tuple(completed),
            failure_reason=reason,
        )

    def _move(self, controller, target, *, quat, start_quat=None, steps=None) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        steps = max(1, int(self.steps_per_phase if steps is None else steps))
        for step in range(1, steps + 1):
            alpha = 0.5 - 0.5 * np.cos(np.pi * step / steps)
            waypoint = (1.0 - alpha) * start + alpha * target
            waypoint_quat = quat
            if start_quat is not None and quat is not None:
                waypoint_quat = _quat_slerp(start_quat, quat, alpha)
            controller.move_ee_to(waypoint, quat=waypoint_quat, steps=1, continuous_ik=True)

    def _angle(self, entity, dof: int) -> float:
        value = entity.get_dofs_position(dofs_idx_local=[int(dof)])
        return float(_as_numpy(value).reshape(-1)[0])

    def _finger_qpos(self, controller) -> float:
        """Where the fingers actually stopped -- the evidence that a knob is held.

        Same reasoning as `axial_insert`: with no lift involved, finger travel is
        the only reading that tells "closed on the knob" from "closed on air".
        """

        try:
            qpos = _as_numpy(controller.robot.get_dofs_position()).reshape(-1)
            return float(np.mean(qpos[-2:]))
        except Exception:  # pragma: no cover - controller shape differs
            return float("nan")

    def _log(self, label: str, controller, entity, dof) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        print(
            f"[pivot_lever {label:<18}] hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" flap={np.rad2deg(self._angle(entity, dof)):+.2f}deg",
            flush=True,
        )
