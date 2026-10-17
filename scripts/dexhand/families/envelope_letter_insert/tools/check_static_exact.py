#!/usr/bin/env python3
"""Authoring only: exact (triangle-level) check of every robot mesh geom against every furniture box at reset, plus
the robot geoms' lowest point against the floor plane. Usage: check_static_exact.py [base_x base_y base_z yaw]."""
import json, sys
from pathlib import Path
import numpy as np
import mujoco
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tools")); sys.path.append(str(HERE.parents[1] / "shared"))
import scene  # noqa
from tri_box import tris_overlap_box, mesh_triangles  # noqa

cfg = json.loads((HERE / "task.json").read_text())
if len(sys.argv) >= 5:
    cfg["marvin"] = {"base_pos": [float(x) for x in sys.argv[1:4]], "base_yaw": float(sys.argv[4])}
model, _ = scene.build(cfg)
data = mujoco.MjData(model)
qadr = model.jnt_qposadr[model.actuator_trnid[:, 0]]
data.qpos[qadr] = cfg["initial_targets"]["sharpa"] if len(sys.argv) < 5 else data.qpos[qadr]
mujoco.mj_forward(model, data)
root = model.body("base_link").id
robot = []
for g in range(model.ngeom):
    b = int(model.geom_bodyid[g])
    p = b
    while p and p != root:
        p = int(model.body_parentid[p])
    if p == root:
        robot.append(g)
furniture = [g for g in range(model.ngeom) if model.geom_bodyid[g] == 0 and model.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX]
floor = [g for g in range(model.ngeom) if model.geom_bodyid[g] == 0 and model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE]
hits = []
lowest = []
for g in robot:
    if model.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
        continue
    tri = mesh_triangles(model, data, g)
    lowest.append((float(tri[:, :, 2].min()), g))
    for f in furniture:
        m = tris_overlap_box(tri, data.geom_xpos[f], data.geom_xmat[f].reshape(3, 3), model.geom_size[f])
        if m.any():
            hits.append({"robot": f"{model.body(int(model.geom_bodyid[g])).name}/geom{g}", "group": int(model.geom_group[g]),
                         "furniture": model.geom(f).name, "triangles": int(m.sum())})
floor_z = [float(data.geom_xpos[f][2]) for f in floor]
low = min(lowest)
print(json.dumps({"base": cfg["marvin"], "exact_overlaps": hits, "floor_z": floor_z,
                  "robot_lowest_z": round(low[0], 4), "lowest_geom": f"{model.body(int(model.geom_bodyid[low[1]])).name}/geom{low[1]}"}, indent=1))
