# Reference solution (oil stroke copy)

The exemplar is what the robot paints when it executes the hidden stroke program `program.json` (authored for the benchmark, CC0;
made by `programs.py`): `plan_oracle.py` -> `ref_oil.py` paints every stroke (a dip in its colour's well = a fresh brush, travel
20 mm above the paper, a vertical touch-down to the first press, the Catmull-Rom path through the control points at the stroke's
speed with the press interpolated, lift; IK for the desired tip 0.125 s ahead), the arm parks at the end.
`scripts/robopaint_brush_mk_task.py` ran it on a blank exemplar, froze the painted main sheet as target.png (+ its paint coverage
in target_masks.npz), re-froze the instance on it and recorded the same actions as `oracle_qpos.npy`; `solve.sh` replays them
(`oracle_paint.py`), which reproduces the exemplar exactly.
