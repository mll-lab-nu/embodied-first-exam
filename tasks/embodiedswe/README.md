# EmbodiedSWE

EmbodiedSWE's robot benchmark (`robobench`, commit `67f44e8a2ca5`) on Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the
GPU: the agent writes a program, `solution/solve.py` exposing `solve(env)`, that completes a manipulation or
loco-manipulation task by stepping the env. `simulator = "embodiedswe"`. 24 tasks (assembly, packing, puzzle, cutting
and loco-manipulation scenes, one frozen instance each): EmbodiedSWE's 28 published tasks without its 4 deformable ones
(they need Newton physics and a networked VLM judge). For now all 24 are in the `all` set and none is in the core set.
Each is in privileged mode (`task_type = "policy"`) and, as `<task>-standard`, in standard mode
(`task_type = "trajectory"`, "Standard mode" below);
all 24 scenes are static, so there is no standard-realtime mode.

| Task | Preset | Robot |
|---|---|---|
| `embodiedswe-assembly-bulb-franka-osc-i00-privileged` | `assembly.bulb.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-puzzle-stack-blocks-g1-pink-ik-i00-privileged` | `puzzle.stack_blocks.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-locomanip-fruit-delivery-g1-loco-pink-ik-i00-privileged` | `locomanip.fruit_delivery.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-assembly-allen-bolt-franka-osc-i00-privileged` | `assembly.allen_bolt.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-ikea-table-bimanual-franka-osc-i00-privileged` | `assembly.ikea_table.bimanual_franka.osc` | two Franka Pandas, operational-space control |
| `embodiedswe-assembly-nut-thread-franka-osc-i00-privileged` | `assembly.nut_thread.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-gpu-franka-osc-i00-privileged` | `assembly.pc_gpu.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-gpu-ram-franka-osc-i00-privileged` | `assembly.pc_gpu_ram.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-motherboard-franka-osc-i00-privileged` | `assembly.pc_motherboard.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-assembly-pc-ram-franka-osc-i00-privileged` | `assembly.pc_ram.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-packing-pen-holder-franka-osc-i00-privileged` | `packing.pen_holder.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-packing-tool-packing-franka-osc-i00-privileged` | `packing.tool_packing.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-packing-egg-carton-g1-pink-ik-i00-privileged` | `packing.egg_carton.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-privileged` | `packing.clear_organic_objects.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-puzzle-coffee-franka-osc-i00-privileged` | `puzzle.coffee.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-puzzle-syringe-bimanual-franka-osc-i00-privileged` | `puzzle.syringe.bimanual_franka.osc` | two Franka Pandas, operational-space control |
| `embodiedswe-puzzle-push-shapes-g1-pink-ik-i00-privileged` | `puzzle.push_shapes.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-puzzle-classify-objects-g1-pink-ik-i00-privileged` | `puzzle.classify_objects.g1.pink_ik` | Unitree G1 (fixed pelvis), Pink IK |
| `embodiedswe-cutting-slice-franka-osc-i00-privileged` | `cutting.slice.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-cutting-dice-franka-osc-i00-privileged` | `cutting.dice.franka.osc` | Franka Panda, operational-space control |
| `embodiedswe-locomanip-box-to-bin-g1-loco-pink-ik-i00-privileged` | `locomanip.box_to_bin.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-locomanip-wheel-carry-g1-loco-pink-ik-i00-privileged` | `locomanip.wheel_carry.g1.loco_pink_ik` | Unitree G1 (walking), Pink IK |
| `embodiedswe-assembly-so101-bimanual-franka-osc-i00-privileged` | `assembly.so101.bimanual_franka.osc` | two Franka Pandas, operational-space control |
| `embodiedswe-puzzle-spatula-franka-osc-i00-privileged` | `puzzle.spatula.franka.osc` | Franka Panda, operational-space control |

## Grading

The verifier grades as EmbodiedSWE's harbor verifier (`eval/harbor_support/verifier.py` at the pinned commit) does,
one seed (the frozen instance, seed 0). The candidates are the checkpoints the agent froze with `submit` and the final
`solution/` (see Checkpoints). Each distinct candidate runs in a fresh process: the trusted simulator builds the env
from the frozen instance (EmbodiedSWE's own build and seeded reset, GPU PhysX), attaches the task's grader
(EmbodiedSWE's, unchanged) and runs the candidate's `solve(env)` in a separate process as an unprivileged user,
without network or GPU, behind a proxy env (`embodied_first_exam/benchmarks/embodiedswe/esw_proxy.py`): reads return
copies, `env.step(action)` steps the simulator, everything else is refused. A candidate's process has EmbodiedSWE's
rollout limit, 1800 s of wall clock from its start (the simulator's start-up and the import of `solve.py` count); then
it gets SIGTERM, the solve is ended and the verdict is read on the state at that moment; 30 s later, SIGKILL. A request
still being served then (a long `env.step`) ends the same way: `solve_status` `timeout`, graded, not an error. A process
that ends without a verdict while solving scores 0; in any other phase it is the verifier's error (`infra_error`).
The verdict is EmbodiedSWE's: success = the grader's end predicate (the cutting and SO101 scenes have no `success()`:
their graders' predicates, enough pieces and all of them on the board, and every screw fastened with the servo and
the forearm seated, are also the tooling's `cut_success` and `so101_success` for the development `check`);
`progress` = its rubric score, the peak recorded progress, so progress made before an exception or the time limit
counts. The spatula scene's tool-only rule (the hand or a finger touching the bread disqualifies the episode) is
enforced by the verifier: PhysX contact reports on the bread, read after every physics substep against the hand and
finger links; a contact with a nonzero force sets success and progress to 0 (`disqualified`, `tool_contact` in
`reward.json`). An exception from `env.step` is raised in `solve`, as EmbodiedSWE's `GradedEnv` lets it propagate.
Actions are applied as given: as in EmbodiedSWE, a Franka's operational-space controller scales the 6 pose deltas by
`pos_scale` / `rot_scale` without clipping them and clamps the joint torques (100 N·m); only an action's shape and
finite values are checked. A run in which no action reached the simulator scores 0.

The result is one candidate, selected as EmbodiedSWE selects: the highest `progress` (their score), ties to higher
success, then to the earliest (`final` is last); a candidate that ran wins a tie against one that never did (an
invalid checkpoint, a missing `solve.py`). `reward.txt` and `reward.json` give that candidate's success and progress
(`selected_submission`, `selected_final`); `results.json` lists every candidate with its status, score and success.
The selected candidate's trajectory, `trajectory.npz` (every action, and Isaac Lab's scene state, each asset's root
pose and velocity and joint positions and velocities, every 0.1 s of simulated time, at most 3,000 states: a longer
run is kept at a coarser spacing), is the run's record; with it come its `rollout.json` and `solve.log`. The video,
`replay.mp4`, is rendered after the verdict in a fresh process: each recorded state is posed on the bodies (no physics
step) and drawn, so the video shows the graded run's own states (`video_source = "recorded_states"`; a scene's
non-physical visuals, such as a liquid level, are not part of the state). Before it, the same process re-executes the
selected trajectory's actions with the camera drawing, as a live recording would, and records whether that reaches
the graded run's final state (`camera_replay_match`, `camera_replay_success` in `video.json`; at most 1800 s). Neither
changes the verdict.

### Checkpoints (a benchmark-specific exception)

As in EmbodiedSWE, the agent may freeze up to 64 checkpoints of its deliverable while it works: `submit "note"`
(`esw_submit.py`, in the image as `/usr/local/bin/submit`) copies `/app/output/solution/` to
`/app/output/submissions/NNNNNN/solution/` with a receipt, `submission.json` (the sha256 of every file and of that
inventory), serialized with flock. The verifier checks every receipt and freezes every candidate before any of them
runs; a checkpoint whose files differ from its receipt, or a directory that is not a checkpoint, scores 0 and is not
run. Byte-identical candidates (the same content hash) are graded once; a later copy takes the earlier one's result.
The other benchmarks of this repository grade one deliverable once; this one keeps EmbodiedSWE's checkpoint
protocol, so its result is comparable with EmbodiedSWE's own. The instruction states the limits.

The verifier's time limit (`task.toml` `[verifier] timeout_sec`) covers the worst case, 64 checkpoints and the final
folder, each distinct and each using its whole limit, then the video:

    (64 + 1) x (1800 + 30) + (900 + 1800 + 600) + 300 = 122,550 s

1800 + 30 is a candidate's limit and grace; 900 + 1800 + 600 the video process's (start-up with cameras, the camera
replay's budget, posing and encoding); 300 the margin. A typical trial grades a few candidates and takes minutes.

Differences from EmbodiedSWE's own grading, on purpose:
- `solve` runs in a sandbox (a separate process as an unprivileged user, no network, no GPU) behind a proxy env, not
  in the simulator's process.
- One frozen instance per task, seed 0 (EmbodiedSWE's harbor protocol averages over its seeds).
- The video poses the selected run's recorded states after the verdict; EmbodiedSWE renders live during the run when
  asked to. Cameras in the scene change GPU PhysX's later bits (measured: in the stack scene a run with cameras ends
  elsewhere, in SO101's it does not; drawing the frames itself changes nothing, "Standard mode"), so the graded run
  has no cameras.
- The spatula scene's tool-only rule is checked. EmbodiedSWE states it in the scene's description and leaves it to
  the harness, whose grading does not check it.
- A malformed submissions directory (an entry that is not a checkpoint, more than 64 checkpoints) leaves those entries
  ungraded with score 0 instead of failing the whole evaluation.

## Standard mode (eai-standard/2.2)

`<task>-standard` is the privileged task's twin: the same frozen instance (`environment/sim/instance.json`, byte for
byte), grader and time limit. The simulator runs in the `sim` sidecar (`embodied_first_exam/benchmarks/embodiedswe/sim/`:
`server.py` on the shared layer, `esw_std.py` for the robots, cameras and kinematics; files image
`embodiedswe-standard-files`), built by the privileged tooling (`rcb_embodiedswe.py`: the same build and start-state check);
the agent's container holds the shared client only. No reset. The episode ends after the first call at whose end the
grader's success predicate holds, when the agent's time is up, on a simulator error, on a tool contact (spatula) or at
400,000 control steps (`step_guard`, a technical cap). Graded by the live episode (`final.json` from the service, no
replay): success is the grader's predicate on the live state, `progress` its rubric's peak; the spatula scene's tool-only
rule is the privileged one and disqualifies the episode. A success that ended the episode stays a success through a
crash and resume (the verdict is checkpointed); a tool contact still wins over it. The 400,000-step cap is 7.4 h of
simulated time for a Franka (15 Hz) and 1.9 h for the G1 (60 Hz), which a G1 episode can reach within the 4 h limit
(26 ms per control step on an L40S); the instructions state it. Simulated time advances only inside calls.

Success texts: each standard instruction (and `/spec`'s `task_text`) states the grader's predicate in one
paragraph ("Success, exactly: ..."), every threshold equal to the grader's effective value for that preset, objects
named by appearance or starting place, upstream identifiers only in brackets (PROTOCOL §5).

World-frame information: the standard texts may give world coordinates of fixed fixtures and goal regions (EmbodiedSWE's
own task texts do, e.g. box_to_bin's bin and wheel_carry's basket zone, and the success texts give the grader's goal
points and zones; the world frame is `/spec`'s `world`, its origin at the robot's start spot on the floor for the
walking G1), never the start pose of a movable object, an object's state or the success predicate's internals beyond
its thresholds. Camera calibration is given, so a calibrated camera also tells where the workspace is.

Differences from the privileged twin: one live episode graded as it ran (no candidates, no checkpoints, no 1800 s
rollout limit: the agent's 4 h are the episode's wall clock); the episode ends at the first call whose end satisfies the
predicate (privileged: the predicate on the rollout's final state); a simulator error ends the episode (reason `error`,
graded as it stands), where a privileged `solve()` sees the exception from `env.step` and may catch it and go on; cameras,
depth and proprioception only; a Franka row is the pose the operational-space controller latches (privileged: its
native 6-D delta), a G1 row is the native action.

Actions: `ee_pose` only, rows streamed at the control rate with the agent's `dt` (a multiple of the control period, at
most 0.5 s; a chunk at most 10 s), linear (quaternions slerped) or hold. A row is EmbodiedSWE's own controller target:
- Franka (`*.franka.osc`, `*.bimanual_franka.osc`; 15 Hz): per arm the world pose of `panda_hand` and the two finger
  targets (9 per arm). Each control step gives the operational-space controller the 6-D action that latches exactly that
  pose as its target (its action smoothing inverted); torque law, gains and the 100 N·m clamp are EmbodiedSWE's.
- G1 (`*.g1.pink_ik`, `*.g1.loco_pink_ik`; 60 Hz): the native action, two wrist poses and 14 hand joint targets, then the
  base command `[vx, vy, wz, hip_height]` when walking (switched at the row).

`joint_position` is not offered: the arms are driven by task-space controllers, and a joint-position mode would be
another controller (`/kinematics` gives FK and IK to plan in joint space). Joint targets are not clipped, as in EmbodiedSWE.

Cameras (640×480 RGB, `distance_to_image_plane` depth) from EmbodiedSWE's own declarations: the scene's `CAMERAS` at
their nominal pose, `overview` (the room's camera) and the Franka's `wrist` (`left_wrist` / `right_wrist` on two arms).
The G1 declares none, so `head` sits where the real G1 carries its D435 (Unitree's `d435_joint` on `torso_link`). They
are created before the env's only `sim.reset()`, and the start state still matches the frozen instance. wheel_carry
declares its views in world heights (their targets on its 0.694 m table tops); robobench's replay adds `surface_z` to
every scene's views, which would put these 0.69 m too high, so they are used as declared. The service renders 12
warm-up frames before the first one (a new view's first frames are noisy without the renderer's history).
`max_frames_per_call` = 240 images (cameras × frames: the first, one every control_hz / video_fps control steps, the
last; per-frame depth counted again; `video="none"` takes the first and the last frame only), checked before a call
runs (a 400): the largest legal response, 240 RGB frames and their mp4s, stays under the shared layer's 256 MiB limit
(measured with the final service: sim memory peak 15.6 GiB on clear_organic_objects, GPU 11.5 GiB on bulb). A call that names no cameras gets one static view (`front`, `wide`, else `overview`) and the
robot's own cameras, at the highest rate up to 5 fps at which a 30 s watch fits (one Franka 4 fps, two Frankas 2, the
G1 3; `/spec`'s `default_cameras` and `budget.default_video_fps`), so every call legal at the defaults is answered in full; an
unknown camera name is a 400. `/kinematics`:
pinocchio on the kinematics URDF robobench ships (the Franka arm; the G1's upper body). Proprio: 42 columns per Franka arm,
172 for the G1 (176 walking).

Video: a live recording (`live.mp4`: every camera tiled, 5 frames per second of simulated time). Crash recovery: every control
step journaled; resume class `approx`. GPU PhysX makes a run reproducible only in the same process history: cameras in
the scene, and the service's start-up reads of the articulation (its spec and calibration), change the later bits
(measured on an L40S). The service repeats itself bit for bit, but an action sequence recorded in another process can
diverge in it (the fruit-delivery reference did); an open-loop sequence must be recorded on the service's own start-up.
The grader's per-step history is kept bounded (the peak-progress record and the latest), so a long episode does not grow
the service's memory with it.

Start-up and resume (docs/protocol/standard_mode.md §13.4-13.5): the Kit cache is a trial-scoped volume, so every trial
starts cold. From the service's start to its scene, calibration and start-state check: 217 to 275 s (L40S, other trials
on the host; a warm cache is no faster), against `RCB_STARTUP_TIMEOUT_S` = 900 s. A resume replays the journal without
rendering, on the agent's wall clock, at about the scene's control-step cost (`env.step` alone: stack 26 ms, fruit
delivery 43 ms, spatula 138 ms, SO101 377-394 ms per step); measured through the service: 3,000 stack_blocks steps in
172 s (57 ms per step, the replayed state exact). The collect hook waits up to 2700 s for the episode's end through a
resume (at these rates about 7,000 SO101 or 47,000 stack steps); past that the trial is the verifier's error
(`infra_error`), never a score.

Positive examples: no reference solution ships. The internal references of two scenes, recorded as `ee_pose` rows on
the service's start-up and streamed through the client, score 1 (Harbor, L40S): stack_blocks and fruit_delivery. The
other 22 have no positive example yet. `nop` scores 0 on all 24.

## Time budget

The limit is EmbodiedSWE's rollout limit, 1800 s per candidate, start-up and import included. Measured on an L40S host
(one env, GPU PhysX, `env.step` only): a fresh process starts and builds a scene in 13 to 27 s once the Kit cache is
warm; the stack scene takes 26 ms per control step, fruit delivery 43 ms, spatula 138 ms, and SO101, the slowest (two
arms, 16 physics substeps at 240 Hz, twelve screws with continuous collision detection), 377 to 394 ms, so 30 minutes
hold about 4,500 SO101 control steps, 5 minutes of simulated time.

## Device

PhysX and the G1's frozen locomotion policy run on the GPU (`device="cuda:0"`), as in EmbodiedSWE, in the verifier and
in the agent's development env alike (`make_env()` builds exactly as grading does). On one GPU model a fresh process
repeats a run bit for bit (measured on L40S: the stack scene's closed-loop rollout twice and its recorded actions
replayed twice, SO101 three times, the same final-state hash). The frozen instance records its start state's hash, its
scene state vector and the GPU model that froze it (NVIDIA L40S). The rollout compares its start state: on that model
the hash must match (a mismatch is the verifier's error, `instance_mismatch`); on another model the difference is
recorded (`instance_ok`, `instance_same_gpu`, `instance_max_abs_diff`, `instance_within_tol` at 1e-4 in
`reward.json`), never an error. A run on another GPU model may differ in its bits; a closed-loop solve that reads the
state is robust to that, an open-loop action sequence may not be.

## Image

`ghcr.io/mll-lab-nu/efe-private:embodiedswe-<VERSION>` (`images/embodiedswe/`, BUILD_ONLY): RoboLab's recipe plus
robobench at the pinned commit, scrubbed of graders, smoke probes and solve-calibrated comments, and its asset bundle
by sha256. Isaac Lab's default ground plane and its 3 textures are mirrored into the image by sha256
(`isaac_assets.json`), and the Isaac Lab kit files point their asset root there, so no scene reads the network. Some
upstream binary USD assets carry "Generated from Composed Stage" doc strings with their authors' build paths; these
hold no task content and are left as shipped.

## Provenance

EmbodiedSWE: github.com/EmbodiedSWE/EmbodiedSWE (Apache-2.0), assets on Hugging Face EmbodiedSWE/robobench-assets.
