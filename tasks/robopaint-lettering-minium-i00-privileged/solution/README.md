# Reference solution (lettering)

Made once at generation time by `scripts/robopaint_brush_mk_task.py --family lettering` on the graders' full instance (tests/instance.json, whose `truth` has
the exemplar's pen paths; the agent's copy does not): `plan_oracle.py` -> `ref_lettering.py` writes every stroke along its pen path
with the tool turned to the stroke's pen orientation (broad nib: the edge's pen angle, a constant 1 mm press; pointed pen: the tines'
spread axis and the press depth of each point from the line width, hairlines at 0.5 mm), a dip first, travel 15 mm above the paper,
a vertical touch-down, 2 cm/s, each control step commanding IK(desired tip 0.125 s ahead), three passes of iterative learning
control on the realized tip path; the arm parks at the end. `rcb_brush.py run-oracle` records the final pass -> `oracle_qpos.npy`;
`solve.sh` replays it (`oracle_paint.py`), because the agent's container has no exemplar geometry to plan from. `letters.py` holds
the authored letter skeletons (CC0) the generator used.
