"""Private oracle-development owner; one Env and no externally reachable server."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import traceback
from uuid import uuid4

from .contracts import METHODS, UnsupportedCapability, CalibrationError, digest, json_value, positive_int


class BoundaryStop(BaseException):
    """SegmentRunner records cancellation and releases ownership before reraising."""


class BoundedPolicy:
    def __init__(self, loaded, limit, cancelled, before_action=None):
        self.loaded, self.limit, self.cancelled = loaded, limit, cancelled
        self.before_action = before_action
        self.count = 0
        self.stop_reason = None

    def initialize(self, context):
        signature = digest(json_value(context))
        if self.loaded["initialized"]:
            if self.loaded["context"] != signature:
                raise ValueError("Policy observation contract changed; load a new policy instance")
        else:
            initialize = getattr(self.loaded["policy"], "initialize", None)
            if initialize is not None and initialize(context) is not None:
                raise ValueError("initialize must return None")
            self.loaded.update(initialized=True, context=signature)

    def act(self, observation):
        if self.cancelled() or self.count >= self.limit:
            self.stop_reason = "cancelled" if self.cancelled() else "control_step_limit"
            raise BoundaryStop(self.stop_reason)
        action = self.loaded["policy"].act(observation)
        if action is not None:
            self.count += 1
            if self.before_action is not None:
                self.before_action(action, self.loaded["policy"])
        return action

    def on_segment_end(self, observation, result):
        callback = getattr(self.loaded["policy"], "on_segment_end", None)
        if callback is not None and self.stop_reason is None:
            return callback(observation, result)


class DevelopmentOwner:
    def __init__(self, config, output, session_id, kind, send, cancelled, candidate=None):
        from .evidence import Evidence
        from .inspection import EventWindows
        from .checkpoints import Checkpoints
        from topogym.simulator.config import SimulatorConfig
        self.output, self.session_id, self.kind = Path(output), session_id, kind
        self.send, self.cancelled = send, cancelled
        self.env = self.runner = self.probe = None
        self.poisoned = False
        self.watch_cameras = {}
        self.policies = {}
        self.action_count = 0
        self.operation_id = None
        from .profiling import Profiler
        self.profiler = Profiler(send, self.profile_context)
        self.evidence = Evidence(self.output, session_id)
        self.windows = EventWindows(self.window_event, durable_events=True)
        self.checkpoints = Checkpoints(self)
        from .tracking import Tracking
        self.tracking = Tracking(self.output, send)
        from .grasp_observation import GraspTrace
        self.grasp_trace = GraspTrace(self.evidence.event)
        self.active_trial, self.grasp_trials = None, {}
        self.candidate = candidate or {}
        if self.candidate and kind != "physics":
            raise UnsupportedCapability("Material/trial candidates require a fresh physics session")
        # The actor privilege configuration is never used as a development gate.
        # This process is an owner created only by the private source-workspace API.
        self.config = SimulatorConfig(**dict(config, enable_privileged=True,
                                             work_dir=str(self.output / "scene")))
        self.progress("building_" + kind)
        start = time.monotonic()
        if kind == "physics":
            with self.profiler.span("imports"):
                from topogym.simulator import Env, SegmentRunner
                from .rendering import DevelopmentSensors
                import torch
                torch.set_num_threads(1)
            if self.config.compute_backend == "cuda" and not torch.cuda.is_available():
                raise UnsupportedCapability("CUDA is unavailable; choose explicit CPU/no-RGB or run the Nyx check on a GPU host")
            self.env = Env(self.config, sensor_factory=DevelopmentSensors)
            from .instrumentation import install
            with self.profiler.span("instrumentation_setup"):
                install(self)
            with self.profiler.span("scene_setup"):
                from .candidates import build_candidate, effective_materials
                with build_candidate(self.env, self.candidate) as declaration:
                    try:
                        self.env.reset(seed=self.config.seed)
                    finally:
                        if self.candidate:
                            self.evidence.event("candidate_declared", intervention=True, **declaration)
                if self.candidate:
                    from topogym.utils.io import write_json_atomic
                    self.candidate_report = dict(declaration, effective=effective_materials(self.env, self.candidate))
                    write_json_atomic(self.output / "candidate.json", self.candidate_report, mode=0o600)
            from topogym.simulator.rollout_simulation.policy_observation import resolve_profile
            profile = resolve_profile(self.env, mode="unlimited", settings={"rgb_camera_ids": []},
                                      state_fields=("world", "robot", "task"))
            with self.profiler.span("runner_setup"):
                self.runner = SegmentRunner(self.env, self.output / "execution", initial_profile=profile)
            self.env.add_state_sink(self.tick)
            self.env.add_transition_sink(self.transition)
            self.evidence.event("episode_started", metadata=self.env.episode_metadata)
        else:
            with self.profiler.span("geometry_setup"):
                self.get_probe()
        self.evidence.timing("startup", time.monotonic()-start)
        self.scene_revision = digest(json_value(self.env.episode_metadata)) if self.env else self.probe.scene_revision
        if self.candidate:
            self.scene_revision = digest(dict(scene=self.scene_revision, candidate=self.candidate))
        self.progress("idle")

    def window_event(self, kind, **values):
        # Evidence is durable before a potentially slow or failed screenshot.
        self.evidence.event(kind, **values)
        settings = self.watch_cameras.get(values.get("watch_id"))
        if settings and kind == "event_window_triggered":
            try:
                result = dict(keyframe=self.capture_frame(**settings))
            except Exception as error:
                result = dict(keyframe_error=dict(type=type(error).__name__, message=str(error)))
            self.evidence.event("event_keyframe", window_id=values["window_id"],
                                watch_id=values["watch_id"], **result)

    def profile_context(self):
        env = self.env
        return dict(operation_id=self.operation_id, state_ref=self.state_ref(),
                    physics_step=0 if env is None or env._world is None else env._world.physics_step,
                    control_step=0 if env is None else env._control_step)

    def state_ref(self):
        return None if self.env is None else dict(episode_id=self.env._episode_id, state_id=self.env._state_id)

    def progress(self, stage, **extra):
        row = dict(stage=stage, operation_id=self.operation_id, state_ref=self.state_ref(),
                   updated_at_monotonic=time.monotonic(),
                   control_steps_committed=self.action_count,
                   physics_step=0 if self.env is None or self.env._world is None else self.env._world.physics_step,
                   **extra)
        self.send(dict(kind="progress", progress=row))
        return row

    def tick(self, record):
        # Physics callbacks are passive; never acquire the supervisor lock here.
        grasp_events = self.grasp_trace.observe(record)
        if self.active_trial is not None:
            self.active_trial.tick(record, grasp_events)
        if self.tracking.pending is not None:
            with self.profiler.span("tracking_tick"):
                self.tracking.tick(record)
        self.send(dict(kind="progress", progress=dict(stage="physics", operation_id=self.operation_id,
            updated_at_monotonic=time.monotonic(),
            state_ref={key: record["state"][key] for key in ("episode_id", "state_id")},
            physics_step=record["state"]["physics_step"], control_steps_committed=self.action_count)))

    def transition(self, transition):
        if self.tracking.pending is not None:
            with self.profiler.span("tracking_commit"):
                self.tracking.finish(transition)
        self.action_count += 1
        self.evidence.event("control_committed", action=transition.action,
            action_count=self.action_count, physics_steps=transition.physics_steps,
            state_ref=dict(episode_id=transition.episode_id, state_id=transition.state_id))
        self.progress("control_committed")
        summary = self.summary()
        self.send(dict(kind="control_sample", sample=summary))
        self.windows.push(summary)
        if self.active_trial is not None:
            self.active_trial.transition()
        self.progress("control_boundary")

    def need_physics(self):
        if self.env is None:
            raise UnsupportedCapability("This operation requires kind='physics', not a geometric probe")

    def get_probe(self):
        if self.probe is None:
            from .geometry import RigidProbe
            self.probe = RigidProbe(self.config, self.output / ("probe_" + uuid4().hex))
            if self.env is not None:
                self.probe.sync(json_value(self.env._world.read_state()), self.state_ref())
        return self.probe

    def summary(self):
        from .inspection import contact_summary, event_summary
        world = self.env._world.read_state()
        return json_value(dict(state_ref=self.state_ref(), branch_id=self.env._branch_id,
            grasp_events=self.grasp_trace.control_events,
            **event_summary(world, self.env._robot.observe(), self.env._robot.capture_state().targets,
                            contact_summary(world, self.env._world.entities))))

    def capabilities(self):
        return dict(kind=self.kind, physics=self.env is not None,
            inspect=True, contacts=self.env is not None, event_windows=self.env is not None,
            step=self.env is not None, run_policy=self.env is not None, checkpoint=True,
            capture_frame=bool(self.env is not None and self.config.enable_rgb),
            rendering="on-demand shared Nyx SensorSuite; no RGB during control steps",
            probe_adapter=self.config.task_id == "cast_keyhole" and self.config.variation_id != "seeded",
            object_edits="detached geometry only", probe_grasp="kinematic constraint; no contact qualification",
            solve_ik=self.env is not None, check_robot_path=self.env is not None,
            dynamic_teleport=False, dynamic_pin=False, cross_process_native_checkpoint=False,
            event_preframes=False, exact_contact_point_overlay=False,
            profiling=self.profiler.coverage, newton_iterations=False, newton_residual=False,
            historical_ipc_rerender=False,
            control_tracking=self.env is not None, planning_cache=self.env is not None,
            planning_adapters=["keyhole_tcp"],
            grasp_explanation=self.env is not None, grasp_trials=self.env is not None,
            grasp_events="World-tick collection; control-boundary windows",
            material_candidates="new isolated physics sessions; frozen initial-state material edits unsupported",
            formal_eval_access=False, third_party_python_sandbox=False)

    def inspect(self, entity=None, near=None, scope="physics"):
        if self.env is None or scope == "probe":
            return self.get_probe().inspect(entity or near)
        if scope != "physics":
            raise ValueError("scope must be physics or probe")
        world = self.env._world.read_state()
        robot = self.env._robot.observe()
        target = entity or near
        if target is not None:
            if target in world["bodies"]:
                world = dict(bodies={target: world["bodies"][target]}, physics_step=world["physics_step"])
            elif target in robot:
                robot = {target: robot[target]}
                world = {}
            else:
                raise ValueError("Unknown entity or robot group")
        return dict(scope="physical_measurement", world=world, robot=robot,
                    targets=self.env._robot.capture_state().targets,
                    task=self.env._task.get_state(), action_spec=self.env.action_spec,
                    info=self.env._info(), probe_is_detached=True)

    def contacts(self, entities=None):
        self.need_physics()
        from .inspection import contact_summary
        return contact_summary(self.env._world.read_state(), self.env._world.entities, entities)

    def capture_frame(self, camera="cam_high", **options):
        self.need_physics()
        from .rendering import capture
        with self.profiler.span("capture_frame"):
            return capture(self.env, self.output / "frames", camera, **options)

    def watch(self, events, before_steps=3, after_steps=3, camera=None, near=None, overlays=()):
        self.need_physics()
        if camera is not None and (not self.config.enable_rgb or camera not in self.env._world.cameras):
            raise UnsupportedCapability("Event keyframes require an existing Nyx camera")
        if not self.windows.history:
            self.windows.history.append(self.summary())
        result = self.windows.watch(events, before_steps, after_steps)
        if camera is not None:
            self.watch_cameras[result["watch_id"]] = dict(camera=camera, near=near, overlays=overlays)
            result["frame_capture"] = "durable numerical trigger, then Nyx keyframe; pre-event window is numerical"
        return result

    def unwatch(self, watch_id):
        self.windows.watches.pop(watch_id)
        self.watch_cameras.pop(watch_id, None)
        return dict(removed=watch_id)

    def step(self, action):
        self.need_physics()
        # A projected segment has no automatic RGB recording. The ordinary
        # run_segment default intentionally records every available camera.
        owner = self
        class OneAction:
            sent = False
            def act(self, observation):
                if self.sent:
                    return None
                self.sent = True
                owner.before_action(action)
                return action
        try:
            return self.runner.run_policy(request_id=uuid4().hex, policy=OneAction(),
                submission_hash=digest(dict(one_action=action)), mode="unlimited",
                observation_profile={"rgb_camera_ids": []}, state_fields=())
        finally:
            self.tracking.finish()

    def step_until(self, event, max_control_steps=20, action=None):
        self.need_physics()
        from .inspection import triggered
        positive_int(max_control_steps, "max_control_steps")
        before = self.summary()
        triggered(event, None, before)  # Validate before moving.
        results, reason = [], "control_step_limit"
        for _ in range(max_control_steps):
            if self.cancelled():
                reason = "cancelled"
                break
            result = self.step(action or {})
            results.append(result)
            current = self.summary()
            if triggered(event, before, current):
                reason = "event"
                break
            if self.env._terminated or self.env._truncated or result["reason"] not in {"policy_done", "segment_complete"}:
                reason = result["reason"]
                break
            before = current
        return dict(reason=reason, control_steps=sum(row["control_steps"] for row in results), segments=results)

    def load_policy(self, spec):
        if not isinstance(spec, dict) or set(spec) - {"path", "factory", "kwargs"}:
            raise ValueError("policy requires path, optional factory (default make_policy), and kwargs")
        source = Path(spec["path"]).resolve()
        payload = source.read_bytes()
        signature = digest(dict(source_sha256=hashlib.sha256(payload).hexdigest(),
                                factory=spec.get("factory", "make_policy"), kwargs=spec.get("kwargs", {})))
        if signature not in self.policies:
            folder = self.output / "policies"
            folder.mkdir(exist_ok=True)
            path = folder / (signature + ".py")
            path.write_bytes(payload)
            module_spec = importlib.util.spec_from_file_location("calibration_policy_" + signature, path)
            module = importlib.util.module_from_spec(module_spec)
            import sys
            sys.modules[module_spec.name] = module
            module_spec.loader.exec_module(module)
            policy = getattr(module, spec.get("factory", "make_policy"))(**spec.get("kwargs", {}))
            if not callable(getattr(policy, "act", None)):
                raise TypeError("Policy must implement act(observation)")
            self.policies[signature] = dict(policy=policy, initialized=False, context=None)
            self.evidence.event("policy_loaded", signature=signature, source=str(source), saved_source=str(path))
        return signature, self.policies[signature]

    def run_policy(self, policy, max_control_steps=100):
        self.need_physics()
        positive_int(max_control_steps, "max_control_steps")
        started = time.monotonic()
        key, loaded = self.load_policy(policy)
        self.evidence.timing("policy_load", time.monotonic()-started)
        wrapper = BoundedPolicy(loaded, max_control_steps, self.cancelled, self.before_action)
        token = uuid4().hex
        try:
            result = self.runner.run_policy(request_id=token, policy=wrapper,
                submission_hash=digest(dict(policy=key, max_control_steps=max_control_steps)),
                mode="unlimited", observation_profile={"rgb_camera_ids": []},
                state_fields=("world", "robot", "task"))
        except BoundaryStop:
            result = self.runner._records[self.runner._requests[token]]["result"]
        finally:
            self.tracking.finish()
        return dict(result=result, development_stop_reason=wrapper.stop_reason,
                    policy_signature=key, policy_state_restorable=all(callable(getattr(loaded["policy"], name, None))
                        for name in ("save_debug_state", "load_debug_state")))

    def checkpoint(self, name, world_only=False):
        return self.checkpoints.save(name, world_only=world_only)

    def restore(self, checkpoint):
        return self.checkpoints.restore(checkpoint)

    def sync_probe(self):
        self.need_physics()
        return self.get_probe().sync(json_value(self.env._world.read_state()), self.state_ref())

    def set_object_pose(self, entity, pose, **options):
        return self.get_probe().set_pose(entity, pose, **options)

    def set_relative_pose(self, entity, reference, pose):
        return self.get_probe().set_pose(entity, pose, frame=reference)

    def pin_object(self, entity):
        return self.get_probe().pin(entity, True)

    def unpin_object(self, entity):
        return self.get_probe().pin(entity, False)

    def set_probe_grasp(self, hand, entity=None, transform=None, hand_pose=None):
        if hand_pose is None and entity is not None and self.env is not None:
            measured = self.env._robot.observe()[hand]
            hand_pose = dict(position_m=measured["tcp_position_world_m"], quaternion_wxyz=measured["tcp_orientation_wxyz"])
        return self.get_probe().grasp(hand, entity, transform, hand_pose)

    def sweep_object(self, entity, poses, **options):
        return self.get_probe().sweep(entity, poses, cancelled=self.cancelled, **options)

    def solve_ik(self, targets, seeds=None):
        self.need_physics()
        from .kinematics import solve
        return solve(self.env, targets, seeds)

    def check_robot_path(self, path, allowed_contacts=(), include_tcp=False):
        self.need_physics()
        from .kinematics import RobotGeometry
        return RobotGeometry(self.env).check(path, allowed_contacts=allowed_contacts,
                                             include_tcp=include_tcp, cancelled=self.cancelled)

    def rank_grasps(self, candidates, allowed_contacts=()):
        positive_int(len(candidates), "candidates", 1000)
        results = []
        for i, candidate in enumerate(candidates):
            if self.cancelled():
                break
            ik = self.solve_ik(candidate["targets"], candidate.get("seeds"))
            for result in ik["candidates"]:
                if result["accepted"]:
                    audit = self.check_robot_path([result["qpos"]], allowed_contacts)
                    result.update(accepted=audit["passed"], collision_audit=audit)
            results.append(dict(candidate_index=i, solutions=ik["candidates"]))
        results.sort(key=lambda row: max(((s["collision_audit"].get("minimum_environment_clearance_m") or 0.,
                                          s.get("minimum_joint_margin_rad", -1.))
                                         for s in row["solutions"] if s["accepted"]), default=(-1., -1.)), reverse=True)
        return dict(ranked=results, ranking="collision-free sampled poses, environment clearance, then joint margin",
                    scope="candidate poses only; approach path and actual grasp remain unqualified")

    def preview_geometry(self, parameters):
        return self.get_probe().preview(parameters)

    def compare_geometry(self, a, b):
        return self.get_probe().compare(a, b)

    def export_geometry_patch(self, candidate):
        return self.get_probe().export_patch(candidate)

    def timings(self):
        return dict(costs=deepcopy(self.evidence.costs), scope="wall time per tool operation, startup and policy load")

    def before_action(self, action, policy=None):
        self.grasp_trace.begin_control()
        if not any(row["active"] for row in self.tracking.records.values()):
            return
        with self.profiler.span("tracking_begin"):
            # The previous committed tick already contains all measured data.
            record = self.runner._last_tick
            self.tracking.begin(action, record, self.env.action_spec["mode"],
                segment_id=self.runner._active,
                action_index=len(self.runner._records[self.runner._active]["steps"]), policy=policy)

    def start_tracking(self, **options):
        self.need_physics()
        return self.tracking.start(self.env.tick_record(), **options)

    def tracking_report(self, tracking_id):
        return self.tracking.report(tracking_id)

    def stop_tracking(self, tracking_id):
        return self.tracking.stop(tracking_id)

    def plan_cache(self, cache_dir=None):
        from .plan_cache import PlanCache
        root = Path(__file__).resolve().parents[3]
        return PlanCache(cache_dir or root / "runs/oracle_dev/plan_cache")

    def cache_plan(self, plan_bundle, cache_dir=None):
        return self.plan_cache(cache_dir).put(plan_bundle)

    def plan_preparation(self, adapter, cache_dir):
        self.need_physics()
        from .adapters.planning import load_adapter
        from .plan_cache import PlanPreparation
        return PlanPreparation(self.plan_cache(cache_dir), load_adapter(self, adapter),
            lambda: dict(self.state_ref(), branch_id=self.env._branch_id), self.cancelled)

    def check_cached_plan(self, plan_id, tolerances, adapter="keyhole_tcp", cache_dir=None):
        return self.plan_preparation(adapter, cache_dir).check(plan_id, tolerances)

    def prepare_plan(self, request, adapter="keyhole_tcp", *, tolerances, use_cache=True, cache_dir=None):
        result = self.plan_preparation(adapter, cache_dir).prepare(request, tolerances=tolerances, use_cache=use_cache)
        self.evidence.event("plan_prepared", plan_id=result["plan_id"], selection=result["selection"],
                            timings=result["timings"], bound_state=result["bound_state"])
        return result

    def grasp_status(self, hand=None):
        self.need_physics()
        if hand is not None and hand not in self.env._robot.groups:
            raise ValueError("Unknown robot hand")
        from .grasp_observation import explain_grasp
        manager = self.env._world._grasp_manager
        return dict(explain_grasp(None if manager is None else manager.read(), hand=hand),
                    state_ref=self.state_ref(), branch_id=self.env._branch_id,
                    physics_steps_advanced=0)

    def run_grasp_trial(self, trial):
        self.need_physics()
        from .grasp_trials import GraspTrial
        from .candidates import candidate_trial
        runtime = GraspTrial(self, candidate_trial(trial, self.candidate))
        self.grasp_trials[runtime.trial_id] = str(runtime.folder / "report.json")
        self.evidence.event("grasp_trial_started", trial_id=runtime.trial_id, report=self.grasp_trials[runtime.trial_id])
        return runtime.run()

    def grasp_trial_report(self, trial_id):
        return json.loads(Path(self.grasp_trials[trial_id]).read_text())

    def export_report(self):
        return self.evidence.report(capabilities=self.capabilities(), state_ref=self.state_ref(),
                                    control_steps_committed=self.action_count, tracking=self.tracking.records,
                                    grasp_trials=self.grasp_trials, candidate=self.candidate)

    def close(self):
        self.tracking.close()
        self.windows.reset("close")
        if self.runner is not None:
            self.runner.close()
        if self.env is not None:
            self.env.close()
        self.evidence.report(capabilities=self.capabilities(), status="closed", control_steps_committed=self.action_count,
                             tracking=self.tracking.records, grasp_trials=self.grasp_trials, candidate=self.candidate)
        self.evidence.close()
        self.profiler.close()
        return dict(closed=True)

    def dispatch(self, method, params, operation_id):
        if self.poisoned and method not in {"close", "timings", "export_report"}:
            raise CalibrationError("Owner state is inconsistent; restart the worker")
        self.operation_id = operation_id
        self.progress(method)
        intervention = method in {"set_object_pose", "set_relative_pose", "pin_object", "unpin_object", "set_probe_grasp", "preview_geometry"}
        self.evidence.event("operation_started", intervention=intervention,
                            operation_id=operation_id, method=method, params=params, state_ref=self.state_ref())
        start = time.monotonic()
        try:
            with self.profiler.span("operation", method=method):
                result = getattr(self, method)(**params)
            if method != "close":
                self.evidence.event("operation_completed", operation_id=operation_id, state_ref=self.state_ref())
            return json_value(dict(result, session_id=self.session_id, operation_id=operation_id,
                                   scene_revision=self.scene_revision,
                                   source_state_ref=self.state_ref(), exploration=self.evidence.exploration,
                                   formal_qualification=False))
        finally:
            self.evidence.timing(method, time.monotonic()-start)
            if method != "close":
                self.progress("idle")


def worker_main(pipe, cancel, config, output, session_id, kind, candidate=None):
    if os.name == "posix":
        os.setsid()
    os.umask(0o077)
    # Native compiler/solver output can be large; keep it with owned artifacts.
    with open(Path(output) / "worker.log", "a", buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        owner = None
        try:
            owner = DevelopmentOwner(config, output, session_id, kind, pipe.send, cancel.is_set, candidate=candidate)
            pipe.send(dict(kind="ready", progress=owner.progress("idle")))
            while True:
                request = pipe.recv()
                operation_id = request["operation_id"]
                try:
                    if request.get("session_id") != session_id or request["method"] not in METHODS:
                        raise PermissionError("Invalid private session request")
                    result = owner.dispatch(request["method"], request["params"], operation_id)
                    pipe.send(dict(kind="result", operation_id=operation_id, result=result))
                    if request["method"] == "close":
                        owner = None
                        break
                except Exception as error:
                    traceback.print_exc()
                    pipe.send(dict(kind="result", operation_id=operation_id,
                                   error=dict(type=type(error).__name__, message=str(error))))
        except EOFError:
            pass
        except BaseException as error:
            traceback.print_exc()
            try:
                pipe.send(dict(kind="startup_error", error=dict(type=type(error).__name__, message=str(error))))
            except (BrokenPipeError, EOFError, OSError):
                pass
        finally:
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    traceback.print_exc()
            pipe.close()
