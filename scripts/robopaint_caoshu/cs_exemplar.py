#!/usr/bin/env python3
"""RoboPaint caoshu (草書) exemplar builder: a public-domain scan of a cursive work -> the task's exemplar file in Make Me a Hanzi's
graphics.txt format (one JSON line per character; "strokes" = the REGIONS of its ink, one simple polygon each, "medians" = their
centre paths), the CONTACT plan (trails: the regions one brush contact writes, in order and direction) and review pictures.

    python cs_exemplar.py --spec exemplars.json --slug wen --out work/wen --source-dir <dir with the source scan>

Method (after the xingshu builder of 2026-09-28, changed for cursive where marked):
 1. ink = the crop's pixels darker than its Otsu threshold on max(R, G, B) (coloured papers and red seals stay above it), with a
    hysteresis (CURSIVE: lighter pixels connected to that ink, below weak_scale x the threshold, keep faint ligatures); the
    8-connected ink components with >= keep_frac of their pixels inside the box (cuts the ligatures into the neighbours), minus
    the spec's exclude rectangles;
 2. the crop is warped (bicubic, on the grey level) into the 1024-unit em raster: singles with the larger side = 820 units centred
    at em (512, 388) (Make Me a Hanzi's centre); a work keeps its column as written in ONE em frame shared by its characters (the
    larger side = side_em); thresholded, smoothed (smooth_sigma), specks removed, pin holes filled (loops stay open); CURSIVE:
    where the raw ink is thin (hairlines, radius <= hair_r) a light smoothing is kept instead, grown by hair_grow px;
 3. CURSIVE: the skeleton graph (skimage skeletonize; junctions = crossing number >= 3) is simplified (junctions joined by a short
    edge merged, end branches shorter than spur_em + spur_k x the stroke radius pruned, the shortest first, fans at a blunt end
    with spur_k_fan, edges joined through every two-ended junction) and split into TRAILS by good continuation at every junction
    (the pair of edge ends with the smallest turn <= max_turn_deg goes on; a crossing = two pairs), so a trail runs through
    crossings and loops as a writer's brush does; each trail = one brush contact (xingshu joined region ends within a tolerance);
 4. CURSIVE: every trail is cut into equal pieces of at most seg_mm of centre path on the sheet (a long stroke is several regions,
    so the region-coverage rule holds along its whole length); every ink pixel goes to the piece of its nearest skeleton pixel; a
    piece that is not one simple region (a ring) is cut finer; pieces are dilated 1 px inside the ink (no seams);
 5. outline per piece: cv2 external contour on a 4x raster, light smoothing, approxPolyDP, em coordinates to 0.1 unit (x = column,
    y = 900 - row), one "M x y L ... Z" path; median = the piece's centre path in the trail's direction (a contact's pieces chain
    end to start), resampled to 8-40 points.
Writing direction of a trail: from its end nearer the top (row + 0.3 col smaller); contacts ordered by character, then top to
bottom. Characters of a shared frame: each piece goes to the character whose band (split_src_y) holds its centroid.
"""
from __future__ import annotations

import argparse, json, math, os, sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import cv2
from skimage.morphology import skeletonize

Image.MAX_IMAGE_PIXELS = None
EM = 1024
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ----------------------------------------------------------------------------------------------- 1-2: ink mask in the em raster
def load_ink(t: dict, src: str) -> tuple[np.ndarray, dict]:
    im = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = t["box"]
    pad = int(t.get("pad_px", 24))
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(im.width, x1 + pad), min(im.height, y1 + pad)
    rgb = np.asarray(im.crop((X0, Y0, X1, Y1)), np.float32)
    V = rgb.max(-1)
    inner = V[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
    thr, _ = cv2.threshold(np.clip(inner, 0, 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = float(thr) * float(t.get("thr_scale", 1.0))
    weak = thr * float(t.get("weak_scale", 1.3))         # hysteresis: lighter pixels connected to the ink (thin ligatures) are ink too
    strong = V < thr
    wl, wn = ndimage.label(V < weak, structure=np.ones((3, 3)))
    has_strong = np.zeros(wn + 1, bool)
    has_strong[np.unique(wl[strong])] = True
    has_strong[0] = False
    ink = has_strong[wl]
    for ex in t.get("exclude", []):                       # source-pixel rectangles to drop (a neighbour's ink, a seal's dark rim)
        ink[max(0, ex[1] - Y0):max(0, ex[3] - Y0), max(0, ex[0] - X0):max(0, ex[2] - X0)] = False
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    inbox = np.zeros_like(ink)
    inbox[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
    keep = np.zeros(n + 1, bool)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    ins = np.bincount(lab[inbox].ravel(), minlength=n + 1)
    for j in range(1, n + 1):
        keep[j] = sizes[j] >= int(t.get("min_src_px", 40)) and ins[j] >= float(t.get("keep_frac", 0.5)) * sizes[j]
    kept = keep[lab]
    clip = np.zeros_like(ink)
    m = int(t.get("clip_px", 6))
    clip[max(0, y0 - Y0 - m):y1 - Y0 + m, max(0, x0 - X0 - m):x1 - X0 + m] = True
    kept &= clip
    rr, cc = np.nonzero(kept)
    bb = (rr.min(), rr.max() + 1, cc.min(), cc.max() + 1)
    h, w = bb[1] - bb[0], bb[3] - bb[2]
    side = float(t.get("side_em", 820))
    s = side / max(h, w)
    cy, cx = (bb[0] + bb[1]) / 2.0, (bb[2] + bb[3]) / 2.0
    # em raster (row, col): the glyph's centre at (512, 512) = em (512, 388)
    A = np.array([[s, 0, 512 - s * cx], [0, s, 512 - s * cy]], np.float32)      # crop (col, row) -> raster (col, row)
    Vw = cv2.warpAffine(V, A, (EM, EM), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255.0)
    Kw = cv2.warpAffine(kept.astype(np.float32), A, (EM, EM), flags=cv2.INTER_LINEAR, borderValue=0.0)
    raw = (Vw < weak) & (Kw > 0.5)
    close_r = int(t.get("close_r", 0))                         # dry brush (飛白): a closing fills its white streaks into one stroke
    if close_r > 0:
        yy, xx = np.mgrid[-close_r:close_r + 1, -close_r:close_r + 1]
        raw = ndimage.binary_closing(raw, (xx * xx + yy * yy) <= close_r * close_r) & (Kw > 0.5)
    sig = float(t.get("smooth_sigma", 3.2))
    ink_em = ndimage.gaussian_filter(raw.astype(np.float32), sig) > 0.5
    # hairlines (牵丝, 1-3 source px): the smoothing above would erase them; where the raw ink is thin (radius <= hair_r em px)
    # a light smoothing is kept instead, grown by hair_grow px (a minimum hairline width the brush can make)
    hair_r = float(t.get("hair_r", 3.0))
    if hair_r > 0:
        fine = ndimage.gaussian_filter(raw.astype(np.float32), float(t.get("hair_sigma", 1.0))) > 0.5
        edt = ndimage.distance_transform_edt(fine)
        skf = skeletonize(fine)
        thin = ndimage.binary_dilation(skf & (edt <= hair_r) & ~ink_em, np.ones((3, 3)), iterations=int(hair_r) + 2)
        hair = fine & thin
        hair = ndimage.binary_dilation(hair, np.ones((3, 3)), iterations=int(t.get("hair_grow", 1)))
        ink_em = ink_em | hair
    ink_em = remove_small(ink_em, int(t.get("min_speck_px", 900)))
    holes = ndimage.binary_fill_holes(ink_em) & ~ink_em
    hl, hn = ndimage.label(holes)
    if hn:
        hs = np.bincount(hl.ravel())
        for j in range(1, hn + 1):
            if hs[j] < int(t.get("max_pinhole_px", 500)):
                ink_em[hl == j] = True
    meta = {"source_crop": [int(X0), int(Y0), int(X1), int(Y1)], "box": list(map(int, t["box"])), "otsu_maxrgb": round(thr, 2), "weak_maxrgb": round(weak, 2),
            "scale_em_per_src_px": round(s, 5), "src_bbox_rc": [int(v) for v in bb], "side_em": side,
            "transform": [[round(float(v), 6) for v in row] for row in A]}
    return ink_em, meta


def disk(r: int) -> np.ndarray:
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


def bridge_dashes(ink: np.ndarray, faint: np.ndarray, max_gap: float, min_faint: float, width: int,
                  max_dev_deg: float = 45.0) -> tuple[np.ndarray, int]:
    """A faint stroke that breaks into dashes (dry brush on a fast hairline): join two skeleton ends of the ink when they are at
    most max_gap source px apart, both point towards each other (within max_dev_deg) and at least min_faint of the straight
    corridor between them holds faint ink (`faint`, within 2 px). The joint is a line `width` px wide. Returns (ink, joints)."""
    sk = skeletonize(ink)
    P = np.pad(sk.astype(np.int8), 1)
    ring = [P[0:-2, 1:-1], P[0:-2, 2:], P[1:-1, 2:], P[2:, 2:], P[2:, 1:-1], P[2:, 0:-2], P[1:-1, 0:-2], P[0:-2, 0:-2]]
    nb = sum(r.astype(np.int32) for r in ring)
    ends = np.argwhere(sk & (nb == 1))
    if len(ends) < 2:
        return ink, 0

    def tangent(e):                                       # direction from the skeleton 10 px back to the end
        cur, path = tuple(e), [tuple(e)]
        for _ in range(10):
            nx = [(cur[0] + a, cur[1] + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a or b)
                  and 0 <= cur[0] + a < sk.shape[0] and 0 <= cur[1] + b < sk.shape[1] and sk[cur[0] + a, cur[1] + b]
                  and (cur[0] + a, cur[1] + b) not in path]
            if not nx:
                break
            cur = nx[0]; path.append(cur)
        v = np.asarray(path[0], float) - np.asarray(path[-1], float)
        n = np.linalg.norm(v)
        return v / n if n > 0 and len(path) > 4 else None
    tans = [tangent(e) for e in ends]
    near = ndimage.maximum_filter(faint, size=5)
    cos_min = np.cos(np.radians(max_dev_deg))
    out = ink.copy(); used = set(); joints = 0
    cand = sorted((float(np.hypot(*(ends[i] - ends[j]))), i, j) for i in range(len(ends)) for j in range(i + 1, len(ends))
                  if 3 < np.hypot(*(ends[i] - ends[j])) <= max_gap)
    for d, i, j in cand:
        if i in used or j in used or tans[i] is None or tans[j] is None:
            continue
        u = (ends[j] - ends[i]) / d
        if np.dot(tans[i], u) < cos_min or np.dot(tans[j], -u) < cos_min:
            continue
        n = int(np.ceil(d)) + 1
        rr = np.rint(np.linspace(ends[i][0], ends[j][0], n)).astype(int)
        cc = np.rint(np.linspace(ends[i][1], ends[j][1], n)).astype(int)
        inner = slice(2, max(3, n - 2))
        if near[rr[inner], cc[inner]].mean() < min_faint:
            continue
        line = np.zeros_like(ink)
        line[rr, cc] = True
        out |= ndimage.binary_dilation(line, disk(max(1, width // 2)))
        used.add(i); used.add(j); joints += 1
    return out, joints


def load_ink_v2(t: dict, src: str) -> tuple[np.ndarray, dict]:
    """The ink, version 2 (10-09, after the review of the first prototypes; the rules, the same for every target):
      - threshold: Otsu on max(R, G, B) of the box (lightly blurred, 0.7 px), lighter pixels below weak_scale x the threshold kept
        where they touch that ink (faint 牽絲);
      - 飛白: a closing with a disk of close_r source px fills the dry streaks inside a stroke's envelope;
      - dashes: a faint stroke broken into dashes is joined between two stroke ends that point at each other when the corridor
        between them holds faint ink (bridge_dashes; bridge_gap px at most);
      - exclude rectangles drop a neighbour's ink, a seal or a stain; cut rectangles sever a ligature into a neighbouring character;
      - the components with >= keep_frac of their pixels in the box are kept WHOLE (never clipped at the box); a kept component
        that reaches the crop's edge is reported (meta["touches_edge"]: the box or the pad must grow);
      - edges: in the em raster the signed distance of the ink is smoothed (edge_sigma source px) and cut at 0, except along thin
        strokes (radius <= thin_r em units), which keep their light smoothing: smooth edges, hairlines kept."""
    im = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = t["box"]
    pad = int(t.get("pad_px", 80))
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(im.width, x1 + pad), min(im.height, y1 + pad)
    V = ndimage.gaussian_filter(np.asarray(im.crop((X0, Y0, X1, Y1)), np.float32).max(-1), float(t.get("blur_src", 0.7)))
    inner = V[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
    thr, _ = cv2.threshold(np.clip(inner, 0, 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = float(thr) * float(t.get("thr_scale", 1.0))
    weak = thr * float(t.get("weak_scale", 1.3))
    strong = V < thr
    wl, wn = ndimage.label(V < weak, structure=np.ones((3, 3)))
    hs = np.zeros(wn + 1, bool); hs[np.unique(wl[strong])] = True; hs[0] = False
    ink = hs[wl]
    excl = np.zeros_like(ink)
    for ex in t.get("exclude", []):
        excl[max(0, ex[1] - Y0):max(0, ex[3] - Y0), max(0, ex[0] - X0):max(0, ex[2] - X0)] = True
    ink &= ~excl
    r = int(t.get("close_r", 0))
    if r > 0:
        ink = ndimage.binary_closing(ink, disk(r)) & ~excl
    for cr in t.get("close_regions", []):                       # 飛白 inside one stroke: fill its streaks there only
        a0, b0, a1, b1, rr_ = cr
        sl = (slice(max(0, b0 - Y0), max(0, b1 - Y0)), slice(max(0, a0 - X0), max(0, a1 - X0)))
        ink[sl] = ndimage.binary_closing(ink[sl], disk(int(rr_)), border_value=0) | ink[sl]
    joints = 0
    for poly, wpx in t.get("bridge_lines", []):                 # a faint 牽絲 seen as dashes in the scan, joined along its path
        line = np.zeros_like(ink)
        for (xa, ya), (xb, yb) in zip(poly[:-1], poly[1:]):
            n = int(np.ceil(np.hypot(xb - xa, yb - ya))) + 1
            line[np.clip(np.rint(np.linspace(ya, yb, n)).astype(int) - Y0, 0, ink.shape[0] - 1),
                 np.clip(np.rint(np.linspace(xa, xb, n)).astype(int) - X0, 0, ink.shape[1] - 1)] = True
        ink |= ndimage.binary_dilation(line, disk(max(1, int(wpx) // 2)))
        joints += 1
    if float(t.get("bridge_gap", 0)) > 0:
        faint = (V < thr * float(t.get("faint_scale", 1.45))) & ~excl
        ink, nj = bridge_dashes(ink, faint, float(t.get("bridge_gap", 30)), float(t.get("bridge_faint", 0.3)), int(t.get("bridge_w", 3)))
        joints += nj
    for cu in t.get("cut", []):
        ink[max(0, cu[1] - Y0):max(0, cu[3] - Y0), max(0, cu[0] - X0):max(0, cu[2] - X0)] = False
    holes = ndimage.binary_fill_holes(ink) & ~ink
    hl, hn = ndimage.label(holes)
    if hn:
        hsz = np.bincount(hl.ravel())
        ink |= (hsz < int(t.get("max_pinhole_src", 25)))[hl] & (hl > 0)
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    inbox = np.zeros_like(ink); inbox[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
    sizes = np.bincount(lab.ravel(), minlength=n + 1); ins = np.bincount(lab[inbox].ravel(), minlength=n + 1)
    keep = (sizes >= int(t.get("min_src_px", 40))) & (ins >= float(t.get("keep_frac", 0.5)) * sizes); keep[0] = False
    kept = keep[lab]
    edge = np.zeros_like(kept); edge[[0, -1], :] = True; edge[:, [0, -1]] = True
    touches = bool((kept & edge).any())
    rr, cc = np.nonzero(kept)
    bb = (rr.min(), rr.max() + 1, cc.min(), cc.max() + 1)
    h, w = bb[1] - bb[0], bb[3] - bb[2]
    side = float(t.get("side_em", 820))
    s = side / max(h, w)
    cy, cx = (bb[0] + bb[1]) / 2.0, (bb[2] + bb[3]) / 2.0
    A = np.array([[s, 0, 512 - s * cx], [0, s, 512 - s * cy]], np.float32)
    soft = ndimage.gaussian_filter(kept.astype(np.float32), 0.6)
    Fw = cv2.warpAffine(soft, A, (EM, EM), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
    base = Fw >= 0.5
    sdf = ndimage.distance_transform_edt(base) - ndimage.distance_transform_edt(~base)
    smooth = ndimage.gaussian_filter(sdf, float(t.get("edge_sigma", 1.6)) * s) > 0
    thin_r = float(t.get("thin_r", 3.5)) * (s / 2.5) if t.get("thin_r_scaled", True) else float(t.get("thin_r", 3.5))
    skb = skeletonize(base)
    thin = ndimage.binary_dilation(skb & (sdf <= max(thin_r, 3.0)), disk(int(np.ceil(max(thin_r, 3.0))) + 2))
    ink_em = smooth | (base & thin)
    ink_em = ndimage.binary_closing(ink_em, disk(2))
    ink_em = remove_small(ink_em, int(t.get("min_speck_px", 600)))
    holes = ndimage.binary_fill_holes(ink_em) & ~ink_em
    hl, hn = ndimage.label(holes)
    if hn:
        hsz = np.bincount(hl.ravel())
        ink_em |= (hsz < int(t.get("max_pinhole_px", 500)))[hl] & (hl > 0)
    meta = {"source_crop": [int(X0), int(Y0), int(X1), int(Y1)], "box": list(map(int, t["box"])), "ink_v": 2, "otsu_maxrgb": round(thr, 2),
            "scale_em_per_src_px": round(s, 5), "src_bbox_rc": [int(v) for v in bb], "side_em": side, "joints": joints,
            "touches_edge": touches, "transform": [[round(float(v), 6) for v in row] for row in A]}
    return ink_em, meta


def remove_small(m: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return m
    sz = np.bincount(lab.ravel())
    ok = sz >= min_px
    ok[0] = False
    return ok[lab]


# ----------------------------------------------------------------------------------------------- 3: skeleton graph
def skeleton_graph(sk: np.ndarray) -> tuple[list[dict], list[dict]]:
    """Nodes {"kind": "j" (junction cluster: crossing number >= 3) | "e" (end), "rc": centre (row, col)} and edges {"a", "b",
    "path": [(r, c), ...]} (the skeleton pixels between two nodes, both node pixels included); a closed curve without nodes gets one
    node of its own."""
    H, W = sk.shape
    P = np.pad(sk.astype(np.int8), 1)
    ring = [P[0:-2, 1:-1], P[0:-2, 2:], P[1:-1, 2:], P[2:, 2:], P[2:, 1:-1], P[2:, 0:-2], P[1:-1, 0:-2], P[0:-2, 0:-2]]
    cn = sum(np.abs(ring[i].astype(np.int32) - ring[(i + 1) % 8]) for i in range(8)) // 2
    nb = sum(r.astype(np.int32) for r in ring)
    jpx = sk & (cn >= 3)
    epx = sk & ((cn <= 1) | (nb <= 1)) & ~jpx
    jl, jn = ndimage.label(ndimage.binary_dilation(jpx, np.ones((3, 3))) & sk, structure=np.ones((3, 3)))
    nodes, node_of = [], {}
    for j in range(1, jn + 1):
        rr, cc = np.nonzero(jl == j)
        k = len(nodes)
        nodes.append({"kind": "j", "rc": (float(rr.mean()), float(cc.mean()))})
        for p in zip(rr.tolist(), cc.tolist()):
            node_of[p] = k
    for r, c in zip(*np.nonzero(epx)):
        p = (int(r), int(c))
        if p not in node_of:
            node_of[p] = len(nodes)
            nodes.append({"kind": "e", "rc": (float(r), float(c))})
    edges, used, used_pairs = [], set(), set()
    nbrs = lambda q: [(q[0] + dr, q[1] + dc) for dr, dc in N8 if 0 <= q[0] + dr < H and 0 <= q[1] + dc < W and sk[q[0] + dr, q[1] + dc]]
    for p0, k0 in list(node_of.items()):
        for q in nbrs(p0):
            if q in node_of:
                k1 = node_of[q]
                if k1 != k0 and (min(k0, k1), max(k0, k1)) not in used_pairs:
                    used_pairs.add((min(k0, k1), max(k0, k1)))
                    edges.append({"a": k0, "b": k1, "path": [p0, q]})
                continue
            if q in used:
                continue
            path, prev, cur = [p0, q], p0, q
            used.add(q)
            end = None
            while True:
                cand = [z for z in nbrs(cur) if z != prev and z not in path[-4:]]
                hit = [z for z in cand if z in node_of and (node_of[z] != k0 or len(path) > 4)]
                if hit:
                    end = node_of[hit[0]]; path.append(hit[0]); break
                free = sorted([z for z in cand if z not in used and z not in node_of], key=lambda z: abs(z[0] - cur[0]) + abs(z[1] - cur[1]))
                if not free:
                    break
                prev, cur = cur, free[0]
                used.add(cur); path.append(cur)
            if end is not None:
                edges.append({"a": k0, "b": end, "path": path})
    rest = sk.copy()
    for p in node_of:
        rest[p] = False
    for q in used:
        rest[q] = False
    lab, n = ndimage.label(rest, structure=np.ones((3, 3)))
    for j in range(1, n + 1):                                  # closed curves without a node
        rr, cc = np.nonzero(lab == j)
        if len(rr) < 20:
            continue
        mem = set(zip(rr.tolist(), cc.tolist()))
        start = (int(rr[0]), int(cc[0]))
        k = len(nodes)
        nodes.append({"kind": "j", "rc": (float(start[0]), float(start[1]))})
        path, seen, cur = [start], {start}, start
        while True:
            nx = sorted([z for z in nbrs(cur) if z in mem and z not in seen], key=lambda z: abs(z[0] - cur[0]) + abs(z[1] - cur[1]))
            if not nx:
                break
            cur = nx[0]; seen.add(cur); path.append(cur)
        path.append(start)
        edges.append({"a": k, "b": k, "path": path})
    return nodes, edges


def plen(path) -> float:
    P = np.asarray(path, np.float64)
    return float(np.sum(np.hypot(*np.diff(P, axis=0).T))) if len(P) > 1 else 0.0


def degree(edges: list, k: int) -> int:
    return sum((e["a"] == k) + (e["b"] == k) for e in edges)


def join_at(nodes: list, edges: list, k: int) -> bool:
    """A junction with exactly two edge ends (not a loop's own two ends) is no junction: join the two edges through it."""
    inc = []
    for i, e in enumerate(edges):
        if e["a"] == k:
            inc.append((i, True))
        if e["b"] == k:
            inc.append((i, False))
    if len(inc) != 2 or inc[0][0] == inc[1][0]:
        return False
    (i, i_at_a), (j, j_at_a) = inc
    ei, ej = edges[i], edges[j]
    pi = ei["path"][::-1] if i_at_a else ei["path"]            # ends at k
    pj = ej["path"] if j_at_a else ej["path"][::-1]            # starts at k
    a = ei["b"] if i_at_a else ei["a"]
    b = ej["b"] if j_at_a else ej["a"]
    new = {"a": a, "b": b, "path": pi + pj}
    for x in sorted((i, j), reverse=True):
        edges.pop(x)
    edges.append(new)
    nodes[k]["kind"] = "gone"
    return True


def simplify(nodes: list, edges: list, dist: np.ndarray, t: dict) -> None:
    """Merge junctions joined by a short edge (an angled crossing gives two junctions a few pixels apart), prune spurs (an end
    branch at a junction shorter than spur_em + spur_k x the stroke's radius there; the shortest first, one at a time), join edges
    through every two-ended junction."""
    merge_em, merge_k = float(t.get("merge_em", 10)), float(t.get("merge_k", 1.0))
    spur_em, spur_k, spur_k_fan = float(t.get("spur_em", 24)), float(t.get("spur_k", 1.6)), float(t.get("spur_k_fan", 3.5))
    rad = lambda k: float(dist[int(round(nodes[k]["rc"][0])), int(round(nodes[k]["rc"][1]))])
    changed = True
    while changed:
        changed = False
        for i, e in enumerate(edges):                          # merge
            a, b = e["a"], e["b"]
            if a != b and nodes[a]["kind"] == "j" and nodes[b]["kind"] == "j" and plen(e["path"]) < merge_em + merge_k * max(rad(a), rad(b)):
                na, nb_ = degree(edges, a), degree(edges, b)
                w = na / (na + nb_)
                nodes[a]["rc"] = tuple(w * np.asarray(nodes[a]["rc"]) + (1 - w) * np.asarray(nodes[b]["rc"]))
                for e2 in edges:
                    if e2 is e:
                        continue
                    if e2["a"] == b:
                        e2["a"] = a; e2["path"] = e["path"] + e2["path"] if e["a"] == a else e["path"][::-1] + e2["path"]
                    if e2["b"] == b:
                        e2["b"] = a; e2["path"] = e2["path"] + (e["path"][::-1] if e["a"] == a else e["path"])
                nodes[b]["kind"] = "gone"
                edges.pop(i)
                changed = True
                break
        if changed:
            continue
        spurs, at_j = [], {}
        for i, e in enumerate(edges):
            a, b = e["a"], e["b"]
            if a == b:
                continue
            kinds = (nodes[a]["kind"], nodes[b]["kind"])
            if set(kinds) != {"e", "j"}:
                continue
            j = a if kinds[0] == "j" else b
            if degree(edges, j) < 3:
                continue
            at_j.setdefault(j, []).append((plen(e["path"]), i))
        for j, lst in at_j.items():
            lst.sort()
            for n_, (L, i) in enumerate(lst):
                # a fan of end branches at one junction (a blunt end of a wide stroke): all but the longest may be longer
                k_ = spur_k_fan if (len(lst) >= 2 and n_ < len(lst) - 1) else spur_k
                if L < spur_em + k_ * rad(j):
                    spurs.append((L, i, j))
        if spurs:
            L, i, j = min(spurs)
            e = edges.pop(i)
            other = e["b"] if e["a"] == j else e["a"]
            nodes[other]["kind"] = "gone"
            changed = True
            continue
        for k, nd in enumerate(nodes):
            if nd["kind"] == "j" and join_at(nodes, edges, k):
                changed = True
                break


def end_dir(nodes: list, edges: list, ei: int, at_a: bool, dist_px: float = 40.0) -> np.ndarray:
    """Unit direction (row, col) in which edge ei leaves its node (its a end if at_a): from the node to the path point dist_px along
    (half the edge if shorter)."""
    path = edges[ei]["path"] if at_a else edges[ei]["path"][::-1]
    P = np.asarray(path, np.float64)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    i = int(np.searchsorted(d, min(dist_px, 0.5 * d[-1])))
    v = P[min(max(i, 1), len(P) - 1)] - np.asarray(nodes[edges[ei]["a"] if at_a else edges[ei]["b"]]["rc"])
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def trails(nodes: list, edges: list, max_turn_deg: float) -> list[list[tuple[int, bool]]]:
    """Edges chained through junctions by good continuation: at every junction the pair of edge ends with the smallest turn is
    joined first (a crossing = two pairs), pairs turning more than max_turn_deg are not. A trail = [(edge, forward), ...]."""
    ends_at = {}
    for ei, e in enumerate(edges):
        ends_at.setdefault(e["a"], []).append((ei, True))
        ends_at.setdefault(e["b"], []).append((ei, False))
    pair = {}
    for k, ends in ends_at.items():
        if nodes[k]["kind"] != "j" or len(ends) < 2:
            continue
        dirs = {x: end_dir(nodes, edges, x[0], x[1]) for x in ends}
        cand = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                a, b = ends[i], ends[j]
                if a[0] == b[0]:
                    continue                                   # a loop's two ends at its own node
                turn = 180.0 - math.degrees(math.acos(float(np.clip(np.dot(dirs[a], dirs[b]), -1, 1))))
                cand.append((turn, a, b))
        used = set()
        for turn, a, b in sorted(cand, key=lambda x: x[0]):
            if turn > max_turn_deg or a in used or b in used:
                continue
            used.add(a); used.add(b); pair[a] = b; pair[b] = a
    done, out = set(), []

    def walk(ei: int, fwd: bool):
        tr = []
        while ei not in done:
            done.add(ei); tr.append((ei, fwd))
            nxt = pair.get((ei, not fwd))                       # leaving through b when walked forward
            if nxt is None:
                break
            ei, fwd = nxt
        return tr
    for ei in range(len(edges)):
        if ei in done:
            continue
        for fwd in (True, False):
            if (ei, fwd) not in pair:
                out.append(walk(ei, fwd)); break
    for ei in range(len(edges)):
        if ei not in done:
            out.append(walk(ei, True))
    return [t for t in out if t]


def trail_path(edges: list, tr) -> np.ndarray:
    pts = []
    for ei, fwd in tr:
        p = edges[ei]["path"] if fwd else edges[ei]["path"][::-1]
        if pts and tuple(pts[-1]) == tuple(p[0]):
            p = p[1:]
        pts.extend(p)
    return np.asarray(pts, np.float64)


# ----------------------------------------------------------------------------------------------- 4: pieces along the trails
def pieces(ink: np.ndarray, paths: list[np.ndarray], seg_em: float, min_piece_px: int) -> tuple[np.ndarray, list, list]:
    """Label every ink pixel with the piece (trail t, part i) of its nearest centre-path pixel. Each trail is cut into
    n = ceil(L / seg_em) equal parts. Returns (label raster (0 = paper), [(t, i)] per label, [centre path (N, 2) rows/cols] per label)."""
    lab_sk = np.zeros(ink.shape, np.int32)
    keys, meds = [], []
    for t, P in enumerate(paths):
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))] if len(P) > 1 else np.zeros(1)
        L = float(d[-1])
        n = max(1, int(math.ceil(L / seg_em - 1e-9)))
        cuts = np.linspace(0, L, n + 1)
        for i in range(n):
            sel = (d >= cuts[i] - 1e-9) & (d <= cuts[i + 1] + 1e-9)
            Q = P[sel]
            if len(Q) == 0:
                continue
            keys.append((t, i)); meds.append(Q)
            lid = len(keys)
            rr = np.clip(np.rint(Q[:, 0]).astype(int), 0, ink.shape[0] - 1)
            cc = np.clip(np.rint(Q[:, 1]).astype(int), 0, ink.shape[1] - 1)
            free = lab_sk[rr, cc] == 0
            lab_sk[rr[free], cc[free]] = lid
    if not keys:
        return np.zeros(ink.shape, np.int32), [], []
    _, (ir, ic) = ndimage.distance_transform_edt(lab_sk == 0, return_indices=True)
    lab = lab_sk[ir, ic] * ink
    return lab.astype(np.int32), keys, meds


def clean_pieces(lab: np.ndarray, ink: np.ndarray) -> np.ndarray:
    """Each piece one 8-connected part: smaller parts go to the neighbouring piece they share most border with."""
    out = lab.copy()
    for _ in range(3):
        changed = False
        for r in range(1, int(out.max()) + 1):
            m = out == r
            if not m.any():
                continue
            cl, cn = ndimage.label(m, structure=np.ones((3, 3)))
            if cn <= 1:
                continue
            sz = np.bincount(cl.ravel()); sz[0] = 0
            big = int(np.argmax(sz))
            for j in range(1, cn + 1):
                if j == big:
                    continue
                part = cl == j
                ring = ndimage.binary_dilation(part, np.ones((3, 3))) & ~part & ink
                nb = out[ring]
                nb = nb[(nb != r) & (nb != 0)]
                if len(nb):
                    out[part] = np.bincount(nb).argmax()
                    changed = True
        if not changed:
            break
    return out


def has_hole(m: np.ndarray) -> bool:
    return bool((ndimage.binary_fill_holes(m) & ~m).sum() > 0)


# ----------------------------------------------------------------------------------------------- 5: outlines and medians
def outline(m: np.ndarray, eps: float = 0.9, max_pts: int = 400) -> list[tuple[int, int]]:
    rr, cc = np.nonzero(m)
    r0, c0 = max(0, rr.min() - 2), max(0, cc.min() - 2)
    sub = m[r0:rr.max() + 3, c0:cc.max() + 3]
    big = np.kron(sub.astype(np.uint8), np.ones((4, 4), np.uint8))     # 4x: the contour runs 1/8 px inside the pixel edges
    cs, _ = cv2.findContours(big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float64)
    c = (c + 0.5) / 4.0 - 0.5 + np.array([c0, r0], np.float64)        # (N, 2) x = col, y = row in the raster
    if len(c) > 40:                                                     # circular smoothing (~1.5 px)
        k = np.exp(-0.5 * (np.arange(-12, 13) / 5.0) ** 2); k /= k.sum()
        c = np.stack([np.convolve(np.r_[c[-12:, j], c[:, j], c[:12, j]], k, mode="valid") for j in range(2)], 1)
    a = cv2.approxPolyDP(c.astype(np.float32).reshape(-1, 1, 2), eps, True)[:, 0, :]
    while len(a) > max_pts:
        eps *= 1.3
        a = cv2.approxPolyDP(c.astype(np.float32).reshape(-1, 1, 2), eps, True)[:, 0, :]
    pts = [(round(float(x), 1), round(float(y), 1)) for x, y in a]
    dedup = [pts[0]] + [p for i, p in enumerate(pts[1:]) if p != pts[i]]
    return dedup


def svg_of(pts_colrow: list[tuple[float, float]]) -> str:
    em = [(x, round(900 - y, 1)) for x, y in pts_colrow]
    return "M " + " L ".join(f"{x:g} {y:g}" for x, y in em) + " Z"


def median_em(Q: np.ndarray) -> list[list[int]]:
    """Centre path (rows, cols) -> 8..40 em points [x, y] (x = col, y = 900 - row), lightly smoothed."""
    if len(Q) >= 5:
        k = np.ones(5) / 5
        Qs = np.stack([np.convolve(np.r_[[Q[0, j]] * 2, Q[:, j], [Q[-1, j]] * 2], k, mode="valid") for j in range(2)], 1)
    else:
        Qs = Q
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Qs, axis=0).T))] if len(Qs) > 1 else np.zeros(1)
    n = int(np.clip(round(d[-1] / 12.0) + 1, 8, 40)) if d[-1] > 0 else 2
    s = np.linspace(0, d[-1], n)
    r = np.interp(s, d, Qs[:, 0]); c = np.interp(s, d, Qs[:, 1])
    return [[int(round(cc)), int(round(900 - rr))] for rr, cc in zip(r, c)]


# ----------------------------------------------------------------------------------------------- polygon check (the scorer's raster)
def poly_mask(pts_colrow, shape) -> np.ndarray:
    from matplotlib.path import Path as MPath
    P = np.asarray(pts_colrow, np.float64)
    m = np.zeros(shape, bool)
    c0, c1 = max(0, int(P[:, 0].min())), min(shape[1] - 1, int(P[:, 0].max()) + 1)
    r0, r1 = max(0, int(P[:, 1].min())), min(shape[0] - 1, int(P[:, 1].max()) + 1)
    uu, vv = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
    m[r0:r1 + 1, c0:c1 + 1] = MPath(P).contains_points(np.stack([uu.ravel(), vv.ravel()], 1).astype(float)).reshape(uu.shape)
    return m


def self_intersects(pts) -> bool:
    P = np.asarray(pts, np.float64)
    n = len(P)
    S = [(P[i], P[(i + 1) % n]) for i in range(n)]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    for i in range(n):
        a, b = S[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = S[j]
            if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]) or max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
                continue
            d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
            if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 < 0 and d3 * d4 < 0:
                return True
    return False


# ----------------------------------------------------------------------------------------------- main
def build(t: dict, src: str, out: str) -> dict:
    os.makedirs(out, exist_ok=True)
    ink, meta = (load_ink_v2 if int(t.get("ink_v", 1)) == 2 else load_ink)(t, src)
    dist = ndimage.distance_transform_edt(ink)
    nodes, edges = skeleton_graph(skeletonize(ink))
    simplify(nodes, edges, dist, t)
    trs = trails(nodes, edges, float(t.get("max_turn_deg", 75)))
    paths = [trail_path(edges, tr) for tr in trs]
    # tiny trails hanging on another trail's ink (outline bumps) go; a tiny trail that is a whole ink component (a dot) stays
    comp, _ = ndimage.label(ink, structure=np.ones((3, 3)))
    cid = lambda P: comp[int(np.clip(round(P[len(P) // 2, 0]), 0, EM - 1)), int(np.clip(round(P[len(P) // 2, 1]), 0, EM - 1))]
    min_trail = float(t.get("min_trail_em", 40))
    keep = []
    for i, P in enumerate(paths):
        L = plen(P)
        if L < min_trail and any(cid(Q) == cid(P) and plen(Q) >= min_trail for j, Q in enumerate(paths) if j != i):
            continue
        keep.append(i)
    trs = [trs[i] for i in keep]; paths = [paths[i] for i in keep]
    # direction: start at the end nearer the top (row + 0.3 col)
    for i, P in enumerate(paths):
        if len(P) > 1 and (P[-1, 0] + 0.3 * P[-1, 1]) < (P[0, 0] + 0.3 * P[0, 1]):
            paths[i] = P[::-1]
    # drop trails that are pure skeleton noise (shorter than 6 units) unless they are a whole component
    em_mm = float(t.get("box_mm", 150.0)) / EM
    seg = float(t.get("seg_mm", 30.0)) / em_mm                  # a region = at most seg_mm of centre path on the sheet
    for it in range(6):
        lab, keys, meds = pieces(ink, paths, seg, 0)
        lab = clean_pieces(lab, ink)
        bad = [r for r in range(1, len(keys) + 1) if (lab == r).any() and has_hole(lab == r)]
        if not bad:
            break
        seg *= 0.7                                              # a ring piece: cut finer
    # renumber pieces in writing order: contacts (trails) ordered by character band, then by the start's row
    chars = t["chars"]
    A = np.asarray(meta["transform"]); Y0 = meta["source_crop"][1]
    splits = [float(A[1, 1] * (y - Y0) + A[1, 2]) for y in t.get("split_src_y", [])]   # raster rows between the characters (shared frame)
    meta["split_rows_em"] = [round(v, 1) for v in splits]

    def char_of_rc(r: float) -> int:
        return int(sum(r > s for s in splits))
    tr_order = sorted(range(len(paths)), key=lambda i: (char_of_rc(paths[i][0, 0]), paths[i][0, 0] + 0.3 * paths[i][0, 1]))
    pieces_out = []                                             # {"label", "trail", "part", "char"}
    for ti in tr_order:
        parts = sorted([(k[1], j + 1) for j, k in enumerate(keys) if k[0] == ti])
        for part, lid in parts:
            m = lab == lid
            if m.sum() < 30:
                continue
            rr, cc = np.nonzero(m)
            pieces_out.append({"label": lid, "trail": ti, "part": part, "char": char_of_rc(float(rr.mean()))})
    contacts_lab = []                                           # per contact: [(label, forward)] in writing order
    for ti in tr_order:
        ks = [(p["label"], True) for p in sorted([p for p in pieces_out if p["trail"] == ti], key=lambda p: p["part"])]
        if ks:
            contacts_lab.append(ks)
    L_em = [float(np.sum(np.hypot(*np.diff(P, axis=0).T))) if len(P) > 1 else 0.0 for P in paths]
    extra = {"contact_len_em": [round(L_em[ti], 1) for ti in tr_order if any(p["trail"] == ti for p in pieces_out)],
             "skeleton_nodes": sum(n["kind"] != "gone" for n in nodes), "skeleton_edges": len(edges)}
    return write_outputs(t, out, ink, meta, chars, splits, pieces_out, lab, {k + 1: Q for k, Q in enumerate(meds)}, contacts_lab, extra,
                         {"seg_em_used": round(seg, 1), "box_mm": float(t.get("box_mm", 150.0)), "seg_mm": float(t.get("seg_mm", 30.0))})


def build_xingshu(t: dict, src: str, out: str) -> dict:
    """The xingshu rule on the same ink (the xingshu builder of 2026-09-28 and kaishu/work/k/xs_join.py, as described in their
    REPORT and NOTES), for comparison with the caoshu rule:
      regions  = skeleton branches: spurs < 46 units pruned (no width term), branches meeting at a junction with good continuation
                 (<= 50 deg) merged into one branch, every ink pixel to its nearest branch, pieces < 2600 px merged into the
                 neighbour with the longest border, a ring cut in two (xingshu cut it open with a 4 px gap); no length limit;
      medians  = the branch's centre path, left to right when mostly horizontal, otherwise top to bottom;
      contacts = 連筆: every region has two ports (its median's ends); the closest free port pairs of different regions are joined
                 when they are within 70/1024 of a character's box and the straight connector stays on the ink (dilated by
                 0.67 mm), never closing a cycle (greedy, closest first); each chain = one contact, starting at its upper-left end.
    In a shared frame (a work) a character's box = box_mm / n_chars; joins across characters are allowed there (the ligature is on
    the sheet), unlike xingshu's works, whose boxes cut the ligatures at the crop."""
    os.makedirs(out, exist_ok=True)
    ink, meta = load_ink(t, src)
    dist = ndimage.distance_transform_edt(ink)
    nodes, edges = skeleton_graph(skeletonize(ink))
    simplify(nodes, edges, dist, {"spur_em": t.get("xs_spur_em", 46), "spur_k": 0.0, "spur_k_fan": 0.0,
                                  "merge_em": t.get("merge_em", 10), "merge_k": t.get("merge_k", 1.0)})
    trs = trails(nodes, edges, float(t.get("xs_turn_deg", 50)))
    paths = [trail_path(edges, tr) for tr in trs]
    # rings: a closed branch would be a region with a hole -> two halves
    split = []
    for P in paths:
        if len(P) > 8 and np.hypot(*(P[0] - P[-1])) < 3.0:
            h = len(P) // 2
            split += [P[:h + 1], P[h:]]
        else:
            split.append(P)
    paths = split
    lab, keys, meds = pieces(ink, paths, 1e9, 0)
    lab = clean_pieces(lab, ink)
    for it in range(4):                                        # a piece that still holds a hole: cut its branch in two
        holes = [r for r in range(1, len(keys) + 1) if (lab == r).any() and has_hole(lab == r)]
        if not holes:
            break
        new = []
        for i, P in enumerate(paths):
            if (i + 1) in holes and len(P) > 8:
                h = len(P) // 2
                new += [P[:h + 1], P[h:]]
            else:
                new.append(P)
        paths = new
        lab, keys, meds = pieces(ink, paths, 1e9, 0)
        lab = clean_pieces(lab, ink)
    # small pieces (< min_piece_px) go to the neighbour with the longest border; the neighbour keeps its median
    min_px = int(t.get("xs_min_piece_px", 2600))
    alive = {r for r in range(1, len(keys) + 1) if (lab == r).any()}
    iso = set()                                                # isolated small pieces (a dot of its own) stay
    while True:
        sizes = {r: int((lab == r).sum()) for r in alive - iso}
        small = sorted([r for r in sizes if sizes[r] < min_px], key=lambda r: sizes[r])
        if not small:
            break
        r = small[0]
        m = lab == r
        ring = ndimage.binary_dilation(m, np.ones((3, 3))) & ~m & ink
        nb = lab[ring]; nb = nb[(nb != r) & (nb != 0)]
        if len(nb) == 0:
            iso.add(r)
            continue
        cnt = np.bincount(nb)
        for q in [int(x) for x in np.argsort(-cnt) if cnt[x] > 0]:   # the neighbour sharing the longest border, unless the merge
            if not has_hole((lab == q) | m):                         # would close a ring (a region must stay one simple polygon)
                lab[m] = q
                alive.discard(r)
                break
        else:
            iso.add(r)
    # medians oriented as xingshu's: left to right when mostly horizontal, otherwise top to bottom
    med = {}
    for r in alive:
        Q = meds[r - 1]
        dr_, dc_ = Q[-1, 0] - Q[0, 0], Q[-1, 1] - Q[0, 1]
        if (abs(dc_) >= abs(dr_) and dc_ < 0) or (abs(dc_) < abs(dr_) and dr_ < 0):
            Q = Q[::-1]
        med[r] = Q
    # 連筆 contacts (xs_join.plan_contacts)
    chars = t["chars"]
    A = np.asarray(meta["transform"]); Y0 = meta["source_crop"][1]
    splits = [float(A[1, 1] * (y - Y0) + A[1, 2]) for y in t.get("split_src_y", [])]
    meta["split_rows_em"] = [round(v, 1) for v in splits]
    em_mm = float(t.get("box_mm", 150.0)) / EM
    char_box_mm = float(t.get("box_mm", 150.0)) / (len(chars) if t.get("kind") == "work" else 1)
    tol = 70.0 / 1024.0 * char_box_mm / em_mm                   # in em raster px
    near = ndimage.binary_dilation(ink, np.ones((3, 3)), iterations=max(1, int(round(0.67 / em_mm))))
    R = sorted(alive)
    port = lambda r, e: med[r][0] if e == 0 else med[r][-1]

    def on_ink(a, b, n=25):
        for tt in np.linspace(0, 1, n):
            q = a + (b - a) * tt
            i, j = int(round(q[0])), int(round(q[1]))
            if not (0 <= i < EM and 0 <= j < EM) or not near[i, j]:
                return False
        return True
    cand = []
    for ia, a in enumerate(R):
        for b in R[ia + 1:]:
            for ea in (0, 1):
                for eb in (0, 1):
                    d = float(np.hypot(*(port(a, ea) - port(b, eb))))
                    if d <= tol:
                        cand.append((d, a, ea, b, eb))
    cand.sort()
    grp = {r: r for r in R}

    def find(i):
        while grp[i] != i:
            grp[i] = grp[grp[i]]; i = grp[i]
        return i
    used, link = set(), {}
    for d, a, ea, b, eb in cand:
        if (a, ea) in used or (b, eb) in used or find(a) == find(b):
            continue
        if not on_ink(port(a, ea), port(b, eb)):
            continue
        used.add((a, ea)); used.add((b, eb)); link[(a, ea)] = (b, eb); link[(b, eb)] = (a, ea)
        grp[find(a)] = find(b)
    done, chains = set(), []
    for r0 in R:
        if r0 in done:
            continue
        r, e, seen = r0, 0, set()
        while (r, e) in link and r not in seen:                 # back to the chain's free end
            seen.add(r)
            r2, e2 = link[(r, e)]
            r, e = r2, 1 - e2
        ch = []
        while True:
            ch.append((r, e == 0)); done.add(r)                 # enter r at port e: forward iff e == 0
            ex = (r, 1 - e)
            if ex not in link:
                break
            r, e = link[ex]
            if r in done:
                break
        chains.append(ch)

    def end_key(ch, first=True):
        r, f = ch[0] if first else ch[-1]
        q = (med[r][0] if f else med[r][-1]) if first else (med[r][-1] if f else med[r][0])
        return float(q[0]) + 0.3 * float(q[1])
    chains = [[(r, not f) for r, f in reversed(ch)] if end_key(ch, False) < end_key(ch, True) else ch for ch in chains]

    def char_of_rc(rw: float) -> int:
        return int(sum(rw > s_ for s_ in splits))

    def start_rc(ch):
        r, f = ch[0]
        return med[r][0] if f else med[r][-1]
    chains.sort(key=lambda ch: (char_of_rc(float(start_rc(ch)[0])), float(start_rc(ch)[0]) + 0.3 * float(start_rc(ch)[1])))
    pieces_out = []
    for ci, ch in enumerate(chains):
        for r, f in ch:
            rr, cc = np.nonzero(lab == r)
            pieces_out.append({"label": r, "trail": ci, "part": len(pieces_out), "char": char_of_rc(float(rr.mean()))})
    meds_dir = {}
    for ch in chains:
        for r, f in ch:
            meds_dir[r] = med[r]                                 # stored in xingshu's orientation; the contact keeps the flag
    contacts_lab = [[(r, bool(f)) for r, f in ch] for ch in chains]
    extra = {"contact_len_em": [round(sum(plen(med[r]) for r, _ in ch), 1) for ch in chains],
             "skeleton_nodes": sum(n["kind"] != "gone" for n in nodes), "skeleton_edges": len(edges)}
    return write_outputs(t, out, ink, meta, chars, splits, pieces_out, lab, meds_dir, contacts_lab, extra,
                         {"rule": "xingshu", "join_tol_em": round(tol, 1), "box_mm": float(t.get("box_mm", 150.0))})


def write_outputs(t: dict, out: str, ink: np.ndarray, meta: dict, chars: str, splits: list, pieces_out: list, lab: np.ndarray,
                  meds: dict, contacts_lab: list, extra: dict, tail: dict) -> dict:
    """The exemplar file (graphics.txt), the contacts file and the pictures from the pieces (pieces_out: {"label", "char"} in
    writing order; meds: label -> centre path (rows, cols) in its writing direction; contacts_lab: per contact [(label, forward)])."""
    # group by character (stable), keeping the writing order inside each character
    order = sorted(range(len(pieces_out)), key=lambda i: (pieces_out[i]["char"], i))
    pieces_out = [pieces_out[i] for i in order]
    recs = [{"character": ch, "strokes": [], "medians": []} for ch in chars]
    union = np.zeros(ink.shape, bool)
    polys = []
    for gi, pc in enumerate(pieces_out):
        m = lab == pc["label"]
        m2 = ndimage.binary_dilation(m, np.ones((3, 3))) & ink        # 1 px into the neighbours (no seams)
        pts = outline(m2)
        if self_intersects(pts):
            pts = outline(ndimage.binary_opening(m2, np.ones((3, 3))), eps=1.2)
        polys.append(pts)
        pm = poly_mask(pts, ink.shape)
        union |= pm
        Q = meds[pc["label"]]
        recs[pc["char"]]["strokes"].append(svg_of(pts))
        recs[pc["char"]]["medians"].append(median_em(Q))
    # global stroke index (the instance's order: characters in order, their pieces in writing order)
    gidx = 0
    lab2g = {}
    for ci in range(len(chars)):
        for pc in [p for p in pieces_out if p["char"] == ci]:
            lab2g[pc["label"]] = gidx
            gidx += 1
    contacts = []
    for ks_lab in contacts_lab:
        ks = [(lab2g[lb], f) for lb, f in ks_lab if lb in lab2g]
        if ks:
            contacts.append([[int(k), bool(f)] for k, f in ks])
    inter = (union & ink).sum(); uni = (union | ink).sum()
    iou = float(inter / max(1, uni))
    stats = {"slug": t["slug"], "chars": chars, "n_regions": len(pieces_out), "n_contacts": len(contacts),
             "regions_per_char": [len(r["strokes"]) for r in recs], "contact_regions": [len(c) for c in contacts],
             "contact_len_em": extra["contact_len_em"],
             "skeleton_nodes": extra["skeleton_nodes"], "skeleton_edges": extra["skeleton_edges"], "ink_px": int(ink.sum()), "polygon_iou_vs_mask": round(iou, 4),
             "max_pts": max(len(p) for p in polys), **tail, **meta}
    with open(os.path.join(out, f"{t['slug']}.graphics.txt"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump({"slug": t["slug"], "chars": chars, "contacts": contacts, "stats": stats}, open(os.path.join(out, f"{t['slug']}.contacts.json"), "w"),
              indent=1, ensure_ascii=False)
    # pictures: the ink (black on white), the pieces coloured with their medians and the contacts
    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).save(os.path.join(out, f"{t['slug']}_ink.png"))
    rng = np.random.default_rng(3)
    pal = rng.integers(60, 230, (len(pieces_out) + 1, 3)).astype(np.uint8)
    pic = np.full(ink.shape + (3,), 255, np.uint8)
    for gi, pts in enumerate(polys):
        pm = poly_mask(pts, ink.shape)
        pic[pm] = pal[gi]
    im = Image.fromarray(pic)
    dr = ImageDraw.Draw(im)
    cols = [(200, 0, 0), (0, 0, 200), (0, 140, 0), (160, 0, 160), (200, 120, 0), (0, 150, 150), (90, 90, 90), (120, 60, 0)]
    for ci_, ks in enumerate(contacts):
        col = cols[ci_ % len(cols)]
        for k, _ in ks:
            # find the piece's median in the records
            n = 0
            for r in recs:
                if k < n + len(r["medians"]):
                    med = r["medians"][k - n]
                    break
                n += len(r["medians"])
            P = [(x, 900 - y) for x, y in med]
            dr.line(P, fill=col, width=3)
            dr.ellipse([P[0][0] - 4, P[0][1] - 4, P[0][0] + 4, P[0][1] + 4], fill=col)
            dr.text((P[len(P) // 2][0] + 4, P[len(P) // 2][1]), str(k + 1), fill=(0, 0, 0))
    for s_ in splits:
        dr.line([(0, s_), (EM, s_)], fill=(255, 0, 0), width=1)
    im.save(os.path.join(out, f"{t['slug']}_pieces.png"))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True); ap.add_argument("--slug", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--source-dir", help="where the source scan lies (default: the spec's directory)")
    ap.add_argument("--rule", choices=("caoshu", "xingshu"), default="caoshu",
                    help="caoshu: trails by smoothest continuation, regions <= seg_mm; xingshu: its branch regions and 70-em joins")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    t = next(x for x in spec["targets"] if x["slug"] == a.slug)
    src = t.get("source") or spec["source"]["file"]
    if not os.path.isabs(src):
        src = os.path.join(a.source_dir or os.path.dirname(os.path.abspath(a.spec)), src)
    st = (build_xingshu if a.rule == "xingshu" else build)(t, src, a.out)
    print(json.dumps(st, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
