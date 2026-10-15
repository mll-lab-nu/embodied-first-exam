# Reference execution (generation time, on the graders' copy of the instance): scripts/robopaint_brush_mk_task.py runs
# `rcb_brush.py run-oracle --code plan_oracle.py`; the robot-free plans (solution/plans.json, from opt_calli.py) are written on the
# robot with lag feed-forward and iterative learning control (ref_calli.py); run-oracle records the final pass, which becomes
# solution/oracle_qpos.npy of both twins.
import json, os, sys
sol = os.environ.get("RCB_SOLUTION_DIR", "/solution"); sys.path.insert(0, sol)
from ref_calli import paint  # noqa: E402

pl = json.load(open(os.path.join(sol, "plans.json")))
info = paint(s, p, pl["plans"], ilc_passes=int(pl.get("ilc_passes", 3)), entry=pl.get("entry", "vertical"), exit=pl.get("exit"))  # noqa: F821
print("oracle plan:", info, {k: v for k, v in s.status().items() if k in ("iou", "boundary_f", "min_stroke_coverage", "stray_frac", "n_strokes", "success")})  # noqa: F821
