"""Old vs new start of the wand (top and side views, YAM world frame, layout yaw 0)."""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial.transform import Rotation
from bw_geom import *

s = Scene(layout=Layout(0.0, (0.5144, 0.270, TABLE_Z)))
post = s.rail[0]
old_R, old_p = s.start_R, s.start_p
h_old = np.degrees(np.arctan2(*old_R.apply([1, 0, 0])[[1, 0]]))
NEW_YAW = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
Rz = Rotation.from_euler("z", NEW_YAW - h_old, degrees=True)
new_R = Rz * old_R
new_p = Rz.apply(old_p - np.r_[post[:2], 0]) + np.r_[post[:2], 0]


def wand_outline(p, R):
    a = np.linspace(0, 2 * np.pi, 100)
    ring_o = np.c_[(LOOP_R + TUBE_R) * np.cos(a), (LOOP_R + TUBE_R) * np.sin(a), 0 * a]
    ring_i = np.c_[(LOOP_R - TUBE_R) * np.cos(a), (LOOP_R - TUBE_R) * np.sin(a), 0 * a]
    stem = np.array([[LOOP_R, 0, 0], [GRIP_X0, 0, 0]])
    box = np.array([[GRIP_X0, -GRIP_HALF_W, 0], [GRIP_X1, -GRIP_HALF_W, 0], [GRIP_X1, GRIP_HALF_W, 0], [GRIP_X0, GRIP_HALF_W, 0], [GRIP_X0, -GRIP_HALF_W, 0]])
    boxs = np.array([[GRIP_X0, 0, -GRIP_HALF_T], [GRIP_X1, 0, -GRIP_HALF_T], [GRIP_X1, 0, GRIP_HALF_T], [GRIP_X0, 0, GRIP_HALF_T], [GRIP_X0, 0, -GRIP_HALF_T]])
    return [R.apply(x) + p for x in (ring_o, ring_i, stem, box, boxs)]


fig, ax = plt.subplots(2, 2, figsize=(13, 9))
for col, (title, p, R, col_c) in enumerate((("OLD start (handle under the wire span: YAM cannot pick it)", old_p, old_R, "tab:red"),
                                             (f"NEW start (handle yawed to {NEW_YAW:.0f} deg about the start post)", new_p, new_R, "tab:green"))):
    t, sd = ax[0, col], ax[1, col]
    for c, h, Rb in s.deck_boxes[:2]:
        ext = Rb.as_matrix() @ np.diag(h)
        cx = c[0] + np.array([-1, 1, 1, -1, -1]) * abs(ext[0]).sum(); cy = c[1] + np.array([-1, -1, 1, 1, -1]) * abs(ext[1]).sum()
        t.plot(cx, cy, color="tan", lw=1)
    t.plot(s.rail[:, 0], s.rail[:, 1], "k-", lw=2, label="wire (top view: span hidden above)")
    for c, h, _ in s.stops:
        t.add_patch(plt.Rectangle((c[0] - h[0], c[1] - h[1]), 2 * h[0], 2 * h[1], color="saddlebrown"))
    for nm, by in (("left arm base", 0.305), ("right arm base", -0.305)):
        t.plot(0.2525, by, "bs"); t.annotate(nm, (0.2525, by), textcoords="offset points", xytext=(5, 5), fontsize=8)
    outl = wand_outline(p, R)
    for x in outl[:4]:
        t.plot(x[:, 0], x[:, 1], color=col_c, lw=1.5)
    hd = R.apply([1, 0, 0])
    t.annotate("", xy=(p[0] + 0.08 * hd[0], p[1] + 0.08 * hd[1]), xytext=(p[0], p[1]), arrowprops=dict(arrowstyle="->", color=col_c, lw=2))
    t.set_title(title + "\ntop view", fontsize=10); t.set_aspect("equal"); t.set_xlim(0.2, 0.9); t.set_ylim(-0.35, 0.35)
    t.set_xlabel("x [m]"); t.set_ylabel("y [m]"); t.grid(alpha=0.3)
    sd.plot(s.rail[:, 0], s.rail[:, 2], "k-", lw=2)
    sd.axhline(s.deck_top, color="tan", lw=2, label="deck top")
    sd.axhline(TABLE_Z, color="gray", lw=1, label="table")
    for x in (outl[0], outl[1], outl[2], outl[4]):
        sd.plot(x[:, 0], x[:, 2], color=col_c, lw=1.5)
    sd.set_title("side view (x-z)", fontsize=10); sd.set_aspect("equal"); sd.set_xlim(0.2, 0.9); sd.set_ylim(0.74, 1.08)
    sd.set_xlabel("x [m]"); sd.set_ylabel("z [m]"); sd.grid(alpha=0.3)
    sd.annotate("wire span 157 mm above the deck", (0.55, s.rail[:, 2].max()), textcoords="offset points", xytext=(0, 6), fontsize=8)
ax[0, 1].annotate(f"start yaw change: {h_old:.1f} -> {NEW_YAW:.1f} deg", (new_p[0], new_p[1]), textcoords="offset points", xytext=(10, -40), fontsize=9, color="tab:green")
fig.suptitle("buzz_wire_3d very_easy: wand start pose, old vs new (YAMLab world, layout yaw 0, t = (0.5144, 0.270, 0.7517))")
plt.tight_layout()
plt.savefig(sys.argv[1] if len(sys.argv) > 1 else "start_old_vs_new.png", dpi=110)
print("saved; old handle yaw", round(h_old, 1))
