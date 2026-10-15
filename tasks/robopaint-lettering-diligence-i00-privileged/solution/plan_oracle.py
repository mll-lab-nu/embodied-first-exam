# Reference execution (generation time, on the graders' copy of the instance): scripts/robopaint_brush_mk_task.py runs
# `rcb_brush.py run-oracle --code plan_oracle.py`; ref_lettering.py writes every contact of solution/plans.json (the exemplar's
# writing routes with the tines' spread, and the pen's spread axis) with the pointed pen, lag feed-forward + iterative learning
# control; run-oracle records the final pass, which becomes solution/oracle_qpos.npy of both twins.
import json, os, sys
sol = os.environ.get("RCB_SOLUTION_DIR", "/solution"); sys.path.insert(0, sol)
from ref_lettering import paint  # noqa: E402

info = paint(s, p, json.load(open(os.path.join(sol, "plans.json"))))  # noqa: F821
print("oracle plan:", info, {k: v for k, v in s.status().items() if k in ("iou_registered", "boundary_f", "min_stroke_coverage_registered", "stray_frac", "n_strokes", "success")})  # noqa: F821
