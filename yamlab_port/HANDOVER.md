# YAMLab port of the old RoboTangle tasks: handover

For: **pingyue**. From: the YAMLab port team (agents coordinated for Qineng), 2026-10-12. Questions: **Qineng**.

This branch (`dev/yamlab_port`) is a self-contained project, separate from `robot_coding_bench` main. It holds the task code, oracles, scripts, notes, evidence and small videos of porting five old RoboTangle task families into [YAMLab](https://github.com/ARISE-Initiative/yamlab).

## 1. Goal and rules

**Goal:** port the old, pre-MuJoCo **RoboTangle** tasks (Genesis-based release `robotangle-r2`) into YAMLab.

**Rules (set by the user):**
- **The robot and its settings stay exactly as YAMLab defines them.** That covers the YAM arms, the gripper, gains, base poses, cameras, the 14-D joint-position action and 30 Hz control (`configs/robot/yam.yaml`, `yamlab/robot/**`).
- **Only the tasks change:** objects, fixtures, layout, task config and the goal check.
- Every ported tier must have a working, scripted **oracle**.
- **Easier tiers first;** go up a tier only when the lower one works.
- Keep each task's topology and difficulty. Fixtures may be re-laid for the YAM workspace: the two arms stand side by side facing +X, unlike the old ALOHA (facing arms) or single-Panda setups. Each re-layout is recorded.

**Families and priorities:**
- Priority 1: knot_untying, fiber_bundling, buzz_wire_3d.
- Then: cast_keyhole (a rigid backup) and rope_threading.

Old tiers, easiest first: very_easy, easier, easy, medium, hard.

## 2. Status at handover

"Done" means it meets the definition of done in section 5.

| family | tier | status | evidence / video |
|---|---|---|---|
| fiber_bundling | very_easy | **done** | `tasks/fiber_bundling/out/vef*`, `video/very_easy/{top,ring}.mp4` |
| fiber_bundling | easier | **done** | `out/eaf*`, `video/easier/{top,ring}.mp4` |
| fiber_bundling | easy | in progress (assets + task ready; feed fails) | `out/es1`, `out/es2` (metrics/plots) |
| knot_untying | very_easy | **done** | `tasks/knot_untying/runs/very_easy_or8`, `video/very_easy/{top,rope}.mp4` |
| knot_untying | easier | **done** | `runs/easier_ea7`, `video/easier/{top,rope}.mp4` |
| knot_untying | easy | in progress (start settles correctly; oracle ran out of iterations) | `runs/easy_ey1_failed` |
| knot_untying | medium | in progress (the overhand start is representable; the carry rule fails on a true knot) | `runs/medium_md1_failed` |
| cast_keyhole | very_easy | **done** | `tasks/cast_keyhole/runs_meta/oracle_ve*`, `video/very_easy/{top,plates}.mp4` |
| cast_keyhole | easier | **closed: not feasible for the YAM with the original puzzle** (user decision) | `STATUS.md` "easier work log", `runs_meta/ea_t*.png` |
| buzz_wire_3d | very_easy | **done** (with approved task deviations) | `tasks/buzz_wire_3d/results/oracle9`, `video/very_easy/{top,wire_far}.mp4` |
| buzz_wire_3d | easier | in progress (only the finish placement is blocked) | `results/easier_oracle{1,2,3}` |
| rope_threading | easy | **done** | `tasks/rope_threading/evidence/or3`, `video/easy/{top,rings}.mp4` |
| rope_threading | medium | not started (layout problem found; reach study partial) | `STATUS.md` "Medium" |
| all | hard | not started | |

Each family folder `tasks/<family>/` has:
- `STATUS.md`: the exact final state, numbers, re-layout, deviations, run directories, and what was tried;
- `README.md`: how to build and run;
- code: the YAMLab task files, an asset builder, the oracle, a replay script, and checks.

## 3. Setup on your own machine

**What we used:**
- Isaac Sim **5.1.0** (pip);
- Isaac Lab at commit **f4aa17f87e2e5db5484f0b5974918573e8918ce2** (2.3.2; YAMLab's pinned commit);
- torch 2.7.0 + cu128, Python 3.11;
- YAMLab = upstream **ARISE-Initiative/yamlab @ ec0455d2b4ce35f21fc126418ea5e74ac567133d**, unmodified. We never patched YAMLab: every task adds its own files plus two registration lines;
- LeRobot `lerobotv2.0` branch (RogerDAI1217/lerobot), an import-time dependency of `yamlab/utils/recorders.py`.

**Install** (mirrors YAMLab's own `install.sh` Option B; our scripted version is `setup/vast_install.sh`):

```bash
# Python 3.11 env (conda or uv)
pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com
git clone https://github.com/isaac-sim/IsaacLab.git && cd IsaacLab && git checkout f4aa17f87e2e5db5484f0b5974918573e8918ce2
./isaaclab.sh --install none && cd ..
git clone https://github.com/ARISE-Initiative/yamlab.git && cd yamlab && git checkout ec0455d2b4ce35f21fc126418ea5e74ac567133d && cd ..
git clone -b lerobotv2.0 https://github.com/RogerDAI1217/lerobot.git && pip install -e lerobot
pip install "pyarrow==18.1.0" "datasets==3.6.0"   # Isaac needs numpy 1.26; newer pyarrow/datasets require numpy 2
pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128   # re-pin if something moved it
export OMNI_KIT_ACCEPT_EULA=YES
```

**How we ran tasks:**
- We did **not** pip-install yamlab. Each family runs on its **own copy** of the pristine clone, with its task installed into it by the family's `install.sh` / `install_task.sh` / `apply_overlay.sh` (or `cp` lines in its README), and `PYTHONPATH=<that copy>`.
- Several families' helper scripts that mirrored code to our borrowed box `vast` and ran commands there over ssh (`sync.sh`, `vs.sh`, `vssh.sh`, `vast_run.sh`, `sync_to_vast.sh`) are removed from this copy because they only work with our host and key; READMEs and STATUS files still mention them and `/workspace/yamlab_port/...` paths. **You won't have vast.** Read those paths as "the machine with Isaac": set up a local copy and run the same Python entry points (`vrun.sh` / `run.sh` / `vast_launch.sh` show the exact commands).

**Hosts we used (for context only):**
- **vast:** a borrowed RTX PRO 6000 box, no docker. It ran physics fine, but Isaac's RTX renderer segfaulted there (`rtx.scenedb`), so it did physics only.
- **ws (RTX 4090):** rendered the videos inside the `eai-robolab:0.1.2` container, using a venv that reproduces vast's exact stack (`setup/ws_vaststack.sh`).
- **Your ws3 setup should work directly.**

**Physics settings:** all oracle runs use **CPU PhysX, 1 env**: `device="cpu"`, `num_envs=1`, `mode="evaluation"`. Pass `--device cpu` explicitly, because `AppLauncher` otherwise defaults to `cuda:0`, which is slower here and not bit-identical with the reference runs.

## 4. Per-family details

The old task sources:
- **The STL package** (geometry in mm, layouts, start states, rope/cable/wire specs) for our five families is bundled in **`robotangle_v1_stl/`**. It is a subset of the lab workspace's `tmp/2026-10-11_robotangle_v1_stl/`; see its README for frames and units. Asset builders read from it.
- **The old task code** (success predicates, generators, old oracles) is in `robot_coding_bench` at commit **2dafa5f2b** (dev/jianwen, `topogym/tasks/<family>/common.py`, `topogym/assets/geometry/`, `topogym/planning/<family>/`). The last pre-MuJoCo main is **4ff51fa5b**. Get them with `git worktree add --detach <dir> 2dafa5f2b` in a `robot_coding_bench` clone (we kept ours under `ref/`, not in this branch).

All goal checks port the old predicates with the old thresholds unless a deviation is listed in the family's `STATUS.md`. All re-layout transforms are in `PLAN.md` ("Re-layout log").

### 4.1 fiber_bundling: cable through a copper ring (`tasks/fiber_bundling/`)

**Model:**
- The cable is one fixed-base articulation: capsule lead, trunk and 2-4 strands with ball joints, gravity off (the old model had gravity compensation 1.0).
- The ring is 64 capsules; the clearance is 1.48 mm radial, and it works in PhysX: the jacket passes within 0.18 mm of the axis.

**Re-layout:** `Rz(+90)`. The cable runs along +y; the ring is in front of the left arm.

**Oracle** (`tools/oracle.py`): lift the trunk out of the U cradle, regrasp 70 mm behind the face, comb the strands into the bundle with presses, then feed along the ring axis with integral correction.

**Done tiers:**
- very_easy: oracle success at step 2921.
- easier: oracle success at step 3808.
- Both: two bit-identical replays; nop, no-comb and 12 mm-offset negatives fail.

Run with `checks.sh <prefix> <gym id>` (see the README).

**Deviations:**
- Strand joint damping 2e-2 (old 2e-5): PhysX pinch drift.
- The trunk is lifted out of the cradle first.
- A gentle ~3 N grasp.
- Friction 0.5.

**Note:** after vef/eaf the feed step was changed for easy. easier still succeeds with the new code (`ea5`); very_easy was not re-run with it. The saved `vef`/`eaf` actions replay unchanged.

**easy (4 strands), in progress:**
- Combing works.
- The feed fails (`es1`, `es2`): two strands spread to 19-31 mm, catch on the ring, and fold onto the fingers.
- **Next idea:** re-centre with feedback and feed straight from the last press. Alternatively, press all strands into one sector, or raise the strand damping to ~5e-2 (a deviation to document).

### 4.2 knot_untying: untangle a rope on the table (`tasks/knot_untying/`)

**Rope model** (reused by rope_threading): one reduced-coordinate articulation of capsules (r 4 mm, ~10 mm links, 99-111 links) with **D6 joints**. Translations are locked; the drives are on rotX/Y/Z, with stiffness from E and nu.
- **Not `UsdPhysics.SphericalJoint`:** its drives are silently inactive in an articulation.
- **Armature ≥ 1e-6 is required,** or the chain goes NaN.
- **The start pose must be written as joint coordinates;** PhysX ignores authored link poses.
- An extra reset event zeroes the joint targets.

**Re-layout:** yaw -90°, with the old bounding-box centre at (0.56, 0).

**Oracle** (`scripts/oracle.py`):
1. Privileged crossing analysis.
2. Carry the free end that is "over" at its first crossing across the under strand; replan per crossing.
3. Spread with two arms before the final release, so the goal latches with margin.

**Done tiers:**
- very_easy `or8`: latches at step 2527 with an 18.89 mm tightest gap (threshold 8 mm).
- easier `ea7`: latches at 2235 with 17.45 mm.
- Replays are bit-identical; nop and naive fail.

**Deviations:**
- Capsule chain instead of FEM/IPC.
- Table height 0.7500.
- The quiet check uses finite differences.
- The settled start has an 8 mm crossing gap.
- The squeeze is self-limited, because the finger contact filter can only watch one body.
- The HDF5 recorder is off.

**easy, in progress:** the start settles with order O O U U. `ey1` reduced the crossings but ran out of `--max_iters 4`. Next: rerun with `--max_iters 8 --max_steps 6000`.

**medium (overhand), in progress:**
- The start survives the settle (U O U O U O).
- The single-carry rule fails on a true knot (`md1`: 3 → 9 crossings).
- **Next idea:** pull the end tail back out along its own path while the other arm pins the loop, then use the existing carry and spread steps.

### 4.3 cast_keyhole: two interlocked keyhole plates (`tasks/cast_keyhole/`)

**Model:** the plates use the old generator's exact convex slab prisms, so no convex decomposition is needed; the slot clearances are exact.

**Re-layout:** a translation only.

**Oracle** (`scripts/oracle.py --params params/very_easy.json`):
1. Settle.
2. Bimanual face clamps.
3. Stand the silver on its edge.
4. The old +90° key turn and channel route.
5. Place the silver in the goal square.

**very_easy, done:**
- Success latches at step 2509 after 15 consecutive steps (= 0.5 s).
- Replays are bit-identical.
- nop fails; the naive straight pull jams.
- Penetration ≤ 0.12 mm, checked offline.

**easier, closed** (user decision: ship very_easy only, no rest fixture):
- The easier channel sweeps the silver legs over the whole gold edge band that very_easy grips.
- The remaining free gold regions are too short for the YAM's 60 mm finger blades, unreachable, or need ~20 N of grip; the YAM gripper gives 9-14 N.
- 16 Isaac trials and 6 IK searches failed. Full evidence: `STATUS.md`, and `PLAN.md` "Closed: cast_keyhole easier".

**What could reopen easier without changing the puzzle** (untested ideas):
- A regrasp sequence that lets the gold rest on the silver bar in an intermediate pose.
- A two-stage disassembly that uses the table edge as a support. The table edge is part of the workstation, not a new fixture.

### 4.4 buzz_wire_3d: guide a loop along a bent wire without touching it (`tasks/buzz_wire_3d/`)

**Model:**
- The wire is a static capsule chain, exact radius.
- The wand is one rigid body: a ring of 64 capsules, a stem, and a box grip.
- Touches are checked every physics substep by a contact sensor plus a geometric gap check.

**Approved task deviations** (the user's rule "only the task changes"; the wand is part of the task):
- **Taller and longer wooden handle: 45 × 9.8 × 16 mm** (old 30.5 × 9.8 × 7). The YAM finger hulls touch only on the last 14 mm of the tips, so the old 7 mm handle on the deck cannot be lifted. Figure: `tool_old_vs_new.png`.
- **Start yaw 11.3° → 60° about the start post.** Figure: `start_old_vs_new.png`.
- **Wand metal friction 1.0 and wand solver velocity iterations 4** (accepted by the user).
- The ring grip is used for the carry.
- At the finish the wand is released from 32 mm.

The wire, loop, clearances, traversal predicate and finish goal are unchanged.

**Re-layout:** a translation only. The span runs along +x; the start post is at x 0.395 and the finish post at x 0.745.

**Oracle** (`tools/oracle_r.py`): left tip pinch at the start, handover to a right ring grip, carry along the rail, handover to a left pen grip at the finish post, release.

**very_easy, done:**
- oracle9 succeeds at step 5660 with no touch; the minimum gap is 8.46 mm.
- Two replays are bit-identical.
- nop times out; the naive straight carry touches the wire at step 2625.

**easier, in progress:**
- Pick, handover and carry all work in Isaac (gap ≥ 8.1 mm).
- Only the finish fails: the lateral bend and the dip collide with the left forearm and the wrist camera. Variants tried: pen-grip variants, scene shifts, a ring-tube clamp, a mirrored sequence, a relay side-pinch (tips over at the post), and a tuned grip (rejected at the handover; fingers 1.6 mm into the deck).
- **Next idea:** keep the tuned left pen grip (tips at 62 mm, roll 10°, tilt -8°). Add a small search over handover height (0.09-0.12 m), roll and tilt at the measured pose, or lower the wand with the ring grip to ~60 mm before the handover.

### 4.5 rope_threading: thread a rope through rings in order and direction (`tasks/rope_threading/`)

**Model:** the knot_untying rope model, stiffer (E 5 MPa; the droop matches Euler-Bernoulli), 110 links. The ALOHA risers are dropped.

**Re-layout:** `Rz(+90)`, with the rings toward the arms.

**Goal:** the **released task's terminal**, release profile `contact_relaxed_v16`: 1 cm/s quiet, a 1 mm contact allowance, round-ring slices. The class defaults (strict) are logged as diagnostics.

**Oracle** (`tools/oracle.py`):
1. Pinch-drag the end over the table edge, then take a deep grasp of the overhang.
2. A 180° wrist roll.
3. Feed R1.
4. The right arm receives and pulls the rope through.
5. Regrip.
6. Feed R2.

**easy, done:**
- `or3`, one continuous run from reset, succeeds at step 4963 (sequence R1-, R2+).
- Replays are bit-identical.
- nop and two naive variants fail.
- **Flag (accepted):** the goal latches while the right arm still holds the rope. That is allowed by the released predicate, and the strict diagnostics are also true at the latch. A full release finish also passes the released predicate but not the strict one, because the rope rests on R1's rim.

**medium, not started.** The old 3-ring scene does not fit the real tabletop (x 0.3025-0.8975) in any rotation: it needs 0.623 m of depth and the table has 0.595 m.
- **Proposed fix:** place the ring assembly rigidly and give the rope start its own rigid placement (a deviation; supported by `rope_yaw_deg` / `rope_t_xy` in `RELAYOUT`).
- A partial numpy reach study (32 of 494 layouts) has found no layout where all six strokes are reachable. The R3 feed (tilted 18° up) is the problem.
- **Next:** finish the reach search, build the medium assets, add a third feed stage, then the deliverables.

## 5. Definition of done for a tier

1. The YAMLab task is registered, with assets built from `robotangle_v1_stl/`, the re-layout recorded, and the goal check equal to the old predicate (deviations documented).
2. The scripted oracle succeeds as **one continuous run from `env.reset()` in `mode="evaluation"`** (CPU, 1 env, terminations on). It saves its 14-D action sequence (`actions.npy`).
3. **Two open-loop replays** of those actions reach success at the same step, **bit-identical** to the oracle: the same state hash.
4. **nop** (hold the start) and a **naive** variant fail for the intended reason.
5. **Video** by state playback (section 6), plus notes in `STATUS.md` (numbers, deviations, run directories).

## 6. Gotchas we paid for

- **`mode="replay"` (and teleop) drops the `task_success` and `time_out` terminations.** Always validate in `mode="evaluation"`. An oracle that runs in replay mode can keep going past the success latch and report a state the real env never evaluates.
- **The env auto-resets inside the terminating step.** The scene after that step is the reset state, so record the latch values before it.
- **Cameras perturb PhysX.** With `--enable_cameras`, even the identical stack diverges at the first rich contact (fiber diverged at step 435). Never use a camera re-simulation as "the oracle video". **Videos come from state playback** (`setup/render_states.py`):
  - `dump`: no cameras, saves `InteractiveScene.get_state()` every step;
  - `render`: cameras on, writes each state with `scene.reset_to` + `sim.forward()` + `sim.render()`, never stepping physics;
  - render-only close-up cameras via `--closeup NAME=eye:target:fov`.
- **Determinism:**
  - Replays are bit-identical on the same software stack; vast EPYC vs ws Ryzen gave identical results with the same stack.
  - Different stacks diverge: Isaac Lab 2.3.2.post1 pip in `eai-robolab` vs f4aa17f source.
  - CPU PhysX is the deterministic path.
- **The YAM gripper is weak and fork-shaped.**
  - It squeezes ~9-14 N.
  - The finger collision hulls form a V-fork with inner contact only near the tips (~14 mm, ±9 mm).
  - Flat thin objects on the table are hard to pinch.
  - YAMLab's grasp clamp and `is_grasping()` only see one filtered body, so they are useless for multi-link ropes and cables; limit the squeeze in the oracle instead.
- **The real table collider** top is z **0.7500**, extent x 0.3025-0.8975, y ±0.65. `yam.yaml`'s 0.7517 and ±0.55 are nominal.
- **Reach:** top-down grasps reach only ~0.40-0.50 m out and low. Forward-pointing grasps reach ~0.65 m at 25 cm height. A vertical tool cannot get above z ≈ 0.955.
- **PhysX velocities on resting chains and interlocked bodies jitter** (5-15 mm/s). Use finite-difference speeds for "quiet" checks.
- **YAMLab's HDF5 recorder** writes `/tmp/isaaclab/logs/dataset.hdf5` for every process, and concurrent runs clash on its lock. Point it at a per-process dir or disable it.
- **Physics on vast's GPU pipeline** (`cuda:0`) is ~40× slower for these single-env tasks and not bit-identical with CPU.

## 7. Map of this branch

| path | what |
|---|---|
| `HANDOVER.md` | this file |
| `README.md` | status table (most detailed) and render notes |
| `PLAN.md` | plan, re-layout log, closed/parked decisions with evidence |
| `YAMLAB_NOTES.md` | study of YAMLab: robot, task anatomy, deformables, hosts, measured facts |
| `INDEX.md` | file index |
| `tasks/COMMON_BRIEF.md` | the rules every task agent followed |
| `tasks/<family>/` | per-family code, `STATUS.md`, `README.md`, evidence, videos |
| `setup/` | install scripts (`vast_install.sh`, `vast_syslibs.sh`), smoke tests, the ws render path (`ws_*.sh`, `ws_vaststack.sh`), `render_states.py` |
| `robotangle_v1_stl/` | old geometry package, subset for our five families |

**Not in this branch:**
- The YAMLab clone (pinned above, unmodified).
- `ref/` (worktrees of the old sources; see section 4).
- Per-step state dumps (`*.npz`), logs and checkpoints. Exceptions: small `.npz` inputs the code needs (start states, kinematics tables, gripper hulls) are included.
- Wrist-camera videos.

The full run directories remain on vast (`/workspace/yamlab_port/runs/<family>/`) and the render outputs on ws (`/data/qineng/04_code_robot_challenge/2026-10-12_yamlab/out/`) while those hosts last. Ask Qineng if you need something from them.
