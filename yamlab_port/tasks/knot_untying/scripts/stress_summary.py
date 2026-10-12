"""Summarise a run's rope behaviour: blow-up step, FD speed percentiles while the rope is held,
final goal state. python stress_summary.py <run_dir> [<run_dir> ...]"""
import json, os, sys
import numpy as np
for run in sys.argv[1:]:
    L = json.load(open(os.path.join(run, "goal_log.json")))
    S = np.load(os.path.join(run, "states.npz")); P = S["rope_pos"]; A = S["actions"]
    bad = next((r["step"] for r in L if not r["intact"]), None)
    held = np.flatnonzero((A[:, 6] > -0.01) | (A[:, 13] > -0.01))   # a gripper commanded closed
    v = np.array([np.nanmax(np.linalg.norm(P[k] - P[k - 1], axis=1)) * 30 if k else 0 for k in range(len(P))])
    hv = v[held[held > 0]] if len(held) else np.array([0.0])
    hv = hv[np.isfinite(hv)]
    m = json.load(open(os.path.join(run, "metrics.json")))
    print(os.path.basename(run.rstrip("/")), "success", m["success"], "succ_step", m["success_step"], "blowup_step", bad,
          "held_steps", len(held), "held FD speed p50/p95/max m/s %.3f/%.3f/%.3f" % (np.median(hv), np.quantile(hv, .95), hv.max()),
          "final", {k: L[-1][k] for k in ("n_crossings", "planar_clear", "on_table", "quiet", "intact")})
