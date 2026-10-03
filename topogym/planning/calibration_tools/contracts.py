"""JSON-only private protocol; these checks are not an in-process sandbox."""
from dataclasses import dataclass
import hashlib
import json
import math
import re


class CalibrationError(RuntimeError):
    pass


class UnsupportedCapability(CalibrationError):
    pass


class OperationTimeout(CalibrationError):
    pass


class WorkerLost(CalibrationError):
    pass


class RequestConflict(CalibrationError):
    pass


@dataclass(frozen=True)
class Budgets:
    startup_s: float = 300.
    operation_s: float = 120.
    render_s: float = 120.
    policy_s: float = 600.
    physics_step_s: float = 120.
    memory_percent: float = 90.

    def __post_init__(self):
        for name, value in vars(self).items():
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.memory_percent > 90:
            raise ValueError("memory_percent must not exceed 90")


def json_value(value):
    from topogym.utils.io import to_jsonable
    return json.loads(json.dumps(to_jsonable(value), allow_nan=False))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value):
        raise ValueError("Expected a 1..100 character identifier (letters, digits, _, ., -)")
    if value in {".", ".."}:
        raise ValueError("Reserved identifier")
    return value


def positive_int(value, name, maximum=100000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [1, {maximum}]")
    return value


METHODS = frozenset({
    "capabilities", "inspect", "contacts", "capture_frame", "watch", "unwatch",
    "step", "step_until", "run_policy", "checkpoint", "restore", "sync_probe",
    "set_object_pose", "set_relative_pose", "pin_object", "unpin_object", "set_probe_grasp",
    "sweep_object", "solve_ik", "check_robot_path", "rank_grasps", "preview_geometry",
    "compare_geometry", "export_geometry_patch", "timings", "export_report", "close",
    "start_tracking", "tracking_report", "stop_tracking",
    "cache_plan", "check_cached_plan", "prepare_plan",
    "grasp_status", "run_grasp_trial", "grasp_trial_report",
    "task_summary", "contact_details", "gripper_geometry", "drive_object",
})
