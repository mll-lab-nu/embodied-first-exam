"""Matplotlib stand-in for a render: plates (and link_6 / TCP markers) from a states .npz at chosen steps.

usage: python plot_state.py <states.npz> <layout.json> <out.png> [step ...]   (default: first, middle, last)
Three views per step: top (x-y), front (y-z), side (x-z); the goal square and separator are drawn.
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

z = np.load(sys.argv[1])
lay = json.load(open(sys.argv[2]))
out = sys.argv[3]
n = len(z["keyhole_gold"])
steps = [int(s) for s in sys.argv[4:]] or [0, n // 2, n - 1]
steps = [min(max(s if s >= 0 else n + s, 0), n - 1) for s in steps]
V = {k: np.asarray(v) for k, v in lay["vertices_part_m"].items()}
g = lay["goal_region"]
col = {"keyhole_gold": "#b8860b", "keyhole_silver": "#708090"}
fig, axes = plt.subplots(len(steps), 3, figsize=(15, 4.2 * len(steps)), squeeze=False)
for r, s in enumerate(steps):
    for c, (i, j, title) in enumerate(((0, 1, "top x-y"), (1, 2, "front y-z"), (0, 2, "side x-z"))):
        ax = axes[r, c]
        for name, verts in V.items():
            st = z[name][s]
            P = Rotation.from_quat(st[[4, 5, 6, 3]]).apply(verts) + st[:3]
            ax.scatter(P[:, i], P[:, j], s=1, color=col[name])
        for arm, cc in (("left_arm", "tab:blue"), ("right_arm", "tab:red")):
            if arm + "_link6" in z:
                L = z[arm + "_link6"][s]
                ax.plot(L[i], L[j], "o", color=cc, ms=6)
            if arm + "_tcp" in z:
                T = z[arm + "_tcp"][s]
                ax.plot(T[i], T[j], "x", color=cc, ms=8)
        if (i, j) == (0, 1):
            (x0, y0), (x1, y1) = g["xy_min"], g["xy_max"]
            ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], "g--")
            ax.axhline(g["separator_offset"] * g.get("separator_sign", 1.0), color="k", ls=":", lw=1)
        else:
            ax.axhline(g["table_z"], color="k", lw=1)
        ax.set_aspect("equal"); ax.grid(alpha=.3)
        ax.set_title(f"step {s}: {title}")
fig.tight_layout()
fig.savefig(out, dpi=80)
print("wrote", out)
