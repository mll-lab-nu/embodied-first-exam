"""Task declarations and restorable task state, independent of Genesis lifecycle."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def merge_parameters(defaults, supplied):
    """Recursively copy mappings, preserving defaults and caller-owned values."""
    result = deepcopy(dict(defaults))
    for key, value in supplied.items():
        result[key] = (merge_parameters(result[key], value)
                       if isinstance(result.get(key), Mapping) and isinstance(value, Mapping)
                       else deepcopy(value))
    return result


def _parameter_at(config, path):
    for name in path.split("."):
        config = config[name]
    return config


@dataclass(frozen=True)
class EntitySpec:
    """Engine-independent entity declaration.

    ``surface`` accepts Genesis surface parameters plus ``diffuse_texture_path``
    for a generated or packaged image. World resolves that path into a texture;
    callers must omit ``color`` when the image already contains the palette.
    """

    name: str
    morph_type: str
    asset_path: str | Path | None
    position_m: tuple[float, float, float] = (0., 0., 0.)
    quaternion_wxyz: tuple[float, float, float, float] = (1., 0., 0., 0.)
    fixed: bool = False
    material: Mapping[str, Any] = field(default_factory=dict)
    physics_model: str = "rigid"
    morph_options: Mapping[str, Any] = field(default_factory=dict)
    surface: Mapping[str, Any] = field(default_factory=dict)
    initial_joint_positions: Mapping[str, float] = field(default_factory=dict)
    volume_path: str | Path | None = None
    contact_roles: Mapping[str, str] = field(default_factory=dict)
    material_map_path: str | Path | None = None


@dataclass(frozen=True)
class AttachmentSpec:
    """A permanent material endpoint attached to a rigid body, solved in IPC."""
    name: str
    soft_entity: str
    rigid_entity: str
    endpoint: str
    band_length_m: float
    stiffness_n_m: float = 1.e5

    def __post_init__(self):
        if self.endpoint not in {"start", "end"}:
            raise ValueError("Attachment endpoint must be start or end")
        if not all(isinstance(v, str) and v for v in (self.name, self.soft_entity, self.rigid_entity)):
            raise ValueError("Attachment and entity names must be nonempty")
        if not all(np.isfinite(v) and v > 0 for v in (self.band_length_m, self.stiffness_n_m)):
            raise ValueError("Attachment band and stiffness must be finite and positive")


@dataclass(frozen=True)
class InitialStateSpec:
    """Owner-only numeric initial-state archive, applied before episode birth."""
    manifest_path: str | Path
    sha256: str
    schema_version: int = 1
    acceptance: str = "released_stable"

    def __post_init__(self):
        if self.schema_version != 1 or len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError("Invalid initial-state schema or SHA-256")
        if self.acceptance not in {"released_stable", "scene_layout"}:
            raise ValueError("Unknown initial-state acceptance")


@dataclass(frozen=True)
class TaskSpec:
    entities: tuple[EntitySpec, ...]
    physics_options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    attachments: tuple[AttachmentSpec, ...] = ()
    initial_state: InitialStateSpec | None = None
    initial_robot_targets: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskResult:
    reward: float = 0.
    terminated: bool = False
    task_success: bool = False
    reason: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    evaluation_status: str | None = None


class TaskDefinition:
    """Define assets, initial state and a goal; World owns all engine operations."""

    task_id = "abstract"
    physics_model = "rigid"
    # Success evaluation is enabled by default, independently of physical
    # qualification. This is an enable switch, not the episode's success state.
    goal_complete = True
    defaults: Mapping[str, Any] = {}
    variation_id = "base"
    family_id = "reference"
    model_revision = "simulator_v1"
    terminal_revision = "legacy_v1"
    difficulty = None
    fixed_parameters = ()
    # Top-level leaves added for seeded scene variation. Their defaults reproduce the
    # scene from before they existed, so at the default they stay out of instance_id
    # and the recorded preset; any other value enters both.
    hash_when_changed = ()

    def __init__(self, config: Mapping[str, Any] | None = None, seed: int = 0):
        if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
            raise ValueError("Task seed must be a nonnegative integer")
        supplied = dict(config or {})
        unknown = supplied.keys() - self.defaults.keys()
        if unknown:
            raise ValueError(f"Unknown {self.task_id} task parameters: {sorted(unknown)}")
        self.config = merge_parameters(self.defaults, supplied)
        if "terminal" in self.config:
            terminal = self.config["terminal"]
            if not isinstance(terminal, Mapping) or set(terminal) != set(self.defaults["terminal"]):
                raise ValueError("Unknown or missing terminal parameter")
            for name, value in terminal.items():
                if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)) or not np.isfinite(value) or value <= 0:
                    raise ValueError(f"terminal.{name} must be finite and positive")
        for path in self.fixed_parameters:
            if _parameter_at(self.config, path) != _parameter_at(self.defaults, path):
                raise ValueError(f"{self.variation_id}: {path} defines this setting and cannot be overridden")
        duration = float(self.config.get("stable_duration_s", .5))
        if not np.isfinite(duration) or duration < 0:
            raise ValueError("stable_duration_s must be finite and nonnegative")
        if "minimum_separation_m" in self.config:
            separation = float(self.config["minimum_separation_m"])
            if not np.isfinite(separation) or separation <= 0:
                raise ValueError("minimum_separation_m must be finite and positive")
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        from topogym.assets.library import resource_path
        self.resource_hashes = {
            value: hashlib.sha256(resource_path(value).read_bytes()).hexdigest()
            for name in ("geometry_resource", "template_resource", "layout_resource",
                         "asset_resource", "prototype_resource")
            if (value := getattr(self, name, None))
        }
        identity = json.dumps(dict(task_id=self.task_id, family_id=self.family_id,
                                  model_revision=self.model_revision,
                                  terminal_revision=self.terminal_revision,
                                  resources=self.resource_hashes, config=self.identity_config(), seed=self.seed),
                              sort_keys=True, allow_nan=False)
        self.instance_id = hashlib.sha256(identity.encode()).hexdigest()
        self.stable_time_s = 0.
        self._goal_active = False
        self.last_physics_step: int | None = None
        self.result = TaskResult()
        self.task_state: dict = {}
        self._settling_reference = None
        self.entities: dict[str, Any] = {}
        self.table_height_m = 0.

    def identity_config(self):
        """The config that identifies this instance; see hash_when_changed."""
        return {key: value for key, value in self.config.items()
                if not (key in self.hash_when_changed and value == self.defaults[key])}

    def declare(self, asset_dir: Path, table_height_m: float) -> TaskSpec:
        raise NotImplementedError

    def bind(self, entities: Mapping[str, Any]) -> None:
        self.entities = dict(entities)

    def bind_robot(self, description) -> None:
        """Bind explicit robot contact roles after entities, before evaluation."""

    def finalize_spec(self, spec, *, asset_dir, scene_config):
        """Finalize an instance using the actual scene before asset hashing/build."""
        return spec

    def evaluate_state(self, state: Mapping[str, Any]) -> tuple[bool, str | None, dict]:
        """Return goal reached, failure reason and metrics, without changing state."""
        raise NotImplementedError

    def initial_task_state(self, world_state: Mapping[str, Any]) -> dict:
        return {}

    def terminal_metadata(self) -> dict:
        """Owner evidence; numerical thresholds are not policy observations."""
        metadata = dict(revision=self.terminal_revision, goal_complete=self.goal_complete,
            stable_duration_s=self.config.get("stable_duration_s", .5),
            parameters=self.config.get("terminal", {}))
        spec = self.final_settling_spec()
        if spec is not None:
            metadata["final_settling"] = dict(revision="release_settling_v2", **asdict(spec))
        return deepcopy(metadata)

    def final_settling_spec(self):
        """Opt into shared post-release confirmation; holding tasks return None."""
        return None

    def _evaluate_terminal(self, state, private, reference):
        reached, failure, metrics, private = self.evaluate_transition(state, private)
        spec = self.final_settling_spec()
        next_reference = None
        if spec is not None and not failure:
            from topogym.evaluation.terminal import evaluate_settling
            settled, measurements, next_reference = evaluate_settling(
                state, spec, reference if reached else None)
            status = metrics.get("evaluation_status", "available")
            if status not in {"available", "unavailable"}:
                raise ValueError("Invalid task evaluation status")
            status = "available" if status == measurements["evaluation_status"] == "available" else "unavailable"
            metrics = {**metrics, "final_settling": measurements, "evaluation_status": status}
            reached = bool(reached and settled and status == "available")
            if not reached:
                next_reference = None
        return reached, failure, metrics, private, next_reference

    def public_instruction(self) -> str:
        """Static instruction explicitly selected for the policy profile."""
        from .goal_description import TASK_IDS, describe_goal, render_goal
        if self.task_id in TASK_IDS:
            return render_goal(describe_goal(self), include_summary=True)
        return getattr(self, "instruction", "")

    def _evaluation_status(self, metrics, failure=None):
        status = metrics.get("evaluation_status", "available")
        if status not in {"available", "unavailable"}:
            raise ValueError("Invalid task evaluation status")
        return "available" if failure or (self.goal_complete and status == "available") else "unavailable"

    def validate_task_state(self, state: dict) -> None:
        """Validate portable task history; subclasses also enforce their schema."""
        def check(value):
            if isinstance(value, Mapping):
                if any(not isinstance(key, str) for key in value):
                    raise ValueError("Task history keys must be strings")
                for child in value.values():
                    check(child)
            elif isinstance(value, (tuple, list)):
                for child in value:
                    check(child)
            elif isinstance(value, np.ndarray):
                if value.dtype.kind not in "biuf" or not np.isfinite(value).all():
                    raise ValueError("Task history arrays must be finite numeric arrays")
            elif isinstance(value, (float, int, np.number)):
                if not np.isfinite(value):
                    raise ValueError("Task history must be finite")
            elif value is not None and not isinstance(value, (str, bool)):
                raise ValueError("Unsupported task history value")
        if not isinstance(state, dict):
            raise ValueError("Task history must be a dictionary")
        check(state)

    def evaluate_transition(self, world_state, task_state):
        """Pure transition; only update() commits the returned history."""
        reached, failure, metrics = self.evaluate_state(world_state)
        return reached, failure, metrics, task_state

    def initialize(self, state: Mapping[str, Any]) -> None:
        """Reject broken birth states without counting preparation as task execution."""
        if int(state["physics_step"]) != 0:
            raise ValueError("Task initialization requires the new episode clock at zero")
        private = deepcopy(self.initial_task_state(state))
        self.validate_task_state(private)
        _, failure, metrics, _, _ = self._evaluate_terminal(state, deepcopy(private), None)
        if failure:
            raise ValueError(f"Invalid {self.task_id} initial state: {failure}")
        result = TaskResult(evaluation_status=self._evaluation_status(metrics),
                            metrics={**metrics, "stable_time_s": 0., "goal_evaluation_complete": self.goal_complete})
        self.stable_time_s = 0.
        self._goal_active = False
        self._settling_reference = None
        self.last_physics_step = 0
        self.task_state = private
        self.result = result

    def update(self, state: Mapping[str, Any], physics_dt_s: float) -> TaskResult:
        if not np.isfinite(physics_dt_s) or physics_dt_s <= 0:
            raise ValueError("physics_dt_s must be finite and positive")
        step = int(state["physics_step"])
        if self.last_physics_step == step:
            return self.result
        if self.last_physics_step is not None and step != self.last_physics_step + 1:
            raise ValueError("Task updates require consecutive physics steps; restore Task state when rewinding")
        if self.result.terminated:
            return self.result
        reached, failure, metrics, private, reference = self._evaluate_terminal(
            state, deepcopy(self.task_state), deepcopy(self._settling_reference))
        private = deepcopy(private)
        self.validate_task_state(private)
        evaluation_status = self._evaluation_status(metrics, failure)
        # Unavailable evidence cannot advance a stability window or produce success.
        active = bool(reached and not failure and metrics.get("evaluation_status", "available") == "available")
        stable = self.stable_time_s + float(physics_dt_s) if active and self._goal_active else 0.
        required = float(self.config.get("stable_duration_s", .5))
        succeeded = bool(self.goal_complete and active and stable + 1e-12 >= required)
        result = TaskResult(reward=1. if succeeded else 0., terminated=bool(failure or succeeded),
                                 task_success=succeeded, reason=failure or ("Goal stable" if succeeded else None),
                                 evaluation_status=evaluation_status,
                                 metrics={**metrics, "stable_time_s": stable, "goal_evaluation_complete": self.goal_complete})
        self.last_physics_step, self.stable_time_s = step, stable
        self._goal_active, self.task_state, self.result = active, private, result
        self._settling_reference = reference
        return self.result

    def observe(self) -> dict:
        """Optional task measurements; SensorSuite already provides world/robot state."""
        return {}

    def get_state(self) -> dict:
        saved = dict(schema_version=2, task_id=self.task_id, instance_id=self.instance_id,
                             task_state=self.task_state,
                             stable_time_s=self.stable_time_s, last_physics_step=self.last_physics_step,
                             goal_active=self._goal_active,
                             result=asdict(self.result), rng_state=self.rng.bit_generator.state)
        if self.final_settling_spec() is not None:
            saved["final_settling"] = dict(schema_version=1, reference=self._settling_reference)
        return deepcopy(saved)

    def set_state(self, state: Mapping[str, Any]) -> None:
        saved = deepcopy(dict(state))
        if (saved.get("schema_version") != 2 or saved.get("task_id") != self.task_id
                or saved.get("instance_id") != self.instance_id):
            raise ValueError("Task state belongs to a different task, instance or schema")
        stable = float(saved["stable_time_s"])
        if not np.isfinite(stable) or stable < 0 or not isinstance(saved["result"], dict):
            raise ValueError("Invalid task checkpoint")
        if not isinstance(saved["goal_active"], bool):
            raise ValueError("Invalid task checkpoint goal flag")
        probe = np.random.default_rng()
        probe.bit_generator.state = saved["rng_state"]
        step = saved["last_physics_step"]
        if step is not None and (isinstance(step, bool) or not isinstance(step, int) or step < 0):
            raise ValueError("Invalid task checkpoint step")
        result = TaskResult(**saved["result"])
        private = saved["task_state"]
        self.validate_task_state(private)
        if (not np.isfinite(result.reward) or (result.task_success and not result.terminated)
                or result.evaluation_status not in {None, "available", "unavailable"}
                or (result.terminated and result.evaluation_status == "unavailable")
                or (not self.goal_complete and (result.task_success or result.reward != 0.))):
            raise ValueError("Invalid task checkpoint result")
        reference = None
        spec = self.final_settling_spec()
        if spec is not None:
            from topogym.evaluation.terminal import validate_reference
            settling = saved.get("final_settling")
            if not isinstance(settling, dict) or set(settling) != {"schema_version", "reference"} or settling["schema_version"] != 1:
                raise ValueError("Missing or incompatible final settling checkpoint")
            reference = settling["reference"]
            validate_reference(reference, spec)
            if saved["goal_active"] != (reference is not None):
                raise ValueError("Settling reference differs from active confirmation window")
        self.stable_time_s, self.last_physics_step = stable, step
        self._goal_active = saved["goal_active"]
        self.result, self.rng = result, probe
        self.task_state = private
        self._settling_reference = reference


class UnavailableTaskDefinition(TaskDefinition):
    """Importable placeholder that cannot masquerade as an existing scene."""

    unavailable_reason = "This setting has not been implemented"

    def __init__(self, config=None, seed=0):
        raise NotImplementedError(f"{self.variation_id}: {self.unavailable_reason}")


class RigidTaskDefinition(TaskDefinition):
    """Shared read-only rigid measurements; individual tasks retain their goals."""

    def bind(self, entities: Mapping[str, Any]) -> None:
        super().bind(entities)
        self._link_indices_by_entity = {
            name: {int(link.idx) for link in entity.links}
            for name, entity in entities.items() if hasattr(entity, "links")
        }
        self._task_link_indices = {
            int(link.idx) for name in self.local_vertices for link in entities[name].links
        }
        robot = entities.get("robot")
        self._robot_link_indices = set() if robot is None else {int(link.idx) for link in robot.links}
        self._movable_task_link_indices = {
            int(link.idx) for name in self.local_vertices for link in entities[name].links
            if not link.is_fixed
        }
        self._finger_links_by_hand = {}

    def bind_robot(self, description) -> None:
        robot = self.entities.get("robot")
        self._finger_links_by_hand = {} if robot is None else {
            group.name: tuple(int(robot.get_link(name).idx) for name in group.grasp.finger_links)
            for group in description.groups if group.grasp is not None
        }

    def terminal_metadata(self) -> dict:
        from topogym.utils.grasp import TASK_CONTACT_PENETRATION_M, GRASP_CONTACT_PENETRATION_M
        return super().terminal_metadata() | dict(contact_penetration=dict(
            other_contacts_m=TASK_CONTACT_PENETRATION_M,
            held_finger_contacts_m=GRASP_CONTACT_PENETRATION_M,
            holding_evidence="same_hand_bilateral_contact_or_live_rigid_assist_binding"))

    def rigid_measurements(self, state: Mapping[str, Any]):
        from scipy.spatial.transform import Rotation

        poses, bounds, quiet = {}, {}, True
        for name, vertices in self.local_vertices.items():
            body = state["bodies"][name]
            position = np.asarray(body["position_m"], dtype=float)
            quaternion = np.asarray(body["quaternion_wxyz"], dtype=float)
            velocity = np.asarray(body["linear_velocity_m_s"], dtype=float)
            angular = np.asarray(body["angular_velocity_rad_s"], dtype=float)
            if not np.isfinite(np.r_[position, quaternion, velocity, angular]).all():
                return {}, {}, False, "Non-finite physical state"
            rotation = Rotation.from_quat(quaternion[[1, 2, 3, 0]])
            points = rotation.apply(vertices) + position
            if points[:, 2].min() < self.table_height_m - .1:
                return {}, {}, False, "A task body fell below the table"
            poses[name] = (position, rotation)
            bounds[name] = (points.min(axis=0), points.max(axis=0))
            quiet = quiet and np.linalg.norm(velocity) < .001 and np.linalg.norm(angular) < .02
        contact_states = [dict(contacts=state.get("contacts"), grasp=state.get("grasp"))]
        if state.get("terminal_contract_version", 1) == 2:
            events = state.get("contact_events") or {}
            if not events.get("substeps_complete") or not events.get("contact_snapshots"):
                raise RuntimeError("terminal contract 2 requires complete rigid substep contact coverage")
            contact_states = events["contact_snapshots"]
        for sample in contact_states:
            contacts = sample["contacts"]
            if contacts is None:
                continue
            from topogym.utils.grasp import (
                TASK_CONTACT_PENETRATION_M, GRASP_CONTACT_PENETRATION_M, held_finger_contact_mask,
            )
            a, b = np.asarray(contacts["link_a"]), np.asarray(contacts["link_b"])
            involved = np.isin(a, list(self._task_link_indices)) | np.isin(b, list(self._task_link_indices))
            penetration = np.asarray(contacts["penetration"])
            held = held_finger_contact_mask(contacts, self._finger_links_by_hand,
                                          self._movable_task_link_indices, sample.get("grasp"))
            if penetration[involved & ~held].max(initial=0.) > TASK_CONTACT_PENETRATION_M:
                return poses, bounds, False, "Task contact penetration exceeded 1 mm"
            if penetration[involved & held].max(initial=0.) > GRASP_CONTACT_PENETRATION_M:
                return poses, bounds, False, "Held finger contact penetration exceeded 2 mm"
        return poses, bounds, bool(quiet), None

    def released(self, state: Mapping[str, Any], names=None) -> bool:
        if not self._robot_link_indices:
            return True
        contacts = state.get("contacts")
        if contacts is None:
            return False  # No contact evidence is not evidence of release.
        a, b = np.asarray(contacts["link_a"]), np.asarray(contacts["link_b"])
        selected = self._task_link_indices if names is None else set().union(
            *(self._link_indices_by_entity[name] for name in names))
        task, robot = list(selected), list(self._robot_link_indices)
        held = ((np.isin(a, task) & np.isin(b, robot)) | (np.isin(b, task) & np.isin(a, robot)))
        force = np.linalg.norm(np.asarray(contacts["force"]), axis=-1)
        return not bool(np.any(held & (force > .05)))
