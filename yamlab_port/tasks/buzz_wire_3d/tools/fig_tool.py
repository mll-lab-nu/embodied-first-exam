"""Tool deviation figure: old vs port grip, with the YAM finger-tip contact patch (side view of the grip face)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bw_geom import LOOP_R, TUBE_R, STEM_LEN, GRIP_X0

grips = {"old grip 30.52 x 9.8 x 7 mm": (30.52, 9.8, 7.0), "port grip 45 x 9.8 x 16 mm": (45.0, 9.8, 16.0)}
fig, ax = plt.subplots(2, 2, figsize=(12, 7))
for col, (name, (L, W, H)) in enumerate(grips.items()):
    x0 = GRIP_X0 * 1000
    t, sd = ax[0, col], ax[1, col]
    a = np.linspace(0, 2 * np.pi, 200)
    for r in (LOOP_R + TUBE_R, LOOP_R - TUBE_R):
        t.plot(1000 * r * np.cos(a), 1000 * r * np.sin(a), color="darkorange")
    t.plot([LOOP_R * 1000, x0], [0, 0], color="darkorange", lw=2.5)
    t.add_patch(plt.Rectangle((x0, -W / 2), L, W, color="saddlebrown", alpha=0.7))
    t.set_title(f"{name}\ntop view (wand frame)"); t.set_aspect("equal"); t.set_xlim(-20, 85); t.set_ylim(-20, 20)
    t.plot(0, 0, "k+"); t.annotate("wire", (0, 0), textcoords="offset points", xytext=(4, 4), fontsize=8)
    sd.plot([-(LOOP_R + TUBE_R) * 1000, (LOOP_R + TUBE_R) * 1000], [0, 0], color="darkorange", lw=2.5)
    sd.plot([LOOP_R * 1000, x0], [0, 0], color="darkorange", lw=2.5)
    sd.add_patch(plt.Rectangle((x0, -H / 2), L, H, color="saddlebrown", alpha=0.7, label="grip side face"))
    sd.axhline(-H / 2, color="tan", lw=1, ls="--", label="deck (resting, ~flat)")
    # YAM tip contact patch for the top-down pinch (tips ~3-4 mm above the deck, patch 14 mm long, +-9 mm wide)
    c = 62.0 if L > 40 else 52.5
    tip = -H / 2 + 4.0
    sd.add_patch(plt.Rectangle((c - 9, tip), 18, 14, fill=False, ec="blue", lw=2, label="YAM finger-tip contact patch"))
    sd.set_title("side view: contact patch vs grip face"); sd.set_aspect("equal"); sd.set_xlim(-20, 85); sd.set_ylim(-12, 24)
    sd.legend(fontsize=7, loc="upper left")
    for a_ in (t, sd):
        a_.set_xlabel("x along the handle [mm]"); a_.grid(alpha=0.3)
fig.suptitle("buzz_wire_3d tool deviation: enlarged wooden grip (loop, stem, wire and clearances unchanged)")
plt.tight_layout(); plt.savefig("../tool_old_vs_new.png", dpi=110); print("saved")
