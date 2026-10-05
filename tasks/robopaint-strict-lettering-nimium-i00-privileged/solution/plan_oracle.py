# Reference execution (generation time, on the graders' copy of the instance with the exemplar's pen paths): scripts/robopaint_brush_mk_task.py
# runs `rcb_brush.py run-oracle --code plan_oracle.py`; ref_lettering.py writes every stroke along its pen path with the tool turned to
# the stroke's pen orientation (broad nib: the pen angle; pointed pen: the tines' spread axis, and the press depth from the line
# width), lag feed-forward + iterative learning control; run-oracle records the final pass, which becomes solution/oracle_qpos.npy of
# both twins.
import os, sys
sol = os.environ.get("RCB_SOLUTION_DIR", "/solution"); sys.path.insert(0, sol)
from ref_lettering import paint  # noqa: E402

info = paint(s, p)  # noqa: F821
print("oracle plan:", info, {k: v for k, v in s.status().items() if k in ("iou_registered", "boundary_f", "min_stroke_coverage_registered", "stray_frac", "n_strokes", "success")})  # noqa: F821
