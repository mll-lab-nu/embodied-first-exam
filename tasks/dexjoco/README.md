# DexJoCo

## Overview

Dexterous manipulation with a 16-DoF Allegro hand on a Franka Panda arm, or with two of them side by side, from
DexJoCo: its 11 tasks, each on one frozen scene instance taken from a public human demonstration, in two modes. That
makes 22 task directories, `tasks/dexjoco/dexjoco-<family>-i00-privileged` and `-standard`.

- **privileged**: the agent has the full simulator (`rcb_dexjoco.Session`) and hands in one trajectory of action rows,
  which the verifier replays open-loop from the frozen instance.
- **standard**: the robot is a service in a `sim` sidecar that the agent cannot open. The agent gets camera images with
  their calibration, proprioception and forward / inverse kinematics, in one live episode with no reset. The live
  episode is graded.

Both modes use DexJoCo's own success check of the task, with the changes listed below. Physics and rendering run on
the CPU (MuJoCo 3.4.0, OSMesa): no GPU is needed.

Image: `ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2` (`images/dexjoco/`: DexJoCo at `8d23b0f` and its pinned dependency
closure; no demonstrations, no policies). Every image is public, and Harbor pulls it:
```bash
harbor run -d embodied-first-exam@all -p tasks/dexjoco -a codex -m <provider>/<model>
```

## Upstream and license

- Upstream: DexJoCo, [brave-eai/dexjoco](https://github.com/brave-eai/dexjoco) at `8d23b0f`
  (`8d23b0fab23b17a58c4b55f3942e17013aaf8267`), cloned when the image is built. Citation: Wang et al., 2026, "DexJoCo:
  A Benchmark and Toolkit for Task-Oriented Dexterous Manipulation on MuJoCo", arXiv:2605.16257.
- License: MIT (copyright 2026 Dexjoco contributors). Bundled robot models: Franka Emika Panda (Apache License 2.0),
  Wonik Allegro hand (BSD 2-Clause). Upstream's teleoperation stack includes GeoRT under a **non-commercial** license
  (CC BY-NC); the image deletes it (`rm -rf teleoperation`), so no non-commercial component is in any task.
- Demonstrations: the Hugging Face dataset `DexJoCo/DexJoCo-Datasets-Raw` (public). Each instance is the initial state
  of one of them, and each reference solution is that demonstration's actions. Neither the image nor the agent's files
  name the demonstration.

## Changes from upstream

- **Instance as a snapshot.** DexJoCo's reset samples poses from the global RNG, and its state restorers edit the
  MuJoCo model (table height, fixed bodies), so a scene cannot be rebuilt from a seed. `instance.npz` holds the full
  physics state (`mjSTATE_INTEGRATION`), the mocap targets, the controls, every numeric `MjModel` array a task can
  change, and the env's Python-side task state (counters, flags), after DexJoCo's own restorer has applied the
  demonstration's `state[0]`. Its hash is checked whenever a task rebuilds it. Its `meta` never says which
  demonstration the scene came from (`rcb_dexjoco.check_instance_meta`).
- **Episode limits lifted.** DexJoCo's episode caps (1000-1500 control steps), its real-time pacing, its per-step camera
  rendering and the Hanoi env's wall-clock auto-reset after an illegal stack are disabled in `rcb_dexjoco.py`. The
  wall clock is the agent's budget; `MAX_STEPS` (10,000,000 control steps) only stops a runaway episode.
- **water_plant aim.** Upstream's check (nozzle in the zone around the plant while the trigger is held, 30 steps) also
  passes with the bottle lying on the table and spraying away from the plant. The task additionally requires the spray
  direction (the bottle's local +z) within 45° of the line from the nozzle to the plant, counted with the rest for
  30 consecutive steps; upstream's own success alone no longer ends the episode. The demonstration sprays 33° off.
- **Agent-ended standard episodes.** A success never ends a standard episode and is never shown
  (`Session(hide_success=True)`); task failures still end it. How each family is judged at the end is in its README
  (an event during the episode for microwave, photograph and water_plant; the end state, with up to 1.2 s of holding
  the last command for a hold count to complete, for assembly, Hanoi, unlock-iPad, click-mouse, fold-glasses and
  pinch-tongs; the end state alone for hammer_nail and pick_bucket).
- **Threads.** DexJoCo's operational-space controller does its linear algebra in numpy, and OpenBLAS splits a product
  differently on 1, on 2-3 and on 4 or more threads: three different final states, and the references of
  `bimanual_assembly` and `fold_glasses` fail on fewer than 4. Every container that runs the simulator sets
  `OPENBLAS_NUM_THREADS=4`. OpenBLAS never runs more threads than the CPUs in the process's affinity, so the 4 CPUs
  must be visible (a cpuset, `taskset` or a 2-CPU Slurm allocation narrows that; a `cpus:` quota does not).
  `rcb_dexjoco.blas_threads()` asks the loaded OpenBLAS for its count; with fewer than 4 no verdict is produced (below).
- **Image pruning.** The image removes upstream's git history, the OpenPI examples and assets (policy configs and norm
  statistics), the teleoperation stack and the docs' pictures.

## Interface

World frame: z up, metres; the robot stands at low x and reaches towards +x (bimanual: the right arm at y < 0, the left
at y > 0); quaternions are wxyz. Control runs at 50 Hz, 10 physics substeps of 2 ms.

An action row is DexJoCo's own: per arm the tcp target pose (xyz, quaternion wxyz, world frame), which DexJoCo's
operational-space controller tracks, and 16 Allegro joint targets (rad; the simulator clamps them to the actuator
ranges). Single arm 23 values, bimanual 46 (right arm first; the left hand's fingers in DexJoCo's mirrored order: ring,
middle, index, thumb).

**Privileged.** `/opt/tools/rcb_dexjoco.py` (`from rcb_dexjoco import Session`) on the frozen instance: unlimited exact
resets, live object poses (`s.objects()`), DexJoCo's state dict (`s.state()`), thin primitives (tcp-target moves,
hand-joint interpolation, hold, raw rows), rendering, recording, `s.status()` (with DexJoCo's `info`, and `aim_deg` for
water_plant), `s.replay()` (as the grader does) and `s.save_trajectory()`, which refuses more than 50,000 rows
(`MAX_TRAJECTORY_ROWS`, 1000 s of robot time; the longest reference has 1085). Each instruction gives the table height
and the arm bases. Sessions append one line per start / reset / record / replay / exit to
`/app/output/rcb_session_log.jsonl`, which the verifier reports as self-reported cost.

**Standard** (`eai-standard/3.0`). The adapter is `embodied_first_exam/benchmarks/dexjoco/sim/server.py` (each standard
task's `environment/sim/server.py`) on the shared layer `embodied_first_exam/standard/`, resume class `exact`.
- Actions: `ee_pose` (DexJoCo's own row) and `joint_position` (per arm 7 arm and 16 hand joint targets; the arm part
  becomes a tcp target by forward kinematics and the same controller tracks it, so the measured joints may differ in
  the arm's redundant direction). Either way the executed, journaled and recorded row is DexJoCo's own, so the
  recorded `trajectory.npz` replays in the privileged tooling unchanged.
- Observations: every camera of the scene (static `front`, `back`, `left`, `right`, `top0`; the hand cameras on each
  hand's mount) at 640 × 480, with calibration and optional z-depth. A camera on a body that is neither fixed in the
  world nor moved by the robot's own joints gives images and depth only (no mount or extrinsics):
  bimanual_photograph's `cam_pos_z`, on the camera the hands pick up. At most 1000 images per call (`/spec`
  `max_frames_per_call`), checked before anything runs. Proprioception: `joint_pos`, `joint_vel`, `joint_effort` (7 + 16
  per arm), `tcp_pose`, `tcp_target`, `hand_target`; no gripper-opening column.
- Kinematics: stateless FK of the arm links, the hand mount and the tcp; IK of each tcp over its arm's 7 joints.
  `robot_spec` gives joint limits, the hand drives' gains, the tcp (DexJoCo's `attachment_site`, the flange) and the
  arm bases.
- Not given: object poses, the table height, workspace coordinates, the success signal, resets. The goals state their
  thresholds as relative distances.

## Grading

**Privileged.** `tests/grade.py` replays `/app/output/trajectory.npz` once in a fresh process of the verifier's own
container (no network), from `tests/instance.npz`. As in DexJoCo's evaluation, the episode ends at the first success
or task failure; success = the replay ends in success. `deterministic` = 1, `determinism_checked` = 0 and `replays` = 1
(`--repeat N` is kept for a determinism measurement by hand). A missing file (`missing_trajectory`), a file for another
task (`wrong_family`) or a file that is not a readable trajectory within the cap (`bad_trajectory`) is the agent's 0.
`grader_error` = 1 comes with `infra_error` = 1: an exception in the grader, an instance that does not rebuild to its
hash (`instance_mismatch`), or fewer than 4 OpenBLAS threads (`too_few_cpus`, with `visible_cpus` and
`blas_threads`). The verdict is written before `replay.mp4` is rendered, and the video stops 2700 s after the grader
started.

**Standard.** The service judges the live episode with DexJoCo's check (`Session.step`, with this benchmark's changes)
and records the verdict; `tests/grade.py` reads it from `final.json` (`graded_by = "live"`, `replays = 0`). Nothing is
replayed to grade it. The frozen instance is checked when the episode begins: a scene that does not rebuild to the
instance's hash gets no episode (`instance_mismatch`, `infra_error` = 1). A sidecar with fewer than 4 OpenBLAS threads
starts no episode either (`too_few_cpus`, `grader_error` and `infra_error` = 1). A simulator error raised by the
agent's call ends the episode with 0 (`sim_error` = 1). The video is one pass over the recorded trajectory after the
verdict (`environment/sim/video.py`: the default static camera and the right hand camera); it never changes the
verdict.

## Tasks

| family | robot | task |
|---|---|---|
| water_plant | single arm | spray the plant: trigger held with the nozzle near the plant and aimed at it, 30 steps |
| click_mouse | single arm | mouse on the pad, clicked there, then on the pad for 10 steps |
| hammer_nail | single arm | drive the nail at least 4 cm deep with strikes |
| pick_bucket | single arm | boxed food in the bucket and the bucket lifted 15 cm |
| pinch_tongs | single arm | three pinches with the tongs, then held 10 cm up for 30 steps |
| fold_glasses | single arm | both temples folded and the glasses in the case, 50 steps |
| bimanual_hanoi | bimanual | the three-disk tower on post C, 20 steps; an illegal stack fails |
| bimanual_microwave_cook | bimanual | hot dog in, door closed, start button pressed |
| bimanual_unlock_ipad | bimanual | 1-2-3 entered with right-hand fingertips, unlocked 10 steps; a wrong digit fails |
| bimanual_assembly | bimanual | the peg touching the socket's bottom for 30 steps |
| bimanual_photograph | bimanual | camera 0.4 m in front of the logo, axis within 10°, shutter pressed |

Robots: `franka-allegro` (6 families), `franka-allegro-bimanual` (5 families). Each family has one privileged and one
standard task on the same instance (`instance_seed` 0); the other allowed seeds' instances and references are in the
privileged task's `tests/seeds/` (`[metadata.seeds]` in each `task.toml`). Each task's README states its exact success
condition. Every task's agent time is its own `[agent] timeout_sec` (1 h). Agent egress is the model APIs and the
package registries only, in both modes: the demonstrations are public.

## Others

- **Reference solutions** (`solution/`, never in the image): the demonstration's own actions
  (`solution/oracle_trajectory.npz`), rounded to float32 (the standard client's precision) and cut where the replay
  ends in success; `bimanual_hanoi` holds its last row 8 more steps, since the rounded rows end its 20-step count short.
  Standard mode streams the same rows as `ee_pose` chunks, so the recorded trajectory is exactly the privileged
  reference.
- **Resources:** the caps are in each task's README. The 4 CPUs of the agent's container (privileged) and of the sim
  sidecar (standard) must be visible to the process (Threads, above).
