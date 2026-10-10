#!/usr/bin/env python3
"""Difficulty axes of the RoboPaint calligraphy pairs (kaishu, xingshu, caoshu), measured on the committed frozen files:
  - from the instance: characters, the stroke cap (= contacts), regions;
  - from the reference plans (solution/plans.json, robot-free handle paths): length per contact, total turning per contact,
    sharp turns (> 90 deg within 6 mm of path), the press range inside a contact;
  - from the picture (tests/target.png): the exemplar's stroke width along its centre (2 x the distance to the ink edge on the
    skeleton): p10 / p50 / p90, the share of centre length thinner than 2.5 mm (hairlines), total centre length.
    python cs_metrics.py <dir with robopaint-*-privileged/{tests,solution}> <tool dir> > metrics.json
"""
import json, math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import skeletonize

root, tool = sys.argv[1], sys.argv[2]
sys.path.insert(0, tool)
import opt_calli as O  # noqa: E402

PX_MM = 227.1845 / 1024
PAPER = np.array([0.972, 0.957, 0.925]); INK = np.array([0.075, 0.072, 0.080])


def plan_stats(P):
    P = np.asarray(P, np.float64)
    xy = O.catmull_rom(P[:, :2], 24)
    seg = np.hypot(*np.diff(xy, axis=0).T)
    L = float(seg.sum()) * 1000
    keep = seg > 1e-7
    d = np.diff(xy, axis=0)[keep]
    ang = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    turn = np.abs(np.diff(ang))
    total_turn = float(np.degrees(turn.sum()))
    s = np.cumsum(seg[keep])[:-1] * 1000 if len(seg[keep]) > 1 else np.zeros(0)
    sharp = 0
    if len(turn):
        th = np.r_[0, np.cumsum(turn)]
        j = 0
        for i in range(len(s)):                                   # turn > 90 deg accumulated within 6 mm of path
            while s[i] - s[j] > 6.0:
                j += 1
            if th[i + 1] - th[j] > math.pi / 2:
                sharp += 1
                j = i + 1
    z = P[:, 2] * 1000
    return {"len_mm": L, "turn_deg": total_turn, "sharp": sharp, "z_min_mm": float(z[1:].min()) if len(z) > 1 else float(z.min()),
            "z_max_mm": float(z.max())}


def width_stats(png):
    img = np.asarray(Image.open(png).convert("RGB"), np.float64) / 255.0
    cov = np.clip(((PAPER - img) * (PAPER - INK)).sum(-1) / ((PAPER - INK) ** 2).sum(), 0, 1)
    ink = cov >= 0.5
    sk = skeletonize(ink)
    dist = ndimage.distance_transform_edt(ink)
    w = 2 * dist[sk] * PX_MM
    return {"centre_len_mm": float(sk.sum() * PX_MM), "w_p10": float(np.percentile(w, 10)), "w_p50": float(np.percentile(w, 50)),
            "w_p90": float(np.percentile(w, 90)), "hair_share": float((w < 2.5).mean()), "ink_mm2": float(ink.sum() * PX_MM ** 2)}


rows = []
for t in sorted(os.listdir(root)):
    if not t.endswith("-privileged"):
        continue
    fam, slug = t.split("-")[1], "-".join(t.split("-")[2:-2])
    inst = json.load(open(os.path.join(root, t, "tests", "instance.json"), encoding="utf-8"))
    tr = inst["truth"]
    chars = tr.get("characters") or tr["character"]
    plans = json.load(open(os.path.join(root, t, "solution", "plans.json"), encoding="utf-8"))["plans"]
    ps = [plan_stats(P) for P in plans]
    ws = width_stats(os.path.join(root, t, "tests", "target.png"))
    r = {"family": fam, "slug": slug, "chars": chars, "n_chars": len(chars), "cap": int(inst["target"]["success"]["max_strokes"]),
         "regions": int(tr["n_strokes"]), "contacts_per_char": inst["target"]["success"]["max_strokes"] / len(chars),
         "path_mm": sum(p["len_mm"] for p in ps), "longest_mm": max(p["len_mm"] for p in ps),
         "mean_contact_mm": float(np.mean([p["len_mm"] for p in ps])),
         "turn_per_contact_deg": float(np.mean([p["turn_deg"] for p in ps])), "max_turn_deg": max(p["turn_deg"] for p in ps),
         "sharp_turns": sum(p["sharp"] for p in ps), "sharp_per_char": sum(p["sharp"] for p in ps) / len(chars),
         "press_range_mm": float(np.median([p["z_max_mm"] - p["z_min_mm"] for p in ps])), **ws}
    r["width_ratio_p90_p10"] = r["w_p90"] / max(1e-6, r["w_p10"])
    rows.append(r)
print(json.dumps(rows, ensure_ascii=False, indent=0))
