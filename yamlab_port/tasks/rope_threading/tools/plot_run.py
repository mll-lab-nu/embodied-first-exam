"""Top views (plot_layout.draw_state: robot at the bottom, +y left) of a medium run's logged states at chosen steps.
Layout from RT_RELAYOUT (shift_env.sh); steps are action counts (states index = step - 1).
Usage: python plot_run.py <states.npz> --steps 6000 6500 --titles "a" "b" --out fig.png [--suptitle ...]
"""
import argparse, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plot_layout as PL

ap = argparse.ArgumentParser()
ap.add_argument("states")
ap.add_argument("--steps", type=int, nargs="+", required=True)
ap.add_argument("--titles", nargs="+", default=None)
ap.add_argument("--suptitle", default="")
ap.add_argument("--out", required=True)
a = ap.parse_args()
cfg = json.loads(os.environ["RT_RELAYOUT"])
rings, _ = PL.scene(cfg["yaw_deg"], cfg["t_xy"], cfg["rope_yaw_deg"], cfg["rope_t_xy"])
S = np.load(a.states)
n = len(a.steps)
fig, axs = plt.subplots(1, n, figsize=(13 * n, 13.5), dpi=100, squeeze=False)
for i, st in enumerate(a.steps):
    k = min(st, len(S["q"])) - 1
    title = a.titles[i] if a.titles else f"step {st}"
    PL.draw_state(axs[0, i], rings, S["q"][k], S["rope_pos"][k], f"{title}（step {st}, {st / 30:.1f} s）", feed_tip="start",
                  end_labels=False)
    axs[0, i].plot(*PL.uv(S["rope_pos"][k][0]), "*", color="#c0392b", ms=30, zorder=9)      # the fed (start) tip
if a.suptitle:
    fig.suptitle(a.suptitle, fontsize=26)
fig.tight_layout()
fig.savefig(a.out)
print("saved", a.out)
