from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .attachment import AttachmentManager, ParticleAttachment, parent_pos_for_child

HAND_TO_ENDPOINT_Z: float = 0.1029
DEFAULT_ENDPOINT_OFFSET = (0.0, 0.0, -HAND_TO_ENDPOINT_Z)


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def _xyz(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 3)[0]


def _lerp(start, end, alpha: float) -> np.ndarray:
    return (1.0 - alpha) * np.asarray(start, dtype=float) + alpha * np.asarray(end, dtype=float)


def _ease(alpha: float) -> float:
    alpha = float(np.clip(alpha, 0.0, 1.0))
    return 0.5 - 0.5 * float(np.cos(np.pi * alpha))


def _endpoint_indices(handle: Any, endpoint: str) -> np.ndarray:
    indices = handle.start_indices if endpoint == "start" else handle.end_indices
    indices = np.asarray(indices, dtype=int)
    if indices.size == 0:
        raise RuntimeError(f"No endpoint particles found for {handle.name}:{endpoint}.")
    return indices


def _endpoint_pin(handle: Any, endpoint: str):
    return handle.start_pin if endpoint == "start" else handle.end_pin


def _entity_pos(entity: Any) -> np.ndarray:
    return _xyz(entity.get_pos())


def current_endpoint_center(handle: Any, endpoint: str) -> np.ndarray:
    indices = _endpoint_indices(handle, endpoint)
    particles = _as_numpy(handle.entity.get_particles_pos())
    if particles.ndim == 3:
        particles = particles[0]
    return np.asarray(particles[indices], dtype=float).mean(axis=0)


def sync_endpoint_pin(
    handle: Any,
    endpoint: str,
    center: np.ndarray | None = None,
    *,
    enabled: bool = False,
) -> None:
    # Keeping this opt-in avoids the PBD/rigid overlap crashes observed when
    # repeatedly moving endpoint pins and particles in the same native step.
    if not enabled:
        return
    pin = _endpoint_pin(handle, endpoint)
    if pin is None:
        return
    if center is None:
        center = current_endpoint_center(handle, endpoint)
    pin.set_pos(tuple(np.asarray(center, dtype=float)), zero_velocity=True)


class EndpointAttachment(ParticleAttachment):
    """``ParticleAttachment`` specialized to a rope endpoint, plus its visible pin.

    The welding mechanics live in the base class so the endpoint path and the
    mid-rope path cannot drift apart; this adds only the two endpoint-specific
    pieces -- resolving "start"/"end" to particle indices, and dragging the
    endpoint's visible pin along.
    """

    def __init__(
        self,
        handle: Any,
        endpoint: str,
        parent_pos_fn: Callable[[], Any],
        offset=DEFAULT_ENDPOINT_OFFSET,
        *,
        sync_pin: bool = False,
        set_particles_vel: bool = False,
    ) -> None:
        super().__init__(
            handle.entity,
            _endpoint_indices(handle, endpoint),
            parent_pos_fn,
            offset=offset,
            zero_velocity=set_particles_vel,
        )
        self.handle = handle
        self.endpoint = endpoint
        self.sync_pin = bool(sync_pin)

    def drive_to(self, center) -> None:
        super().drive_to(center)
        if self.active:
            sync_endpoint_pin(self.handle, self.endpoint, center, enabled=self.sync_pin)


class EndpointAttachmentManager:
    """Synchronize active PBD endpoint attachments around every scene step."""

    def __init__(self, scene: Any) -> None:
        self.scene = scene
        self.attachments: list[EndpointAttachment] = []
        self._original_step = None

    def create(
        self,
        handle: Any,
        endpoint: str,
        parent_pos_fn: Callable[[], Any],
        offset=DEFAULT_ENDPOINT_OFFSET,
        *,
        sync_pin: bool = False,
        set_particles_vel: bool = False,
    ) -> EndpointAttachment:
        attachment = EndpointAttachment(
            handle,
            endpoint,
            parent_pos_fn,
            offset=offset,
            sync_pin=sync_pin,
            set_particles_vel=set_particles_vel,
        )
        self.attachments.append(attachment)
        return attachment

    def sync(self) -> None:
        for attachment in self.attachments:
            attachment.sync()

    def __enter__(self):
        if self._original_step is not None:
            return self
        self._original_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            self.sync()
            result = self._original_step(*args, **kwargs)
            self.sync()
            return result

        self.scene.step = wrapped_step
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_step is not None:
            self.scene.step = self._original_step
            self._original_step = None


@dataclass(frozen=True)
class RopeEndpointDragPrimitive:
    """Robot-driven drag of a PBD rope endpoint via its visible anchor pin."""

    move_steps: int
    gripper_steps: int
    drag_steps: int
    endpoint_lift: float
    arc_height: float = 0.0
    endpoint_offset: tuple[float, float, float] = DEFAULT_ENDPOINT_OFFSET
    sync_pin: bool = False
    set_particles_vel: bool = False
    debug_print_steps: bool = False

    def run(
        self,
        controller: Any,
        *,
        pin_attachment_manager: AttachmentManager,
        endpoint_attachment_manager: EndpointAttachmentManager,
        handle: Any,
        endpoint: str,
        target_center,
        grasp_qpos: float,
    ) -> None:
        pin = _endpoint_pin(handle, endpoint)
        if pin is None:
            raise RuntimeError(
                "RopeEndpointDragPrimitive requires rope.anchor_pins.enabled=true "
                "with endpoint pins so the gripper has a visible handle."
            )

        source_center = _entity_pos(pin)
        target_center = np.asarray(target_center, dtype=float)
        endpoint_offset = np.asarray(self.endpoint_offset, dtype=float)

        source_hand = parent_pos_for_child(source_center, endpoint_offset, 0.0)
        target_hand = parent_pos_for_child(target_center, endpoint_offset, 0.0)
        approach_source = source_hand.copy()
        approach_source[2] = max(approach_source[2], 1.02)
        approach_target = target_hand.copy()
        approach_target[2] = approach_source[2]

        lift = max(0.0, float(self.endpoint_lift))
        lifted_source = source_center.copy()
        lifted_source[2] += lift
        lifted_target = target_center.copy()
        lifted_target[2] += lift
        lifted_source_hand = parent_pos_for_child(lifted_source, endpoint_offset, 0.0)

        if self.debug_print_steps:
            print(f"robot_drag open_gripper steps={self.gripper_steps}")
        controller.open_gripper(self.gripper_steps)
        self._move_hand(controller, approach_source, steps=self.move_steps, label="move_approach_source")
        self._move_hand(controller, source_hand, steps=max(1, self.move_steps // 2), label="move_source")

        if self.debug_print_steps:
            print(f"robot_drag close_gripper qpos={grasp_qpos} steps={self.gripper_steps}")
        controller.set_gripper(grasp_qpos, steps=self.gripper_steps)

        if self.debug_print_steps:
            hand = controller.hand_pos()
            endpoint_center = current_endpoint_center(handle, endpoint)
            pin_center = _entity_pos(pin)
            attached_center = hand + endpoint_offset
            snap = float(np.linalg.norm(attached_center - pin_center))
            print(
                "robot_drag attach begin "
                f"hand={hand} pin={pin_center} endpoint={endpoint_center} "
                f"attached_center={attached_center} snap={snap:.6f}"
            )

        pin_attachment = pin_attachment_manager.create(
            entity=pin,
            parent_pos_fn=controller.hand_pos,
            offset=endpoint_offset,
        )
        pin_attachment.attach()
        endpoint_attachment = endpoint_attachment_manager.create(
            handle,
            endpoint,
            lambda: _entity_pos(pin),
            offset=(0.0, 0.0, 0.0),
            sync_pin=self.sync_pin,
            set_particles_vel=self.set_particles_vel,
        )
        endpoint_attachment.attach()

        if self.debug_print_steps:
            print(
                f"robot_drag attach end pin={_entity_pos(pin)} "
                f"endpoint={current_endpoint_center(handle, endpoint)}"
            )

        lift_steps = max(1, self.drag_steps // 6) if lift > 0.0 and self.drag_steps >= 3 else 0
        drop_steps = lift_steps
        carry_steps = max(1, self.drag_steps - lift_steps - drop_steps)
        self._move_hand(controller, lifted_source_hand, steps=lift_steps, label="lift")

        for step in range(1, carry_steps + 1):
            alpha = _ease(step / carry_steps)
            center = _lerp(lifted_source, lifted_target, alpha)
            center[2] += float(self.arc_height) * np.sin(np.pi * alpha)
            hand_pos = parent_pos_for_child(center, endpoint_offset, 0.0)
            controller.move_ee_to(hand_pos, steps=1)
            if self.debug_print_steps and (step == 1 or step == carry_steps or step % 25 == 0):
                print(
                    f"robot_drag carry step={step}/{carry_steps} "
                    f"hand={controller.hand_pos()} pin={_entity_pos(pin)} "
                    f"endpoint={current_endpoint_center(handle, endpoint)}"
                )

        self._move_hand(controller, target_hand, steps=drop_steps, label="drop")
        if self.debug_print_steps:
            print(f"robot_drag open_release steps={self.gripper_steps}")
        controller.open_gripper(self.gripper_steps)
        endpoint_attachment.release()
        pin_attachment.release()
        self._move_hand(controller, approach_target, steps=max(1, self.move_steps // 2), label="retract")

    def _move_hand(self, controller: Any, target_pos, *, steps: int, label: str) -> None:
        steps = max(0, int(steps))
        if steps == 0:
            return
        if self.debug_print_steps:
            print(f"robot_drag {label} begin steps={steps}")
        start = controller.hand_pos()
        target = np.asarray(target_pos, dtype=float)
        for step in range(1, steps + 1):
            controller.move_ee_to(_lerp(start, target, step / steps), steps=1)
        if self.debug_print_steps:
            print(f"robot_drag {label} end hand={controller.hand_pos()}")
