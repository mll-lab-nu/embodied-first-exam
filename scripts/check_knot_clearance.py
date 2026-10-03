#!/usr/bin/env python3
"""Check knot_untying's per-tick planar clearance (tooling v9: rcb_topogym._tree_planar_clearance, k-d tree candidates)
against the vectorized all-pairs form it replaced (rcb_topogym._vectorized_planar_clearance): the same bool and the same
reported minimum (bit for bit) on random polylines, projected trefoils (crossings), parallel strands near the clearance
threshold, folds and repeated points. Also times both on a 770-station curve (the knot centerline's size).

    python scripts/check_knot_clearance.py [--curves 3000] [--seed 0]

Run in the TopoGym image (scipy, topogym.utils.geometry.passage). Exit 1 on any difference."""
import argparse
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "rcb_topogym", Path(__file__).resolve().parents[1] / "harbor_templates/topogym/common/rcb_topogym.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def stations(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def curve(rng, kind, n):
    t = np.linspace(0, 1, n)
    if kind == "walk":
        p = np.cumsum(rng.normal(scale=rng.uniform(0.002, 0.02), size=(n, 3)), axis=0)
    elif kind == "trefoil":
        u = 2 * np.pi * t * rng.uniform(0.6, 1.0)
        r = rng.uniform(0.03, 0.08)
        p = np.stack([r * (np.sin(u) + 2 * np.sin(2 * u)), r * (np.cos(u) - 2 * np.cos(2 * u)), -r * np.sin(3 * u)], axis=1)
    elif kind == "strands":   # a U-turn: two parallel strands at a gap near the clearance threshold
        gap = rng.uniform(0.002, 0.02)
        half = n // 2
        a = np.stack([np.linspace(0, 0.3, half), np.zeros(half), np.zeros(half)], axis=1)
        turn = np.stack([0.3 + gap / 2 * np.sin(np.linspace(0, np.pi, 9)), gap / 2 - gap / 2 * np.cos(np.linspace(0, np.pi, 9)),
                         np.zeros(9)], axis=1)[1:-1]
        b = np.stack([np.linspace(0.3, 0, n - half), np.full(n - half, gap), np.zeros(n - half)], axis=1)
        p = np.concatenate([a, turn, b]) + rng.normal(scale=1e-5, size=(len(a) + len(turn) + len(b), 3))
    else:                     # spiral, sometimes with a repeated point or a fold planted
        u = 2 * np.pi * t * rng.uniform(1, 4)
        r = 0.02 + 0.05 * t
        p = np.stack([r * np.cos(u), r * np.sin(u), 0.01 * t], axis=1)
        if rng.random() < .2:
            k = rng.integers(1, n - 1); p[k] = p[k - 1]
        elif rng.random() < .2:
            k = rng.integers(1, n - 2); p[k + 1, :2] = p[k - 1, :2]
    return p


def outcome(fn, p, s, d):
    try:
        ok, info = fn(p, s, d)
        return bool(ok), info.get("projected_degenerate"), info.get("minimum_nonlocal_distance_m")
    except Exception as error:  # noqa: BLE001 - the comparison is the point
        return type(error).__name__, str(error)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--curves", type=int, default=3000); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    diffs, kinds = [], {}
    for i in range(a.curves):
        kind = ("walk", "trefoil", "strands", "spiral")[i % 4]
        p = curve(rng, kind, int(rng.integers(4, 400)))
        s = stations(p) if rng.random() < .95 else stations(p)[::-1]   # a few invalid (decreasing) stations
        d = float(rng.uniform(0.002, 0.012))
        want, got = outcome(tool._vectorized_planar_clearance, p, s, d), outcome(tool._tree_planar_clearance, p, s, d)
        kinds.setdefault((kind, want[0] if isinstance(want[0], bool) else "error"), 0)
        kinds[(kind, want[0] if isinstance(want[0], bool) else "error")] += 1
        if want != got:
            diffs.append(dict(curve=i, kind=kind, vectorized=want, tree=got))
    u = np.linspace(0, 6 * np.pi, 770)   # a clean 3-turn spiral: non-local neighbours, no crossing, no early return
    p = np.stack([(0.02 + 0.004 * u) * np.cos(u), (0.02 + 0.004 * u) * np.sin(u), 0.001 * u], axis=1)
    s, d = stations(p), 0.0084
    times = {}
    for name, fn in (("vectorized", tool._vectorized_planar_clearance), ("tree", tool._tree_planar_clearance)):
        t0 = time.perf_counter()
        for _ in range(5):
            fn(p, s, d)
        times[name] = (time.perf_counter() - t0) / 5
    print(f"curves {a.curves}: differences {len(diffs)}; outcomes {dict(sorted(kinds.items(), key=str))}")
    print(f"770 stations: vectorized {times['vectorized'] * 1e3:.1f} ms, tree {times['tree'] * 1e3:.1f} ms per call")
    for x in diffs[:10]:
        print(x)
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
