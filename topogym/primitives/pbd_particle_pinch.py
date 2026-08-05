from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from .pick_place import HAND_TO_PAD_Z


def _ease(alpha: float) -> float:
    alpha = float(np.clip(alpha, 0.0, 1.0))
    return 0.5 - 0.5 * float(np.cos(np.pi * alpha))


@dataclass(frozen=True)
class PBDCornerLiftResult:
    success: bool
    initial_corner_pos: np.ndarray
    final_corner_pos: np.ndarray
    lift_delta: float
    xy_displacement: float


@dataclass(frozen=True)
class PBDCornerLiftPrimitive:
    """Use a closed fingertip pair to sweep a flat free corner off its edge."""

    approach_z: float
    press_clearance: float
    start_inset: float
    sweep_distance: float
    sweep_lift: float
    move_steps: int
    gripper_steps: int
    tool_qpos: float
    hold_steps: int = 20
    motion_settle_steps: int = 10
    min_lift_delta: float = 0.004
    min_xy_displacement: float = 0.010
    verbose: bool = False
    debug_stop_after: str | None = None

    def run(
        self,
        controller,
        *,
        grasp_point,
        outward_direction,
        before_sweep=None,
        ee_quat=None,
    ) -> PBDCornerLiftResult:
        outward = np.asarray(outward_direction, dtype=float)
        outward = outward / max(float(np.linalg.norm(outward)), 1e-8)
        initial = np.asarray(grasp_point(), dtype=float)
        self._log_phase(
            "start",
            initial=initial.tolist(),
            outward=outward.tolist(),
            tool_qpos=float(self.tool_qpos),
        )
        controller.set_gripper(
            float(self.tool_qpos),
            steps=self.gripper_steps,
        )
        self._log_phase("after_tool_close", hand=controller.hand_pos().tolist())
        self._maybe_stop("corner_close")

        press = initial.copy()
        press[:2] -= outward[:2] * float(self.start_inset)
        press[2] += float(self.press_clearance)
        approach_hand = press.copy()
        approach_hand[2] = max(
            float(self.approach_z),
            float(press[2] + HAND_TO_PAD_Z + 0.05),
        )
        self._move_hand(
            controller,
            approach_hand,
            steps=self.move_steps,
            quat=ee_quat,
            rotate_from_current=True,
        )
        self._log_phase(
            "after_approach",
            target=approach_hand.tolist(),
            hand=controller.hand_pos().tolist(),
        )
        self._maybe_stop("corner_approach")
        self._move_hand(
            controller,
            press + np.array([0.0, 0.0, HAND_TO_PAD_Z]),
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
        )
        self._log_phase(
            "after_descend",
            target=(press + np.array([0.0, 0.0, HAND_TO_PAD_Z])).tolist(),
            hand=controller.hand_pos().tolist(),
            corner=np.asarray(grasp_point(), dtype=float).tolist(),
        )
        self._maybe_stop("corner_descend")
        if before_sweep is not None:
            self._log_phase("before_release")
            before_sweep()
            self._log_phase("after_release")
        self._maybe_stop("corner_release")

        sweep = press.copy()
        sweep[:2] += outward[:2] * float(self.sweep_distance)
        sweep[2] += float(self.sweep_lift)
        self._move_hand(
            controller,
            sweep + np.array([0.0, 0.0, HAND_TO_PAD_Z]),
            steps=self.move_steps,
            quat=ee_quat,
        )
        self._log_phase(
            "after_sweep",
            target=(sweep + np.array([0.0, 0.0, HAND_TO_PAD_Z])).tolist(),
            hand=controller.hand_pos().tolist(),
            corner=np.asarray(grasp_point(), dtype=float).tolist(),
        )
        self._maybe_stop("corner_sweep")
        controller.step(max(0, int(self.hold_steps)))
        final = np.asarray(grasp_point(), dtype=float)
        lift_delta = float(final[2] - initial[2])
        xy_displacement = float(np.linalg.norm(final[:2] - initial[:2]))
        success = bool(
            lift_delta >= float(self.min_lift_delta)
            or xy_displacement >= float(self.min_xy_displacement)
        )
        if self.verbose:
            print(
                "[pbd_corner_lift result]"
                f" success={success}"
                f" initial={initial.tolist()}"
                f" final={final.tolist()}"
                f" lift_delta={lift_delta:.4f}"
                f" xy_displacement={xy_displacement:.4f}",
                flush=True,
            )

        controller.open_gripper(self.gripper_steps)
        retreat = controller.hand_pos()
        retreat[2] = max(float(self.approach_z), float(retreat[2]) + 0.06)
        self._move_hand(
            controller,
            retreat,
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
        )
        return PBDCornerLiftResult(
            success=success,
            initial_corner_pos=initial,
            final_corner_pos=final,
            lift_delta=lift_delta,
            xy_displacement=xy_displacement,
        )

    def _log_phase(self, label: str, **items) -> None:
        if not self.verbose:
            return
        suffix = " ".join(f"{key}={value}" for key, value in items.items())
        print(f"[pbd_corner_lift {label}] {suffix}", flush=True)

    def _maybe_stop(self, marker: str) -> None:
        if self.debug_stop_after == marker:
            raise SystemExit(
                f"peeling debug stop reached after {marker}"
            )

    def _move_hand(
        self,
        controller,
        target,
        *,
        steps: int,
        quat,
        rotate_from_current: bool = False,
    ) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        start_quat = controller.hand_quat() if rotate_from_current else None
        steps = max(1, int(steps))
        for step in range(1, steps + 1):
            alpha = _ease(step / steps)
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


@dataclass(frozen=True)
class PBDParticlePinchResult:
    success: bool
    grasped: bool
    released: bool
    failure_reason: str | None
    initial_grasp_pos: np.ndarray
    lifted_grasp_pos: np.ndarray
    final_grasp_pos: np.ndarray
    completed_phases: tuple[str, ...]
    completed_segments: tuple[str, ...] = ()
    segment_follow_errors: tuple[float, ...] = ()


@dataclass(frozen=True)
class PBDParticleAttachmentDragPrimitive:
    """Attach a touched PBD particle group to the hand and drag it kinematically.

    This is a suction/sticky-contact approximation. It intentionally avoids
    rigid finger-to-cloth contact, which is fragile in Genesis 1.1.0 for the
    flat Peeling setup.
    """

    approach_z: float
    touch_clearance: float
    lift_delta: float
    move_steps: int
    gripper_steps: int
    attach_tolerance: float
    # Optional cosmetic close: with None (the Peeling default) the gripper stays
    # open the whole time, which is honest for a suction approximation but reads
    # as "the hand never touched it" when the held thing is a rope. Set it to
    # slightly more than half the rope's diameter and the fingers bracket the
    # rope without squeezing it -- the hold stays kinematic, so finger contact
    # never fights the weld.
    grasp_qpos: float | None = None
    motion_settle_steps: int = 20
    max_follow_error: float = 0.045
    max_segment_follow_error: float | None = None
    release_hold_steps: int = 30
    verbose: bool = False
    debug_stop_after: str | None = None

    def run(
        self,
        controller,
        *,
        grasp_point,
        grasp_particles=None,
        set_grasp_particles=None,
        set_attached_sheet=None,
        target_centers,
        target_steps=None,
        segment_labels=None,
        on_attach=None,
        on_segment_start=None,
        on_segment_complete=None,
        before_release=None,
        ee_quat=None,
    ) -> PBDParticlePinchResult:
        targets = [np.asarray(target, dtype=float) for target in target_centers]
        if not targets:
            raise ValueError(
                "PBDParticleAttachmentDragPrimitive requires at least one target."
            )
        if set_attached_sheet is None and (
            grasp_particles is None or set_grasp_particles is None
        ):
            raise ValueError(
                "PBDParticleAttachmentDragPrimitive requires either "
                "set_attached_sheet or both grasp_particles and "
                "set_grasp_particles."
            )
        if target_steps is None:
            steps = [int(self.move_steps)] * len(targets)
        else:
            steps = [max(1, int(value)) for value in target_steps]
            if len(steps) != len(targets):
                raise ValueError("target_steps must match target_centers.")
        if segment_labels is None:
            labels = [
                f"segment_{index + 1:02d}" for index in range(len(targets))
            ]
        else:
            labels = [str(value) for value in segment_labels]
            if len(labels) != len(targets):
                raise ValueError("segment_labels must match target_centers.")

        completed: list[str] = []
        completed_segments: list[str] = []
        segment_follow_errors: list[float] = []
        initial_pos = np.asarray(grasp_point(), dtype=float)
        self._log("start", controller, initial_pos)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")

        touch_hand = self._hand_for_grasp(initial_pos)
        approach_hand = touch_hand.copy()
        approach_hand[2] = max(float(self.approach_z), touch_hand[2] + 0.06)
        self._move_hand(
            controller,
            approach_hand,
            steps=self.move_steps,
            quat=ee_quat,
            rotate_from_current=True,
        )
        completed.append("approach")
        self._maybe_stop("attach_approach")

        self._move_hand(
            controller,
            touch_hand,
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
        )
        completed.append("touch")
        attach_center = self._grasp_for_hand(controller.hand_pos())
        attach_error = float(np.linalg.norm(attach_center - grasp_point()))
        self._log(
            "after_touch",
            controller,
            grasp_point(),
            extra=f" attach_error={attach_error:.4f}",
        )
        if attach_error > float(self.attach_tolerance):
            controller.open_gripper(self.gripper_steps)
            completed.append("attach_failed_open")
            self._retreat(controller, quat=ee_quat)
            completed.append("attach_failed_retreat")
            final_pos = np.asarray(grasp_point(), dtype=float)
            return PBDParticlePinchResult(
                success=False,
                grasped=False,
                released=True,
                failure_reason=(
                    "attach_check_failed:"
                    f" attach_error={attach_error:.4f}"
                    f" tolerance={float(self.attach_tolerance):.4f}"
                ),
                initial_grasp_pos=initial_pos,
                lifted_grasp_pos=final_pos,
                final_grasp_pos=final_pos,
                completed_phases=tuple(completed),
                completed_segments=tuple(completed_segments),
                segment_follow_errors=tuple(segment_follow_errors),
            )
        self._maybe_stop("attach_touch")

        particle_offsets = None
        if set_attached_sheet is None:
            particle_offsets = np.asarray(
                grasp_particles(),
                dtype=float,
            ) - np.asarray(
                grasp_point(),
                dtype=float,
            )
        if self.grasp_qpos is not None:
            controller.set_gripper(float(self.grasp_qpos), steps=self.gripper_steps)
            completed.append("close")
        # Weld where the material actually IS, not where the hand is. The drive
        # below commands the group centre to the hand's pad position; without
        # this offset the group is teleported by the whole attach error on the
        # first sync -- a 13 mm jump in one 10 ms step is 1.3 m/s handed to a
        # short band whose neighbours are at rest, which is enough to blow up a
        # stiff PBD body. Carrying the offset makes the group follow the hand's
        # *motion* while keeping its own position.
        attach_offset = np.asarray(grasp_point(), dtype=float) - self._grasp_for_hand(
            controller.hand_pos()
        )
        if on_attach is not None:
            on_attach()
        completed.append("attach")

        lift_hand = controller.hand_pos().copy()
        lift_hand[2] += float(self.lift_delta)
        self._move_hand(
            controller,
            lift_hand,
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
            attached=True,
            particle_offsets=particle_offsets,
            set_grasp_particles=set_grasp_particles,
            set_attached_sheet=set_attached_sheet,
            attach_offset=attach_offset,
        )
        completed.append("lift_test")
        lifted_pos = np.asarray(grasp_point(), dtype=float)
        lift_amount = float(lifted_pos[2] - initial_pos[2])
        follow_error = self._follow_error(controller, lifted_pos)
        grasped = bool(
            lift_amount >= float(self.lift_delta) * 0.5
            and follow_error <= float(self.max_follow_error)
        )
        self._log(
            "after_lift",
            controller,
            lifted_pos,
            extra=(
                f" lift_delta={lift_amount:.4f}"
                f" follow_error={follow_error:.4f}"
            ),
        )
        if not grasped:
            controller.open_gripper(self.gripper_steps)
            completed.append("recovery_open")
            self._retreat(controller, quat=ee_quat)
            completed.append("recovery_retreat")
            final_pos = np.asarray(grasp_point(), dtype=float)
            return PBDParticlePinchResult(
                success=False,
                grasped=False,
                released=True,
                failure_reason=(
                    "attachment_lift_check_failed:"
                    f" lift_delta={lift_amount:.4f}"
                    f" follow_error={follow_error:.4f}"
                ),
                initial_grasp_pos=initial_pos,
                lifted_grasp_pos=lifted_pos,
                final_grasp_pos=final_pos,
                completed_phases=tuple(completed),
                completed_segments=tuple(completed_segments),
                segment_follow_errors=tuple(segment_follow_errors),
            )
        self._maybe_stop("attach_lift")

        follow_limit = (
            float(self.max_follow_error)
            if self.max_segment_follow_error is None
            else float(self.max_segment_follow_error)
        )
        for index, (label, target, segment_steps) in enumerate(
            zip(labels, targets, steps),
            start=1,
        ):
            if on_segment_start is not None:
                on_segment_start(index, len(targets), label, target.copy())
            target_hand = self._hand_for_grasp(target)
            self._move_hand(
                controller,
                target_hand,
                steps=segment_steps,
                quat=ee_quat,
                attached=True,
                particle_offsets=particle_offsets,
                set_grasp_particles=set_grasp_particles,
                set_attached_sheet=set_attached_sheet,
                attach_offset=attach_offset,
            )
            grasp_pos = np.asarray(grasp_point(), dtype=float)
            follow_error = self._follow_error(controller, grasp_pos)
            target_error = float(np.linalg.norm(grasp_pos - target))
            completed_segments.append(label)
            segment_follow_errors.append(follow_error)
            self._log_segment(
                label,
                index=index,
                total=len(targets),
                grasp_pos=grasp_pos,
                follow_error=follow_error,
                target_error=target_error,
            )
            if on_segment_complete is not None:
                on_segment_complete(
                    index,
                    len(targets),
                    label,
                    target.copy(),
                    grasp_pos.copy(),
                    follow_error,
                    target_error,
                )
            if follow_error > follow_limit:
                controller.open_gripper(self.gripper_steps)
                completed.append("recovery_open")
                self._retreat(controller, quat=ee_quat)
                completed.append("recovery_retreat")
                final_pos = np.asarray(grasp_point(), dtype=float)
                return PBDParticlePinchResult(
                    success=False,
                    grasped=True,
                    released=True,
                    failure_reason=(
                        "attachment_segment_follow_failed:"
                        f" segment={label}"
                        f" follow_error={follow_error:.4f}"
                        f" limit={follow_limit:.4f}"
                    ),
                    initial_grasp_pos=initial_pos,
                    lifted_grasp_pos=lifted_pos,
                    final_grasp_pos=final_pos,
                    completed_phases=tuple(completed),
                    completed_segments=tuple(completed_segments),
                    segment_follow_errors=tuple(segment_follow_errors),
                )

        completed.append("drag")
        final_target = targets[-1]
        pre_release_pos = np.asarray(grasp_point(), dtype=float)
        if before_release is not None:
            before_release(pre_release_pos.copy(), final_target.copy())
        pre_release_pos = np.asarray(grasp_point(), dtype=float)
        target_error = float(np.linalg.norm(pre_release_pos - final_target))

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        self._retreat(controller, quat=ee_quat)
        completed.append("retreat")
        final_pos = np.asarray(grasp_point(), dtype=float)
        success = target_error <= float(self.max_follow_error)
        return PBDParticlePinchResult(
            success=success,
            grasped=True,
            released=True,
            failure_reason=(
                None
                if success
                else f"target_check_failed: grasp_target_error={target_error:.4f}"
            ),
            initial_grasp_pos=initial_pos,
            lifted_grasp_pos=lifted_pos,
            final_grasp_pos=final_pos,
            completed_phases=tuple(completed),
            completed_segments=tuple(completed_segments),
            segment_follow_errors=tuple(segment_follow_errors),
        )

    def _hand_for_grasp(self, grasp_pos: np.ndarray) -> np.ndarray:
        return np.asarray(grasp_pos, dtype=float) + np.array(
            [0.0, 0.0, HAND_TO_PAD_Z + float(self.touch_clearance)]
        )

    def _grasp_for_hand(self, hand_pos: np.ndarray) -> np.ndarray:
        return np.asarray(hand_pos, dtype=float) - np.array(
            [0.0, 0.0, HAND_TO_PAD_Z + float(self.touch_clearance)]
        )

    def _attached_center(self, controller, attach_offset) -> np.ndarray:
        """Where the welded group's centre should be for the hand's current pose."""

        center = self._grasp_for_hand(controller.hand_pos())
        if attach_offset is None:
            return center
        return center + np.asarray(attach_offset, dtype=float)

    def _follow_error(self, controller, grasp_pos: np.ndarray) -> float:
        return float(
            np.linalg.norm(
                np.asarray(grasp_pos, dtype=float)
                - self._grasp_for_hand(controller.hand_pos())
            )
        )

    def _retreat(self, controller, *, quat) -> None:
        retreat = controller.hand_pos()
        retreat[2] = max(float(self.approach_z), float(retreat[2]) + 0.08)
        self._move_hand(
            controller,
            retreat,
            steps=max(1, self.move_steps // 2),
            quat=quat,
        )

    def _move_hand(
        self,
        controller,
        target,
        *,
        steps: int,
        quat,
        rotate_from_current: bool = False,
        attached: bool = False,
        particle_offsets=None,
        set_grasp_particles=None,
        set_attached_sheet=None,
        attach_offset=None,
    ) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        start_quat = controller.hand_quat() if rotate_from_current else None
        steps = max(1, int(steps))
        for step in range(1, steps + 1):
            alpha = _ease(step / steps)
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
            if attached:
                center = self._attached_center(controller, attach_offset)
                self._sync_attachment(
                    center,
                    particle_offsets=particle_offsets,
                    set_grasp_particles=set_grasp_particles,
                    set_attached_sheet=set_attached_sheet,
                )
        if attached:
            center = self._attached_center(controller, attach_offset)
            self._sync_attachment(
                center,
                particle_offsets=particle_offsets,
                set_grasp_particles=set_grasp_particles,
                set_attached_sheet=set_attached_sheet,
            )
            for _ in range(max(0, int(self.motion_settle_steps))):
                center = self._attached_center(controller, attach_offset)
                self._sync_attachment(
                    center,
                    particle_offsets=particle_offsets,
                    set_grasp_particles=set_grasp_particles,
                    set_attached_sheet=set_attached_sheet,
                )
                controller.scene.step()
            center = self._attached_center(controller, attach_offset)
            self._sync_attachment(
                center,
                particle_offsets=particle_offsets,
                set_grasp_particles=set_grasp_particles,
                set_attached_sheet=set_attached_sheet,
            )
        else:
            controller.step(max(0, int(self.motion_settle_steps)))

    @staticmethod
    def _sync_attachment(
        center,
        *,
        particle_offsets,
        set_grasp_particles,
        set_attached_sheet,
    ) -> None:
        if set_attached_sheet is not None:
            set_attached_sheet(center)
            return
        set_grasp_particles(center + particle_offsets)

    def _log(self, label: str, controller, grasp_pos, *, extra: str = "") -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        grasp_pos = np.asarray(grasp_pos, dtype=float)
        print(
            f"[pbd_attach {label:<16}]"
            f" hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" corner=({grasp_pos[0]:+.3f},{grasp_pos[1]:+.3f},"
            f"{grasp_pos[2]:+.3f})"
            f"{extra}",
            flush=True,
        )

    def _log_segment(
        self,
        label: str,
        *,
        index: int,
        total: int,
        grasp_pos: np.ndarray,
        follow_error: float,
        target_error: float,
    ) -> None:
        if not self.verbose:
            return
        print(
            f"[pbd_attach segment {index:02d}/{total:02d}]"
            f" label={label}"
            f" corner=({grasp_pos[0]:+.3f},{grasp_pos[1]:+.3f},"
            f"{grasp_pos[2]:+.3f})"
            f" follow_error={follow_error:.4f}"
            f" target_error={target_error:.4f}",
            flush=True,
        )

    def _maybe_stop(self, marker: str) -> None:
        if self.debug_stop_after == marker:
            raise SystemExit(
                f"peeling debug stop reached after {marker}"
            )


@dataclass(frozen=True)
class PBDParticlePinchDragPrimitive:
    """Pinch a tracked group of PBD particles and drag it through waypoints."""

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "descend",
        "close",
        "grasp_settle",
        "lift_test",
        "drag",
        "release",
        "retreat",
    )

    approach_z: float
    lift_delta: float
    move_steps: int
    gripper_steps: int
    grasp_qpos: float
    close_hold_steps: int = 50
    motion_settle_steps: int = 20
    min_lift_delta: float = 0.008
    max_grasp_error: float = 0.05
    max_segment_follow_error: float | None = None
    release_hold_steps: int = 30
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        grasp_point,
        target_centers,
        target_steps=None,
        segment_labels=None,
        on_segment_start=None,
        on_segment_complete=None,
        before_release=None,
        ee_quat=None,
    ) -> PBDParticlePinchResult:
        targets = [np.asarray(target, dtype=float) for target in target_centers]
        if not targets:
            raise ValueError(
                "PBDParticlePinchDragPrimitive requires at least one target."
            )
        if target_steps is None:
            steps = [int(self.move_steps)] * len(targets)
        else:
            steps = [max(1, int(value)) for value in target_steps]
            if len(steps) != len(targets):
                raise ValueError("target_steps must match target_centers.")
        if segment_labels is None:
            labels = [
                f"segment_{index + 1:02d}" for index in range(len(targets))
            ]
        else:
            labels = [str(value) for value in segment_labels]
            if len(labels) != len(targets):
                raise ValueError("segment_labels must match target_centers.")

        completed: list[str] = []
        completed_segments: list[str] = []
        segment_follow_errors: list[float] = []
        initial_pos = np.asarray(grasp_point(), dtype=float)
        self._log("start", controller, initial_pos)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")

        grasp_hand = initial_pos.copy()
        grasp_hand[2] += HAND_TO_PAD_Z
        approach_hand = grasp_hand.copy()
        approach_hand[2] = max(
            float(self.approach_z),
            float(grasp_hand[2]) + 0.06,
        )
        self._move_hand(
            controller,
            approach_hand,
            steps=self.move_steps,
            quat=ee_quat,
            rotate_from_current=True,
        )
        completed.append("approach")
        self._move_hand(
            controller,
            grasp_hand,
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
        )
        completed.append("descend")
        self._log("after_descend", controller, grasp_point())

        controller.set_gripper(float(self.grasp_qpos), steps=self.gripper_steps)
        completed.append("close")
        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        self._log("after_close", controller, grasp_point())

        lift_hand = grasp_hand.copy()
        lift_hand[2] += float(self.lift_delta)
        self._move_hand(
            controller,
            lift_hand,
            steps=max(1, self.move_steps // 2),
            quat=ee_quat,
        )
        completed.append("lift_test")
        lifted_pos = np.asarray(grasp_point(), dtype=float)
        lift_amount = float(lifted_pos[2] - initial_pos[2])
        follow_error = self._follow_error(controller, lifted_pos)
        grasped = bool(
            lift_amount >= float(self.min_lift_delta)
            and follow_error <= float(self.max_grasp_error)
        )
        self._log("after_lift_test", controller, lifted_pos)
        if not grasped:
            controller.open_gripper(self.gripper_steps)
            completed.append("recovery_open")
            self._move_hand(
                controller,
                approach_hand,
                steps=max(1, self.move_steps // 2),
                quat=ee_quat,
            )
            completed.append("recovery_retreat")
            final_pos = np.asarray(grasp_point(), dtype=float)
            return PBDParticlePinchResult(
                success=False,
                grasped=False,
                released=True,
                failure_reason=(
                    "lift_check_failed:"
                    f" lift_delta={lift_amount:.4f}"
                    f" grasp_follow_error={follow_error:.4f}"
                ),
                initial_grasp_pos=initial_pos,
                lifted_grasp_pos=lifted_pos,
                final_grasp_pos=final_pos,
                completed_phases=tuple(completed),
                completed_segments=tuple(completed_segments),
                segment_follow_errors=tuple(segment_follow_errors),
            )

        follow_limit = (
            float(self.max_grasp_error)
            if self.max_segment_follow_error is None
            else float(self.max_segment_follow_error)
        )
        for index, (label, target, segment_steps) in enumerate(
            zip(labels, targets, steps),
            start=1,
        ):
            if on_segment_start is not None:
                on_segment_start(index, len(targets), label, target.copy())
            target_hand = target.copy()
            target_hand[2] += HAND_TO_PAD_Z
            self._move_hand(
                controller,
                target_hand,
                steps=segment_steps,
                quat=ee_quat,
            )
            grasp_pos = np.asarray(grasp_point(), dtype=float)
            follow_error = self._follow_error(controller, grasp_pos)
            target_error = float(np.linalg.norm(grasp_pos - target))
            completed_segments.append(label)
            segment_follow_errors.append(follow_error)
            self._log_segment(
                label,
                index=index,
                total=len(targets),
                grasp_pos=grasp_pos,
                follow_error=follow_error,
                target_error=target_error,
            )
            if on_segment_complete is not None:
                on_segment_complete(
                    index,
                    len(targets),
                    label,
                    target.copy(),
                    grasp_pos.copy(),
                    follow_error,
                    target_error,
                )
            if follow_error > follow_limit:
                controller.open_gripper(self.gripper_steps)
                completed.append("recovery_open")
                self._retreat(controller, quat=ee_quat)
                completed.append("recovery_retreat")
                final_pos = np.asarray(grasp_point(), dtype=float)
                return PBDParticlePinchResult(
                    success=False,
                    grasped=True,
                    released=True,
                    failure_reason=(
                        "segment_follow_failed:"
                        f" segment={label}"
                        f" grasp_follow_error={follow_error:.4f}"
                        f" limit={follow_limit:.4f}"
                    ),
                    initial_grasp_pos=initial_pos,
                    lifted_grasp_pos=lifted_pos,
                    final_grasp_pos=final_pos,
                    completed_phases=tuple(completed),
                    completed_segments=tuple(completed_segments),
                    segment_follow_errors=tuple(segment_follow_errors),
                )

        completed.append("drag")
        final_target = targets[-1]
        pre_release_pos = np.asarray(grasp_point(), dtype=float)
        target_error = float(np.linalg.norm(pre_release_pos - final_target))
        self._log("after_drag", controller, pre_release_pos)
        if before_release is not None:
            before_release(pre_release_pos.copy(), final_target.copy())

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        self._retreat(controller, quat=ee_quat)
        completed.append("retreat")
        final_pos = np.asarray(grasp_point(), dtype=float)
        success = target_error <= float(self.max_grasp_error)
        return PBDParticlePinchResult(
            success=success,
            grasped=True,
            released=True,
            failure_reason=(
                None
                if success
                else f"target_check_failed: grasp_target_error={target_error:.4f}"
            ),
            initial_grasp_pos=initial_pos,
            lifted_grasp_pos=lifted_pos,
            final_grasp_pos=final_pos,
            completed_phases=tuple(completed),
            completed_segments=tuple(completed_segments),
            segment_follow_errors=tuple(segment_follow_errors),
        )

    @staticmethod
    def _follow_error(controller, grasp_pos: np.ndarray) -> float:
        expected = controller.hand_pos() - np.array(
            [0.0, 0.0, HAND_TO_PAD_Z]
        )
        return float(np.linalg.norm(grasp_pos - expected))

    def _retreat(self, controller, *, quat) -> None:
        retreat = controller.hand_pos()
        retreat[2] = max(float(self.approach_z), float(retreat[2]) + 0.08)
        self._move_hand(
            controller,
            retreat,
            steps=max(1, self.move_steps // 2),
            quat=quat,
        )

    def _move_hand(
        self,
        controller,
        target,
        *,
        steps: int,
        quat,
        rotate_from_current: bool = False,
    ) -> None:
        start = controller.hand_pos()
        target = np.asarray(target, dtype=float)
        start_quat = controller.hand_quat() if rotate_from_current else None
        steps = max(1, int(steps))
        for step in range(1, steps + 1):
            alpha = _ease(step / steps)
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

    def _log(self, label: str, controller, grasp_pos) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        grasp_pos = np.asarray(grasp_pos, dtype=float)
        finger_q = controller.gripper_qpos()
        print(
            f"[pbd_pinch {label:<16}]"
            f" hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" corner=({grasp_pos[0]:+.3f},{grasp_pos[1]:+.3f},"
            f"{grasp_pos[2]:+.3f})"
            f" finger_q=({finger_q[0]:.4f},{finger_q[1]:.4f})",
            flush=True,
        )

    def _log_segment(
        self,
        label: str,
        *,
        index: int,
        total: int,
        grasp_pos: np.ndarray,
        follow_error: float,
        target_error: float,
    ) -> None:
        if not self.verbose:
            return
        print(
            f"[pbd_pinch segment {index:02d}/{total:02d}]"
            f" label={label}"
            f" corner=({grasp_pos[0]:+.3f},{grasp_pos[1]:+.3f},"
            f"{grasp_pos[2]:+.3f})"
            f" follow_error={follow_error:.4f}"
            f" target_error={target_error:.4f}",
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
        value = start + float(alpha) * (end - start)
        return value / np.linalg.norm(value)
    theta_0 = float(np.arccos(dot))
    sin_theta_0 = float(np.sin(theta_0))
    theta = theta_0 * float(alpha)
    return (
        np.sin(theta_0 - theta) / sin_theta_0 * start
        + np.sin(theta) / sin_theta_0 * end
    )
