"""Authoring probe: boot interior and sole heights in the frozen mounting (prints numbers only)."""
import json, sys
from pathlib import Path
import numpy as np, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene import build, BOOT_ROTATION
cfg = json.loads((Path(__file__).resolve().parents[1] / "task.json").read_text())
m, xml = build(cfg)
d = mujoco.MjData(m); mujoco.mj_forward(m, d)
boot = m.body("boot").id
P = d.xpos[boot]; R = d.xmat[boot].reshape(3, 3)
print("boot pos", P, "\nR", R.round(3))
patch = [m.geom(f"boot_patch_{i}").id for i in range(292)]
vis = m.geom("boot_visual").id
def ray(origin, direction, groups):
    gid = np.zeros(1, np.int32); best = (np.inf, -1)
    for g in groups:
        dist = mujoco.mj_rayMesh(m, d, g, origin, direction) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH else -1
        if 0 <= dist < best[0]: best = (dist, g)
    return best
def L2W(p): return P + R @ np.asarray(p, float)
# footbed: from inside the shaft toward the sole (local -z)
for name, groups in (("patch", patch), ("visual", [vis])):
    o = L2W([0, 0.065, 0.30]); dirn = R @ np.array([0, 0, -1.0])
    dist, g = ray(o, dirn, groups)
    print(name, "inner sole along shaft axis at local z =", 0.30 - dist)
# shaft interior half-widths at several heights
for z in (0.06, 0.10, 0.14, 0.18, 0.22, 0.26, 0.30):
    out = []
    for direction in ([1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]):
        o = L2W([0, 0.065, z]); dist, g = ray(o, R @ np.array(direction, float), patch)
        dv, _ = ray(o, R @ np.array(direction, float), [vis])
        out.append((round(dist, 4), round(dv, 4)))
    print("local z", z, "patch/visual distances +x -x +y -y:", out)
# sole surface heights (world) along the sole
for ly in np.arange(-0.11, 0.111, 0.01):
    row = []
    for lx in (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03):
        o = L2W([lx, ly, -0.1]); dist, g = ray(o, np.array([0, 0, -1.0]), patch)
        row.append(f"{(o[2]-dist-P[2])*1000:6.1f}" if np.isfinite(dist) else "   .  ")
    print(f"ly {ly:+.2f}", " ".join(row))
