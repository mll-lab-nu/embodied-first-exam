# Reference solution (calligraphy)

Made once at generation time by `scripts/robopaint_brush_mk_task.py` on the graders' copy of the instance (tests/instance.json,
whose `truth` holds the exemplar's outlines; the agent's copy does not):
1. `opt_calli.py` — robot-free trajectory optimisation against the task's brush model, one stroke at a time: K control points
   (x, y, press) of the handle path, initialised by inverting the brush's trailing dynamics along the exemplar's median (Make Me a
   Hanzi medians), scipy least_squares on the rendered stroke vs the stroke's mask (512 px grid; the other strokes are "don't
   care") -> `plans.json`.
2. `plan_oracle.py` -> `ref_calli.py` — the plans written on the robot: a dip before every stroke, travel, a 4 mm approach along
   the first tangent, touch-down, the stroke at 2 cm/s, lift; each control step commands IK(desired tip 0.125 s ahead) (PD lag
   feed-forward) and three passes of iterative learning control correct the commanded path by the realized tip error; the arm
   parks at the end. `rcb_brush.py run-oracle` records the final pass -> `oracle_qpos.npy`.
3. `solve.sh` replays `oracle_qpos.npy` (`oracle_paint.py`), because the agent's container has nothing to plan from but the picture.
