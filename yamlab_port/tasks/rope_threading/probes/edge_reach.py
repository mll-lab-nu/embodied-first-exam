"""Left top-down deep grasp past the left table edge (y > 0.55): rope along y, rope centre z_r, TCP = rope + 0.012 z."""
import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
EY, EZ = PN.EY, PN.EZ
for zr in (0.745, 0.735):
    for x in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        row = []
        for y in (0.69, 0.71, 0.73, 0.75):
            r = "."
            for zs in (1, -1):
                T = PN.frame_az(-EZ, zs * EY, (x, y, zr + 0.012))
                q = PN.solve("left", T, margin=0.03)
                if q is not None:
                    c = PN.arm_clearance("left", q, FIX)
                    r = ("+" if zs > 0 else "-") if min(c.values()) > 0.005 else "c"
                    if r != "c": break
            row.append(r)
        print(f"rope z {zr:.3f} x {x:.2f}: y 0.69..0.75 ->", " ".join(row))
