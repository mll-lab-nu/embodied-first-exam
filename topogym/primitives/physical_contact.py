from __future__ import annotations

import numpy as np


def print_collision_il_contract(
    task_name: str,
    *,
    manipulated: list[str] | tuple[str, ...],
    contact_actor: str = "franka_gripper",
    runtime_attachment: bool = False,
    runtime_set_pose: bool = False,
    success_checks: list[str] | tuple[str, ...] = (),
) -> None:
    """Print a grep-friendly contract for collision-based IL demos.

    This is intentionally a runtime log instead of a comment: dataset collection
    should be able to record which demos used contact/collision transport and
    which used environment mechanisms.
    """

    print(
        f"{task_name} il_contract "
        "mode=collision_based_contact "
        f"manipulated={','.join(str(item) for item in manipulated)} "
        f"contact_actor={contact_actor} "
        f"runtime_attachment={bool(runtime_attachment)} "
        f"runtime_set_pose={bool(runtime_set_pose)} "
        f"success_checks={','.join(str(item) for item in success_checks)}",
        flush=True,
    )


def entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0].astype(float)


def entity_quat(entity) -> np.ndarray:
    """An entity's world orientation as (w, x, y, z)."""

    value = entity.get_quat()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 4)[0].astype(float)


def ee_quat_for_yaw(default_ee_quat, yaw: float) -> np.ndarray:
    default = np.asarray(default_ee_quat, dtype=float)
    half = 0.5 * float(yaw)
    yaw_quat = np.array([np.cos(half), 0.0, 0.0, np.sin(half)], dtype=float)
    quat = _quat_mul(yaw_quat, default)
    return quat / np.linalg.norm(quat)


def validate_rigid_friction(value: float, name: str) -> float:
    value = float(value)
    if not 0.01 <= value <= 5.0:
        raise ValueError(
            f"{name} must be in Genesis' stable rigid-friction range [0.01, 5.0]; got {value}."
        )
    return value


def configure_gripper_contact_friction(
    *,
    entities,
    robot,
    finger_links,
    object_friction: float,
    finger_friction: float,
) -> None:
    object_friction = validate_rigid_friction(object_friction, "object_friction")
    for entity in entities:
        entity.set_friction(object_friction)
    configure_finger_contact_friction(
        robot=robot,
        finger_links=finger_links,
        finger_friction=finger_friction,
    )


def configure_finger_contact_friction(
    *,
    robot,
    finger_links,
    finger_friction: float,
) -> None:
    finger_friction = validate_rigid_friction(
        finger_friction,
        "finger_friction",
    )
    for link_name in finger_links:
        robot.get_link(str(link_name)).set_friction(finger_friction)


def quat_mul(a, b) -> np.ndarray:
    """Hamilton product of two (w, x, y, z) quaternions."""

    aw, ax, ay, az = np.asarray(a, dtype=float)
    bw, bx, by, bz = np.asarray(b, dtype=float)
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dtype=float,
    )


_quat_mul = quat_mul


def quat_about_axis(axis, angle: float) -> np.ndarray:
    """Rotation of ``angle`` radians about a world axis, as (w, x, y, z).

    Left-multiply an entity's current orientation by this to turn it in world
    axes: ``quat_mul(quat_about_axis(u, theta), entity_quat(e))``.
    """

    axis = np.asarray(axis, dtype=float)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-12:
        raise ValueError("quat_about_axis needs a non-degenerate axis.")
    half = 0.5 * float(angle)
    return np.concatenate(([np.cos(half)], np.sin(half) * axis / norm))
