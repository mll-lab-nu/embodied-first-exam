# LabUtopia

## Overview
Nine tasks of [LabUtopia](https://github.com/Rui-li023/LabUtopia) (Li et al., 2025; NeurIPS 2025 Datasets and
Benchmarks, [arXiv:2505.22634](https://arxiv.org/abs/2505.22634)) on NVIDIA Isaac Sim 6.1.0, in both modes: 18 task
directories, `tasks/labutopia/labutopia-<family>-i00-{privileged,standard}`. The scene is a chemistry laboratory: a
bench with glassware (beakers, a conical flask), a heater with a button, an instrument with a button panel, a drying
oven with a hinged door, a cabinet with drawers. The robot is a Franka Panda with its own gripper (`robot =
"franka-panda"`, `simulator = "labutopia"`).

```bash
harbor run -d embodied-first-exam@all -p tasks/labutopia -a codex -m <model>
```
The first task builds the simulator image from public sources; later tasks reuse it.

| | |
|---|---|
| upstream | LabUtopia @ `8df72784265c375a327ffa3f0a0cf8c676f229a7` (code MIT, assets CC BY-NC 4.0) |
| simulator | NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; see Changes from upstream), PhysX on the CPU, RTX cameras |
| image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` (`images/labutopia/`), never published: built locally |
| GPU | an RTX-class NVIDIA GPU (ray-tracing cores; `gpu_types` RTX 4090, L40S) with a driver Isaac Sim 6.1.0 supports (595 branch listed by NVIDIA; also runs on 580.178.04); 32 GB of RAM per simulator that renders |
| time limit | 3600 s in both modes (`[agent] timeout_sec`) |
| oracle | `full` in every task: LabUtopia's own scripted controller for the task, recorded |

**Before you run.**
- **Licence.** The image contains NVIDIA Isaac Sim 6.1.0 / Omniverse Kit (pip wheels from pypi.nvidia.com) and 64 files
  from NVIDIA's public asset server. Building and running it accepts the
  [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html)
  and NVIDIA's terms for those wheels and assets (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`). LabUtopia's assets are
  non-commercial (below). No account, login or token is needed.
- **Disk.** About 90 GB free for the first build (the image is about 40 GB).
- **First build.** About 25 min on a fast link, with network access to github.com (+ LFS), astral.sh, pypi.org,
  pypi.nvidia.com and omniverse-content-production.s3-us-west-2.amazonaws.com. Every task's Dockerfile starts with the
  recipe (`images/labutopia/Dockerfile`), so the build runs once per Docker host and later tasks take it from Docker's
  build cache. Maintainers who can pull the private image get its layers instead (compose `build.cache_from`). To
  build ahead of a run: `c=$(python3 scripts/stamp_mtimes.py stage tasks/labutopia/labutopia-pick-i00-privileged
  "$(mktemp -d)") && harbor run -p "$c" -a oracle` (reward 1). Each task allows 5400 s for its image build
  (`build_timeout_sec`).
- **Start-up.** The first simulator with its renderer in a container prepares the laboratory stage: 5 to 27 minutes,
  paid inside the agent's time in standard mode (Others, "Two kinds of Session").

## Upstream and license
[LabUtopia](https://github.com/Rui-li023/LabUtopia) at commit `8df72784265c375a327ffa3f0a0cf8c676f229a7`. The code is
under the MIT License (Copyright (c) 2025). The data assets (the laboratory stages and objects, baked into the image)
are under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): **non-commercial**, research and educational
use only. NVIDIA Isaac Sim 6.1.0 and Omniverse Kit may be used but not redistributed, so the image is never published
(`images/labutopia/BUILD_ONLY`). The Franka robot model is Isaac Sim 6.1's asset.

## Changes from upstream
- **Simulator version: Isaac Sim 6.1.0, not 5.1.0.** On NVIDIA's R595 driver, 5.1.0 crashes at start-up in its RTX
  renderer (a known incompatibility); 6.1.0 is the first release whose requirements list an R595 driver. Every instance
  and reference here is for 6.1.0. LabUtopia's code runs unchanged; the tooling adjusts three things before importing
  it (`rcb_labutopia._compat`): the deprecated extensions LabUtopia imports are enabled; one removed helper
  (`add_update_semantics`, used only for segmentation cameras) gets a stand-in; the finger contact sensors LabUtopia
  creates and never reads are created the way 5.1 created them. The controllers' success rates here are not
  LabUtopia's.
- **Nothing is loaded from the network at run time.** LabUtopia loads the robot from NVIDIA's asset server, and its
  stages reference more there by URL (the drawer tasks' cabinet, four materials). The image mirrors these 64 files under
  the server's own paths (each checked by sha256: `images/labutopia/nvidia_assets.sha256`), and the tooling redirects
  the server's URLs to the mirror (`omni.client.set_alias`), so LabUtopia's files stay as they are.
- **Success checks: LabUtopia's, restated as rules.** Each family's rule is a copy of the success check of LabUtopia's
  controller for the task (`rcb_labutopia.py`, one class per rule, each citing its source). LabUtopia evaluates a check
  while its script runs and reads the verdict when the script (or a phase of it) ends; a rule here cannot refer to a
  script, so:
  - a counter of 60 consecutive control steps is complete the moment it reaches 60, not when the script ends;
  - phases advance at the first step their check holds (`place`, `heat_liquid`, `open_close`), not when the scripted
    motion of the phase ends;
  - `place` adds what LabUtopia's timing implied: the hand more than 0.05 m from the beaker (the release condition of
    LabUtopia's other pick-and-place controller) for the 60 steps;
  - `shake` counts from the start of the episode, not from the end of the scripted pick;
  - `open_close` adds a direction: LabUtopia's second check asks only for the handle 0.13 m from where it was when the
    opening ended, which a drawer pulled further out would pass; the rule also asks the handle to be nearer to where
    it started.
- **Frame limits lifted.** LabUtopia's frame limits (800 to 2500 frames per task) are replaced by one technical cap:
  36,000 control steps (600 s of simulated time), stated in the instructions and in `/spec` (`max_control_steps`).
- **Controllers removed.** `images/labutopia/strip_solutions.py` deletes `controllers/` (the scripted solutions and
  their motion primitives), `policy/`, `data_collectors/`, `main.py` and the two factories that build them, in the same
  layer as the clone; the build fails if one is left. `tasks/`, `robots/`, `utils/`, `config/` and `assets/` stay.
- **Added.** Frozen instances, the privileged tooling (`rcb_labutopia.Session`), and the standard-mode service.

## Interface
- **Action.** 18 numbers per control step: a position target and a velocity target for each of the Franka's 9 joints
  (7 arm joints, 2 finger joints), what LabUtopia's controllers send. The joints' drives apply stiffness × position
  error + damping × velocity error. Accepted ranges: an arm joint's limits widened by 0.1 rad, -0.1 to 0.1 m for a
  finger (its travel is 0 to 0.04 m), ±10 for a velocity target; values outside are clipped. In the 6.1 asset
  `panda_finger_joint2` mirrors `panda_finger_joint1`: its targets are ignored.
- **Control step = one physics step, 1/60 s**, LabUtopia's own physics and controller rate.
- **The arm is not at rest at the start.** LabUtopia's reset leaves the Franka straight up with the drive targets of its
  home pose; held, they bring it there in about two seconds.
- **Privileged mode.** `rcb_labutopia.Session` in the agent's container: LabUtopia's task object and config, the USD
  stage, the robot, LabUtopia's readers, the rule's quantities, reset, step, recording, self-replay, the tool frame,
  forward and inverse kinematics of the arm, rendering (RGB and depth). Isaac Sim's own motion generation for the Franka
  (RMPflow, Lula kinematics) is in the image. Deliverable: `/app/output/trajectory.npz`, `(T, 18)`.
- **Standard mode** (`eai-standard/3.0`), the same adapter `environment/sim/server.py` in all nine families:
  - action types `joint_position` (9 position targets within the joints' ranges; velocity targets zero) and
    `joint_position_velocity` (the 18 targets above); rows `dt` apart, a multiple of 1/60 s;
  - LabUtopia's cameras for the task at 512 × 512, depth on request: `camera_1` (fixed, from the front), `camera_2`
    (fixed, straight down) and `wrist_cam` (on the hand); glassware is nearly transparent in RGB and absent from depth;
  - proprioception = the robot's own joints (positions, velocities, drive efforts), the gripper's opening, the
    tool-frame pose and the targets in effect; never an object or an instrument;
  - `/kinematics`: the tool frame (the point between the fingertips) and the hand link for arm joint positions, and
    damped-least-squares IK; `robot_spec` with the base pose, joint limits, drive gains and the gripper's command;
  - one episode, no reset.
- **World-frame information.** A privileged instruction gives the rule with LabUtopia's numbers, world heights and USD
  paths included: that mode reads the simulator anyway. A standard instruction states the same goal with every quantity
  relative to where things start ("more than 10 cm above where it stood", "pushed in more than 5 mm") and never a world
  coordinate or an object pose; the arm's base pose is in `/spec` (`robot_spec.base`).
  `ci_checks/check-world-frame-texts.sh` checks the standard texts.

## Grading
- **Rules.** Each family's rule (`rcb_labutopia.py`) is evaluated after every control step. The readings are
  LabUtopia's own (`utils/object_utils.py`): an object's *centre* is the centre of its bounding box, the *hand* is the
  point between the fingertips. The exact rule of each family is in its tasks' READMEs.

  | family | rule (LabUtopia's thresholds) | source |
  |---|---|---|
  | `pick` | the flask's centre more than 0.10 m above where it started, for 60 consecutive control steps | `pick_controller._check_success` |
  | `press` | the red button's cap pushed in more than 5 mm (beyond 0.405 m along x; it starts at 0.40), for 60 consecutive steps | `press_controller._check_success` |
  | `open_door`, `open_drawer` | the handle's centre more than 0.12 m from where it started and the hand more than 0.04 m from it, for 60 consecutive steps | `open_controller._check_success` |
  | `place` | the beaker lifted more than 0.10 m; then its centre within 0.05 m (horizontally) of the plate's and within 0.05 m of its initial height, the hand more than 0.05 m from it, for 60 consecutive steps | `place_controller._check_phase_success`; the release distance from `pickplace_controller.is_success` |
  | `pour` | the small beaker lifted more than 0.12 m; then, counted only while its centre is within the pour distance of the large beaker's (horizontally; 0.0776 m): turned more than 50 degrees, turned back to within 30 degrees, then more than 0.05 m above its start for 84 counted steps | `pour_controller._check_phase_success`, step for step |
  | `shake` | counted only while the beaker's centre is 0.05 m or more above its start: five moves of 0.05 m or more (horizontally); then within 0.01 m in x and in y over 60 counted steps | `shake_controller.is_success`, step for step |
  | `heat_liquid` | the beaker's centre lifted (above 0.82 m); then on the plate (centre at or below 0.86 m, within 0.05 m in x and in y of the plate's frame); then that with the button pressed (below 0.761 m) | `placepress_controller._check_phase_success`, in its order |
  | `open_close` | the open rule with 0.13 m for 60 consecutive steps; then the handle more than 0.13 m from where it is at that step and nearer to where it started, the hand more than 0.04 m from it, for 60 consecutive steps | `openclose_controller._check_open_success`, `_check_close_success`; the direction is added here |

- **Privileged mode: one replay.** `tests/grade.py`, in a separate sandbox without network, copies the trajectory's rows
  into a clean file and replays them once in a fresh process with its own copy of the tooling and the instance. The
  replay ends at the first step at which the rule is met (success) or when the rows run out. A file that cannot be read
  (not an npz, no `actions`, the wrong shape, more than 36,000 rows) is the agent's 0. A replay without a result, and a
  replay whose scene does not rebuild the instance's recorded placements (`instance_ok`), are `grader_error` and
  `infra_error`. A second replay renders `replay.mp4` after the verdict is on disk; it never changes it.
- **Standard mode: the live episode.** Meeting the rule does not end the episode and is never shown. The episode ends
  at `POST /finish`, at the end of the agent's session, or at the 36,000-step cap. `server.py` keeps the rule running
  after every control step and judges the episode when it ends:
  - goals that are a state (`pick`, `open_door`, `open_drawer`, `place`, `open_close`) are judged on the state the
    episode ends in; the rule's earlier phases (place's lift, open_close's opening) count as they happened;
  - goals that are an act (`press`, `pour`, `shake`) count once they have happened;
  - `heat_liquid`'s press with the beaker on the plate counts once it has happened, and the beaker must still be on the
    plate at the end;
  - at `/finish` and at the session's end, a hold the rule is counting (60 control steps; pour's 84) is run out with
    the last command held, for at most 120 control steps. The step cap is judged as it stands.

  The collect hook (`environment/sim/finalize.sh`) ends the episode, writes `final.json` from the service's record and
  then, after the verdict is on disk, replays the recorded trajectory once to render `replay.mp4`. An episode that ended
  in a simulator error scores 0. A live episode that did not rebuild the instance's placements (`instance_mismatch`), a
  missing or unfinished `final.json`, and no `episode.json` are `infra_error`, not the agent's 0.
- **Time limits.** Privileged: a verdict replay may take 2400 s; `[verifier] timeout_sec` 5400 covers it, the video
  replay and a margin, so `tests/grade.py` always writes a reward first. Standard: the collect hook's `timeout_sec` is
  4800 s (the episode's end, through a resume, the video replay and a margin).

## Tasks
| family | LabUtopia's config (level) | what stands on the bench | seed | reference rows (1/60 s each) |
|---|---|---|---|---|
| `pick` | `level1_pick` (1) | a glass conical flask | 0 | 478 |
| `press` | `level1_press` (1) | an instrument panel with three buttons | 0 | 328 |
| `open_door` | `level1_open_door` (1) | a drying oven, door closed | 4 | 687 |
| `open_drawer` | `level1_open_drawer` (1) | a cabinet, drawers closed | 2 | 641 |
| `place` | `level1_place` (1) | a glass beaker and a target plate | 0 | 836 |
| `pour` | `level1_pour` (1) | two glass beakers | 0 | 985 |
| `shake` | `level1_shake` (1) | a small glass beaker | 0 | 1087 |
| `heat_liquid` | `level2_HeatLiquid` (2) | a small glass beaker and a heater with a button | 1 | 1264 |
| `open_close` | `level2_openclose` (2) | a cabinet, drawers closed | 0 | 1341 |

The benchmark's own field `level` is LabUtopia's level (1: an atomic action, 2: a short-horizon task).

- **Instance.** One frozen instance per family: LabUtopia's scene built the way its `main.py` builds it (the Franka,
  the laboratory's USD stage, the task object of the family's config), then its own `reset()` with numpy's and Python's
  random generators seeded with the instance's seed, then 5 physics steps without a command. The seed of a family is
  the smallest of 0 to 4 on which LabUtopia's controller succeeds and the rule agrees with its verdict. The task's
  `instance.json` records the seed and two hashes: of the placements LabUtopia's reset authored (every load compares
  it, `instance_ok`) and of the start state (reported as `start_state_exact`).
- **Selection.** LabUtopia has 29 configs in five levels. A family here is a LabUtopia task (a) that its scripted
  controller solves through the robot's joint targets alone, (b) whose success check can be stated without that
  controller's script, and (c) that a motion made for nothing does not solve.
  - In: 9 tasks of levels 1 and 2. `level1_pour` / `level2_PourLiquid`, `level1_shake` / `level2_ShakeBeaker` and
    `level1_place` / `level2_TransportBeaker` put the same task to a scripted controller the same way: one family
    each, from the level-1 config.
  - Level 3 (six configs) is the same tasks on other objects and materials, LabUtopia's generalisation split for
    learned policies: not separate families.
  - Left out: `level1_close_door` and `level1_close_drawer`. They start with the door or drawer open, and their checks
    ask only that the handle has moved and the hand is away: random arm motions satisfy them. Closing stays in as the
    second half of `open_close`.
  - Left out: every task with the glass rod (`level1_stir`, `level2_StirGlassrod`, `level4_LiquidMixing`,
    `level4_OpenTransportPour`). LabUtopia's controllers write the rod's position every step so that it follows the
    hand; a trajectory of joint targets cannot repeat that.
  - Left out: `level4_CleanBeaker` (its check looks only at where the two beakers stand at the end, and one starts
    there), `level4_DeviceOperation` (its checks are tied to the controller's own phase counter), and level 5 (a
    Franka on a Ridgeback base: a different robot and action).
- **Reference solutions.** LabUtopia's scripted controllers (`controllers/<task>_controller.py`, state machines over
  RMPflow), run on the tooling's Session from the frozen instance in a checkout that still has them: the 18 targets in
  effect at every step, cut at the first step at which the family's rule is met (`solution/oracle.npz`). The privileged
  oracle hands the rows in; the standard oracle streams them through the client as `joint_position_velocity` chunks.
  One substitution, in `pour`: LabUtopia's pour primitive turns the wrist joint in velocity mode; the recorder executes
  that command as a position target that advances at the commanded velocity (391 of the reference's 985 rows).

## Others
### Determinism
PhysX runs on the CPU (LabUtopia's default backend, `numpy`). In the image:
- a fresh process repeats an episode bit for bit: the same rows give the same state hash (the robot's joints and
  targets, every rigid body's pose and velocity), in the same container or another one, with empty or filled caches,
  with or without rendering;
- `reset()` inside a process does not: the start state then differs by about 1e-5. So the privileged grader replays in
  a fresh process, and the privileged instruction tells the agent to check its final trajectory with the same command;
- outside the image the last bits can differ (another state hash, the same verdict). A trial is graded on the host it
  ran on.

### Two kinds of Session
With its RTX renderer, Isaac Sim prepares a whole stage for rendering when the stage is loaded. The first time in a
container, on eight idle cores: 5 minutes for the stage of six families (`lab_001`) and 13 minutes for the stage of
`press`, `shake` and `heat_liquid` (`lab_003`, 21 GB of RAM at the peak). The work is CPU-bound, so it takes longer when
simulators share cores (20 to 23 minutes each for `lab_003`, two at a time on eight cores). The start-up watchdog of a
standard task is 2400 s. It is paid once per container: Kit's caches are inside its package directory, and none is
shared between the agent's container, the sim sidecar and the verifier. A process that only simulates starts the
application without a Vulkan device (about 40 s the first time, about 20 s later); `Session(..., cameras=True)` starts
the renderer. The standard service is of the second kind; the privileged grader's verdict replay and the oracle are of
the first. The same rows end in the same state with the renderer and without it.

### Known limits
- **No liquid.** On the CPU backend nothing liquid is simulated (the `lab_003` stage's particle set needs GPU dynamics),
  and no success check in LabUtopia reads particles. `pour` is judged by the container's tilt above the target, `shake`
  by the container's motion, `heat_liquid` by a beaker on a plate and a button. The instructions say so.
- **The checks are LabUtopia's, with their slack.** `shake` counts five horizontal moves of 5 cm in any direction;
  `heat_liquid`'s button counts however it got pressed; `open_close` counts a drawer that came back without being
  pushed, once it was opened and released for a second.
- **Kit prints one start-up error** (`omni.physx.supportui`, "no running event loop") when LabUtopia's own extension
  bundle is enabled in a script; it has no effect.

### Egress
Agent egress is the model APIs and the package registries, in both modes (`[agent] network_mode = "allowlist"`). The
controllers are in LabUtopia's public repository, and a standard-mode agent could rebuild the simulator from it.
