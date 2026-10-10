#!/usr/bin/env python3
"""RoboPaint lettering exemplar builder (臨摹 of engraved English roundhand): a public-domain scan -> the exemplar of a lettering task.

    python lt_exemplar.py --spec exemplars.json --slug liberty --source-dir <dir with the scans> --tools <dir with rcb_brush*.py> --out <dir>

The exemplar is the scan's ink re-drawn with the task's own pointed pen (rcb_brush.py PointedPenPainter: a 0.4 mm hairline, the
tines' spread up to 2.0 mm along one axis), so every mark of the target is one the pen can make:
 1. ink = darkness (1 - max(R,G,B) / the paper's local level) of the crop, upsampled x4 (bicubic), above its Otsu threshold, with a
    hysteresis (fainter pixels connected to that ink keep faint hairlines whole), lightly smoothed; the spec's exclude rectangles
    and components outside the box go; pin holes are filled, the loops stay open;
 2. skeleton (skimage) -> graph (nodes: ends and junction clusters; edges: the pixel paths between them); end branches shorter than
    spur_k x the stroke radius at their junction are pruned (the forks of square stroke ends), shortest first;
 3. along every edge: the centre path (smoothed, in sheet mm) and the ink's thickness (2 x the distance to the edge; held across
    junction zones, where the distance is inflated);
 4. the pen: one spread axis for the whole exemplar (an oblique holder keeps the slit along the slant), fitted as the normal of the
    shades' mean direction (the thick ink, doubled-angle mean); the tines' spread per point w = h + (t - h) / max(|sin(dir - axis)|,
    sin_min), clipped to [h, w_max]: a mark of width t where the point moves across the axis;
 5. REGIONS (the scored strokes, rcb_brush_score.LetterTarget): the edges joined into trails by good continuation at the junctions
    (the pair of ends with the smallest turn <= max_turn_deg goes on), each trail cut into equal pieces of <= seg_mm (30 mm);
 6. CONTACTS (the stroke cap): one per connected piece of ink (the exemplar's own pen lifts); each gets a writing ROUTE, the
    reference plan: an Euler path over its edges (odd junctions paired by the shortest connections, which are written twice:
    retraces), starting at its leftmost odd end; a dot (an i's dot, a full stop) is a short pressed dash.
Outputs: <slug>.exemplar.json (pieces + routes + the record), <slug>_qa.png (the target's outline on the scan, regions coloured),
<slug>_target.png (the pen's rendering at the sheet raster), metrics (fidelity: the target vs the scan's ink on the sheet raster).
"""
from __future__ import annotations

import argparse, json, math, os, sys
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import cv2
from skimage.morphology import skeletonize

Image.MAX_IMAGE_PIXELS = None
U = 4                                    # upsampling of the scan before thresholding (smooth edges, hairlines several px wide)
SHEET_MM = 227.1845
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ------------------------------------------------------------------------------------------------ 1: ink
def load_ink(t: dict, src: str) -> tuple[np.ndarray, np.ndarray, dict]:
    im = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = t["box"]
    pad = int(t.get("pad_px", 12))
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)
    rgb = np.asarray(im.crop((X0, Y0, X1, Y1)), np.float32)
    V = rgb.max(-1)
    k = int(t.get("bg_px", 31))
    bg = ndimage.grey_closing(V, size=(k, k))
    bg = ndimage.gaussian_filter(bg, k / 3.0)
    D = np.clip((bg - V) / np.maximum(bg, 1.0), 0.0, 1.0)
    Du = cv2.resize(D, None, fx=U, fy=U, interpolation=cv2.INTER_CUBIC)
    inner = D[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
    thr, _ = cv2.threshold(np.clip(inner * 255, 0, 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = float(thr) / 255.0 * float(t.get("thr_scale", 1.0))
    weak = thr * float(t.get("weak_scale", 0.55))
    strong = Du > thr
    wl, wn = ndimage.label(Du > weak, structure=np.ones((3, 3)))
    has = np.zeros(wn + 1, bool); has[np.unique(wl[strong])] = True; has[0] = False
    ink = has[wl]
    ink = ndimage.gaussian_filter(ink.astype(np.float32), float(t.get("smooth_px", 1.2))) > 0.5
    for ex in t.get("exclude", []):                     # source px rectangles: neighbours' ink, ruled lines, specks
        ink[max(0, (ex[1] - Y0) * U):max(0, (ex[3] - Y0) * U), max(0, (ex[0] - X0) * U):max(0, (ex[2] - X0) * U)] = False
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    inbox = np.zeros_like(ink)
    inbox[(y0 - Y0) * U:(y1 - Y0) * U, (x0 - X0) * U:(x1 - X0) * U] = True
    sizes = np.bincount(lab.ravel(), minlength=n + 1); ins = np.bincount(lab[inbox].ravel(), minlength=n + 1)
    keep = (sizes >= float(t.get("min_src_px2", 10.0)) * U * U) & (ins >= float(t.get("keep_frac", 0.5)) * sizes)
    keep[0] = False
    ink = keep[lab]
    ink, n_bridges = bridge_gaps(ink, Du, float(t.get("bridge_src_px", 6.0)) * U, float(t.get("bridge_dark", 0.6)) * weak,
                                 float(t.get("bridge_cone_deg", 35.0)), float(t.get("bridge_short_src_px", 4.0)) * U,
                                 float(t.get("bridge_short_dark", 0.25)) * weak)
    holes = ndimage.binary_fill_holes(ink) & ~ink
    hl, hn = ndimage.label(holes)
    if hn:
        hs = np.bincount(hl.ravel())
        small = hs < float(t.get("max_pinhole_src_px2", 3.0)) * U * U
        small[0] = False
        ink |= small[hl]
    touch = [int(j) for j in np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]]) if j and keep[j]]
    meta = {"source_crop": [int(X0), int(Y0), int(X1), int(Y1)], "box": list(map(int, t["box"])), "otsu_darkness": round(thr, 4),
            "weak_darkness": round(weak, 4), "components_touching_crop_edge": len(touch), "bridged_gaps": n_bridges,
            "smallest_components_src_px2": sorted(round(float(v) / U / U, 1) for v in sizes[1:][keep[1:]])[:6]}
    return ink, Du, meta


def bridge_gaps(ink: np.ndarray, Du: np.ndarray, dist_px: float, dark: float, cone_deg: float, short_px: float = 0.0,
                short_dark: float = 1.0) -> tuple[np.ndarray, int]:
    """Faint hairlines that the threshold broke: a skeleton end is joined to the nearest skeleton pixel within dist_px that is not
    on its own stroke (another ink piece, or the same piece but more than 4 x dist_px away along the skeleton: a hairline broken
    where the rest of the figure still connects it), inside a cone of cone_deg around the end's outward direction, if the scan's
    darkness along the joining segment never drops below `dark` (there is ink there, only fainter), or, for a gap of at most
    short_px, its mean darkness reaches short_dark (a hairline the engraving made very faint); the join is drawn 3 px wide."""
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    sk = skeletonize(ink)
    P = np.pad(sk, 1).astype(np.uint8)
    nb = sum(np.roll(np.roll(P, dr, 0), dc, 1) for dr, dc in N8)[1:-1, 1:-1] * sk
    ends = np.argwhere(sk & (nb == 1))
    pts = np.argwhere(sk)
    if len(ends) == 0 or len(pts) == 0:
        return ink, 0
    from scipy.spatial import cKDTree
    tree = cKDTree(pts)
    out = ink.copy(); joined = 0; done = set()
    H, W = sk.shape

    def near_on_skeleton(e, limit):
        """The skeleton pixels within `limit` steps of e along the skeleton (8-connected)."""
        seen = {tuple(e)}; front = [tuple(e)]
        for _ in range(int(limit)):
            nxt = []
            for r, c in front:
                for dr, dc in N8:
                    q = (r + dr, c + dc)
                    if 0 <= q[0] < H and 0 <= q[1] < W and sk[q] and q not in seen:
                        seen.add(q); nxt.append(q)
            if not nxt:
                break
            front = nxt
        return seen
    for e in ends:
        # outward direction: from the skeleton 8 px back to the end
        idx = tree.query_ball_point(e, 9)
        own = [pts[i] for i in idx if lab[tuple(pts[i])] == lab[tuple(e)]]
        if len(own) < 3:
            continue
        back = np.mean(own, axis=0)
        v = e - back
        if np.hypot(*v) < 1e-6:
            continue
        v = v / np.hypot(*v)
        best = None
        own = None
        for i in tree.query_ball_point(e, dist_px):
            q = pts[i]
            if lab[tuple(q)] == lab[tuple(e)]:
                if own is None:
                    own = near_on_skeleton(e, 4 * dist_px)
                if tuple(q) in own:
                    continue
            w = q - e
            d = float(np.hypot(*w))
            if d < 1e-6 or math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(w / d, v)))))) > cone_deg:
                continue
            if best is None or d < best[0]:
                best = (d, q)
        if best is None:
            continue
        d, q = best
        key = (tuple(e), tuple(q)) if lab[tuple(q)] == lab[tuple(e)] else tuple(sorted((int(lab[tuple(e)]), int(lab[tuple(q)]))))
        m = max(2, int(math.ceil(d)))
        line = np.stack([np.linspace(e[0], q[0], m + 1), np.linspace(e[1], q[1], m + 1)], 1)
        vals = Du[np.round(line[:, 0]).astype(int), np.round(line[:, 1]).astype(int)]
        if key in done or not (float(vals.min()) >= dark or (d <= short_px and float(vals.mean()) >= short_dark)):
            continue
        done.add(key)
        for r_, c_ in np.round(line).astype(int):
            out[max(0, r_ - 1):r_ + 2, max(0, c_ - 1):c_ + 2] = True
        joined += 1
    return out, joined


# ------------------------------------------------------------------------------------------------ 2: skeleton graph
def skeleton_graph(sk: np.ndarray):
    """-> nodes [(r, c)], edges [{"a", "b", "path": [(r, c), ...]}] (node pixels included at both ends)."""
    H, W = sk.shape
    P = np.pad(sk, 1).astype(np.uint8)
    nb = sum(np.roll(np.roll(P, dr, 0), dc, 1) for dr, dc in N8)[1:-1, 1:-1] * sk
    node_px = sk & (nb != 2)
    jl, jn = ndimage.label(node_px & (nb >= 3), structure=np.ones((3, 3)))
    nodes, node_of = [], {}
    for j in range(1, jn + 1):
        rr, cc = np.nonzero(jl == j)
        k = len(nodes); nodes.append((float(rr.mean()), float(cc.mean())))
        for p in zip(rr.tolist(), cc.tolist()):
            node_of[p] = k
    for r, c in zip(*np.nonzero(node_px & (nb < 3))):
        node_of[(int(r), int(c))] = len(nodes); nodes.append((float(r), float(c)))
    nbrs = lambda q: [(q[0] + dr, q[1] + dc) for dr, dc in N8 if 0 <= q[0] + dr < H and 0 <= q[1] + dc < W and sk[q[0] + dr, q[1] + dc]]
    edges, used = [], set()
    for p0, k0 in list(node_of.items()):
        for q in nbrs(p0):
            if q in node_of:
                k1 = node_of[q]
                if k1 != k0 and (min(p0, q), max(p0, q)) not in used:
                    used.add((min(p0, q), max(p0, q)))
                    edges.append({"a": k0, "b": k1, "path": [p0, q]})
                continue
            if q in used:
                continue
            path, prev, cur = [p0, q], p0, q
            used.add(q)
            while True:
                cand = [z for z in nbrs(cur) if z != prev]
                hit = [z for z in cand if z in node_of and not (node_of[z] == k0 and len(path) <= 2)]
                if hit:
                    path.append(hit[0]); edges.append({"a": k0, "b": node_of[hit[0]], "path": path}); break
                free = [z for z in cand if z not in used]
                if not free:
                    break
                free.sort(key=lambda z: abs(z[0] - cur[0]) + abs(z[1] - cur[1]))
                prev, cur = cur, free[0]
                used.add(cur); path.append(cur)
    rest = sk.copy()
    for p in list(node_of) + [q for q in used if isinstance(q[0], int)]:
        rest[p] = False
    lab, n = ndimage.label(rest, structure=np.ones((3, 3)))
    for j in range(1, n + 1):                                   # closed curves without a node (an o on its own)
        rr, cc = np.nonzero(lab == j)
        mem = set(zip(rr.tolist(), cc.tolist()))
        start = (int(rr[0]), int(cc[0]))
        k = len(nodes); nodes.append((float(start[0]), float(start[1])))
        path, seen, cur = [start], {start}, start
        while True:
            nx = sorted([z for z in nbrs(cur) if z in mem and z not in seen], key=lambda z: abs(z[0] - cur[0]) + abs(z[1] - cur[1]))
            if not nx:
                break
            cur = nx[0]; seen.add(cur); path.append(cur)
        path.append(start)
        edges.append({"a": k, "b": k, "path": path})
    return nodes, edges


def degree(edges, k):
    return sum((e["a"] == k) + (e["b"] == k) for e in edges)


def prune_and_merge(nodes, edges, R, spur_k, spur_px):
    """Prune end branches shorter than spur_k x the radius at their junction + spur_px (shortest first), then join the edges through
    every node of degree 2."""
    changed = True
    while changed:
        changed = False
        cand = []
        for i, e in enumerate(edges):
            da, db = degree(edges, e["a"]), degree(edges, e["b"])
            if e["a"] == e["b"]:
                continue
            for end, other, dend, doth in ((e["a"], e["b"], da, db), (e["b"], e["a"], db, da)):
                if dend == 1 and doth >= 3:
                    r = R[int(round(nodes[other][0])), int(round(nodes[other][1]))]
                    if len(e["path"]) < spur_k * r + spur_px:
                        cand.append((len(e["path"]), i))
        if cand:
            cand.sort()
            edges.pop(cand[0][1])
            changed = True
            continue
        for k in range(len(nodes)):                               # join through degree-2 nodes
            inc = [i for i, e in enumerate(edges) if e["a"] == k or e["b"] == k]
            if len(inc) == 2 and inc[0] != inc[1]:
                e1, e2 = edges[inc[0]], edges[inc[1]]
                p1 = e1["path"] if e1["b"] == k else e1["path"][::-1]
                p2 = e2["path"] if e2["a"] == k else e2["path"][::-1]
                a = e1["a"] if e1["b"] == k else e1["b"]
                b = e2["b"] if e2["a"] == k else e2["a"]
                new = {"a": a, "b": b, "path": p1 + p2[1:]}
                for i in sorted(inc, reverse=True):
                    edges.pop(i)
                edges.append(new)
                changed = True
                break
    used = sorted({e["a"] for e in edges} | {e["b"] for e in edges})
    remap = {k: i for i, k in enumerate(used)}
    return [nodes[k] for k in used], [{"a": remap[e["a"]], "b": remap[e["b"]], "path": e["path"]} for e in edges]


# ------------------------------------------------------------------------------------------------ 3-4: paths, widths, pen
def smooth_path(P: np.ndarray, sigma: float, closed: bool) -> np.ndarray:
    if len(P) < 5 or sigma <= 0:
        return P.astype(np.float64)
    if closed:
        Q = np.vstack([P[:-1]] * 3)
        S = np.stack([ndimage.gaussian_filter1d(Q[:, i].astype(np.float64), sigma) for i in range(2)], 1)
        n = len(P) - 1
        out = S[n:2 * n + 1]
        out[-1] = out[0]
        return out
    S = np.stack([ndimage.gaussian_filter1d(P[:, i].astype(np.float64), sigma, mode="nearest") for i in range(2)], 1)
    w = np.minimum(1.0, np.arange(len(P)) / (2 * sigma)) * np.minimum(1.0, np.arange(len(P))[::-1] / (2 * sigma))
    return S * w[:, None] + P * (1 - w[:, None])                  # the end points stay where they are


def resample(P: np.ndarray, extra: list[np.ndarray], step: float):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    if d[-1] < 1e-9:
        return P[:1].copy(), [x[:1].copy() for x in extra], d[:1]
    n = max(2, int(math.ceil(d[-1] / step)) + 1)
    s = np.linspace(0, d[-1], n)
    Q = np.stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])], 1)
    return Q, [np.interp(s, d, x) for x in extra], s


def simplify(P: np.ndarray, W: np.ndarray, eps: float, w_scale: float = 0.25) -> np.ndarray:
    """Indices of the points kept by Ramer-Douglas-Peucker on (x, y, w_scale * w) with tolerance eps (mm): the exemplar file keeps
    a few points per millimetre on curves and few on straight runs; the pen's sweep between kept points is linear in position and
    spread, so the dropped points lie within eps of it."""
    Q = np.c_[P, w_scale * np.asarray(W)]
    keep = np.zeros(len(Q), bool); keep[0] = keep[-1] = True
    stack = [(0, len(Q) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = Q[b] - Q[a]; L = float(np.linalg.norm(seg))
        R = Q[a + 1:b] - Q[a]
        if L < 1e-12:
            d = np.linalg.norm(R, axis=1)
        else:
            u = seg / L
            d = np.linalg.norm(R - np.outer(R @ u, u), axis=1)
        k = int(np.argmax(d))
        if d[k] > eps:
            m = a + 1 + k; keep[m] = True
            stack += [(a, m), (m, b)]
    return np.nonzero(keep)[0]


def writer_angle(dxy: np.ndarray) -> np.ndarray:
    """Directions in sheet mm (X right, Y down) -> angles in the writer's view (0 = along the line to the right, CCW positive)."""
    return np.arctan2(-dxy[:, 1], dxy[:, 0])


def build(t: dict, src: str, tools: str, out: str, slug: str) -> dict:
    sys.path.insert(0, tools)
    import rcb_brush as RB
    import rcb_brush_score as RS
    ink, Du, meta = load_ink(t, src)
    X0, Y0 = meta["source_crop"][:2]
    rr, cc = np.nonzero(ink)
    bb = (rr.min(), rr.max() + 1, cc.min(), cc.max() + 1)                  # the ink's bbox (upsampled crop px)
    s_mm = float(t["width_mm"]) / ((bb[3] - bb[2]) / U)                    # sheet mm per source px
    h_mm, wmax = RB.BRUSH_POINTED["hairline_m"] * 1000, RB.BRUSH_POINTED["max_width_m"] * 1000
    cx, cy = SHEET_MM / 2 + float(t.get("dx_mm", 0.0)), SHEET_MM / 2 + float(t.get("dy_mm", 0.0))
    ox = cx - (bb[2] + bb[3]) / 2 / U * s_mm                               # sheet mm of upsampled px (r, c): (ox + c/U*s, oy + r/U*s)
    oy = cy - (bb[0] + bb[1]) / 2 / U * s_mm
    to_mm = lambda r, c: (ox + np.asarray(c, np.float64) / U * s_mm, oy + np.asarray(r, np.float64) / U * s_mm)
    px_mm = s_mm / U
    R = ndimage.distance_transform_edt(ink)
    sk = skeletonize(ink)
    nodes, edges = skeleton_graph(sk)
    nodes, edges = prune_and_merge(nodes, edges, R, float(t.get("spur_k", 1.6)), float(t.get("spur_px", 3)))
    deg = defaultdict(int)
    for e in edges:
        deg[e["a"]] += 1; deg[e["b"]] += 1
    # 3: per edge: smoothed centre path in sheet mm + thickness (held across junction zones)
    E = []
    for e in edges:
        P = np.asarray(e["path"], np.float64)
        closed = e["a"] == e["b"] and len(P) > 3 and tuple(P[0]) == tuple(P[-1])
        r = R[P[:, 0].astype(int), P[:, 1].astype(int)]
        dist = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
        good = np.ones(len(P), bool)
        for end, k in ((0, e["a"]), (-1, e["b"])):
            if deg[k] >= 3:
                rn = R[int(round(nodes[k][0])), int(round(nodes[k][1]))]
                zone = 1.3 * rn + 2
                good &= (dist - dist[end] if end == 0 else dist[-1] - dist) > zone
        if good.sum() >= 2:
            r = np.interp(np.arange(len(P)), np.nonzero(good)[0], r[good])
        elif len(P):
            r = np.full(len(P), float(np.median(r)))
        S = smooth_path(P, float(t.get("path_sigma_px", 3.0)), closed)
        Xm, Ym = to_mm(S[:, 0], S[:, 1])
        thick = np.maximum(2 * r * px_mm, 0.0)
        Q, (T,), _ = resample(np.stack([Xm, Ym], 1), [ndimage.gaussian_filter1d(thick, 2.0, mode="nearest")], float(t.get("step_mm", 0.1)))
        E.append({"a": e["a"], "b": e["b"], "P": Q, "t": T, "closed": closed})
    # 4: the pen's spread axis: normal of the thick ink's mean direction (doubled angles)
    num = den = 0.0
    for e in E:
        if len(e["P"]) < 3:
            continue
        ang = writer_angle(np.gradient(e["P"], axis=0))
        wgt = np.clip(e["t"] - 2.0 * h_mm, 0, None)
        num += float(np.sum(wgt * np.sin(2 * ang))); den += float(np.sum(wgt * np.cos(2 * ang)))
    shade_dir = 0.5 * math.degrees(math.atan2(num, den))
    axis = float(t["axis_deg"]) if "axis_deg" in t else ((shade_dir - 90.0 + 90.0) % 180.0) - 90.0
    sin_min = float(t.get("sin_min", 0.35))
    for e in E:
        if len(e["P"]) >= 2:
            ang = writer_angle(np.gradient(e["P"], axis=0))
            sn = np.maximum(np.abs(np.sin(ang - math.radians(axis))), sin_min)
        else:
            sn = np.ones(len(e["P"]))
        w = h_mm + np.clip(e["t"] - h_mm, 0, None) / sn
        e["w"] = np.clip(ndimage.gaussian_filter1d(w, 1.5, mode="nearest") if len(w) > 3 else w, h_mm, wmax)
        e["len"] = float(np.sum(np.hypot(*np.diff(e["P"], axis=0).T))) if len(e["P"]) > 1 else 0.0
    # ball terminals (a round blob at a stroke's free end: an r's or c's ball, a full stop run into a flourish): the pen's mark
    # at a point is a bar along its spread axis, so the end inside the ball becomes a pressed dash across the axis (along the
    # slant), as wide as the ball, which makes a round blob of the ball's size
    u_slant = np.array([math.cos(math.radians(axis + 90.0)), -math.sin(math.radians(axis + 90.0))])   # sheet mm (X right, Y down)
    n_balls = 0
    for e in E:
        if e["closed"] or len(e["P"]) < 8:
            continue
        for at_start in (True, False):
            k = e["a"] if at_start else e["b"]
            if deg[k] != 1:
                continue
            P = e["P"] if at_start else e["P"][::-1]
            T = e["t"] if at_start else e["t"][::-1]
            Wd = e["w"] if at_start else e["w"][::-1]
            d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
            near = d <= float(t.get("ball_zone_mm", 1.2))
            before = (d >= 1.2) & (d <= 3.0)
            if near.sum() < 2 or before.sum() < 2:
                continue
            i_c = int(np.argmax(np.where(near, T, -1)))
            D = float(T[i_c])
            if D < float(t.get("ball_min_mm", 0.75)) or D < float(t.get("ball_ratio", 2.0)) * float(np.median(T[before])):
                continue
            c = P[i_c]
            # keep the stroke up to where it enters the ball (from the far side), then the dash through the ball's centre
            inside = np.hypot(*(P - c).T) <= D / 2
            first_out = int(np.argmax(~inside[i_c:])) + i_c if (~inside[i_c:]).any() else len(P) - 1
            L = max(0.05, D - h_mm)
            dash = np.stack([c + u_slant * L / 2, c - u_slant * L / 2])
            if np.dot(P[first_out] - c, u_slant) > 0:
                dash = dash[::-1]                                  # end the dash on the side the stroke leaves from
            wb = min(wmax, max(h_mm, D))
            P2 = np.vstack([dash, P[first_out:]]); W2 = np.r_[[wb, wb], Wd[first_out:]]; T2 = np.r_[[D, D], T[first_out:]]
            if not at_start:
                P2, W2, T2 = P2[::-1], W2[::-1], T2[::-1]
            e["P"], e["w"], e["t"] = P2, W2, T2
            n_balls += 1
        e["len"] = float(np.sum(np.hypot(*np.diff(e["P"], axis=0).T))) if len(e["P"]) > 1 else 0.0
    # components (contacts) over the graph
    parent = list(range(len(nodes)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for e in E:
        parent[find(e["a"])] = find(e["b"])
    comp_of_node = {k: find(k) for k in range(len(nodes))}
    comps = defaultdict(list)
    for i, e in enumerate(E):
        comps[comp_of_node[e["a"]]].append(i)
    # dots: components whose ink is tiny -> a short pressed dash through the blob (along the slant)
    lab, nl = ndimage.label(ink, structure=np.ones((3, 3)))
    comp_ink = {}
    for c, ei in comps.items():
        e0 = E[ei[0]]
        X, Y = e0["P"][len(e0["P"]) // 2]
        rr0, cc0 = int(round((Y - oy) / s_mm * U)), int(round((X - ox) / s_mm * U))
        rr0, cc0 = min(max(rr0, 0), ink.shape[0] - 1), min(max(cc0, 0), ink.shape[1] - 1)
        j = lab[rr0, cc0]
        if j == 0:
            win = lab[max(0, rr0 - 6):rr0 + 7, max(0, cc0 - 6):cc0 + 7]
            j = int(np.bincount(win[win > 0]).argmax()) if (win > 0).any() else 0
        comp_ink[c] = j
    skel_comp_labels = set(comp_ink.values())
    dots = []
    for j in range(1, nl + 1):                                     # ink pieces without a skeleton edge (round dots)
        if j not in skel_comp_labels:
            dots.append(j)
    for c, ei in list(comps.items()):                               # an i's dot, a full stop: little centre path for its size
        tot = sum(E[i]["len"] for i in ei); tmax = max(float(np.max(E[i]["t"])) if len(E[i]["t"]) else 0.0 for i in ei)
        if tot < max(float(t.get("dot_len_mm", 1.0)), 1.5 * tmax) and comp_ink[c]:
            dots.append(comp_ink[c]); del comps[c]
    dot_edges = set(i for i in range(len(E)) if comp_of_node[E[i]["a"]] not in comps)
    seg_mm = float(t.get("seg_mm", 30.0))
    pieces, routes = [], []
    # 5: regions = trails by good continuation, cut into <= seg_mm pieces
    ends = defaultdict(list)                                       # node -> [(edge index, at start?)]
    for i, e in enumerate(E):
        ends[e["a"]].append((i, True)); ends[e["b"]].append((i, False))
    def end_dir(i, at_start):
        P = E[i]["P"]; m = min(len(P) - 1, max(1, int(round(1.0 / float(t.get("step_mm", 0.1))))))
        v = (P[m] - P[0]) if at_start else (P[-1 - m] - P[-1])
        n = np.hypot(*v)
        return v / n if n > 1e-9 else np.array([1.0, 0.0])
    pair = {}
    max_turn = math.radians(float(t.get("max_turn_deg", 75.0)))
    for k, lst in ends.items():
        if len(lst) < 2:
            continue
        cand = []
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                if lst[x][0] == lst[y][0] and E[lst[x][0]]["closed"]:
                    continue
                d1, d2 = end_dir(*lst[x]), end_dir(*lst[y])
                turn = math.pi - math.acos(max(-1.0, min(1.0, float(np.dot(d1, d2)))))   # 0 = straight on
                cand.append((turn, x, y))
        cand.sort()
        taken = set()
        for turn, x, y in cand:
            if turn > max_turn or x in taken or y in taken:
                continue
            taken |= {x, y}
            pair[lst[x]] = lst[y]; pair[lst[y]] = lst[x]
    seen = set(dot_edges)
    trails = []
    for i in range(len(E)):
        if i in seen:
            continue
        # walk back to a trail end, then forward
        cur, fwd = i, True
        guard = 0
        while guard < len(E) + 2:
            guard += 1
            end = (cur, True) if fwd else (cur, False)        # the start end of cur in direction fwd
            nxt = pair.get(end)
            if nxt is None or nxt[0] == i:
                break
            cur, fwd = nxt[0], not nxt[1]
        chain, c2, f2 = [], cur, fwd
        while True:
            if c2 in seen:
                break
            seen.add(c2); chain.append((c2, f2))
            end = (c2, False) if f2 else (c2, True)
            nxt = pair.get(end)
            if nxt is None:
                break
            c2, f2 = nxt[0], nxt[1]
        trails.append(chain)
    min_trail = float(t.get("min_trail_mm", 1.5))
    dropped = 0
    for chain in trails:
        first, last = chain[0], chain[-1]
        n0 = E[first[0]]["a"] if first[1] else E[first[0]]["b"]
        n1 = E[last[0]]["b"] if last[1] else E[last[0]]["a"]
        if sum(E[i]["len"] for i, _ in chain) < min_trail and deg[n0] >= 3 and deg[n1] >= 3:
            dropped += 1                                           # a junction connector inside the other strokes' ink
            continue
        P = np.vstack([E[i]["P"] if f else E[i]["P"][::-1] for i, f in chain])
        W = np.concatenate([E[i]["w"] if f else E[i]["w"][::-1] for i, f in chain])
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
        L = d[-1]
        n = max(1, int(math.ceil(L / seg_mm - 1e-9)))
        cuts = np.linspace(0, L, n + 1)
        for a_, b_ in zip(cuts[:-1], cuts[1:]):
            m = (d >= a_ - 1e-9) & (d <= b_ + 1e-9)
            idx = np.nonzero(m)[0]
            if len(idx) == 0:
                continue
            idx = np.r_[max(0, idx[0] - 1), idx, min(len(P) - 1, idx[-1] + 1)]
            idx = np.unique(idx)
            pieces.append({"points": P[idx], "w": W[idx], "comp": comp_of_node[E[chain[0][0]]["a"]], "len": float(b_ - a_)})
    for j in dots:
        rr_, cc_ = np.nonzero(lab == j)
        if len(rr_) < float(t.get("min_dot_src_px2", 12.0)) * U * U:
            continue                                               # a speck of the paper, not a dot
        Xc, Yc = to_mm(rr_.mean(), cc_.mean())
        Xp, Yp = to_mm(rr_, cc_)
        rel = np.stack([Xp - Xc, Yp - Yc], 1)
        e_ax = np.array([math.cos(math.radians(axis)), -math.sin(math.radians(axis))])
        ext_e = float(np.percentile(rel @ e_ax, 98) - np.percentile(rel @ e_ax, 2)) + px_mm      # across the slant (the spread)
        ext_u = float(np.percentile(rel @ u_slant, 98) - np.percentile(rel @ u_slant, 2)) + px_mm  # along the slant
        wd = min(wmax, max(h_mm, ext_e)); L = max(0.05, ext_u - h_mm)
        P = np.stack([np.array([Xc, Yc]) - u_slant * L / 2, np.array([Xc, Yc]) + u_slant * L / 2])
        Q, (Wd,), _ = resample(P, [np.full(2, wd)], 0.1)
        c = ("dot", j)
        pieces.append({"points": Q, "w": Wd, "comp": c, "len": float(np.hypot(*(P[1] - P[0])))})
        routes.append({"comp": c, "points": Q, "w": Wd, "dot": True})
    # 6: contacts: an Euler route per component (odd nodes paired by shortest connections, written twice)
    for c, eidx in comps.items():
        routes.append(euler_route(c, eidx, E, nodes))
    # order: contacts left to right by their start
    routes.sort(key=lambda r: (float(r["points"][0][0])))
    comp_ids = {}
    for k, r in enumerate(routes):
        comp_ids[str(r["comp"])] = k
    for p in pieces:
        p["contact"] = comp_ids[str(p["comp"])]
    pieces.sort(key=lambda p: (p["contact"], float(p["points"][0][0])))
    # the target: LetterTarget of the pieces on the sheet raster; fidelity against the scan's ink on that raster
    eps = float(t.get("simplify_mm", 0.004))
    for p in pieces + routes:
        P, Wd = np.asarray(p["points"], np.float64), np.asarray(p["w"], np.float64)
        if len(P) > 2:
            idx = simplify(P, Wd, eps)
            p["points"], p["w"] = P[idx], Wd[idx]
    tgt_strokes = [{"points_mm": [[round(float(x), 3), round(float(y), 3)] for x, y in p["points"]],
                    "widths_mm": [round(float(w), 3) for w in p["w"]], "angle_deg": round(axis, 3)} for p in pieces]
    sheet = RB.Sheet("main", (-0.10, 0.0), 1024, 1024, RB.PAPER_SIDE_M / 1024)
    LT = RS.LetterTarget({"nib": {"kind": "pointed", "hairline_m": h_mm / 1000, "max_width_m": wmax / 1000}, "strokes": tgt_strokes,
                          "box_mm": [0, 0, 0]}, sheet)
    cov = LT.coverage()
    # the scan's ink resampled onto the sheet raster
    pxs = RB.PAPER_SIDE_M * 1000 / 1024
    us = (np.arange(1024) + 0.5) * pxs
    cgrid = (us - ox) / s_mm * U; rgrid = (us - oy) / s_mm * U
    mapx, mapy = np.meshgrid(cgrid.astype(np.float32), rgrid.astype(np.float32))
    scan_ink = cv2.remap(ink.astype(np.float32), mapx, mapy, cv2.INTER_LINEAR, borderValue=0) >= 0.5
    scan_dark = cv2.remap(Du.astype(np.float32), mapx, mapy, cv2.INTER_LINEAR, borderValue=0)
    T = cov >= 0.5
    inter, union = int((T & scan_ink).sum()), int((T | scan_ink).sum())
    near_T = ndimage.distance_transform_edt(~T) * pxs <= 0.5
    near_S = ndimage.distance_transform_edt(~scan_ink) * pxs <= 0.5
    fid = {"iou_vs_scan": round(inter / max(1, union), 4), "scan_ink_within_0.5mm": round(float((scan_ink & near_T).sum()) / max(1, scan_ink.sum()), 4),
           "target_ink_within_0.5mm_of_scan": round(float((T & near_S).sum()) / max(1, T.sum()), 4),
           "target_area_mm2": round(float(T.sum()) * pxs * pxs, 1), "scan_area_mm2": round(float(scan_ink.sum()) * pxs * pxs, 1)}
    bbT = np.nonzero(T)
    fid["target_bbox_mm"] = [round(float(bbT[1].min() * pxs), 2), round(float(bbT[0].min() * pxs), 2),
                             round(float((bbT[1].max() + 1) * pxs), 2), round(float((bbT[0].max() + 1) * pxs), 2)]
    route_len = sum(float(np.sum(np.hypot(*np.diff(r["points"], axis=0).T))) for r in routes if len(r["points"]) > 1)
    ink_len = sum(e["len"] for e in E)
    rec = {"slug": slug, "text": t["text"], "hand": t.get("hand", "round hand"), "source": t["source"], "box_src_px": t["box"],
           "mm_per_src_px": round(s_mm, 5), "sheet_mm_of_crop_px0": [round(ox, 4), round(oy, 4)], "axis_deg": round(axis, 3), "shade_dir_deg": round(shade_dir, 2),
           "n_contacts": len(routes), "n_regions": len(pieces), "ink_path_mm": round(ink_len, 1), "route_mm": round(route_len, 1),
           "retrace_mm": round(route_len - ink_len, 1), "fidelity": fid, "ink": meta, "junction_stubs_dropped": dropped,
           "ball_terminals": n_balls, "dots": sum(1 for r in routes if r.get("dot")),
           "contacts_mm": [round(float(np.sum(np.hypot(*np.diff(r["points"], axis=0).T))), 1) if len(r["points"]) > 1 else 0.0 for r in routes],
           "spread_at_max_frac": round(float(np.mean(np.concatenate([e["w"] for e in E]) >= wmax - 1e-6)), 4),
           "region_len_mm": {"min": round(min(p["len"] for p in pieces), 2), "max": round(max(p["len"] for p in pieces), 2)}}
    ex = {**rec, "pieces": tgt_strokes, "piece_contact": [p["contact"] for p in pieces],
          "routes": [{"points_mm": [[round(float(x), 3), round(float(y), 3)] for x, y in r["points"]], "widths_mm": [round(float(w), 3) for w in r["w"]],
                      "dot": bool(r.get("dot", False))} for r in routes]}
    os.makedirs(out, exist_ok=True)
    json.dump(ex, open(os.path.join(out, f"{slug}.exemplar.json"), "w"), indent=1, ensure_ascii=False)
    # pictures: the target (pen rendering), and the QA overlay (scan + the target's outline, regions coloured)
    a = cov[..., None]
    img = np.asarray(RB.PAPER_RGB, np.float32) * (1 - a) + np.asarray(RB.INK_RGB, np.float32) * a
    Image.fromarray(np.round(img * 255).astype(np.uint8)).save(os.path.join(out, f"{slug}_target.png"))
    qa_overlay(out, slug, src, meta, s_mm, ox, oy, cov, pieces, [{"points": r["points"]} for r in routes])
    return rec


def euler_route(c, eidx, E, nodes) -> dict:
    """An Euler path over the component's edges; odd nodes paired greedily by the shortest connections (Dijkstra over the edges),
    whose edges are written twice (retraces). Starts at the leftmost odd node (or the leftmost node of a closed figure)."""
    import heapq
    adj = defaultdict(list)                                       # node -> [(edge id, other node)]
    for i in eidx:
        adj[E[i]["a"]].append((i, E[i]["b"])); adj[E[i]["b"]].append((i, E[i]["a"]))
    deg = {k: len(v) for k, v in adj.items()}
    odd = [k for k, d in deg.items() if d % 2]
    mult = defaultdict(int)
    for i in eidx:
        mult[i] += 1
    def dijkstra(s):
        dist, prev = {s: 0.0}, {}
        h = [(0.0, s)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e18):
                continue
            for i, v in adj[u]:
                nd = d + E[i]["len"]
                if nd < dist.get(v, 1e18):
                    dist[v] = nd; prev[v] = (u, i); heapq.heappush(h, (nd, v))
        return dist, prev
    xs = lambda k: nodes[k][1]
    odd.sort(key=xs)
    start_pair = odd[:1]
    rest = odd[1:]
    # keep the leftmost odd node and the one farthest to the right as the two ends; pair the others greedily
    if rest:
        endn = max(rest, key=xs)
        rest = [k for k in rest if k != endn]
    while rest:
        k = rest.pop(0)
        dist, prev = dijkstra(k)
        j = min(rest, key=lambda z: dist.get(z, 1e18))
        rest.remove(j)
        v = j
        while v != k:
            u, i = prev[v]; mult[i] += 1; v = u
    start = odd[0] if odd else min(adj, key=xs)
    # Hierholzer with smooth continuation preference
    avail = defaultdict(list)
    for i in eidx:
        for _ in range(mult[i]):
            avail[E[i]["a"]].append(i)
            if E[i]["b"] != E[i]["a"]:
                avail[E[i]["b"]].append(i)
            else:
                avail[E[i]["a"]].append(i)
    left = {i: mult[i] for i in eidx}
    def take(u, i):
        left[i] -= 1
        avail[u].remove(i)
        v = E[i]["b"] if E[i]["a"] == u else E[i]["a"]
        avail[v].remove(i)
        return v
    stack, out = [(start, None, True)], []
    while stack:
        u, i_in, f_in = stack[-1]
        if avail[u]:
            # prefer the edge leaving u straightest from the incoming direction
            if i_in is not None:
                Pin = E[i_in]["P"] if f_in else E[i_in]["P"][::-1]
                m = min(len(Pin) - 1, 10)
                din = Pin[-1] - Pin[-1 - m]
            else:
                din = None
            best, bi = None, None
            for i in set(avail[u]):
                fw = E[i]["a"] == u
                P = E[i]["P"] if fw else E[i]["P"][::-1]
                m = min(len(P) - 1, 10)
                dout = P[m] - P[0]
                sc = 0.0 if din is None else -float(np.dot(din, dout) / (np.hypot(*din) * np.hypot(*dout) + 1e-12))
                if best is None or sc < best:
                    best, bi = sc, i
            fw = E[bi]["a"] == u
            v = take(u, bi)
            stack.append((v, bi, fw))
        else:
            stack.pop()
            if i_in is not None:
                out.append((i_in, f_in))
    out.reverse()
    pts, ws = [], []
    for i, fw in out:
        P = E[i]["P"] if fw else E[i]["P"][::-1]
        Wd = E[i]["w"] if fw else E[i]["w"][::-1]
        if pts:
            P, Wd = P[1:], Wd[1:]
        pts.append(P); ws.append(Wd)
    return {"comp": c, "points": np.vstack(pts), "w": np.concatenate(ws)}


def qa_overlay(out, slug, src, meta, s_mm, ox, oy, cov, pieces, routes) -> None:
    """QA pictures. <slug>_qa.png: the scan (grey, x4) with the target's outline (red: the 0.5 level of the pen's coverage);
    <slug>_contacts.png: the target with each contact in its own colour and the regions' cut points (black ticks)."""
    from skimage import measure
    X0, Y0, X1, Y1 = meta["source_crop"]
    S = 4
    im = Image.open(src).convert("L").crop((X0, Y0, X1, Y1))
    big = im.resize((im.width * S, im.height * S), Image.BICUBIC).convert("RGB")
    big = Image.blend(big, Image.new("RGB", big.size, (255, 255, 255)), 0.15)
    d = ImageDraw.Draw(big)
    pxs = SHEET_MM / 1024
    for c in measure.find_contours(cov, 0.5):
        Xm, Ym = (c[:, 1] + 0.5) * pxs, (c[:, 0] + 0.5) * pxs
        pts = list(zip(((Xm - ox) / s_mm * S).tolist(), ((Ym - oy) / s_mm * S).tolist()))
        if len(pts) > 1:
            d.line(pts, fill=(225, 25, 25), width=2)
    big.save(os.path.join(out, f"{slug}_qa.png"))
    # contacts in colour on the target (sheet raster x2)
    pal = [(31, 119, 180), (214, 39, 40), (44, 160, 44), (148, 103, 189), (255, 127, 14), (23, 190, 207), (140, 86, 75), (227, 119, 194),
           (188, 189, 34), (127, 127, 127)]
    K = 2
    canvas = Image.new("RGB", (1024 * K, 1024 * K), (250, 247, 240))
    d = ImageDraw.Draw(canvas)
    for k, r in enumerate(routes):
        P = np.asarray(r["points"]) / pxs * K
        col = pal[k % len(pal)]
        if len(P) > 1:
            d.line([tuple(p) for p in P.tolist()], fill=col, width=3)
        d.ellipse([P[0][0] - 5, P[0][1] - 5, P[0][0] + 5, P[0][1] + 5], outline=col, width=2)
        d.text((P[0][0] + 6, P[0][1] - 18), str(k + 1), fill=col)
    for p in pieces:
        for q in (p["points"][0], p["points"][-1]):
            x, y = q[0] / pxs * K, q[1] / pxs * K
            d.line([(x - 4, y - 4), (x + 4, y + 4)], fill=(0, 0, 0), width=2)
    canvas.save(os.path.join(out, f"{slug}_contacts.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True); ap.add_argument("--slug", required=True); ap.add_argument("--source-dir", required=True)
    ap.add_argument("--tools", required=True, help="a directory holding rcb_brush.py and rcb_brush_score.py (a task's tests/)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    t = spec["targets"][a.slug]
    src = os.path.join(a.source_dir, t["source"]["file"])
    rec = build(t, src, a.tools, a.out, a.slug)
    print(json.dumps(rec, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
