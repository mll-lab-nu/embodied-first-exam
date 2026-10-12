# cast_keyhole STATUS

## State (2026-10-12)

very_easy: DONE. Oracle succeeds (runs/oracle_ve: success latched at step 2509 = 83.6 s sim, 109 s wall on the
loaded vast host); open-loop replay of actions.npy succeeds at the same step and is bit-identical to the oracle
run and to a second replay (state hash f36fea3ae676009c, max deviation 0.0 on all plate/arm states); nop fails;
naive straight pull (no key turn) jams at the channel entry and fails. Offline penetration audit: max
gold-silver penetration 0.12 mm (guard 1 mm).
easier: STOPPED after a bounded design round (16 sim trials ea_t1..t15 + 6 IK searches), no oracle success.
Task, assets, goal check and nop are in place (nop fails). Blocker evidence in "## easier work log" below.

## Verified so far

- Geometry: ported generator rebuilds the STL package exactly (bounds error 3e-14 mm, STL-to-mesh max 1e-5 mm,
  volumes equal to 1e-6 mm3). Colliders = the old generator's own convex slab prisms (gold 48, silver 22), exact
  and non-overlapping (no convex decomposition; collider volume = mesh volume). Start gap colliders 4.807 mm
  (package: 4.80). Masses from the old density 6600 kg/m3: gold 0.6395 kg, silver 0.4263 kg.
- Old relative route (simplified_policy.py, +90 deg key turn then channel guides) on the exact colliders: min
  clearance 4.36 mm (turn), 1.125 mm (channel entry, = the old README's 1.125 mm), 25.7 mm at the end. The
  mirrored key turn (-90 deg) has the same clearances.
- Naive straight pulls from the start (no key turn), exact colliders: blocked after 31.5 mm (-y), 5.5 (+y),
  8.5 (+-x), 20 (+-z).
- numpy YAM FK/IK (tools/yam_kin.py) vs Isaac link_6: 0.0003 mm / 3e-5 deg.
- Scene smoke (vast, CPU PhysX, 65 steps/s physics-only): loads, no explosion; the authored X-shaped start is
  NOT self-supporting: within ~1 s the plates fall almost flat (gold 17 deg, silver 24 deg), still interlocked,
  max speed 0.3 m/s, at rest after ~2 s; lowest point 1.7 mm below the nominal table top (table collider).

## Findings that shaped the oracle

- Physical tabletop = top of the workstation's `table_surface` collider, z = 0.7500 (yam.yaml's 0.7517 is the
  calibration top; resting plates sit 1.7 mm "below" it). The goal check uses 0.7500 (the old check used the
  scene's support height); start poses are 0.5 mm above 0.7500 as in the old start.
- Interlocked plates at rest report persistent velocity jitter (|v| ~0.015 m/s, |w| ~0.38 rad/s) while their
  poses are constant to 0.1 mm (contact solver noise of the interlock). A single plate resting flat on the
  table is quiet (3e-6 m/s, 3e-5 rad/s), so the old quiet thresholds (1 mm/s, 0.02 rad/s) are usable for the
  goal (silver alone). Nop run: fails (silver not in the square, gold 13 mm over the separator after the settle).
- YAMLab's grasp flag (both pads in contact, >= 0.1 N) drops intermittently while the plate is still held, so
  the oracle's lost-grasp guard uses the measured in-hand slip instead.

- YAM gripper squeeze on a 9 mm plate is weak (finger kp 2000 N/m, ~9-14 N): a near-flat gold held at its edge
  survives a 3 cm lift (0.2 mm slip) but slips out when the assembly is re-oriented (trial 1).
- YAM reach (numpy IK, joint margin >= 0.1 rad): top-down TCP only up to ~0.40-0.50 m horizontal at 3-15 cm
  above the base height, and NOT reachable at 25 cm above; forward-pointing reachable to 0.65 m at 25 cm.
  So plans that lift the assembly high or point down far away are infeasible.
- Design v3: gold (left arm) face clamp on its +x prong band (x 20..39 mm: never swept by the silver for the
  +90 deg turn); silver (right arm) top-down face clamp on its -x side bar at the COM (the gold lives in the
  silver's x_s ~ 0 plane, so these fingers can never touch it); gold held flat ~7 cm above the table; the key
  turn is a wrist roll of the right arm; the channel is split between both arms.

## Re-layout (old table frame mm -> YAMLab world m)

p_world = p_old / 1000 + (0.52, -0.10, 0.7500), no rotation (old +x -> +X, old +y -> +Y). Gold starts at
(0.4495, -0.05), silver at (0.5905, -0.05) (part frames, z 0.7813); goal square X 0.3917..0.6483, Y 0.0148..0.2713; gold must stay at
Y <= -0.0152 (old separator y <= 84.8 mm). Reason: the gold's free band then faces the left arm, the silver's
free edge the right arm; all positions inside the measured YAM reach. (Yaw 90/180 variants were evaluated and
rejected for reach.)

## Deviations from the old task (so far)

- Penetration guard (old: task contact penetration > 1 mm fails) is evaluated offline from logged poses, not
  in the per-step torch check.
- Release is not required (old: holding_allowed=True); reported as a diagnostic.
- Goal square / separator taken from the package numbers (my recomputation from the exported meshes differs
  by ~1 mm, the old one used the Genesis-converted collision vertices).

## Oracle trial log (very_easy, vast runs/orc_t*)

- t1 (old W pose, assembly lifted + tilted): gold dropped during the re-orientation (weak grip).
- t2-t7 (v3: gold flat in the air, silver top-down): gold slips out of the band clamp in level/align (pry).
- t8-t12 (v4: silver stands on its +x edge on the table, gold flat on top resting on the silver bar): setup OK
  for the gripper, but the left wrist (joint 4) hits its +90 deg limit when flattening the gold near the
  centre. Random IK search (tools/plan_search2.py, 600 samples) found work poses with both arms feasible
  (gold margin 0.18 rad): bar (0.595, -0.213), assembly yaw -15 deg, gold yaws 44 deg of the 90 deg key turn.
- t13-t16: phases re-based on measured poses caused command jumps (fixed: phases continue from the desired
  poses). t15/t16 then completed setup + the full key turn; the slide jammed at the channel entry
  (bar y ~10 units) because the relative configuration was 13 deg / 8 mm off nominal (in-hand slip of both
  plates; the channel clearance is 1.1 mm).
- t17-t20: relative feedback (silver follows the filtered measured gold) to remove that offset.

Final-code check: after all easier changes, `scripts/oracle.py --params params/very_easy.json` was rerun
(runs/oracle_ve_final): actions identical to oracle_ve (max diff 0.0), success at step 2509, final hash
f36fea3ae676009c. The new options (regrasps, compliant stand, IK-gated correction) are off by default.

## Success latch (confirmed)

`CastKeyholeManager.update_success` counts consecutive control steps on which the full predicate holds
(silver all inside, gold on the system side, silver quiet, no failure) and latches success only when the count
reaches `ceil(stable_duration_s / step_dt)` = ceil(0.5 s / (4 x 1/120 s)) = 15 steps, i.e. the old 0.5 s
stable_duration window. The count resets to 0 on any step where the predicate fails. In oracle_ve the latch step
2509 shows consecutive_steps = 15. The `task_success` termination reads the latched flag, so the env terminates
and auto-resets on the step after the latch; the oracle stops on the latch step and the replay ends there too.

All runs (oracle, both replays, nop, naive; very_easy and easier) create the env through
`scripts/ck_env.make_env`, which always uses YAMLab mode="evaluation" (CPU, 1 env) with the task's
time_out / task_success / task_failure terminations active (not "replay"/"teleoperation", which drop them).

## Final very_easy numbers (vast, CPU PhysX, physics-only)

| run | result | steps | key values |
|---|---|---|---|
| oracle_ve (`params/very_easy.json`) | success, latched at step 2509 | 2510 | silver all inside (margin 18.6 mm), gold separator margin 152 mm, silver 0.15 mm/s, 0.0025 rad/s, released; penetration max 0.12 mm |
| replay_ve1 / replay_ve2 | success at 2509, bit-identical to oracle and to each other | 2510 | final hash f36fea3ae676009c |
| nop_ve2 | fail | 690 | silver 113 mm outside the square, gold 15 mm over the separator (after the settle) |
| naive_ve (no key turn, straight pull) | fail | 2535 | jams at bar y ~11.4 plate units (offline geometry: blocked after 31.5 mm), plates stay interlocked; penetration max 0.54 mm |

Re-layout log row: cast_keyhole very_easy: p_world = p_old_table/1000 + (0.52, -0.10, 0.7500), no rotation;
table z = physical table_surface top. Goal square world X 0.3917..0.6483, Y 0.0148..0.2713; separator: gold
Y <= -0.0152. Reason: gold's free band faces the left arm, silver's free edge the right arm, measured reach.

## easier work log and blocker evidence

Built and verified: assets (gold 52 slab prisms, 0.6085 kg; silver unchanged), geometry vs STLs 1e-5 mm, start
gap 4.807 mm, route clearance 1.125 mm, nop fails (runs/nop_ea, nop_ea2), gym id CastKeyhole-Easier-v0.

Why the very_easy plan does not transfer: easier's channel shifts the bar +3.5 units (+10.7 mm) for gold y
-9..-60 mm, so the silver legs then reach gold x 38.7 mm, i.e. the whole +x band (runs_meta/swept_easier_+1.png).
At |gold z| <= 55 mm the only gold regions the silver never sweeps are (a) the band x 20..39 mm next to the
fork end, gold y -105..-65 mm (40 mm long, shorter than the 60 mm finger blades), and (b) the cap top
y 70..102 mm, x > 5 mm. The finger blades are 21-25 mm thick, so they cannot get under the legs.

What was tried (all with the unchanged YAM, friction grasps only):
1. Fork-end grasp along +y (approach from the open end): no IK for either arm in the yaw-0 layout
   (pointing forward at the arm's far bearing) or the yaw -90 layout (ps_ea / ps_ea2, 0 seeds).
2. Band grasp at gold y -96..-99 mm from the start (layouts X0 0.60 / yaw -20): the left arm reaches it only
   with the scene moved out (X0 >= ~0.56), which puts the silver at the right arm's limit. Trials ea_t1, t2,
   t5-t13: the gold, held 95 mm from its COM, pivots in the grip during the stand (14 mm / 8 deg), or with a
   compliant hand sags 20 mm onto the silver; the silver then slips 25 mm in its grip during the rigid move,
   with 1-5 cm right-arm IK error (the arms push the jammed pair against each other).
3. Regrasp after the stand (ea_t3/t4) and in the work pose (ea_t14/t15): once released, the gold drops until
   its fork end lies on the table (band 5-10 mm above the table, runs_meta/ea_t15.png); a side clamp needs
   the plate >= ~25 mm above the table (blade extends 25 mm below the TCP plane), so the new grasp closes on
   nothing (finger stops at -0.029, no grasp contact).
4. Cap-region grasp (analysed, not run): the COM is 70-100 mm away on the far side of the only support
   (the silver bar at gold y 64 mm), so the 9-14 N grip would need ~20 N to hold the gold level.

Conclusion: with the unchanged YAM (about 9-15 N squeeze, 25 mm-thick blades, reach limits) I found no
friction-grasp plan for easier. The smallest changes that would likely make it work: a second gold support
(e.g. a fixed rest/post on the table under the gold's fork end during the slide, i.e. a scene fixture),
or a stronger/longer-padded gripper, or allowing the old task's grasp assist (weld) - all outside the rules.

easier layout currently built: p_world = p_old/1000 + (0.54, -0.10, 0.7500), no rotation (tools/layout.py TIER_LAYOUT).
