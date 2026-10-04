"""Confirm sampled motion after release, without engine access or a second clock.

Collision bounding boxes provide a conservative clearance certificate: overlap
means clearance is unconfirmed, not that the surfaces necessarily touch. FEM
volumes can refine this certificate using robot convex covers and all tetrahedra.
Task-specific placement/support requirements remain with the task.
"""
from dataclasses import dataclass, asdict
from collections.abc import Mapping
import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class SettlingSpec:
    rigid_targets: tuple = ()
    fem_targets: tuple = ()
    particle_targets: tuple = ()
    clearance_m: float = .005
    maximum_speed_m_s: float = .001
    maximum_angular_speed_rad_s: float = .02
    maximum_drift_m: float = .001
    maximum_rotation_drift_rad: float = .02
    particle_radius_m: float = 0.
    robot_contact_policy: str = "all_parts_clearance"

    def __post_init__(self):
        if any(not isinstance(names, tuple) for names in (self.rigid_targets, self.fem_targets, self.particle_targets)):
            raise ValueError("Settling targets must be tuples")
        names = self.targets
        if not names or len(set(names)) != len(names) or any(not isinstance(n, str) or not n for n in names):
            raise ValueError("Settling requires distinct named targets")
        if self.robot_contact_policy not in {"all_parts_clearance", "fixed_contact_active_clearance_v1"}:
            raise ValueError("Unknown robot release contact policy")
        if self.robot_contact_policy != "all_parts_clearance" and (self.rigid_targets or self.particle_targets):
            raise ValueError("Exact robot contact policy currently requires FEM targets")
        for key, value in asdict(self).items():
            if key.endswith("targets") or key == "robot_contact_policy":
                continue
            if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number))
                    or not np.isfinite(value) or value < 0 or (key != "particle_radius_m" and value == 0)):
                raise ValueError(f"Invalid settling threshold: {key}")

    @property
    def targets(self):
        return self.rigid_targets + self.fem_targets + self.particle_targets


def _array(value, shape, label):
    a = np.asarray(value, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ValueError(f"Invalid settling {label}")
    return a


def _points(value):
    a = np.asarray(value, dtype=float)
    if a.ndim != 2 or a.shape[1] != 3 or not len(a) or not np.isfinite(a).all():
        raise ValueError("Invalid settling material points")
    return a


def _rotation(value):
    q = _array(value, (4,), "quaternion")
    if np.linalg.norm(q) < 1e-12:
        raise ValueError("Invalid settling quaternion")
    return Rotation.from_quat(q[[1, 2, 3, 0]])


def validate_reference(reference, spec):
    if reference is None:
        return
    if not isinstance(reference, dict) or set(reference) != set(spec.targets):
        raise ValueError("Settling reference targets differ from task")
    for name in spec.targets:
        if name in spec.rigid_targets:
            if set(reference[name]) != {"position_m", "quaternion_wxyz"}:
                raise ValueError("Invalid settling rigid reference")
            _array(reference[name]["position_m"], (3,), "position")
            _rotation(reference[name]["quaternion_wxyz"])
        else:
            _points(reference[name])


def _boxes(value):
    a = np.asarray(value, dtype=float)
    if a.ndim != 3 or a.shape[1:] != (2, 3) or not np.isfinite(a).all() or np.any(a[:, 0] > a[:, 1]):
        raise ValueError("Invalid release collision bounds")
    return a


def evaluate_settling(state, spec, reference=None):
    """Return (candidate, metrics, next_reference); caller owns the time window.

    Missing optional evidence is unavailable. Malformed/stale supplied evidence
    raises. Neither a planner phase nor a gripper command is accepted as proof.
    Assist is conservatively global: any active assist restarts confirmation.
    """
    validate_reference(reference, spec)
    current, target_boxes = {}, {}
    speed, angular_speed, drift, rotation_drift = 0., 0., 0., 0.
    for name in spec.rigid_targets:
        body = state["bodies"][name]
        p = _array(body["position_m"], (3,), "position")
        r = _rotation(body["quaternion_wxyz"])
        v = _array(body["linear_velocity_m_s"], (3,), "velocity")
        w = _array(body["angular_velocity_rad_s"], (3,), "angular velocity")
        speed, angular_speed = max(speed, float(np.linalg.norm(v))), max(angular_speed, float(np.linalg.norm(w)))
        current[name] = dict(position_m=p.copy(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]])
        if reference is not None:
            drift = max(drift, float(np.linalg.norm(p-reference[name]["position_m"])))
            rotation_drift = max(rotation_drift, float((r*_rotation(reference[name]["quaternion_wxyz"]).inv()).magnitude()))
    for group, names in (("fem", spec.fem_targets), ("particles", spec.particle_targets)):
        for name in names:
            body = state[group][name]
            p = _points(body["position_m"])
            v = _array(body["velocity_m_s"], p.shape, "material velocity")
            speed = max(speed, float(np.linalg.norm(v, axis=1).max()))
            current[name] = p.copy()
            padding = spec.particle_radius_m if group == "particles" else 0.
            target_boxes[name] = np.array([[p.min(0)-padding, p.max(0)+padding]])
            if reference is not None:
                old = _array(reference[name], p.shape, "material reference")
                drift = max(drift, float(np.linalg.norm(p-old, axis=1).max()))

    missing = []
    assist = state.get("assist_active")
    if assist is None:
        missing.append("assist_active")
    elif not isinstance(assist, (bool, np.bool_)):
        raise ValueError("Invalid assist_active flag")
    released = assist is not None and not assist
    geometry = state.get("release_geometry")
    clearance, coarse_clearance, clear = None, None, False
    refined, contact_metrics = [], {}
    if geometry is None:
        missing.append("release_geometry")
    else:
        if geometry["schema_version"] not in (1, 2, 3) or geometry["physics_step"] != state["physics_step"]:
            raise ValueError("Stale or unsupported release geometry")
        if not isinstance(geometry["complete"], bool):
            raise ValueError("Invalid release geometry coverage")
        if not geometry["complete"]:
            missing.append("collision_geometry_coverage")
        else:
            robot = _boxes(geometry["robot_bounds_m"])
            if not isinstance(geometry["robot_present"], bool) or (geometry["robot_present"] and not len(robot)):
                raise ValueError("Missing robot collision bounds")
            if not geometry["robot_present"] and len(robot):
                raise ValueError("Unexpected robot collision bounds")
            planes, topology = None, {}
            if geometry["schema_version"] >= 2:
                from .clearance import validate_robot_planes, validate_elements, fem_clearance_lower_bound
                planes = validate_robot_planes(geometry["robot_convex_planes_m"], len(robot))
                topology = geometry["fem_elements"]
                if not isinstance(topology, Mapping):
                    raise ValueError("Invalid release FEM topology")
                topology = {name: validate_elements(topology[name], len(current[name]))
                            for name in spec.fem_targets if name in topology}
            for name in spec.rigid_targets:
                target_boxes[name] = _boxes(geometry["target_bounds_m"][name])
                if not len(target_boxes[name]):
                    raise ValueError("Missing target collision bounds")
            clear = True
            if spec.robot_contact_policy != "all_parts_clearance":
                from .robot_contact import evaluate_robot_contact
                if geometry["schema_version"] != 3 or set(topology) != set(spec.fem_targets):
                    missing.append("exact_robot_contact_geometry")
                    clear = False
                else:
                    clear, contact_metrics = evaluate_robot_contact(current, topology, geometry, spec.clearance_m)
                    clearance = contact_metrics["active_clearance_lower_bound_m"]
                    refined = list(spec.fem_targets)
            for name, boxes in (target_boxes.items() if spec.robot_contact_policy == "all_parts_clearance" else ()):
                if len(robot):
                    gaps = np.maximum(np.maximum(boxes[:, None, 0]-robot[None, :, 1],
                                                 robot[None, :, 0]-boxes[:, None, 1]), 0.)
                    distance = float(np.linalg.norm(gaps, axis=-1).min())
                    coarse_clearance = distance if coarse_clearance is None else min(coarse_clearance, distance)
                    if distance < spec.clearance_m and name in topology:
                        distance = max(distance, fem_clearance_lower_bound(
                            current[name], topology[name], robot, planes, spec.clearance_m))
                        refined.append(name)
                    clearance = distance if clearance is None else min(clearance, distance)
                    clear &= distance >= spec.clearance_m

    quiet = speed <= spec.maximum_speed_m_s and angular_speed <= spec.maximum_angular_speed_rad_s
    bounded = drift <= spec.maximum_drift_m and rotation_drift <= spec.maximum_rotation_drift_rad
    reached = bool(not missing and released and clear and quiet and bounded)
    metrics = dict(evaluation_status="unavailable" if missing else "available",
        missing_evidence=missing, assist_released=bool(released), robot_clear=bool(clear),
        clearance_lower_bound_m=clearance, quiet=bool(quiet), drift_bounded=bool(bounded),
        maximum_speed_m_s=speed, maximum_angular_speed_rad_s=angular_speed,
        maximum_drift_m=drift, maximum_rotation_drift_rad=rotation_drift,
        sampling_scope="physics_tick_end", coarse_clearance_lower_bound_m=coarse_clearance,
        refined_fem_targets=refined,
        clearance_method="conservative_convex_volume_bounds" if refined else "conservative_collision_bounds")
    if spec.robot_contact_policy != "all_parts_clearance":
        metrics.update(contact_metrics, robot_contact_policy=spec.robot_contact_policy,
                       clearance_method="volume_bounds_then_native_solid_geometry")
    return reached, metrics, (current if reference is None else reference) if reached else None
