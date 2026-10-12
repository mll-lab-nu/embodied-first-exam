"""Top-view + side-view frame strip of a logged run (states.npz from oracle.py / replay.py): rope
centreline coloured by height, crossings marked, TCPs of both arms. No Isaac needed.
  python plot_run.py <run_dir> [n_frames]"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

run = sys.argv[1]
nf = int(sys.argv[2]) if len(sys.argv) > 2 else 8
S = np.load(os.path.join(run, "states.npz"))
P = S["rope_pos"]
T = S["tcp"] if "tcp" in S.files else None
mp = os.path.join(run, "metrics.json")
if os.path.exists(mp) and json.load(open(mp)).get("end_reason"):
    # evaluation mode: the env auto-reset inside the terminating step -> drop that reset frame
    P = P[:-1]
    T = T[:-1] if T is not None else None
idx = np.linspace(0, len(P) - 1, nf).astype(int)
fig, axs = plt.subplots(2, nf, figsize=(3 * nf, 6), gridspec_kw=dict(height_ratios=[3, 1]))
for c, k in enumerate(idx):
    p = P[k]
    ax = axs[0, c]
    sc = ax.scatter(p[:, 1], p[:, 0], c=(p[:, 2] - 0.75) * 1000, s=6, cmap="viridis", vmin=0, vmax=30)
    ax.plot(p[:, 1], p[:, 0], "-", lw=0.5, color="k", alpha=0.4)
    ax.plot(p[0, 1], p[0, 0], "go", ms=5); ax.plot(p[-1, 1], p[-1, 0], "rs", ms=5)
    if T is not None:
        ax.plot(T[k, 1], T[k, 0], "b^", ms=6); ax.plot(T[k, 4], T[k, 3], "m^", ms=6)
    ax.set_xlim(0.45, -0.45); ax.set_ylim(0.30, 0.85); ax.set_aspect("equal")
    ax.set_title(f"step {k + 1} ({(k + 1) / 30:.1f} s)", fontsize=8)
    ax.tick_params(labelsize=6)
    ax2 = axs[1, c]
    ax2.plot(p[:, 0], (p[:, 2] - 0.75) * 1000, ".", ms=2)
    if T is not None:
        ax2.plot([T[k, 0], T[k, 3]], [(T[k, 2] - 0.75) * 1000, (T[k, 5] - 0.75) * 1000], "^")
    ax2.set_ylim(-2, 120); ax2.tick_params(labelsize=6)
axs[0, 0].set_ylabel("world x (m), top view, y to the left"); axs[1, 0].set_ylabel("z above 0.75 (mm)")
fig.colorbar(sc, ax=axs[0, -1], fraction=0.05, label="centre height mm")
plt.tight_layout()
out = os.path.join(run, "frames_topview.png")
plt.savefig(out, dpi=80)
print("WROTE", out)
