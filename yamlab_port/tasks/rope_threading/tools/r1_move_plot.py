"""Top view for r1_move_eval: per group the best candidate (old position grey, new coloured), R2 exit receive points, arm bases (plot_layout.draw)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plot_layout as P
import r1_move_eval as R
import r1_move_summary as S

OFFC = "#8a8a8a"


def ring_outline(r):
    import threading_geom as TH
    u, v = TH.ring_basis(r["normal"]); th = np.linspace(0, 2 * np.pi, 97)
    return r["center"] + 0.075 * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)


def scene(spec):
    R.SPEC = {}
    old, rope = R.place_patched(R.YAW, R.T0)
    for r in old:
        r["yaw"] = R.YAW
    R.SPEC = spec
    new, _ = R.place_patched(R.YAW, R.T0)
    R.SPEC = {}
    rope = M_rope()
    return old, new, rope


def M_rope():
    rope = R.M.ROPE.copy()
    rope[:, :2] = R.M.ROPE[:, :2] @ P.rot(R.ROPE_YAW).T + np.asarray(R.ROPE_T)
    rope[:, 2] += R.M.TABLE
    return rope


def draw_group(ax, spec, title, note):
    old, new, rope = scene(spec)
    P.draw(ax, new, rope, title, feed_tip="start")
    for r0, r1 in zip(old, new):
        moved = np.linalg.norm(r0["center"] - r1["center"]) > 1e-6 or abs(r0["normal"] @ r1["normal"] - 1) > 1e-9
        if not moved:
            continue
        ax.plot(*P.uv(ring_outline(r0)), color=OFFC, lw=4, ls="--", zorder=3)
        Rz = P.rot(r0["yaw"])
        c = np.array([[0.025, 0.04], [-0.025, 0.04], [-0.025, -0.04], [0.025, -0.04], [0.025, 0.04]]) @ Rz.T
        ax.plot(*P.uv(np.c_[c + r0["base_center"][:2], np.zeros(5)]), color=OFFC, lw=2.5, ls="--", zorder=3)
        ax.plot(*P.uv(r0["stand_center"]), "o", color=OFFC, ms=8, zorder=3)
        a, b = P.uv(r0["center"]), P.uv(r1["center"])
        ax.annotate("", xy=(b[0][0], b[1][0]), xytext=(a[0][0], a[1][0]), arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=3.5, mutation_scale=30), zorder=9)
        ax.text(a[0][0], a[1][0] - 0.065, r0["name"] + " 原位", color=OFFC, ha="center", va="top", fontsize=22, zorder=9)
    # R2 exit receive points (0.05 / 0.07 / 0.10 m behind R2's face, new position solid, old position grey)
    for rs, col, mk in ((old, OFFC, "x"), (new, "#d35400", "X")):
        r2 = next(r for r in rs if r["name"] == "R2"); d = -r2["sign"] * r2["normal"]
        pts = np.array([r2["center"] + t * d for t in (0.05, 0.07, 0.10)])
        ax.plot(*P.uv(pts), "-", color=col, lw=2, zorder=8)
        ax.plot(*P.uv(pts), mk, color=col, ms=14, mew=3, zorder=8)
    r2 = next(r for r in new if r["name"] == "R2"); d = -r2["sign"] * r2["normal"]
    q = P.uv(r2["center"] + 0.10 * d)
    ax.text(q[0][0] - 0.03, q[1][0] + 0.03, "R2 出口接收点\n(面后 5/7/10 cm)", color="#d35400", fontsize=22, ha="right", va="bottom", zorder=9,
            bbox=dict(fc="white", ec="#d35400", alpha=0.9))
    ax.text(0.0, -0.11, note, transform=ax.transAxes, fontsize=22, ha="left", va="top", zorder=9)
    for t in list(ax.texts):
        if t.get_text().startswith(("机器人底座区", "环：俯视", "材料")):
            t.remove()
    for t in ax.texts:
        if t.get_fontsize() < 21:
            t.set_fontsize(21)
    ax.set_xlim(-0.6, 0.5); ax.set_ylim(0.05, 1.1)
    return new
