# rope_threading -> YAMLab: STATUS

Updated 2026-10-14 ~19:00 local (orbits3 00:00 UTC): medium DONE on the D12 layout (deliverable mor1, see "Medium, D12
layout"); medium runs on orbits3 `/data/pingyue/yamlab/runs/rope/` (`work/runs/<run>`, `work/render/`).
Easy: 2026-10-12 ~18:30 vast time, FINAL hand-over state (agent: rope_threading task agent). Nothing of this agent
is running on vast. Local source of truth: this folder. vast:
`/workspace/yamlab_port/runs/rope_threading/` (`yamlab/` = our copy + overlay, `task/` = mirror of this folder,
`work/` = logs and runs).

## State

| tier | task + goal check | rope model | oracle (from reset, mode=evaluation) | replay | nop / naive | metrics |
|---|---|---|---|---|---|---|
| easy | DONE: `RopeThreading-Easy-v0`, release-profile predicate (strict logged) | D6 capsule chain, stiffness validated | SUCCESS: or3, success at control step 4963 (165.4 s sim, 475 s wall) | open-loop replay x2 SUCCESS at step 4963, bit-identical to the oracle and to each other on vast (rope_state_sha16 20fa2e63d0ea5887) | nop2 FAILS (180 s, not threaded); naive2 (no R2 feed) FAILS (sequence R1- only, quiet); naive1 (tip beside R1) FAILS (no crossing) | metrics.json per run |
| medium | DONE: `RopeThreading-Medium-v0` on the D12 layout (code default since 2026-10-14; deviations D9-D12, D10 = 300 s limit), same predicate | same | SUCCESS: mor1, success at control step 7233 (241.1 s sim of 300 s, 1157 s wall on orbits3), crossings [R1-, R2+, R3+] | open-loop replay x2 (mrp1, mrp2) SUCCESS at step 7233, bit-identical to the oracle and to each other (rope_state_sha16 a6d7bc53ec2c50d3) | mnop1 FAILS (300 s time-out, no crossing); mnaive1 (tip beside R3, the first ring fed) FAILS (no crossing; run ends at the receive, grasp blocked); mnaive2 (naive_nolast: R1 never fed) FAILS (sequence [R2+, R3+], quiet) | metrics.json per run; video `video/medium/` |

Evidence (vast `work/runs/`, copies of small files in `evidence/`):
- or3 (deliverable oracle): actions.npy (4963 x 14), states.npz (rope link poses, both TCPs, joints, actions per step),
  goal_log.jsonl (goal diagnostics per step), metrics.json, states_plot.png (stage snapshots; stand-in for video).
- rp1, rp2: replays of or3/actions.npy (metrics.json, states.npz). nop2, naive1, naive2: from-reset negatives.
- or1/or2: hold-finish runs (earlier, strict predicate as success); or4: release finish run to its end (diagnostic,
  env mode "replay", no terminations).
- Video: `video/easy/` (the lead's state-playback render of or3 on ws).
- medium (orbits3 `work/runs/`, copies in `evidence/`): mor1 (deliverable: actions.npy 7233 x 14, metrics.json, goal-log tail),
  mrp1, mrp2 (replays: metrics.json), mnop1, mnaive1, mnaive2 (negatives: actions, metrics, goal-log tail). R2a / R2a_rp: the
  development run mor1 reproduces (same actions byte for byte). Video `video/medium/{top,rings}.mp4` (state playback of mor1).

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
- D9 (medium only; approved by the user 2026-10-12 via the YAMLab coordinator) the ring assembly and the rope start
  are placed rigidly EACH. Reason: the old medium scene (three rings + stand bases + rope start) needs >= 0.623 m of
  table depth in any rotation; the YAM table collider has 0.595 m (x 0.3025..0.8975). Transform
  (`threading_geom.RELAYOUT["medium"]`): rings, stands, bases `world_xy = Rz(yaw_deg) old_xy + t_xy`; rope start
  `world_xy = Rz(rope_yaw_deg) old_xy + rope_t_xy` (z as easy). Ring geometry, heights above the table, relative ring
  poses, order and direction are unchanged; the rope shape is unchanged and unthreaded; relative to the rings the
  rope start is turned 90 deg (its 0.70 m wide U only fits along the table width). First values (2026-10-12 21:50, superseded by D11/D12 below; from
  `tools/medium_layout_search.py --reverse` + `--refine`): rings yaw 195, t (0.54, 0.12); rope yaw 90, t (0.58, -0.05)
  = the easy rope start shifted 5 cm to -y, all stand bases inside its U, >= 63 mm clear (t x 0.58 was tried 10-13: the right arm then drags too little overhang for the ledge grasp). The first proposal (yaw 0,
  t (0.44, -0.08), `medium_layout_v1.png`) failed in Isaac: the R3 stand stood 0.2 m in front of the left shoulder
  (no collision-free ready pose) and the end's pick region lay under R3. Figure: `evidence/medium_layout/medium_layout_v2.png`.
- D10 (medium only; approved by the user 2026-10-13 via the YAMLab coordinator) episode length 300 s instead of
  YAMLab's default 180 s (`configs/tasks/rope_threading.yaml` `variants:`; easy keeps 180 s). The old task has no time
  limit; three rings take ~4 min at the oracle's pace (md49 was truncated at 180 s during the second ring's re-grasp).
- D11 (medium only; proposed by the user 2026-10-14 ("why can the rope start not be on the left"), approved via the
  YAMLab coordinator; implemented with D12, code default since 2026-10-14) the rope start is mirrored across the U's
  symmetry axis (the U still bulges away from the robot; the material start, the fed end, lies on the left next to R3, the
  end on the right). Rope shape, material order and the success predicate are unchanged (the predicate uses point order and
  ring normals, not handedness); a mirror is not a rigid motion, so it relaxes D9's "rope shape unchanged". Evaluation:
  `evidence/medium_layout/yaw15_mirror_eval.md`.
- D12 (medium only; approved by the user 2026-10-14 via the YAMLab coordinator: ring-group translation, with margin) the yaw 15
  ring group of D11 moves from t (0.532, -0.241) to t (0.612, -0.351) (yaw 15 and the mirrored rope start kept); the rope t is
  re-chosen: (0.54, -0.03) in the mirrored convention (RT_RELAYOUT rope_t_xy (0.54, -0.0703)), the valid placement (>= 3 cm from
  bases/posts, left pick and the pick's first drag feasible) nearest the D11 rope. Reason: at the D11 t, R3 is too close to the left
  shoulder (easy's flip/roll/push moved rigidly onto R3: IK 33/38; the oracle's settle onto the R3 feed frame fails, M1-M3). Choice
  (`tools/layout_eval_shift.py`, 2 cm grid x 0.532-0.652, y -0.271..-0.391): every check passes at t and its 8 neighbours; margin
  +x >= 4 cm (grid end), -x 6 cm, +y 6 cm, -y >= 4 cm; weakest step R1 feed (right arm, 2 poses, the most anywhere). Backup t
  (0.592, -0.351). Code default since 2026-10-14: `threading_geom.RELAYOUT["medium"]` = dict(yaw_deg=15, t_xy=(0.612, -0.351),
  rope_yaw_deg=90, rope_t_xy=(0.54, -0.0703), rope_mirror_deg=90), `assets/medium/` = the build with these values (orbits3
  `assets_s612`, byte-identical); RT_RELAYOUT / RT_ASSET_DIR remain for exploration only. Evidence: `evidence/medium_layout/yaw15_shift_eval.md`.

## Medium, D12 layout: DONE (2026-10-14, orbits3; deliverable mor1)

Deliverable (final code, code-default layout, no RT_* variables; mode evaluation, one continuous run from env.reset()):
`run.sh 7200 task/tools/oracle.py --task RopeThreading-Medium-v0 --out runs/mor1 --feed_tip start --pick_arm left --flip 1
--ledge_align 0 --reseat 0 --finish hold --repush 0 0 --chain LR,RR,R --grasp_from_tip 0.24 --overhang 0.31 --recv_env_clear 0.01
--flip_x 0.622 --flip_y 0.345 --pull_xyz [[0.58,-0.1,1.0],[0.635,-0.532,1.0]] --drop_xyz [[0.58,-0.12,0.9],[0.5,-0.4,0.95]]
--lay [null,[0.51,-0.42,18,0.17]] --lay_drag 0.10` (the recorded args of mor1 and R2a differ only in --out and the development flag
--save_ckpt).
- mor1: success at control step 7233 (241.1 s of the 300 s limit, wall 1157 s), rope_state_sha16 a6d7bc53ec2c50d3; at the latch
  threaded, crossings [R1-, R2+, R3+], quiet (max FD speed 0.47 mm/s), intact (max joint gap 1.7e-7 m); strict_threaded false
  (rope on a rim, D2), strict_quiet true. actions.npy is byte-identical to R2a's, metrics `final` and all stage logs equal:
  the pinch-closed check added after R2a (`check_closed`, reads the finger only, never steps the sim) changes no action.
- Replays (`replay.py --actions mor1/actions.npy`): mrp1, mrp2 success at step 7233, rope_state_sha16 a6d7bc53ec2c50d3 (both).
- Negatives (same arguments + --variant): mnop1 (`--variant nop --nop_steps 9000`) holds the start pose and is truncated at
  step 9001 (300.0 s): no crossing, success false. mnaive1 (`naive`: the first feed passes the tip 13 cm beside R3, the first ring
  fed) ends the feed 0.19 m past R3's plane, 0.19 m off-axis, no crossing; the right's receive grasp is then blocked (jaw stopped at
  62 mm, `grasp_right_blocked`, step 4004) and the run stops: success false, sequence []. mnaive2 (`naive_nolast`: the oracle up to
  the receive past R2, then 20 s still) never feeds R1: sequence [R2+, R3+], quiet (1.5 mm/s), threaded false, success false
  (stops at step 6591).
- Video (state playback, `setup/render_states.py`, same pipeline as easy): dump of the actions on orbits3 (R2a/actions.npy, byte-identical to
  mor1's; no cameras; success at the same step 7233, the terminal step is not recorded: 7232 states), render on orbits3's RTX 4090 (libGLU.so.1 + libOpenGL.so.0
  copied to `/data/pingyue/yamlab/deps/lib`, LD_LIBRARY_PATH), every 2nd state at 15 fps (real time), 3617 frames, pose readback
  error 7.7e-7 m. `video/medium/top.mp4` (top camera), `video/medium/rings.mp4` (render-only camera from the far-left corner,
  eye (0.90, 0.35, 1.35) -> (0.62, -0.17, 1.02), fov 55 deg: all three rings and the route).

Development run R2a (the same actions; launched with `shift_run.sh s612`, i.e. the D12 layout via RT_RELAYOUT / RT_ASSET_DIR):

`shift_run.sh s612 R2a --chain LR,RR,R --grasp_from_tip 0.24 --overhang 0.31 --recv_env_clear 0.01 --flip_x 0.622 --flip_y 0.345
--pull_xyz [[0.58,-0.1,1.0],[0.635,-0.532,1.0]] --drop_xyz [[0.58,-0.12,0.9],[0.5,-0.4,0.95]] --lay [null,[0.51,-0.42,18,0.17]]
--lay_drag 0.10` (mode evaluation, finish hold): success at control step 7233 (241.1 s of the 300 s limit, wall 1118 s),
rope_state_sha16 a6d7bc53ec2c50d3; crossings [R1-, R2+, R3+], quiet 15 steps (max FD speed 0.5 mm/s), tip 0.122 m past R1 (16 mm
off-axis). Up to recv2 (step 5991) the run is step-identical to X6a. Actions: `work/runs/R2a/actions.npy` (7233 x 14; copy +
metrics in `evidence/R2a/`). Open-loop replay (`replay.py`, R2a_rp): success at 7233, same rope_state_sha16.
- R1 stage (`oracle.lay_regrip`, new `--lay`): the right, holding the end 0.071 m from the tip after receiving R2, carries it to the
  table under R1's feed line and drags it 0.10 m along R1's horizontal feed direction yawed 18 deg, lets go, pinches the rope 0.17 m
  from the tip top-down (z_tcp toward the tip) and lifts; to_feed_frame then turns in place about the grip onto an R1 feed frame
  (chord correction 58.6 deg, direction d1, approach (0.93, -0.20, -0.32)); after a lay it also requires the whole push to be a
  feasible line (`stroke_ok`; L2r's frame 10 deg off d1 left the workspace mid-push and fed only 0.5 of the stroke). Stage times:
  lay 20.5 s, orient 13.9 s, feed + latch 7.0 s.
- Why not the others (offline `tools/r1_screen.py` on the X6a states, Runner criteria): the left reaches no rope point between R2
  and the right hand (0/68 poses at every 0.03 m from 0.10 to 0.40 m from the tip); the rope hanging from R2 after a drop gives 2-3
  reachable grasps per distance and none turns onto a feed frame, neither in place nor by a joint-space route (direct or via pose).
- Dev runs from X6a/ckpt_recv2: L1r (lay at 0.15 m, 0.20 m drag) threads R1 (tip 0.048 m past) but never goes quiet: the drag pulled
  the tail through R3 until the material end hung 2 cm above the table and chattered (FD 1.2-5 cm/s for 20 s); L2r (0.17 m, 0.20 m
  drag) succeeds but marginally (push 0.5, tip 0.013 m past, 15 cm of tail left behind R3); L3r (= R2a's settings) succeeds with
  tip 0.123 m past and the tail still on the table. The 0.10 m drag pulls ~0.3 m less rope through R3 than the 0.20 m drag.
- Figure: `evidence/medium_layout/r1_lay_R2a.png`; run table: `evidence/medium_layout/yaw15_shift_eval.md`.

## Medium attempt A (2026-10-12/13): yaw 195, reverse route — stopped at the R3 -> R2 transfer

Layout `RELAYOUT["medium"] = dict(yaw_deg=195.0, t_xy=(0.54, 0.12), rope_yaw_deg=90.0, rope_t_xy=(0.58, -0.05))`;
oracle `--feed_tip start --chain RL RL L --flip 1 --reseat 1 --ledge_align 1 --feed_extra 0.025 --recv_min_from_tip 0.055
--handover 1 0 --regrip_from_tip 0.19 0.17 0.15 --feed_start 0.24 0.20 0.24 --feed_stop 0.07 0.07 0.07` (md26/md27 on orbits3).
Reached: right picks the start tip at the right edge, table re-seat, flip, R3 fed (R3+, tip 12.9 cm past), left receives,
pulls 0.22 m, drops (the rope stays threaded). Blocked: R2 can only be fed by the right while the left received R3;
drop + regrip (md26/27/34/35/39), in-air handover (md31, IK scan of 108 left positions), staging near R2's feed line
(md32/33/36-38) all fail; rotating the rings +-15/30 deg or pushing them 2-8 cm out does not help (IK); 90 % of the left's
failures are collisions with R1's ring/stand. Evidence: `evidence/medium_layout/blocker_R3_to_R2_transfer.png`,
`stuck_md26_R3done_*.png`, `stuck_md31_handover_*.png`. Physics found on the way: the rope pivots ~23 deg in the YAM jaws at the
ledge grasp (fingertip-only contact) and its free end curls with the rest shape (~1.5 deg/cm, rest = initial U).

## Medium attempt B (2026-10-13): yaw 0, t (0.40, -0.16), forward route — stopped at R1

Chosen because each ring's receiver feeds the next ring there (no transfer). With the rope start at t (0.58, -0.01) the
left's first pinch lay under R3 (md40); at t (0.58, 0.03) the pick passes (md42: drags, ledge grasp, table re-seat to
6.9 deg), but no rotation onto an R1 feed frame exists: the left's only R1 feed in the reach search is 21 deg off the ring
normal and the oracle feeds on-axis. The layout refine now checks the pick exactly as oracle.pinch / Runner.reachable
(seeded from the ready q, the other arm at its ready q): it reproduces md1-md4 and md40 (fail) and md5 (pass).

## Medium attempt C (2026-10-13): yaw 345, t (0.42, -0.08), rope t (0.58, 0.09), forward route — stopped at R1

From the re-screen of the approved D9 types (no transfer, or a feasible one; feeds within 25 deg of the ring normal):
only yaw 0 (attempt B) and this layout pass ready + pick. Chain LR, RL, L (as easy).
- md43/md44: the pick passes; R1 orient fails. The pick ends with the left top-down at the edge of its workspace (tip
  toward +y); in-place rotation, lifting > 6 cm or moving inward > 5 cm has no IK. The held chord is 38 deg off
  the gripper axis after the lift (13 deg while the free end is pressed flat). No feed frame with the held chord within
  25 deg of R1's normal is reachable (0 of 888).
- Oracle-only changes added (tier defaults for medium): `--reseat_at` (press at (0.65, 0.45), tip yawed to 90 deg),
  `--reseat_roll` -90 (roll about the rope axis after the press: jaw axis vertical), `--feed_cone` 25 (ring-1 feed
  directions up to 25 deg off d_1), and a joint-space route through `--orient_vias` [0.60, 0.10, 1.25] already in the
  feed orientation (offline transition search over press point x yaw x roll x route: 32 of 768 candidates pass).
- md45: the route reaches the R1 feed start (feed direction 10 deg off the normal), but the held chord is 51 deg off
  the gripper axis (15.7 deg pressed); aim corrections of 49 / 25 / 12 deg are unreachable; the tip stops 3.6 cm before R1.
- Probes (orbits3 copy only, reverted): squeeze +44 % from the ledge grasp on (md48): 17.5 -> 51.9 deg; rope
  torsional contact patch 4 mm (md47): 8.6 -> 47.7 deg. Neither changes the angle.
- Mechanism (measured afterwards from the states): the pinch holds the rope's angle rigidly; it is set when the ledge
  grasp closes on the overhang, which already bends down there (md43: 53 deg at closing, 37-40 deg after the press
  and slide; md45: 29-32 deg in the gripper frame while the joint route turns the gripper by > 100 deg). The chord adds
  the free end's curl (rest shape) and sag. In-air grasps (receive) align to <= 7 deg (md34). Gravity does not turn
  the rope in the pinch; the earlier reading of md43 (13 -> 38 deg = a turn in the pinch) was wrong.
- Options figure sent (evidence/medium_layout/deviation_options_grasp_pivot.png); the user rejected the grasp assist
  and fixed the layout at yaw 195 (next section).

## Medium, fixed layout (user, 2026-10-13): yaw 195, t (0.54, 0.12), rope t (0.58, -0.05)

Code and assets are back at attempt A's layout and oracle defaults; every figure uses tools/plot_layout.draw_state (top
view, robot at the bottom, R1 left, R3 right). Current blocker: evidence/medium_layout/current_blocker_yaw195.png (md34:
R3 done, the left holds the end past R3; R2 needs the right). Action-only methods asked by the user, offline:
- (i) jaw axis vertical: feed frames reachable (start + end grip, within 25 deg): R3 right 34, R2 right 2 / left 4
  (16 deg off), R1 left 36. The right's R3 feed already has the jaw axis near vertical (z -0.95): the 21 deg (pinch) /
  36 deg (chord) offset there is horizontal, from the ledge grasp; the rope does not sag in the pinch (chord 2-4 deg
  above the gripper axis).
- (ii) pre-compensation at R3 (md26): 25-50 % of the 36 deg plus an off-axis feed direction brings the chord within
  6 deg of the normal (reachable); the full 36 deg is out of reach (start pose out of the workspace, or wrist joints 4/5
  80-90 deg past their limits). R2 does not need it (in-air grasps <= 7 deg).
- (iii) closer grasp + short pushes: concerns the R3 push (which passes); not the R2 blocker.
The R2 blocker is the left -> right transfer. The left can feed R2 itself (4 frames, 16 deg off), so a path without an
arm-to-arm transfer is evaluated next; option 3 (rings placed one by one) + an action is the fallback.

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

## Medium (R1-, R2+, R3+): first reach study (2026-10-12; superseded by the sections above)

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

None for easy or medium. Notes for the lead:
- The goal latches before the release part of the default finish, because the rope is already threaded and still
  while the right holds it (the old task's session also ends on the first success tick). The release finish itself
  ends in a state that passes the release predicate but not the strict one (or4).
- `--save_ckpt` / `--resume` (stage snapshots) are development helpers only; all deliverables run from reset.
