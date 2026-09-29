"""Episode-bound sequences of existing control steps, with continuous evidence."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import Lock, get_ident
from uuid import uuid4
import json
import weakref

from topogym.utils.io import to_jsonable, write_json_atomic, relative_file
from topogym.utils.snapshots import freeze
from .segment_contract import SegmentError, action_copy, fingerprint, public_info, request_id
from .evidence import SegmentEvidence, EvidenceError
from .artifacts import ArtifactStore
from .history import SegmentHistory


class SegmentRunner:
    """Owner creates after reset; one runner owns one episode until close/reset.

    Public handles cannot reset, construct, or close Env. This is a local API
    permission boundary, not isolation from untrusted code in the same process.
    """

    def __init__(self, env, output_root, *, prepared_output=False,
                 initial_observation_steps=0, initial_profile=None):
        if type(initial_observation_steps) is not int or not 0 <= initial_observation_steps <= 1000:
            raise ValueError("initial_observation_steps must be an integer in [0, 1000]")
        if initial_profile is not None:
            from .policy_observation import ObservationProfile
            if not isinstance(initial_profile, ObservationProfile):
                raise TypeError("initial_profile must be a validated observation profile")
            if initial_profile.mode == "unlimited" and not env.config.enable_privileged:
                raise PermissionError("Privileged access is disabled")
        env._require_ready()
        if env._execution_guard is not None:
            raise RuntimeError("An execution owner is already attached")
        self.env = env
        self.episode_id = env._episode_id
        self.root = Path(output_root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("Output directories cannot be symlinks")
        self.root.mkdir(parents=True, exist_ok=prepared_output, mode=0o700)
        if prepared_output:
            reserved = {"report.json", "segments", "private", "rgb", "recording", "views",
                        "config.json", "asset_manifest.json", "source_manifest.json"}
            if any(p.name in reserved or p.name.startswith("segment_") for p in self.root.iterdir()):
                raise FileExistsError("Output contains existing simulator artifacts")
        # A prepared rollout may contain source_snapshot and run_report.json.
        # Exclusive reservation prevents concurrent writers or reuse after failure.
        (self.root / ".segment_runner").mkdir(mode=0o700)
        self._lock = Lock()
        self._executing_thread = None
        self._dispatch_thread = self._manager_thread = None
        self._active = None
        self._records = {}
        self._requests = {}
        self._closed = self._failed = False
        self._initializing = True
        self._subscriptions = []
        self._evidence = None
        self._interaction = env.interaction()
        self._artifacts = ArtifactStore(self.root)
        self._last_tick = None
        self._report = dict(schema_version=1, episode_id=self.episode_id, status="running",
                            segments=[], errors=[], enable_rgb=env.config.enable_rgb)
        try:
            if not env._mutation_lock.acquire(blocking=False):
                raise SegmentError("execution_busy")
            try:
                env._require_ready()
                if env._episode_id != self.episode_id:
                    raise SegmentError("episode_expired")
                if env._execution_guard is not None:
                    raise SegmentError("An execution owner is already attached")
                env._execution_guard = self._guard
            finally:
                env._mutation_lock.release()
            self._save_report()
            self._evidence = SegmentEvidence(self.root, env)
            self._tick(env.tick_record(), segment_id=0)
            self._subscriptions = [env.add_state_sink(self._tick),
                                   env.add_transition_sink(self._transition),
                                   env.add_lifecycle_sink(self._lifecycle)]
            if env.config.enable_rgb:
                self._subscriptions.append(env.add_frame_sink(self._frame))
            self._initializing = False
            self.initial = self._dispatch(self._initialize, initial_observation_steps, initial_profile)
        except BaseException as error:
            self._report["errors"].append(self._error(error, "initialize"))
            self._report["status"] = "incomplete"
            self._detach()
            self._save_report()
            raise

    def interaction(self, *, privileged=False):
        self._check()
        # Use the existing owner authorization check, including strict bools.
        access = self.env.interaction(privileged=privileged)
        return SegmentInteraction(self, access, privileged)

    def _initialize(self, steps, profile):
        descriptor = self._begin("initial-observation", profile=profile, initial=True)
        token = descriptor["token"]
        for _ in range(steps):
            if self.env._terminated or self.env._truncated:
                break
            try:
                self._step(0, token, {}, None, finalize_terminal=False)
            except SegmentError:
                # Preserve a sealed failure for diagnostics; readiness must reject it.
                if self._records[0]["result"] is None:
                    raise
                break
        reason = ("env_terminal" if self.env._terminated else
                  "env_time_limit" if self.env._truncated else "initial_observation")
        return self._end(0, token, reason=reason)

    def run_policy(self, *, request_id, policy, submission_hash, mode="limited",
                   observation_profile=None, state_fields=()):
        """Run one submitted passive policy; this manager API owns all steps.

        The manager hashes the submitted source and parameters. Repeating that
        identity returns the sealed result without invoking the policy again.
        """
        from .policy import execute_policy
        return self._dispatch(execute_policy, self, request_id, policy,
                              submission_hash=submission_hash, mode=mode,
                              observation_profile=observation_profile, state_fields=state_fields)

    def _policy_inputs(self, state_fields=(), access=None):
        observation = self._interaction.observe()
        proprioception = self.env._sensors.proprioception()
        privileged = {name: access.get(name) for name in state_fields}
        return observation, proprioception, privileged

    def _check(self):
        if self._closed or self.env._closed or self.env._episode_id != self.episode_id:
            raise SegmentError("episode_expired")

    def _dispatch(self, operation, *args, **kwargs):
        self._check()
        if not self._lock.acquire(blocking=False):
            raise SegmentError("execution_busy")
        try:
            self._check()
            self._dispatch_thread = get_ident()
            return operation(*args, **kwargs)
        finally:
            self._dispatch_thread = None
            self._lock.release()

    def _guard(self, operation):
        if self._initializing:
            raise SegmentError("execution_busy")
        if operation == "step" and self._executing_thread != get_ident():
            raise SegmentError("Use the active segment interaction for steps")
        if operation in {"reset", "close", "_restore"}:
            # Actor rewind already owns this lock. Manager mutations reserve it
            # through the whole Env mutation, including lifecycle callbacks.
            nested_rewind = operation == "_restore" and self._dispatch_thread == get_ident()
            if not nested_rewind and not self._lock.acquire(blocking=False):
                raise SegmentError("execution_busy")
            if operation == "_restore" and self._active is not None:
                if not nested_rewind:
                    self._lock.release()
                raise SegmentError("End the active segment before rewind")
            if not nested_rewind:
                self._manager_thread = get_ident()
                def release():
                    self._manager_thread = None
                    self._lock.release()
                return release

    def _state_ref(self):
        return dict(episode_id=self.episode_id, state_id=self.env._state_id)

    @staticmethod
    def _error(error, stage):
        return dict(stage=stage, type=type(error).__name__, message=str(error))

    def _save_report(self):
        report = dict(self._report)
        if self._evidence is not None:
            report["statistics"] = self._evidence.statistics()
        write_json_atomic(self.root / "report.json", report)

    def _tick(self, record, *, segment_id=None):
        self._last_tick = record
        identity = self._active if segment_id is None else segment_id
        self._evidence.tick(record, segment_id=identity)
        active = self._records.get(identity)
        if active is not None and active.get("history") is not None:
            active["history"].tick(record, action=active.get("current_action"),
                                   action_index=len(active["steps"]))

    def _transition(self, transition):
        self._evidence.write("control_steps", dict(kind="completed", segment_id=self._active,
            action_index=len(self._records[self._active]["steps"]),
            state_ref=self._state_ref(), physics_steps=transition.physics_steps,
            action_duration_s=transition.action_duration_s, info=transition.info,
            reward=transition.reward, terminated=transition.terminated, truncated=transition.truncated))
        self._records[self._active]["history"].event("completed",
            action_index=len(self._records[self._active]["steps"]),
            state_ref=self._state_ref(), physics_steps=transition.physics_steps,
            feedback=public_info(transition.info))

    def _frame(self, frame):
        record = self._records[self._active]
        if record["media"] is None:
            return
        try:
            record["media"].append(self._select_frame(frame, record["camera_ids"]))
        except Exception as error:
            raise EvidenceError("Frame recording failed") from error

    def _lifecycle(self, event):
        self._evidence.write("history_events", event)
        if event["kind"] in {"before_reset", "close"}:
            self._close(reason="cancelled")
        elif event["kind"] == "rewind":
            self._last_tick = self.env.tick_record()
            for record in self._records.values():
                if record["media"] is not None:
                    record["media"].session.on_lifecycle(event)

    @staticmethod
    def _select_frame(frame, camera_ids):
        if camera_ids is None:
            return frame
        from dataclasses import replace
        return replace(frame, rgb=freeze({name: frame.rgb[name] for name in camera_ids}),
                       camera_metadata=freeze({name: frame.camera_metadata[name] for name in camera_ids}))

    def _begin(self, identifier, *, signature=None, camera_ids=None, profile=None, initial=False):
        request_id(identifier)
        if identifier in self._requests:
            record = self._records[self._requests[identifier]]
            if record["signature"] != signature:
                raise SegmentError("request_id_conflict")
            return self._descriptor(record)
        if self._failed:
            raise SegmentError("runner_faulted")
        if self._active is not None:
            raise SegmentError("segment_already_active")
        self.env._require_ready()
        if not initial and (self.env._terminated or self.env._truncated):
            raise SegmentError("episode_ended")
        identity = 0 if initial else max(self._records, default=0) + 1
        self.env._checkpoint_current()   # "segment" history: a segment start is a rewind target
        if profile is not None:
            camera_ids = profile.rgb_camera_ids
        record = dict(segment_id=identity, request_id=identifier, token=uuid4().hex,
                      signature=signature, status="active", start=self._state_ref(),
                      start_tick=self.env._world.physics_step,
                      start_control_step=self.env._control_step,
                      start_time=self.env._world.sim_time_s, branch_id=self.env._branch_id,
                      steps=[], media=None, history=None, result=None, errors=[], camera_ids=camera_ids,
                      profile=profile, current_action=None)
        self._records[identity] = record
        self._requests[identifier] = identity
        self._active = identity
        try:
            if self.env.config.enable_rgb and camera_ids != ():
                from topogym.recording.segment import SegmentMedia
                record["media"] = SegmentMedia(self.root, identity,
                    self._select_frame(self.env.sensor_frame(), camera_ids))
            record["history"] = SegmentHistory(self.root, identity, profile)
            record["history"].tick(self._last_tick, initial=True)
            write_json_atomic(self.root / f"segments/segment_{identity}/result.json", self._descriptor(record))
            self._evidence.write("control_steps", dict(kind="begin", segment_id=identity,
                request_id=identifier, state_ref=record["start"]))
            return self._descriptor(record)
        except BaseException as error:
            record["errors"].append(self._error(error, "begin"))
            self._failed = True
            self._end(identity, record["token"], reason="evidence_error")
            raise SegmentError("evidence_error") from None

    def _descriptor(self, record):
        return freeze({key: record[key] for key in
                       ("segment_id", "request_id", "token", "status", "start", "branch_id")})

    def _record(self, identity, token):
        record = self._records.get(identity)
        if record is None or token != record["token"]:
            raise SegmentError("invalid_segment_token")
        return record

    def _step(self, identity, token, action, sequence, *, finalize_terminal=True):
        record = self._record(identity, token)
        if sequence is None:
            sequence = len(record["steps"])
        if type(sequence) is not int or sequence < 0 or sequence > len(record["steps"]):
            raise SegmentError("invalid_action_sequence")
        try:
            action = action_copy(action)
            signature = fingerprint(action)
            if sequence < len(record["steps"]):
                previous = record["steps"][sequence]
                if signature != previous["signature"]:
                    raise SegmentError("action_sequence_conflict")
                return previous["result"]
            if record["status"] != "active" or self._active != identity:
                raise SegmentError("segment_not_active")
            self._evidence.write("control_steps", dict(kind="requested", segment_id=identity,
                action_index=sequence, action=action, state_ref=self._state_ref()))
            record["history"].event("requested", action_index=sequence,
                action=action, state_ref=self._state_ref())
            record["current_action"] = freeze(action)
            self._executing_thread = get_ident()
            try:
                result = self._interaction.step(action)
            finally:
                self._executing_thread = None
            record["steps"].append(dict(signature=signature, action=freeze(action), result=result))
        except SegmentError:
            raise
        except BaseException as error:
            evidence_failure = (isinstance(error, EvidenceError) or
                                (self.env._faulted and self.env._stage in {"state_output", "output"}))
            reason = ("evidence_error" if evidence_failure else
                      "env_error" if self.env._faulted else "invalid_action")
            self._failed |= reason != "invalid_action"
            record["errors"].append(self._error(error, self.env._stage))
            if self.env._fault_detail is not None:
                record["errors"][-1]["environment_fault"] = dict(self.env._fault_detail)
            try:
                self._evidence.write("control_steps", dict(kind="failed", segment_id=identity,
                    action_index=sequence, reason=reason, error=record["errors"][-1],
                    last_saved_state_ref=self._state_ref()))
                record["history"].event("failed", action_index=sequence, reason=reason,
                                         state_ref=self._state_ref())
            except Exception as evidence_error:
                record["errors"].append(self._error(evidence_error, "error_evidence"))
                self._failed = True
            self._end(identity, token, reason=reason)
            raise SegmentError(reason) from None
        if finalize_terminal and (result[2] or result[3]):
            self._end(identity, token, reason="env_terminal" if result[2] else "env_time_limit")
        return result

    def _end(self, identity, token, *, reason="segment_complete"):
        record = self._record(identity, token)
        if record["result"] is not None:
            return record["result"]
        if self._active != identity:
            raise SegmentError("segment_not_active")
        record["status"] = "finalizing"
        media, media_result = record["media"], {}
        complete = reason not in {"env_error", "evidence_error", "observation_error"}
        try:
            if media is not None:
                # A simulation error may leave the last RGB before the last tick.
                media_result = media.finish(complete=not media.session.failed)
        except BaseException as error:
            record["errors"].append(self._error(error, "media_finalize"))
            complete = False
            self._failed = True
            if reason == "segment_complete":
                reason = "evidence_error"
            try:
                media.abort()
            except Exception as close_error:
                record["errors"].append(self._error(close_error, "media_close"))
        state = self._last_tick["state"]
        end = dict(episode_id=self.episode_id, state_id=state["state_id"])
        if not self.env._faulted:
            feedback = public_info(self.env._info())
        elif record["steps"]:
            feedback = record["steps"][-1]["result"][4]
        else:
            feedback = freeze(dict(evaluation_status="unavailable", task_success=None))
        public = dict(schema_version=2, segment_id=identity, request_id=record["request_id"],
            episode_id=self.episode_id, branch_id=record["branch_id"],
            status="complete" if complete else "incomplete", reason=reason,
            start_state_ref=record["start"], end_state_ref=end,
            control_steps=len(record["steps"]),
            attempted_control_steps=self.env._control_step-record["start_control_step"],
            physics_steps=self.env._world.physics_step-record["start_tick"],
            saved_physics_steps=state["physics_step"]-record["start_tick"],
            uncheckpointed_physics_steps=self.env._world.physics_step-state["physics_step"],
            simulated_duration_s=self.env._world.sim_time_s-record["start_time"],
            physics_tick_complete=complete, control_step_complete=not self.env._faulted,
            evidence_complete=complete, feedback=feedback, media={}, logs={})
        if identity == 0:
            public["state_ref"] = end  # Initial observation ends at the first policy's start.
        try:
            if "policy" in record:
                metadata = record["policy"]
                metadata.update(reason=reason, control_steps=len(record["steps"]),
                    start_state_ref=record["start"], end_state_ref=end, errors=record["errors"],
                    status=("finished" if reason == "policy_done" else "stopped_by_env"
                            if reason in {"env_terminal", "env_time_limit"} else "failed"))
                self._evidence.write_policy_report(identity, metadata)
            public["media"]["videos"] = {name: self._artifacts.add(path)
                for name, path in media_result.get("videos", {}).items()}
            if "frame_map" in media_result:
                public["media"]["frame_map"] = self._artifacts.add(media_result["frame_map"])
            for key in ("camera_order", "frame_count", "presentation_padding_frames", "final_frame_state_id",
                        "initial_frame_state_id", "initial_frame_sha256", "final_frame_sha256", "fps"):
                if key in media_result:
                    public["media"][key] = media_result[key]
            history = record["history"]
            if history is None:
                raise EvidenceError("Segment history is unavailable")
            history.event("end", reason=reason, state_ref=end)
            profile = record["profile"]
            fields = profile.state_fields if profile else ()
            public["logs"] = {kind: self._artifacts.add(path, required_state_fields=fields)
                              for kind, path in history.finish().items()}
            public["history"] = dict(**history.counts, mode=profile.mode if profile else "limited",
                                     privileged_fields=list(profile.state_fields) if profile else [])
            self._evidence.write("control_steps", dict(kind="end", segment_id=identity,
                reason=reason, end_state_ref=end, errors=record["errors"]))
        except BaseException as error:
            record["errors"].append(self._error(error, "finalize_evidence"))
            public.update(status="incomplete", evidence_complete=False)
            public["physics_tick_complete"] = False
            self._failed = True
            if record["history"] is not None:
                try:
                    record["history"].close()
                except Exception:
                    pass
        record["status"] = public["status"]
        record["result"] = freeze(public)
        self._active = None
        self._report["segments"].append(dict(result=public, errors=record["errors"]))
        if self._failed:
            self._report["status"] = "incomplete"
        try:
            # Publish the public completion marker only after owner evidence.
            self._save_report()
            write_json_atomic(self.root / f"segments/segment_{identity}/result.json", public)
        except Exception as error:
            self._failed = True
            self._report["status"] = "incomplete"
            record["errors"].append(self._error(error, "manifest_finalize"))
            public.update(status="incomplete", evidence_complete=False)
            public["physics_tick_complete"] = False
            record["result"] = freeze(public)
            try:
                write_json_atomic(self.root / f"segments/segment_{identity}/result.json", public)
                self._save_report()
            except Exception:
                pass  # A persistent storage failure cannot publish completion.
        return record["result"]

    def _run(self, identifier, actions):
        if not isinstance(actions, (list, tuple)):
            raise ValueError("actions must be a list or tuple")
        actions = [action_copy(action) for action in actions]
        self._validate_batch(actions)
        descriptor = self._begin(identifier, signature=fingerprint(actions))
        identity, token = descriptor["segment_id"], descriptor["token"]
        record = self._records[identity]
        if record["result"] is not None:
            return record["result"]
        for index, action in enumerate(actions):
            self._step(identity, token, action, index)
            if record["result"] is not None:
                break
        return self._end(identity, token)

    def _validate_batch(self, actions):
        """Reject static mistakes before execution; resolve deltas/IK per step."""
        import numpy as np
        if self.env.config.control_mode == "JOINT_ABS":
            for action in actions:
                self.env._robot.validate_action(action)
            return
        spec = self.env.action_spec
        for action in actions:
            if set(action) - spec["groups"].keys():
                raise ValueError("Unknown robot action group")
            for name, values in action.items():
                group = spec["groups"][name]
                if not isinstance(values, Mapping) or not values or set(values) - group["fields"].keys():
                    raise ValueError("Invalid action fields")
                for field, value in values.items():
                    if list(np.asarray(value).shape) != group["fields"][field]:
                        raise ValueError("Invalid action shape")
                grip = group["gripper_field"]
                if grip in values and not group["gripper_limits"][0] <= values[grip] <= group["gripper_limits"][1]:
                    raise ValueError("Invalid gripper target")
                pose_fields = set(values) - {grip}
                if spec["mode"] == "EE_ABS" and pose_fields and pose_fields != {"position_world_m", "orientation_wxyz"}:
                    raise ValueError("EE_ABS requires a complete pose")
                if "orientation_wxyz" in values and not np.isclose(np.linalg.norm(values["orientation_wxyz"]), 1., atol=1e-6, rtol=0):
                    raise ValueError("Quaternion must have unit norm")

    def _logs(self, identity, kind, *, start=0, limit=100):
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ValueError("Evidence root cannot be a symlink")
        if type(identity) is not int or identity not in (0, *self._records):
            raise ValueError("Unknown segment ID")
        if kind not in {"control_steps", "physics_states", "history_events"}:
            raise ValueError("Unknown log kind")
        if type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Invalid log page")
        values, matched = [], 0
        path = relative_file(self.root, f"private/{kind}.jsonl")
        with path.open() as stream:
            for line in stream:
                value = json.loads(line)
                if kind == "history_events" or value.get("segment_id") == identity:
                    if matched >= start:
                        values.append(value)
                    matched += 1
                    if len(values) == limit:
                        break
        return freeze(values)

    def _array(self, chunk_id, key):
        import numpy as np
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ValueError("Evidence root cannot be a symlink")
        if type(chunk_id) is not int or not 0 <= chunk_id < self._evidence.array_chunks:
            raise ValueError("Unknown array chunk ID")
        path = relative_file(self.root, f"private/arrays/chunk_{chunk_id:08d}.npz")
        with np.load(path, allow_pickle=False) as chunk:
            if not isinstance(key, str) or key not in chunk.files:
                raise ValueError("Unknown array key")
            return freeze(chunk[key])

    def _detach(self):
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()
        if self.env._execution_guard == self._guard:
            self.env._execution_guard = None
        if self._evidence is not None:
            self._evidence.close()
        self._closed = True

    def _close(self, *, reason="cancelled"):
        if self._active is not None:
            record = self._records[self._active]
            self._end(self._active, record["token"], reason=reason)
        self._report["status"] = "incomplete" if self._failed else "complete"
        try:
            self._save_report()
        finally:
            self._detach()

    def close(self):
        if not self._closed:
            self._dispatch(self._close)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class SegmentInteraction:
    __slots__ = ("__owner", "__access", "__privileged", "__segment")

    def __init__(self, runner, access, privileged):
        self.__owner = weakref.ref(runner)
        self.__access = access
        self.__privileged = privileged
        self.__segment = None

    def _runner(self):
        runner = self.__owner()
        if runner is None:
            raise SegmentError("episode_expired")
        runner._check()
        return runner

    @property
    def action_spec(self):
        self._runner()
        return self.__access.action_spec

    @property
    def observation_spec(self):
        self._runner()
        return self.__access.observation_spec

    @property
    def timing_spec(self):
        self._runner()
        return self.__access.timing_spec

    @property
    def initial(self):
        return self._runner().initial

    def observe(self):
        runner = self._runner()
        return runner._dispatch(self.__access.observe)

    def render(self):
        runner = self._runner()
        return runner._dispatch(self.__access.render)

    def is_solved(self):
        runner = self._runner()
        return runner._dispatch(self.__access.is_solved)

    def begin_segment(self, *, request_id):
        runner = self._runner()
        self.__segment = runner._dispatch(runner._begin, request_id)
        return self.__segment

    def step(self, action, *, sequence=None):
        runner = self._runner()
        if self.__segment is None:
            raise SegmentError("no_active_segment")
        return runner._dispatch(runner._step, self.__segment["segment_id"],
                                self.__segment["token"], action, sequence)

    def end_segment(self):
        runner = self._runner()
        if self.__segment is None:
            raise SegmentError("no_active_segment")
        return runner._dispatch(runner._end, self.__segment["segment_id"], self.__segment["token"])

    def run_segment(self, *, request_id, actions):
        runner = self._runner()
        return runner._dispatch(runner._run, request_id, actions)

    def rewind_to(self, state_ref):
        runner = self._runner()
        return runner._dispatch(self.__access.rewind_to, state_ref)

    def get(self, name):
        runner = self._runner()
        return runner._dispatch(self.__access.get, name)

    def get_log(self, segment_id, kind, *, start=0, limit=100):
        runner = self._runner()
        if not self.__privileged:
            raise PermissionError("Detailed logs require privilege")
        return runner._dispatch(runner._logs, segment_id, kind, start=start, limit=limit)

    def get_log_array(self, chunk_id, key):
        runner = self._runner()
        if not self.__privileged:
            raise PermissionError("Detailed logs require privilege")
        return runner._dispatch(runner._array, chunk_id, key)

    def read_artifact(self, artifact_id):
        runner = self._runner()
        return runner._artifacts.read(artifact_id, privileged=self.__privileged)
