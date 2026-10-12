# YAMLab port of old RoboTangle tasks

**What this is.** A local, unpublished port of a subset of the **old (pre-MuJoCo, Genesis-based) RoboTangle tasks** into [YAMLab](https://github.com/ARISE-Initiative/yamlab) (MIT; Isaac Sim 5.1 + Isaac Lab 2.3.2, bimanual I2RT YAM arms). The robot and its settings stay exactly as YAMLab defines them; only the tasks are new. Each ported task gets a goal check equivalent to the old success predicate and a scripted oracle that solves it.

**Handed over to pingyue on 2026-10-12: start with `HANDOVER.md`.** Branch `dev/yamlab_port` (separate project, orphan history).

## Sources

- YAMLab: `yamlab/` (clone of ARISE-Initiative/yamlab @ ec0455d).
- Old task code: `ref/topogym_2dafa5f/` (worktree of `dev/jianwen` 2dafa5f2b, topogym on Genesis 1.2.1) and `ref/rcb_main_4ff51fa/` (worktree of `robot_coding_bench` main 4ff51fa5b). Detached, read-only use.
- Geometry: `../tmp/2026-10-11_robotangle_v1_stl/<family>/<tier>/` (STL in mm, layouts, start states, rope/cable/wire specs).

## Plan

See `PLAN.md` (feasibility per family, tier order, goal checks, oracles, risks) and `YAMLAB_NOTES.md` (what YAMLab is and how a task is built).

Priority (user): knot_untying, fiber_bundling, buzz_wire_3d first; then cast_keyhole (rigid backup) and rope_threading. Easiest tiers first.

## Status

| family | tier(s) | state | goal check | oracle | nop fails | video | notes |
|---|---|---|---|---|---|---|---|
| (setup) | - | vast env OK (physics-only); render path WORKING on ws (eai-robolab container + overlay, smoke frames in `setup/render_smoke/`) | - | - | - | - | `setup/` |
| knot_untying | very_easy, easier (easy, medium: in progress; see STATUS) | **SOLVED both** in the registered env (evaluation mode): very_easy `or8` latches at step 2527 with tightest gap 18.89 mm; easier `ea7` latches at 2235 with 17.45 mm (threshold 8 mm, unchanged); easy+ not attempted | old planar_clearance + on_table + quiet (FD) + intact, same thresholds | yes, bit-identical on vast (rp8, rpe7) | nop + naive fail (nop8, nv8, nope8, nve8) | **both rendered**: `tasks/knot_untying/video/{very_easy,easier}/` (`top.mp4`, `rope.mp4` close-up) | rope = 99/111-link D6 capsule articulation; two-arm spread before release; deviations D1-D7 in its STATUS.md |
| fiber_bundling | very_easy, easier (easy: in progress, feed fails; see STATUS) | **SOLVED both** (vef step 2921; eaf step 3808; jacket axis within 0.18 mm, min jacket-ring gap 1.30 mm of 1.48 nominal); easy+ not attempted | old terminal_v4, same thresholds | yes, bit-identical x2 on vast; **bit-identical on ws with the vast stack** | nop + no-comb + 12 mm off-axis fail | **both rendered** (state playback, faithful): `tasks/fiber_bundling/video/{very_easy,easier}/` (`top.mp4`, `ring.mp4` = render-only close-up, wrist views) | strand damping 2e-2 (old 2e-5, PhysX pinch drift), trunk lifted from cradle, gentle 3 N grasp; see its STATUS.md |
| buzz_wire_3d | very_easy (easier in progress) | **very_easy SOLVED** with approved task deviations (taller handle 45x9.8x16 mm, start yaw 60 deg, wand friction 1.0): oracle9 succeeds at step 5660, never touches (min gap 8.46 mm), traversal complete, finish 0.17 mm / 0 deg; easier: finish handover blocked by the lateral bend, being re-planned | old terminal_v4 (touch / traversal / finish), same thresholds | yes, bit-identical x2 on vast | nop (time-out, no traversal) + naive straight carry (touches at step 2625) fail | **rendered**: `tasks/buzz_wire_3d/video/very_easy/` (`top.mp4`, `wire_far.mp4` = clear far-side close-up, `wire.mp4`) | figures `start_old_vs_new.png`, `tool_old_vs_new.png`; ring grip for the carry |
| cast_keyhole | very_easy; easier CLOSED (not feasible for the YAM with the original puzzle; user decision) | **very_easy SOLVED** (latch at step 2509 after 15 consecutive steps = 0.5 s, silver 18.6 mm inside the square). **easier: blocked under the current rules** after 16 sim trials + 6 IK searches: the easier channel's silver legs sweep the whole gold edge band; the remaining free regions are too short for the 60 mm blades or need ~20 N grip vs the YAM's 9-14 N. Smallest fixes are all outside the rules (fixed rest under the gold, stronger gripper, weld assist) | old placement predicate (separation, inside region, quiet); penetration audited offline (max 0.12 mm) | yes, bit-identical x2 on vast | nop + naive straight pull (jams) fail | **rendered**: `tasks/cast_keyhole/video/very_easy/` (`top.mp4`, `plates.mp4` close-up); easier parked (PLAN.md) | exact old convex slab colliders; plate friction combine=max (object side); table height 0.7500 |
| rope_threading | easy (medium: not started, table too shallow for the old scene; see STATUS) | **easy SOLVED**: or3, one continuous from-reset run (evaluation mode), success at step 4963 (165 s sim); sequence R1-, R2+; strict diagnostics also true at the latch | released task's terminal (release profile contact_relaxed_v16); strict class defaults logged | yes, bit-identical x2 on vast | nop + 2 naive (no R2 feed / tip beside R1) fail | **rendered**: `tasks/rope_threading/video/easy/` (`top.mp4`, `rings.mp4` close-up) | 110-link D6 capsule rope (E 5 MPa, droop matches Euler-Bernoulli); pinch-drag + deep regrasp over the table edge; deviations D1-D8 |

## Render note (2026-10-12)

- Open-loop replays are bit-identical on the same stack. The eai-robolab stack (Isaac Lab 2.3.2.post1) diverged from vast (fiber ve9 at step 435), so plain ws re-sims are NOT videos of the oracle.
- **Fixed:** vast's exact stack (isaacsim 5.1.0 pip + Isaac Lab f4aa17f + torch 2.7.0 cu128 + pins) built inside the ws container as `/data/.../venv_vast`. The fiber vef replay on ws (Ryzen 7950X) is then **bit-identical to vast (EPYC 9354)**: same 2922-step hash chain 681f013a..., success at 2921. The CPU class does not matter; the stack does.
- **Cameras perturb PhysX:** with `--enable_cameras` even the vast stack diverges at fiber step 435. Re-sims with cameras are never videos of the oracle.
- **Video method = state playback** (`setup/render_states.py`). Pass 1: `dump`, no cameras, vast stack (on ws in `/data/.../venv_vast`, bit-identical to vast), saves `InteractiveScene.get_state()` every step. Pass 2: `render`, cameras, writes each state with `scene.reset_to`, then `sim.forward()` + `sim.render()`; physics is never stepped. Checks: fiber vef dump = vast states at all 2921 pre-terminal steps; render pose readback error 6.6e-7 m.

## Compute

Simulation runs only on vast (`/workspace/yamlab_port/`, nice 19, at most ~8 processes, shared GPU) and, as a fallback, ws/ws2/ws3 (`~/01_projects/04_code_robot_challenge/tmp/<date>_yamlab/`, `/data/qineng/04_code_robot_challenge/<date>_yamlab/`). Quest: CPU nodes for offline geometry; gengpu A100/H100 (no RT cores) physics-only. Rendering: ws/ws3 Isaac 5.1 container (vast RTX segfaults). The laptop runs no simulations.
