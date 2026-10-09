#!/usr/bin/env python3
"""Robot-free study of the caoshu scoring (what the picture rule + the contact cap catch), on the reference plans:
  ref            the reference plans (one contact each)
  shift_X        every plan moved X mm along the sheet's x (registration takes up to 5 mm of a global shift, so a pure shift
                 is free: this shifts each contact by a different amount, alternating +X / -X: a relative placement error)
  press_F        every press x F
  const_contact  each contact at one press (its median): width variation inside a contact removed
  const_global   every contact at the same press (the median of all): a uniform marker
  per_region     one contact per region (lifts at every region boundary), each region's part of its contact's path
  split_half     every contact cut in two (a lift in the middle)
  missing_k      contact k left out (the best of them is reported)
  naive          the handle on each region's centre path, the press from the local width, a contact per region
Prints one JSON line per case: success, the picture metrics, n_strokes vs the cap.
    python cs_perturb.py --exemplar work/ex/<slug> --plans work/plan/<slug>/plans.json
"""
import argparse, json, os, sys
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cs_plan as C  # noqa: E402
B, G, O = C.B, C.G, C.O


def sub_plans(P: np.ndarray, n: int) -> list:
    """Cut a plan's control points into n consecutive pieces (each >= 2 points, overlapping by one point)."""
    K = len(P)
    cuts = np.linspace(0, K - 1, n + 1).round().astype(int)
    out = []
    for i in range(n):
        a, b = cuts[i], max(cuts[i + 1], cuts[i] + 1)
        out.append(P[a:b + 1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exemplar", required=True); ap.add_argument("--plans", required=True)
    ap.add_argument("--cases", default="ref,shift_0.5,shift_1.0,shift_1.5,press_0.8,press_1.2,const_contact,const_global,per_region,split_half,missing,naive")
    a = ap.parse_args()
    ex = os.path.abspath(a.exemplar); slug = os.path.basename(ex.rstrip("/"))
    inst, cj, medians, wf = C.ctx(ex, slug, False)
    tgt = wf.target
    plans = [np.asarray(P, np.float64) for P in json.load(open(a.plans))["plans"]]
    contacts = cj["contacts"]
    cap = len(plans)

    def run(name, plist):
        pt = C.write(inst, C.paths_of(plist))
        m = C.score(inst, pt, tgt)
        r = {"case": name, **C.short(m), "cap": cap}
        print(json.dumps(r), flush=True)
        return r

    res = []
    for case in a.cases.split(","):
        if case == "ref":
            res.append(run(case, plans))
        elif case.startswith("shift_"):
            mm = float(case.split("_")[1])
            res.append(run(case, [P + np.array([(mm if i % 2 == 0 else -mm) / 1000, 0, 0]) for i, P in enumerate(plans)]))
        elif case.startswith("press_"):
            f = float(case.split("_")[1])
            res.append(run(case, [P * np.array([1, 1, f]) for P in plans]))
        elif case == "const_contact":
            res.append(run(case, [np.c_[P[:, :2], np.r_[P[0, 2], np.full(len(P) - 1, np.median(P[1:, 2]))]] for P in plans]))
        elif case == "const_global":
            zg = float(np.median(np.concatenate([P[1:, 2] for P in plans])))
            res.append(run(case, [np.c_[P[:, :2], np.r_[min(P[0, 2], zg), np.full(len(P) - 1, zg)]] for P in plans]))
        elif case == "per_region":
            out = []
            for P, c in zip(plans, contacts):
                out += sub_plans(P, len(c)) if len(c) > 1 else [P]
            res.append(run(case, out))
        elif case == "split_half":
            out = []
            for P in plans:
                out += sub_plans(P, 2) if len(P) >= 4 else [P]
            res.append(run(case, out))
        elif case == "missing":
            best = None
            for k in range(len(plans)):
                pt = C.write(inst, C.paths_of([P for j, P in enumerate(plans) if j != k]))
                m = C.score(inst, pt, tgt)
                if best is None or m["iou"] > best[1]["iou"]:
                    best = (k, m)
            r = {"case": f"missing_best(contact {best[0] + 1})", **C.short(best[1]), "cap": cap}
            print(json.dumps(r), flush=True); res.append(r)
        elif case == "naive":
            sheet = tgt.sheet
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
            r = {"case": "naive", **C.short(m), "cap": cap}
            print(json.dumps(r), flush=True); res.append(r)
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(a.plans)), "perturb.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
