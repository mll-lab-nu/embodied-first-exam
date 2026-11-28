# RoboLab

## Overview

[NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 on Isaac Lab 2.3.2 / Isaac Sim 5.1: tabletop tasks with a
language goal for a Franka Panda with a Robotiq 2F-85 gripper (RoboLab's DROID setup, joint-position actions).

| | |
|---|---|
| upstream | [NVlabs/RoboLab](https://github.com/NVlabs/RoboLab) at `9db0aaf09d9fe5d4f37b168320788258c7012463` (tag v0.3.1); Yang et al., RSS 2026 |
| tasks | 53 families × 2 modes = 106 tasks: `tasks/robolab/robolab-<family>-i00-privileged` and `-standard`, both on the same frozen instance |
| metadata | `simulator = "robolab"`, `robot = "franka-robotiq-2f85"`, `family = "<RoboLab task name>"` |
| simulator image | `images/robolab/` (Isaac Lab 2.3.2 / Isaac Sim 5.1, RoboLab and its asset library), built locally: it contains Isaac Sim, which may not be redistributed |
| files image | `ghcr.io/mll-lab-nu/efe:robolab-files-<VERSION>` (`images/robolab-files/`, public): the tooling `rcb_robolab.py` and the standard sidecar's files |
| GPU | an RTX-class NVIDIA GPU (Isaac renders with RTX even headless; PhysX runs on the CPU) |
| reference solutions | `banana_in_bowl` and `rubiks_cube_left_of_bowl` (both modes); the other 51 families have none (RoboLab ships no expert or planner) |

```bash
harbor run -d embodied-first-exam@all -p tasks/robolab -a codex -m <model>
```
The first task builds the simulator image from public sources; later tasks reuse it.

Each task's README is rendered from `tasks/robolab/readme.toml` (benchmark, licence, and each family's success
condition, with the upstream source it was read from), its `instruction.md` and its `task.toml`.

## Upstream and license

- **RoboLab** ([NVlabs/RoboLab](https://github.com/NVlabs/RoboLab), commit `9db0aaf`, v0.3.1): code under the Apache
  License 2.0. Its bundled assets carry their own licences (upstream `THIRD_PARTY_NOTICES.md`): the scenes, fixtures,
  materials and robots, and the `handal`, `hope`, `basic`, `fruits_veggies` and `objaverse` object sets, are
  **CC BY-NC-SA 4.0 (non-commercial, share-alike)**; the `ycb` objects are MIT; the `hot3d` objects CC BY-SA 4.0 with
  the HOT3D licence's non-sale restriction; the `vomp` objects CC BY 4.0; the backgrounds CC0 1.0.
- **Isaac Sim 5.1 / Omniverse Kit and the Isaac Lab 2.3.2 wheels** (from pypi.nvidia.com): NVIDIA proprietary software,
  licensed for use, not for redistribution. Building and running the image accepts the
  [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html)
  and NVIDIA's terms for those wheels (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`). Isaac Lab's source is BSD-3-Clause.
- The image is therefore **BUILD_ONLY** (`images/robolab/BUILD_ONLY`: the licences, the pinned inputs and the check of
  a build). The organization's private copy, `ghcr.io/mll-lab-nu/efe-private:robolab-<images/robolab/VERSION>`, is only
  the tasks' `build.cache_from`.
- Citation: Yang et al., "RoboLab: A High-Fidelity Simulation Benchmark for Analysis of Task Generalist Policies", RSS
  2026 (arXiv:2604.09860).

## Changes from upstream

- **Success terms.** Each family's success predicate is RoboLab's own `success` termination term for that task, with
  three changes in the tooling (`embodied_first_exam/benchmarks/robolab/rcb_robolab.py`):
  - **"The gripper" is both fingers.** RoboLab's DROID robot declares one contact body, `left_inner_finger`
    (`robolab/robots/droid.py`), so an object pinched by the right finger read as released. `GRIPPER_CONTACT` declares
    both inner fingers and makes "gripper" RoboLab's own alias group of the two (any member counts), set before the
    env is registered.
  - **On the table where the words say so.** `take_measuring_spoon_out` and `cooking_clear_plate` use RoboLab's own
    `object_outside_of_and_on_surface` with surface `table` and their own parameters instead of `object_outside_of`,
    which would count an object lifted out of the container or knocked off the table.
  - **A settle hold at the end.** After a trajectory's last row the replay holds that row for 30 control steps (2 s),
    the term still checked at every step; in standard mode the service holds the last command as long when the
    episode ends.
- **Episode length.** RoboLab's per-task `episode_length_s` time-out is stretched past the runaway guard of 100,000
  control steps: the agent's wall clock is the only budget.
- **Standard mode: the success term never ends the episode.** The tooling wraps the term
  (`Session._hide_success_term`): RoboLab still evaluates it after every control step, so stateful terms (the in-order
  families) see every step, but it never terminates the env and is never shown.
- **Assets localized.** 15 USD layers of the asset library reference NVIDIA's public Omniverse content bucket (table,
  bin and robot materials, their textures). The image holds the 419 files (635 MB), each checked against
  `images/robolab/remote_assets.sha256` (`mirror_remote_assets.py`), and points the layers at the copies. Physics is
  unchanged: no family references remote geometry.
- **Removed.** RoboLab's one recorded episode (`examples/recorded_data/RubiksCubeAndBananaTask`, a solution of
  `rubiks_cube_and_banana`) and the repository's `.git` are deleted from the image in the layer that clones it.
- **Added.** Frozen instances: the full scene state after RoboLab's canonical seeded reset (`env.reset()` twice, as
  RoboLab's evaluation loop does), with its state hash, made by `rcb_robolab.py make-instance --task <family> --seed 0`;
  each was checked in a second fresh process (the same hash, no success at the start or during a 1 s hold). The
  privileged tooling, and the standard mode (a sim sidecar); upstream has neither.
- **Isaac versions.** RoboLab v0.3.1 on its `isaac51` extra (Isaac Lab 2.3.2.post1 / Isaac Sim 5.1.0), installed from
  the lockfile `images/robolab/uv.lock`. Physics runs on the CPU (PhysX), pinned in each frozen instance.

## Interface

- **Actions (both modes).** RoboLab's DROID joint-position action, one row per control step at 15 Hz (sim dt 1/120 s,
  decimation 8): 7 absolute Franka joint targets (rad, PD-tracked) and a binary Robotiq command (0 open, 1 closed).
- **Privileged mode.** `/opt/tools/rcb_robolab.py` (`from rcb_robolab import Session`): the frozen scene, object poses
  and bounds, unlimited `s.reset()`, thin primitives (differential-IK moves, joint moves, gripper, hold), rendering,
  recording, and replay as the verifier does it. Task-level skills (grasp, place) are never part of the tooling. The
  deliverable is `/app/output/trajectory.npz` (`task`, `actions` (T, 8), T ≤ 100,000). Every Python process pays about
  2 minutes of Isaac launch and scene build.
- **Standard mode.** The robot is a service in the `sim` sidecar (GPU on the sidecar; wire protocol `eai-standard/3.0`), reached through
  `/opt/tools/rcb_client.py` or the `efe-robot` MCP tools; the agent's container has no simulator and no GPU. Actions:
  `joint_position` (8, rows `dt` apart, a multiple of 1/15 s) and `ee_pose` (8, closed-loop differential IK in the
  fingertip-centre frame, at most 0.25 m/s). Cameras: `egocentric_mirrored_camera` and `over_shoulder_left_camera`
  (static) and `wrist_cam` (on the Robotiq base link); Isaac `distance_to_image_plane` depth on request; `/kinematics`
  from a numpy model of the arm; 32 proprioception columns. One episode, no reset; the agent ends it with `/finish`.
  Not given: object poses, any success signal.
- **World-frame information.** Standard tasks never say where things are in the world
  (`ci_checks/check-world-frame-texts.sh`). The world convention is the robot's root frame: the Franka
  base at the origin, x forward towards the table, y to the robot's left, z up. Privileged tasks give the full state
  through the tooling.
- **Time.** 3600 s for every task of both modes (`[agent] timeout_sec`); every instruction states it.
- **Network.** The agent reaches the model APIs and the package registries only (`network_mode = "allowlist"`, the hosts
  of `scripts/set_agent_egress.py`). Isaac needs no network: everything is in the image, and the EULA is accepted by
  environment variables. Both verifiers run with `network_mode = "no-network"`.

## Grading

- **Success at a control step.** RoboLab evaluates its success term after every control step. In privileged mode the
  first step where it holds ends the replay (RoboLab's termination freezes the env), so a goal state that holds at one
  control step counts. In standard mode the term is judged once, at the last control step of the episode, after the
  settle hold. Most terms require the object to be released (neither inner finger touching it). Each task's README
  states its condition exactly.
- **Privileged: up to 3 fresh-process replays.** `tests/grade.py` replays `/app/output/trajectory.npz` up to 3 times
  (`[metadata] replays`), each in a fresh process, and stops at the first success: PhysX on the CPU reproduces the live
  run bit for bit in a fresh process on one host, but a second replay in one process drifts in the last bits, and the
  final state can differ in the last bits across hosts. The rebuilt frozen scene must match the recorded one (exact
  state hash, or every object pose and joint within tolerance), else the trial is an infrastructure failure. A file
  that is not a readable trajectory is the agent's 0.
- **Standard: the live episode.** Nothing is replayed. At `/finish`, or when the agent's session ends, the service holds
  the last command for 30 control steps on the live simulator and judges the term at the end of that hold; at the
  step cap and on a simulator error the term as it stands. The verifier only reads `final.json`.
- **Infrastructure vs agent failures.** A rebuilt start scene that does not match the frozen instance, a replay process
  without a result or past its time limit (privileged), and a missing or unfinalized `final.json`, a give-up after
  crashes between calls or a failed resume (standard) are `infra_error = 1`, never the agent's 0. A simulator error or
  a crash inside the agent's calls is the agent's 0.
- **Video.** Privileged: the deciding replay, filmed by the tooling. Standard: filmed during the live episode (a frame
  of the viewport and wrist cameras every 3 control steps) and encoded after the verdict. A failed video never changes
  a verdict.

## Tasks

One privileged and one standard task per family; each family is the RoboLab benchmark task of that name.

| kind | families |
|---|---|
| put objects in a container | `apple_and_yogurt_in_bowl`, `banana_in_bowl`, `bananas_in_bin_one_more`, `bananas_in_bin_three_total`, `bbq_sauce_in_bin`, `blocks_in_bin`, `clutter_plastic`, `clutter_pumpkin`, `condiments_in_bin`, `cubes_and_blocks_in_bin`, `food_packing2_cans`, `food_packing3_cans`, `larger_object_raisin_box_in_bin`, `marker_in_mug`, `mustard_in_left_bin`, `mustard_in_right_bin`, `plastic_bottles_in_square_pail`, `put_two_mugs_on_shelf`, `recycle_carton`, `recycle_cartons_vertical_crate`, `red_dishes_in_bin`, `rubiks_cube_and_banana`, `rubiks_cubes_in_bin`, `spoon_in_mug`, `throw_away_snacks`, `utensils_in_mug` |
| in a given order | `banana_then_rubiks_cube`, `rubiks_cube_then_banana` |
| take objects out | `bananas_out_of_bin`, `cooking_clear_plate`, `keyboard_out_of_bin`, `take_measuring_spoon_out`, `take_mugs_off_of_shelf`, `take_spatula_off_shelf`, `tools_picking_drill`, `unstack_rubiks_cube` |
| place on top of something | `butter_above_raisin`, `fruits_green_limes_on_plate`, `fruits_on_plate3`, `mustard_above_raisin` |
| stack | `block_stacking_order_agnostic`, `block_stacking_specified_order`, `stack3_rubiks_cube`, `stack_yellow_on_red` |
| place relative to another object | `rubiks_cube_behind_bowl`, `rubiks_cube_in_front_of_bowl`, `rubiks_cube_left_of_bowl`, `rubiks_cube_right_of_bowl`, `white_mug_in_center_of_table` |
| pick up | `pick_glasses`, `pick_orange_object`, `pick_up_blue_pitcher` |
| reorient | `reorient_red_mug` |

- **Instances.** Each family's frozen instance is in its privileged task (`environment/instance.json`, copied to
  `tests/`) and in its standard task (`environment/sim/instance.json`).
- **Reference solutions.** `banana_in_bowl` and `rubiks_cube_left_of_bowl`: a script on the privileged tooling plus the
  skills in `solution/ref_primitives.py` (never in the agent's image); the standard task streams the privileged
  oracle's recorded joint targets through the client in one-second chunks.
- **Shared code.** One source each in `embodied_first_exam/benchmarks/robolab/` (`rcb_robolab.py`, `ref_primitives.py`,
  `sim/`); every copy is byte-identical across the benchmark (`check-tooling-identity.sh`). After a change to
  `rcb_robolab.py`: bump `images/robolab-files/VERSION`, `python3 scripts/files_image.py build robolab-files`, push it,
  `python3 scripts/files_image.py pin robolab-files <digest>`.

## Others

- **Host.** Linux x86_64, Docker with BuildKit and the NVIDIA Container Toolkit, an RTX-class GPU with a driver Isaac Sim
  5.1 supports (checked on RTX 4090 and RTX PRO 6000). One Isaac simulator at a time per 32 GB of host RAM. The first
  build needs about 60 GB of free disk (the image is about 27 GB) and 20-60 min, with network access to github.com
  (and its LFS), snapshot.ubuntu.com, pypi.org, pypi.nvidia.com, download.pytorch.org and NVIDIA's public Omniverse
  content bucket.
- **Kit cache.** Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own
  cache volumes, never the agent's, each scoped to the trial's compose project.
- **Known looseness of upstream terms.** "Inside" extends without limit along the container's up axis, so a toppled or
  tilted container can count objects as outside or inside; `object_upright` has no support term; the stacking terms do
  not require the gripper to let go; `tools_picking_drill`'s term names the left bin while the drill starts in the right
  bin. Each task's README states its condition as the code checks it.
- **Physics.** Contact can make the physics diverge after an ordinary-looking grasp (rare: about once in 350 trials); in
  standard mode that episode is lost. A privileged `s.reset()` does not restore the start bit for bit, so the verifier
  replays in a fresh process.
- **Crash recovery (standard).** Resume class `exact`: the resumed service, a fresh process, replays the journal, and
  the state hash at the last checkpoint must match exactly, else the episode ends as an infrastructure failure.
