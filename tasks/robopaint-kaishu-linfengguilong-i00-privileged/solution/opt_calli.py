"""Reference planner for the RoboPaint calligraphy oracles (kaishu, xingshu), step 1 (robot-free; solution/ only, never in the agent
image; run at generation time on the graders' copy of the instance).

Trajectory optimisation against the task's brush model (rcb_brush.WangBrush / CalligraphyPainter), in the spirit of Wang et al.
2020 Sec. V (optimise each stroke's end-effector path against the rendered stroke), with our own parametrisation: K control points
(x, y, press z) of the handle (tip) path, a Catmull-Rom curve through them in xy, z interpolated linearly, sampled every `step_m`
(the model has no speed term). Initialisation = the exact inverse of the brush's trailing dynamics for a taut "leash": the mark's
root follows the handle like a trailer, so a root that traces a centre path needs the handle Offset(z) ahead along its tangent,
with z from the local width (twice the distance to the ink's edge, through the inverse Width line). Objective: scipy
least_squares (trf, finite differences) on the rendered coverage vs the ink of the stroke on a 512 px grid of the sheet, the
other strokes' ink being "don't care", plus a small smoothness term on z.

How the brush meets the paper (stroke_path; plans.json "entry" / "exit", read by ref_calli.py on the robot):
  - entry "vertical": a 4 mm approach along the first tangent 4 mm above the paper, a vertical touch-down; "diagonal": a straight
    8 mm line along the first tangent from 4 mm above the paper down to the first point, without a stop above it (a stop makes
    the arm rebound, and the brush, whose angle follows any motion in the air, then meets the paper with its drag tail turned
    against the stroke);
  - exit "vertical": a vertical lift; "diagonal": a straight 8 mm line along the last tangent up to 4 mm above the paper (it leaves
    a needle tail); "return" (回锋): back onto the mark's root while lifting, so the root stays and the stroke's end stays blunt.

Two planners:
  - the per-stroke planner (default; the earlier references): one plan per exemplar stroke along its Make Me a Hanzi median,
    K = one control point per 10 mm (4-14), 25 iterations;
  - v2, --profile print (2026-10-09, a print-like copy): one plan per brush contact (kaishu: a stroke; xingshu: the contacts of a
    connected-stroke plan, --contacts-from), each region's centre path a walk over its skeleton that covers every branch,
    diagonal entry and return exit, a minimum press, denser control points, a weighted residual and boost rounds (PROFILES,
    plan_v2).

    python opt_calli.py --instance <full instance.json> --graphics graphics.txt --out plans.json [--nfev 25] [--entry diagonal]
    python opt_calli.py --instance <full instance.json> --graphics graphics.txt --out plans.json --profile print [--contacts-from
        <plans.json with "contacts">] [--workers 16]
"""
from __future__ import annotations
import argparse, heapq, json, math, os, sys, time
if __name__ == "__main__":         # one BLAS thread before numpy loads: the plans must not depend on the host's core count
    for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[_v] = "1"
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


def stroke_path(P: np.ndarray, paper_z: float, step: float, entry: str = "vertical", exit: str | None = None) -> np.ndarray:
    """Handle (tip) samples (N, 3) for one stroke plan P (K, 3: x, y, press): approach, touch-down, body, lift (entry "vertical"), or
    entry line, body, exit line (entry "diagonal")."""
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
    exit = entry if exit is None else exit
    if entry == "diagonal":
        t1 = xy_r[-1] - xy_r[max(0, len(xy_r) - 4)]; t1 = t1 / max(1e-9, np.linalg.norm(t1))
        L = 0.008
        A = np.r_[xy_r[0] - t0 * L, above]; Bp = np.r_[xy_r[0], -z_r[0]]
        n_dn = max(1, int(round(np.linalg.norm(Bp - A) / step)))
        down = [A + (Bp - A) * a for a in np.linspace(0, 1, n_dn + 1)[:-1]]
        C = np.r_[xy_r[-1], -z_r[-1]]
        if exit == "diagonal":
            D = np.r_[xy_r[-1] + t1 * L, above]
        elif exit == "vertical":
            D = np.r_[xy_r[-1], above]
        elif exit == "return":           # 回锋: back onto the mark's root while lifting, so the root stays and the end stays blunt
            back = max(0.0, float(np.polyval(B.BRUSH_WANG["offset_cm"], min(z_r[-1], B.BRUSH_WANG["z_max_cm"] / 100) * 100)) / 100)
            D = np.r_[xy_r[-1] - t1 * back, above]
        else:
            raise ValueError(f"exit {exit!r}: vertical, diagonal or return")
        n_up = max(1, int(round(np.linalg.norm(D - C) / step)))
        up = [C + (D - C) * a for a in np.linspace(0, 1, n_up + 1)[1:]]
        H = np.vstack([np.asarray(down), np.c_[xy_r, -z_r], np.asarray(up)])
        H[:, 2] = paper_z + H[:, 2]
        return H
    if entry != "vertical":
        raise ValueError(f"entry {entry!r}: vertical or diagonal")
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
    def __init__(self, wc: World, median_units: list, k: int, step_m: float = 4e-4, entry: str = "vertical"):
        self.Wc, self.k, self.step, self.entry = wc, k, step_m, entry
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
        for p in stroke_path(P, B.PAPER_Z, self.step, self.entry):
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


# --------------------------------------------------------------------------- v2 (2026-10-09): a print-like copy
# One plan per brush contact (kaishu: an exemplar stroke; xingshu: the contacts of a connected-stroke plan, --contacts-from), K
# control points along the contact's centre path, optimised against the brush model with a weighted residual. What it adds to
# the per-stroke planner above (--profile print, the profile's values in PROFILES):
#   - the centre path of a region is a walk over its skeleton between the ends of its median that covers every branch (loops
#     followed round, side branches out and back; the brush is lifted to the minimum press where the walk turns back); the walk
#     may end elsewhere when that makes it much shorter (route_free_end: a region whose median covers only part of its ink,
#     e.g. a hook merged with the next stroke, is written in one pass instead of out and back);
#   - the brush enters the paper on a line along the stroke and leaves it back onto its own root (stroke_path entry "diagonal",
#     exit "return"): no turned drag tail at the touch-down, no needle tail at the end;
#   - a minimum press along the whole contact (it never breaks into two contacts on the robot), denser control points (kstep_mm),
#     more iterations, stray ink > 1 mm from the exemplar weighted up (w_far);
#   - boost rounds: the contacts holding a region whose robot-free coverage is under cov_target are re-optimised with the missing
#     ink weighted up;
#   - the finite-difference Jacobian is computed by `workers` processes (fork); the result does not depend on their number.
PROFILES = {"print": {"res": 512, "kstep_mm": 6.0, "kmax": 30, "nfev": 50, "entry": "diagonal", "exit": "return", "w_in": 1.0,
                      "w_near": 1.0, "w_far": 1.5, "z_min": 0.0006, "tip_r_mm": 1.5, "prune_mm": 1.5, "route_max_ratio": 4.0,
                      "route_free_end": 0.8,
                      "detour_margin_mm": 1.0, "detour_min_mm2": 3.0, "init_inside": 0.6, "step_m": 4e-4, "boost_rounds": 2,
                      "cov_target": 0.92, "boost_w_in": 3.0, "boost_w_far": 3.0, "boost_nfev": 40,
                      "candidates": [{"route": "median", "detours": False}, {"route": "skeleton", "detours": False},
                                     {"route": "median", "detours": True}]}}
_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def thin(img: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning of a boolean image."""
    im = img.astype(np.uint8).copy()
    while True:
        changed = False
        for step in (0, 1):
            P = np.pad(im, 1)
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            Bn = p2.astype(int) + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(int) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            m = (im == 1) & (Bn >= 2) & (Bn <= 6) & (A == 1) & c
            if m.any():
                im[m] = 0; changed = True
        if not changed:
            return im.astype(bool)


def graph(sk: np.ndarray):
    """Nodes (endpoints, junction clusters) and edges (pixel chains) of a skeleton."""
    pts = set(zip(*np.nonzero(sk)))
    nb = lambda p: [(p[0] + a, p[1] + b) for a, b in _N8 if (p[0] + a, p[1] + b) in pts]
    deg = {p: len(nb(p)) for p in pts}
    junc = np.zeros(sk.shape, bool)
    for p, d in deg.items():
        if d >= 3:
            junc[p] = True
    lab, nj = ndimage.label(junc, structure=np.ones((3, 3)))
    node_of = {}
    nodes = []
    for j in range(1, nj + 1):
        rr, cc = np.nonzero(lab == j)
        nodes.append((float(rr.mean()), float(cc.mean())))
        for p in zip(rr, cc):
            node_of[p] = len(nodes) - 1
    for p, d in deg.items():
        if d <= 1 and p not in node_of:
            nodes.append((float(p[0]), float(p[1]))); node_of[p] = len(nodes) - 1
    edges, seen = [], set()
    for p0, n0 in list(node_of.items()):
        for q in nb(p0):
            if q in node_of:
                if node_of[q] != n0 and (min(p0, q), max(p0, q)) not in seen and q not in [r for r in nb(p0) if node_of.get(r) == n0 and r != q]:
                    seen.add((min(p0, q), max(p0, q)))
                    if node_of[q] != n0:
                        edges.append([n0, node_of[q], [p0, q]])
                continue
            if (p0, q) in seen:
                continue
            chain, prev, cur = [p0, q], p0, q
            while cur not in node_of:
                nxt = [r for r in nb(cur) if r != prev and r not in chain[-3:]]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                chain.append(cur)
            seen.add((p0, q)); seen.add((chain[-1], chain[-2]))
            end = node_of.get(cur)
            if end is None:                                  # a dead end that is not a node (should not happen)
                nodes.append((float(cur[0]), float(cur[1]))); end = len(nodes) - 1; node_of[cur] = end
            edges.append([n0, end, chain])
    # pure loops (no node at all): one node on the ring
    if not nodes and pts:
        p0 = min(pts)
        nodes.append((float(p0[0]), float(p0[1]))); node_of[p0] = 0
        chain, prev, cur = [p0], None, p0
        while True:
            nxt = [r for r in nb(cur) if r != prev and r not in chain[-2:]]
            if not nxt or nxt[0] == p0:
                break
            prev, cur = cur, nxt[0]; chain.append(cur)
            if len(chain) > len(pts) + 2:
                break
        chain.append(p0)
        edges.append([0, 0, chain])
    return nodes, edges


def elen(e):
    c = np.asarray(e[2], float)
    return float(np.sum(np.hypot(*np.diff(c, axis=0).T))) if len(c) > 1 else 0.0


def prune(nodes, edges, min_len):
    while True:
        deg = [0] * len(nodes)
        for u, v, _ in edges:
            deg[u] += 1; deg[v] += 1
        drop = [i for i, (u, v, c) in enumerate(edges) if u != v and (deg[u] == 1 or deg[v] == 1) and elen((u, v, c)) < min_len and len(edges) > 1]
        if not drop:
            return edges
        edges = [e for i, e in enumerate(edges) if i != drop[0]]


def shortest(nodes, edges, s):
    adj = {}
    for i, (u, v, c) in enumerate(edges):
        L = elen((u, v, c)); adj.setdefault(u, []).append((v, L, i)); adj.setdefault(v, []).append((u, L, i))
    dist, prev = {s: 0.0}, {}
    h = [(0.0, s)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, 1e18):
            continue
        for v, L, i in adj.get(u, []):
            if d + L < dist.get(v, 1e18):
                dist[v] = d + L; prev[v] = (u, i); heapq.heappush(h, (d + L, v))
    return dist, prev


def skeleton_route(mask: np.ndarray, start_px, end_px, prune_px: float, free_end: float = 0.0):
    """A covering walk over mask's skeleton from the node nearest start_px to the node nearest end_px:
    -> (pixel polyline (N, 2) as (row, col), tip pixels where the walk turns back, whether it ends at the node nearest end_px).
    free_end > 0: the walk may end at another node if that makes it shorter than free_end x the walk to end_px."""
    sk = thin(mask)
    if sk.sum() < 3:
        return None, [], True
    nodes, edges = graph(sk)
    edges = prune(nodes, edges, prune_px)
    used = sorted({u for u, _, _ in edges} | {v for _, v, _ in edges})
    if not used:
        return None, [], True
    near = lambda p: min(used, key=lambda n: (nodes[n][0] - p[0]) ** 2 + (nodes[n][1] - p[1]) ** 2)
    s, t = near(start_px), near(end_px)
    deg = {n: 0 for n in used}
    for u, v, _ in edges:
        deg[u] += 1; deg[v] += 1
    odd = {n for n in used if deg[n] % 2 == 1}

    def cover(t):                                             # the walk's edges (greedy pairing of the odd nodes along shortest
        want = sorted(odd ^ ({s, t} if s != t else set()))    # paths; those edges duplicated) and the added length
        E, extra = [list(e) for e in edges], 0.0
        while want:
            a = want.pop(0)
            dist, prev = shortest(nodes, edges, a)
            b = min(want, key=lambda n: dist.get(n, 1e18))
            want.remove(b)
            extra += dist.get(b, 1e18)
            n = b
            while n != a:
                u, i = prev[n]
                E.append(list(edges[i])); n = u
        return E, extra
    E, extra = cover(t)
    end_kept = True
    if free_end:                                              # end anywhere if that walk is much shorter (a region whose median
        total = sum(elen(e) for e in edges)                   # covers only part of it: the walk would come back over the rest)
        best = min(used, key=lambda n: (cover(n)[1], n))
        Eb, xb = cover(best)
        if best != t and total + xb < free_end * (total + extra):
            t, E, extra, end_kept = best, Eb, xb, False
    # Hierholzer
    adj = {n: [] for n in used}
    for i, (u, v, c) in enumerate(E):
        adj[u].append(i); adj[v].append(i)
    usedE = [False] * len(E)
    stack, path = [(s, None)], []
    while stack:
        n, ei = stack[-1]
        while adj[n] and usedE[adj[n][-1]]:
            adj[n].pop()
        if adj[n]:
            i = adj[n].pop(); usedE[i] = True
            u, v, c = E[i]
            stack.append((v if u == n else u, (i, u == n)))
        else:
            stack.pop()
            if ei is not None:
                path.append(ei)
    path.reverse()
    poly, tips, last = [], [], None
    for k, (i, fwd) in enumerate(path):
        c = E[i][2] if fwd else E[i][2][::-1]
        if poly and tuple(poly[-1]) == tuple(c[0]):
            c = c[1:]
        poly.extend([list(p) for p in c])
        if k + 1 < len(path):
            j, fwd2 = path[k + 1]
            same = (E[j][0], E[j][1]) in ((E[i][0], E[i][1]), (E[i][1], E[i][0])) and E[j][2][0] in (E[i][2][0], E[i][2][-1]) and len(E[j][2]) == len(E[i][2])
            end_node = E[i][1] if fwd else E[i][0]
            if same and deg.get(end_node, 0) == 1:
                tips.append(nodes[end_node])
    if not poly:
        return None, [], True
    return np.asarray(poly, float), tips, end_kept


def px_to_world(sheet, u, v) -> np.ndarray:
    return np.stack([sheet.x_far - (np.asarray(v, float) + 0.5) * sheet.px_m, sheet.y_left - (np.asarray(u, float) + 0.5) * sheet.px_m], -1)


def add_detours(w: World, mask_u: np.ndarray, poly: np.ndarray, o: dict) -> tuple[np.ndarray, list]:
    """Out-and-back excursions from the centre path into lobes of the contact's ink it leaves uncovered (e.g. the inner
    horizontals of 目 merged into a vertical's region): a lobe = ink farther than the local half-width + detour_margin_mm from
    the path, of at least detour_min_mm2; the excursion goes to the lobe's thickest point near its far end and back (a tip)."""
    sh = w.main; px = sh.px_m
    S = resample(poly, px * 0.5)
    u, v = sh.world_to_px(S[:, 0], S[:, 1])
    ui = np.clip(np.rint(u).astype(int), 0, sh.cols - 1); vi = np.clip(np.rint(v).astype(int), 0, sh.rows - 1)
    line = np.zeros(mask_u.shape, bool); line[vi, ui] = True
    dpath, (iy, ix) = ndimage.distance_transform_edt(~line, return_indices=True)
    din = ndimage.distance_transform_edt(mask_u)
    unc = mask_u & (dpath > din[iy, ix] + o["detour_margin_mm"] / 1000.0 / px)
    lab, n = ndimage.label(unc)
    ins = []
    for c in range(1, n + 1):
        comp = lab == c
        if comp.sum() * (px * 1000) ** 2 < o["detour_min_mm2"]:
            continue
        far = comp & (dpath >= 0.7 * dpath[comp].max())
        rr, cc = np.nonzero(far)
        k = int(np.argmax(din[rr, cc]))
        tgt = px_to_world(sh, cc[k], rr[k])
        j = int(np.argmin(np.hypot(S[:, 0] - tgt[0], S[:, 1] - tgt[1])))
        ins.append((j, tgt))
    if not ins:
        return poly, []
    out, last = [], 0
    for j, tgt in sorted(ins, key=lambda t: t[0]):
        out.append(S[last:j + 1]); out.append(np.vstack([tgt, S[j]])); last = j + 1
    out.append(S[last:])
    return np.vstack(out), [t for _, t in ins]


def contact_path(w: World, medians: list, contact: list, o: dict) -> tuple[np.ndarray, list]:
    """The contact's centre path: its regions in order, each a skeleton walk between the ends of its median (route "skeleton";
    the median itself if the walk is missing or longer than route_max_ratio x the median) -> (polyline (N, 2), turn-back tips)."""
    segs, tips = [], []
    for k, fwd in contact:
        P = mmah_to_world(w, np.asarray(medians[k], np.float64), k)
        P = P if fwd else P[::-1]
        if o.get("route") == "skeleton":
            sh = w.main
            m = w.target.stroke_masks[k]
            u, v = sh.world_to_px(P[[0, -1], 0], P[[0, -1], 1])
            rr, cc = np.nonzero(m)
            pad = 4
            r0, c0 = max(0, rr.min() - pad), max(0, cc.min() - pad)
            sub = m[r0:rr.max() + pad + 1, c0:cc.max() + pad + 1]
            poly_px, tp, end_kept = skeleton_route(sub, (v[0] - r0, u[0] - c0), (v[1] - r0, u[1] - c0),
                                                  o["prune_mm"] / 1000.0 / sh.px_m, o.get("route_free_end", 0.0))
            if poly_px is not None:
                Lr = float(np.sum(np.hypot(*np.diff(poly_px, axis=0).T))) * sh.px_m
                Lm = float(np.sum(np.hypot(*np.diff(P, axis=0).T)))
                if Lr <= o["route_max_ratio"] * max(Lm, 1e-3):
                    wp = px_to_world(sh, poly_px[:, 1] + c0, poly_px[:, 0] + r0)
                    wp = ndimage.uniform_filter1d(wp, 5, axis=0, mode="nearest")
                    P = np.vstack([P[:1], wp] + ([P[-1:]] if end_kept else []))
                    tips += [px_to_world(sh, c + c0, r + r0) for r, c in tp]
        segs.append(P)
    poly = np.vstack(segs)
    if o.get("detours"):
        mask_u = np.any([w.target.stroke_masks[int(k)] for k, _ in contact], axis=0)
        poly, _ = add_detours(w, mask_u, poly, o)          # the excursions' turns keep the press (their lobes are short)
    return poly, tips


class ContactOpt:
    """One contact's plan: K control points (x, y, press) of the handle along the contact's centre path."""

    def __init__(self, w: World, poly: np.ndarray, ks: list, o: dict, tips=()):
        self.W, self.o, self.tips = w, o, [np.asarray(t, float) for t in tips]
        self.cfg = dict(w.inst["brush"]); self.cfg["substep_m"] = max(self.cfg["substep_m"], w.main.px_m)
        self.brush = B.WangBrush(self.cfg)
        tc = w.target
        self.mask = np.any([tc.stroke_masks[k] for k in ks], axis=0)
        rest = [m for j, m in enumerate(tc.stroke_masks) if j not in ks]
        other = np.any(rest, axis=0) if rest else np.zeros_like(self.mask)
        self.care = ~(other & ~self.mask)
        far = ndimage.distance_transform_edt(~tc.mask) * w.main.px_m > 0.001        # > 1 mm from any exemplar ink: stray
        self.wmap = np.where(self.mask, o["w_in"], np.where(far, o["w_far"], o["w_near"])).astype(np.float32) * self.care
        r, c = np.nonzero(self.mask)
        pad = int(math.ceil(0.014 / w.main.px_m))
        self.win = (max(0, r.min() - pad), min(self.mask.shape[0], r.max() + pad + 1), max(0, c.min() - pad), min(self.mask.shape[1], c.max() + pad + 1))
        L = float(np.sum(np.hypot(*np.diff(poly, axis=0).T)))
        self.K = int(np.clip(round(L / (o["kstep_mm"] / 1000.0)) + 2, 4, o["kmax"]))
        self.P0 = self._init(poly)

    def _width_inv(self, w_m: float) -> float:
        a, b = self.cfg["width_cm"]
        return float(np.clip((w_m * 100 - b) / a, 0.02, self.cfg["z_max_cm"]) / 100)

    def _init(self, med: np.ndarray) -> np.ndarray:
        """The inverse of the brush's trailing dynamics along the centre path (as StrokeOpt), a control point on every tip."""
        W = self.W
        S = resample(med, 5e-4)
        dist = ndimage.distance_transform_edt(self.mask) * W.main.px_m
        u, v = W.main.world_to_px(S[:, 0], S[:, 1])
        ui = np.clip(np.rint(u).astype(int), 0, W.main.cols - 1); vi = np.clip(np.rint(v).astype(int), 0, W.main.rows - 1)
        z = ndimage.uniform_filter1d(np.array([self._width_inv(2 * d) for d in dist[vi, ui]]), 9, mode="nearest")
        T = np.gradient(S, axis=0); T /= np.maximum(1e-12, np.linalg.norm(T, axis=1, keepdims=True))
        off = np.array([self.brush.offset_of(zz) for zz in z]); d = np.array([self.brush.drag_of(zz) for zz in z])
        H = S + off[:, None] * T
        idx = np.linspace(0, len(S) - 1, self.K).round().astype(int)
        for t in self.tips:
            j = int(np.argmin(np.hypot(S[:, 0] - t[0], S[:, 1] - t[1])))
            near = np.hypot(S[:, 0] - t[0], S[:, 1] - t[1]) < self.o["tip_r_mm"] / 1000.0
            z[near] = np.minimum(z[near], self.o["z_min"])
            k = int(np.argmin(np.abs(idx - j))); idx[k] = j
        idx = np.unique(np.clip(idx, 0, len(S) - 1))
        while len(idx) < self.K:
            idx = np.unique(np.r_[idx, (idx[:-1] + idx[1:]) // 2])[: self.K]
        idx = idx[: self.K]
        P = np.c_[H[idx], np.maximum(z[idx], self.o["z_min"])]
        P[0, :2] = S[0] + T[0] * (d[0] * self.o["init_inside"])
        return P

    def render(self, P: np.ndarray) -> np.ndarray:
        pt = B.CalligraphyPainter(self.cfg, self.W.sheets, self.W.wells); pt.loaded = True
        for p in stroke_path(P, B.PAPER_Z, self.o["step_m"], self.o["entry"], self.o["exit"]):
            pt.sample(p, R_DOWN)
        pt.finish()
        return pt.ink["main"]

    def residuals(self, x: np.ndarray) -> np.ndarray:
        P = x.reshape(self.K, 3)
        ink = self.render(P)
        r0, r1, c0, c1 = self.win
        diff = (ink[r0:r1, c0:c1] - self.mask[r0:r1, c0:c1].astype(np.float32)) * self.wmap[r0:r1, c0:c1]
        return np.concatenate([diff.ravel(), 0.3 * np.diff(P[:, 2]) / 0.002])

    def _jac(self, x: np.ndarray) -> np.ndarray:
        h = np.tile([2e-4, 2e-4, 1.5e-4], self.K)
        h = np.where(x + h > self.hi, -h, h)
        r0 = self.residuals(x)
        cols = self._map(_col, [(x, j, float(h[j])) for j in range(len(x))])
        return np.stack([(c - r0) / h[j] for j, c in enumerate(cols)], 1)

    def optimize(self, nfev: int, workers: int = 1, x_init=None) -> tuple[np.ndarray, dict]:
        lo = np.tile([-np.inf, -np.inf, self.o["z_min"]], self.K); hi = np.tile([np.inf, np.inf, self.cfg["z_max_cm"] / 100], self.K)
        self.hi = hi
        x0 = np.clip((self.P0 if x_init is None else np.asarray(x_init)).ravel(), lo + 1e-9, hi - 1e-9)
        t = time.time(); f0 = float(np.sum(self.residuals(x0) ** 2))
        global _CO
        _CO = self
        if workers > 1:
            import multiprocessing as mp
            with mp.get_context("fork").Pool(min(workers, 3 * self.K)) as pool:
                self._map = pool.map
                res = least_squares(self.residuals, x0, jac=self._jac, bounds=(lo, hi), x_scale=np.tile([1e-3, 1e-3, 1e-3], self.K),
                                    max_nfev=nfev, method="trf")
        else:
            self._map = lambda f, a: list(map(f, a))
            res = least_squares(self.residuals, x0, jac=self._jac, bounds=(lo, hi), x_scale=np.tile([1e-3, 1e-3, 1e-3], self.K),
                                max_nfev=nfev, method="trf")
        self._map = None
        return res.x.reshape(self.K, 3), {"cost0": round(f0, 3), "cost": round(float(2 * res.cost), 3), "nfev": int(res.nfev),
                                          "wall_s": round(time.time() - t, 1), "K": self.K}


R_DOWN = np.diag([1.0, -1.0, -1.0])
_CO = None


def _col(args):
    x, j, h = args
    x2 = np.array(x, copy=True); x2[j] += h
    return _CO.residuals(x2)


def render_plans(inst: dict, plans: list, o: dict) -> tuple[World, np.ndarray, int]:
    """Every contact rendered robot-free on the scoring raster (max over contacts) and the number of inked contacts."""
    w = World(inst)
    cfg = dict(inst["brush"]); cfg["substep_m"] = max(cfg["substep_m"], w.main.px_m)
    ink = np.zeros((w.main.rows, w.main.cols), np.float32); n = 0
    for P in plans:
        pt = B.CalligraphyPainter(cfg, w.sheets, w.wells); pt.loaded = True
        for p in stroke_path(np.asarray(P, np.float64), B.PAPER_Z, o["step_m"], o["entry"], o["exit"]):
            pt.sample(p, R_DOWN)
        pt.finish()
        n += sum(1 for st in pt.strokes if st["sheet"] == "main" and st["inked"])
        np.maximum(ink, np.asarray(pt.ink["main"], np.float32), out=ink)
    return w, ink, n


def plan_v2(inst: dict, medians: list, contacts: list, o: dict, workers: int = 1, log=print) -> tuple[list, list]:
    """Plans for every contact (longest first), then the boost rounds."""
    wc = World(coarse_inst(inst, o["res"]) if o["res"] != inst["sheets"][0]["rows"] else inst)
    def job(i, oo, x_init=None):
        ks = [int(k) for k, _ in contacts[i]]
        poly, tips = contact_path(wc, medians, contacts[i], oo)
        co = ContactOpt(wc, poly, ks, oo, tips)
        if x_init is not None and len(x_init) != co.K:
            raise SystemExit(f"contact {i}: warm start with {len(x_init)} control points, the path gives {co.K}")
        P, inf = co.optimize(oo["nfev"], workers, x_init)
        return [[round(float(v), 7) for v in row] for row in P], inf
    plans, info, chosen = [None] * len(contacts), [None] * len(contacts), [None] * len(contacts)
    order = sorted(range(len(contacts)), key=lambda i: (-len(contacts[i]), i))
    for i in order:
        for ci, cd in enumerate(o["candidates"]):
            P, inf = job(i, {**o, **cd})
            log(f"contact {i + 1} candidate {ci + 1} {cd}: K={inf['K']} cost {inf['cost0']} -> {inf['cost']} ({inf['nfev']} evals, {inf['wall_s']} s)")
            if info[i] is None or inf["cost"] < info[i]["cost"]:
                plans[i], info[i], chosen[i] = P, {**inf, "candidate": cd}, cd
    for rnd in range(int(o["boost_rounds"])):
        w, ink, _ = render_plans(inst, plans, o)
        m = G.score_ink(ink, w.target, None, inst["truth"].get("tol_mm", 1.0), inst["target"]["success"])
        low = {k for k in range(len(medians)) if m[f"stroke_coverage_{k + 1:02d}"] < o["cov_target"]}
        redo = [i for i in order if any(int(k) in low for k, _ in contacts[i])]
        log(f"boost round {rnd + 1}: regions under {o['cov_target']}: {sorted(k + 1 for k in low)} -> contacts {[i + 1 for i in redo]}")
        if not redo:
            break
        ob = {**o, "w_in": o["w_in"] * o["boost_w_in"], "w_far": o["w_far"] * o["boost_w_far"], "nfev": o["boost_nfev"]}
        for i in redo:
            P, inf = job(i, {**ob, **chosen[i]}, np.asarray(plans[i], np.float64))
            plans[i], info[i] = P, {**info[i], f"boost{rnd + 1}": inf}
    return plans, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True); ap.add_argument("--graphics", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--nfev", type=int, default=25)
    ap.add_argument("--entry", choices=("vertical", "diagonal"), default="vertical")
    ap.add_argument("--profile", choices=sorted(PROFILES), help="the v2 planner with these settings (PROFILES); without it, the "
                    "per-stroke planner of the earlier references")
    ap.add_argument("--contacts-from", help="v2: take the contacts (lists of [region, forward]) from this plans.json (xingshu); "
                    "default one contact per stroke")
    ap.add_argument("--workers", type=int, default=1, help="v2: processes for the finite-difference Jacobian")
    a = ap.parse_args()
    inst = json.load(open(a.instance))
    tr = inst["truth"]
    chars = tr.get("characters") or tr["character"]
    recs = {}
    for line in open(a.graphics, encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        if d["character"] in chars:
            recs[d["character"]] = d
    strokes = [st for c in chars for st in recs[c]["strokes"]] if all(c in recs for c in chars) else None
    if strokes != tr["strokes"]:
        raise SystemExit("graphics.txt entries missing or different from the instance's outlines")
    medians = [m for c in chars for m in recs[c]["medians"]]
    char = chars
    if a.profile:
        o = dict(PROFILES[a.profile])
        contacts = (json.load(open(a.contacts_from))["contacts"] if a.contacts_from else [[[k, True]] for k in range(len(medians))])
        if sorted(int(k) for c in contacts for k, _ in c) != list(range(len(medians))):
            raise SystemExit("the contacts must hold every region exactly once")
        t = time.time()
        plans, info = plan_v2(inst, medians, contacts, o, a.workers, log=lambda s: print(s, flush=True))
        out = {"character": char, "step_m": o["step_m"], "entry": o["entry"], "exit": o["exit"], "profile": a.profile, "options": o}
        if a.contacts_from:
            out["contacts"] = contacts
        json.dump({**out, "plans": plans, "info": info}, open(a.out, "w"), indent=1, ensure_ascii=False)
        print(json.dumps({"contacts": len(plans), "wall_s": round(time.time() - t, 1)}))
        return 0
    wc = World(coarse_inst(inst, 512))
    plans, info = [], []
    for k in range(len(medians)):
        so = StrokeOpt(wc, medians[k], k, entry=a.entry)
        P, inf = so.optimize(a.nfev)
        plans.append([[round(float(v), 7) for v in row] for row in P]); info.append(inf)
        print(f"stroke {k + 1}: K={so.K} cost {inf['cost0']:.1f} -> {inf['cost']:.1f} ({inf['nfev']} evals, {inf['wall_s']} s)", flush=True)
    entry = {} if a.entry == "vertical" else {"entry": a.entry}
    json.dump({"character": char, "step_m": 4e-4, **entry, "plans": plans, "info": info}, open(a.out, "w"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
