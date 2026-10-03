"""Declared grasp phases executed by the shared SegmentRunner, with passive metrics."""
from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4

import numpy as np

from .contracts import UnsupportedCapability, digest, json_value, positive_int
from .grasp_observation import explain_grasp
from .tracking import pose, tcp_pose
from topogym.utils.io import write_json_atomic


PHASES = ("approach", "close", "lift", "hold", "release")


def normalize_trial(trial):
    trial = json_value(trial)
    if not isinstance(trial, dict) or set(trial)-{"hand", "target", "phases", "criteria", "record_video"}:
        raise ValueError("Trial requires hand, target, phases; optional criteria and record_video")
    if not isinstance(trial.get("hand"), str) or not trial["hand"]:
        raise ValueError("Trial must name a hand")
    target = trial.get("target")
    if isinstance(target, str):
        target = dict(entity=target)
    if not isinstance(target, dict) or set(target)-{"entity", "link", "vertex_indices"} or not target.get("entity"):
        raise ValueError("Target requires entity; optional rigid link or material vertex_indices")
    if "link" in target and "vertex_indices" in target:
        raise ValueError("Choose a rigid link or material vertices")
    indices = target.get("vertex_indices")
    if indices is not None and (not isinstance(indices, list) or not indices or
            any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices)):
        raise ValueError("vertex_indices must be distinct nonnegative integers")
    trial["target"] = target
    phases = trial.get("phases", [])
    if (not isinstance(phases, list) or not all(isinstance(p, dict) for p in phases)
            or [p.get("name") for p in phases] != list(PHASES)):
        raise ValueError("Declare approach, close, lift, hold, release in that order")
    expanded = []
    for phase in phases:
        if set(phase)-{"name", "actions", "action", "steps"}:
            raise ValueError("Unknown phase option")
        if "actions" in phase:
            if set(phase) != {"name", "actions"}:
                raise ValueError("Use actions or action+steps for a phase")
            actions = phase["actions"]
        else:
            if "action" not in phase or "steps" not in phase:
                raise ValueError("Phase requires actions or action+steps")
            positive_int(phase["steps"], "phase steps", 10000)
            actions = [deepcopy(phase["action"]) for _ in range(phase["steps"])]
        if not isinstance(actions, list) or not actions or not all(isinstance(a, dict) for a in actions):
            raise ValueError("Each phase requires a nonempty list of action mappings")
        expanded.append(dict(name=phase["name"], actions=actions))
    positive_int(sum(len(p["actions"]) for p in expanded), "total trial controls", 10000)
    trial["phases"] = expanded
    criteria = dict(minimum_lift_m=.02, maximum_slip_m=.01, minimum_hold_s=.1)
    supplied = trial.get("criteria", {})
    if not isinstance(supplied, dict) or set(supplied)-set(criteria):
        raise ValueError("Unknown trial criterion")
    criteria.update(supplied)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or v < 0
           for v in criteria.values()) or criteria["minimum_hold_s"] <= 0:
        raise ValueError("Criteria must be finite and nonnegative; minimum_hold_s must be positive")
    trial["criteria"] = criteria
    if type(trial.get("record_video", False)) is not bool:
        raise ValueError("record_video must be boolean")
    trial.setdefault("record_video", False)
    return trial


def target_point(record, target):
    world, name = record["world"], target["entity"]
    if "vertex_indices" in target or name in world.get("fem", {}) or name in world.get("particles", {}):
        if "link" in target:
            raise ValueError("A deformable target cannot name a rigid link")
        values = world.get("fem", {}).get(name, world.get("particles", {}).get(name))
        if values is None:
            raise ValueError("Target has no material vertices")
        x = np.asarray(values["position_m"], dtype=float)
        if "vertex_indices" in target:
            x = x[target["vertex_indices"]]
        result, kind = x.mean(axis=0), "fixed_vertex_set_centroid" if "vertex_indices" in target else "whole_material_vertex_centroid"
    else:
        value = (world["articulations"][name]["links"][target["link"]] if "link" in target
                 else world["bodies"][name])
        result, kind = np.asarray(value["position_m"], dtype=float), "rigid_link_origin"
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError("Target position is unavailable or nonfinite")
    return result, kind


class TrialMetrics:
    """One declared material point/link, kept fixed throughout the trial."""
    def __init__(self, trial, initial):
        self.trial, self.phase = trial, "initial"
        self.latest = initial
        self.lift_origin = self.hold_relative = None
        self.hold_start_height = None
        self.release_start_height = None
        self.material_edges = self.material_lengths = None
        self.hold_s = self.current_hold_s = self.longest_hold_s = 0.
        self.max_slip = self.max_lift = 0.
        self.minimum_hold_lift = self.min_volume = self.max_strain = None
        self.last_time = initial["state"]["sim_time_s"]
        self.phase_ticks = {p: 0 for p in PHASES}
        self.point_kind = target_point(initial, trial["target"])[1]

    def relative_point(self, record, point):
        p, r = pose(tcp_pose(record["robot"][self.trial["hand"]]))
        return r.inv().apply(point-p)

    def begin(self, phase):
        if phase != self.phase:
            point, _ = target_point(self.latest, self.trial["target"])
            if phase == "lift":
                self.lift_origin = point.copy()
            if phase == "hold":
                self.hold_relative = self.relative_point(self.latest, point)
                self.hold_start_height = float(point[2])
            if phase == "release":
                self.release_start_height = float(point[2])
            self.phase = phase

    def sample(self, record):
        point, _ = target_point(record, self.trial["target"])
        now = record["state"]["sim_time_s"]
        dt = now-self.last_time
        if dt <= 0:
            raise ValueError("Trial samples must advance one continuous branch")
        lift = None if self.lift_origin is None else float(point[2]-self.lift_origin[2])
        slip = None
        self.phase_ticks[self.phase] += 1
        if self.phase in {"lift", "hold"}:
            self.max_lift = max(self.max_lift, lift)
        if self.phase == "hold":
            slip = float(np.linalg.norm(self.relative_point(record, point)-self.hold_relative))
            self.hold_s += dt
            self.max_slip = max(self.max_slip, slip)
            self.minimum_hold_lift = lift if self.minimum_hold_lift is None else min(self.minimum_hold_lift, lift)
            c = self.trial["criteria"]
            good = lift >= c["minimum_lift_m"] and slip <= c["maximum_slip_m"]
            self.current_hold_s = self.current_hold_s+dt if good else 0.
            self.longest_hold_s = max(self.longest_hold_s, self.current_hold_s)
        world = record["world"]
        volume = world.get("ipc", {}).get("volume_ratio", {}).get(self.trial["target"]["entity"], {}).get("minimum")
        if volume is not None:
            self.min_volume = volume if self.min_volume is None else min(self.min_volume, volume)
        grasp = explain_grasp(world.get("grasp"), hand=self.trial["hand"])
        hand = grasp["hands"].get(self.trial["hand"], {})
        measured = hand.get("health") or hand.get("admission", {})
        strain = measured.get("max_material_edge_ratio")
        if self.material_edges is not None:
            vertices = np.asarray(world["fem"][self.trial["target"]["entity"]]["position_m"])
            strain = float((np.linalg.norm(vertices[self.material_edges[:, 1]]-
                vertices[self.material_edges[:, 0]], axis=1)/self.material_lengths).max())
            if self.max_strain is None or strain > self.max_strain:
                self.max_strain = strain
        if strain is not None and hand.get("entity") == self.trial["target"]["entity"]:
            self.max_strain = strain if self.max_strain is None else max(self.max_strain, strain)
        self.latest, self.last_time = record, now
        return json_value(dict(state=record["state"], phase=self.phase, target_position_m=point,
            lift_m=lift, slip_m=slip, volume_ratio_minimum=volume, material_edge_ratio=strain, grasp=grasp,
            fingers={k: v for k, v in record["robot"][self.trial["hand"]].items() if k.startswith("finger_position_")}))

    def summary(self, completed):
        point, _ = target_point(self.latest, self.trial["target"])
        c = self.trial["criteria"]
        passed = bool(completed and self.minimum_hold_lift is not None and
            self.minimum_hold_lift >= c["minimum_lift_m"] and self.max_slip <= c["maximum_slip_m"] and
            self.longest_hold_s+1.e-12 >= c["minimum_hold_s"] and (self.min_volume is None or self.min_volume > 0))
        from .grasp_observation import condition
        checks = dict(lift=condition(self.minimum_hold_lift, c["minimum_lift_m"], minimum=True),
            slip=condition(self.max_slip if self.hold_s else None, c["maximum_slip_m"]),
            hold_duration=condition(self.longest_hold_s, c["minimum_hold_s"], minimum=True),
            completed_phases=dict(satisfied=completed))
        return dict(criteria_passed=passed, criteria_checks=checks, maximum_lift_m=self.max_lift,
            minimum_hold_lift_m=self.minimum_hold_lift, maximum_hold_slip_m=self.max_slip,
            measured_hold_s=self.hold_s, longest_qualified_hold_s=self.longest_hold_s,
            release_drop_m=None if self.release_start_height is None else self.release_start_height-float(point[2]),
            minimum_volume_ratio=self.min_volume, maximum_reported_material_edge_ratio=self.max_strain,
            phase_ticks=self.phase_ticks, target_measurement=self.point_kind,
            physical_release_verified=False, scope="declared lift/hold measurements; no task-success or force certificate")


class GraspTrial:
    def __init__(self, owner, trial):
        self.owner, self.trial = owner, normalize_trial(trial)
        initial = owner.env.tick_record()
        if self.trial["hand"] not in initial["robot"]:
            raise ValueError("Unknown trial hand")
        target_point(initial, self.trial["target"])
        for phase in self.trial["phases"]:
            for action in phase["actions"]:
                if not set(action) <= initial["robot"].keys() or not all(isinstance(v, dict) for v in action.values()):
                    raise ValueError("Actions must address existing robot hands")
        if self.trial["record_video"] and not owner.config.enable_rgb:
            raise UnsupportedCapability("Trial video requires a session built with Nyx RGB")
        self.metrics = TrialMetrics(self.trial, initial)
        world = getattr(owner.env, "_world", None)
        entity = None if world is None else world.entities.get(self.trial["target"]["entity"])
        if entity is not None and hasattr(entity, "material_coordinates") and hasattr(entity, "elems"):
            from itertools import combinations
            elements = np.asarray(entity.elems)
            edges = np.unique(np.sort(np.concatenate([elements[:, [a, b]] for a, b in combinations(range(4), 2)]), axis=1), axis=0)
            coordinates = np.asarray(entity.material_coordinates)
            lengths = np.linalg.norm(coordinates[edges[:, 1]]-coordinates[edges[:, 0]], axis=1)
            if len(edges) and np.all(lengths > 0):
                self.metrics.material_edges, self.metrics.material_lengths = edges, lengths
        self.trial_id = uuid4().hex
        self.folder = owner.output / "grasp_trials" / self.trial_id
        self.folder.mkdir(parents=True)
        self.samples = (self.folder / "samples.jsonl").open("x", buffering=1)
        self.completed_controls = 0
        self.events, self.recording, self.sensors = [], None, None
        self.report = dict(trial_id=self.trial_id, status="running", trial=self.trial,
            initial_state=json_value(initial["state"]), source_manifest=str(owner.output / "source_manifest.json"),
            action_hash=digest(self.trial["phases"]), formal_qualification=False, recording=None,
            samples=str(self.folder / "samples.jsonl"), report=str(self.folder / "report.json"),
            metrics_coverage="World ticks; FEM rest-edge ratios and available native volumes; no IPC force completeness")
        self.save()

    def save(self):
        self.report.update(completed_controls=self.completed_controls, events=self.events,
                           last_state=json_value(self.metrics.latest["state"]),
                           metrics=self.metrics.summary(self.report["status"] == "completed"))
        write_json_atomic(self.folder / "report.json", self.report, mode=0o600)

    def tick(self, record, events):
        self.events.extend(dict(row, state=json_value(record["state"])) for row in events)
        self.samples.write(json.dumps(self.metrics.sample(record), allow_nan=False)+"\n")

    def capture(self):
        if self.recording is not None:
            env = self.owner.env
            _, frame = self.sensors.sample(episode_id=env._episode_id, branch_id=env._branch_id,
                                           state_id=env._state_id, task=env._task)
            self.recording.append(frame)

    def transition(self):
        self.completed_controls += 1
        self.save()  # Save numerical progress before rendering.
        self.capture()

    def run(self):
        from .worker import BoundaryStop
        owner, runtime = self.owner, self
        planned = [(p["name"], action) for p in self.trial["phases"] for action in p["actions"]]
        class Policy:
            index = 0
            def act(self, observation):
                if owner.cancelled():
                    raise BoundaryStop("cancelled")
                if self.index == len(planned):
                    return None
                phase, action = planned[self.index]
                runtime.metrics.begin(phase)
                self.index += 1
                owner.before_action(action)
                return deepcopy(action)
        policy, token = Policy(), uuid4().hex
        started = time.monotonic()
        try:
            if self.trial["record_video"]:
                from topogym.recording.session import RecordingSession
                from topogym.sensors.observation import SensorSuite
                self.sensors = SensorSuite(owner.env._world, owner.env._robot, enable_rgb=True)
                self.recording = RecordingSession(self.folder / "recording", metadata=dict(
                    scope="declared grasp trial from current state; not necessarily home",
                    initial_state=self.report["initial_state"], formal_qualification=False))
                self.recording.__enter__()
                self.report["recording"] = str(self.folder / "recording")
                self.capture()
            owner.active_trial = self
            try:
                result = owner.runner.run_policy(request_id=token, policy=policy,
                    submission_hash=digest(self.trial), mode="unlimited",
                    observation_profile={"rgb_camera_ids": []}, state_fields=())
            except BoundaryStop:
                result = owner.runner._records[owner.runner._requests[token]]["result"]
                self.report["status"] = "cancelled"
            else:
                self.report["status"] = ("completed" if self.completed_controls == len(planned) and
                    result.get("control_step_complete", True) else "incomplete")
            self.report["execution"] = json_value(result)
        except BaseException as error:
            self.report.update(status="failed", error=dict(type=type(error).__name__, message=str(error)))
            raise
        finally:
            owner.active_trial = None
            owner.tracking.finish()
            self.samples.close()
            self.report["wall_s"] = time.monotonic()-started
            if self.recording is not None:
                try:
                    self.recording.finish(dict(status=self.report["status"], task_success=False))
                    self.recording.close(commit=True)
                except Exception as error:
                    self.report.update(status="failed", recording_error=str(error))
            self.save()
        return deepcopy(self.report)
