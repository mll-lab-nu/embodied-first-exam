# Reference solution (calligraphy)

Made at generation time on the graders' copy of the instance (tests/instance.json, whose `truth` holds the exemplar's ink; the
agent's copy does not):
1. `opt_calli.py --profile print` (2026-10-09) — robot-free trajectory optimisation against the task's brush model, one brush
   contact at a time (kaishu: an exemplar stroke; xingshu: a contact of the connected-stroke plan, `--contacts-from`):
   - K control points (x, y, press) about every 6 mm along the contact's centre path, initialised by inverting the brush's
     trailing dynamics; scipy least_squares on the rendered contact against its ink (512 px grid; the other contacts' ink "don't
     care"; ink more than 1 mm from the exemplar weighted 1.5×);
   - three centre paths are tried per contact and the lowest residual is kept: the regions' medians; a walk over each region's
     skeleton that covers every branch (rings round, side branches out and back; it ends elsewhere than the median's end when
     that is much shorter, e.g. a hook merged with the next stroke written in one pass); the medians with out-and-back
     excursions into lobes they leave uncovered;
   - two boost rounds for the contacts holding a region covered under 0.92 (missing and stray ink weighted 3×);
   - the brush enters the paper on a line along the stroke and leaves it back onto its own root (回锋), with a press of at least
     0.6 mm, so that a contact never splits in two;
   - deterministic: one BLAS thread, and the result does not depend on `--workers`. `plans.json` records the settings.
2. `plan_oracle.py` -> `ref_calli.py` — the plans written on the robot: a dip before every contact, travel, the entry line, the
   contact at 2 cm/s, the return exit; each control step commands IK(desired tip 0.125 s ahead) (PD lag feed-forward) and passes
   of iterative learning control correct the commanded path by the realized tip error (three, or `plans.json` `ilc_passes`: the
   robot step was run with 3 and 5 and the result with the larger worst margin against IoU 0.92, boundary F 0.90, every region
   0.90 and stray 0.01 kept); the arm parks at the end. `rcb_brush.py run-oracle` records the final pass -> `oracle_qpos.npy`.
3. `solve.sh` replays `oracle_qpos.npy` (`oracle_paint.py`), because the agent's container has nothing to plan from but the picture.

Until 2026-10-09 the references came from the per-stroke planner (`opt_calli.py` without `--profile`: vertical touch-down and
lift, one control point per 10 mm, 25 iterations; xingshu's contacts from an external connected-stroke optimiser).
