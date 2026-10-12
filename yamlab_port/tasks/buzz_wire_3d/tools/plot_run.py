"""Stand-in evidence plot of a logged run: loop-centre path vs the rail (side/top views) and key signals."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bw_geom import Scene, Layout, TABLE_Z

states, out = sys.argv[1], sys.argv[2]
tier = sys.argv[3] if len(sys.argv) > 3 else "very_easy"
d = np.load(states)
s = Scene(tier, Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
W = d["wand_T"].reshape(-1, 3, 4)
p = W[:, :, 3]
num = dict(zip([str(k) for k in d["diag_num_keys"]], d["diag_num"].T))
flag = dict(zip([str(k) for k in d["diag_flag_keys"]], d["diag_flag"].T))
t = np.arange(len(p)) / 30.0
fig, ax = plt.subplots(2, 2, figsize=(12, 8))
ax[0, 0].plot(s.rail[:, 1], s.rail[:, 2], "k-", lw=2, label="wire")
ax[0, 0].plot(p[:, 1], p[:, 2], "r-", lw=1, label="loop centre")
ax[0, 0].axhline(s.deck_top, color="tan", label="deck top")
ax[0, 0].set_xlabel("y [m]"); ax[0, 0].set_ylabel("z [m]"); ax[0, 0].invert_xaxis(); ax[0, 0].legend(); ax[0, 0].set_title("front view")
ax[0, 1].plot(s.rail[:, 1], s.rail[:, 0], "k-", lw=2)
ax[0, 1].plot(p[:, 1], p[:, 0], "r-", lw=1)
ax[0, 1].set_xlabel("y [m]"); ax[0, 1].set_ylabel("x [m]"); ax[0, 1].invert_xaxis(); ax[0, 1].set_title("top view")
ax[1, 0].plot(t, 1000 * np.minimum(num["min_gap_m"], 0.05), label="min metal-wire gap so far [mm]")
ax[1, 0].plot(t, 1000 * num["route_cursor_m"] / 10, label="route cursor [cm]")
ax[1, 0].plot(t, 1000 * np.minimum(num["distance_to_finish_m"], 0.05), label="distance to finish [mm] (clip 50)")
ax[1, 0].legend(); ax[1, 0].set_xlabel("t [s]")
for i, k in enumerate(["touched", "traversal_complete", "supported", "released", "quiet", "ok_now", "success"]):
    ax[1, 1].plot(t, flag[k] * 0.8 + i, label=k)
ax[1, 1].set_yticks(range(7)); ax[1, 1].set_yticklabels(["touched", "complete", "supported", "released", "quiet", "ok", "success"])
ax[1, 1].set_xlabel("t [s]")
plt.tight_layout()
plt.savefig(out, dpi=90)
print("saved", out)
