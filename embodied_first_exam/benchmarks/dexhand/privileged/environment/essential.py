"""Dispatch the six fixed-wrist, contact-driven essential dexterity scenes."""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

_HERE = Path(__file__).resolve().parent
_REGISTRY = _HERE / "essential_registry.json"
if not _REGISTRY.exists():
    _REGISTRY = _HERE.parent / "task_library" / "index.json"
_ENTRIES = json.loads(_REGISTRY.read_text())["tasks"]
MODULES = {entry["id"]: entry["module"] for entry in _ENTRIES}
FREE_TASKS = {entry["id"] for entry in _ENTRIES if entry["free_objects"]}
_LOADED = {}
DEFAULT_WRIST = [-0.08, 0.0, 0.29, 0.0, 0.0, 0.0]


def is_essential(spec):
    return spec["id"] in MODULES


def module(spec):
    family = spec["id"]
    if family not in _LOADED:
        authoring = _HERE.parent / "task_library" / family / "scene.py"
        if authoring.is_file():
            loader = importlib.util.spec_from_file_location(MODULES[family], authoring)
            value = importlib.util.module_from_spec(loader)
            sys.modules[MODULES[family]] = value
            loader.loader.exec_module(value)
        else:
            value = importlib.import_module(MODULES[family])
        _LOADED[family] = value
    return _LOADED[family]


def initial_wrist(spec):
    return spec.get("parameters", {}).get("initial_wrist", DEFAULT_WRIST)


def wrist_wire_tolerance(spec):
    """Permit only float32 transport rounding, then normalize to fixed targets."""
    return [abs(struct.unpack("f", struct.pack("f", float(value)))[0] - value) + 1e-12
            for value in initial_wrist(spec)]


def offered_hands(spec):
    """The hands this family offers and why not more: offered_hands.json beside the frozen instance (the runtime
    directory in a task, task_library/<family>/ while authoring), else both hands."""
    for path in (_HERE / "offered_hands.json", _HERE.parent / "task_library" / spec["id"] / "offered_hands.json"):
        if path.is_file():
            value = json.loads(path.read_text())
            if value.get("family") == spec["id"]:
                return list(value["hands"]), str(value.get("reason", ""))
    return ["sharpa", "wuji"], ""


def wuji_reset(spec):
    """The family's declared Wuji Hand 2.2 reset finger pose (joint name -> radians), or {} for neutral fingers.

    Kept in wuji_reset.json beside the frozen instance (task_library/<family>/ while authoring, the runtime directory in
    a task) so the validated Sharpa instance stays byte-identical.
    """
    for path in (_HERE / "wuji_reset.json", _HERE.parent / "task_library" / spec["id"] / "wuji_reset.json"):
        if path.is_file():
            value = json.loads(path.read_text())
            if value.get("family") == spec["id"]:
                return dict(value["initial_fingers"])
    return {}


# Instance parameters a family may re-declare for Wuji in wuji_reset.json: only where the held objects start.
WUJI_OBJECT_KEYS = ("initial_position", "initial_quaternion")


def wuji_initial_objects(spec):
    """The family's declared Wuji Hand 2.2 start placement of the held objects (parameter name -> value), or {}.

    ``initial_objects`` in wuji_reset.json: only ``initial_position*`` / ``initial_quaternion*`` keys are accepted (a
    small re-placement of held objects into the Wuji grasp, found by settling in physics). Stages, invariants, guards,
    fixtures and every other parameter are the same for both hands; reset-relative quantities (e.g. walnut B's pose)
    are measured from the post-reset pose of the selected hand, as for Sharpa.
    """
    for path in (_HERE / "wuji_reset.json", _HERE.parent / "task_library" / spec["id"] / "wuji_reset.json"):
        if path.is_file():
            value = json.loads(path.read_text())
            if value.get("family") == spec["id"]:
                objects = dict(value.get("initial_objects", {}))
                for key in objects:
                    prefix = next((p for p in WUJI_OBJECT_KEYS if key.startswith(p)), None)
                    if prefix is None or "initial_position" + key[len(prefix):] not in spec.get("parameters", {}):
                        raise ValueError(f"wuji_reset.json may not declare {key!r}")
                return objects
    return {}
