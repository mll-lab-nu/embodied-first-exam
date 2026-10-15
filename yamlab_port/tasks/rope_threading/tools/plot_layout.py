"""Top view of the medium re-layout for review: (a) the old scene under the easy transform, (b) the chosen layout
(ring assembly and rope start placed rigidly each, threading_geom.RELAYOUT["medium"]) with the arm per stroke.
Viewed from behind the robot: +y (left arm) on the left, +x (away from the robot) up. draw_state() adds a run
state (rope, both arms, TCPs) in the same view: the one drawing used for every medium figure.
Usage: python plot_layout.py --out medium_layout.png [--chain RL,RL,L --feed_tip start]  (chain in feeding order)
"""
import argparse, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import medium_layout_search as M
import plan_np as PN
import yam_kin as K

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(M.SRC))))     # rope_threading_lib (numpy only)
import threading_geom as TH

for f_ in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"):
    if os.path.exists(f_):
        matplotlib.font_manager.fontManager.addfont(f_)
plt.rcParams.update({"font.family": ["Noto Sans CJK JP", "DejaVu Sans"], "font.size": 20})
ARM = {"L": "左臂", "R": "右臂"}


def uv(p):
    p = np.atleast_2d(p)
    return -p[:, 1], p[:, 0]


def rot(yaw):
    a = np.radians(yaw)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def draw(ax, rings, rope, title, chain=None, feed_tip="end", end_labels=True):
    ax.add_patch(plt.Rectangle((-PN.TABLE_Y, PN.TABLE_X[0]), 2 * PN.TABLE_Y, PN.TABLE_X[1] - PN.TABLE_X[0],
                               fc="#f3efe6", ec="#6b5d45", lw=2.5, zorder=0))
    ax.add_patch(plt.Rectangle((-0.75, 0.05), 1.5, 0.2475, fc="#d9d9d9", ec="#888", hatch="//", zorder=0))
    ax.text(-0.72, 0.09, "机器人底座区", ha="left", va="center", color="#444")
    for s, lab in (("left", "左臂基座"), ("right", "右臂基座")):
        b = K.BASES[s]
        ax.plot(*uv(b), "s", ms=22, color="#555", zorder=3)
        ax.text(*[c[0] for c in uv(b + [-0.045, 0, 0])], lab, ha="center", va="top")
    for k, r in enumerate(rings):
        u, v = TH.ring_basis(r["normal"])
        th = np.linspace(0, 2 * np.pi, 97)
        circ = r["center"] + 0.075 * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
        on_table = PN.TABLE_X[0] <= r["base_center"][0] <= PN.TABLE_X[1] and abs(r["base_center"][1]) <= PN.TABLE_Y
        col = "#1f5fa8" if on_table else "#c0392b"
        ax.plot(*uv(circ), color=col, lw=4, zorder=4)
        Rz = rot(r.get("yaw", 0.0))
        corners = np.array([[0.025, 0.04], [-0.025, 0.04], [-0.025, -0.04], [0.025, -0.04], [0.025, 0.04]]) @ Rz.T
        ax.plot(*uv(np.c_[corners + r["base_center"][:2], np.zeros(5)]), color=col, lw=2.5, zorder=4)
        ax.plot(*uv(r["stand_center"]), "o", color=col, ms=8, zorder=5)
        d = r["sign"] * r["normal"] * (-1 if feed_tip == "start" else 1)     # the fed tip's travel
        a0, a1 = uv(r["center"]), uv(r["center"] + 0.13 * d)
        ax.annotate("", xy=(a1[0][0], a1[1][0]), xytext=(a0[0][0], a0[1][0]),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=3, mutation_scale=28), zorder=6)
        txt = f"{r['name']}{'+' if r['sign'] > 0 else '−'}  (h {r['center'][2] - TH.TABLE_SUPPORT_Z:.2f} m)"
        if chain is not None:
            order = k if feed_tip == "end" else len(rings) - 1 - k
            f, *rcv = chain[order]
            txt += f"\n第 {order + 1} 个穿"
            txt += f"\n{ARM[f]}喂入" + (f" → {ARM[rcv[0]]}接收" if rcv else "（最后一环）")
        (ru,), (rv,) = uv(r["center"])
        slot = sorted(uv(q["center"])[0][0] for q in rings).index(ru)       # labels in one row above the table
        ax.annotate(txt, xy=(ru, rv), xytext=(-0.45 + 0.45 * slot, 1.0), color=col, fontsize=19,
                    ha="center", va="center", zorder=7, bbox=dict(fc="white", ec=col, alpha=0.9),
                    arrowprops=dict(arrowstyle="-", color=col, lw=1.5, ls="--"))
    ax.plot(*uv(rope), color="#2e7d32", lw=5, zorder=2)
    for i_, col_ in ((0, "#2e7d32"), (-1, "#e67e22")):
        fed_ = (i_ == 0) == (feed_tip == "start")
        ax.plot(*uv(rope[i_]), "*" if fed_ else "o", color=col_, ms=28 if fed_ else 14, zorder=3)
    fed = "（被喂入）"
    if end_labels:
        ax.text(*[c[0] + o for c, o in zip(uv(rope[0]), (0.02, -0.05))], "材料起点" + (fed if feed_tip == "start" else ""),
                color="#2e7d32", ha="left", va="top")
        ax.text(*[c[0] + o for c, o in zip(uv(rope[-1]), (-0.02, -0.05))], "材料终点" + (fed if feed_tip == "end" else ""),
                color="#e67e22", ha="right", va="top")
    ax.text(0.73, 0.06, "环：俯视投影；方框：支架底座；箭头：被喂绳头的穿过方向", ha="right", va="bottom", fontsize=17, color="#333")
    ax.set_xlim(-0.75, 0.75); ax.set_ylim(0.05, 1.12); ax.set_aspect("equal")
    ax.set_xlabel("← +y（左）     世界坐标 y (m)     −y（右）→"); ax.set_ylabel("x (m)，远离机器人 ↑")
    ax.set_xticks(np.arange(-0.6, 0.61, 0.2)); ax.set_xticklabels([f"{-t:.1f}" for t in np.arange(-0.6, 0.61, 0.2)])
    ax.set_title(title, fontsize=24, pad=14)


HAND = {"left": ("#7d3c98", "左手"), "right": ("#b9770e", "右手")}


def draw_state(ax, rings, q, rope, title, chain=None, feed_tip="start", end_labels=True):
    """A run state (q: the 14 logged joints, rope: centreline in material order) in the same top view: the scene,
    the rope, both arms (capsule model, translucent) and each TCP (dot). Returns the TCP poses {side: T}."""
    draw(ax, rings, rope, title, chain=chain, feed_tip=feed_tip, end_labels=end_labels)
    tcp = {}
    for s, sl, gi in (("left", slice(0, 6), 6), ("right", slice(7, 13), 13)):
        col = HAND[s][0]
        A, B, _ = PN.arm_capsules(s, q[sl], grip_open=q[gi] < -0.02)
        for a, b in zip(A, B):
            ax.plot(*uv(np.array([a, b])), color=col, lw=16, alpha=0.35, solid_capstyle="round", zorder=5)
        tcp[s] = K.base_to_world(K.fk_tcp(q[sl]), s)
        ax.plot(*uv(tcp[s][:3, 3]), "o", ms=16, color=col, mec="white", mew=2, zorder=8)
    return tcp


def scene(yaw, t, rope_yaw, rope_t):
    rings, _ = M.place(yaw, t)
    for r in rings:
        r["yaw"] = yaw
    rope = M.ROPE.copy()
    rope[:, :2] = M.ROPE[:, :2] @ rot(rope_yaw).T + np.asarray(rope_t)
    rope[:, 2] += M.TABLE
    return rings, rope


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="medium_layout.png")
    ap.add_argument("--chain", default="RL,RL,L", help="per ring in feeding order: feeding arm [+ receiving arm]")
    ap.add_argument("--feed_tip", default="start", choices=["end", "start"])
    a = ap.parse_args()
    cfg = TH.RELAYOUT["medium"]
    easy = TH.RELAYOUT["easy"]
    fig, axs = plt.subplots(1, 2, figsize=(26, 13.5), dpi=100)
    draw(axs[0], *scene(easy["yaw_deg"], easy["t_xy"], easy["yaw_deg"], easy["t_xy"]),
         f"(a) 原 medium 场景整体按 easy 变换（yaw {easy['yaw_deg']:.0f}°）：R3 落在底座区（红）")
    draw(axs[1], *scene(cfg["yaw_deg"], cfg["t_xy"], cfg["rope_yaw_deg"], cfg["rope_t_xy"]),
         f"(b) 新布局：环组 yaw {cfg['yaw_deg']:.0f}°, t={tuple(cfg['t_xy'])}；绳起点 yaw {cfg['rope_yaw_deg']:.0f}°, "
         f"t={tuple(cfg['rope_t_xy'])}", chain=[list(c) for c in a.chain.split(",")], feed_tip=a.feed_tip)
    fig.tight_layout()
    fig.savefig(a.out)
    print("saved", a.out, json.dumps(cfg))
