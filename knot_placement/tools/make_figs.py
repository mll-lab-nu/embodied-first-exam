"""Figures for the knot placement design packet: top / oblique / side views of a snapshot (task-local frame, metres).
usage: python make_figs.py   (reads ../data/*.json, writes ../figs/*.png)"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
F = os.path.join(HERE, "..", "figs")
tiers = json.load(open(os.path.join(D, "tiers_raw.json")))
snaps = json.load(open(os.path.join(D, "snapshots.json")))
plans = json.load(open(os.path.join(D, "plans.json")))
BASES = {"left": (-0.469, -0.019), "right": (0.469, -0.019)}
REACH = [(0.585, "reach (vertical pinch, <= 3 cm up)", "-"), (0.55, "reach <= 11 cm up", "--")]
COL = {"a": "tab:blue", "b": "tab:orange", "rope": "tab:blue"}


def box_corners(f):
    c = np.asarray(f["pos"][:2]); h = np.asarray(f["size"][:2]); yaw = np.deg2rad(f.get("yaw_deg", 0.))
    R = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    return c + (np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * h) @ R.T


def draw_top(ax, inst, ropes, plan, title, old_path=None):
    t = tiers[inst]
    for name, poly in (t["regions"] or {}).items():
        p = np.asarray(poly)
        ax.fill(p[:, 0], p[:, 1], color="tab:green", alpha=.12)
        ax.plot(*np.vstack([p, p[:1]]).T, color="tab:green", lw=1.2)
        ax.text(p[:, 0].min() + .005, p[:, 1].max() - .018, f"goal region {name}", color="darkgreen", fontsize=8)
    for f in t["fixtures"]:
        if f["kind"] == "box":
            q = box_corners(f)
            ax.fill(q[:, 0], q[:, 1], color="0.55" if f["role"] == "curb" else "0.25", alpha=.85)
            if f["role"] == "curb":
                ax.text(q[:, 0].mean(), q[:, 1].mean(), "curb (4.5 cm tall)", ha="center", va="center", fontsize=7, color="w")
            elif "plate" in f["name"]:
                ax.text(q[:, 0].max() + .005, q[:, 1].max(), f["name"].replace("_plate", ""), fontsize=6)
        else:
            ax.add_patch(plt.Circle(f["pos"][:2], f["radius"], color="0.2"))
            ax.text(f["pos"][0] + .015, f["pos"][1], f"{f['name']} (16 cm)" if f.get("height", 0) > .1 else f["name"], fontsize=6)
    for h, b in BASES.items():
        ax.plot(*b, "k^", ms=8)
        ax.text(b[0], b[1] - .03, f"{h} arm base", ha="center", fontsize=7)
        for r, lab, ls in REACH:
            ax.add_patch(plt.Circle(b, r, fill=False, ls=ls, color="0.5", lw=.8))
    if old_path:
        for r, pth in old_path.items():
            q = np.asarray(pth)
            ax.plot(q[:, 0], q[:, 1], ":", color="tab:red", lw=1.2, label="today's layout path (near side first)" if r == list(old_path)[0] else None)
    for r, info in (plan or {}).items():
        if "path" in info:
            q = np.asarray(info["path"])
            ax.plot(q[:, 0], q[:, 1], "--", color="tab:green", lw=1.4, label="one feasible goal shape (far side first)" if r == list(plan)[0] else None)
    for r, pts in ropes.items():
        a = np.asarray(pts)
        ax.plot(a[:, 0], a[:, 1], "-", color=COL.get(r, "tab:blue"), lw=2.2, label=f"rope {r} now")
        ax.plot(a[0, 0], a[0, 1], "ks", ms=5)
        ax.annotate(f"rope {r}\nfree end", a[-1, :2], fontsize=8, color=COL.get(r, "tab:blue"),
                    xytext=(8, -12), textcoords="offset points")
    ax.set_xlim(-.62, .62); ax.set_ylim(-.42, .42); ax.set_aspect("equal"); ax.grid(alpha=.25)
    ax.set_xlabel("x (m, task frame; +x = right arm side)"); ax.set_ylabel("y (m; -y = front)")
    ax.set_title(title, fontsize=9); ax.legend(fontsize=7, loc="lower center", ncol=2)


def draw_side(ax, inst, ropes, title):
    t = tiers[inst]
    for f in t["fixtures"]:
        if f["role"] == "curb":
            c, h = f["pos"], f["size"]
            ax.fill_between([c[1] - h[1], c[1] + h[1]], [0, 0], [c[2] + h[2]] * 2, color="0.55", alpha=.8)
            ax.text(c[1], c[2] + h[2] + .003, "curb", ha="center", fontsize=7)
        if f["role"] == "post":
            ax.fill_between([f["pos"][1] - f["radius"], f["pos"][1] + f["radius"]], [0, 0], [f["height"]] * 2, color="0.25", alpha=.5)
    for name, poly in (t["regions"] or {}).items():
        p = np.asarray(poly)
        ax.axvspan(p[:, 1].min(), p[:, 1].max(), color="tab:green", alpha=.08)
    for r, pts in ropes.items():
        a = np.asarray(pts)
        ax.plot(a[:, 1], a[:, 2] * 1000 / 1000, "-", color=COL.get(r, "tab:blue"), lw=1.5, label=f"rope {r}")
    ax.axhline(.011, color="tab:red", ls="--", lw=.8)
    ax.text(-.4, .0115, "on-table limit: centre line <= 11 mm (2 r + 3 mm)", fontsize=7, color="tab:red")
    ax.set_xlim(-.42, .42); ax.set_ylim(-.005, .1); ax.grid(alpha=.25)
    ax.set_xlabel("y (m)"); ax.set_ylabel("z above table (m)"); ax.set_title(title, fontsize=9); ax.legend(fontsize=7)


def draw_oblique(ax, inst, ropes, plan, title, z_scale=3.):
    t = tiers[inst]
    for name, poly in (t["regions"] or {}).items():
        p = np.asarray(poly); verts = [[(x, y, 0) for x, y in p]]
        ax.add_collection3d(Poly3DCollection(verts, color="tab:green", alpha=.15))
    for f in t["fixtures"]:
        if f["kind"] == "box":
            q = box_corners(f); top = (f["pos"][2] + f["size"][2]) * z_scale
            for i in range(4):
                a_, b_ = q[i], q[(i + 1) % 4]
                ax.add_collection3d(Poly3DCollection([[(a_[0], a_[1], 0), (b_[0], b_[1], 0), (b_[0], b_[1], top), (a_[0], a_[1], top)]],
                                                     color="0.55" if f["role"] == "curb" else "0.3", alpha=.6))
            ax.add_collection3d(Poly3DCollection([[(x, y, top) for x, y in q]], color="0.55", alpha=.6))
        else:
            th = np.linspace(0, 2 * np.pi, 20); x = f["pos"][0] + f["radius"] * np.cos(th); y = f["pos"][1] + f["radius"] * np.sin(th)
            for z in (0, f["height"] * z_scale):
                ax.plot(x, y, z, color="0.2", lw=.8)
            ax.plot([f["pos"][0]] * 2, [f["pos"][1]] * 2, [0, f["height"] * z_scale], color="0.2", lw=2)
    for r, pts in ropes.items():
        a = np.asarray(pts)
        ax.plot(a[:, 0], a[:, 1], a[:, 2] * z_scale, color=COL.get(r, "tab:blue"), lw=2)
        ax.text(a[-1, 0], a[-1, 1], a[-1, 2] * z_scale + .01, f"{r}", color=COL.get(r, "tab:blue"))
    for r, info in (plan or {}).items():
        if "path" in info:
            q = np.asarray(info["path"]); ax.plot(q[:, 0], q[:, 1], 0 * q[:, 0], "--", color="tab:green", lw=1)
    for h, b in BASES.items():
        ax.scatter([b[0]], [b[1]], [0], marker="^", color="k")
    ax.set_xlim(-.55, .55); ax.set_ylim(-.42, .42); ax.set_zlim(0, .5)
    ax.view_init(elev=35, azim=-60); ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel(f"z x{z_scale:g}")
    ax.set_title(title, fontsize=9)


for name, sn in snaps.items():
    inst = sn["instance"]
    old = sn.get("old_layout_path")
    fig, ax = plt.subplots(figsize=(11, 8))
    draw_top(ax, inst, sn["ropes"], plans.get(name), f"{name} (top view): {sn['source']}", old_path=old)
    fig.savefig(os.path.join(F, f"{name}_top.png"), dpi=110, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4))
    draw_side(ax, inst, sn["ropes"], f"{name} (side view, looking along -x): rope heights vs the curb")
    fig.savefig(os.path.join(F, f"{name}_side.png"), dpi=110, bbox_inches="tight"); plt.close(fig)
    fig = plt.figure(figsize=(10, 8)); ax = fig.add_subplot(111, projection="3d")
    draw_oblique(ax, inst, sn["ropes"], plans.get(name), f"{name} (oblique, heights x3)")
    fig.savefig(os.path.join(F, f"{name}_oblique.png"), dpi=110, bbox_inches="tight"); plt.close(fig)
    print("wrote", name)
