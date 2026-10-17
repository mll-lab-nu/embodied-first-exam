#!/usr/bin/env python3
"""Authoring only: minimum vertex clearance (m) of every robot mesh geom (outside the active hand) from every furniture
box over a trajectory (complements the exact SAT overlap test of check_robot_furniture.py)."""
import json, sys
from pathlib import Path
import numpy as np
import mujoco
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tools")); sys.path.append(str(HERE.parents[1] / "shared"))
from runtime import Session  # noqa
from replay import load_trajectory  # noqa
from check_robot_furniture import subtree  # noqa

rows, hand, _ = load_trajectory(sys.argv[1])
every = int(sys.argv[2]) if len(sys.argv) > 2 else 5
s = Session(hand=hand); m, d = s.model, s.data
rb = subtree(m, m.body("base_link").id); ah = subtree(m, m.body("wrist_stage").id)
robot = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in rb and int(m.geom_bodyid[g]) not in ah and m.geom_type[g] == 7]
furn = [g for g in range(m.ngeom) if m.geom_bodyid[g] == 0 and m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX]
local = {g: m.mesh_vert[m.mesh_vertadr[m.geom_dataid[g]]: m.mesh_vertadr[m.geom_dataid[g]] + m.mesh_vertnum[m.geom_dataid[g]]] for g in robot}
best = {}
s.reset()
for k in range(-1, len(rows)):
    if k >= 0:
        s.step(rows[k])
        if k % every and not s.done:
            continue
    for g in robot:
        w = local[g] @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
        for f in furn:
            p = (w - d.geom_xpos[f]) @ d.geom_xmat[f].reshape(3, 3)
            q = np.maximum(np.abs(p) - m.geom_size[f], 0.0)
            dist = float(np.sqrt((q ** 2).sum(1)).min())
            if dist < best.get((g, f), (np.inf,))[0]:
                best[(g, f)] = (dist, k)
    if s.done:
        break
top = sorted(best.items(), key=lambda t: t[1][0])[:6]
out = [dict(robot=f"{m.body(int(m.geom_bodyid[g])).name}/geom{g}", furniture=m.geom(f).name, min_vertex_clearance_m=round(v[0], 4), control=v[1]) for (g, f), v in top]
print(json.dumps(out, indent=1))
