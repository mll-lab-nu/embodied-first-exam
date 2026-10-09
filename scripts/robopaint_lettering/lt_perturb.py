#!/usr/bin/env python3
"""Robot-free rule study of a lettering pair: does the unchanged scorer (rcb_brush_score.score_ink with the pair's own success rule)
fail the cheap ways of writing the exemplar? Each variant of the reference plan (solution/plans.json: one writing route per contact,
the tines' spread per point, the pen's spread axis) is drawn with the pen's ideal mark (rcb_brush_score.pointed_sweep_mask: the pen
exactly on its path, no robot) and scored like a sheet, one realized stroke per drawn route.

    python lt_perturb.py --task tasks/robopaint-lettering-<slug>-i00-privileged [--out <slug>_perturb.json]
"""
from __future__ import annotations
import argparse, json, math, os, sys

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True); ap.add_argument("--out")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.task, "tests"))
    import rcb_brush as RB
    import rcb_brush_score as RS
    inst = json.load(open(os.path.join(a.task, "tests", "instance.json")))
    plans = json.load(open(os.path.join(a.task, "solution", "plans.json")))
    cfg = inst["target"]["success"]
    sheet = RB.sheets_from_inst(inst)["main"]
    tgt = RS.load_truth(inst, sheet, os.path.join(a.task, "tests"), None)
    b = inst["brush"]; h = float(b["hairline_m"]); wmax = float(b["max_width_m"])
    axis0 = float(plans["axis_deg"])
    routes = [(np.asarray(r["points_mm"], np.float64), np.asarray(r["widths_mm"], np.float64) / 1000.0) for r in plans["routes"]]

    def draw(rts, axis_deg=axis0):
        """rts: [(points_mm (N, 2), spread_m (N,))] -> (ink, strokes) as the painter would leave them with the pen on its path."""
        ink = np.zeros((sheet.rows, sheet.cols), np.float32); strokes = []
        for P, W in rts:
            x, y = sheet.mm_to_world(P[:, 0], P[:, 1])
            cov = RS.pointed_sweep_mask(sheet, np.stack([x, y], 1), np.clip(W, h, wmax), math.radians(axis_deg), h)
            np.maximum(ink, cov, out=ink)
            rr, cc = np.nonzero(cov > 0)
            if len(rr) == 0:
                continue
            r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
            strokes.append({"sheet": "main", "inked": True, "mask_bbox": (int(r0), int(c0)), "mask": np.round(cov[r0:r1, c0:c1] * 255).astype(np.uint8)})
        return ink, strokes

    def score(name, rts, axis_deg=axis0, note="", quiet=False):
        ink, strokes = draw(rts, axis_deg)
        m = RS.score_ink(ink, tgt, strokes, cfg=cfg)
        ok = RS.is_success(m, cfg)
        fails = [k for k, bad in (("IoU", m["iou"] < cfg["iou"]), ("BF", m["boundary_f"] < cfg["boundary_f"]),
                                  ("region", m["min_stroke_coverage"] < cfg["min_stroke_coverage"]), ("stray", m["stray_frac"] > cfg["max_stray_frac"]),
                                  ("cap", m["stroke_count_ok"] < 1)) if bad]
        rec = {"variant": name, "success": bool(ok), "iou": round(m["iou"], 3), "boundary_f": round(m["boundary_f"], 3),
               "min_region": round(m["min_stroke_coverage"], 3), "stray": round(m["stray_frac"], 4), "strokes": int(m["n_strokes"]),
               "cap": int(m["max_strokes"]), "fails": fails, "note": note}
        if not quiet:
            print(json.dumps(rec, ensure_ascii=False), flush=True)
        return rec

    def split(P, W, every_mm):
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
        n = max(1, int(math.ceil(d[-1] / every_mm)))
        cuts = np.linspace(0, d[-1], n + 1)
        out = []
        for a_, b_ in zip(cuts[:-1], cuts[1:]):
            m = (d >= a_ - 1e-9) & (d <= b_ + 1e-9)
            if m.sum() >= 1:
                out.append((P[m], W[m]))
        return out

    allw = np.concatenate([W for _, W in routes])
    mean_w = float(np.mean(allw))
    out = [score("reference plan, the pen exactly on its path", routes)]
    out.append(score("constant press per contact (its mean spread)", [(P, np.full(len(W), float(np.mean(W)))) for P, W in routes]))
    out.append(score("one constant press for the whole exemplar (mean spread)", [(P, np.full(len(W), mean_w)) for P, W in routes]))
    out.append(score("hairline only (no shades)", [(P, np.full(len(W), h)) for P, W in routes]))
    out.append(score("full press everywhere", [(P, np.full(len(W), wmax)) for P, W in routes]))
    for f in (0.8, 1.2):
        out.append(score(f"press x{f} (spread {f} x above the hairline)", [(P, h + (W - h) * f) for P, W in routes]))
    for dmm in (0.5, 1.0):
        out.append(score(f"contacts shifted alternately +-{dmm} mm (x)", [(P + np.array([dmm if k % 2 == 0 else -dmm, 0.0]), W) for k, (P, W) in enumerate(routes)]))
    for dang in (30.0, 90.0):
        out.append(score(f"pen axis turned {dang:g} deg", routes, axis_deg=axis0 + dang))
    long_i = int(np.argmax([np.sum(np.hypot(*np.diff(P, axis=0).T)) if len(P) > 1 else 0 for P, _ in routes]))
    P, W = routes[long_i]
    half = len(P) // 2
    out.append(score("one lift in the middle of the longest contact", routes[:long_i] + [(P[:half], W[:half]), (P[half:], W[half:])] + routes[long_i + 1:]))
    out.append(score("a lift every 30 mm (one stroke per region length)", [q for P, W in routes for q in split(P, W, 30.0)]))
    best = None
    for k in range(len(routes)):                                   # skip the contact whose absence costs the least IoU
        rec_ink, rec_st = draw(routes[:k] + routes[k + 1:])
        m = RS.score_ink(rec_ink, tgt, rec_st, cfg=cfg)
        if best is None or m["iou"] > best[0]:
            best = (m["iou"], k)
    out.append(score(f"skip one contact (the cheapest: contact {best[1] + 1})", routes[:best[1]] + routes[best[1] + 1:]))
    # the naive plan: every region written on its own along its path, its own spread profile (one stroke per region)
    regions = [(np.asarray(s_["points_mm"], np.float64), np.asarray(s_["widths_mm"], np.float64) / 1000.0) for s_ in inst["truth"]["strokes"]]
    out.append(score("naive: every region its own stroke (its own path and spread)", regions))
    out.append(score("naive within the cap: each contact at its mean press, axis 0 deg", [(P, np.full(len(W), float(np.mean(W)))) for P, W in routes], axis_deg=0.0))
    # colouring in with the pen's hairline: the routes at a light touch, every shaded part filled with parallel hairline passes
    # (0.3 mm apart, across its width) inside the same contact; the process rule's numbers for it (path and mark width)
    fills, extra = [], 0.0
    for P, W in routes:
        fills.append((P, np.full(len(W), h)))
        if len(P) < 3:
            continue
        T = np.gradient(P, axis=0); T /= np.maximum(np.hypot(*T.T), 1e-12)[:, None]
        Nrm = np.stack([-T[:, 1], T[:, 0]], 1)
        vis = h + (W - h) * np.abs(np.sin(np.arctan2(-T[:, 1], T[:, 0]) - math.radians(axis0)))   # the mark's width there (mm... in m)
        for off in np.arange(0.3, 1.0, 0.3) / 1000.0:
            for sgn in (1, -1):
                m = vis / 2 - h / 2 >= off - 1e-9
                if m.sum() < 2:
                    continue
                idx = np.nonzero(m)[0]
                runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
                for r in runs:
                    if len(r) < 2:
                        continue
                    Q = P[r] + sgn * off * 1000.0 * Nrm[r]
                    fills.append((Q, np.full(len(r), h)))
                    extra += float(np.sum(np.hypot(*np.diff(Q, axis=0).T)))
    rec = score("colouring in: hairline press, the shades filled with parallel passes", fills,
                note="contacts counted as the routes'; the fill passes joined inside each contact", quiet=True)
    ref_path = sum(float(np.sum(np.hypot(*np.diff(P, axis=0).T))) for P, _ in routes if len(P) > 1)
    rec["strokes"] = len(routes); rec["fails"] = [f for f in rec["fails"] if f != "cap"]
    rec["success"] = not rec["fails"]
    rec["path_mm_vs_reference"] = round((ref_path + extra) / ref_path, 2)
    rec["note"] += f"; path {ref_path + extra:.0f} mm = {rec['path_mm_vs_reference']} x the routes' {ref_path:.0f} mm (rule limit: 3 x the reference's); mark width ~ the hairline 0.4 mm"
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    out.append(rec)
    if a.out:
        json.dump({"task": os.path.basename(a.task.rstrip("/")), "rule": cfg, "variants": out}, open(a.out, "w"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
