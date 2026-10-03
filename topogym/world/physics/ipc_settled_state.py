"""A settled IPC scene, frozen with its instance and restored at every build (no settling ticks at run time).

The IPC rope families settle for 300-800 ticks before their instance is frozen (`SimulatorConfig.reset_physics_steps`).
Settling at every build costs 0.8-2.4 min and, because GPU contact solving is not bit-deterministic, starts each build
~0.04 um from the others, which a near-threshold squeeze can turn into another contact branch (2026-10-02 IPC study).
This module exports the settled native state once (libuipc's dump files, the scene attribute buffers and the coupler's
previous link transforms: what `CheckpointStore` captures for a rewind) and restores it into a freshly built world at
the build's own native frame, then re-syncs Genesis the way `EpisodeIPCCoupler.reset` does. Every build then starts from
the same bits. Numeric archive (no pickle): `initial_state.save_numeric_archive` plus the dump files under `dump/`, each
with its sha256.
"""
from __future__ import annotations

import json
import zlib
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import numpy as np

from topogym.utils.io import relative_file
from topogym.world.initial_state import load_numeric_archive, read_archive_manifest, save_numeric_archive

CODEC = "topogym_ipc_settled_v1"


def identity(world, task, spec, asset_build):
    """What the archive is valid for: the scene (task, variation, seed, assets, the task's physics options) and the native
    format (Genesis, pyuipc and the libuipc build). Not the solver dt or tolerances: a settled state is a valid start for
    any of them."""
    from topogym.utils.io import to_jsonable
    parameters = {k: v for k, v in dict(task.config).items() if not str(k).endswith(("_path", "_resource"))}
    build = Path("/opt/uipc-build.json")
    uipc_build = json.loads(build.read_text()).get("source_commit") if build.is_file() else None
    return to_jsonable(dict(codec=CODEC, genesis=version("genesis-world"), pyuipc=version("pyuipc"), uipc_build=uipc_build,
                            task_id=task.task_id, seed=task.seed, parameters=parameters,
                            physics_options=spec.physics_options, asset_sha256=dict(asset_build.sha256)))


def _slot_keys(store):
    """(geometry index, collection, attribute) of every buffer CheckpointStore._slots() returns, in its order: buffers are
    matched by these names, not by position and shape alone."""
    from uipc.backend import SceneVisitor
    keys = []
    for index, slot in enumerate(SceneVisitor(store.coupler._ipc_scene).geometries()):
        geometry = slot.geometry()
        for collection_name, collection in geometry.to_json().items():
            if not isinstance(collection, dict):
                continue
            for name in collection:
                target = geometry[collection_name].find(name)
                try:
                    value = np.asarray(target.view())
                except (AttributeError, TypeError):
                    continue
                if value.dtype.kind in "fiu":
                    keys.append([index, collection_name, name])
    return keys


def _fem_positions(world):
    from topogym.world.physics.fem import read_vertices
    return {name: np.asarray(read_vertices(entity)["position_m"], dtype=np.float64)
            for name, entity in world.entities.items() if hasattr(entity, "material_coordinates")}


def export_settled_state(world, folder, *, scene_identity, metadata):
    """Write the world's current native IPC state to `folder` (must not exist). Returns the manifest path."""
    coupler = world.scene.sim.coupler
    state = coupler.checkpoint_store.capture()
    files = [(relative, zlib.decompress(data)) for relative, data in state.files]
    previous = [value for _, value in state.previous_link_transforms]
    for value in previous:
        for row in value:
            for item in row:
                if item is not None and not isinstance(item, np.ndarray):
                    raise TypeError(f"Unsupported previous link transform {type(item).__name__}")
    payload = dict(attributes=[np.asarray(values) for _, values in state.attributes], previous=previous,
                   fem=_fem_positions(world))
    keys = _slot_keys(coupler.checkpoint_store)
    if len(keys) != len(payload["attributes"]):
        raise RuntimeError("IPC attribute buffer names do not match CheckpointStore's buffers")
    meta = dict(codec=CODEC, identity=scene_identity, frame=int(state.frame), metadata=metadata, attribute_keys=keys,
                files=[dict(path=relative, sha256=_sha256(data), bytes=len(data)) for relative, data in files])
    manifest = save_numeric_archive(folder, payload, meta)
    for relative, data in files:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"Unexpected native dump path {relative}")
        path = Path(folder) / "dump" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return manifest


def restore_settled_state(world, manifest_path, *, scene_identity):
    """Restore the archived state into `world` (built, at its first native frame, nothing stepped since)."""
    import uipc
    from genesis.engine.couplers.ipc_coupler.data import COUPLING_TYPE
    import genesis.utils.geom as gu

    manifest_path = Path(manifest_path)
    meta = read_archive_manifest(manifest_path)["metadata"]
    if meta.get("codec") != CODEC:
        raise ValueError(f"Unsupported IPC settled-state codec {meta.get('codec')!r}")
    if meta["identity"] != scene_identity:
        changed = sorted(k for k in set(meta["identity"]) | set(scene_identity)
                         if meta["identity"].get(k) != scene_identity.get(k))
        raise ValueError(f"IPC settled state belongs to another scene or native format: {changed}")
    payload, _ = load_numeric_archive(manifest_path)
    coupler = world.scene.sim.coupler
    store, native = coupler.checkpoint_store, coupler._ipc_world
    source, current = int(meta["frame"]), int(native.frame())
    existing = sorted(str(p.relative_to(store.workspace)) for p in store.workspace.rglob("*")
                      if p.is_file() and (p.name.endswith(f".{current}") or p.name.endswith(f".{current}.json")))
    written = []
    for entry in meta["files"]:
        data = relative_file(manifest_path.parent / "dump", entry["path"]).read_bytes()
        if _sha256(data) != entry["sha256"]:
            raise ValueError(f"IPC settled-state file hash mismatch: {entry['path']}")
        relative = _at_frame(entry["path"], source, current)
        if relative.endswith(".json"):   # libuipc's state.<frame>.json carries the frame, and recover() checks it
            record = json.loads(data.decode())
            if isinstance(record, dict) and "frame" in record:
                record["frame"] = current
            data = json.dumps(record, indent=4).encode()
        path = store.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(relative)
    if existing and sorted(written) != existing:
        raise ValueError("IPC settled state has another native subsystem set than this scene")
    if store.attribute_slots is None:
        store.attribute_slots = store._slots()
    slots, values = store.attribute_slots, payload["attributes"]
    if len(slots) != len(values) or _slot_keys(store) != meta["attribute_keys"]:
        raise ValueError(f"IPC settled state has other attribute buffers than this scene ({len(values)} vs {len(slots)})")
    for slot, value in zip(slots, values):
        view = uipc.view(slot)
        if np.asarray(view).shape != value.shape or np.asarray(view).dtype != value.dtype:
            raise ValueError("IPC settled-state attribute buffer differs in shape or type")
        np.copyto(view, value)
    if not native.recover(current) or int(native.frame()) != current:
        raise RuntimeError(f"Native IPC recover({current}) of the settled state failed")
    native.retrieve()
    articulations = list(coupler._articulation_data_by_entity.values())
    if len(articulations) != len(payload["previous"]):
        raise ValueError("IPC settled state has another articulation set")
    for data, value in zip(articulations, payload["previous"]):
        data.prev_links_transform = deepcopy(value)
    # Genesis side, as EpisodeIPCCoupler.reset does after its own recover (no clock advance).
    coupler._target_substep = 0
    coupler._store_gs_rigid_states()
    coupler._retrieve_fem_states()
    coupler._retrieve_rigid_states()
    for entity in coupler._entities_by_coup_type.get(COUPLING_TYPE.IPC_ONLY, ()):
        if entity.base_link.is_fixed:
            continue
        pos, quat = gu.T_to_trans_quat(np.asarray(coupler._abd_data_by_link[entity.base_link][0].transform))
        qpos = np.r_[np.asarray(pos, dtype=np.float64), np.asarray(quat, dtype=np.float64)]
        coupler.rigid_solver.set_qpos(qpos, qs_idx=slice(entity.q_start, entity.q_start + 7), skip_forward=False)
        coupler.rigid_solver.set_dofs_velocity(velocity=None, dofs_idx=slice(entity.dof_start, entity.dof_start + 6),
                                               skip_forward=False)
    restored = _fem_positions(world)
    error = max((float(np.max(np.abs(restored[name] - value))) for name, value in payload["fem"].items()), default=0.0)
    if set(restored) != set(payload["fem"]) or error > 0.0:
        raise RuntimeError(f"IPC settled state did not reach Genesis' FEM vertices (max |dx| {error})")
    return dict(codec=CODEC, source_frame=source, frame=current, files=len(written), attributes=len(slots),
                metadata=meta["metadata"])


def _sha256(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _at_frame(relative, source, current):
    for suffix in (f".{source}.json", f".{source}"):
        if relative.endswith(suffix):
            return relative[: -len(suffix)] + suffix.replace(f".{source}", f".{current}")
    raise ValueError(f"Native dump file {relative} does not belong to frame {source}")
