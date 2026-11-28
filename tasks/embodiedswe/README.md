# EmbodiedSWE

## Overview

EmbodiedSWE's robot benchmark (`robobench`) on Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the GPU: long-horizon
assembly, packing, puzzle, cutting and loco-manipulation scenes. In privileged mode the agent writes a program,
`solution/solve.py` exposing `solve(env)`, that completes the task by stepping the env; in standard mode it drives the
robot live through the standard service. `simulator = "embodiedswe"`.

| | |
|---|---|
| upstream | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), `robobench` at `67f44e8a2ca51c3e133867e5e669377778e8f97d` |
| tasks | 24 scenes × 2 modes = 48 tasks: `tasks/embodiedswe/embodiedswe-<suite>-<scene>-<robot>-i00-privileged` (`task_type = "policy"`) and `-standard` (`task_type = "trajectory"`); one frozen instance each (seed 0); all scenes are static, so there is no realtime mode |
| robots | `franka-panda` (one Franka, operational-space control), `franka-panda-bimanual` (two Frankas), `unitree-g1-dex3` (Unitree G1, fixed pelvis or walking, Pink IK) |
| image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-<VERSION>` (`images/embodiedswe/`, BUILD_ONLY: built locally, never published) |
| GPU | an RTX-class NVIDIA GPU (ray-tracing cores), one of the task's `gpu_types` (L40S, L40, L4, RTX 4090, RTX 6000 Ada); PhysX and the G1's locomotion policy run on it |
| agent time | 4 h per task (`[agent] timeout_sec = 14400`) |

The per-task READMEs are rendered from `tasks/embodiedswe/readme.toml`: the benchmark, the licence, and each scene's
success condition with the grader and scene code it was read from.

### Before you run

The base image may not be redistributed (Upstream and license), so every host builds it once before the first run,
from the repository root:

```bash
docker build -t ghcr.io/mll-lab-nu/efe-private:embodiedswe-$(cat images/embodiedswe/VERSION) images/embodiedswe
```

The build accepts NVIDIA's Isaac Sim terms, RoboLab's and EmbodiedSWE's Apache-2.0 licences and the licences of the
assets in EmbodiedSWE's bundle (`images/embodiedswe/BUILD_ONLY` lists them); it needs no account or token, and
RoboLab's recipe inside it needs about 60 GB of free disk and 20-60 min. The tasks name the image in their `FROM`;
`harbor run` does not build it.

## Upstream and license

- **EmbodiedSWE**: [EmbodiedSWE/EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) at commit
  `67f44e8a2ca51c3e133867e5e669377778e8f97d`, Apache License 2.0. Paper: Shen et al., 2026, "EmbodiedSWE: Coding Agents
  for Long Horizon Dexterous Robotics", arXiv:2609.27308.
- **Assets**: EmbodiedSWE's bundle on Hugging Face (`EmbodiedSWE/robobench-assets`, revision
  `62fab5b70ccb0103c60c4ca39236abae2cc8e900`), every file checked by sha256 against `robobench/assets_manifest.json`.
  The bundle mixes licences, some **non-commercial (CC BY-NC)** or store-licensed (Fab / Objaverse models); each
  asset's licence file ships with it.
- **Simulator**: NVIDIA Isaac Sim 5.1 / Omniverse Kit and the Isaac Lab 2.3.2 wheels, licensed by NVIDIA for use, not
  for redistribution, installed by RoboLab's recipe (`images/robolab/`, Apache License 2.0).

## Changes from upstream

- **Tasks.** EmbodiedSWE's 28 published tasks without its 4 deformable ones (they need Newton physics and a networked
  VLM judge): 24 scenes, each at one preset (scene, robot and controller) and one frozen instance, seed 0
  (EmbodiedSWE's own harbor protocol averages over its seeds).
- **Physics, scenes and success checks: none.** The scenes, presets and graders are EmbodiedSWE's at the pinned
  commit. Each task's grader (`tests/grader/<scene>.py`, and `environment/sim/grader/<scene>.py` in standard mode) is
  byte-identical to upstream's `robobench/suites/<suite>/grader/<scene>.py`.
- **Scrubbed image.** `images/embodiedswe/scrub_embodiedswe.py` keeps only `robobench/`, `LICENSE` and
  `pyproject.toml`; removes every suite's `grader/` and `smokes/` and the deformable suite; strips comments and
  non-module docstrings from the suites' binding files (`configs/envs.py`, calibration notes of solved bindings);
  rewrites solve-calibrated comments in the shipped scenes and text assets; and removes the working poses from two
  `describe()` texts (box_to_bin, wheel_carry) and `robobench/scripts/robot_binding_smoke.py`. It asserts that every
  module's code (its AST without docstrings) is unchanged. Isaac Lab's default ground plane and its 3 textures are
  mirrored into the image by sha256 (`isaac_assets.json`), so no scene reads the network. Some upstream binary USD
  assets carry "Generated from Composed Stage" doc strings with their authors' build paths; they hold no task content
  and are left as shipped.
- **Grading, on purpose different from EmbodiedSWE's own:**
  - `solve` runs in a sandbox (a separate process as an unprivileged user, no network, no GPU) behind a proxy env
    (`embodied_first_exam/benchmarks/embodiedswe/esw_proxy.py`), not in the simulator's process.
  - The spatula scene's tool-only rule (the hand or a finger touching the bread disqualifies the episode) is checked.
    EmbodiedSWE states it in the scene's description and leaves it to the harness, whose grading does not check it.
  - The cutting scenes and SO101 have no `success()`; their graders' end predicates are also the tooling's
    `cut_success` and `so101_success` for the development `check`.
  - The video poses the selected run's recorded states after the verdict; EmbodiedSWE renders live during the run when
    asked to. Cameras in the scene change GPU PhysX's later bits, so the graded run has no cameras.
  - A malformed submissions directory (an entry that is not a checkpoint, more than 64 checkpoints) leaves those
    entries ungraded with score 0 instead of failing the whole evaluation.
- **Added.** The standard mode (a sim sidecar, below); the frozen instances (`environment/instance.json`: preset, seed,
  start-state vector and hash, the GPU model that froze it).

## Interface

### Privileged mode

`/opt/efe/rcb_embodiedswe.py` (`make_env()`) builds the env exactly as grading does: EmbodiedSWE's preset, one
environment, seed 0, PhysX on the GPU (`device="cuda:0"`), checked against the frozen instance. In development anything
goes (resets, restored states, cameras). The deliverable is the folder `/app/output/solution/` with `solve.py`.
Actions are EmbodiedSWE's native ones, applied as given: a Franka's operational-space controller scales the 6 pose
deltas by `pos_scale` / `rot_scale` without clipping them and clamps the joint torques (100 N·m); a G1 takes two wrist
poses and 14 hand joint targets, plus the base command when walking. Only an action's shape and finite values are
checked. `python /opt/efe/rcb_embodiedswe.py check --solution /app/output/solution` runs a folder exactly as grading
does.

Checkpoints, as in EmbodiedSWE: `submit "note"` (`esw_submit.py`, in the image as `/usr/local/bin/submit`) copies
`/app/output/solution/` to `/app/output/submissions/NNNNNN/solution/` with a receipt, `submission.json` (the sha256 of
every file and of that inventory), serialized with flock; at most 64.

### Standard mode

The service speaks eai-standard/3.0. The simulator runs in the `sim` sidecar
(`embodied_first_exam/benchmarks/embodiedswe/sim/`: `server.py`, `esw_std.py` for the robots, cameras and kinematics,
files image `embodiedswe-files`; `live_video.py` from `standard-files`), built by the privileged tooling (`rcb_embodiedswe.py`: the
same build and start-state check); the agent's container holds the shared client only. The frozen instance
(`environment/sim/instance.json`) and the grader are the privileged task's, byte for byte.

- **Actions.** `ee_pose` only, rows streamed at the control rate with the agent's `dt` (a multiple of the control
  period, at most 0.5 s; a chunk at most 10 s), linear (quaternions slerped) or hold. A row is EmbodiedSWE's own
  controller target. Franka (15 Hz): per arm the world pose of `panda_hand` and the two finger targets (9 per arm);
  each control step gives the operational-space controller the 6-D action that latches exactly that pose (its action
  smoothing inverted). G1 (60 Hz; 50 Hz for box_to_bin and wheel_carry): the native action, two wrist poses and 14
  hand joint targets, then the base command `[vx, vy, wz, hip_height]` when walking. `joint_position` is not offered:
  the arms are driven by task-space controllers (`/kinematics` gives FK and IK, pinocchio on robobench's kinematics
  URDF). Joint targets are not clipped, as in EmbodiedSWE.
- **Cameras.** 640×480 RGB and `distance_to_image_plane` depth, from EmbodiedSWE's own declarations: the scene's
  cameras at their nominal pose, `overview` and the Franka's `wrist` (`left_wrist` / `right_wrist` on two arms). The G1
  declares none, so `head` sits where the real G1 carries its D435 (`d435_joint` on `torso_link`). They are created
  before the env's only `sim.reset()`, and the start state still matches the frozen instance. wheel_carry's views are
  used as declared (robobench's replay would add `surface_z` and put them 0.69 m too high). The service renders 12
  warm-up frames first. `max_frames_per_call` = 240 images (cameras × frames, per-frame depth counted again), checked
  before a call runs (a 400). A call that names no cameras gets one static view and the robot's own cameras at the
  `/spec` defaults. Proprioception: 42 columns per Franka arm, 172 for the G1 (176 walking).
- **World-frame information.** The standard texts may give world coordinates of fixed fixtures and goal regions
  (EmbodiedSWE's own task texts do); the world frame is `/spec`'s `world`, its origin at the robot's start spot on the
  floor for the walking G1. They never give the start pose of a movable object, an object's state, or the success
  predicate's internals beyond its thresholds. Camera calibration is given.
- **Start-up.** The Kit cache is a trial-scoped volume, so every trial starts cold: 217 to 275 s from the service's
  start to its scene, calibration and start-state check (L40S), against `RCB_STARTUP_TIMEOUT_S` = 900 s.
- **Crash recovery.** Every control step is journaled; resume class `approx` (GPU PhysX repeats a run bit for bit only
  in the same process history). A resume replays the journal without rendering, on the agent's wall clock. The collect
  hook waits up to 2700 s for the episode's end through a resume; past that the trial is an infrastructure failure,
  never a score. A success the verdict recorded stays a success through a resume; a tool contact still wins over it.
- **Video.** A live recording, `live.mp4` (every camera tiled, 5 frames per second of simulated time).

### Device and determinism

PhysX runs on the GPU in the verifier and in the agent's development env alike. On one GPU model a fresh process
repeats a run bit for bit (measured on L40S). Cameras in the scene and the standard service's start-up reads of the
articulation change the later bits, so an open-loop action sequence recorded in another process can diverge. The
frozen instance records its start state's hash and the GPU model that froze it (NVIDIA L40S): on that model a hash
mismatch is an infrastructure failure (`instance_mismatch`); on another model the difference is recorded
(`instance_ok`, `instance_same_gpu`, `instance_max_abs_diff`, `instance_within_tol` at 1e-4), never an error.

## Grading

Success is the task's grader's end predicate (its `check_success()`, the scene's own predicates with the preset's
thresholds); each task README states it exactly. `progress` is the grader's rubric score, the peak recorded during the
run; it ranks the privileged candidates and is reported, but only success counts as solved.

- **Privileged: candidates.** `tests/grade.py` grades as EmbodiedSWE's harbor verifier
  (`eval/harbor_support/verifier.py` at the pinned commit) does. The candidates are the checkpoints and the final
  `solution/`. The verifier checks every receipt and freezes every candidate before any of them runs; a checkpoint
  whose files differ from its receipt, or a candidate without `solve.py`, scores 0 and is not run. Byte-identical
  candidates are graded once.
- **Privileged: one run per candidate.** Each candidate runs in a fresh process: the trusted simulator builds the env
  from the frozen instance, attaches the task's grader and runs the candidate's `solve(env)` in a separate process as
  an unprivileged user, without network or GPU, behind the proxy env: reads return copies, `env.step(action)` steps
  the simulator, everything else is refused. The process has EmbodiedSWE's rollout limit, 1800 s of wall clock from
  its start (start-up and import count); then SIGTERM, the verdict is read on the state at that moment, and 30 s later
  SIGKILL. An exception from `env.step` is raised in `solve`, as EmbodiedSWE's `GradedEnv` lets it propagate. A
  process that ends without a verdict while solving scores 0; in any other phase it is the verifier's error
  (`infra_error`).
- **Privileged: selection.** As EmbodiedSWE selects: the highest progress, ties to higher success, then to the earliest
  (`final` is last); a candidate that ran wins a tie against one that never did. `reward.txt` and `reward.json` give
  that candidate's success and progress (`selected_submission`, `selected_final`); `results.json` lists every
  candidate. The selected candidate's `trajectory.npz` (every action, and the scene state every 0.1 s of simulated
  time, at most 3,000 states) is the run's record. The video, `replay.mp4`, is rendered after the verdict by posing the
  recorded states (`video_source = "recorded_states"`); before it, the same process re-executes the actions with the
  camera drawing and records whether that reaches the graded final state (`camera_replay_match`, `video.json`).
  Neither changes the verdict.
- **Privileged: verifier time.** `[verifier] timeout_sec` covers the worst case, 64 checkpoints and the final folder,
  each distinct and using its whole limit, then the video: (64 + 1) × (1800 + 30) + (900 + 1800 + 600) + 300 =
  122,550 s. A typical trial grades a few candidates and takes minutes.
- **Standard: the live episode.** No candidates, no checkpoints, no 1800 s rollout limit: the agent's 4 h are the
  episode's wall clock. No reset. The episode ends at `POST /finish`, when the agent's time is up, on a simulator error
  (a 0), on a tool contact (spatula; a 0) or at 400,000 control steps (`step_limit`, a technical cap: 7.4 h of
  simulated time for a Franka, 1.9 h for the G1 at 60 Hz). The verdict is the grader's on the live state when it ends
  (`final.json` from the service, no replay); what the grader latches as it happens counts as it happened. The grader's
  per-step history is kept bounded (the peak-progress record and the latest), so a long episode does not grow the
  service's memory.
- **Tool-only rule (spatula).** PhysX contact reports on the bread, read after every physics substep against the hand
  and finger links; a contact with a nonzero force sets success and progress to 0 (`disqualified`, `tool_contact` in
  `reward.json`) and, in standard mode, ends the episode.

## Tasks

24 scenes, each in privileged and standard mode. The `-standard` task of a scene has the same frozen instance, grader
and time limit as its `-privileged` task.

| Task (privileged) | Preset | Robot |
|---|---|---|
| `embodiedswe-assembly-allen-bolt-franka-osc-i00-privileged` | `assembly.allen_bolt.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-bulb-franka-osc-i00-privileged` | `assembly.bulb.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-ikea-table-bimanual-franka-osc-i00-privileged` | `assembly.ikea_table.bimanual_franka.osc` | two Franka Pandas, operational-space control |
| `embodiedswe-assembly-nut-thread-franka-osc-i00-privileged` | `assembly.nut_thread.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-gpu-franka-osc-i00-privileged` | `assembly.pc_gpu.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-gpu-ram-franka-osc-i00-privileged` | `assembly.pc_gpu_ram.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-motherboard-franka-osc-i00-privileged` | `assembly.pc_motherboard.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-ram-franka-osc-i00-privileged` | `assembly.pc_ram.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-so101-bimanual-franka-osc-i00-privileged` | `assembly.so101.bimanual_franka.osc` | two Franka Pandas, operational-space control |
| `embodiedswe-cutting-dice-franka-osc-i00-privileged` | `cutting.dice.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-cutting-slice-franka-osc-i00-privileged` | `cutting.slice.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-locomanip-box-to-bin-g1-loco-pink-ik-i00-privileged` | `locomanip.box_to_bin.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-locomanip-fruit-delivery-g1-loco-pink-ik-i00-privileged` | `locomanip.fruit_delivery.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-locomanip-wheel-carry-g1-loco-pink-ik-i00-privileged` | `locomanip.wheel_carry.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-privileged` | `packing.clear_organic_objects.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-packing-egg-carton-g1-pink-ik-i00-privileged` | `packing.egg_carton.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-packing-pen-holder-franka-osc-i00-privileged` | `packing.pen_holder.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-packing-tool-packing-franka-osc-i00-privileged` | `packing.tool_packing.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-puzzle-classify-objects-g1-pink-ik-i00-privileged` | `puzzle.classify_objects.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-puzzle-coffee-franka-osc-i00-privileged` | `puzzle.coffee.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-puzzle-push-shapes-g1-pink-ik-i00-privileged` | `puzzle.push_shapes.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-puzzle-spatula-franka-osc-i00-privileged` | `puzzle.spatula.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-puzzle-stack-blocks-g1-pink-ik-i00-privileged` | `puzzle.stack_blocks.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-puzzle-syringe-bimanual-franka-osc-i00-privileged` | `puzzle.syringe.bimanual_franka.osc` | two Franka Pandas, operational-space control |

No reference solution ships (`oracle = "none"`).
