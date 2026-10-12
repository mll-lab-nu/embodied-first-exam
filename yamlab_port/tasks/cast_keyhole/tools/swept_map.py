"""Where does the silver plate go, relative to gold, along the route?  Rasterise the silver material
(sampled points) over all route samples into the gold plate frame, keep |gold z| <= zmax, and plot the
projection on the gold plane together with the gold outline (to choose a gold grasp the silver never sweeps).

usage: python swept_map.py <tier> <turn_sign> [zmax_m]   -> swept_<tier>_<sign>.png / .npz
"""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import route as rt
from route_check import plate_cells

tier, sign = sys.argv[1], int(sys.argv[2])
zmax = float(sys.argv[3]) if len(sys.argv) > 3 else .055
rec = kg.load_record(tier)
plates = kg.build_plates(rec)
rng = np.random.default_rng(0)
pts = []
for v in plate_cells(plates["silver"]):
    lo, hi = v.min(0), v.max(0)
    n = int(np.prod(np.maximum(hi - lo, 1e-3)) / 1e-9 * 0.4) + 50
    p = lo + rng.random((n, 3)) * (hi - lo)
    # keep points inside the convex cell (half-space test via the hull)
    import trimesh
    h = trimesh.convex.convex_hull(v)
    inside = np.all((h.face_normals @ p.T).T - np.sum(h.face_normals * h.triangles[:, 0], axis=1) <= 1e-9, axis=1)
    pts.append(p[inside])
pts = np.concatenate(pts)
path = rt.route(rec, tier, sign, n_turn=45, step_m=.002)
res = .001
H = {}
for r, c, stage in path:
    origin = rt.silver_plate_pose_in_gold(r, c, rec["scale"])
    q = r.apply(pts) + origin
    q = q[np.abs(q[:, 2]) <= zmax]
    key = "turn" if stage.startswith("turn") else "slide"
    H.setdefault(key, set()).update(map(tuple, np.round(q[:, :2] / res).astype(int)))
fig, ax = plt.subplots(figsize=(6, 10))
colors = {"turn": (0.2, 0.4, 1.0, 0.25), "slide": (1.0, 0.3, 0.2, 0.25)}
for k, s in H.items():
    a = np.array(list(s)) * res * 1000
    ax.scatter(a[:, 0], a[:, 1], s=1, color=colors[k], label=f"silver swept ({k}), |z|<={zmax*1000:.0f}mm")
for ring in plates["gold"].rings:
    r_ = np.asarray(ring) * rec["scale"]
    ax.plot(*np.vstack((r_, r_[:1])).T, "k-", lw=1)
ax.set_aspect("equal"); ax.grid(alpha=.3); ax.legend(loc="upper right", fontsize=7)
ax.set_xlabel("gold plate x (mm)"); ax.set_ylabel("gold plate y (mm)")
ax.set_title(f"{tier} sign {sign:+d}: silver sweep in the gold plane")
out = Path(__file__).parent / f"swept_{tier}_{sign:+d}.png"
fig.savefig(out, dpi=110)
np.savez(out.with_suffix(".npz"), **{k: np.array(list(s)) for k, s in H.items()}, res=res)
print("wrote", out)
