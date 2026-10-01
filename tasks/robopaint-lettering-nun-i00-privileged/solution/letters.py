"""RoboPaint lettering exemplars: letter skeletons authored for this benchmark (CC0-1.0; graders + generation time only, never in the
agent's container). A letter = {"adv": advance, "strokes": [stroke, ...]}; a stroke = a list of control points, sampled as a
Catmull-Rom curve of the pen's path (broad nib: the middle of the edge; pointed pen: the point), where the string "|" starts a new
piece at the previous point (a sharp corner or a retrace cusp: the curve is not smoothed through it) and "poly" strokes
(textura) are straight segments between their points.

Hands (units: broad nib = nib widths, pointed pen = x-heights; origin = the letter's left end on the baseline, y up):
- italic (pen angle 35 deg, x-height 5, 5 deg slant): i, n, m (the M2 prototypes), u, p (descender to -3);
- foundational (30 deg, x-height 4, upright): o, n, m, u (M2), i;
- uncial (25 deg, a flattish pen, x-height 4, round and wide): d, o, n, u, m;
- textura (30 deg, x-height ~5, upright, poly strokes): minims with diamond heads and feet, hairline shoulders: i, n, m, u;
- copperplate (pointed flexible pen, x-height 1 = x_height_mm, 55 deg slant; every point carries the mark's width in mm:
  hairlines 0.4, full shades 2.0): i, n, m, u, joined by hairline connectors (exit of one letter = entry of the next).
word_strokes(word, hand, unit_mm, origin_mm) lays a word (a space = a word space) out left to right in paper millimetres; layout(word,
hand) places it on the main sheet (the generator's placement)."""
from __future__ import annotations
import math
import numpy as np

H, S, M = 0.4, 2.0, 1.1                     # copperplate widths (mm): hairline, full shade, half shade

# ---- copperplate elements (unsheared x-height units; the slant shear is applied by word_strokes)
def _cp_entry():
    return [(-0.45, 0.5, H), (-0.2, 0.74, H), (0.0, 1.0, H)]


def _cp_stem_turn(x: float, exit_to: float | None = 0.8):
    """A shaded downstroke from the x-height with an underturn at the baseline and a hairline exit up to (x + exit_to, 0.5)."""
    pts = [(x, 1.0, H), (x, 0.88, 0.9), (x, 0.74, S), (x, 0.36, S), (x + 0.03, 0.18, 1.3), (x + 0.11, 0.05, 0.6), (x + 0.26, 0.0, H),
           (x + 0.43, 0.09, H)]
    if exit_to is not None:
        pts += [(x + 0.62, 0.3, H), (x + exit_to, 0.5, H)]
    return pts


def _cp_stem_square(x: float):
    """A shaded downstroke from the x-height, square at the baseline (the pen lifts there)."""
    return [(x, 1.0, H), (x, 0.88, 0.9), (x, 0.74, S), (x, 0.2, S), (x, 0.02, S)]


def _cp_branch(x0: float, x1: float):
    """Hairline up the previous stem from the baseline, branching into an arch over to the next stem at x1 (downstroke begins)."""
    return [(x0, 0.03, H), (x0, 0.3, H), (x0 + 0.03, 0.6, H), (x0 + 0.14, 0.87, H), (x0 + 0.36, 1.0, H), (x1 - 0.14, 0.94, H),
            (x1 - 0.02, 0.8, 1.0), (x1, 0.64, S)]


def _cp_letters():
    d = 0.72                                  # stem spacing (x-heights)
    L = {}
    L["i"] = {"adv": 0.8 + 0.45, "strokes": [_cp_entry() + ["|"] + _cp_stem_turn(0.0),
                                             [(0.06, 1.42, 0.9), (0.04, 1.36, S), (0.02, 1.3, 0.9)]]}
    L["u"] = {"adv": d + 0.8 + 0.45, "strokes": [_cp_entry() + ["|"] + _cp_stem_turn(0.0, None) + [(0.6, 0.45, H), (d, 1.0, H)] + ["|"]
                                                 + _cp_stem_turn(d)]}
    L["n"] = {"adv": d + 0.8 + 0.45, "strokes": [_cp_entry() + ["|"] + _cp_stem_square(0.0),
                                                 _cp_branch(0.0, d) + _cp_stem_turn(d)[3:]]}
    L["m"] = {"adv": 2 * d + 0.8 + 0.45, "strokes": [_cp_entry() + ["|"] + _cp_stem_square(0.0),
                                                     _cp_branch(0.0, d) + _cp_stem_square(d)[3:],
                                                     _cp_branch(d, 2 * d) + _cp_stem_turn(2 * d)[3:]]}
    return L


# ---- textura minims (poly strokes; nib widths)
def _tx_minim(x: float, head: bool = True, foot: bool = True):
    pts = [(x - 0.34, 4.95), (x, 4.46)] if head else [(x, 4.46)]
    pts += [(x, 0.55)]
    if foot:
        pts += [(x + 0.34, 0.06)]
    return pts


def _tx_letters():
    sp = 1.6
    L = {}
    L["i"] = {"adv": 0.84, "strokes": [{"poly": _tx_minim(0.5)}, {"poly": [(0.3, 6.35), (0.64, 5.86)]}]}
    L["n"] = {"adv": 0.84 + sp, "strokes": [{"poly": _tx_minim(0.5)}, {"poly": [(0.55, 4.3)] + _tx_minim(0.5 + sp)}]}
    L["m"] = {"adv": 0.84 + 2 * sp, "strokes": [{"poly": _tx_minim(0.5)}, {"poly": [(0.55, 4.3)] + _tx_minim(0.5 + sp)},
                                                {"poly": [(0.55 + sp, 4.3)] + _tx_minim(0.5 + 2 * sp)}]}
    L["u"] = {"adv": 0.84 + sp, "strokes": [{"poly": _tx_minim(0.5) + [(0.45 + sp, 0.7)]}, {"poly": _tx_minim(0.5 + sp)}]}
    return L


HANDS = {
    # rules under the common registration (tooling snapshot 21; request L/6): calibrated on the robot, see requests/L/6_registration
    "italic": {"pen": "broad", "angle_deg": 35.0, "slant_deg": 5.0, "gap": 0.7, "space": 3.2, "success": {"iou": 0.86, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0},
               "letters": {
                   "i": {"adv": 1.5, "strokes": [[(0.0, 4.55), (0.35, 4.85), (0.55, 5.0), (0.55, 3.0), (0.55, 0.9), (0.62, 0.3), (0.95, 0.02), (1.45, 0.35)],
                                                 [(0.55, 6.45), (0.68, 6.65), (0.80, 6.85)]]},
                   "n": {"adv": 3.55, "strokes": [[(0.0, 4.55), (0.35, 4.85), (0.55, 5.0), (0.55, 2.5), (0.55, 0.0), (0.55, 1.6), (0.62, 3.2),
                                                   (0.95, 4.35), (1.55, 4.95), (2.25, 4.75), (2.55, 3.9), (2.55, 2.0), (2.55, 0.9), (2.62, 0.3),
                                                   (2.95, 0.02), (3.45, 0.35)]]},
                   "m": {"adv": 5.6, "strokes": [[(0.0, 4.55), (0.35, 4.85), (0.55, 5.0), (0.55, 2.5), (0.55, 0.0), (0.55, 1.6), (0.62, 3.2),
                                                  (0.95, 4.35), (1.5, 4.95), (2.2, 4.75), (2.5, 3.9), (2.5, 2.0), (2.5, 0.0), (2.5, 1.6), (2.57, 3.2),
                                                  (2.9, 4.35), (3.45, 4.95), (4.15, 4.75), (4.45, 3.9), (4.45, 2.0), (4.45, 0.9), (4.52, 0.3),
                                                  (4.85, 0.02), (5.35, 0.35)]]},
                   "p": {"adv": 3.1, "strokes": [[(0.0, 4.55), (0.35, 4.85), (0.55, 5.0), (0.55, 2.0), (0.55, -1.0), (0.55, -3.0)],
                                                 [(0.6, 3.3), (0.95, 4.4), (1.55, 4.97), (2.25, 4.75), (2.6, 3.8), (2.55, 2.0), (2.2, 0.6), (1.55, 0.02),
                                                  (0.95, 0.12), (0.6, 0.5)]]},
                   "u": {"adv": 3.55, "strokes": [[(0.0, 4.55), (0.35, 4.85), (0.55, 5.0), (0.55, 2.6), (0.6, 1.1), (0.85, 0.3), (1.35, 0.0),
                                                   (1.95, 0.25), (2.38, 1.0), (2.55, 2.4)],
                                                  [(2.55, 5.0), (2.55, 3.0), (2.55, 0.9), (2.62, 0.3), (2.95, 0.02), (3.45, 0.35)]]},
               }},
    "foundational": {"pen": "broad", "angle_deg": 30.0, "slant_deg": 0.0, "gap": 0.8, "space": 3.0, "success": {"iou": 0.85, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0},
                     "letters": {
                         "o": {"adv": 4.4, "strokes": [[(2.3, 4.0), (1.2, 3.75), (0.35, 2.9), (0.2, 2.0), (0.4, 1.0), (1.2, 0.2), (2.1, 0.0)],
                                                       [(2.0, 4.0), (3.0, 3.8), (3.85, 3.0), (4.1, 2.0), (3.9, 1.0), (3.1, 0.2), (2.0, 0.0)]]},
                         "n": {"adv": 3.9, "strokes": [[(0.0, 3.6), (0.4, 3.9), (0.6, 4.0), (0.6, 2.0), (0.6, 0.0)],
                                                       [(0.6, 2.9), (1.1, 3.75), (1.9, 4.05), (2.75, 3.75), (3.1, 2.9), (3.1, 1.5), (3.1, 0.0)]]},
                         "m": {"adv": 6.0, "strokes": [[(0.0, 3.6), (0.4, 3.9), (0.6, 4.0), (0.6, 2.0), (0.6, 0.0)],
                                                       [(0.6, 2.9), (1.05, 3.75), (1.75, 4.05), (2.5, 3.75), (2.85, 2.9), (2.85, 1.5), (2.85, 0.0)],
                                                       [(2.85, 2.9), (3.3, 3.75), (4.0, 4.05), (4.75, 3.75), (5.1, 2.9), (5.1, 1.5), (5.1, 0.0)]]},
                         "u": {"adv": 3.9, "strokes": [[(0.0, 3.8), (0.3, 4.0), (0.6, 4.0), (0.6, 1.4), (0.85, 0.45), (1.6, 0.0), (2.5, 0.2), (3.1, 1.0)],
                                                       [(3.1, 4.0), (3.1, 2.0), (3.1, 0.3), (3.3, 0.0), (3.7, 0.15)]]},
                         "i": {"adv": 1.2, "strokes": [[(0.0, 3.6), (0.4, 3.9), (0.6, 4.0), (0.6, 2.0), (0.6, 0.0)],
                                                       [(0.48, 5.05), (0.6, 5.25), (0.72, 5.45)]]},
                     }},
    "uncial": {"pen": "broad", "angle_deg": 25.0, "slant_deg": 0.0, "gap": 0.75, "space": 3.0, "success": {"iou": 0.86, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0},
               "letters": {
                   "o": {"adv": 4.8, "strokes": [[(2.5, 4.0), (1.25, 3.8), (0.35, 3.0), (0.15, 2.0), (0.4, 0.95), (1.3, 0.15), (2.4, 0.0)],
                                                 [(2.2, 4.0), (3.4, 3.8), (4.35, 3.0), (4.6, 2.0), (4.35, 0.95), (3.45, 0.15), (2.3, 0.0)]]},
                   "n": {"adv": 4.0, "strokes": [[(0.2, 3.75), (0.5, 4.0), (0.7, 3.9), (0.7, 2.0), (0.7, 0.0)],
                                                 [(0.75, 3.85), (1.6, 2.7), (2.5, 1.4), (3.3, 0.15)],
                                                 [(3.3, 4.05), (3.35, 2.0), (3.3, 0.1)]]},
                   "u": {"adv": 4.1, "strokes": [[(0.2, 3.75), (0.5, 4.0), (0.7, 3.9), (0.7, 1.8), (0.95, 0.7), (1.6, 0.1), (2.4, 0.05), (3.05, 0.5), (3.4, 1.4)],
                                                 [(3.4, 4.0), (3.4, 2.0), (3.4, 0.3), (3.6, 0.0), (3.95, 0.15)]]},
                   "m": {"adv": 5.2, "strokes": [[(1.5, 3.85), (0.75, 3.4), (0.35, 2.4), (0.3, 1.2), (0.55, 0.0)],
                                                 [(0.75, 3.3), (1.3, 3.9), (2.0, 4.0), (2.55, 3.5), (2.7, 2.4), (2.7, 1.2), (2.65, 0.0)],
                                                 [(2.7, 3.3), (3.3, 3.9), (4.05, 4.0), (4.65, 3.4), (4.9, 2.3), (4.75, 1.0), (4.2, 0.0)]]},
                   "d": {"adv": 4.4, "strokes": [[(2.9, 3.8), (1.7, 3.95), (0.7, 3.35), (0.25, 2.2), (0.4, 1.0), (1.1, 0.2), (2.1, 0.0), (3.0, 0.25), (3.6, 0.9)],
                                                 [(0.6, 5.9), (1.6, 6.3), (2.8, 6.0), (3.6, 5.0), (3.9, 3.6), (3.9, 2.0), (3.75, 0.6), (3.5, 0.0)]]},
               }},
    "textura": {"pen": "broad", "angle_deg": 30.0, "slant_deg": 0.0, "gap": 0.76, "space": 3.0, "letters": _tx_letters(), "success": {"iou": 0.87, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0}},
    # copperplate: its own rule (robot study, NOTES of the lettering family): the ink is mostly 0.4 mm hairlines, so a ~0.2 mm tracking
    # error costs the oracle ~0.25 of IoU; the threshold sits between the oracle and every constant-pressure baseline
    "copperplate": {"pen": "pointed", "angle_deg": -35.0, "slant_deg": 35.0, "gap": 0.0, "space": 1.0, "unit_mm": 11.0, "letters": _cp_letters(),
                    "success": {"iou": 0.70, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0}},
}


def catmull_rom(P: np.ndarray, n_per: int = 20) -> np.ndarray:
    P = np.asarray(P, np.float64)
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


def polyline(P: np.ndarray, step: float = 0.05) -> np.ndarray:
    P = np.asarray(P, np.float64)
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b[:2] - a[:2]) / step)))
        out.append(a + (b - a) * (np.arange(1, n + 1) / n)[:, None])
    return np.vstack(out)


def sample_stroke(st) -> np.ndarray:
    """A stroke's control points -> the sampled pen path (N, 2 or 3 with the width)."""
    if isinstance(st, dict):
        return polyline(np.asarray(st["poly"], np.float64))
    pieces, cur = [], []
    for p in st:
        if isinstance(p, str):
            pieces.append(cur); cur = [cur[-1]]
        elif not cur or tuple(p) != tuple(cur[-1]):
            cur.append(p)
    pieces.append(cur)
    out = []
    for k, pc in enumerate(pieces):
        c = catmull_rom(np.asarray(pc, np.float64), 20)
        out.append(c if k == 0 else c[1:])
    return np.vstack(out)


def word_strokes(word: str, hand: str, unit_mm: float, origin_mm: tuple[float, float]) -> tuple[list[dict], dict]:
    """-> (strokes [{"points_mm": [[X, Y], ...], "angle_deg": a, "letter": c (+ "widths_mm")}], layout) in paper mm (X right, Y
    down), the baseline starting at origin_mm. unit_mm = the nib width (broad) or the x-height (pointed)."""
    Hd = HANDS[hand]
    sl = math.tan(math.radians(Hd["slant_deg"]))
    x0, yb = origin_mm
    out = []
    xc = 0.0
    xmin, xmax = 1e9, -1e9
    for ch in word:
        if ch == " ":
            xc += Hd["space"]; continue
        L = Hd["letters"][ch]
        for st in L["strokes"]:
            P = sample_stroke(st)
            X = x0 + (xc + P[:, 0] + P[:, 1] * sl) * unit_mm
            Y = yb - P[:, 1] * unit_mm
            xmin, xmax = min(xmin, X.min()), max(xmax, X.max())
            rec = {"points_mm": np.round(np.stack([X, Y], 1), 4).tolist(), "angle_deg": Hd["angle_deg"], "letter": ch}
            if Hd["pen"] == "pointed":                          # the pen's range: the spline may overshoot the control widths
                rec["widths_mm"] = np.round(np.clip(P[:, 2], H, S), 4).tolist()
            out.append(rec)
        xc += L["adv"] + Hd["gap"]
    return out, {"width_mm": round((xc - Hd["gap"]) * unit_mm, 2), "ink_x_mm": [round(float(xmin), 3), round(float(xmax), 3)], "hand": hand,
                 "pen": Hd["pen"], "angle_deg": Hd["angle_deg"], "unit_mm": unit_mm}


def layout(word: str, hand: str, sheet_mm: float = 227.1845, nib_mm: float = 4.0):
    """The word on the main sheet (the generator's placement): advance width centred, baseline 10 mm below the sheet's centre; unit =
    the broad nib's width or the pointed hand's x-height. -> (strokes, layout, box_mm = [X0, baseline Y, advance width])."""
    unit = float(HANDS[hand].get("unit_mm", nib_mm))
    _, lay = word_strokes(word, hand, unit, (0.0, 0.0))
    X0 = (sheet_mm - lay["width_mm"]) / 2; yb = sheet_mm / 2 + 10.0
    strokes, lay = word_strokes(word, hand, unit, (X0, yb))
    return strokes, lay, [X0, yb, lay["width_mm"]]
