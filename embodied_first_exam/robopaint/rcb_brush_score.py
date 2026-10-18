"""
rcb_brush_score.py — the GRADERS' side of the RoboPaint brush tasks (kaishu, lettering, acrylic, oil). Never in the agent's
container: the unlimited verifier (tests/), the limited sim sidecar (environment/sim/) and the unlimited scoring service
(environment/scorer/) hold it with the graders' frozen instance, whose "truth" section keeps what the score needs (a character's
per-stroke outlines, a word's pen paths, or a painting's paint coverage file). Here: the targets built from the truth, the scores
(masks: IoU, boundary F, per-stroke coverage, stray / missing ink, stroke count, order; paintings: blurred CIELAB ΔE, SSIM of L*,
paint IoU), the instance builder, the agent's copy of an instance (scene + rule only) and the target picture.

CLI (generation time, in the base image):
  python rcb_brush_score.py make-instance --spec spec.json --out dir/instance.json     (+ dir/target.png unless the spec's medium paints it)
  python rcb_brush_score.py make-agent-instance --instance dir/instance.json --out-dir agent/
  python rcb_brush_score.py score --instance dir/instance.json --canvas canvas.png
"""
from __future__ import annotations
import argparse, json, math, os, shutil, sys
from pathlib import Path

import numpy as np

import rcb_brush as R
from rcb_brush import (Sheet, Session, sheets_from_inst, sha16, srgb_to_linear, PAPER_RGB, INK_RGB, TOL_MM, _segment_footprint,
                       _capsule_footprint, default_sheets, build_wells, BRUSH_WANG, BRUSH_NIB, BRUSH_POINTED, BRUSH_MYPAINT, MYPAINT_BRUSHES,
                       REST_QPOS, ROBOT_BASE, CONTROL_HZ, SIM_HZ, MAX_STEPS)


# --------------------------------------------------------------------------- polygons, masks, metrics
def _poly_mask(poly_px: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Pixel centres (integer col u, row v) strictly inside the closed polygon (u, v) (matplotlib's point-in-polygon)."""
    from matplotlib.path import Path as MPath
    m = np.zeros((rows, cols), bool)
    u0 = max(0, int(math.floor(poly_px[:, 0].min()))); u1 = min(cols - 1, int(math.ceil(poly_px[:, 0].max())))
    v0 = max(0, int(math.floor(poly_px[:, 1].min()))); v1 = min(rows - 1, int(math.ceil(poly_px[:, 1].max())))
    if u1 < u0 or v1 < v0:
        return m
    uu, vv = np.meshgrid(np.arange(u0, u1 + 1), np.arange(v0, v1 + 1))
    inside = MPath(poly_px).contains_points(np.stack([uu.ravel(), vv.ravel()], 1).astype(np.float64)).reshape(uu.shape)
    m[v0:v1 + 1, u0:u1 + 1] = inside
    return m


def _poly_coverage(poly_px: np.ndarray, rows: int, cols: int, ss: int = 4) -> np.ndarray:
    """Anti-aliased coverage in [0, 1] of the polygon: ss x ss point samples per pixel (for the target picture only)."""
    from matplotlib.path import Path as MPath
    cov = np.zeros((rows, cols), np.float32)
    u0 = max(0, int(math.floor(poly_px[:, 0].min())) - 1); u1 = min(cols - 1, int(math.ceil(poly_px[:, 0].max())) + 1)
    v0 = max(0, int(math.floor(poly_px[:, 1].min())) - 1); v1 = min(rows - 1, int(math.ceil(poly_px[:, 1].max())) + 1)
    if u1 < u0 or v1 < v0:
        return cov
    off = (np.arange(ss) + 0.5) / ss - 0.5
    uu, vv = np.meshgrid(np.arange(u0, u1 + 1), np.arange(v0, v1 + 1))
    acc = np.zeros(uu.shape, np.float32)
    path = MPath(poly_px)
    for du in off:
        for dv in off:
            acc += path.contains_points(np.stack([(uu + du).ravel(), (vv + dv).ravel()], 1)).reshape(uu.shape)
    cov[v0:v1 + 1, u0:u1 + 1] = acc / (ss * ss)
    return cov


def _boundary(m: np.ndarray) -> np.ndarray:
    from scipy import ndimage
    return m & ~ndimage.binary_erosion(m, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool), border_value=0)


def glyph_boxes(tgt: dict) -> list[list[float]]:
    """The box (paper mm [X0, Y0, size]) of every stroke: one box for a single character, the stroke's own character's box in a
    work of several characters (tgt["glyphs"] = [{"character", "box_mm", "n_strokes"}], strokes in writing order)."""
    if tgt.get("glyphs"):
        return [list(map(float, g["box_mm"])) for g in tgt["glyphs"] for _ in range(int(g["n_strokes"]))]
    return [list(map(float, tgt["box_mm"]))] * len(tgt["strokes"])


def units_to_mm(box: list[float], P_units: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Make Me a Hanzi em units (1024 per em, y up, the em box's upper-left corner at (0, 900)) -> paper mm in the box."""
    X0, Y0, S = box
    k = S / 1024.0
    return X0 + P_units[:, 0] * k, Y0 + (900.0 - P_units[:, 1]) * k


class GlyphTarget:
    """An exemplar character (or a work of several): per-stroke outlines (Make Me a Hanzi graphics.txt, 1024-unit em box with y up,
    the upper-left corner at (0, 900)) placed in square boxes on the main sheet (paper mm: box = [X0, Y0, size]). Masks at the sheet's
    raster."""
    UNITS = 1024.0

    def __init__(self, tgt: dict, sheet: Sheet):
        from svgpathtools import parse_path
        self.d, self.sheet = tgt, sheet
        boxes = glyph_boxes(tgt)
        if len(boxes) != len(tgt["strokes"]):
            raise ValueError("glyph boxes do not match the strokes")
        self.polys_px: list[np.ndarray] = []
        for dstr, box in zip(tgt["strokes"], boxes):
            path = parse_path(dstr)
            pts = [np.array([path.start.real, path.start.imag])]
            for seg in path:
                n = max(2, int(math.ceil(float(seg.length()) / 1.0)))       # <= 1 em unit (<= 0.15 mm for a 150 mm box) between points
                for t in np.linspace(0.0, 1.0, n + 1)[1:]:
                    z = seg.point(t); pts.append(np.array([z.real, z.imag]))
            P = np.asarray(pts, np.float64)
            Xmm, Ymm = units_to_mm(box, P)
            u, v = sheet.mm_to_px(Xmm, Ymm)
            self.polys_px.append(np.stack([u, v], 1))
        self.n_strokes = len(self.polys_px)
        self.stroke_masks = [_poly_mask(p, sheet.rows, sheet.cols) for p in self.polys_px]
        self.mask = np.any(self.stroke_masks, axis=0)
        self.area_px = int(self.mask.sum())
        self.sha = sha16(np.packbits(np.stack(self.stroke_masks)).tobytes(), json.dumps(boxes if tgt.get("glyphs") else tgt["box_mm"]).encode())

    def coverage(self) -> np.ndarray:
        """Anti-aliased coverage of the whole glyph (max over strokes) for the target picture."""
        if self.polys_px is None:
            return self.mask.astype(np.float32)
        c = np.zeros((self.sheet.rows, self.sheet.cols), np.float32)
        for p in self.polys_px:
            np.maximum(c, _poly_coverage(p, self.sheet.rows, self.sheet.cols), out=c)
        return c

    def image(self) -> np.ndarray:
        a = self.coverage()[..., None]
        img = np.asarray(PAPER_RGB, np.float32) * (1 - a) + np.asarray(INK_RGB, np.float32) * a
        return np.round(img * 255).astype(np.uint8)


# --------------------------------------------------------------------------- registration (snapshot 21: every brush family)
REGISTER_MM = 5.0          # the default search window (the rule's success.register_mm; 0 switches registration off)


def register_window_px(cfg: dict | None, px_mm: float) -> int:
    """The half-width of the square search window in whole pixels: floor(register_mm / px_mm)."""
    return max(0, int(math.floor(float((cfg or {}).get("register_mm", REGISTER_MM)) / px_mm + 1e-9)))


def register_masks(I: np.ndarray, G: np.ndarray, R: int) -> tuple[int, int, bool]:
    """Ink targets: the integer translation (dy, dx), |dy|, |dx| <= R, that maximises the overlap count(I[v + dy, u + dx] & G[v, u])
    of the canvas's ink I with the target's mask G (canvas ~ target moved by (dx, dy)). The counts come from one FFT
    cross-correlation of the zero-padded masks and are exact integers (rounded); ties go to the smallest dy^2 + dx^2, then dy,
    then dx. at_edge: the best shift lies on the window's border (the caller then scores at zero shift)."""
    if R <= 0 or not I.any() or not G.any():
        return 0, 0, False
    from scipy import fft as sfft
    H, W = G.shape
    Hp, Wp = sfft.next_fast_len(H + R + 1), sfft.next_fast_len(W + R + 1)
    c = sfft.irfft2(sfft.rfft2(I.astype(np.float64), s=(Hp, Wp)) * np.conj(sfft.rfft2(G.astype(np.float64), s=(Hp, Wp))), s=(Hp, Wp))
    lags = np.arange(-R, R + 1)
    C = np.rint(c[np.ix_(lags % Hp, lags % Wp)]).astype(np.int64)          # C[dy + R, dx + R]
    ys, xs = np.nonzero(C == C.max())
    _, dy, dx = min(((int(y) - R) ** 2 + (int(x) - R) ** 2, int(y) - R, int(x) - R) for y, x in zip(ys, xs))
    return dy, dx, bool(abs(dy) == R or abs(dx) == R)


def register_paint(A: np.ndarray, T: np.ndarray, R: int) -> tuple[int, int, bool]:
    """Paintings: A, T = the canvas's and the target's CIELAB, both blurred at the rule's blur_mm (H, W, 3). The integer translation
    (dy, dx), |dy|, |dx| <= R, that minimises the mean CIELAB difference over a FIXED central window of the target (the sheet minus R
    pixels on every side, so every candidate is judged on the same target pixels): mean ||A[v + dy, u + dx] - T[v, u]||. Coarse to
    fine on s x s block means (s = 4: the whole window; s = 2 and 1: +-2 around the doubled best); ties (objective rounded to 1e-9)
    go to the smallest dy^2 + dx^2, then dy, then dx. at_edge as for register_masks."""
    if R <= 0:
        return 0, 0, False

    def blocks(X: np.ndarray, s: int) -> np.ndarray:
        h, w = X.shape[0] // s * s, X.shape[1] // s * s
        return X[:h, :w].reshape(h // s, s, w // s, s, X.shape[2]).mean((1, 3))

    best = None
    for s in (4, 2, 1):
        As, Ts = (A, T) if s == 1 else (blocks(A, s), blocks(T, s))
        hs, ws = Ts.shape[:2]
        Rs, lim = int(math.ceil(R / s)), R // s
        Tw = Ts[Rs:hs - Rs, Rs:ws - Rs]
        if best is None:
            cands = [(dy, dx) for dy in range(-lim, lim + 1) for dx in range(-lim, lim + 1)]
        else:
            by, bx = 2 * best[0], 2 * best[1]
            cands = [(dy, dx) for dy in range(by - 2, by + 3) for dx in range(bx - 2, bx + 3) if abs(dy) <= lim and abs(dx) <= lim]
        scored = []
        for dy, dx in cands:
            Aw = As[Rs + dy:hs - Rs + dy, Rs + dx:ws - Rs + dx]
            scored.append((round(float(np.sqrt(((Aw - Tw) ** 2).sum(-1)).mean()), 9), dy * dy + dx * dx, dy, dx))
        best = min(scored)[2:]
    dy, dx = best
    return int(dy), int(dx), bool(abs(dy) == R or abs(dx) == R)


def _overlap_slices(shape, dy: int, dx: int, b: int = 0):
    """The overlap of the canvas moved back by (dy, dx) with the target, inside the target's central window [b, N - b) (the rule's
    score_inset_mm; b = 0: the whole sheet): the target's slices [v0, v1) x [u0, u1), the canvas's (the same + (dy, dx)) and the
    origin (v0, u0)."""
    H, W = shape[:2]
    v0, v1, u0, u1 = max(b, -dy, 0), min(H - b, H - dy, H), max(b, -dx, 0), min(W - b, W - dx, W)
    return (slice(v0, v1), slice(u0, u1)), (slice(v0 + dy, v1 + dy), slice(u0 + dx, u1 + dx)), (v0, u0)


def score_inset_px(cfg: dict | None, px_mm: float) -> int:
    """The scored window's inset from every sheet edge in whole pixels: round(score_inset_mm / px_mm) (O/4; 0 = the whole sheet)."""
    return max(0, int(round(float((cfg or {}).get("score_inset_mm", 0.0)) / px_mm)))


class _Overlap:
    """A target restricted to the overlap window of a registration (the attributes the scores read)."""
    def __init__(self, t, sl):
        self.sheet, self.n_strokes = t.sheet, t.n_strokes
        self.mask = t.mask[sl]
        self.stroke_masks = [m[sl] for m in getattr(t, "stroke_masks", [])]
        if hasattr(t, "lab"):
            self.lab = t.lab[sl]
        r = getattr(t, "regions", None)
        self.regions = r[sl] if r is not None else None


def _register_fields(dy: int, dx: int, edge: bool, px_mm: float, R: int, b: int = 0) -> dict[str, float]:
    out = {"register_dx_mm": round(dx * px_mm, 4), "register_dy_mm": round(dy * px_mm, 4),
           "register_shift_mm": round(math.hypot(dx, dy) * px_mm, 4), "register_at_edge": float(edge),
           "register_window_mm": round(R * px_mm, 4)}
    if b:
        out["score_inset_mm"] = round(b * px_mm, 4)
    return out


def _overlap_at(tm: np.ndarray, r0: int, c0: int, m: np.ndarray) -> int:
    """count(tm & m) with the mask m placed at (r0, c0) on tm's raster (clipped at the borders)."""
    H, W = tm.shape; h, w = m.shape
    a0, b0, a1, b1 = max(0, r0), max(0, c0), min(H, r0 + h), min(W, c0 + w)
    if a1 <= a0 or b1 <= b0:
        return 0
    return int((tm[a0:a1, b0:b1] & m[a0 - r0:a1 - r0, b0 - c0:b1 - c0]).sum())


def score_ink(ink: np.ndarray, target, strokes: list[dict] | None = None, tol_mm: float = TOL_MM, cfg: dict | None = None) -> dict[str, float]:
    """Ink coverage of the main sheet (float [0, 1]) vs a mask target (GlyphTarget / LetterTarget), REGISTERED: the canvas is first
    aligned to the target by the best global translation within the rule's register_mm (register_masks; translation only, one shift
    for the whole sheet, so a work's relative layout still counts; a best shift on the window's border -> zero shift) and every
    metric is taken on the overlap at that shift. Reports the shift and the main metrics unregistered. Numeric fields only."""
    cfg = cfg or {}
    px_mm = target.sheet.px_m * 1000.0
    R = register_window_px(cfg, px_mm)
    b = score_inset_px(cfg, px_mm)
    dy, dx, edge = register_masks(np.asarray(ink) >= 0.5, target.mask, R)
    if edge:
        dy = dx = 0

    def at(dy_: int, dx_: int) -> dict[str, float]:
        if (dy_, dx_) == (0, 0) and b == 0:
            return _score_ink_at(ink, target, strokes, tol_mm, cfg)
        st, sc, (v0, u0) = _overlap_slices(np.asarray(ink).shape, dy_, dx_, b)
        moved = None if strokes is None else [dict(s_, mask_bbox=[s_["mask_bbox"][0] - dy_ - v0, s_["mask_bbox"][1] - dx_ - u0, *s_["mask_bbox"][2:]])
                                               if s_["sheet"] == "main" else s_ for s_ in strokes]
        return _score_ink_at(np.asarray(ink)[sc], _Overlap(target, st), moved, tol_mm, cfg)

    base = at(0, 0)
    m = dict(base) if (dy, dx) == (0, 0) else at(dy, dx)
    m.update(_register_fields(dy, dx, edge, px_mm, R, b))
    for k in ("iou", "boundary_f", "min_stroke_coverage", "stray_frac"):
        m[f"{k}_unregistered"] = base.get(k, 0.0)
    return m


def _score_ink_at(ink: np.ndarray, target, strokes: list[dict] | None, tol_mm: float, cfg: dict) -> dict[str, float]:
    """The ink metrics of a canvas against a target on the same raster (no registration)."""
    from scipy import ndimage
    px_mm = target.sheet.px_m * 1000.0
    I = ink >= 0.5; G = target.mask
    inter = int((I & G).sum()); union = int((I | G).sum()); nI = int(I.sum()); nG = int(G.sum())
    iou = inter / union if union else 0.0
    bI, bG = _boundary(I), _boundary(G)
    dG = ndimage.distance_transform_edt(~bG) * px_mm
    dI = ndimage.distance_transform_edt(~bI) * px_mm if bI.any() else np.full(G.shape, 1e3)
    bp = float((dG[bI] <= tol_mm).mean()) if bI.any() else 0.0
    br = float((dI[bG] <= tol_mm).mean()) if bG.any() else 0.0
    bf = 2 * bp * br / (bp + br) if bp + br > 0 else 0.0
    near_G = ndimage.distance_transform_edt(~G) * px_mm <= tol_mm
    near_I = (ndimage.distance_transform_edt(~I) * px_mm <= tol_mm) if nI else np.zeros_like(G)
    stray = int((I & ~near_G).sum()); missing = int((G & ~near_I).sum())
    cov = [float((I & m).sum()) / max(1, int(m.sum())) for m in target.stroke_masks]
    out = {"iou": round(iou, 6), "boundary_precision": round(bp, 6), "boundary_recall": round(br, 6), "boundary_f": round(bf, 6),
           "ink_precision": round(inter / nI, 6) if nI else 0.0, "ink_recall": round(inter / nG, 6) if nG else 0.0,
           "min_stroke_coverage": round(min(cov), 6) if cov else 0.0, "mean_stroke_coverage": round(float(np.mean(cov)), 6) if cov else 0.0,
           "stray_frac": round(stray / max(1, nG), 6), "missing_frac": round(missing / max(1, nG), 6),
           "ink_area_mm2": round(nI * px_mm ** 2, 2), "target_area_mm2": round(nG * px_mm ** 2, 2), "n_target_strokes": float(target.n_strokes)}
    for k, c in enumerate(cov):
        out[f"stroke_coverage_{k + 1:02d}"] = round(c, 6)
    # strokes: count (inked contacts with the main sheet) and order (each realized stroke -> the target stroke it covers most)
    if strokes is not None:
        main = [s for s in strokes if s["sheet"] == "main" and s["inked"]]
        out["n_strokes"] = float(len(main))
        out["n_practice_strokes"] = float(sum(1 for s in strokes if s["sheet"] == "practice" and s["inked"]))
        out["n_dry_strokes"] = float(sum(1 for s in strokes if not s["inked"]))
        match = []
        for s in main:
            r0, c0, m = s["mask_bbox"][0], s["mask_bbox"][1], s["mask"] >= 128
            best, bi = 0, -1
            for k, tm in enumerate(target.stroke_masks):
                ov = _overlap_at(tm, r0, c0, m)
                if ov > best:
                    best, bi = ov, k
            match.append(bi)
        seq = [k for k in match if k >= 0]
        pairs = [(i, j) for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] != seq[j]]
        out["stroke_order_concordance"] = round(sum(seq[i] < seq[j] for i, j in pairs) / len(pairs), 6) if pairs else 0.0
        out["stroke_order_exact"] = float(seq == list(range(target.n_strokes)))
        out["strokes_matched_distinct"] = float(len(set(seq)))
        cap = int(cfg.get("max_strokes", target.n_strokes))
        out["max_strokes"] = float(cap)
        out["stroke_count_ok"] = float(len(main) <= cap)
    return out


def is_success(m: dict, cfg: dict) -> bool:
    """cfg = instance["target"]["success"]: minimum IoU / boundary F / per-stroke coverage, maximum stray ink, stroke cap; all taken
    at the registration (score_ink)."""
    return bool(m.get("iou", 0) >= cfg["iou"] and m.get("boundary_f", 0) >= cfg["boundary_f"]
                and m.get("min_stroke_coverage", 0) >= cfg["min_stroke_coverage"] and m.get("stray_frac", 1) <= cfg["max_stray_frac"]
                and m.get("stroke_count_ok", 0) >= 1.0)


def final_reward(m: dict) -> float:
    """Continuous score in [0, 1]: the (registered) IoU, scaled down when the stroke cap is exceeded."""
    iou = float(m.get("iou", 0.0))
    n, cap = float(m.get("n_strokes", 0.0)), float(m.get("max_strokes", 1.0))
    return round(iou * (min(1.0, cap / n) if n > cap else 1.0), 6)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB in [0, 1] (..., 3) -> CIELAB (D65)."""
    c = srgb_to_linear(np.clip(rgb, 0, 1))
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


class PaintTarget:
    """A painting exemplar: the picture target.png (the main sheet, 1024 px; the agent has the same file) + its paint coverage (alpha,
    the graders' truth_alpha.npz). No geometry exists: the exemplar is a painting of a hidden stroke program that only solution/ has."""
    def __init__(self, truth: dict, sheet: Sheet, base_dir: str, picture):
        self.d, self.sheet = truth, sheet
        img = picture.rgb.astype(np.float64) / 255.0
        if img.shape[:2] != (sheet.rows, sheet.cols):
            raise ValueError("painting target size != the main sheet's raster")
        d = np.load(os.path.join(base_dir, truth["alpha"]), allow_pickle=False)
        self.rgb, self.alpha = img, d["alpha"].astype(np.float32) / 255.0
        self.lab = srgb_to_lab(img)
        self.mask = self.alpha >= 0.5
        self.area_px = int(self.mask.sum())
        self.n_strokes = int(truth["n_strokes"])
        self.stroke_masks = []
        # optional colour regions of the exemplar (graders only; P/1): int labels 1..R of the picture's palette-colour areas, 0 = none
        self.regions = d["regions"].astype(np.int32) if "regions" in d.files else None
        extra = (d["regions"].astype(np.uint16).tobytes(),) if self.regions is not None else ()
        self.sha = sha16(np.round(img * 255).astype(np.uint8).tobytes(), d["alpha"].tobytes(), *extra)

    def image(self) -> np.ndarray:
        return np.round(self.rgb * 255).astype(np.uint8)


def _ssim(a: np.ndarray, b: np.ndarray, sigma: float) -> float:
    from scipy.ndimage import gaussian_filter as g
    L = 100.0
    C1, C2 = (0.01 * L) ** 2, (0.03 * L) ** 2
    mu_a, mu_b = g(a, sigma), g(b, sigma)
    saa = g(a * a, sigma) - mu_a ** 2; sbb = g(b * b, sigma) - mu_b ** 2; sab = g(a * b, sigma) - mu_a * mu_b
    return float((((2 * mu_a * mu_b + C1) * (2 * sab + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (saa + sbb + C2))).mean())


def score_paint(rgb: np.ndarray, alpha: np.ndarray, target: PaintTarget, strokes: list[dict] | None = None, cfg: dict | None = None) -> dict[str, float]:
    """A painted main sheet vs the painting exemplar, REGISTERED: the canvas is first aligned to the picture by the best global
    translation within the rule's register_mm (register_paint on the blurred CIELAB; translation only; a best shift on the window's
    border -> zero shift); every metric is taken on the overlap of both pictures at that shift (both cropped: no fill colour),
    restricted to the target's central window when the rule sets score_inset_mm (O/4: the near-edge strip is not scored).
    Reports the shift and the main metrics unregistered (zero shift, the same window)."""
    from scipy.ndimage import gaussian_filter
    cfg = cfg or {}
    px_mm = target.sheet.px_m * 1000.0
    R = register_window_px(cfg, px_mm)
    rgb, alpha = np.asarray(rgb, np.float64), np.asarray(alpha)
    b = score_inset_px(cfg, px_mm)

    def at(dy_: int, dx_: int) -> dict[str, float]:
        if (dy_, dx_) == (0, 0) and b == 0:
            return _score_paint_at(rgb, alpha, target, strokes, cfg)
        st, sc, _ = _overlap_slices(rgb.shape, dy_, dx_, b)
        return _score_paint_at(rgb[sc], alpha[sc], _Overlap(target, st), strokes, cfg)

    base = at(0, 0)
    dy = dx = 0; edge = False
    if R > 0:
        sig = float(cfg.get("blur_mm", 1.0)) / px_mm
        dy, dx, edge = register_paint(gaussian_filter(srgb_to_lab(rgb), (sig, sig, 0)), gaussian_filter(target.lab, (sig, sig, 0)), R)
        if edge:
            dy = dx = 0
    m = dict(base) if (dy, dx) == (0, 0) else at(dy, dx)
    m.update(_register_fields(dy, dx, edge, px_mm, R, b))
    for k in ("de_mean", "de_p90", "ssim_L", "edge_corr", "paint_iou"):
        m[f"{k}_unregistered"] = base.get(k, 0.0)
    return m


def _score_paint_at(rgb: np.ndarray, alpha: np.ndarray, target, strokes: list[dict] | None, cfg: dict) -> dict[str, float]:
    """A painted main sheet (display RGB [0, 1], paint coverage) vs the painting exemplar, at the coarse scale where a copy is judged:
    both pictures blurred with sigma = blur_mm; mean / p90 CIELAB colour difference (ΔE*ab, 1976) over the region either has paint
    (dilated by 2 mm), the fraction of that region with ΔE > 10, SSIM of L* (sigma 1.5 mm windows), paint-coverage IoU; stroke count."""
    from scipy import ndimage
    from scipy.ndimage import gaussian_filter
    px_mm = target.sheet.px_m * 1000.0
    sig = float(cfg.get("blur_mm", 1.0)) / px_mm
    A = gaussian_filter(srgb_to_lab(np.asarray(rgb, np.float64)), (sig, sig, 0))
    T = gaussian_filter(target.lab, (sig, sig, 0))
    de = np.sqrt(((A - T) ** 2).sum(-1))
    P = np.asarray(alpha) >= 0.5
    region = ndimage.binary_dilation(P | target.mask, iterations=max(1, int(round(2.0 / px_mm))))
    dr = de[region] if region.any() else np.zeros(1)
    inter = int((P & target.mask).sum()); union = int((P | target.mask).sum())
    # P/1: the coarse scale (sigma coarse_mm: the colour masses), the fine structure (SSIM of L* at sigma fine_mm), the edges
    # (correlation of the L* gradient magnitudes at the judging scale) and the per-region coverage (the fraction of each exemplar
    # colour region within region_de of the exemplar at the judging scale; min and area-weighted mean over the regions)
    sc = float(cfg.get("coarse_mm", 4.0)) / px_mm
    Ac = gaussian_filter(A, (sc, sc, 0)); Tc = gaussian_filter(T, (sc, sc, 0))
    dc = np.sqrt(((Ac - Tc) ** 2).sum(-1))
    sf = float(cfg.get("fine_mm", 0.5)) / px_mm
    Lf_a = gaussian_filter(srgb_to_lab(np.asarray(rgb, np.float64))[..., 0], sf); Lf_t = gaussian_filter(target.lab[..., 0], sf)
    ga = np.hypot(*np.gradient(A[..., 0])); gt = np.hypot(*np.gradient(T[..., 0]))
    ga_r, gt_r = ga[region] - ga[region].mean(), gt[region] - gt[region].mean()
    den = float(np.sqrt((ga_r ** 2).sum() * (gt_r ** 2).sum()))
    extra = {"de_mean_coarse": round(float(dc[region].mean()) if region.any() else 0.0, 4), "ssim_L_fine": round(_ssim(Lf_a, Lf_t, 1.5 / px_mm), 6),
             "edge_corr": round(float((ga_r * gt_r).sum()) / den, 6) if den > 0 else 0.0}
    if getattr(target, "regions", None) is not None:
        lab_ = target.regions.ravel()
        R_ = int(lab_.max())
        n_ = np.bincount(lab_, minlength=R_ + 1)[1:]
        k_ = np.bincount(lab_, weights=(de.ravel() <= float(cfg.get("region_de", 10.0))).astype(np.float64), minlength=R_ + 1)[1:]
        ok_ = n_ > 0
        cov_ = k_[ok_] / n_[ok_]
        extra["region_cov_min"] = round(float(cov_.min()), 6) if cov_.size else 1.0
        extra["region_cov_mean"] = round(float((k_[ok_].sum()) / n_[ok_].sum()), 6) if cov_.size else 1.0
        extra["n_regions"] = float(cov_.size)
    out = {"de_mean": round(float(dr.mean()), 4), "de_p90": round(float(np.percentile(dr, 90)), 4), "de_bad_frac": round(float((dr > 10.0).mean()), 6),
           "de_mean_sheet": round(float(de.mean()), 4), "ssim_L": round(_ssim(A[..., 0], T[..., 0], 1.5 / px_mm), 6),
           "paint_iou": round(inter / union, 6) if union else 0.0, "paint_area_mm2": round(int(P.sum()) * px_mm ** 2, 1),
           "target_paint_area_mm2": round(int(target.mask.sum()) * px_mm ** 2, 1), "n_target_strokes": float(target.n_strokes), **extra}
    if strokes is not None:
        main = [s_ for s_ in strokes if s_["sheet"] == "main" and s_["inked"]]
        out["n_strokes"] = float(len(main))
        out["n_practice_strokes"] = float(sum(1 for s_ in strokes if s_["sheet"] == "practice" and s_["inked"]))
        out["n_dry_strokes"] = float(sum(1 for s_ in strokes if not s_["inked"]))
        cap = int(cfg.get("max_strokes", 10 ** 6))
        out["max_strokes"] = float(cap); out["stroke_count_ok"] = float(len(main) <= cap)
    return out


PAINT_RULE_MAX = ("de_mean_coarse",)                                     # P/1: optional rule terms, checked when the rule names them
PAINT_RULE_MIN = ("ssim_L_fine", "edge_corr", "region_cov_min", "region_cov_mean")


def is_success_paint(m: dict, cfg: dict) -> bool:
    ok = bool(m.get("de_mean", 1e9) <= cfg["de_mean"] and m.get("de_p90", 1e9) <= cfg.get("de_p90", 1e9) and m.get("ssim_L", 0) >= cfg["ssim_L"]
              and m.get("paint_iou", 0) >= cfg["paint_iou"] and m.get("stroke_count_ok", 0) >= 1.0)
    ok = ok and all(m.get(k, 1e9) <= cfg[k] for k in PAINT_RULE_MAX if k in cfg)
    return bool(ok and all(m.get(k, -1e9) >= cfg[k] for k in PAINT_RULE_MIN if k in cfg))


def final_reward_paint(m: dict) -> float:
    """Continuous score in [0, 1]: 1 - mean ΔE / 20 (clipped), scaled down above the stroke budget."""
    v = max(0.0, 1.0 - float(m.get("de_mean", 20.0)) / 20.0)
    n, cap = float(m.get("n_strokes", 0.0)), float(m.get("max_strokes", 1e9))
    return round(v * (min(1.0, cap / n) if n > cap else 1.0), 6)


def load_truth(inst: dict, sheet: Sheet, base_dir: str, picture):
    """The graders' ground truth of a brush task (instance["truth"]; only in tests/, the sim sidecar and the scoring service)."""
    t, kind = inst["truth"], inst["target"]["kind"]
    if kind == "glyph":
        return GlyphTarget(t, sheet)
    if kind == "letters":
        return LetterTarget(t, sheet)
    if kind == "painting":
        return PaintTarget(t, sheet, base_dir, picture)
    raise ValueError(f"unknown target kind {kind!r}")


def score_session(s, strokes: list[dict]) -> dict[str, float]:
    """The grader's metrics of a Session's main sheet (s.truth = the ground truth) + success and final_reward."""
    cfg = s.inst["target"]["success"]
    if s.inst["target"]["kind"] == "painting":
        m = score_paint(s.painter.display("main"), s.painter.display_ink("main"), s.truth, strokes, cfg=cfg)
        m["success"] = float(is_success_paint(m, cfg))
        m["final_reward"] = final_reward_paint(m)
        return m
    m = score_ink(s.painter.display_ink("main"), s.truth, strokes, cfg=cfg)
    m["success"] = float(is_success(m, cfg))
    m["final_reward"] = final_reward(m)
    return m


def nib_sweep_mask(sheet: Sheet, path_xy: np.ndarray, angle_rad: float, nib_w: float, nib_t: float, step: float = 1e-4) -> np.ndarray:
    """The ideal mark of a vertical broad nib at pen angle `angle_rad` (the edge's direction in the writer's view: 0 = along the
    writing line) swept along the world path (N, 2): coverage in [0, 1] on the sheet raster (for the exemplar)."""
    e = np.array([math.sin(angle_rad), -math.cos(angle_rad)])           # writer's (right, up) = world (-y, +x)
    P = path_xy
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    n = max(2, int(math.ceil(d[-1] / step)) + 1)
    s_ = np.linspace(0, d[-1], n)
    Q = np.stack([np.interp(s_, d, P[:, 0]), np.interp(s_, d, P[:, 1])], 1)
    cov = np.zeros((sheet.rows, sheet.cols), np.float32)
    for q in Q:
        a, b = q - e * nib_w / 2, q + e * nib_w / 2
        r = _segment_footprint(sheet, a[0], a[1], b[0], b[1], nib_t)
        if r is None:
            continue
        r0, c0, al = r
        sl = (slice(r0, r0 + al.shape[0]), slice(c0, c0 + al.shape[1]))
        np.maximum(cov[sl], al, out=cov[sl])
    return cov


def pointed_sweep_mask(sheet: Sheet, path_xy: np.ndarray, widths_m: np.ndarray, angle_rad: float, hairline_m: float,
                       step: float = 1e-4) -> np.ndarray:
    """The ideal mark of a vertical pointed pen with its spread axis at `angle_rad` (writer's view, 0 = along the writing line) swept
    along the world path (N, 2) with the mark's width (N,) per point (the tines' spread + the hairline): coverage in [0, 1]."""
    e = np.array([math.sin(angle_rad), -math.cos(angle_rad)])
    P = path_xy
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    n = max(2, int(math.ceil(d[-1] / step)) + 1)
    s_ = np.linspace(0, d[-1], n)
    Q = np.stack([np.interp(s_, d, P[:, 0]), np.interp(s_, d, P[:, 1])], 1)
    Wd = np.interp(s_, d, np.asarray(widths_m, np.float64))
    cov = np.zeros((sheet.rows, sheet.cols), np.float32)
    for q, w in zip(Q, Wd):
        hl = max(0.0, w - hairline_m) / 2
        a, b = q - e * hl, q + e * hl
        r = _capsule_footprint(sheet, a[0], a[1], b[0], b[1], hairline_m)
        if r is None:
            continue
        r0, c0, al = r
        sl = (slice(r0, r0 + al.shape[0]), slice(c0, c0 + al.shape[1]))
        np.maximum(cov[sl], al, out=cov[sl])
    return cov


class LetterTarget(GlyphTarget):
    """An exemplar written with a broad nib or a pointed pen: per-stroke pen paths (paper mm polylines) swept by the ideal vertical
    pen at the stroke's pen angle (target.strokes = [{"points_mm": [[X, Y], ...], "angle_deg": a (+ "widths_mm": [w, ...] for a
    pointed pen)}], the pen from target.nib). Masks = coverage >= 0.5."""
    def __init__(self, tgt: dict, sheet: Sheet):
        self.d, self.sheet, self.polys_px = tgt, sheet, None
        nib = tgt["nib"]
        self.covs = []
        for st in tgt["strokes"]:
            P = np.asarray(st["points_mm"], np.float64)
            x, y = sheet.mm_to_world(P[:, 0], P[:, 1])
            if nib.get("kind") == "pointed":
                self.covs.append(pointed_sweep_mask(sheet, np.stack([x, y], 1), np.asarray(st["widths_mm"], np.float64) / 1000.0,
                                                    math.radians(st["angle_deg"]), nib["hairline_m"]))
            else:
                self.covs.append(nib_sweep_mask(sheet, np.stack([x, y], 1), math.radians(st["angle_deg"]), nib["width_m"], nib["thick_m"]))
        self.stroke_masks = [c >= 0.5 for c in self.covs]
        self.n_strokes = len(self.stroke_masks)
        self.mask = np.any(self.stroke_masks, axis=0)
        self.area_px = int(self.mask.sum())
        self.sha = sha16(np.packbits(np.stack(self.stroke_masks)).tobytes(), json.dumps(tgt["box_mm"]).encode())

    def coverage(self) -> np.ndarray:
        c = np.zeros((self.sheet.rows, self.sheet.cols), np.float32)
        for cv in self.covs:
            np.maximum(c, cv, out=c)
        return c


MMAH_COMMIT = "bddc96d41bef78427ed0e034e9f7e31d71fd1b92"
APL_NOTICE = ("The exemplar's stroke outlines are Make Me a Hanzi's graphics.txt entry for this character (github.com/skishore/makemeahanzi "
              f"@ {MMAH_COMMIT[:7]}; graphics.txt is derived from the fonts AR PL KaitiM GB and AR PL UKai) and are distributed under the "
              "Arphic Public License (ARPHICPL.TXT next to this file). Modification notice (APL section 2a): 2026-09-28, robot-coding-bench "
              "(RoboPaint) copied the outlines unmodified and added only their placement on the paper (box_mm); the picture made from them "
              "(target.png) is a rendering of the same outlines.")
PICTURE_NOTICE = ("This picture renders glyph outlines derived from the fonts AR PL KaitiM GB and AR PL UKai (Arphic Technology), distributed "
                  "under the Arphic Public License (ARPHICPL.TXT); changed 2026-09-28 by robot-coding-bench (placed on the sheet, rendered).")


def build_instance(spec: dict) -> dict:
    medium = spec["medium"]
    inst = {"task": spec["task"], "family": spec["task"], "medium": medium, "sheets": default_sheets(),
            "robot_qpos": list(REST_QPOS), "robot_base": list(ROBOT_BASE), "control_hz": CONTROL_HZ, "sim_hz": SIM_HZ, "max_steps": MAX_STEPS}
    if medium == "calligraphy":
        inst["brush"] = dict(BRUSH_WANG)
        inst["wells"] = build_wells([("ink", "#131214")], 0.020, rule="a tip inside the ink stone's circle and below the ink surface loads ink "
                                    "and restores the brush (its hairs are gathered back to a point); the brush starts dry")
        t = spec["target"]
        chars = t.get("characters") or t["character"]              # a work: several characters, each in its own box
        recs = {}
        for line in open(t["graphics"], encoding="utf-8"):
            d = json.loads(line)
            if d["character"] in chars:
                recs[d["character"]] = d
        missing = [c for c in chars if c not in recs]
        if missing:
            raise SystemExit(f"{missing!r} not in {t['graphics']}")
        n = sum(len(recs[c]["strokes"]) for c in chars)
        succ = dict(t["success"]); succ.setdefault("max_strokes", n + int(t.get("stroke_slack", 0)))
        inst["target"] = {"kind": "glyph", "image": "target.png", "success": succ}
        src = {"source": f"Make Me a Hanzi graphics.txt @ {MMAH_COMMIT[:7]} (AR PL KaitiM GB / AR PL UKai)", "license": "Arphic Public License",
               "notice": APL_NOTICE, "tol_mm": TOL_MM}
        if len(chars) == 1 and not t.get("characters"):
            inst["truth"] = {"character": chars, "box_mm": [float(v) for v in t["box_mm"]], "strokes": recs[chars]["strokes"], "n_strokes": n, **src}
        else:
            boxes = t["boxes"]
            if len(boxes) != len(chars):
                raise SystemExit("a work needs one box per character")
            inst["truth"] = {"characters": chars, "glyphs": [{"character": c, "box_mm": [float(v) for v in bx], "n_strokes": len(recs[c]["strokes"])}
                                                             for c, bx in zip(chars, boxes)],
                             "strokes": [st for c in chars for st in recs[c]["strokes"]], "n_strokes": n, **src}
    elif medium == "broad_nib":
        inst["brush"] = dict(BRUSH_NIB)
        inst["wells"] = build_wells([("ink", "#131214")], 0.020, rule="a tip inside the ink well's circle and below the ink surface loads "
                                    "ink (a steel nib has no other state); the pen starts dry")
        t = spec["target"]
        succ = dict(t["success"]); succ.setdefault("max_strokes", len(t["strokes"]) + int(t.get("stroke_slack", 0)))
        inst["target"] = {"kind": "letters", "image": "target.png", "success": succ}
        inst["truth"] = {"word": t["word"], "hand": t["hand"], "box_mm": [float(v) for v in t["box_mm"]],
                         "nib": {"width_m": inst["brush"]["nib_width_m"], "thick_m": inst["brush"]["nib_thick_m"]},
                         "strokes": t["strokes"], "n_strokes": len(t["strokes"]), "source": "letter skeletons authored for this benchmark",
                         "license": "CC0-1.0", "tol_mm": TOL_MM}
    elif medium == "pointed_pen":
        inst["brush"] = dict(BRUSH_POINTED)
        inst["wells"] = build_wells([("ink", "#131214")], 0.020, rule="a tip inside the ink well's circle and below the ink surface loads "
                                    "ink (a steel point has no other state); the pen starts dry")
        t = spec["target"]
        succ = dict(t["success"]); succ.setdefault("max_strokes", len(t["strokes"]) + int(t.get("stroke_slack", 0)))
        inst["target"] = {"kind": "letters", "image": "target.png", "success": succ}
        inst["truth"] = {"word": t["word"], "hand": t["hand"], "box_mm": [float(v) for v in t["box_mm"]],
                         "nib": {"kind": "pointed", "hairline_m": inst["brush"]["hairline_m"], "max_width_m": inst["brush"]["max_width_m"]},
                         "strokes": t["strokes"], "n_strokes": len(t["strokes"]), "source": "letter skeletons authored for this benchmark",
                         "license": "CC0-1.0", "tol_mm": TOL_MM}
    elif medium == "mypaint":
        b = dict(BRUSH_MYPAINT); b.update(spec.get("brush", {}))
        if "preset_json" not in b:
            b["preset_json"] = open(os.path.join(spec.get("brushes_dir", MYPAINT_BRUSHES), b["preset"] + ".myb")).read()
        inst["brush"] = b
        pal = spec["palette"]                                            # [[name, hex], ...]: every colour the painting needs, premixed
        lay = spec.get("wells_layout", {})                               # P/1: larger palettes (defaults = the 7-well prototypes)
        rows = int(lay.get("rows", 2 if len(pal) > 5 else 1))
        inst["wells"] = build_wells([tuple(w) for w in pal], float(lay.get("radius_m", 0.012)), plate_center=tuple(lay.get("plate_center", (-0.10, 0.160))),
                                    spacing=float(lay.get("spacing_m", 0.030)), rows=rows, plate_half=tuple(lay.get("plate_half", (0.075, 0.035, 0.003))),
                                    rule="a tip inside a well's circle and below the paint surface loads that paint on a fresh brush (the "
                                         "previous paint is gone: no mixing on the palette, no depletion); the brush starts dry")
        t = spec["target"]
        succ = dict(t["success"]); succ.setdefault("max_strokes", int(math.ceil(t["n_strokes"] * float(t.get("stroke_budget_factor", 1.5)))))
        inst["target"] = {"kind": "painting", "image": "target.png", "success": succ}
        inst["truth"] = {"name": t["name"], "alpha": "truth_alpha.npz", "n_strokes": int(t["n_strokes"]),
                         "source": t.get("source", "painted by a hidden stroke program (solution/) with this instance's robot and brush"),
                         "license": t.get("license", "CC0-1.0")}
        for k in ("reference", "notes"):                                  # P/1: e.g. the public-domain source image's record
            if k in t:
                inst["truth"][k] = t[k]
    else:
        raise SystemExit(f"medium {medium!r} not implemented yet")
    return inst


def _versions() -> dict:
    v = R._versions()
    for mod in ("matplotlib", "svgpathtools"):
        try:
            m = __import__(mod); v[mod] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001
            v[mod] = None
    return v


def render_picture(inst: dict, sheet: Sheet) -> np.ndarray:
    """target.png of a mask target (glyph / letters): the exemplar's anti-aliased coverage in ink on the paper colour."""
    t = GlyphTarget(inst["truth"], sheet) if inst["target"]["kind"] == "glyph" else LetterTarget(inst["truth"], sheet)
    return t.image()


def cmd_make_instance(a) -> None:
    """The graders' frozen instance + (mask targets) target.png next to it; a painting's target.png + truth_alpha.npz must exist there
    already (the generator paints them). The picture's pixels enter instance_sha."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    inst = build_instance(json.load(open(a.spec)))
    sheets = sheets_from_inst(inst)
    if inst["target"]["kind"] in ("glyph", "letters"):
        meta = PngInfo()
        if inst["target"]["kind"] == "glyph":
            meta.add_text("Comment", PICTURE_NOTICE)
        Image.fromarray(render_picture(inst, sheets["main"])).save(out.parent / "target.png", pnginfo=meta)
    s = Session(inst=inst, render=False, base_dir=str(out.parent))
    inst["instance_sha"] = s.instance_sha
    inst["target"]["truth_sha"] = s.truth.sha
    inst["truth"]["area_mm2"] = round(s.truth.area_px * (s.geo.px_m * 1000) ** 2, 1)
    inst["versions"] = _versions()
    json.dump(inst, open(out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"instance_sha": s.instance_sha, "truth_sha": s.truth.sha, "area_mm2": inst["truth"]["area_mm2"], "out": str(out)}))
    s.close()


AGENT_TARGET_KEYS = ("kind", "image", "success")


def agent_copy(full: dict) -> dict:
    """The agent's copy: the scene (sheets, wells, brush, robot), the rule (target.success incl. the stroke cap) and the picture's
    file name; nothing derived from the target."""
    agent = {k: v for k, v in full.items() if k != "truth"}
    agent["target"] = {k: full["target"][k] for k in AGENT_TARGET_KEYS}
    agent["versions"] = {k: v for k, v in full.get("versions", {}).items() if k not in ("svgpathtools", "matplotlib")}
    return agent


def cmd_make_agent_instance(a) -> None:
    """out-dir/instance.json (the agent's copy) + out-dir/target.png; checked: the same instance_sha, and no truth in the copy."""
    full = json.load(open(a.instance))
    src = Path(a.instance).parent
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    json.dump(agent_copy(full), open(out / "instance.json", "w"), indent=1, ensure_ascii=False)
    if (src / "target.png").resolve() != (out / "target.png").resolve():
        shutil.copy(src / "target.png", out / "target.png")
    s = Session(instance=str(out / "instance.json"), render=False)
    ok = s.instance_sha == full.get("instance_sha") and s.instance_exact and s.truth is None
    print(json.dumps({"agent_instance": str(out / "instance.json"), "instance_sha": s.instance_sha, "instance_exact": s.instance_exact,
                      "no_truth": s.truth is None, "ok": ok}))
    s.close()
    if not ok:
        sys.exit(1)


def cmd_score(a) -> None:
    """Score a picture of the main sheet (canvas.png, as written by replay --canvas-out); mask targets: the ink coverage is recovered
    from the colour."""
    from PIL import Image
    inst = json.load(open(a.instance))
    sheets = sheets_from_inst(inst)
    base = os.path.dirname(os.path.abspath(a.instance))
    tgt = load_truth(inst, sheets["main"], base, R.TargetPicture(os.path.join(base, inst["target"]["image"])))
    img = np.asarray(Image.open(a.canvas).convert("RGB"), np.float64) / 255.0
    paper, ink = np.asarray(PAPER_RGB), np.asarray(INK_RGB)
    cov = np.clip(((paper - img) * (paper - ink)).sum(-1) / ((paper - ink) ** 2).sum(), 0.0, 1.0).astype(np.float32)
    print(json.dumps(score_ink(cov, tgt, None, cfg=inst["target"]["success"])))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--spec", required=True); q.add_argument("--out", required=True)
    q = sub.add_parser("make-agent-instance"); q.add_argument("--instance", required=True); q.add_argument("--out-dir", required=True)
    q = sub.add_parser("score"); q.add_argument("--instance", required=True); q.add_argument("--canvas", required=True)
    a = p.parse_args()
    {"make-instance": cmd_make_instance, "make-agent-instance": cmd_make_agent_instance, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
