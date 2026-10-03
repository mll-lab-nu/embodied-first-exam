"""Pure instance, file and trajectory contracts; no simulator imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import numpy as np

SCHEMA = 1
MAX_ROWS = 1_000_000


class BridgeError(ValueError):
    """An incompatibility that must not be repaired by changing the oracle."""


def read_json(path):
    return json.loads(Path(path).read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def json_digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def member(root, name):
    """Only regular, relative files, including all parent components."""
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or ".." in relative.parts
            or "\\" in name or str(relative) != name):
        raise BridgeError(f"Unsafe bundle member: {name!r}")
    root = Path(root).resolve()
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise BridgeError(f"Symlinks are not portable reference inputs: {name}")
    if not path.is_file():
        raise BridgeError(f"Missing reference input: {name}")
    return path


def file_hashes(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BridgeError(f"Symlink in reference tree: {path}")
        if path.is_file() and "__pycache__" not in path.parts:
            name = path.relative_to(root).as_posix()
            result[name] = digest(member(root, name))
    return result


def differences(expected, actual, prefix=""):
    """Return field-level differences without applying defaults or normalizing physics."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        rows = []
        for key in sorted(expected.keys() | actual.keys()):
            field = f"{prefix}.{key}" if prefix else key
            if key not in expected or key not in actual:
                rows.append(dict(field=field, expected=expected.get(key), actual=actual.get(key),
                                 missing="expected" if key not in expected else "actual"))
            else:
                rows.extend(differences(expected[key], actual[key], field))
        return rows
    if canonical(expected) == canonical(actual):
        return []
    return [dict(field=prefix, expected=expected, actual=actual)]


def instance_binding(path):
    path = Path(path)
    instance = read_json(path)
    required = {"task", "simulator", "state_sha", "action_layout", "action_dim", "asset_identity", "topogym_source"}
    if not required <= instance.keys():
        raise BridgeError(f"Incomplete frozen instance: {sorted(required - instance.keys())}")
    layout = instance["action_layout"]
    if (not isinstance(layout, list) or not layout
            or not all(isinstance(name, str) for name in layout) or len(set(layout)) != len(layout)
            or instance["action_dim"] != len(layout)):
        raise BridgeError("Invalid action layout")
    if not instance["state_sha"] or not instance["asset_identity"] or not instance["topogym_source"]:
        raise BridgeError("Frozen instance lacks state, asset or installed-source identity")
    config = instance["simulator"]
    if (not isinstance(config.get("physics_dt_s"), (int, float))
            or not np.isfinite(config["physics_dt_s"]) or config["physics_dt_s"] <= 0
            or type(config.get("control_decimation")) is not int or config["control_decimation"] < 1):
        raise BridgeError("Invalid frozen timing")
    assets = path.parent / "instance_assets"
    asset_files = {"instance_assets/" + k: v for k, v in file_hashes(assets).items()} if assets.exists() else {}
    # Archive references must resolve inside the identity's hashed asset tree.
    refs = [config.get("ipc_settled_state"),
            (config.get("task_parameters") or {}).get("initial_state_path")]
    for name in filter(None, refs):
        member(path.parent, name)
        if name not in asset_files:
            raise BridgeError(f"Frozen-state input is outside instance_assets: {name}")
    return dict(instance=instance, instance_sha256=json_digest(instance), asset_files=asset_files)


def require_same_instance(expected, actual):
    diff = differences(expected, actual)
    if diff:
        raise BridgeError("Frozen instance differs: " + ", ".join(row["field"] for row in diff[:12]))


def check_session(session, binding, *, instance_path=None):
    instance = binding["instance"]
    # Existing task tooling resolves this one portable asset path before making
    # its Session. Accept that exact resolution, without changing physics fields.
    config = dict(instance["simulator"])
    parameters = dict(config.get("task_parameters") or {})
    dependency = parameters.get("initial_state_path")
    if dependency and instance_path is not None:
        parameters["initial_state_path"] = str(member(Path(instance_path).parent, dependency))
        config["task_parameters"] = parameters
    fields = dict(task=session.task, config=session.config, state_sha=session.instance_sha,
                  assets=session.asset_identity, layout=list(session.action_layout))
    expected = dict(task=instance["task"], config=config, state_sha=instance["state_sha"],
                    assets=instance["asset_identity"], layout=instance["action_layout"])
    require_same_instance(expected, fields)
    if session.n_steps != 0 or getattr(session, "_resets", 0) != 0:
        raise BridgeError("Reference requires the fresh frozen episode")
    if not session.instance_matches:
        raise BridgeError("Runtime did not restore the frozen instance")


def load_trajectory(path, binding, *, native=False):
    """Require source identity and command semantics, never infer them from an array shape."""
    instance = binding["instance"]
    with np.load(path, allow_pickle=False) as data:
        array_key = "targets" if native else "actions"
        layout_key = "layout" if native else "action_layout"
        required = {array_key, layout_key, "task", "instance_sha", "scene_seed"}
        if not required <= set(data.files):
            raise BridgeError(f"Trajectory needs identity/command fields: {sorted(required - set(data.files))}")
        if (str(data["task"].item()) != instance["task"]
                or str(data["instance_sha"].item()) != instance["state_sha"]
                or data["scene_seed"].item() != instance["simulator"]["seed"]):
            raise BridgeError("Trajectory belongs to a different frozen instance")
        layout = data[layout_key].tolist()
        expected_layout = [name.removesuffix("_gripper") + "_native_gripper"
                           if name.endswith("_gripper") else name for name in instance["action_layout"]] if native else instance["action_layout"]
        if layout != expected_layout:
            raise BridgeError("Trajectory action layout differs; automatic reordering is disabled")
        raw = data[array_key]
        if (raw.dtype.kind not in "fiu" or raw.ndim != 2
                or raw.shape[1] != instance["action_dim"] or not 1 <= len(raw) <= MAX_ROWS
                or not np.isfinite(raw).all()):
            raise BridgeError("Invalid, empty or nonfinite command array")
        if not native and not np.array_equal(raw, raw.astype(np.float32)):
            raise BridgeError("Public trajectory cannot be represented exactly as float32")
        rows = raw.astype(np.float64 if native else np.float32)
        tick_key = "physics_steps" if native else "physics_steps_per_action"
        ticks = data[tick_key].copy() if tick_key in data else None
    decimation = instance["simulator"]["control_decimation"]
    if ticks is not None and (ticks.dtype.kind not in "iu" or ticks.shape != (len(rows),)
            or not np.all(ticks[:-1] == decimation) or not 1 <= ticks[-1] <= decimation):
        raise BridgeError("Trajectory timing would require resampling or a nonterminal partial step")
    return rows, ticks
