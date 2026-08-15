from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from .attachment import rotate_z
from .pick_place import HAND_TO_PAD_Z


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _entity_pos(entity: Any) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def _quat_yaw(quat) -> float | None:
    quat = _as_numpy(quat).reshape(-1, 4)[0].astype(float)
    norm = float(np.linalg.norm(quat))
    if norm <= 1e-8:
        return None
    w, x, y, z = quat / norm
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def _entity_yaw(entity: Any) -> float | None:
    get_quat = getattr(entity, "get_quat", None)
    if get_quat is None:
        return None
    return _quat_yaw(get_quat())


def _yaw_text(yaw: float | None) -> str:
    return "none" if yaw is None else f"{np.rad2deg(yaw):+.1f}deg"


def _vec_text(vec: np.ndarray) -> str:
    vec = np.asarray(vec, dtype=float).reshape(3)
    return f"({vec[0]:+.4f},{vec[1]:+.4f},{vec[2]:+.4f})"


def _follow_state(controller, handle_pos: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    expected_handle_pos = controller.hand_pos() - np.array([0.0, 0.0, HAND_TO_PAD_Z])
    delta = np.asarray(handle_pos, dtype=float) - expected_handle_pos
    return expected_handle_pos, delta, float(np.linalg.norm(delta))


def _ease(alpha: float) -> float:
    alpha = float(np.clip(alpha, 0.0, 1.0))
    return 0.5 - 0.5 * float(np.cos(np.pi * alpha))


@dataclass(frozen=True)
class HandleDragResult:
    success: bool
    grasped: bool
    released: bool
    failure_reason: str | None
    initial_handle_pos: np.ndarray
    lifted_handle_pos: np.ndarray
    final_handle_pos: np.ndarray
    completed_phases: tuple[str, ...]
    completed_segments: tuple[str, ...] = ()
    segment_follow_errors: tuple[float, ...] = ()


@dataclass(frozen=True)
class HandleDragPrimitive:
    """Physically grasp a RIGID handle and carry it through waypoints.

    Solver-agnostic by construction: it commands the arm and reads the handle's
    rigid pose, and never touches the deformable the handle is attached to --
    how that body is solved (PBD particles, FEM+IPC nodes) is the backend's
    problem. It was called ``PBDHandleDragPrimitive`` until 2026-08-12, which
    outlived the PBD era and misled a reader into thinking the rope material
    needed changing.
    """

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
    # Optional slow "peel-out" beat before the main lift: with the fingers
    # settled on the handle, ease the handle a small distance up so it visibly
    # unseats/unplugs deliberately instead of the handle appearing to launch
    # ahead of a large fast lift. 0 = disabled (unchanged for other callers).
    pre_lift_delta: float = 0.0
    pre_lift_steps: int = 0
    motion_settle_steps: int = 20
    min_lift_delta: float = 0.018
    max_handle_error: float = 0.035
    max_segment_follow_error: float | None = None
    max_segment_target_error: float | None = None
    target_error_abort_fraction: float = 0.75
    early_complete_segment_labels: tuple[str, ...] = ()
    early_complete_target_error: float | None = None
    max_downward_follow_error_z: float | None = None
    release_hold_steps: int = 30
    recover_on_segment_failure: bool = True
    runtime_attachment: bool = False
    runtime_attachment_child_yaw_offset: float = 0.0
    runtime_attachment_handoff_steps: int = 0
    motion_profile: str = "ease"
    # Anchor each segment's interpolation at the PREVIOUS commanded target
    # instead of the actual hand pose. With dense waypoints the actual pose
    # carries the PD gravity droop, so re-anchoring every segment produces a
    # per-waypoint dip-and-recover sawtooth (visible hand bobbing); command
    # continuity turns the droop into a constant offset.
    command_space_segments: bool = False
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        handle: Any,
        target_centers,
        target_steps=None,
        segment_labels=None,
        on_segment_start=None,
        on_segment_complete=None,
        on_close=None,
        on_lift=None,
        before_release=None,
        ee_quat=None,
        segment_quats=None,
        trace: list[np.ndarray] | None = None,
        attachment_manager=None,
    ) -> HandleDragResult:
        targets = [np.asarray(target, dtype=float) for target in target_centers]
        if not targets:
            raise ValueError("HandleDragPrimitive requires at least one target center.")
        if target_steps is None:
            steps = [int(self.move_steps)] * len(targets)
        else:
            steps = [max(1, int(value)) for value in target_steps]
            if len(steps) != len(targets):
                raise ValueError("target_steps must match target_centers.")
        if segment_labels is None:
            labels = [f"segment_{index + 1:02d}" for index in range(len(targets))]
        else:
            labels = [str(value) for value in segment_labels]
            if len(labels) != len(targets):
                raise ValueError("segment_labels must match target_centers.")
        # Per-segment hand orientation. None means the whole drag holds
        # `ee_quat`, which is what every caller but rope_winding wants; winding
        # turns the wrist as it orbits so the rope keeps the same bearing out of
        # the hand instead of sweeping around it.
        if segment_quats is None:
            quats = [ee_quat] * len(targets)
        else:
            quats = [np.asarray(value, dtype=float) for value in segment_quats]
            if len(quats) != len(targets):
                raise ValueError("segment_quats must match target_centers.")

        completed: list[str] = []
        completed_segments: list[str] = []
        segment_follow_errors: list[float] = []
        initial_pos = _entity_pos(handle)
        runtime_attachment = None
        if trace is not None:
            trace.append(initial_pos.copy())
        self._log("start", controller, handle)

        controller.open_gripper(self.gripper_steps)
        completed.append("open")

        grasp_hand = initial_pos.copy()
        grasp_hand[2] += HAND_TO_PAD_Z
        approach_hand = grasp_hand.copy()
        approach_hand[2] = max(float(self.approach_z), float(grasp_hand[2]) + 0.06)
        self._move_hand(
            controller,
            approach_hand,
            steps=self.move_steps,
            quat=ee_quat,
            rotate_from_current=True,
        )
        completed.append("approach")
        self._move_hand(controller, grasp_hand, steps=max(1, self.move_steps // 2), quat=ee_quat)
        completed.append("descend")
        self._log("after_descend", controller, handle)

        controller.set_gripper(float(self.grasp_qpos), steps=self.gripper_steps)
        completed.append("close")
        if on_close is not None:
            # Fires with the fingers closed, before any settle step, so callers can
            # hand the handle between kinematic constraints without a free gap.
            on_close()
        controller.step(max(0, int(self.close_hold_steps)))
        completed.append("grasp_settle")
        self._log("after_close", controller, handle)
        pre_lift_pos = _entity_pos(handle)

        if float(self.pre_lift_delta) > 0.0:
            # Deliberate slow unseating before the main lift (see field doc).
            peel_hand = grasp_hand.copy()
            peel_hand[2] += float(self.pre_lift_delta)
            self._move_hand(
                controller,
                peel_hand,
                steps=max(1, int(self.pre_lift_steps)),
                quat=ee_quat,
            )
            completed.append("peel_out")

        lift_hand = grasp_hand.copy()
        lift_hand[2] += float(self.lift_delta)
        if on_lift is not None:
            # Fires as the handle is about to leave the table, and the lift itself
            # is the window it gets to act over. A caller that wants to reorient
            # what it is holding has to wait for this: doing it on `on_close`
            # would swing the part into the tabletop it is still resting on.
            on_lift(max(1, self.move_steps // 2))
        self._move_hand(controller, lift_hand, steps=max(1, self.move_steps // 2), quat=ee_quat)
        completed.append("lift_test")
        lifted_pos = _entity_pos(handle)
        lift_amount = float(lifted_pos[2] - pre_lift_pos[2])
        _, follow_delta, follow_error = _follow_state(controller, lifted_pos)
        grasped = (
            lift_amount >= float(self.min_lift_delta)
            and follow_error <= float(self.max_handle_error)
        )
        self._log("after_lift_test", controller, handle)
        if not grasped:
            controller.open_gripper(self.gripper_steps)
            completed.append("recovery_open")
            self._move_hand(controller, approach_hand, steps=max(1, self.move_steps // 2), quat=ee_quat)
            completed.append("recovery_retreat")
            final_pos = _entity_pos(handle)
            return HandleDragResult(
                success=False,
                grasped=False,
                released=True,
                failure_reason=(
                    "lift_check_failed:"
                    f" lift_delta={lift_amount:.4f}"
                    f" handle_follow_error={follow_error:.4f}"
                    f" follow_xyz={_vec_text(follow_delta)}"
                ),
                initial_handle_pos=initial_pos,
                lifted_handle_pos=lifted_pos,
                final_handle_pos=final_pos,
                completed_phases=tuple(completed),
                completed_segments=tuple(completed_segments),
                segment_follow_errors=tuple(segment_follow_errors),
            )

        if self.runtime_attachment:
            if attachment_manager is None:
                raise ValueError(
                    "runtime_attachment=True requires an attachment_manager."
                )
            attachment_yaw = _entity_yaw(handle)
            if attachment_yaw is None:
                attachment_yaw = 0.0
            attach_pos = _entity_pos(handle)
            attach_offset = rotate_z(
                attach_pos - np.asarray(controller.hand_pos(), dtype=float),
                -float(attachment_yaw),
            )
            runtime_attachment = attachment_manager.create(
                entity=handle,
                parent_pos_fn=controller.hand_pos,
                offset=attach_offset,
                yaw=float(attachment_yaw),
                child_yaw_offset=float(self.runtime_attachment_child_yaw_offset),
            )
            runtime_attachment.attach()
            completed.append("runtime_attachment")
            self._log("after_runtime_attach", controller, handle)

        segment_follow_limit = (
            float(self.max_handle_error)
            if self.max_segment_follow_error is None
            else float(self.max_segment_follow_error)
        )
        segment_target_limit = (
            None
            if self.max_segment_target_error is None
            else float(self.max_segment_target_error)
        )
        downward_follow_z_limit = (
            None
            if self.max_downward_follow_error_z is None
            else float(self.max_downward_follow_error_z)
        )
        early_complete_labels = {
            str(value) for value in self.early_complete_segment_labels
        }
        early_complete_error = (
            None
            if self.early_complete_target_error is None
            else float(self.early_complete_target_error)
        )
        previous_command_hand = None
        previous_command_quat = None
        for index, (label, target, segment_steps, segment_quat) in enumerate(
            zip(labels, targets, steps, quats),
            start=1,
        ):
            if on_segment_start is not None:
                on_segment_start(index, len(targets), label, target.copy())
            target_hand = target.copy()
            target_hand[2] += HAND_TO_PAD_Z
            segment_aborted = self._move_hand(
                controller,
                target_hand,
                start_override=(
                    previous_command_hand if self.command_space_segments else None
                ),
                steps=segment_steps,
                quat=segment_quat,
                # Turn from the last COMMANDED orientation, not the measured one,
                # for the same reason positions are commanded that way: IK lag
                # would otherwise feed back into the next segment's start.
                start_quat_override=previous_command_quat,
                trace_handle=handle,
                trace=trace,
                progress_label=label,
                progress_index=index,
                progress_total=len(targets),
                abort_follow_error=segment_follow_limit,
                abort_target_error=segment_target_limit,
                abort_target_fraction=float(self.target_error_abort_fraction),
                abort_downward_follow_z=downward_follow_z_limit,
                early_complete_target_error=(
                    early_complete_error if label in early_complete_labels else None
                ),
            )
            previous_command_hand = target_hand.copy()
            previous_command_quat = segment_quat
            segment_handle_pos = _entity_pos(handle)
            _, follow_delta, follow_error = _follow_state(controller, segment_handle_pos)
            target_error = float(np.linalg.norm(segment_handle_pos - target))
            completed_segments.append(label)
            segment_follow_errors.append(follow_error)
            self._log_segment(
                label,
                controller=controller,
                handle=handle,
                index=index,
                total=len(targets),
                handle_pos=segment_handle_pos,
                follow_error=follow_error,
                target_error=target_error,
            )
            callback_abort_reason = None
            if on_segment_complete is not None:
                callback_abort = on_segment_complete(
                    index,
                    len(targets),
                    label,
                    target.copy(),
                    segment_handle_pos.copy(),
                    follow_error,
                    target_error,
                )
                if callback_abort:
                    callback_abort_reason = (
                        "segment_callback_abort"
                        if callback_abort is True
                        else str(callback_abort)
                    )
            if segment_aborted or follow_error > segment_follow_limit or callback_abort_reason:
                if runtime_attachment is not None:
                    runtime_attachment.release()
                    runtime_attachment = None
                    completed.append("runtime_attachment_release_on_failure")
                released = False
                if self.recover_on_segment_failure:
                    controller.open_gripper(self.gripper_steps)
                    released = True
                    completed.append("recovery_open")
                    retreat_hand = controller.hand_pos()
                    retreat_hand[2] = max(float(self.approach_z), float(retreat_hand[2]) + 0.08)
                    self._move_hand(
                        controller,
                        retreat_hand,
                        steps=max(1, self.move_steps // 2),
                        quat=ee_quat,
                    )
                    completed.append("recovery_retreat")
                else:
                    completed.append("safe_abort_no_recovery_step")
                final_pos = _entity_pos(handle)
                return HandleDragResult(
                    success=False,
                    grasped=True,
                    released=released,
                    failure_reason=(
                        f"{callback_abort_reason or 'segment_follow_failed'}"
                        f" segment={label}"
                        f" handle_follow_error={follow_error:.4f}"
                        f" target_error={target_error:.4f}"
                        f" follow_xyz={_vec_text(follow_delta)}"
                        f" limit={segment_follow_limit:.4f}"
                        f" mid_segment_abort={segment_aborted}"
                    ),
                    initial_handle_pos=initial_pos,
                    lifted_handle_pos=lifted_pos,
                    final_handle_pos=final_pos,
                    completed_phases=tuple(completed),
                    completed_segments=tuple(completed_segments),
                    segment_follow_errors=tuple(segment_follow_errors),
                )
        completed.append("drag")
        final_target = targets[-1]
        pre_release_pos = _entity_pos(handle)
        target_error = float(np.linalg.norm(pre_release_pos - final_target))
        self._log("after_drag", controller, handle)
        handoff_engaged = False
        if before_release is not None:
            handoff_engaged = bool(before_release(pre_release_pos.copy(), final_target.copy()))
            pre_release_pos = _entity_pos(handle)
            target_error = float(np.linalg.norm(pre_release_pos - final_target))
        if runtime_attachment is not None:
            runtime_attachment.release(sync=not handoff_engaged)
            runtime_attachment = None
            completed.append("runtime_attachment_release")
            pre_release_pos = _entity_pos(handle)
            target_error = float(np.linalg.norm(pre_release_pos - final_target))
            if handoff_engaged and int(self.runtime_attachment_handoff_steps) > 0:
                controller.step(max(0, int(self.runtime_attachment_handoff_steps)))
                completed.append("runtime_attachment_handoff_settle")
                pre_release_pos = _entity_pos(handle)
                target_error = float(np.linalg.norm(pre_release_pos - final_target))

        controller.open_gripper(self.gripper_steps)
        completed.append("release")
        controller.step(max(0, int(self.release_hold_steps)))
        released_pos = _entity_pos(handle)

        retreat_hand = controller.hand_pos()
        retreat_hand[2] = max(float(self.approach_z), float(retreat_hand[2]) + 0.08)
        self._move_hand(controller, retreat_hand, steps=max(1, self.move_steps // 2), quat=ee_quat)
        completed.append("retreat")
        final_pos = _entity_pos(handle)
        success = target_error <= float(self.max_handle_error)
        return HandleDragResult(
            success=success,
            grasped=True,
            released=True,
            failure_reason=(
                None
                if success
                else f"target_check_failed: handle_target_error={target_error:.4f}"
            ),
            initial_handle_pos=initial_pos,
            lifted_handle_pos=lifted_pos,
            final_handle_pos=final_pos if np.all(np.isfinite(final_pos)) else released_pos,
            completed_phases=tuple(completed),
            completed_segments=tuple(completed_segments),
            segment_follow_errors=tuple(segment_follow_errors),
        )

    def _move_hand(
        self,
        controller,
        target,
        *,
        steps: int,
        quat,
        start_override=None,
        start_quat_override=None,
        rotate_from_current: bool = False,
        trace_handle=None,
        trace: list[np.ndarray] | None = None,
        progress_label: str | None = None,
        progress_index: int | None = None,
        progress_total: int | None = None,
        abort_follow_error: float | None = None,
        abort_target_error: float | None = None,
        abort_target_fraction: float = 0.75,
        abort_downward_follow_z: float | None = None,
        early_complete_target_error: float | None = None,
    ) -> bool:
        start = (
            np.asarray(start_override, dtype=float)
            if start_override is not None
            else controller.hand_pos()
        )
        target = np.asarray(target, dtype=float)
        start_quat = (
            np.asarray(start_quat_override, dtype=float)
            if start_quat_override is not None
            else (controller.hand_quat() if rotate_from_current else None)
        )
        steps = max(1, int(steps))
        progress_interval = max(20, steps // 5)
        handle_target = target - np.array([0.0, 0.0, HAND_TO_PAD_Z])
        profile = str(self.motion_profile).lower()
        if profile not in {"ease", "linear"}:
            raise ValueError("motion_profile must be 'ease' or 'linear'.")
        for step in range(1, steps + 1):
            raw_alpha = step / steps
            alpha = raw_alpha if profile == "linear" else _ease(raw_alpha)
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
            handle_pos = None
            if trace is not None and trace_handle is not None:
                handle_pos = _entity_pos(trace_handle)
                trace.append(handle_pos.copy())
            if (
                self.verbose
                and progress_label is not None
                and trace_handle is not None
                and (step == 1 or step == steps or step % progress_interval == 0)
            ):
                self._log_segment_progress(
                    progress_label,
                    controller=controller,
                    handle=trace_handle,
                    index=int(progress_index or 0),
                    total=int(progress_total or 0),
                    step=step,
                    steps=steps,
                    target=handle_target,
            )
            if abort_follow_error is not None and trace_handle is not None:
                if handle_pos is None:
                    handle_pos = _entity_pos(trace_handle)
                _, follow_delta, follow_error = _follow_state(controller, handle_pos)
                if follow_error > float(abort_follow_error):
                    if self.verbose:
                        print(
                            f"[handle_drag abort {int(progress_index or 0):02d}/"
                            f"{int(progress_total or 0):02d}]"
                            f" label={progress_label}"
                            f" step={step:03d}/{steps:03d}"
                            f" follow_error={follow_error:.4f}"
                            f" follow_xyz={_vec_text(follow_delta)}"
                            f" limit={float(abort_follow_error):.4f}",
                            flush=True,
                        )
                    return True
                if (
                    abort_downward_follow_z is not None
                    and -float(follow_delta[2]) > float(abort_downward_follow_z)
                ):
                    if self.verbose:
                        print(
                            f"[handle_drag abort {int(progress_index or 0):02d}/"
                            f"{int(progress_total or 0):02d}]"
                            f" label={progress_label}"
                            f" step={step:03d}/{steps:03d}"
                            f" follow_z={float(follow_delta[2]):+.4f}"
                            f" downward_limit={float(abort_downward_follow_z):.4f}",
                            flush=True,
                        )
                    return True
                if (
                    abort_target_error is not None
                    and step / steps >= float(abort_target_fraction)
                ):
                    target_error = float(np.linalg.norm(handle_pos - handle_target))
                    if target_error > float(abort_target_error):
                        if self.verbose:
                            print(
                                f"[handle_drag abort {int(progress_index or 0):02d}/"
                                f"{int(progress_total or 0):02d}]"
                                f" label={progress_label}"
                                f" step={step:03d}/{steps:03d}"
                                f" target_error={target_error:.4f}"
                                f" target_limit={float(abort_target_error):.4f}",
                                flush=True,
                            )
                        return True
            if early_complete_target_error is not None and trace_handle is not None:
                if handle_pos is None:
                    handle_pos = _entity_pos(trace_handle)
                target_error = float(np.linalg.norm(handle_pos - handle_target))
                if target_error <= float(early_complete_target_error):
                    if self.verbose:
                        print(
                            f"[handle_drag early_complete "
                            f"{int(progress_index or 0):02d}/"
                            f"{int(progress_total or 0):02d}]"
                            f" label={progress_label}"
                            f" step={step:03d}/{steps:03d}"
                            f" target_error={target_error:.4f}"
                            f" threshold={float(early_complete_target_error):.4f}",
                            flush=True,
                        )
                    return False
        controller.step(max(0, int(self.motion_settle_steps)))
        return False

    def _log(self, label: str, controller, handle: Any) -> None:
        if not self.verbose:
            return
        hand = controller.hand_pos()
        handle_pos = _entity_pos(handle)
        finger_q = controller.gripper_qpos()
        _, follow_delta, follow_error = _follow_state(controller, handle_pos)
        hand_yaw_text = _yaw_text(_quat_yaw(controller.hand_quat()))
        handle_yaw_text = _yaw_text(_entity_yaw(handle))
        print(
            f"[handle_drag {label:<16}]"
            f" hand=({hand[0]:+.3f},{hand[1]:+.3f},{hand[2]:+.3f})"
            f" handle=({handle_pos[0]:+.3f},{handle_pos[1]:+.3f},{handle_pos[2]:+.3f})"
            f" finger_q=({finger_q[0]:.4f},{finger_q[1]:.4f})",
            f"follow_error={follow_error:.4f}",
            f"follow_xyz={_vec_text(follow_delta)}",
            f"hand_yaw={hand_yaw_text}",
            f"handle_yaw={handle_yaw_text}",
            flush=True,
        )

    def _log_segment(
        self,
        label: str,
        *,
        controller,
        handle: Any,
        index: int,
        total: int,
        handle_pos: np.ndarray,
        follow_error: float,
        target_error: float,
    ) -> None:
        if not self.verbose:
            return
        finger_q = controller.gripper_qpos()
        _, follow_delta, _ = _follow_state(controller, handle_pos)
        hand_yaw_text = _yaw_text(_quat_yaw(controller.hand_quat()))
        handle_yaw_text = _yaw_text(_entity_yaw(handle))
        print(
            f"[handle_drag segment {index:02d}/{total:02d}]"
            f" label={label}"
            f" handle=({handle_pos[0]:+.3f},{handle_pos[1]:+.3f},{handle_pos[2]:+.3f})"
            f" finger_q=({finger_q[0]:.4f},{finger_q[1]:.4f})"
            f" follow_error={follow_error:.4f}"
            f" follow_xyz={_vec_text(follow_delta)}"
            f" target_error={target_error:.4f}"
            f" hand_yaw={hand_yaw_text}"
            f" handle_yaw={handle_yaw_text}",
            flush=True,
        )

    def _log_segment_progress(
        self,
        label: str,
        *,
        controller,
        handle: Any,
        index: int,
        total: int,
        step: int,
        steps: int,
        target: np.ndarray,
    ) -> None:
        hand = controller.hand_pos()
        handle_pos = _entity_pos(handle)
        finger_q = controller.gripper_qpos()
        _, follow_delta, follow_error = _follow_state(controller, handle_pos)
        target_delta = handle_pos - target
        target_error = float(np.linalg.norm(handle_pos - target))
        print(
            f"[handle_drag progress {index:02d}/{total:02d}]"
            f" label={label}"
            f" step={step:03d}/{steps:03d}"
            f" handle=({handle_pos[0]:+.3f},{handle_pos[1]:+.3f},{handle_pos[2]:+.3f})"
            f" finger_q=({finger_q[0]:.4f},{finger_q[1]:.4f})"
            f" follow_error={follow_error:.4f}"
            f" follow_xyz={_vec_text(follow_delta)}"
            f" target_error={target_error:.4f}"
            f" target_xyz={_vec_text(target_delta)}"
            f" hand_yaw={_yaw_text(_quat_yaw(controller.hand_quat()))}"
            f" handle_yaw={_yaw_text(_entity_yaw(handle))}",
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
