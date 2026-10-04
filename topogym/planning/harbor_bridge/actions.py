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
        encode = getattr(session.robot, "native_to_action", session.robot.native_to_width)
        decode = getattr(session.robot, "action_to_native", session.robot.width_to_native)
        width = float(np.float32(encode(arm, original[column])))
        if getattr(session.robot, "gripper_space", "width") == "native":
            # Only float32 outward rounding at an authored limit is adjusted.
            # Out-of-range native requests still fail; no drive target is saturated.
            lo, hi = session.env._robot.groups[arm].gripper_limits
            if not lo <= original[column] <= hi:
                raise BridgeError(f"Native gripper target outside model limits: {arm}")
            width = float(np.clip(width, *session.robot.limits[column]))
        recovered = float(decode(arm, width))
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


class SessionPolicyRunner:
    """Run existing act(observation) policies through the caller's Session.

    This adapter has no Env/recorder lifecycle and emits no SegmentRunner proof.
    The bridge wrapper and independent Harbor verifier own trajectory evidence.
    """

    def __init__(self, session, *, control_mode="JOINT_ABS"):
        if control_mode not in {"JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"}:
            raise BridgeError("Unknown policy control mode")
        self.session = session
        self.env = session.env
        self.executor = SessionExecutor(session)
        self.control_mode = control_mode

    def run_policy(self, *, request_id, policy, submission_hash, mode="unlimited",
                   observation_profile=None, state_fields=()):
        if mode != "unlimited" or set(state_fields) - {"world", "task"}:
            raise BridgeError("Session policy adapter supports private robot/world observations only")
        if observation_profile not in (None, {"rgb_camera_ids": []}):
            raise BridgeError("Session policy adapter does not own camera recording")
        from topogym.robot.control import action_spec
        session, env = self.session, self.session.env
        start, tick = session.n_steps, env._world.physics_step
        observation = None
        initialize = getattr(policy, "initialize", None)
        if initialize is not None:
            initialize(dict(action_spec=action_spec(env._robot.description, self.control_mode), timing_spec=env.timing_spec))
        def observe():
            observation = dict(state=dict(env.tick_record()["state"]),
                               robot=env._robot.observe())
            if "world" in state_fields:
                observation["privileged"] = dict(world=env._world.read_state())
            if "task" in state_fields:
                from topogym.utils.io import to_jsonable
                observation.setdefault("privileged", {})["task"] = to_jsonable(env._task.result)
            return observation

        while not session.episode_done and session.episode_end is None:
            observation = observe()
            action = policy.act(observation)
            if action is None:
                break
            if self.executor.step(action, mode=self.control_mode):
                break
        result = dict(request_id=request_id, submission_hash=submission_hash,
                    reason="env_terminal" if session.episode_done or session.episode_end is not None else "policy_done",
                    control_steps=session.n_steps - start, physics_steps=env._world.physics_step - tick,
                    task_success=bool(session.success()), evidence_scope="caller-owned Session trajectory; verifier pending")
        complete = (len(session._recording) == session.n_steps and
                    sum(session._recorded_ticks[start:]) == env._world.physics_step - tick)
        result.update(evidence_complete=complete, physics_tick_complete=complete,
                      control_step_complete=complete, uncheckpointed_physics_steps=0 if complete else None)
        on_end = getattr(policy, "on_segment_end", None)
        if callable(on_end) and observation is not None:
            on_end(observe(), result)
        return result
