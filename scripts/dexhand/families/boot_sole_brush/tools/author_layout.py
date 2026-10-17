"""Authoring: place the six clods on the sole (raycast on the boot's contact hulls) and write them to task.json."""
import json, sys
from pathlib import Path
import numpy as np, mujoco
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from scene import build, clod_vertices
CLODS_LOCAL = [(-0.025, -0.085), (0.025, -0.068), (-0.025, -0.047), (0.025, 0.036), (-0.025, 0.048), (0.025, 0.083)]
path = HERE / "task.json"
cfg = json.loads(path.read_text())
b = cfg["boot"]
cfg["rack"]["peg_top_z"] = round(b["pos"][2] - b["footbed_local_z"] - 0.008, 6)
cfg["clods"] = []
m, _ = build(cfg)
d = mujoco.MjData(m); mujoco.mj_forward(m, d)
P = d.xpos[m.body("boot").id]; R = d.xmat[m.body("boot").id].reshape(3, 3)
patches = [m.geom(f"boot_patch_{i}").id for i in range(292)]
clods = []
for i, (lx, ly) in enumerate(CLODS_LOCAL):
    v = clod_vertices(i)
    hits = []
    for dx in (-0.004, 0.0, 0.004):
        for dy in (-0.004, 0.0, 0.004):
            o = P + R @ np.array([lx, ly, 0.0]) + np.array([dx, dy, 0.1])
            dist = min(d_ for d_ in (mujoco.mj_rayMesh(m, d, g, o, np.array([0, 0, -1.0])) for g in patches) if d_ >= 0)
            hits.append(o[2] - dist)
    surface = max(hits)
    center = P + R @ np.array([lx, ly, 0.0])
    center[2] = surface - v[:, 2].min() + 0.0003
    clods.append({"local_xy": [lx, ly], "pos": [round(float(c), 6) for c in center], "quat": [1, 0, 0, 0]})
    print(i, (lx, ly), "surface z", round(surface, 4), "spread", round(max(hits) - min(hits), 4), "center", center.round(4))
cfg["clods"] = clods
path.write_text(json.dumps(cfg, indent=2) + "\n")
