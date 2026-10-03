#!/usr/bin/env python3
"""Check blanket_flatten's coverage evaluation (image 0.2.11) against the code it replaced:
- footprint_area now builds the triangle polygons in one shapely.from_ragged_array call: it must equal the shipped
  shapely.polygons form (copied below verbatim) bit for bit;
- footprint_area_slabs (vertical slabs, one union per thread): the task's gate rule (recompute with footprint_area when
  the slab coverage is within 1e-3 of the threshold) must give the same decision; differences above 1e-3 fail. On cloth
  states the two agree to ~1e-15; extreme synthetic folds show GEOS' one-shot union drifting by up to ~3e-4 (reported).
States: a regular cloth grid with Delaunay faces (as the task builds them), randomly folded (reflections over random
lines, lifted), rolled and jittered, with coverage bisected around 0.90 for part of them.

    python scripts/check_blanket_coverage_slabs.py [--states 200] [--seed 0]

Run in the TopoGym image (shapely, scipy). Exit 1 on any difference."""
import argparse
import sys
import time

import numpy as np

from topogym.evaluation.cloth_metrics import footprint_area, footprint_area_slabs


def reference(positions, faces):
    """footprint_area up to image 0.2.10 (dev/jianwen feb76f3b3), verbatim."""
    import shapely
    triangles = positions[faces, :2]
    cross = ((triangles[:, 1, 0]-triangles[:, 0, 0])*(triangles[:, 2, 1]-triangles[:, 0, 1])
             -(triangles[:, 1, 1]-triangles[:, 0, 1])*(triangles[:, 2, 0]-triangles[:, 0, 0]))
    triangles = triangles[np.abs(cross) > 1e-12]
    if not len(triangles):
        return 0.
    polygons = shapely.polygons(triangles)
    try:
        return float(shapely.area(shapely.union_all(polygons)))
    except shapely.errors.GEOSException:
        return float(shapely.area(shapely.union_all(polygons, grid_size=1e-8)))


def cloth(nx=60, ny=134, length=0.9, width=0.4):
    from scipy.spatial import Delaunay
    u, v = np.meshgrid(np.linspace(0, length, ny), np.linspace(0, width, nx))
    uv = np.c_[u.ravel(), v.ravel()]
    return np.c_[uv, np.zeros(len(uv))], Delaunay(uv).simplices, length * width


def fold(rng, positions, amount):
    p = positions.copy()
    for _ in range(rng.integers(1, 4)):
        theta = rng.uniform(0, np.pi)
        n = np.array([np.cos(theta), np.sin(theta)])
        c = p[:, :2].mean(0) + rng.normal(scale=0.05, size=2)
        side = (p[:, :2] - c) @ n > amount * rng.uniform(-0.2, 0.2)
        d = ((p[side, :2] - c) @ n)[:, None]
        p[side, :2] -= 2 * d * n
        p[side, 2] += 0.004
    return p + rng.normal(scale=5e-4, size=p.shape)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--states", type=int, default=200); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    flat, faces, area = cloth()
    bad, worst, near, times = [], 0.0, 0, dict(reference=0.0, slabs=0.0)
    for i in range(a.states):
        p = fold(rng, flat, rng.uniform(0, 1))
        if i % 4 == 0:   # shrink toward a coverage near 0.90 (the task's minimum_coverage_ratio)
            p[:, :2] = (p[:, :2] - p[:, :2].mean(0)) * rng.uniform(0.94, 0.96) + p[:, :2].mean(0)
        t0 = time.perf_counter(); ref = reference(p, faces); t1 = time.perf_counter()
        new = footprint_area(p, faces); t2 = time.perf_counter()
        slab = footprint_area_slabs(p, faces); t3 = time.perf_counter()
        times["reference"] += t1 - t0; times["slabs"] += t3 - t2
        cov_ref, cov_slab = ref / area, slab / area
        gate = cov_slab if abs(cov_slab - 0.90) >= 1e-3 else footprint_area(p, faces) / area
        worst = max(worst, abs(cov_ref - cov_slab))
        near += abs(cov_ref - 0.90) < 0.01
        if new != ref or abs(cov_ref - cov_slab) > 1e-3 or (gate >= 0.90) != (cov_ref >= 0.90):
            bad.append(dict(state=i, reference=ref, one_call=new, slabs=slab))
    print(f"states {a.states} ({near} within 0.01 of 0.90): one-call polygons bit-identical in "
          f"{a.states - sum(1 for b in bad if b['one_call'] != b['reference'])}; max |coverage difference| slabs {worst:.2e}; "
          f"differences {len(bad)}; time per state reference {1e3 * times['reference'] / a.states:.0f} ms, "
          f"slabs {1e3 * times['slabs'] / a.states:.0f} ms")
    for b in bad[:10]:
        print(b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
