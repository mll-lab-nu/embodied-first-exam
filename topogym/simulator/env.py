"""The local simulator lifecycle with complete physical-tick episode history."""

from __future__ import annotations
from dataclasses import asdict

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import weakref
from functools import wraps
from threading import Lock

import numpy as np

from topogym.config import SimulatorConfig
from topogym.config.registry import (
    SEEDED_VARIATION,
    task_definition,
    task_registration,
    require_task_support,
    variation_registration,
    variation_gaps,
)
from topogym.utils.snapshots import freeze, thaw
from topogym.simulator.history import EpisodeHistory, EpisodeState, StateInfo
from topogym.simulator.history import Transition


def _mutation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Concurrent or reentrant Env mutation is forbidden")
        release_owner = None
        try:
            if self._execution_guard is not None:
                release_owner = self._execution_guard(method.__name__)
            return method(self, *args, **kwargs)
        finally:
            if release_owner is not None:
                release_owner()
            self._mutation_lock.release()
    return guarded


class Env:
    """Coordinate Task, Robot, World and Sensors; no agent or transport dependency.

    Every successfully completed physical tick is retained on one valid path.
    Privileged rewind restores a tick and discards its old future. reset(seed=...)
    creates a new episode and releases old history. Only the owner receives Env;
    interaction handles deliberately have no reset or scene-construction API.
    Only one built Env may be active in a process because Genesis and its RNGs
    are process-wide. Complete history intentionally has no implicit eviction.
    """

    _active_env = None

    def __init__(self, config: SimulatorConfig | None = None, *, sensor_factory=None):
        self._config = config or SimulatorConfig()
        # Owner-only construction extension. Operator handles and formal
        # defaults remain unchanged; adapters must preserve state identities.
        if sensor_factory is not None and not callable(sensor_factory):
            raise TypeError("sensor_factory must be callable")
        self._sensor_factory = sensor_factory
        # "seeded" picks its tier from the episode seed; without a configured
        # seed the tier is known only at reset.
        self._variation = self._task_class = None
        if self.config.variation_id != SEEDED_VARIATION or self.config.seed is not None:
            self._variation = variation_registration(self.config.task_id, self.config.variation_id, self.config.seed)
            self._task_class = task_definition(self.config.task_id, self._variation["variation_id"])
        self._scene_variation = None
        self._world = self._robot = self._task = self._sensors = None
        self._history = None
        self._temporary = None
        self._closed = False
        self._faulted = False
        self._fault_detail = None
        self._stage = "created"
        self._episode_id = ""
        self._branch_id = 0
        self._branch_parent_state_id = None
        self._state_id = None
        self._control_step = 0
        self._terminated = self._truncated = False
        self._rng = np.random.default_rng()
        self._seed = self.config.seed
        self._transition_sinks = []
        self._frame_sinks = []
        self._lifecycle_sinks = []
        self._state_sinks = []
        self._mutation_lock = Lock()
        self._execution_guard = None
        self.last_transition = None
        # True: observations skip the camera pass and sensor_frame()/render() render the current state when first asked
        # (for consumers that take frames only from those two). Physics never reads the cameras.
        self.defer_rgb = False

    @property
    def config(self):
        return self._config

    @property
    def timing_spec(self):
        return freeze(dict(physics_dt_s=self.config.physics_dt_s,
                           control_decimation=self.config.control_decimation,
                           control_dt_s=self.config.physics_dt_s * self.config.control_decimation))

    def add_state_sink(self, callback):
        """Subscribe to committed ticks; callbacks receive detached measurements."""
        if not callable(callback):
            raise TypeError("state sink must be callable")
        self._state_sinks.append(callback)
        def unsubscribe():
            if callback in self._state_sinks:
                self._state_sinks.remove(callback)
        return unsubscribe

    def tick_record(self, *, world_state=None):
        """Owner-only readable measurements, never a restorable engine snapshot."""
        from dataclasses import asdict
        self._require_ready()
        saved = self._history.get(self._state_id)
        state = asdict(saved.info)
        state["branch_id"] = self._branch_id
        return freeze(dict(schema_version=1, state=state,
                           world=self._world.read_state() if world_state is None else world_state,
                           robot=self._robot.observe(), targets=saved.robot.targets,
                           task=saved.task,
                           coverage=dict(checkpoint_exported=False, ipc_contact_coverage=False,
                                         actuator_force_coverage=False)))

    @property
    def privileged(self):
        from .privileged import PrivilegedAccess
        if not self.config.enable_privileged:
            raise PermissionError("Privileged access is disabled")
        return PrivilegedAccess(self)

    def interaction(self, *, privileged=False):
        """Grant an episode-bound interface without reset/close/config setters."""
        from .interaction import Interaction
        self._require_ready()
        if type(privileged) is not bool:
            raise ValueError("privileged must be a boolean")
        if privileged and not self.config.enable_privileged:
            raise PermissionError("Privileged access is disabled")
        return Interaction(self, privileged=privileged)

    def add_lifecycle_sink(self, callback):
        if not callable(callback):
            raise TypeError("lifecycle sink must be callable")
        self._lifecycle_sinks.append(callback)
        def unsubscribe():
            if callback in self._lifecycle_sinks:
                self._lifecycle_sinks.remove(callback)
        return unsubscribe

    def _emit_lifecycle(self, kind, **payload):
        event = freeze(dict(kind=kind, episode_id=self._episode_id,
                            branch_id=self._branch_id, state_id=self._state_id, **payload))
        for callback in tuple(self._lifecycle_sinks):
            callback(event)

    def support_report(self):
        """Describe missing capabilities without building a scene."""
        from dataclasses import asdict

        result = asdict(task_registration(self.config.task_id))
        result["variation"] = deepcopy(self._variation)
        result["gaps"] = (*result["gaps"], *(asdict(g) for g in
                            variation_gaps(self.config.task_id, self.config.variation_id, self._seed)))
        result["grasp_assist"] = asdict(self.config.grasp_assist)
        return result

    @property
    def state_history(self) -> tuple[StateInfo, ...]:
        """Metadata only: callers cannot mutate saved engine buffers."""
        return () if self._history is None else self._history.states()

    @property
    def action_spec(self):
        from topogym.robot.control import action_spec
        if self._robot is not None:
            description = self._robot.description
        else:
            from topogym.config.scene import load_scene_config
            from topogym.robot.description import describe_robot
            description = describe_robot(load_scene_config(self.config).robot_control)
        spec = action_spec(description, self.config.control_mode)
        # Static execution rules are public; ownership/contact truth stays in
        # the owner-only state stream. Both policy privilege levels use these rules.
        spec["grasp_assist"] = asdict(self.config.grasp_assist)
        return spec

    @property
    def observation_spec(self):
        from topogym.sensors.observation import observation_spec
        from topogym.config.scene import load_scene_config
        return observation_spec(self.action_spec, self.config, load_scene_config(self.config))

    @property
    def episode_metadata(self):
        self._require_ready()
        return freeze(
            dict(
                episode_id=self._episode_id,
                branch_id=self._branch_id,
                branch_parent_state_id=self._branch_parent_state_id,
                task_id=self.config.task_id,
                instance_id=self._task.instance_id,
                seed=self._seed,
                variation_id=self.config.variation_id,
                canonical_variation_id=self._variation["variation_id"],
                family_id=self._task.family_id,
                model_revision=self._task.model_revision,
                terminal=self._task.terminal_metadata(),
                difficulty_target=self._task.difficulty,
                variation_resource_sha256=self._task.resource_hashes,
                asset_sha256=dict(self._asset_build.sha256),
                robot_id=self._robot.description.robot_id,
                physics_engine="genesis",
                compute_backend=self.config.compute_backend,
                max_physics_steps=self.config.max_physics_steps,
                reset_physics_steps=self.config.reset_physics_steps,
                history="current episode valid physical ticks; rewind discards future",
                observation_mode=self.config.observation_mode,
                control_mode=self.config.control_mode,
                random_stream_version=1,
                scene_variation=deepcopy(self._scene_variation),
                initial_state=deepcopy(self._initial_state_report),
                grasp_assist=asdict(self.config.grasp_assist),
            )
        )

    def add_transition_sink(self, callback):
        """Attach a passive consumer, not a replacement step implementation."""
        if not callable(callback):
            raise TypeError("transition sink must be callable")
        self._transition_sinks.append(callback)
        return lambda: self.remove_transition_sink(callback)

    def remove_transition_sink(self, callback):
        if callback in self._transition_sinks:
            self._transition_sinks.remove(callback)

    def add_frame_sink(self, callback):
        if not self.config.enable_rgb:
            raise ValueError("RGB must be enabled before adding a frame consumer")
        if not callable(callback):
            raise TypeError("frame sink must be callable")
        self._frame_sinks.append(callback)
        return lambda: self.remove_frame_sink(callback)

    def remove_frame_sink(self, callback):
        if callback in self._frame_sinks:
            self._frame_sinks.remove(callback)

    @_mutation
    def reset(self, *, seed: int | None = None):
        if self._closed:
            raise RuntimeError("Env is closed")
        if seed is not None and (
            isinstance(seed, bool)
            or not isinstance(seed, (int, np.integer))
            or not 0 <= seed < 2**32
        ):
            raise ValueError("seed must be an integer in [0, 2**32)")
        import secrets
        episode_seed = int(seed) if seed is not None else (
            self.config.seed if self.config.seed is not None else secrets.randbits(32))
        variation, task_class = self._variation, self._task_class
        if self.config.variation_id == SEEDED_VARIATION:
            variation = variation_registration(self.config.task_id, SEEDED_VARIATION, episode_seed)
            task_class = task_definition(self.config.task_id, variation["variation_id"])
        require_task_support(self.config.task_id, "reset", variation["variation_id"])
        if task_class.physics_model == "fem_ipc":
            from topogym.world.physics.ipc import require_episode_checkpoint
            require_episode_checkpoint(self.config.compute_backend)
        active = self._active_env() if self._active_env is not None else None
        if active is not None and active is not self:
            raise RuntimeError(
                "Close the active Env before building another in this process"
            )
        previous_episode_id = self._episode_id
        if previous_episode_id:
            self._emit_lifecycle("before_reset")
        self._release_world()
        self._history = None
        self._faulted = False
        self._fault_detail = None
        self._stage = "reset"
        self._variation, self._task_class = variation, task_class
        self._seed = episode_seed
        self._rng = np.random.default_rng(self._seed)
        self._episode_id = uuid4().hex
        self._branch_id = self._control_step = 0
        self._branch_parent_state_id = None
        self._state_id = None
        self._terminated = self._truncated = False
        self.last_transition = None
        type(self)._active_env = weakref.ref(self)
        try:
            from topogym.config.scene import load_scene_config
            from topogym.world.genesis_world import GenesisWorld
            from topogym.robot.joint_position import make_robot
            from topogym.sensors.observation import SensorSuite

            from topogym.utils.variant_rng import seed_process

            seed_process(self._seed)
            cfg = load_scene_config(self.config)
            parameters = thaw(self.config.task_parameters)
            self._scene_variation = None
            if self.config.variation_id == SEEDED_VARIATION:
                from topogym.tasks.base import merge_parameters
                from topogym.tasks.scene_variation import SCENE_VARIATION_VERSION, draw
                draws = draw(self._task_class, self._seed)
                self._scene_variation = dict(version=SCENE_VARIATION_VERSION, draws=draws)
                # Explicit caller parameters override the seeded draw.
                parameters = merge_parameters(draws, parameters)
            self._task = self._task_class(parameters, seed=self._seed)
            if self.config.work_dir is None:
                self._temporary = TemporaryDirectory(prefix="topogym-episode-")
                folder = Path(self._temporary.name)
            else:
                folder = self.config.work_dir / self._episode_id
                folder.mkdir(parents=True, exist_ok=False)
            table = cfg.env.world.table
            spec = self._task.declare(
                folder / "assets", float(table.pos[2] + table.size[2] / 2)
            )
            spec = self._task.finalize_spec(spec, asset_dir=folder / "assets", scene_config=cfg)
            self._scene_spec = spec
            self._initial_state_report = None
            if spec.initial_state is not None and self.config.reset_physics_steps:
                raise ValueError("Frozen initial state requires reset_physics_steps == 0")
            from topogym.assets.library import describe_build

            self._asset_build = describe_build(
                self.config.task_id, folder / "assets", self._task.config, self._seed
            )
            physics_options = deepcopy(dict(spec.physics_options))
            if self.config.rigid_options:
                physics_options["rigid"] = {**dict(physics_options.get("rigid", {})), **self.config.rigid_options}
            if self.config.ipc_options:
                if "ipc" not in physics_options:
                    raise ValueError("ipc_options require an IPC scene")
                physics_options["ipc"] = {**dict(physics_options["ipc"]), **self.config.ipc_options}
            if self.config.grasp_assist.model == "contact_weld_v1":
                if "ipc" in physics_options:
                    raise ValueError("contact_weld_v1 does not support IPC scenes")
                rigid_options = dict(physics_options.get("rigid", {}))
                rigid_options["max_dynamic_constraints"] = max(2, int(rigid_options.get("max_dynamic_constraints", 0)))
                physics_options["rigid"] = rigid_options
            elif self.config.grasp_assist.model == "ipc_soft_band_v1" and "ipc" not in physics_options:
                raise ValueError("ipc_soft_band_v1 requires FEM IPC")
            elif self.config.grasp_assist.model == "pbd_local_patch_v1" and ("ipc" in physics_options or "pbd" not in physics_options):
                raise ValueError("pbd_local_patch_v1 requires the PBD coupler")
            self._world = GenesisWorld.from_tabletop(
                cfg.env,
                cfg.robot_control,
                physics_options=physics_options,
                compute_backend=self.config.compute_backend,
                precision=self.config.precision,
                seed=self._seed,
                cameras=self.config.enable_rgb,
            )
            self._world.diagnostics_dir = folder / "physics_diagnostics"
            self._world.add_entities(spec.entities)
            if spec.attachments:
                self._world.add_attachments(spec.attachments)
            if self.config.grasp_assist.model in {"ipc_soft_band_v1", "pbd_local_patch_v1"}:
                self._world.prepare_grasp(self.config.grasp_assist)
            self._world.terminal_contract_version = self.config.terminal_contract_version
            self._world.build()
            self._robot = make_robot(self._world.entities["robot"], cfg.robot_control)
            self._robot.reset_home()
            if spec.initial_robot_targets:
                # A pregrasp can start at contact while its closed-jaw target
                # applies preload. Actual joint positions are not teleported.
                self._robot.apply_action(spec.initial_robot_targets)
            self._task.bind(self._world.entities)
            self._task.bind_robot(self._robot.description)
            if spec.initial_state is not None:
                from topogym.world.initial_state import scene_identity, restore_declared_initial_state
                self._initial_state_report = restore_declared_initial_state(
                    self._world, self._robot, spec.initial_state,
                    identity=scene_identity(self.config, cfg, self._task, spec, self._asset_build))
            if self.config.ipc_settled_state is not None:
                from topogym.world.physics.ipc_settled_state import identity, restore_settled_state
                self._initial_state_report = restore_settled_state(
                    self._world, self.config.ipc_settled_state,
                    scene_identity=identity(self._world, self._task, spec, self._asset_build))
            for _ in range(self.config.reset_physics_steps):
                self._world.advance()
            self._world.reset_clock()
            if self.config.grasp_assist.model != "none":
                self._world.configure_grasp(self._robot, self.config.grasp_assist)
            settling = self._task.final_settling_spec()
            if settling is not None:
                self._world.configure_final_settling(settling.rigid_targets,
                    exact_robot_contact=settling.robot_contact_policy != "all_parts_clearance")
            self._task.initialize(self._world.read_state())
            self._sensors = (self._sensor_factory or SensorSuite)(
                self._world, self._robot, enable_rgb=self.config.enable_rgb,
                enable_depth=self.config.enable_depth,
                observation_mode=self.config.observation_mode,
            )
            self._history = EpisodeHistory(self._episode_id, storage=self.config.history_storage)
            self._save_state()
            self._stage = "observation"
            observation = self.observe()
            self._emit_lifecycle("reset", previous_episode_id=previous_episode_id, seed=self._seed)
            return observation, self._info()
        except BaseException as error:
            self._faulted = True
            self._fault_detail = dict(stage=self._stage, error=f"{type(error).__name__}: {error}")
            self._history = None
            self._release_world()
            raise

    @_mutation
    def step(self, action, *, _physics_steps=None):
        self._require_ready()
        # Owner replay may cap a previously interrupted control period. Operator
        # interaction does not expose this keyword; it never extends a period.
        ticks = self.config.control_decimation if _physics_steps is None else _physics_steps
        if type(ticks) is not int or not 1 <= ticks <= self.config.control_decimation:
            raise ValueError("replay tick count must be within one control period")
        if self._terminated or self._truncated:
            raise RuntimeError(
                "Episode has ended; use privileged rewind or ask the owner to reset"
            )
        # Validation must finish before either arm, history or clock changes.
        from topogym.robot.control import compile_action
        try:
            command = compile_action(self._robot, action, self.config.control_mode)
        except (ValueError, TypeError):
            raise  # Invalid operator input leaves the live episode usable.
        except BaseException as error:
            self._faulted = True
            self._fault_detail = dict(stage="control_query", error=f"{type(error).__name__}: {error}",
                                      last_saved_state_id=self._state_id)
            raise
        previous_observation = self.observe()
        previous_state_id = self._state_id
        before = self._world.physics_step
        try:
            self._stage = "command"
            self._robot.apply_action(command)
            self._control_step += 1
            for tick in range(ticks):
                self._stage = "physics"
                self._world.advance()
                self._stage = "task"
                world_state = self._world.read_state()
                # A task may skip a measurement that cannot change its result on a period's inner ticks (blanket coverage).
                self._task.complete_metrics = tick == ticks - 1
                try:
                    result = self._task.update(world_state, self.config.physics_dt_s)
                finally:
                    self._task.complete_metrics = True
                self._terminated = bool(result.terminated)
                self._truncated = bool(
                    not self._terminated
                    and self.config.max_physics_steps is not None
                    and self._world.physics_step >= self.config.max_physics_steps
                )
                self._save_state(world_state=world_state)
                if self._terminated or self._truncated:
                    break
            self._stage = "observation"
            observation = self.observe()
            info = self._info()
            count = self._world.physics_step - before
            info.update(
                physics_steps=count, action_duration_s=count * self.config.physics_dt_s,
                control_mode=self.config.control_mode,
                executed_joint_targets=freeze(self._robot.capture_state().targets),
            )
            transition = Transition(
                self._episode_id,
                self._branch_id,
                previous_state_id,
                self._state_id,
                self._control_step,
                self._world.physics_step,
                self._world.sim_time_s,
                count,
                count * self.config.physics_dt_s,
                previous_observation,
                freeze(action),
                observation,
                float(result.reward),
                self._terminated,
                self._truncated,
                freeze(info),
            )
            self.last_transition = transition
            self._stage = "output"
            for callback in tuple(self._transition_sinks):
                callback(transition)
            if self._frame_sinks:
                frame = self.sensor_frame()
                for callback in tuple(self._frame_sinks):
                    callback(frame)
            return (
                observation,
                float(result.reward),
                self._terminated,
                self._truncated,
                info,
            )
        except BaseException as error:
            self._faulted = True
            self._fault_detail = dict(stage=self._stage, error=f"{type(error).__name__}: {error}",
                                      last_saved_state_id=self._state_id)
            raise

    def _save_state(self, *, world_state=None):
        self._stage = "checkpoint"
        next_id = self._history.next_state_id()
        info = StateInfo(
            self._episode_id,
            self._branch_id,
            next_id,
            self._state_id,
            self._control_step,
            self._world.physics_step,
            self._world.sim_time_s,
            self._terminated,
            self._truncated,
        )
        # "segment" history: a complete world checkpoint only at the episode's first tick; segment starts are completed
        # by _checkpoint_current. Every tick still records its identity, robot targets, task state and RNG.
        complete = self.config.history_storage != "segment" or next_id == 0
        snapshot = EpisodeState(
            info,
            self._world.capture_state() if complete else None,
            self._robot.capture_state(),
            deepcopy(self._task.get_state()),
            deepcopy(self._rng.bit_generator.state),
        )
        self._history.append(snapshot)
        self._state_id = next_id
        self._sensors.invalidate()
        if self._state_sinks:
            self._stage = "state_output"
            record = self.tick_record(world_state=world_state)
            for callback in tuple(self._state_sinks):
                callback(record)

    def _checkpoint_current(self):
        """Owner hook (SegmentRunner._begin): make the current tick a complete checkpoint under "segment" history.

        No physics has advanced since this tick was recorded, so the world captured now is that tick's world."""
        self._require_ready()
        if self.config.history_storage != "segment":
            return
        if self._history.get(self._state_id).world is None:
            self._history.upgrade(self._state_id, self._world.capture_state())

    @_mutation
    def _restore(self, state_ref):
        if not self.config.enable_privileged:
            raise PermissionError("Privileged access is disabled")
        if self._closed or self._history is None or self._world is None:
            raise RuntimeError("No episode history exists")
        saved = self._history.resolve(state_ref)  # Validate before any mutation.
        if saved.world is None:
            raise ValueError('history_storage="segment" keeps complete checkpoints only at the episode start and at each '
                             'segment start; rewind to one of those (or select history_storage="memory")')
        state_id = saved.info.state_id
        try:
            self._stage = "rewind"
            self._world.restore_state(saved.world)
            self._robot.restore_state(saved.robot)
            self._task.set_state(deepcopy(saved.task))
            self._rng.bit_generator.state = deepcopy(saved.rng_state)
            self._control_step = saved.info.control_step
            self._terminated, self._truncated = (
                saved.info.terminated,
                saved.info.truncated,
            )
            self._branch_id = self._history.new_branch()
            self._branch_parent_state_id = state_id
            self._state_id = state_id
            self._faulted = False
            self._fault_detail = None
            self.last_transition = None
            self._sensors.invalidate()
            discarded_ids = []
            release = getattr(self._world, "discard_states", None)
            for item in self._history.iter_truncate_after(state_ref):
                discarded_ids.append(item.info.state_id)
                if release is not None and item.world is not None:
                    release([item.world])
            self._emit_lifecycle("rewind", invalidated_state_ids=discarded_ids,
                                 restored_physics_step=saved.info.physics_step)
            info = self._info()
            info["restored_from_state_id"] = state_id
            return self.observe(), info
        except BaseException as error:
            self._faulted = True
            self._fault_detail = dict(stage="rewind", error=f"{type(error).__name__}: {error}",
                                      last_saved_state_id=self._state_id)
            raise

    def is_solved(self):
        self._require_ready()
        return bool(self._task.result.task_success)

    def observe(self, *, _rgb=False):
        self._require_ready()
        observation, _ = self._sensors.sample(
            episode_id=self._episode_id,
            branch_id=self._branch_id,
            state_id=self._state_id,
            task=self._task,
            rgb=_rgb or not self.defer_rgb,
        )
        return observation

    def sensor_frame(self, *, depth=False):
        self.observe(_rgb=True)
        if depth:
            return self._sensors.depth_frame()
        return self._sensors._frame

    def render(self):
        if not self.config.enable_rgb:
            raise RuntimeError("RGB observation was not enabled for this Env")
        return self.sensor_frame().rgb

    def _info(self):
        result = self._task.result
        status = result.evaluation_status
        if result.terminated:
            status = "available"
        elif status is None:
            status = "available" if self._task.goal_complete else "unavailable"
        return dict(
            episode_id=self._episode_id,
            task_id=self.config.task_id,
            seed=self._seed,
            state_ref=dict(episode_id=self._episode_id, state_id=self._state_id),
            state_id=self._state_id,
            branch_id=self._branch_id,
            branch_parent_state_id=self._branch_parent_state_id,
            control_step=self._control_step,
            physics_step=self._world.physics_step,
            sim_time_s=self._world.sim_time_s,
            task_success=bool(result.task_success),
            task_terminated=bool(result.terminated),
            evaluation_status=status,
            terminal_revision=self._task.terminal_revision,
            failure_code=("wire_touched" if result.reason == "wire_touched" else "task_failed")
                if result.terminated and not result.task_success else None,
            termination_reason=result.reason
            if self._terminated
            else ("time_limit" if self._truncated else None),
            goal_evaluation_complete=bool(self._task.goal_complete),
            support=self.support_report(),
        )

    def _require_ready(self):
        if self._closed or self._world is None or self._history is None:
            raise RuntimeError("Env must be reset before use and must not be closed")
        if self._faulted:
            raise RuntimeError("Env is faulted; only reset/close is allowed")

    def _release_world(self):
        try:
            if self._world is not None:
                self._world.close()
        except BaseException:
            # Keep the scene and singleton guard so close can be retried;
            # losing the handle would leak an active engine into another Env.
            self._faulted = True
            raise
        self._world = self._robot = self._task = self._sensors = None
        if self._history is not None:
            self._history.close()
        try:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
        except BaseException:
            self._faulted = True
            raise
        finally:
            active = self._active_env() if self._active_env is not None else None
            if active is self:
                type(self)._active_env = None

    @_mutation
    def close(self):
        if self._closed:
            return
        try:
            self._emit_lifecycle("close")
        except BaseException:
            self._faulted = True
            raise
        self._release_world()
        self._closed = True
        self._history = None
        self._transition_sinks.clear()
        self._frame_sinks.clear()
        self._lifecycle_sinks.clear()
        self._state_sinks.clear()
        self._execution_guard = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
