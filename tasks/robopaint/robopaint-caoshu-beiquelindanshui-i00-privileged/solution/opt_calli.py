"""Reference planner for the RoboPaint kaishu oracle, step 1 (robot-free; solution/ only, never in the agent image; run at
generation time by scripts/robopaint_brush_mk_task.py on the graders' copy of the instance).

Per-stroke trajectory optimisation against the task's brush model (rcb_brush.WangBrush / CalligraphyPainter), in the spirit of
Wang et al. 2020 Sec. V (optimise each stroke's end-effector path against the rendered stroke), with our own parametrisation:
K control points (x, y, press z) of the handle (tip) path, a Catmull-Rom curve through them in xy, z interpolated linearly, sampled
every `step_m` (the model has no speed term), a short approach along the first tangent 4 mm above the paper (sets the brush's
orientation), a vertical touch-down at the first point and a vertical lift at the last.
Initialisation = the exact inverse of the brush's trailing dynamics for a taut "leash": the mark's root follows the handle like a
trailer, so a root that traces the stroke's median (Make Me a Hanzi medians, from graphics.txt) needs the handle Offset(z) ahead
along the median's tangent, with z from the local width (twice the distance to the stroke's edge, through the inverse Width line).
Objective: scipy least_squares (trf, finite differences) on the rendered coverage vs the stroke's mask on a 512 px grid of the
sheet, the other strokes' masks being "don't care", plus a small smoothness term on z.

    python opt_calli.py --instance <full instance.json> --graphics graphics.txt --out plans.json [--nfev 25]
"""
from __future__ import annotations
import argparse, json, math, os, sys, time
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares

sys.path.insert(0, os.environ.get("RCB_TOOLS", "/opt/tools"))
import rcb_brush as B  # noqa: E402
import rcb_brush_score as G  # noqa: E402


class World:
    def __init__(self, inst: dict):
        self.inst = inst
        self.sheets = B.sheets_from_inst(inst)
        self.main = self.sheets["main"]
        self.wells = B.Wells(inst["wells"])
        self.target = G.GlyphTarget(inst["truth"], self.main)
        self.boxes = G.glyph_boxes(inst["truth"])


def coarse_inst(inst: dict, px: int = 512) -> dict:
    c = json.loads(json.dumps(inst))
    r0 = inst["sheets"][0]["rows"]
    for s in c["sheets"]:
        s["px_m"] = s["px_m"] * r0 / px
        s["rows"] = int(round(s["rows"] * px / r0)); s["cols"] = int(round(s["cols"] * px / r0))
    return c


def mmah_to_world(world: World, pts_units: np.ndarray, k: int) -> np.ndarray:
    """Stroke k's Make Me a Hanzi units -> world xy (m), in its character's box."""
    X, Y = G.units_to_mm(world.boxes[k], pts_units)
    x, y = world.main.mm_to_world(X, Y)
    return np.stack([x, y], 1)


def resample(P: np.ndarray, step: float) -> np.ndarray:
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    if d[-1] < 1e-12:
        return P[:1].copy()
    n = max(2, int(math.ceil(d[-1] / step)) + 1)
    s = np.linspace(0, d[-1], n)
    return np.stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])], 1)


def catmull_rom(P: np.ndarray, n_per: int = 24) -> np.ndarray:
    if len(P) == 1:
        return P.copy()
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    t = np.linspace(0, 1, n_per, endpoint=False)[:, None]
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1:])
    return np.vstack(out)


def stroke_path(P: np.ndarray, paper_z: float, step: float) -> np.ndarray:
    """Handle (tip) samples (N, 3) for one stroke plan P (K, 3: x, y, press): approach, touch-down, body, lift."""
    xy = catmull_rom(P[:, :2], 24)
    zs = np.interp(np.linspace(0, len(P) - 1, len(xy)), np.arange(len(P)), P[:, 2])
    xy_r = [xy[0]]; z_r = [zs[0]]
    for i in range(1, len(xy)):
        seg = float(np.hypot(*(xy[i] - xy[i - 1])))
        n = max(1, int(math.ceil(seg / step)))
        for j in range(1, n + 1):
            xy_r.append(xy[i - 1] + (xy[i] - xy[i - 1]) * j / n); z_r.append(zs[i - 1] + (zs[i] - zs[i - 1]) * j / n)
    xy_r = np.asarray(xy_r); z_r = np.maximum(0.0, np.asarray(z_r))
    t0 = xy_r[min(len(xy_r) - 1, 3)] - xy_r[0]; t0 = t0 / max(1e-9, np.linalg.norm(t0))
    above = 0.004
    n_app = max(1, int(round(0.004 / step)))
    app = [np.r_[xy_r[0] - t0 * 0.004 * (1 - a), above] for a in np.linspace(0, 1, n_app + 1)]
    n_dn = max(1, int(round((above + z_r[0]) / step)))
    down = [np.r_[xy_r[0], above - (above + z_r[0]) * a] for a in np.linspace(0, 1, n_dn + 1)[1:]]
    body = np.c_[xy_r, -z_r]
    n_up = max(1, int(round((above + z_r[-1]) / step)))
    up = [np.r_[xy_r[-1], -z_r[-1] + (z_r[-1] + above) * a] for a in np.linspace(0, 1, n_up + 1)[1:]]
    H = np.vstack([np.asarray(app), np.asarray(down), body, np.asarray(up)])
    H[:, 2] = paper_z + H[:, 2]
    return H


class StrokeOpt:
    def __init__(self, wc: World, median_units: list, k: int, step_m: float = 4e-4):
        self.Wc, self.k, self.step = wc, k, step_m
        self.cfg = dict(wc.inst["brush"]); self.cfg["substep_m"] = max(self.cfg["substep_m"], wc.main.px_m)
        self.brush = B.WangBrush(self.cfg)
        tc = wc.target
        self.mask = tc.stroke_masks[k]
        other = np.any([m for j, m in enumerate(tc.stroke_masks) if j != k], axis=0) if len(tc.stroke_masks) > 1 else np.zeros_like(self.mask)
        self.care = ~(other & ~self.mask)
        r, c = np.nonzero(self.mask)
        pad = int(math.ceil(0.012 / wc.main.px_m))
        self.win = (max(0, r.min() - pad), min(self.mask.shape[0], r.max() + pad + 1), max(0, c.min() - pad), min(self.mask.shape[1], c.max() + pad + 1))
        med = mmah_to_world(wc, np.asarray(median_units, np.float64), k)
        L = float(np.sum(np.hypot(*np.diff(med, axis=0).T)))
        self.K = int(np.clip(round(L / 0.010) + 2, 4, 14))
        self.P0 = self._init(med)

    def _width_inv(self, w_m: float) -> float:
        a, b = self.cfg["width_cm"]
        return float(np.clip((w_m * 100 - b) / a, 0.02, self.cfg["z_max_cm"]) / 100)

    def _init(self, med: np.ndarray) -> np.ndarray:
        W = self.Wc
        S = resample(med, 5e-4)
        dist = ndimage.distance_transform_edt(self.mask) * W.main.px_m
        u, v = W.main.world_to_px(S[:, 0], S[:, 1])
        ui = np.clip(np.rint(u).astype(int), 0, W.main.cols - 1); vi = np.clip(np.rint(v).astype(int), 0, W.main.rows - 1)
        z = ndimage.uniform_filter1d(np.array([self._width_inv(2 * d) for d in dist[vi, ui]]), 9, mode="nearest")
        T = np.gradient(S, axis=0); T /= np.maximum(1e-12, np.linalg.norm(T, axis=1, keepdims=True))
        o = np.array([self.brush.offset_of(zz) for zz in z]); d = np.array([self.brush.drag_of(zz) for zz in z])
        H = S + o[:, None] * T
        idx = np.linspace(0, len(S) - 1, self.K).round().astype(int)
        P = np.c_[H[idx], z[idx]]
        P[0, :2] = S[0] + T[0] * (d[0] * 0.6)          # touch down on the median, a little inside (the drag tail reaches back)
        return P

    def render(self, P: np.ndarray) -> np.ndarray:
        pt = B.CalligraphyPainter(self.cfg, self.Wc.sheets, self.Wc.wells)
        pt.loaded = True
        R = np.diag([1.0, -1.0, -1.0])
        for p in stroke_path(P, B.PAPER_Z, self.step):
            pt.sample(p, R)
        pt.finish()
        return pt.ink["main"]

    def residuals(self, x: np.ndarray) -> np.ndarray:
        P = x.reshape(self.K, 3)
        ink = self.render(P)
        r0, r1, c0, c1 = self.win
        diff = (ink[r0:r1, c0:c1] - self.mask[r0:r1, c0:c1].astype(np.float32)) * self.care[r0:r1, c0:c1]
        return np.concatenate([diff.ravel(), 0.3 * np.diff(P[:, 2]) / 0.002])

    def optimize(self, max_nfev: int = 25) -> tuple[np.ndarray, dict]:
        lo = np.tile([-np.inf, -np.inf, 0.0], self.K); hi = np.tile([np.inf, np.inf, self.cfg["z_max_cm"] / 100], self.K)
        x0 = np.clip(self.P0.ravel(), lo + 1e-9, hi - 1e-9)
        t = time.time()
        f0 = float(np.sum(self.residuals(x0) ** 2))
        res = least_squares(self.residuals, x0, bounds=(lo, hi), diff_step=np.tile([2e-4, 2e-4, 1.5e-4], self.K) / np.maximum(1e-9, np.abs(x0)),
                            x_scale=np.tile([1e-3, 1e-3, 1e-3], self.K), max_nfev=max_nfev, method="trf")
        return res.x.reshape(self.K, 3), {"cost0": round(f0, 3), "cost": round(float(2 * res.cost), 3), "nfev": int(res.nfev),
                                          "wall_s": round(time.time() - t, 1), "K": self.K}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True); ap.add_argument("--graphics", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--nfev", type=int, default=25)
    a = ap.parse_args()
    inst = json.load(open(a.instance))
    tr = inst["truth"]
    chars = tr.get("characters") or tr["character"]
    recs = {}
    for line in open(a.graphics, encoding="utf-8"):
        d = json.loads(line)
        if d["character"] in chars:
            recs[d["character"]] = d
    strokes = [st for c in chars for st in recs[c]["strokes"]] if all(c in recs for c in chars) else None
    if strokes != tr["strokes"]:
        raise SystemExit("graphics.txt entries missing or different from the instance's outlines")
    medians = [m for c in chars for m in recs[c]["medians"]]
    char = chars
    wc = World(coarse_inst(inst, 512))
    plans, info = [], []
    for k in range(len(medians)):
        so = StrokeOpt(wc, medians[k], k)
        P, inf = so.optimize(a.nfev)
        plans.append([[round(float(v), 7) for v in row] for row in P]); info.append(inf)
        print(f"stroke {k + 1}: K={so.K} cost {inf['cost0']:.1f} -> {inf['cost']:.1f} ({inf['nfev']} evals, {inf['wall_s']} s)", flush=True)
    json.dump({"character": char, "step_m": 4e-4, "plans": plans, "info": info}, open(a.out, "w"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
