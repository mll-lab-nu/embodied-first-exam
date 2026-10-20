# Oracle for the RoboPaint brush tasks, executed by `rcb_brush.py run-oracle` with `s` (Session) and `p` (primitives) in scope.
# The agent's copy of the instance holds only the scene and the picture, so the oracle replays the joint targets that the reference
# planner (run at generation time on the graders' copy) recorded. The metrics the scoring service returns for
# them go to /app/output/scorer_metrics.json (validation: they must equal the verifier's).
import json, os
import numpy as np

A = np.load(os.path.join(os.environ.get("RCB_SOLUTION_DIR", "/solution"), "oracle_qpos.npy")).astype(np.float32)
for a in A:
    s.step(a)  # noqa: F821
m = s.score()  # noqa: F821
out = os.environ.get("RCB_ORACLE_METRICS_OUT", "/app/output/scorer_metrics.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(m, open(out, "w"), indent=1)
print("oracle: replayed", len(A), "control steps;", {k: v for k, v in m.items() if k in ("iou", "iou_registered", "boundary_f", "min_stroke_coverage", "de_mean", "de_p90", "ssim_L", "paint_iou", "success")})
