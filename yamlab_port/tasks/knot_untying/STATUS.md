# knot_untying -> YAMLab: STATUS

Final state 2026-10-12, handed over (knot_untying task agent; the port goes to pingyue). Local source of truth: this folder. vast: `/workspace/yamlab_port/runs/knot_untying/` (`yamlab/` = our copy with the overlay, `task/` = mirror of this folder, `work/` = logs and outputs).

## State

| tier | task + goal check | rope model | oracle | replay | nop / naive | metrics |
|---|---|---|---|---|---|---|
| very_easy | DONE | D6 rope validated | SUCCESS in the normal env (evaluation mode, terminations on): or8 latches and terminates at step 2527 (84.2 s sim, 168 s wall) with a **tightest non-local gap of 18.89 mm at the latch step**. 2 carries with the left arm, then 3 two-arm held spreads (the left arm keeps holding the tail raised while the right arm shifts the strand next to the tight pair) | SUCCESS at step 2527, **bit-identical** (rope-trajectory sha c9f71a9870bc5148 in both), latch gap 18.89 mm in both | nop8 FAILS (time_out at 900 steps: 1 crossing kept, quiet); naive nv8 FAILS for the intended reason (crossing stays, rope intact and quiet). Both run in evaluation mode | runs/very_easy_or8/metrics.json |
| easier | DONE | same | SUCCESS in the normal env: ea7 latches and terminates at step 2235 (74.5 s sim, 182 s wall) with a **latch gap of 17.45 mm**. 4 carries with the left arm + 1 two-arm held spread | SUCCESS at step 2235, **bit-identical** (sha 6250d007cc138adf), latch gap 17.45 mm | nope8 FAILS (time_out: 2 crossings kept); naive nve8 FAILS for the intended reason (2 crossings stay, rope intact and quiet); evaluation mode | runs/easier_ea7/metrics.json |
| easy | DONE (S1, 2026-10-12) | same | SUCCESS in the normal env: ey2 (`--max_iters 8 --max_steps 6000`, other options default) latches and terminates at step 4370 (145.7 s sim, 262 s wall) with a **latch gap of 19.67 mm**. 6 carries of the start end with the right arm (crossings 2 -> 3 -> 2 -> 1 -> 2 -> 1 -> 0) + 2 two-arm held spreads (left arm; 7.9 -> 12.0 -> 16.3 mm) | SUCCESS at step 4370, **bit-identical** x2 (ry2a, ry2b: rope sha 193862bdb3bc286e = oracle), latch gap 19.67 mm | nop_ey FAILS (time_out at 900 steps: 2 crossings kept, quiet); naive_ey FAILS for the intended reason (2 crossings stay, rope intact and quiet); evaluation mode | runs/easy_ey2/metrics.json |
| medium | registered (`KnotUntying-Medium-v0`), assets built | same, overhand start representable | **NOT solved**: md1 (max_iters 6) node-deletion carries made the knot worse (3 -> 3 -> 4 -> 3 -> 9 crossings), then no free end was over at its first crossing; timed out. **Paused** by S1 2026-10-12 after 5 more rounds (see "Easy and medium") | - | - | runs/medium_md1_failed/metrics.json |

The two-arm held spread exists to make the latch happen at a wide gap (the threshold is unchanged at 8 mm). After a carry has lowered its tail with no crossing left, the carrying arm keeps the tail raised about 6 mm, so the rope is not "on the table" and the goal cannot latch. While the tightest gap is under `--held_target` 16 mm, the other arm grasps a strand 3-10 cm from the tight pair (at least 20 mm clearance, 18 mm jaw), lifts it 2 cm, shifts it 3 cm away from the pair and lets go (up to 3 times). Only then is the tail laid down and released. The goal latches only after that. The post-release spread stays as a fallback; it did not act in or8/ea7.

Evidence (vast `/workspace/yamlab_port/runs/knot_untying/work/`): `or8/`, `ea7/` (actions.npy, states.npz = per-step link poses + both TCPs + actions, goal_log.json, metrics.json with `latch_goal`, frames_topview.png), replays `rp8/`, `rpe7/`, negatives `nop8/`, `nv8/`, `nope8/`, `nve8/`. Local copies in `runs/`; older runs (replay-mode or1-or5, ea1-ea4 and their negatives) are in `runs/superseded/`. Video: rendered by the lead (`scripts/replay.py --actions runs/very_easy_or8/actions.npy --enable_cameras`, likewise `runs/easier_ea7/actions.npy` with `--task KnotUntying-Easier-v0`). The replay ends at the terminating step like the env.

## Easy and medium (easy done; medium paused)

- Settle (`scripts/build_assets.py`, same rope model and re-layout: yaw -90 deg, old bounding-box centre -> (0.56, 0)):
  - easy: 110 links (d 10.010 mm); after 6 s the order is O O U U (= start_state.md), crossing gaps 8.0 mm, max shape change 24 mm (median 3 mm).
  - medium (open overhand / trefoil): 107 links (d 10.035 mm); after 6 s the order is U O U O U O (= start_state.md), gaps 8.0 mm, max change 18 mm (median 7 mm). **The chain represents the overhand knot** (no pass-through, order kept).
- Oracle attempts (normal env, evaluation mode):
  - `ey2` (easy, S1): **solved** with the handover's suggestion (`--max_iters 8 --max_steps 6000`); it needs 6 carries because carries 1 and 4 each add a crossing back. `ey3` (`--past_deg 50`) oscillated between 1 and 2 crossings and timed out. Local runs (S1 host, same pinned stack): `/data/pingyue/yamlab/runs/knot/work/{ey2,ry2a,ry2b,nop_ey,naive_ey}`; video `video/easy/` (state playback: `render_states.py dump` + `render`, top camera + render-only close-up `rope=0.95,0.0,1.32:0.52,0.0,0.752:62`).
  - `ey1` (easy, superseded by ey2): the single-arm node-deletion carry (grasp the free end whose strand is over at its first crossing, carry it 35 deg past the under strand's tail) does not remove one crossing per carry here. The stiff rope springs back, and carry 1 even added a crossing. After 4 carries one crossing was left when `--max_iters 4` ran out. **Best next step: rerun with `--max_iters 8`** (`oracle.py --task KnotUntying-Easy-v0 --max_iters 8 --max_steps 6000 --out ey2`); the trend (3 -> 2 -> 1) suggests it finishes.
  - `md1` (medium): the same rule fails on a true knot. Carrying the end over strands one at a time rearranged the knot into 9 crossings, and then no end was over at its first crossing. The overhand needs the actual untie move: pull the end tail back out through the loop, i.e. follow the tail's own path in reverse (HULK-style "pull the strand through" with the other arm pinning the loop), not single carries. **Best next idea:** grasp the end tail near the knot, lift 5-8 cm, and draw it back along its own centreline (the sequence of stations s -> L) while the other arm pins the loop body; then re-plan the remaining crossings with the current carry rule plus the held spread.
- **Medium, S1 2026-10-12: paused, not closed** (user decision) after 9 attempts and 5 rounds; the medium code is not committed. Patch against c321f495b: `/data/pingyue/yamlab/runs/knot/medium_wip.patch` (`--slip`, `--channel`, `--carry_check` in scripts/oracle.py). Figures: `/data/pingyue/yamlab/runs/knot/figs/round2_ms2i_*.png`, `round4_mc4_*.png`, `round5_ms5_*.png` (script `knot_fig.py` there).
  - The untie works: `--slip 2 --slip_side inner` grasps the strand lying over the start tail at c0 on the inner side, lifts it 5 cm and carries it down the tail and round the tail tip, while the other arm holds the end tail 0.5 m along the rope. c0 slips off the start tip, and the carries reach 1 crossing (ms2i step 3146; ms5 steps 2672 and 4401).
  - Blocker: the last curl (1 crossing) with a 0.45 m start tail. The original carry (grasp 3 cm from the tip, radius 0.36 m) is out of reach (target x 0.765, IK error 18-47 mm). `--carry_check` (grasp <= 0.20 m from the crossing; options ranked by predicted crossings; unreachable options skipped; options that made no progress not repeated) reaches, but the trailing 0.25 m of tail follows the gripper and re-crosses (1 -> 3, 1 -> 2). One grasp too close to a crossing pressed stacked rope through the table (rope_off_table termination, ms5 step 6136).
  - The user's channel method (`--channel`: one arm holds the strand over c0 4 cm beyond it, raised 2.5 cm; the other pulls 7.5 cm past c1) draws about 2 cm per stroke, because only 0.24 m of rope lies between the hands.
  - Other findings: an unpinned pull drags the whole light knot (0.33 g/cm); a tensioned strand bent over the tail clamps it; two YAM wrists closer than ~12 cm collide; a jaw landing on the rope makes PhysX eject it.
  - Next step: for the last curl, first pull the long tail straight along its own direction to a place where it crosses nothing, then carry the curl a short distance. Require grasp points >= 2.5 cm from crossings and other strands.

## Reproduce (vast)

```
# once: ./sync.sh (local -> vast) and ./vssh.sh bash /workspace/yamlab_port/runs/knot_untying/task/apply_overlay.sh
cd /workspace/yamlab_port/runs/knot_untying/work
../task/vrun.sh 3000 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --max_steps 3000 --out or8          # success step 2527, latch gap 18.89 mm
../task/vrun.sh 3600 ../task/scripts/oracle.py --task KnotUntying-Easier-v0  --max_steps 3600 --out ea7          # success step 2235, latch gap 17.45 mm
../task/vrun.sh 1500 ../task/scripts/oracle.py --task KnotUntying-Easy-v0 --max_iters 8 --max_steps 6000 --out ey2  # success step 4370, latch gap 19.67 mm
../task/vrun.sh 3000 ../task/scripts/replay.py --task KnotUntying-VeryEasy-v0 --actions or8/actions.npy --out rp8  # sha c9f71a9870bc5148
../task/vrun.sh 3000 ../task/scripts/replay.py --task KnotUntying-Easier-v0  --actions ea7/actions.npy --out rpe7 # sha 6250d007cc138adf
../task/vrun.sh 1500 ../task/scripts/replay.py --task KnotUntying-Easy-v0 --actions ey2/actions.npy --out ry2a    # sha 193862bdb3bc286e
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --variant nop   --max_steps 900 --out nop8
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --variant naive --max_steps 900 --out nv8
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-Easier-v0  --variant nop   --max_steps 900 --out nope8
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-Easier-v0  --variant naive --max_steps 900 --out nve8
../task/vrun.sh 1500 ../task/scripts/oracle.py --task KnotUntying-Easy-v0 --variant nop   --max_steps 900 --out nop_ey
../task/vrun.sh 1500 ../task/scripts/oracle.py --task KnotUntying-Easy-v0 --variant naive --max_steps 900 --out naive_ey
python ../task/scripts/stress_summary.py nop8 nv8 nope8 nve8; python ../task/scripts/plot_run.py or8 10
```
Run at most 2 Isaac processes at once, under nice 19 (`vrun.sh` already applies nice/timeout). The oracle defaults are the final settings (35 deg carry, held spread to 16 mm, post-release spread to 11 mm, 3 spread attempts). Expect about 170-200 s wall per oracle run on the shared host.

## How the oracle / replay runs treat termination

- Runs or1-or5, ea1-ea4 and their replays used YAMLab's `mode="replay"`. In that mode `configure_for_replay` removes the `time_out` and `task_success` terminations, so those runs stepped past the latch. or5's spread therefore ran after the step where the registered env (evaluation mode) ends the episode and auto-resets. The lead's playback of or5 in the normal env correctly ended at step 1246 with the 8.0 mm gap. Those runs are superseded.
- From or6/ea5 on (final: or8/ea7), the oracle and `replay.py` create the env in `mode="evaluation"`, which is the registered env's normal behaviour: the `task_success`, `time_out` (= `--max_steps`) and `rope_off_table` terminations are active, CPU, 1 env. The run ends at the first terminated step, and the scripts take no further steps. Inside that last step the env auto-resets, so the logged rope pose for the final step is the reset state; `info["goal"]` and `goal_log` hold the evaluation from before the reset. `metrics.json` records the goal diagnostics at the latch step (`latch_goal`, `latch_min_nonlocal_m`).
- The spread now happens before release: the two-arm held spread described above. A one-arm version that shifted the held tail itself (or6) barely changed the gap (8.0 mm, the tight pair is at the old crossing, not at the tail end) and latched at 10.5 mm. A two-arm version with an 11 mm target (or7/ea6) latched at 11.2 mm / 9.8 mm, because once the tail is laid down the free tails can close up again; hence the 16 mm held target.

## Rope model verdict (for rope_threading)

**A capsule chain as ONE reduced-coordinate PhysX articulation works in YAMLab/Isaac Lab 2.3 (CPU PhysX, dt 1/120, YAMLab's 16 min iterations), with two traps.**

- 99-111 links in one articulation load fine (no 64-link limit). PhysX picks the middle link as the root.
- **Trap 1 - joint type: use a generic D6 joint (`UsdPhysics.Joint`, transX/Y/Z locked with LimitAPI low=1 > high=-1, rotX/Y/Z free, `DriveAPI` on rotX/rotY/rotZ).** A `UsdPhysics.SphericalJoint` gives the same 3 DOFs, Isaac Lab reads back the stiffness/damping, but **the drives are inactive** (a curled rope with k = 1e-3 stays curled; the D6 rope uncurls: `probes/probe_drives.py`). All my runs before 2026-10-12 ~09:30 (sweeps sw1-sw4, oracle or1/or2, naive nv1/nvA/nvB) therefore used a limp chain (no bend/twist stiffness, no joint damping, armature only). Re-done with D6 below.
- DOFs are named `j_iii:0/1/2` = rotation-vector components (x = twist about the link axis, y, z = bend) of `conj(q_i) * q_{i+1}`; writing these reproduces authored link poses to 1.8e-7 m for both joint types (`probes/probe_joints.py`, `build_assets.py` INIT_POS_ERR).
- **Trap 2 - initial pose: PhysX does NOT keep authored USD link poses** (joint coords start at 0 = straight). The knotted pose must be written as root pose + joint coordinates (`rope_geom.joint_positions_from_links`). The task overrides `default_root_state` / `default_joint_pos` from `start_state.npz` and an extra reset event zeroes the joint targets (Isaac Lab's `reset_scene_to_default(reset_joint_targets=True)` would otherwise make the knot the rest shape).
- Parameters (`overlay/yamlab/envs/tasks/knot_untying_lib/rope_params.py`):
  - capsule radius 4 mm, link length d = L/N (very_easy 99 links, d 9.989 mm; easier 111 links, d 9.990 mm), capsule cylinder height = d (caps overlap neighbours; adjacent links filtered by the articulation), self-collision on.
  - mass per link rho*pi*r^2*d = 0.326 g (rho 650), inertia from the capsule.
  - drives (implicit PD, target 0 = straight): bend k = E*pi*r^4/4/d = 1.0e-3 N m/rad, twist k = G*pi*r^4/2/d = 7.7e-4 N m/rad (E 50 kPa, nu 0.3); damping 1e-3 N m s/rad; **armature 1e-6 kg m^2 per DOF**.
  - rope material mu 0.3 (static = dynamic, average combine), restitution 0; contact offset 2 mm, rest offset 0; max depenetration velocity 0.5 m/s; articulation solver iterations 32 position / 4 velocity; sleep off.
- Stability numbers:
  - limp chain (sweeps sw1-sw4, 8 s from the knotted very_easy start): **without armature 7 of 8 variants blew up (NaN, "Illegal BroadPhaseUpdateData")**; with armature 1e-6 all stable; joint gaps <= 1.3e-7 m.
  - limp chain under the gripper: or1/or2 oracle carries fine, but a hard straight pull (naive nv1: tail pulled 3 cm beyond its length, tightening the loop neck) made the hanging strand whip at 0.1-0.3 m/s and blow up at step 276; armature 1e-5 (nvB) kept it intact (held-strand FD speed p95 0.08 m/s).
  - D6 rope, 6 s settle from the generator start: crossing count and order kept (very_easy O U, easier U O U O), crossing height gap 8.0 mm (= one diameter: the over strand rests on the under strand; the old frozen start had 16 mm), shape relaxes by max 14 / 19 mm (median 3 mm) under the bend stiffness.
  - **PhysX-reported link velocities are noisy at rest (median 5 mm/s, peaks 1-2 cm/s around the crossing) while positions are still**: finite-difference speed over one control step is 0.3-0.8 mm/s (limp chain, sw4). Not removed by damping, friction, iterations or sleep: TGS velocity noise, not motion -> quiet uses finite differences (D3).
  - table support height: resting bodies sit on z = 0.7500 (rope centres at 0.7540), 1.7 mm below `ROBOT.table_position` z = 0.7517 -> the goal uses 0.7500 (D2).
  - speed: rope alone ~100 physics steps/s; full task env with both arms ~17 control steps/s (CPU, nice 19, loaded host).

## Re-layout (old table frame mm -> YAM world m)

world_xy = R(-90 deg) * (old_xy/1000) + t, world_z = 0.7517 + old_z/1000 (old z is above the table top; rope then settles onto the 0.7500 collider), with R = [[0, 1], [-1, 0]] (old +Y = loop side -> YAM +X away from the bases; old +X -> YAM -Y), t = (0.659, 0.1357) m for very_easy and easier (old bounding-box centre (135.7, -99.0) mm -> (0.56, 0.0)). Reason: tails toward the robots, loop away, rope centred between the arms; very_easy rope spans x 0.38..0.74, y -0.145..0.146; the crossing lands at (0.532, 0.0). Topology, lengths and over/under unchanged.

All four tiers use the same rotation; per-tier translations (old bounding-box centre -> (0.56, 0.0)): very_easy t = (0.6590, 0.1357) m; easier t = (0.6590, 0.1357) m; easy t = (0.6590, 0.1357) m; medium t = (0.6087, 0.1364) m.

Measured reach (USD FK/IK, gripper pointing down, fingertips 2 mm above the table, `scripts/reach_map.py`): each arm reaches x 0.32..0.72 on its own side and across the midline to about y = -/+0.18 (left/right arm); nothing beyond x ~0.76.

## Deviations from the old task (so far)

- D1 rope = capsule chain (99 rigid links + spherical joint drives) instead of FEM IPC; bending/twist stiffness from the same E, nu; mass from rho.
- D2 table height for on_table = physical support 0.7500 (nominal 0.7517 is not where things rest).
- D3 quiet = max finite-difference speed of all link ends + centres over one control step <= 1 mm/s (old: FEM vertex speeds; IPC velocities are per-step displacement / dt too). PhysX's reported velocities are logged as a diagnostic only.
- D4 the start state is the settled chain (6 s settle, over strand resting on the under strand: crossing gap 8 mm instead of the old 16 mm generator start).
- D6 the oracle is new (single-arm node deletion with re-planning, USD-kinematics IK), not the old ALOHA oracle; thresholds of the goal (8 mm planar gap with the 2-diameter local excuse, -1/+3 mm table band, 1 mm/s, 0.5 s hold) are unchanged.
- D5 YAMLab's finger contact sensors filter only the rope's link_000 (a PhysX filter must match one body), so `is_grasping()` and the grasp clamp do not apply to the rope; the oracle limits its own squeeze (jaw 2 mm narrower than the rope).

- D7 the HDF5 recorder is disabled in the task cfg (the oracle/replay write their own npz; parallel runs contended for the recorder's file lock).

## Notes for the lead

- Pull stress with the D6 rope: naive straight pulls of the held tail (very_easy nv3) stay intact (held-strand FD speed p95 0.08 m/s, max 0.10). The limp-chain blow-up (nv1) does not recur.
- Quiet margin: at rest the FD speed is 0.2-0.8 mm/s with rare 1-2 mm/s blips (limp chain); the 15-step hold latched in all oracle runs.
- Tightest non-local gap at the latch step in the normal env: very_easy 18.89 mm, easier 17.45 mm (threshold 8 mm).

## Blockers

None.
