"""Left arm: reachable approaches when the rope (z_tcp) runs along +-x, approach in the y-z plane at angle th from
-z toward -y (th > 0) or +y (th < 0); grip point = TCP + 0.035 approach. Grid over grip x, y, z."""
import sys, json, numpy as np
sys.path.insert(0, '/workspace/yamlab_port/runs/rope_threading/task/tools')
import plan_np as PN
meta = json.load(open('/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib/assets/easy/rope_meta.json'))
FIX = PN.fixture_capsules(meta['rings'])
EX, EY, EZ = PN.EX, PN.EY, PN.EZ
ths = list(range(-60, 91, 15))
print("th:", ths)
for z in (0.80, 0.86, 0.95, 1.02, 1.07):
    for x in (0.62, 0.68, 0.74):
        for y in (0.28, 0.33, 0.38):
            row = ""
            for th in ths:
                r = np.radians(th)
                a = np.array([0, -np.sin(r), -np.cos(r)])
                ok = "."
                for zs in (1, -1):
                    T = PN.frame_az(a, zs * EX); T[:3, 3] = np.array([x, y, z]) - 0.035 * a
                    q = PN.solve("left", T, margin=0.03)
                    if q is not None and min(PN.arm_clearance("left", q, FIX).values()) > 0.01:
                        ok = "+" if zs > 0 else "-"
                        if zs < 0: break
                row += ok
            print(f"z={z:.2f} x={x:.2f} y={y:.2f} {row}"); sys.stdout.flush()
