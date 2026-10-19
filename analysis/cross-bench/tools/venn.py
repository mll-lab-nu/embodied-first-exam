"""Area-proportional three-set Venn layout (fig:venn; figs.fig_venn draws it).

layout() takes each set's size and each pair's intersection and returns circles whose areas are the sizes (r ∝ sqrt(k))
placed so that each pairwise overlap (the circle–circle lens) has the pair's area: the A–B, A–C and B–C distances come
from bisection on the lens area, then A, B, C go on the triangle those three distances make (A left, B right, C below;
clamped to a line when the three distances admit no triangle). The triple region is what that placement gives, so it
is approximate. Each region's number sits in a small pill: at the sample point inside the region where the pill fits
and that lies deepest (farthest from any circle edge, pulled a little toward the region's centroid); a region too small
for its pill gets one just outside the circles with a short leader line. Set labels (a dot in the agent's colour, then
name + k/n) sit just outside their circle, on the side away from the others. Units: the diagram is scaled to fit `fit` (width, height); text sizes are in the same units.
"""
from __future__ import annotations
import math

NUM_FONT, NAME_FONT = 12.0, 11.0                       # region numbers / set labels (viewBox units)
PILL_PX, PILL_H = 5.0, 17.0                            # number pill: side padding, height (app.js draws it the same)
DOT_W = 10.0                                           # the colour dot before a set label, with its gap (app.js)


def lens(r1: float, r2: float, d: float) -> float:
    """Area of the intersection of two circles with radii r1, r2 and centre distance d."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a1 = r1 * r1 * math.acos(max(-1.0, min(1.0, (d * d + r1 * r1 - r2 * r2) / (2 * d * r1))))
    a2 = r2 * r2 * math.acos(max(-1.0, min(1.0, (d * d + r2 * r2 - r1 * r1) / (2 * d * r2))))
    return a1 + a2 - 0.5 * math.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)))


def distance(r1: float, r2: float, area: float) -> float:
    """The centre distance at which two circles overlap by `area` (bisection; lens area falls as d grows). No overlap:
    apart with a small gap; full containment: internally tangent."""
    lo, hi = abs(r1 - r2), r1 + r2
    if area <= 0:
        return hi + 0.08 * (r1 + r2)
    if area >= math.pi * min(r1, r2) ** 2:
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if lens(r1, r2, mid) > area else (lo, mid)
    return (lo + hi) / 2


def _text_w(s: str, size: float) -> float:
    return sum(size * (1.0 if ord(ch) > 0x2e80 else 0.62) for ch in s)


class Box:
    def __init__(self, cx, cy, w, h):
        self.cx, self.cy, self.w, self.h = cx, cy, w, h

    def points(self, pad=0.0):
        hw, hh = self.w / 2 + pad, self.h / 2 + pad
        return [(self.cx + i * hw, self.cy + j * hh) for i in (-1, 0, 1) for j in (-1, 0, 1)]

    def hits(self, o, gap=2.0) -> bool:
        return abs(self.cx - o.cx) * 2 < self.w + o.w + 2 * gap and abs(self.cy - o.cy) * 2 < self.h + o.h + 2 * gap

    def edges(self):
        return self.cx - self.w / 2, self.cy - self.h / 2, self.cx + self.w / 2, self.cy + self.h / 2


def layout(keys: list[str], size: dict, pair: dict, regions: dict, names: dict, fit=(220.0, 190.0)) -> dict:
    """keys: the three set keys (A, B, C); size: key -> count; pair: frozenset({a, b}) -> |a ∩ b| (triple included);
    regions: frozenset of member keys -> count (the seven exclusive regions); names: key -> set label text.
    Returns {"circles": {key: (x, y, r)}, "labels": {key: (x, y, anchor)}, "spots": {region: spot}, "bbox": (x0, y0, x1, y1)}
    with spot = {"x", "y", "inside": bool, "ax", "ay"} (ax, ay: where an outside label's leader line starts) or None
    when the region is empty and has no area."""
    a, b, c = keys
    r = {k: math.sqrt(max(size[k], 0.4) / math.pi) for k in keys}
    d = {frozenset(p): distance(r[p[0]], r[p[1]], pair[frozenset(p)]) for p in ((a, b), (a, c), (b, c))}
    dab, dac, dbc = d[frozenset((a, b))], d[frozenset((a, c))], d[frozenset((b, c))]
    if dab < 1e-9:
        ctr = {a: (0.0, 0.0), b: (0.0, 0.0), c: (0.0, dac)}
    else:
        x = (dac * dac - dbc * dbc + dab * dab) / (2 * dab)
        ctr = {a: (0.0, 0.0), b: (dab, 0.0), c: (x, math.sqrt(max(0.0, dac * dac - x * x)))}
    x0 = min(ctr[k][0] - r[k] for k in keys); x1 = max(ctr[k][0] + r[k] for k in keys)
    y0 = min(ctr[k][1] - r[k] for k in keys); y1 = max(ctr[k][1] + r[k] for k in keys)
    s = min(fit[0] / (x1 - x0), fit[1] / (y1 - y0))
    circ = {k: ((ctr[k][0] - x0) * s, (ctr[k][1] - y0) * s, r[k] * s) for k in keys}
    W, H = (x1 - x0) * s, (y1 - y0) * s

    def member(x, y):
        return frozenset(k for k in keys if (x - circ[k][0]) ** 2 + (y - circ[k][1]) ** 2 < circ[k][2] ** 2)

    step = max(W, H) / 200
    pts = {}
    for i in range(int(W / step) + 1):
        for j in range(int(H / step) + 1):
            p = (i * step, j * step)
            m = member(*p)
            if m:
                pts.setdefault(m, []).append(p)
    wsum = sum(circ[k][2] ** 2 for k in keys)
    ux = sum(circ[k][0] * circ[k][2] ** 2 for k in keys) / wsum
    uy = sum(circ[k][1] * circ[k][2] ** 2 for k in keys) / wsum

    # set labels: just outside each circle, away from the union's centre, clear of the other circles and labels
    placed, labels = [], {}
    for k in keys:
        cx, cy, rr = circ[k]
        base = math.atan2(cy - uy, cx - ux) if math.hypot(cx - ux, cy - uy) > 0.15 * rr else {a: -2.4, b: -0.75, c: math.pi / 2}[k]
        w, h = _text_w(names[k], NAME_FONT) + DOT_W, NAME_FONT * 1.3
        best = None
        for step_i in range(25):
            t = base + (1 if step_i % 2 else -1) * ((step_i + 1) // 2) * math.radians(15)
            px, py = cx + (rr + 6) * math.cos(t), cy + (rr + 6) * math.sin(t)
            ct, st = math.cos(t), math.sin(t)
            if ct > 0.35:
                box, anchor = Box(px + w / 2, py, w, h), "start"
            elif ct < -0.35:
                box, anchor = Box(px - w / 2, py, w, h), "end"
            else:
                box, anchor = Box(px, py + (h / 2 if st > 0 else -h / 2), w, h), "middle"
            inside = sum(1 for q in box.points() for o in keys if o != k
                         and (q[0] - circ[o][0]) ** 2 + (q[1] - circ[o][1]) ** 2 < circ[o][2] ** 2)
            bx0, by0, bx1, by1 = box.edges()            # past the circles' extent: wide costs more than tall
            spill = 0.25 * (max(0.0, -bx0) + max(0.0, bx1 - W)) + 0.05 * (max(0.0, -by0) + max(0.0, by1 - H))
            score = inside * 10 + sum(100 for o in placed if box.hits(o)) + abs(step_i) * 0.6 + spill
            if best is None or score < best[0]:
                best = (score, box, anchor, px, py)
        _, box, anchor, px, py = best
        placed.append(box)
        labels[k] = (px, box.cy, anchor)

    # region numbers: the deepest sample point where the pill fits (pulled a little toward the centroid), else outside
    # the circles with a short leader line
    def depth(x, y):
        return min(abs(math.hypot(x - cx, y - cy) - rr) for cx, cy, rr in circ.values())

    spots, outside = {}, []
    for reg, k in regions.items():
        rp = pts.get(reg, [])
        w, h = len(str(k)) * NUM_FONT * 0.6 + 2 * PILL_PX, PILL_H
        fits = lambda x, y: all(member(*q) == reg for q in Box(x, y, w, h).points(1.5))
        if rp:
            gx, gy = sum(p[0] for p in rp) / len(rp), sum(p[1] for p in rp) / len(rp)
            ok = [p for p in rp[::max(1, len(rp) // 4000)] if fits(*p)]
            if ok:
                x, y = max(ok, key=lambda p: depth(*p) - 0.2 * math.hypot(p[0] - gx, p[1] - gy))
                spots[reg] = {"x": x, "y": y, "inside": True}
                continue
        if not k:
            spots[reg] = None
            continue
        if rp:      # the region's deepest sample point anchors the leader
            anc = max(rp, key=lambda p: depth(*p))
        else:       # the region has no area in this layout: the point that comes closest to being in it
            cand = [p for v in pts.values() for p in v]
            anc = min(cand, key=lambda p: sum(max(0.0, math.hypot(p[0] - circ[o][0], p[1] - circ[o][1]) - circ[o][2]) for o in reg)
                      + sum(max(0.0, circ[o][2] - math.hypot(p[0] - circ[o][0], p[1] - circ[o][1])) for o in keys if o not in reg))
        outside.append((reg, anc, w, h))
    for reg, (ax, ay), w, h in outside:
        base = math.atan2(ay - uy, ax - ux) if math.hypot(ax - ux, ay - uy) > 1 else math.pi / 2
        best = None
        for step_i in range(25):
            t = base + (1 if step_i % 2 else -1) * ((step_i + 1) // 2) * math.radians(10)
            vx, vy = math.cos(t), math.sin(t)
            q = 0.0
            while member(ax + q * vx, ay + q * vy) and q < 4 * max(W, H):
                q += 0.5
            ext = min(w / 2 / max(abs(vx), 1e-6), h / 2 / max(abs(vy), 1e-6))     # centre to the pill's edge along v
            for gap in (5.0, 8.0, 12.0):
                bx, by = ax + (q + gap + ext) * vx, ay + (q + gap + ext) * vy
                box = Box(bx, by, w, h)
                seg = [(ax + u * (q + gap) * vx, ay + u * (q + gap) * vy) for u in (0.55, 0.7, 0.85, 1.0)]
                bad = (any(member(*p) for p in box.points(1.0)) or any(box.hits(o) for o in placed)
                       or any(Box(*p, 0, 0).hits(o, 1.0) for p in seg for o in placed))
                score = (q + gap) + (60 if bad else 0) + step_i * 0.8
                if best is None or score < best[0]:
                    best = (score, box, vx, vy, ext)
                if not bad:
                    break
        _, box, vx, vy, ext = best
        placed.append(box)
        spots[reg] = {"x": box.cx, "y": box.cy, "inside": False, "ax": ax, "ay": ay,
                      "lx": box.cx - (ext + 0.5) * vx, "ly": box.cy - (ext + 0.5) * vy}
    ex = [(0, 0, W, H)] + [b.edges() for b in placed]
    bbox = (min(e[0] for e in ex), min(e[1] for e in ex), max(e[2] for e in ex), max(e[3] for e in ex))
    return {"circles": circ, "labels": labels, "spots": spots, "bbox": bbox}
