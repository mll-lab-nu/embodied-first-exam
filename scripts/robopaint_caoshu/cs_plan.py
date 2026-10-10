#!/usr/bin/env python3
"""RoboPaint caoshu (草書) reference planner, robot-free (the oracle's step 1; graders' copy of the instance; never in the agent's
container). One plan per brush CONTACT of the exemplar (cs_exemplar.py's trails): a single handle path (x, y, press) through all of
the contact's regions, optimised against the task's brush model (opt_calli.StrokeOpt / xingshu's TrailOpt: control points every
step_mm of centre path, initialised by inverting the brush's trailing dynamics along the concatenated centre paths, scipy
least_squares on the rendered contact vs the union of its regions, the other regions "don't care"). Then a full-resolution
robot-free score with the cap = the number of contacts, and pictures.

    python cs_plan.py opt  --exemplar work/ex/wen --out work/plan/wen [--workers 8] [--nfev 25]
    python cs_plan.py eval --exemplar work/ex/wen --out work/plan/wen
Needs RCB_TOOLS = a directory with rcb_brush.py, rcb_brush_score.py, opt_calli.py (the template pair's tests/ and solution/).
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
import argparse, json, math, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, os.environ.get("RCB_TOOLS", "/opt/tools"))
import rcb_brush as B  # noqa: E402
import rcb_brush_score as G  # noqa: E402
import opt_calli as O  # noqa: E402

SHEET_MM = 227.1845
SUCCESS = {"iou": 0.80, "boundary_f": 0.75, "min_stroke_coverage": 0.80, "max_stray_frac": 0.04, "register_mm": 5.0}
R_DOWN = np.diag([1.0, -1.0, -1.0])


def spec_for(ex_dir: str, slug: str) -> tuple[dict, dict]:
    cj = json.load(open(os.path.join(ex_dir, f"{slug}.contacts.json"), encoding="utf-8"))
    chars, st = cj["chars"], cj["stats"]
    box_mm = float(st.get("box_mm") or (210.0 if len(chars) > 1 else 150.0))
    X0 = (SHEET_MM - box_mm) / 2
    if len(chars) == 1:
        tgt = {"character": chars, "box_mm": [X0, X0, box_mm]}
    else:                                                      # a work in ONE frame shared by its characters (the column as written)
        tgt = {"characters": chars, "boxes": [[round(X0, 4), round(X0, 4), box_mm]] * len(chars)}
    spec = {"task": f"robopaint_caoshu_{slug}", "medium": "calligraphy",
            "target": {**tgt, "graphics": os.path.join(ex_dir, f"{slug}.graphics.txt"), "stroke_slack": 0,
                       "success": {**SUCCESS, "max_strokes": len(cj["contacts"])}}}
    return spec, cj


class ContactOpt(O.StrokeOpt):
    """One brush contact through several regions (xingshu's TrailOpt): K control points (x, y, press) every step_m of centre path."""

    def __init__(self, wc, poly: np.ndarray, ks: list[int], step_m: float, kmax: int, z0max: float = 0.003, zmin: float = 0.0,
                 zendmax: float = 0.0, leash_m: float = 0.0):
        self.Wc, self.k, self.step = wc, ks[0], 4e-4
        self.cfg = dict(wc.inst["brush"]); self.cfg["substep_m"] = max(self.cfg["substep_m"], wc.main.px_m)
        self.brush = B.WangBrush(self.cfg)
        tc = wc.target
        self.mask = np.any([tc.stroke_masks[k] for k in ks], axis=0)
        rest = [m for j, m in enumerate(tc.stroke_masks) if j not in ks]
        other = np.any(rest, axis=0) if rest else np.zeros_like(self.mask)
        self.care = ~(other & ~self.mask)
        r, c = np.nonzero(self.mask)
        pad = int(math.ceil(0.012 / wc.main.px_m))
        self.win = (max(0, r.min() - pad), min(self.mask.shape[0], r.max() + pad + 1), max(0, c.min() - pad), min(self.mask.shape[1], c.max() + pad + 1))
        Lm = float(np.sum(np.hypot(*np.diff(poly, axis=0).T)))
        self.K = int(np.clip(round(Lm / step_m) + 2, 4, kmax))
        self.z0max, self.zmin, self.zendmax, self.leash = z0max, zmin, zendmax, leash_m
        self.P0 = self._init(poly)
        self.P0[0, 2] = min(self.P0[0, 2], z0max - 1e-6)

    def optimize(self, max_nfev: int = 25, x_init: np.ndarray | None = None):
        lo = np.tile([-np.inf, -np.inf, self.zmin], self.K); hi = np.tile([np.inf, np.inf, self.cfg["z_max_cm"] / 100], self.K)
        hi[2] = self.z0max
        if self.zendmax > 0:
            hi[-1] = self.zendmax
        if self.leash > 0:                                     # each control point within leash of its start (x, y): the residual only
            for d in (0, 1):                                   # sees the contact's window, so a point outside it would cost nothing
                lo[d::3] = self.P0[:, d] - self.leash; hi[d::3] = self.P0[:, d] + self.leash
        x0 = np.clip((self.P0 if x_init is None else x_init).ravel(), lo + 1e-9, hi - 1e-9)
        t = time.time()
        f0 = float(np.sum(self.residuals(x0) ** 2))
        res = least_squares(self.residuals, x0, bounds=(lo, hi), diff_step=np.tile([2e-4, 2e-4, 1.5e-4], self.K) / np.maximum(1e-9, np.abs(x0)),
                            x_scale=np.tile([1e-3, 1e-3, 1e-3], self.K), max_nfev=max_nfev, method="trf")
        return res.x.reshape(self.K, 3), {"cost0": round(f0, 3), "cost": round(float(2 * res.cost), 3), "nfev": int(res.nfev),
                                          "wall_s": round(time.time() - t, 1), "K": self.K}


_CTX = {}


def ctx(ex_dir: str, slug: str, coarse: bool):
    key = (ex_dir, slug, coarse)
    if key not in _CTX:
        spec, cj = spec_for(ex_dir, slug)
        inst = G.build_instance(spec)
        recs = {}
        for line in open(spec["target"]["graphics"], encoding="utf-8"):
            d = json.loads(line); recs[d["character"]] = d
        medians = [m for c in cj["chars"] for m in recs[c]["medians"]]
        wc = O.World(O.coarse_inst(inst, 512) if coarse else inst)
        _CTX[key] = (inst, cj, medians, wc)
    return _CTX[key]


def contact_poly(wc, medians: list, contact: list) -> np.ndarray:
    segs = []
    for k, fwd in contact:
        P = O.mmah_to_world(wc, np.asarray(medians[k], np.float64), k)
        segs.append(P if fwd else P[::-1])
    return np.vstack(segs)


def opt_job(args):
    ex_dir, slug, i, nfev, step_mm, kmax, z0max, zmin, zendmax, leash_mm = args
    inst, cj, medians, wc = ctx(ex_dir, slug, True)
    contact = [(int(k), bool(f)) for k, f in cj["contacts"][i]]
    so = ContactOpt(wc, contact_poly(wc, medians, contact), [k for k, _ in contact], step_mm / 1000.0, kmax, z0max, zmin, zendmax, leash_mm / 1000.0)
    P, info = so.optimize(nfev)
    return i, P.tolist(), info


def paths_of(plans: list, step: float = 4e-4) -> list:
    return [O.stroke_path(np.asarray(P, np.float64), B.PAPER_Z, step) for P in plans]


def write(inst: dict, paths: list):
    sheets = B.sheets_from_inst(inst)
    pt = B.CalligraphyPainter(inst["brush"], sheets, B.Wells(inst["wells"]))
    w = inst["wells"]["wells"][0]
    for H in paths:
        pt.sample(np.array([w["center_xy"][0], w["center_xy"][1], inst["wells"]["surface_z"] - 0.003]), R_DOWN)
        pt.sample(np.array([w["center_xy"][0], w["center_xy"][1], inst["wells"]["surface_z"] + 0.02]), R_DOWN)
        for p in H:
            pt.sample(p, R_DOWN)
    pt.finish()
    return pt


def score(inst: dict, pt, target) -> dict:
    cfg = dict(inst["target"]["success"])
    m = G.score_ink(pt.ink["main"], target, pt.strokes, cfg=cfg)
    m["success"] = bool(G.is_success(m, cfg)); m["final_reward"] = G.final_reward(m)
    return m


KEYS = ("success", "final_reward", "iou", "boundary_f", "min_stroke_coverage", "mean_stroke_coverage", "stray_frac", "missing_frac",
        "n_strokes", "max_strokes", "register_shift_mm")


def short(m: dict) -> dict:
    return {k: (round(float(m[k]), 4) if not isinstance(m[k], bool) else m[k]) for k in KEYS if k in m}


def pictures(out: str, name: str, pt, target) -> None:
    from PIL import Image
    T = target.mask; I = pt.ink["main"] >= 0.5
    ov = np.full(T.shape + (3,), 255, np.uint8); ov[T & I] = (40, 40, 40); ov[T & ~I] = (60, 190, 60); ov[I & ~T] = (220, 50, 50)
    Image.fromarray(ov).save(os.path.join(out, f"{name}_overlay.png"))
    Image.fromarray(np.round(np.clip(pt.display("main"), 0, 1) * 255).astype(np.uint8)).save(os.path.join(out, f"{name}_ink.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("opt", "eval", "refine"))
    ap.add_argument("--exemplar", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--nfev", type=int, default=25)
    ap.add_argument("--step-mm", type=float, default=7.0); ap.add_argument("--kmax", type=int, default=48)
    ap.add_argument("--z0max", type=float, default=0.003)
    ap.add_argument("--zmin", type=float, default=0.0, help="press floor (m) at every control point: a contact that touches the paper at"
                    " zero press breaks into two strokes on the robot (tracking error lifts the tip)")
    ap.add_argument("--zendmax", type=float, default=0.0, help="press cap (m) at a contact's last control point (0 = none): the touch-down"
                    " and the lift are vertical, and the robot's sway there drags a deep press into a blot (with --z0max for the start)")
    ap.add_argument("--leash-mm", type=float, default=0.0, help="keep every control point within this distance (x and y) of its initial"
                    " place (0 = free): with a press floor the optimiser otherwise parks surplus path off the sheet, out of the residual's window")
    ap.add_argument("--only", default="", help="refine: comma-separated contact indices")
    a = ap.parse_args()
    ex = os.path.abspath(a.exemplar); slug = os.path.basename(ex.rstrip("/"))
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    if a.cmd in ("opt", "refine"):
        inst, cj, medians, wc = ctx(ex, slug, True)
        n = len(cj["contacts"])
        prev = json.load(open(os.path.join(a.out, "plans.json"))) if a.cmd == "refine" else None
        todo = [int(x) for x in a.only.split(",")] if a.only else list(range(n))
        res = {i: (prev["plans"][i], prev["info"][i]) for i in range(n)} if prev else {}
        jobs = sorted([(ex, slug, i, a.nfev, a.step_mm, a.kmax, a.z0max, a.zmin, a.zendmax, a.leash_mm) for i in todo],
                      key=lambda j: -len(cj["contacts"][j[2]]))
        with ProcessPoolExecutor(min(a.workers, len(jobs))) as pool:
            futs = [pool.submit(opt_job, j) for j in jobs]
            for f in as_completed(futs):
                i, P, info = f.result()
                res[i] = (P, info)
                print(f"[{time.time() - t0:6.0f}s] contact {i + 1}/{n}: regions {len(cj['contacts'][i])} K={info['K']} cost {info['cost0']} -> {info['cost']} ({info['wall_s']} s)", flush=True)
        json.dump({"character": cj["chars"], "step_m": 4e-4, "plans": [[[round(float(v), 7) for v in row] for row in res[i][0]] for i in range(n)],
                   "info": [res[i][1] for i in range(n)], "contacts": cj["contacts"]},
                  open(os.path.join(a.out, "plans.json"), "w"), indent=1, ensure_ascii=False)
    if a.cmd in ("eval", "opt", "refine"):
        inst, cj, medians, wf = ctx(ex, slug, False)
        d = json.load(open(os.path.join(a.out, "plans.json")))
        pt = write(inst, paths_of(d["plans"]))
        m = score(inst, pt, wf.target)
        pictures(a.out, "robotfree", pt, wf.target)
        from PIL import Image
        Image.fromarray(wf.target.image()).save(os.path.join(a.out, "target_preview.png"))
        nreg = len(wf.target.stroke_masks)
        cov = [round(m[f"stroke_coverage_{k + 1:02d}"], 3) for k in range(nreg)]
        r = {"slug": slug, "chars": cj["chars"], "contacts": len(d["plans"]), "regions": nreg, "robotfree": short(m), "region_cov": cov,
             "weak_regions": [k + 1 for k, c in enumerate(cov) if c < 0.85],
             "area_mm2": round(wf.target.area_px * (wf.target.sheet.px_m * 1000) ** 2, 1)}
        json.dump(r, open(os.path.join(a.out, "robotfree.json"), "w"), indent=1, ensure_ascii=False)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    print(f"done in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
