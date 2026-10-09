#!/usr/bin/env python3
"""Robot-free comparison of region / contact rules on one exemplar ink: the reference plans (solution/plans.json, written for the
caoshu trails) and a set of cheats, scored against an instance built from a given exemplar variant (its regions) and a cap (its
own contacts, or --cap). One JSON line per case.
    python cs_rulecmp.py --exemplar <dir with <slug>.graphics.txt + <slug>.contacts.json> --plans <plans.json> [--cap N]
Cheats: one press per contact, one press for everything, a lift at every region (the reference path cut wherever its control
points pass into another region), a lift in the middle of every contact, contacts offset +-0.5 / +-1.0 mm alternately, the
naive plan (each region's centre path, press from the local width, one contact per region), a skipped contact (the best one).
Needs RCB_TOOLS (rcb_brush.py, rcb_brush_score.py, opt_calli.py)."""
import argparse, json, os, sys
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cs_plan as C  # noqa: E402
B, G, O = C.B, C.G, C.O


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exemplar", required=True); ap.add_argument("--plans", required=True); ap.add_argument("--cap", type=int)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    ex = os.path.abspath(a.exemplar); slug = os.path.basename(ex.rstrip("/"))
    spec, cj = C.spec_for(ex, slug)
    cap = a.cap or len(cj["contacts"])
    spec["target"]["success"]["max_strokes"] = cap
    inst = G.build_instance(spec)
    recs = {}
    for line in open(spec["target"]["graphics"], encoding="utf-8"):
        d = json.loads(line); recs[d["character"]] = d
    medians = [m for c in cj["chars"] for m in recs[c]["medians"]]
    wf = O.World(inst)
    tgt = wf.target
    sheet = tgt.sheet
    plans = [np.asarray(P, np.float64) for P in json.load(open(a.plans))["plans"]]
    # region label raster (0 = paper): each ink pixel -> its region; paper -> the nearest region (for points off the ink)
    lab = np.zeros(tgt.mask.shape, np.int32)
    for k, m in enumerate(tgt.stroke_masks):
        lab[m & (lab == 0)] = k + 1
    _, (ir, ic) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
    lab_near = lab[ir, ic]

    def region_of(xy):
        u, v = sheet.world_to_px(np.array([xy[0]]), np.array([xy[1]]))
        return int(lab_near[int(np.clip(round(float(v[0])), 0, sheet.rows - 1)), int(np.clip(round(float(u[0])), 0, sheet.cols - 1))])

    def run(name, plist):
        pt = C.write(inst, C.paths_of(plist))
        m = C.score(inst, pt, tgt)
        r = {"rule": a.label, "slug": slug, "case": name, "regions": len(tgt.stroke_masks), "cap": cap, **C.short(m)}
        print(json.dumps(r), flush=True)
        return r

    run("ref", plans)
    for mm in (0.5, 1.0):
        run(f"offset_{mm}", [P + np.array([(mm if i % 2 == 0 else -mm) / 1000, 0, 0]) for i, P in enumerate(plans)])
    for f in (0.8, 1.2):
        run(f"press_{f}", [P * np.array([1, 1, f]) for P in plans])
    run("const_contact", [np.c_[P[:, :2], np.r_[P[0, 2], np.full(len(P) - 1, np.median(P[1:, 2]))]] for P in plans])
    zg = float(np.median(np.concatenate([P[1:, 2] for P in plans])))
    run("const_global", [np.c_[P[:, :2], np.r_[min(P[0, 2], zg), np.full(len(P) - 1, zg)]] for P in plans])
    out = []
    for P in plans:                                       # a lift wherever the control points pass into another region
        labs = [region_of(p[:2]) for p in P]
        cut = [0] + [i for i in range(1, len(P)) if labs[i] != labs[i - 1]] + [len(P)]
        cut = sorted(set(cut))
        segs = [P[max(0, cut[j] - 1):cut[j + 1] + 0] for j in range(len(cut) - 1)]
        segs = [S for S in segs if len(S) >= 2] or [P]
        out += segs
    run("lift_every_region", out)
    out = []
    for P in plans:
        h = len(P) // 2
        out += [P[:h + 1], P[h:]] if len(P) >= 4 else [P]
    run("lift_mid_contact", out)
    best = None
    for k in range(len(plans)):
        pt = C.write(inst, C.paths_of([P for j, P in enumerate(plans) if j != k]))
        m = C.score(inst, pt, tgt)
        if best is None or m["iou"] > best[1]["iou"]:
            best = (k, m)
    print(json.dumps({"rule": a.label, "slug": slug, "case": f"skip_contact_{best[0] + 1}", "regions": len(tgt.stroke_masks), "cap": cap,
                      **C.short(best[1])}), flush=True)
    boxes = G.glyph_boxes(inst["truth"])
    wa, wb = inst["brush"]["width_cm"]; zmax = inst["brush"]["z_max_cm"]
    paths = []
    for k, med in enumerate(medians):
        X, Y = G.units_to_mm(boxes[k], np.asarray(med, np.float64))
        x, y = sheet.mm_to_world(X, Y)
        P = O.resample(np.stack([x, y], 1), 0.0002)
        dist = ndimage.distance_transform_edt(tgt.stroke_masks[k]) * sheet.px_m
        u, v = sheet.world_to_px(P[:, 0], P[:, 1])
        ui = np.clip(np.rint(u).astype(int), 0, sheet.cols - 1); vi = np.clip(np.rint(v).astype(int), 0, sheet.rows - 1)
        zp = np.array([float(np.clip((2 * dd * 100 - wb) / wa, 0.0, zmax) / 100) for dd in dist[vi, ui]])
        zt = B.PAPER_Z - zp; above = B.PAPER_Z + 0.01
        paths.append(np.concatenate([np.c_[np.repeat(P[:1], 21, 0), np.linspace(above, zt[0], 21)], np.c_[P, zt],
                                     np.c_[np.repeat(P[-1:], 21, 0), np.linspace(zt[-1], above, 21)]]))
    pt = C.write(inst, paths)
    m = C.score(inst, pt, tgt)
    print(json.dumps({"rule": a.label, "slug": slug, "case": "naive", "regions": len(tgt.stroke_masks), "cap": cap, **C.short(m)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
