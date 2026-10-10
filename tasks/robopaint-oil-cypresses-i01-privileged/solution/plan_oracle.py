# Reference execution (generation time): scripts/robopaint_brush_mk_task.py runs `rcb_brush.py run-oracle --code plan_oracle.py`;
# ref_oil.py paints the hidden stroke program (solution/program.json) with the robot. That painting IS the exemplar (target.png), so
# the recorded actions (solution/oracle_qpos.npy of both twins) reproduce it exactly.
import json, os, sys
sol = os.environ.get("RCB_SOLUTION_DIR", "/solution"); sys.path.insert(0, sol)
from ref_oil import paint  # noqa: E402

prog = json.load(open(os.path.join(sol, "program.json")))
info = paint(s, p, prog["strokes"], motion=prog.get("motion"))  # noqa: F821
print("oracle plan:", info)
