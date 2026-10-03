"""Cloth grasp-assist support for the Blanket oracles, kept out of the task and world code.

`pbd_local_patch_v1` needs the cloth entity to declare a birth material (UV) map,
which the Blanket task does not declare. `enable()` adds it at runtime, for the
oracle processes only:

1. The Blanket task's declared cloth entity gains `material_map_path`, pointing to
   an archive of its flat birth surface/UV written beside (not inside) the hashed
   asset folder, so the frozen initial-state identity is unchanged.
2. The bound per-particle material coordinates are made read-only. World
   checkpoints snapshot every writable array reachable from an entity; a writable
   map would enter the buffer inventory and the frozen initial state would refuse
   to restore. The map is constant birth data, not engine state.

Geometry, materials, physics, the frozen initial state and the Task's success
predicate are untouched.
"""
from dataclasses import replace
from pathlib import Path

import numpy as np

_ENABLED = []


def enable():
    if _ENABLED:
        return
    from topogym.tasks.blanket_flatten.common import BlanketFlattenTask
    import topogym.world.physics.pbd as pbd

    declare = BlanketFlattenTask.declare

    def declare_with_material_map(self, asset_dir, table_height_m):
        spec = declare(self, asset_dir, table_height_m)
        if self.config["initialization_mode"] == "authored":
            return spec
        path = Path(asset_dir).parent / "blanket_material_map.npz"
        np.savez(path, vertices=self.birth_vertices, faces=self.birth_faces.astype(np.int64), uv=self.birth_uv)
        entities = tuple(replace(e, material_map_path=path) if e.name == "blanket" else e for e in spec.entities)
        return replace(spec, entities=entities)

    bind = pbd.bind_material_map

    def bind_read_only(entity, path):
        bind(entity, path)
        entity.grasp_material_coordinates.flags.writeable = False

    BlanketFlattenTask.declare = declare_with_material_map
    pbd.bind_material_map = bind_read_only
    _ENABLED.append(True)
