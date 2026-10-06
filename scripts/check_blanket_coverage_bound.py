#!/usr/bin/env python3
"""Check topogym.evaluation.cloth_metrics.footprint_area_upper_bound (the coverage skip inside a control step,
blanket_flatten.evaluate_state) on recorded cloth states, without a GPU.

    python scripts/check_blanket_coverage_bound.py <mesh.npz> <states.npy> [--every 1]

<mesh.npz>: faces (the task's particle_faces), area (material area), threshold (minimum_coverage_ratio); <states.npy>:
particle positions, one state per row (e.g. a replay's per-step dump). Pass: the bound is never below the union
(footprint_area_slabs and footprint_area), and wherever it decides the goal (bound / area < threshold - 1e-3) the union
is below the threshold as well. Reports how often it decides and its cost against the union. The per-tick decision
identity on a replay (GPU) is scripts/check_blanket_coverage_skip.py's comparison with the full evaluation."""
import argparse, json, sys, time
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mesh"); ap.add_argument("states"); ap.add_argument("--every", type=int, default=1)
    a = ap.parse_args()
    from topogym.evaluation.cloth_metrics import footprint_area, footprint_area_slabs, footprint_area_upper_bound
    m = np.load(a.mesh)
    faces, area, threshold = m["faces"], float(m["area"]), float(m["threshold"])
    states = np.load(a.states, mmap_mode="r")
    r = dict(states=0, decided=0, below_union=0, wrong_decision=0, bound_s=0.0, union_s=0.0,
             min_margin=None, max_margin=None)
    for i in range(0, len(states), a.every):
        x = np.asarray(states[i], dtype=np.float64)
        if not np.isfinite(x).all() or np.ptp(x[:, 0]) == 0 or np.ptp(x[:, 1]) == 0:
            continue                   # unused rows of a preallocated dump
        r["states"] += 1
        t = time.perf_counter(); bound = footprint_area_upper_bound(x, faces); r["bound_s"] += time.perf_counter() - t
        t = time.perf_counter(); union = footprint_area_slabs(x, faces); r["union_s"] += time.perf_counter() - t
        margin = (bound - union) / area
        r["min_margin"] = margin if r["min_margin"] is None else min(r["min_margin"], margin)
        r["max_margin"] = margin if r["max_margin"] is None else max(r["max_margin"], margin)
        if bound < union or bound < footprint_area(x, faces):
            r["below_union"] += 1
        if bound / area < threshold - 1e-3:
            r["decided"] += 1
            r["wrong_decision"] += int(union / area >= threshold)
    r["passed"] = bool(r["states"] and not r["below_union"] and not r["wrong_decision"])
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
