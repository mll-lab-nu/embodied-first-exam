# Reference solution (lettering)

Made once at generation time by `scripts/robopaint_brush_mk_task.py --family lettering` on the graders' full instance
(tests/instance.json): `plan_oracle.py` -> `ref_lettering.py` writes the exemplar's contacts from `plans.json` (one writing route
per connected piece of the exemplar's ink, with the tines' spread at every point and the pen's spread axis; made from the scan by
`scripts/robopaint_lettering/lt_exemplar.py`) with the pointed pen: one dip, travel 15 mm above the paper, a vertical touch-down,
2 cm/s (slower around sharp turns and turn-backs), the press depth of each point from the spread (hairlines at 0.7 mm), a vertical
lift, each control step commanding IK(desired tip 0.125 s ahead), five passes of iterative learning control on the realized tip
path; the arm parks at the end. `rcb_brush.py run-oracle` records the final pass -> `oracle_qpos.npy`; `solve.sh` replays it
(`oracle_paint.py`), because the agent's container has nothing to plan from but the picture.
