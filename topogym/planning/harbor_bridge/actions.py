"""Robot-independent checked action conversion into the public Session contract."""
from __future__ import annotations

from collections.abc import Mapping
import numpy as np

from .contracts import BridgeError


def public_action(session, row):
    original = np.asarray(row)
    if original.shape != (len(session.action_layout),) or original.dtype.kind not in "fiu":
        raise BridgeError("Expected one numeric row in the frozen public layout")
    row = original.astype(np.float32)
    if not np.isfinite(row).all():
        raise BridgeError("Nonfinite public action")
    if not np.array_equal(session.robot.clip(row.astype(np.float64)), row):
        raise BridgeError("Action would be clipped by the public robot adapter")
    return row


def native_row(session, row, *, gripper_tolerance=1e-6, joint_tolerance=1e-6):
    """Audit float32 and native-finger/width round trips before submitting anything."""
    original = np.asarray(row, dtype=np.float64)
    if original.shape != (len(session.action_layout),) or not np.isfinite(original).all():
        raise BridgeError("Invalid native target row")
    converted = original.copy()
    for arm, column in session.robot.grip_index.items():
        width = float(np.float32(session.robot.native_to_width(arm, original[column])))
        recovered = float(session.robot.width_to_native(arm, width))
        if not np.isfinite(recovered) or abs(recovered - original[column]) > gripper_tolerance:
            raise BridgeError(f"Native gripper target is not representable by public widths: {arm}")
        converted[column] = width
    result = public_action(session, converted)
    grippers = set(session.robot.grip_index.values())
    joints = [i for i in range(len(result)) if i not in grippers]
    if np.any(np.abs(result[joints].astype(np.float64) - original[joints]) > joint_tolerance):
        raise BridgeError("Joint targets lose precision in the public float32 contract")
    return result


def public_row(session, native):
    """Convert compiled native commands, preserving all omitted joint/gripper targets."""
    if not isinstance(native, Mapping) or set(native) - set(session.env._robot.groups):
        raise BridgeError("Unknown arm in native commands")
    targets = session.env._robot.capture_state().targets
    row = session.hold_action().astype(np.float64)
    for side, group in session.env._robot.groups.items():
        update = native.get(side, {})
        if not isinstance(update, Mapping) or set(update) - {"joint_position_rad", group.gripper_field}:
            raise BridgeError(f"Unsupported native command fields for {side}")
        target = dict(targets[side], **update)
        row[session.robot.arm_slice[side]] = target["joint_position_rad"]
        row[session.robot.grip_index[side]] = target[group.gripper_field]
    return native_row(session, row)


class SessionExecutor:
    """A step adapter. It never creates/resets/closes an Env or starts a recorder.

    Task orchestrators retain their observations, stage guards and loop. Compile
    modes are passed explicitly, leaving the frozen Session JOINT_ABS config intact.
    """

    def __init__(self, session):
        self.session = session

    def step(self, action, *, mode="JOINT_ABS"):
        from topogym.robot.control import compile_action
        native = compile_action(self.session.env._robot, action, mode)
        return self.session.step(public_row(self.session, native))

    def step_public(self, row):
        return self.session.step(public_action(self.session, row))
