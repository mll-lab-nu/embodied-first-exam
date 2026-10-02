"""Versioned numeric archives for management-side initial states, never pickle."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from topogym.utils.io import relative_file, sha256_file, write_json_atomic
from topogym.world.state import PackedArray, unpack_buffer


class NumericTree:
    """Preserve tuples, arrays and CPU tensors without serializing live objects."""

    def __init__(self):
        self.arrays = {}

    def encode(self, value):
        if isinstance(value, PackedArray):
            value = unpack_buffer(value)
        tensor = hasattr(value, "detach")
        if tensor:
            value = value.detach().cpu().numpy()
        if isinstance(value, np.ndarray):
            if value.dtype.kind not in "biuf":
                raise ValueError("Initial state supports only real numeric arrays")
            key = f"a{len(self.arrays)}"
            self.arrays[key] = value.copy()
            return dict(kind="tensor" if tensor else "array", key=key,
                        dtype=value.dtype.str, shape=list(value.shape))
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, dict):
            if any(not isinstance(k, str) for k in value):
                raise ValueError("Initial-state mapping keys must be strings")
            return dict(kind="dict", items={k: self.encode(v) for k, v in value.items()})
        if isinstance(value, (tuple, list)):
            return dict(kind="tuple" if isinstance(value, tuple) else "list",
                        items=[self.encode(v) for v in value])
        if value is None or type(value) in (str, bool, int, float):
            if isinstance(value, float) and not np.isfinite(value):
                raise ValueError("Nonfinite scalar in initial-state archive")
            return dict(kind="scalar", value=value)
        raise TypeError(f"Unsupported initial-state value: {type(value).__name__}")

    @staticmethod
    def decode(node, arrays):
        kind = node["kind"]
        if kind in ("array", "tensor"):
            value = arrays[node["key"]].copy()
            if (value.dtype.kind not in "biuf" or list(value.shape) != node["shape"]
                    or value.dtype.str != node["dtype"]):
                raise ValueError("Initial-state array schema mismatch")
            if kind == "tensor":
                import torch
                tensor = torch.from_numpy(value)
                # NumPy empty arrays have zero strides. Preserve an ordinary
                # Torch allocation for empty engine buffers so subsequent
                # snapshot byte comparisons can reinterpret the dtype.
                if tensor.numel() == 0:
                    return torch.empty(tensor.shape, dtype=tensor.dtype, device="cpu")
                return tensor
            return value
        if kind == "dict":
            return {k: NumericTree.decode(v, arrays) for k, v in node["items"].items()}
        if kind in ("tuple", "list"):
            items = [NumericTree.decode(v, arrays) for v in node["items"]]
            return tuple(items) if kind == "tuple" else items
        if kind == "scalar":
            value = node["value"]
            if value is not None and type(value) not in (str, bool, int, float):
                raise ValueError("Invalid scalar schema")
            if isinstance(value, float) and not np.isfinite(value):
                raise ValueError("Nonfinite scalar schema")
            return value
        raise ValueError("Unknown initial-state node kind")


def save_numeric_archive(folder, payload, metadata):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    folder.chmod(0o755)
    tree = NumericTree()
    root = tree.encode(payload)
    np.savez_compressed(folder/"arrays.npz", **tree.arrays)
    (folder/"arrays.npz").chmod(0o644)
    manifest = dict(schema_version=1, metadata=metadata, tree=root,
                    arrays=dict(path="arrays.npz", sha256=sha256_file(folder/"arrays.npz")))
    write_json_atomic(folder/"manifest.json", manifest, mode=0o644)
    return folder/"manifest.json"


def read_archive_manifest(manifest_path, *, expected_sha256=None):
    path = Path(manifest_path)
    if expected_sha256 is not None and sha256_file(path) != expected_sha256:
        raise ValueError("Initial-state manifest hash mismatch")
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported initial-state archive schema")
    return manifest


def load_numeric_archive(manifest_path, *, expected_sha256=None):
    path = Path(manifest_path)
    manifest = read_archive_manifest(path, expected_sha256=expected_sha256)
    data = relative_file(path.parent, manifest["arrays"]["path"])
    if sha256_file(data) != manifest["arrays"]["sha256"]:
        raise ValueError("Initial-state numeric archive hash mismatch")
    with np.load(data, allow_pickle=False) as arrays:
        payload = NumericTree.decode(manifest["tree"], arrays)
    return payload, manifest["metadata"]


def _array_layout(value):
    return dict(type=type(value).__name__, shape=list(value.shape), dtype=str(value.dtype)) if hasattr(value, "shape") else dict(type=type(value).__name__)


def require_same_layout(source, target, path="state"):
    """Check every value's layout before mutating any live buffer."""
    if isinstance(target, PackedArray):
        target = unpack_buffer(target)
    if hasattr(target, "detach"):
        if (not hasattr(source, "detach") or source.shape != target.shape
                or source.dtype != target.dtype):
            raise ValueError(f"Tensor layout differs at {path}: archive={_array_layout(source)}, runtime={_array_layout(target)}; use a compatible runtime or prepare a new initial state")
    elif isinstance(target, np.ndarray):
        if not isinstance(source, np.ndarray) or source.shape != target.shape or source.dtype != target.dtype:
            raise ValueError(f"Array layout differs at {path}: archive={_array_layout(source)}, runtime={_array_layout(target)}; use a compatible runtime or prepare a new initial state")
    elif isinstance(target, dict):
        if not isinstance(source, dict) or source.keys() != target.keys():
            raise ValueError(f"Mapping layout differs at {path}")
        for key in target:
            require_same_layout(source[key], target[key], f"{path}/{key}")
    elif isinstance(target, (tuple, list)):
        if type(source) is not type(target) or len(source) != len(target):
            raise ValueError(f"Sequence layout differs at {path}")
        for i, (a, b) in enumerate(zip(source, target)):
            require_same_layout(a, b, f"{path}/{i}")
    elif type(source) is not type(target):
        raise ValueError(f"Scalar layout differs at {path}")


def validate_initial_state_qualification(qualification, acceptance="released_stable"):
    """Check scope and retained material/placement gates without touching World."""
    if acceptance not in {"released_stable", "scene_layout"}:
        raise ValueError("Unknown initial-state acceptance")
    preparation = qualification.get("preparation", {})
    stable = (qualification.get("passed") is True and preparation.get("completed") is True
            and all(preparation.get("final_gates", {}).values()) and preparation.get("final_gates")
            and all(preparation.get(k) is True for k in ("gravity_restored", "rest_unchanged", "binding_unchanged"))
            and all(preparation.get(k) == 0 for k in ("position_writes", "rest_writes", "support_writes", "pins_added"))
            and qualification.get("binding", {}).get("passed") is True)
    if acceptance == "scene_layout":
        gates = preparation.get("final_gates", {})
        required = {"finite", "all_on_table", "no_table_penetration", "material_intact",
                    "visual_intact", "crumpled", "landed", "nonlocal_particle_clearance"}
        layout = (qualification.get("scope") == "scene_layout"
            and qualification.get("scene_layout_passed") is True
            and preparation.get("scene_layout_completed") is True
            and required <= gates.keys() and all(gates[k] is True for k in required)
            and preparation.get("final_tick", -1) > preparation.get("release_tick", float("inf"))
            and all(preparation.get(k) is True for k in ("gravity_restored", "rest_unchanged", "binding_unchanged"))
            and all(preparation.get(k) == 0 for k in ("position_writes", "rest_writes", "support_writes", "pins_added"))
            and qualification.get("binding", {}).get("passed") is True)
        if not (stable or layout):
            raise ValueError("Frozen initial state lacks scene-layout qualification")
    elif not stable:
        raise ValueError("Frozen initial state lacks successful released preparation qualification")


def restore_declared_initial_state(world, robot, declaration, *, identity):
    """Validate the declared acceptance scope before restoring any buffers."""
    from topogym.world.physics.pbd_initial_state import restore_initial_state
    metadata = read_archive_manifest(declaration.manifest_path, expected_sha256=declaration.sha256)["metadata"]
    validate_initial_state_qualification(metadata.get("qualification", {}), declaration.acceptance)
    report = restore_initial_state(world, declaration.manifest_path, identity=identity, robot=robot,
        expected_sha256=declaration.sha256)
    return report


def scene_identity(config, scene_config, task, spec, asset_build):
    """Physical/configuration identity independent of archive or work directory."""
    from copy import deepcopy
    from omegaconf import OmegaConf
    from topogym.utils.io import to_jsonable
    scene = OmegaConf.to_container(scene_config, resolve=True)
    # This first integration targets the production Blanket/ALOHA scene. The
    # numeric codec also has smaller rigid/PBD fixtures with explicit identities.
    from topogym.assets.robot import asset_root
    if scene_config.robot_control.robot.name != "aloha":
        raise ValueError("Declared frozen initial states currently require ALOHA")
    robot_root = asset_root(scene_config.robot_control.robot.get("asset_root"))/"robots/aloha"
    robot_sources = {str(p.relative_to(robot_root)): sha256_file(p) for p in sorted(robot_root.rglob("*"))
        if p.is_file() and p.suffix.lower() in {".xml", ".stl", ".obj", ".dae", ".ply", ".mtl", ".png"}}
    parameters = deepcopy(task.config)
    for key in ("initialization_mode", "initial_state_path", "initial_state_resource", "initial_state_sha256"):
        parameters.pop(key, None)
    return to_jsonable(dict(schema_version=1, task_id=task.task_id, seed=task.seed,
        parameters=parameters, physics_options=spec.physics_options,
        scene=scene, asset_sha256=dict(asset_build.sha256), robot_asset_sha256=robot_sources,
        compute_backend=config.compute_backend, precision=config.precision))
