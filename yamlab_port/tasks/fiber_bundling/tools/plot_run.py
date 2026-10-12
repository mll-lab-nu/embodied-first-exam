"""Stand-in visual evidence from logged states (no RTX): top + side views of the cable, ring and gripper
at key steps, plus time series (front offset/position, strand radius, bend, contact force).

  python plot_run.py <run_dir> [--frames 8]  -> <run_dir>/plot_views.png, plot_series.png, (gif strip)
"""
import argparse, json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--frames", type=int, default=8)
ap.add_argument("--layout", default=None)
a = ap.parse_args()
S = dict(np.load(os.path.join(a.run, "states.npz"), allow_pickle=True))
M = json.load(open(os.path.join(a.run, "metrics.json")))
names = list(S["link_names"]); links = S["links"]; phase = S["phase"]
lay_path = a.layout or os.path.join(os.path.dirname(os.path.dirname(a.run)), "assets", "very_easy", "layout_world.json")
lay = json.load(open(lay_path))
c = np.array(lay["ring"]["center"]); Rr = np.array(lay["ring"]["R"]); rc = lay["ring"]["centerline_radius"]
ang = np.linspace(0, 2*np.pi, 65); ring = (np.c_[rc*np.cos(ang), rc*np.sin(ang), 0*ang] @ Rr.T)+c


def qmat(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def centerlines(k):
    P = links[k]
    out = {}
    for i, n in enumerate(names):
        L = lay["links"][n]["length"]; p = P[i, :3].astype(float); R = qmat(P[i, 3:].astype(float))
        out[n] = (p, p+R[:, 0]*L)
    return out


# key steps: phase starts + end
keys = [0]+[i for i in range(1, len(phase)) if phase[i] != phase[i-1]]+[len(phase)-1]
keys = sorted(set(keys))
if len(keys) > a.frames:
    keys = [keys[int(round(j))] for j in np.linspace(0, len(keys)-1, a.frames)]
fig, axes = plt.subplots(2, len(keys), figsize=(3.2*len(keys), 6.4))
axes = np.atleast_2d(axes).reshape(2, -1)
for j, k in enumerate(keys):
    cl = centerlines(k)
    hand = S["hand"][k]
    for row, (u, v, lab) in enumerate(((0, 1, "top (x right, y up)"), (1, 2, "side (y right, z up)"))):
        ax = axes[row, j]
        ax.plot(ring[:, u], ring[:, v], color="#c08030", lw=2)
        for n, (p0, p1) in cl.items():
            kind = lay["links"][n]["kind"]
            if kind == "terminal":
                continue
            col = {"lead": "#555", "trunk": "k", "fiber": ("#b02020" if n.startswith("fiber_00") else "#2050b0")}[kind]
            ax.plot([p0[u], p1[u]], [p0[v], p1[v]], color=col, lw=4 if kind == "trunk" else (1 if kind == "fiber" else 3))
        ax.plot(hand[u, 3], hand[v, 3], "g^", ms=8)
        tcp = hand[:3, 3]+hand[:3, 2]*0.1165
        ax.plot([hand[u, 3], tcp[u]], [hand[v, 3], tcp[v]], "g-", lw=2)
        if row == 0:
            ax.set_xlim(c[0]-0.12, c[0]+0.12); ax.set_ylim(c[1]-0.22, c[1]+0.06)
            ax.set_title(f"step {k}\n{phase[k]}", fontsize=9)
        else:
            ax.set_xlim(c[1]-0.22, c[1]+0.06); ax.set_ylim(c[2]-0.10, c[2]+0.14)
        ax.set_aspect("equal"); ax.tick_params(labelsize=6)
        if j == 0: ax.set_ylabel(lab, fontsize=8)
fig.suptitle(f"{os.path.basename(a.run)}: success={M['success']} failed={M['failed']} ({M.get('failure_reason')})", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(a.run, "plot_views.png"), dpi=90)

fig, ax = plt.subplots(5, 1, figsize=(10, 9), sharex=True)
t = np.arange(len(phase))/30.0
ax[0].plot(t, S["front_ahead"]*1000); ax[0].axhline(16, ls="--", c="r"); ax[0].set_ylabel("front ahead\nof ring [mm]")
ax[1].plot(t, S["front_offset"]*1000); ax[1].axhline(1.479, ls="--", c="r"); ax[1].set_ylabel("front radial\noffset [mm]"); ax[1].set_ylim(0, 10)
ax[2].plot(t, S["max_radial"]*1000); ax[2].axhline(17.479, ls="--", c="r"); ax[2].set_ylabel("max strand\nradius [mm]"); ax[2].set_ylim(0, 80)
ax[3].plot(t, S["max_bend"]); ax[3].axhline(60, ls="--", c="r"); ax[3].set_ylabel("max bend [deg]")
ax[4].plot(t, S["force"]); ax[4].set_ylabel("gripper-strand\nforce [N]"); ax[4].set_xlabel("time [s]")
for k in keys:
    for x in ax: x.axvline(k/30.0, c="0.8", lw=0.5)
fig.tight_layout(); fig.savefig(os.path.join(a.run, "plot_series.png"), dpi=90)
print("wrote", os.path.join(a.run, "plot_views.png"), os.path.join(a.run, "plot_series.png"))
