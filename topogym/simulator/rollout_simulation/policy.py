"""Manager-owned passive policy dispatch, using the existing segment step path."""
from collections.abc import Mapping
import re

from topogym.utils.snapshots import freeze
from .segment_contract import (SegmentError, fingerprint, request_id, public_info,
                               validate_policy_output, make_execution_state)
from .policy_observation import validate_profile, project_observation, build_context
from .evidence import EvidenceError


def execute_policy(runner, identifier, policy, *, submission_hash, mode,
                   observation_profile=None, state_fields=()):
    """Internal: runner holds its dispatch lock throughout this call."""
    request_id(identifier)
    if mode not in {"limited", "unlimited"}:
        raise ValueError("mode must be limited or unlimited")
    if not isinstance(submission_hash, str) or re.fullmatch("[0-9a-f]{64}", submission_hash) is None:
        raise ValueError("submission_hash must be a lowercase SHA-256 digest")
    if not callable(getattr(policy, "act", None)):
        raise TypeError("policy must implement act(obs)")
    if not isinstance(state_fields, (tuple, list)) or any(not isinstance(x, str) for x in state_fields):
        raise ValueError("state_fields must be a list or tuple of names")
    if len(set(state_fields)) != len(state_fields):
        raise ValueError("Duplicate state field")
    if set(state_fields) - {"robot", "world", "task"}:
        raise ValueError("Unsupported privileged state field")
    if mode == "limited" and state_fields:
        raise PermissionError("limited does not allow privileged state fields")
    settings = {} if observation_profile is None else observation_profile
    if not isinstance(settings, Mapping):
        raise ValueError("observation_profile must be a mapping")
    # Authorization and identity precede cache lookup, but observation reads do
    # not: even a faulted episode can retrieve an already sealed request result.
    if mode == "unlimited" and not runner.env.config.enable_privileged:
        raise PermissionError("Privileged access is disabled")
    signature = fingerprint(dict(kind="scripted_policy_v1", submission_hash=submission_hash,
        mode=mode, observation_profile=settings, state_fields=sorted(state_fields)))
    if identifier in runner._requests:
        record = runner._records[runner._requests[identifier]]
        if record["signature"] != signature:
            raise SegmentError("request_id_conflict")
        if record["result"] is not None:
            return record["result"]
        raise SegmentError("segment_already_active")
    access = runner.env.interaction(privileged=mode == "unlimited")
    raw, proprioception, extra = runner._policy_inputs(state_fields, access)
    from topogym.config.scene import load_scene_config
    from topogym.sensors.camera_info import camera_contract
    cameras = getattr(load_scene_config(runner.env.config).env, "cameras", {})
    camera_specs = camera_contract(cameras)
    for name, camera in runner.env._world.cameras.items():
        if getattr(camera, "_attached_link", None) is not None or getattr(camera, "_followed_entity", None) is not None:
            camera_specs[name]["motion"] = "moving"
    spec = access.action_spec
    profile = validate_profile(mode=mode, settings=settings, camera_specs=camera_specs,
        action_spec=spec, state_fields=state_fields, privileged_enabled=runner.env.config.enable_privileged,
        raw_observation=raw, proprioception=proprioception)
    context = build_context(profile, spec, access.timing_spec)
    descriptor = runner._begin(identifier, signature=signature, profile=profile)
    identity, token = descriptor["segment_id"], descriptor["token"]
    record = runner._records[identity]
    record["policy"] = dict(schema_version=1, submission_hash=submission_hash,
        observation_profile=profile.identity(), decision_calls=0, status="running")
    previous = None
    obs = None
    interruption = None

    def event(kind, **values):
        runner._evidence.policy_event(kind, segment_id=identity, state_ref=runner._state_ref(),
                                     action_index=len(record["steps"]), **values)

    def projected(raw, proprioception, extra):
        state_ref = {k: raw["state"][k] for k in ("episode_id", "state_id")}
        execution = make_execution_state(control_steps=len(record["steps"]), previous=previous,
            observation_state_ref=state_ref, current_state_ref=runner._state_ref())
        return project_observation(raw, proprioception, profile=profile,
                                    execution_state=execution, privileged_values=extra)

    stage = "policy_evidence"
    try:
        event("policy_submitted", submission_hash=submission_hash, profile=profile.identity())
        runner._evidence.write_policy_report(identity, record["policy"])
        stage = "observation"
        obs = projected(raw, proprioception, extra)
        stage = "policy_initialize"
        initialize = getattr(policy, "initialize", None)
        if initialize is not None:
            if not callable(initialize) or initialize(context) is not None:
                raise ValueError("initialize(context) must return None")
        while True:
            stage = "policy_act"
            record["policy"]["decision_calls"] += 1
            action = policy.act(obs)
            stage = "policy_output"
            validate_policy_output(action)
            stage = "policy_evidence"
            event("policy_output", segment_done=action is None)
            if action is None:
                result = runner._end(identity, token, reason="policy_done")
                break
            stage = "step"
            try:
                transition = runner._step(identity, token, action, sequence=None, finalize_terminal=False)
            except SegmentError:
                if record["result"] is None:
                    raise
                result = record["result"]
                break
            # Use the immutable accepted action echo, not mutable user input.
            previous = dict(action_index=len(record["steps"])-1, action=record["steps"][-1]["action"], completed=True,
                            terminated=transition[2], truncated=transition[3], info=transition[4])
            stage = "observation"
            raw, proprioception, extra = runner._policy_inputs(profile.state_fields, access)
            obs = projected(raw, proprioception, extra)
            if transition[2] or transition[3]:
                result = runner._end(identity, token,
                                     reason="env_terminal" if transition[2] else "env_time_limit")
                break
    except BaseException as error:
        reason = ("cancelled" if not isinstance(error, Exception) else
                  "evidence_error" if isinstance(error, EvidenceError) or stage == "policy_evidence" else
                  "observation_error" if stage == "observation" else
                  "invalid_policy_output" if stage == "policy_output" else "policy_error")
        runner._failed |= reason in {"evidence_error", "observation_error"}
        record["errors"].append(runner._error(error, stage))
        try:
            event("policy_failed", reason=reason, error=record["errors"][-1])
        except Exception as output_error:
            record["errors"].append(runner._error(output_error, "policy_error_evidence"))
            runner._failed = True
            reason = "evidence_error"
        result = runner._end(identity, token, reason=reason)
        if not isinstance(error, Exception):
            interruption = error

    # On failure the last image may precede the last physical tick. Always keep
    # its actual identity and explicitly report whether it is current.
    if obs is not None:
        if stage == "step" and result["reason"] in {"invalid_action", "env_error", "evidence_error"}:
            previous = dict(action_index=len(record["steps"]), action=None, completed=False,
                terminated=runner.env._terminated, truncated=runner.env._truncated,
                info=result["feedback"])
        state_ref = {k: obs["state"][k] for k in ("episode_id", "state_id")}
        execution = make_execution_state(control_steps=result["control_steps"], previous=previous,
            observation_state_ref=state_ref, current_state_ref=runner._state_ref(),
            error_code=None if result["reason"] in {"policy_done", "env_terminal", "env_time_limit"}
                       else result["reason"])
        if runner.env._faulted:
            execution = freeze(dict(execution, observation_is_current=False))
        obs = freeze(dict(obs, execution_state=execution))
    notification = dict(status="absent")
    try:
        callback = getattr(policy, "on_segment_end", None)
        if callback is not None:
            if not callable(callback) or callback(obs, result) is not None:
                raise ValueError("on_segment_end(obs, result) must return None")
            notification = dict(status="delivered")
    except Exception as error:
        notification = dict(status="failed", error=runner._error(error, "policy_notification"))
    try:
        event("policy_notification", **notification)
    except Exception as error:
        runner._report["errors"].append(runner._error(error, "policy_notification_evidence"))
        runner._failed = True
        try:
            runner._save_report()
        except Exception:
            pass
    if interruption is not None:
        raise interruption
    return result
