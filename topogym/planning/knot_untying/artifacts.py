"""Frozen benchmark tooling and portable knot execution evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

from topogym.utils.io import canonical_hash, sha256_file

ROOT = Path(__file__).resolve().parents[3]


def task_dir(variation):
    if variation not in {f"knot_untying_{tier}" for tier in ("easy", "medium", "hard")}:
        raise ValueError(f"unknown knot variation: {variation}")
    return ROOT/"tasks"/f"topogym-knot-untying-{variation.removeprefix('knot_untying_')}-i00-privileged"


def default_instance(variation):
    """Use the instance shipped alongside the loaded tooling; historical inputs must be explicit."""
    return task_dir(variation)/"environment/instance.json"


def load_tooling(variation):
    """Load that task's tooling by path, without modifying sys.path or reusing another task's module."""
    path = task_dir(variation)/"environment/rcb_topogym.py"
    name = f"_topogym_oracle_rcb_{variation}"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


def instance_identity(path):
    """Content identity, including the entire settled-state archive; independent of its directory."""
    path = Path(path).resolve()
    instance = json.loads(path.read_text())
    if instance.get("task") != "knot_untying":
        raise ValueError("expected a knot_untying instance")
    dependencies = {}
    settled = instance["simulator"].get("ipc_settled_state")
    if settled:
        manifest = (path.parent/settled).resolve()
        if not manifest.is_file():
            raise FileNotFoundError(f"missing IPC settled-state manifest: {manifest}")
        dependencies = {str(p.relative_to(manifest.parent)): sha256_file(p)
                        for p in sorted(manifest.parent.rglob("*")) if p.is_file()}
    return dict(instance_sha256=canonical_hash(instance), ipc_files=dependencies,
                variation=instance["simulator"]["variation_id"], seed=instance["simulator"]["seed"])


def validate_instance(path, variation):
    instance = json.loads(Path(path).read_text())
    cfg = instance["simulator"]
    if instance.get("task") != "knot_untying" or cfg["variation_id"] != variation:
        raise ValueError("--variation must match the frozen knot instance")
    if cfg.get("grasp_assist", {}).get("model", "none") != "none":
        raise ValueError("this oracle's grasp calibration requires grasp_assist none")
    if cfg.get("robot_id") != "aloha" or cfg.get("control_mode") != "JOINT_ABS":
        raise ValueError("knot oracle requires ALOHA JOINT_ABS")
    # Frozen tasks built before the 1 mm/s friction smoothing change are incompatible.
    state = cfg.get("ipc_settled_state")
    if state:
        metadata = json.loads((Path(path).parent/state).read_text())["metadata"]
        velocity = metadata["identity"]["physics_options"]["ipc"].get("contact_eps_velocity")
        if velocity != .001:
            raise ValueError("IPC state predates the 1 mm/s friction setting; rebuild with prepare_knot_instances.py")
    return instance


def save_recording(session, path):
    """Atomically snapshot the accepted action/tick prefix without stopping the recorder."""
    actions = np.asarray(session._recording, dtype=np.float32).reshape(-1, session.action_dim)
    ticks = np.asarray(session._recorded_ticks, dtype=np.int64)
    if len(actions) != len(ticks):
        raise ValueError("recording and physics tick ledger lengths differ")
    path = Path(path)
    temporary = path.with_name(path.name+".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, actions=actions, physics_steps_per_action=ticks, trajectory_version=2,
                            task=session.task, topogym_task=session.config["task_id"],
                            variation_id=session.config["variation_id"], scene_seed=int(session.config["seed"]),
                            instance_sha=session.instance_sha, action_dim=session.action_dim,
                            action_layout=np.asarray(session.action_layout), meta=json.dumps(dict(partial=True)))
    temporary.replace(path)
