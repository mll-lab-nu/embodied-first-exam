# rope_threading -> YAMLab: STATUS

Updated 2026-10-12 ~18:30 vast time, FINAL hand-over state (agent: rope_threading task agent). Nothing of this agent
is running on vast. Local source of truth: this folder. vast:
`/workspace/yamlab_port/runs/rope_threading/` (`yamlab/` = our copy + overlay, `task/` = mirror of this folder,
`work/` = logs and runs).

## State

| tier | task + goal check | rope model | oracle (from reset, mode=evaluation) | replay | nop / naive | metrics |
|---|---|---|---|---|---|---|
| easy | DONE: `RopeThreading-Easy-v0`, release-profile predicate (strict logged) | D6 capsule chain, stiffness validated | SUCCESS: or3, success at control step 4963 (165.4 s sim, 475 s wall) | open-loop replay x2 SUCCESS at step 4963, bit-identical to the oracle and to each other on vast (rope_state_sha16 20fa2e63d0ea5887) | nop2 FAILS (180 s, not threaded); naive2 (no R2 feed) FAILS (sequence R1- only, quiet); naive1 (tip beside R1) FAILS (no crossing) | metrics.json per run |
| medium | registered (`RopeThreading-Medium-v0`), assets NOT built, no layout chosen | same | NOT STARTED (re-layout study only, see "Medium" below) | - | - | - |

Evidence (vast `work/runs/`, copies of small files in `evidence/`):
- or3 (deliverable oracle): actions.npy (4963 x 14), states.npz (rope link poses, both TCPs, joints, actions per step),
  goal_log.jsonl (goal diagnostics per step), metrics.json, states_plot.png (stage snapshots; stand-in for video).
- rp1, rp2: replays of or3/actions.npy (metrics.json, states.npz). nop2, naive1, naive2: from-reset negatives.
- or1/or2: hold-finish runs (earlier, strict predicate as success); or4: release finish run to its end (diagnostic,
  env mode "replay", no terminations).
- Video: not rendered (vast has no RTX). Lead: run `tools/replay.py --actions or3/actions.npy --enable_cameras` on ws.

## Re-layout (old table frame mm -> YAM world m)

`world_xy = Rz(+90 deg) @ old_xy/1000 + (0.58, 0.0)`, `world_z = 0.7500 + old_z/1000`
(i.e. `x_w = 0.58 - y_old/1000`, `y_w = x_old/1000`). Whole scene rigid (rings, stands, bases, rope); ring
geometry, heights above the table, relative poses, threading order and direction unchanged.
- easy: R1 centre (0.599, 0.075, 1.0819), normal +y (R1- = travel -y); R2 centre (0.460, -0.025, 1.0609),
  normal -x (R2+ = travel -x). Rope start tip (0.530, -0.370), end tip (0.530, 0.330), U bulge at x 0.88.
- Why: the rings come toward the arms (R2 plane x 0.46, R1 x 0.60), the rope's U bulges away (inside the table).
  `tools/keypose_study.py` (numpy IK on the unchanged YAM): all four threading strokes (left feeds R1 -y, right
  receives behind R1, right feeds R2 -x, left receives behind R2) are reachable for tx 0.50-0.62, |ty| <= 0.08;
  tx 0.58 leaves the most table in front of R2 for the tail. The yaw -90 alternative puts R2 at x ~0.74 (out of
  reach at ring height); yaw 0/180 spans the 70 cm table depth with the rope alone.
- z: old z is height above the tabletop; mapped onto the table collider's support height 0.7500 (nominal top 0.7517;
  knot_untying measured resting bodies at 0.7500), so the bases sit on the table.
- The ALOHA base risers (`left/right_base_riser.stl`) belong to the old robot and are dropped (YAM unchanged).

## Rope model (measured)

- One reduced-coordinate PhysX articulation: 110 capsules r 4 mm, d 10.0 mm (L 1.1 m), self-collision on;
  generic D6 joints (translations locked, rotX/Y/Z drives; knot_untying found that SphericalJoint drives are inactive
  in an articulation). k_bend = E I / d = 0.1005 N m/rad, k_twist = G J / d = 0.0773 N m/rad (E 5 MPa, nu 0.3);
  mass rho pi r^2 d = 0.327 g/link (35.9 g); mu 0.3; damping 1e-2 N m s/rad; armature 1e-5 kg m^2.
- Stiffness check (`probes/probe_stiff.py`, clamped cantilevers, CPU PhysX dt 1/120): tip droop 12 links 6.9 mm
  vs Euler-Bernoulli 7.0 mm; 20 links 56 mm vs 58 mm (small-deflection theory). Damping 2e-4 rings for seconds,
  2e-3 leaves 1-4 mm/s on the 20-link cantilever, 1e-2 + armature 1e-5 is quiet at once (FD speed 0.002 mm/s).
- Rest shape = the start U (drive targets = start-shape joint coordinates), as the release profile's
  `rope_reference_shape="initial"`; a reset event writes those targets (knot_untying zeroes them: straight rest).
- Start state: 4 s settle on the table: drift 0.3 mm, FD speed 0.3-0.5 mm/s, joint gaps 4e-8 m, no crossings.

## Goal check (old `RopeThreadingTask.evaluate_state`, released terminal)

`threading_geom.threading_check`: `aperture_crossings` (copied line for line from topogym passage.py) on the chain
centreline (111 joint points, material order link_000 -> link_109 = CSV row 1 -> last). Per ring: usable radius
R - tube - (r_rope - 1 mm allowance) - 0.1 mm margin at the centre plane; nominal-aperture count equal (thickness);
slices at +-tube radius (round-ring profile) with the same sign list; no ambiguity; all hits sorted along the material
== order. Quiet = max FD speed of joint points + link centres over one control step <= 1 cm/s; intact = finite +
joint gaps <= 1 mm; held 15 control steps (0.5 s), latched; holding allowed. Strict class defaults logged per step.
`probes/test_predicate.py` (strict params): correct route threaded; wrong order, wrong direction at R1, passing over
R1, wrapping R1 twice and grazing the rim (centre 66.5 mm off-axis) all rejected (the rim graze passes the release
profile, as intended by its allowance).

## Deviations

- D1 rope = capsule chain articulation instead of FEM IPC (stiffness from the same E, nu; mass from rho).
- D2 (rim contact) a rope resting on a ring's lower rim crosses at R - tube - r = 65.0 mm, outside the strict usable
  radius 64.9 mm (0.1 mm margin, no contact allowance), so the strict predicate needs the rope held off the rims;
  the release profile's 1 mm allowance accepts a resting rope (the task's success predicate, see the next item).
- D2 thresholds: success = the RELEASED task's terminal (release profile `contact_relaxed_v16`,
  topogym/tasks/release_profile.py, which the robotangle-r2 instances and the STL package come from: 1 cm/s quiet,
  1 mm aperture contact allowance, round-ring slices, 0.1 mm margin, 0.5 s). The old class defaults (1 mm/s, no
  allowance, cylindrical slices) are logged per step as `strict_threaded` / `strict_quiet` / `strict_crossing_sequence`.
  (Until 17:00 the strict set was the success predicate; or1/or2 ran with it.)
- D3 quiet uses finite differences over one control step (PhysX link velocities are noisy at rest).
- D4 table height = support height 0.7500.
- D5 no grasp assist (the release used `ipc_soft_band_v1`): friction grasps only; YAMLab's finger contact filter
  can match one body, so is_grasping()/the grasp clamp do not see the rope (filter on link_109 only); the oracle
  limits its own squeeze (finger target -1.5 mm).
- D6 rope-robot contact: all YAM links collide with the rope (the release used fingers-only rope contact).
- D8 runs use mode="evaluation" (terminations on, CPU, 1 env); the task has no rope-off-table termination (the old
  task has none and the oracle hangs the rope end over the table edge).
- D7 YAMLab's recorder writes /tmp/isaaclab/logs/dataset.hdf5 for every process; two concurrent runs fail on its
  h5 lock, so the task cfg points the (unused, EXPORT_NONE) recorder at a per-process dir.

## Oracle progress (easy)

Status 2026-10-12 ~18:00 vast time: the oracle SUCCEEDS from reset in mode="evaluation" (one continuous run).
- or3 (DELIVERABLE, default `--finish release`, release-profile predicate): success at control step 4963
  (165.4 s sim, 475 s wall on vast), rope_state_sha16 20fa2e63d0ea5887. The goal latched in the stillness right
  after the R2 feed (the right still holds the rope), i.e. before the release part of the finish starts; at the latch
  the strict diagnostics are also true (sequence R1-, R2+; max FD speed 0.88 mm/s).
- or1 / or2 (`--finish hold`, at that time with the strict predicate as success): success at 4974 / 5149, strict and
  release both true at the latch (max FD speed 0.77 / 0.66 mm/s).
- or4 (diagnostic, env mode "replay" = no terminations, release finish run to its end: left receives past R2, pulls
  the end through, releases): the released rope still satisfies the release predicate (held 151 steps at the end,
  max FD speed 0.57 mm/s) but NOT the strict one (strict_threaded false: the rope rests on the rim, thickness band),
  as expected from D2.
Replay (x2) bit-identical; nop2 / naive1 / naive2 fail (see State).
Goal values at the or3 latch (step 4963, goal_log.jsonl): threaded true, crossing_sequence [R1-, R2+], thickness_clear
true, quiet true (max FD speed 0.88 mm/s), intact true (max joint gap 5.9e-8 m); strict_threaded true, strict_quiet true.

Stages (tools/oracle.py, measured):
1. ledge regrasp (left): fingertip-pinch drags move the end until ~0.24-0.27 m of rope overhang the left table edge
   (true collider edge y = 0.65), deep top-down grasp of the overhang 0.17-0.20 m from the tip (rope 11.8 mm inside
   the pads, lift slip 0.5-0.7 mm); back over the table, roll about the rope axis, climb, 180 deg wrist roll
   (tip -> -y), settle on the feed frame.
2. feed R1 (left): tip 8-9 cm through R1, sequence R1- (slip 0.01-0.06 mm).
3. receive (right): approach ~(0.3, 0.7, -0.6) reaching across, rope 11.7 mm inside the pads; left releases.
4. pull 1 (right): 0.34-0.36 m of rope through R1 (slip 0.1-0.25 mm).
5. regrip (right alone): lower the end, release (the rope hangs from R1's rim), re-grasp the hanging rope deep
   0.17-0.19 m from the tip, choosing a grasp whose frame can be rotated in place to the R2 feed frame (rope-axis
   sign matters: only z_tcp away from the tip reaches the feed frame), lift, re-orient.
6. feed R2 (right): tip 7.3 cm through R2, sequence R1-, R2+ (slip 1-1.7 mm); hold still -> goal latches.
Finish (default `--finish release`: left receives past R2, pulls the end through, both release; `--finish hold`:
the right keeps holding). In practice the goal latches in the stillness right after step 6, before the finish
moves. The released end state passes the release predicate but not the strict one (rope on R1's rim, or4 / D2).

## Findings that shape the oracle

- YAM fingers: flat pads 74 x 65 mm, tips 37 mm beyond the TCP; closing on the 8 mm rope stops at finger q -0.0049
  (squeeze kp 2000 x 3.4 mm = 6.8 N per finger with target -1.5 mm). A rope lying on the table can only be pinched
  in the last ~2 mm of the pads. That pinch holds translations (10 cm lift: 0.05 mm slip; 90 deg yaw: < 3 mm) but
  the rope PIVOTS in the jaws (40 deg about the jaw axis during a yaw, t24) and is pulled out when the stiff rope
  must bend back under the grip while climbing to ring height (t5, t18, t22: dropped at 0.93-1.0 m). Fix: the
  ledge regrasp above (a deep grasp), no in-air handover needed.
- In-air handovers between the arms were not workable: the ring stands crowd the middle of the table (R2 post at
  (0.46, 0.05), R1 ring/stand at y 0.075, x 0.52-0.68), and every support grasp the second arm could reach clashed
  with the first gripper or a stand (probes/handover_search*.py).
- The real table collider (workstation.usd `table_surface`) spans x 0.3025-0.8975, y -0.65..0.65 (yam.yaml's nominal
  top is x 0.2995-1.0015, y +-0.55); a solid `base_boundary` block fills x < 0.2975 up to the tabletop.
- The left arm cannot hold a rope running along x above z ~0.9 (approaches in the y-z plane, probes/roll_reach.py),
  so all re-orientation toward the feed pose happens low or by the 180 deg wrist roll (feasible at x 0.55-0.60,
  y 0.30-0.46, z up to 1.05; probes/flip_reach.py).
- Ring stands block the arms: the left arm stalled on the R2 post (joint1 error 0.26 rad at its 28 N m limit,
  run t12). The oracle now checks a capsule model of both arms against the rings/stands, the table and each
  other (`tools/plan_np.py`), which predicts that stall.
- Reach: the right arm can support the rope only near the end tip, with the left pinch carried to about
  (0.52, 0.18-0.25, 0.86-0.90) (`probes/handover_search2.py`).

## Medium (R1-, R2+, R3+): what was done, what is missing

- The old medium scene does NOT fit the YAMLab tabletop collider (x 0.3025..0.8975 = 0.595 m deep, y +-0.65) in any
  rotation: the footprint of rope start + stand bases needs >= 0.623 m of depth (best yaw 45 deg; yaw 0: 0.708 x
  0.747 m). With the easy transform R3 would land at world (0.205, 0.09), on the robots' base block.
  So the medium re-layout must place the RING ASSEMBLY rigidly (all ring geometry / heights / relative poses / order /
  direction kept) and give the ROPE START its own rigid placement (shape unchanged, unthreaded, clear of the stands) -
  a documented deviation. Code support: `threading_geom.RELAYOUT[tier]` may carry `rope_yaw_deg` / `rope_t_xy`
  (used by `start_centerline_world`); `RELAYOUT["medium"]` still holds the easy transform (placeholder).
- Reach study (`tools/medium_layout_search.py --rings_only`, numpy IK + capsule collisions, both arms, 6 strokes =
  feed/receive at R1, R2, R3; 494 candidate layouts with the stand bases on the table): stopped at the wrap-up after
  32 layouts (evidence/medium_layout/medium_layout_partial.log). Best so far: yaw 0, t = (0.44, -0.04) with 5/6
  strokes (R1 feed L/R, R1 receive R, R2 feed R, R2 receive L, R3 receive L; R3 FEED not reachable by either arm);
  yaw 0 with t (0.50-0.56, -0.04..+0.08): 4/6 (R1 feed and R3 feed missing). No layout with all 6 found yet.
- Missing: finish the reach search (all yaws; it takes ~4 h with 16 numpy workers on loaded vast - run with
  `--step 3`, or restrict to yaw 0/180/345/15 first), choose the ring transform + rope-start placement, build the
  medium assets (`tools/build_assets.py --tier medium`, needs Isaac/pxr), extend the oracle with a third ring
  (feed R3 travelling +n3 = (0.3, 0.9, 0.316) tilted 18 deg up), replay, negatives.
- Best next idea: R3's feed is the bottleneck (its travel direction points up and away). Try yaw 180 (old +y -> world
  -y, R3 on the right arm's side) and feeding R3 with the arm that received at R2 after a drop-and-regrasp like the
  easy R2 stage; the old oracle relayed R3 with the second arm (left grasp 24 cm behind the tip).

## Blockers

None for easy. Medium needs a new layout (see State). Notes for the lead:
- The goal latches before the release part of the default finish, because the rope is already threaded and still
  while the right holds it (the old task's session also ends on the first success tick). The release finish itself
  ends in a state that passes the release predicate but not the strict one (or4).
- `tools/resume.py` + `--save_ckpt` (stage snapshots) are development helpers only; all deliverables run from reset.
