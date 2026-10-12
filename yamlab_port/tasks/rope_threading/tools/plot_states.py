"""Stand-in for video: top (x-y) and side (y-z, x-z) views of the logged rope, TCPs and rings at chosen steps.
Usage: python plot_states.py <run_dir> [step ...]   (needs matplotlib; reads states.npz, rings from the task lib)"""
import importlib.util, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

run = sys.argv[1]
lib = os.environ.get("RT_LIB", "/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab/envs/tasks/rope_threading_lib")
spec = importlib.util.spec_from_file_location("threading_geom", f"{lib}/threading_geom.py")
TH = importlib.util.module_from_spec(spec); spec.loader.exec_module(TH)
scn = TH.scene(os.environ.get("RT_TIER", "easy"))
S = np.load(os.path.join(run, "states.npz"))
P, TCP = S["rope_pos"], S["tcp"]
n = len(P)
steps = [int(x) for x in sys.argv[2:]] or list(np.linspace(0, n - 1, 8).astype(int))
fig, axs = plt.subplots(len(steps), 3, figsize=(15, 4 * len(steps)))
for r, k in enumerate(steps):
    k = min(k, n - 1)
    for c, (i, j, lab) in enumerate(((0, 1, "top x-y"), (1, 2, "side y-z"), (0, 2, "side x-z"))):
        ax = axs[r, c] if len(steps) > 1 else axs[c]
        for ring in scn["rings"]:
            u, v = TH.ring_basis(ring["normal"])
            th = np.linspace(0, 2 * np.pi, 100)
            pts = ring["center"] + ring["radius"] * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
            ax.plot(pts[:, i], pts[:, j], color="c" if ring["name"] == "R1" else "g", lw=3)
        ax.plot(P[k][:, i], P[k][:, j], color="orange", lw=2)
        ax.plot(P[k][0, i], P[k][0, j], "go"); ax.plot(P[k][-1, i], P[k][-1, j], "rs")
        ax.plot(TCP[k][0 + i], TCP[k][0 + j], "b^", label="left TCP"); ax.plot(TCP[k][3 + i], TCP[k][3 + j], "m^", label="right TCP")
        ax.set_aspect("equal"); ax.set_title(f"step {k}  {lab}"); ax.grid(alpha=0.3)
plt.tight_layout()
out = os.path.join(run, "states_plot.png")
plt.savefig(out, dpi=60)
print("PLOT", out)
