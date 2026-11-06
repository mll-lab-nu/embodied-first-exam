# LabUtopia

Nine tasks of [LabUtopia](https://github.com/Rui-li023/LabUtopia) (commit `8df7278`; NeurIPS 2025 Datasets and
Benchmarks, [arXiv:2505.22634](https://arxiv.org/abs/2505.22634)) on NVIDIA Isaac Sim 6.1.0, in both modes: 18 task
directories, `tasks/labutopia/labutopia-<family>-i00-{privileged,standard}`. The scene is a chemistry laboratory: a
bench with glassware (beakers, a conical flask), a heater with a button, an instrument with a button panel, a drying
oven with a hinged door, a cabinet with drawers; the robot is a Franka Panda with its own gripper. `robot =
"franka-panda"`, `simulator = "labutopia"`. The tasks are in the `all` set only (not in `docs/core_set.toml`). Results
are attributed by DIGEST (PROTOCOL H.8).

LabUtopia's code is MIT, its assets CC BY-NC 4.0; Isaac Sim may not be redistributed, so the image is never published.
LabUtopia pins Isaac Sim 5.1.0; this benchmark runs it on 6.1.0 (below, "Simulator version").

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/labutopia -a codex -m openai/gpt-6-astra
```
The first task builds the simulator image from public sources (below); later tasks reuse it.

## Before you run

- **Licence.** The simulator image contains NVIDIA Isaac Sim 6.1.0 / Omniverse Kit (pip wheels from pypi.nvidia.com)
  and 64 files from NVIDIA's public asset server: building and running it accepts the
  [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html)
  and NVIDIA's terms for those wheels and assets (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`). LabUtopia's code is MIT
  and its assets (baked in) are [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): research and
  educational use only. Read them before your first run. No account, login or token is needed.
- **GPU and driver.** Linux x86_64, Docker with BuildKit and the NVIDIA Container Toolkit, an RTX-class NVIDIA GPU (Isaac
  renders with RTX even headless; PhysX runs on the CPU) with a driver Isaac Sim 6.1.0 supports (NVIDIA lists 595.58.03
  on Linux; checked on 595.91.07 with an RTX PRO 6000 Blackwell Server Edition and on 580.178.04 with an RTX 4090).
  32 GB of RAM per simulator that
  renders.
- **Disk.** About 90 GB free for the first build (the image is about 40 GB).
- **First build.** The image is not on a public registry, so the first task builds it with Docker from public sources:
  about 25 min on a fast link, network access to github.com (+ LFS), astral.sh, pypi.org, pypi.nvidia.com and
  omniverse-content-production.s3-us-west-2.amazonaws.com. Every task's Dockerfile starts with that recipe
  (`images/labutopia/Dockerfile`), so the build runs once per Docker host and later tasks take it from Docker's build
  cache. Maintainers who can pull `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` get its layers instead (compose
  `build.cache_from`). To build it ahead of the run: `c=$(python3 scripts/stamp_mtimes.py stage
  tasks/labutopia/labutopia-pick-i00-privileged "$(mktemp -d)") && harbor run -p "$c" -a oracle` (reward 1). Each task
  allows 5400 s for its image build (`build_timeout_sec`), room for a first build on a slower link.
- **Start-up.** The first simulator with its renderer in a container prepares the laboratory stage: 5 to 27 minutes,
  paid inside the agent's time in standard mode (below, "Two kinds of Session").

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

Every family has `oracle = "full"`: LabUtopia's own scripted controller for the task. The benchmark's own field
`level` is LabUtopia's level (1: an atomic action, 2: a short-horizon task).

## Selection
LabUtopia has 29 configs in five levels. A family here is a LabUtopia task (a) that its scripted controller solves
through the robot's joint targets alone, (b) whose success check can be stated without that controller's script and
(c) that a motion made for nothing does not solve.
- **In: 9 tasks of levels 1 and 2.** Three of them exist under two configs each that put the same task to a scripted
  controller in the same way (`level1_pour` / `level2_PourLiquid`, `level1_shake` / `level2_ShakeBeaker`,
  `level1_place` / `level2_TransportBeaker`; in LabUtopia they differ in which part of the motion a learned policy
  takes over): one family each, from the level-1 config.
- **Level 3 (six configs)** is the same tasks on other objects and materials, LabUtopia's generalisation split for
  learned policies: not separate families.
- **Left out: `level1_close_door` and `level1_close_drawer`.** They start with the door or the drawer open in the
  arm's reach, and their checks ask only that the handle has moved (0.13 m in any direction for the drawer, 0.08 m
  along one axis for the door) and that the hand is away from it: of ten smooth random arm motions, 3 satisfy the
  door's check and 6 the drawer's, and each is satisfied by its own reference reversed. Closing stays in as the second
  half of `open_close`, which no random motion and no other reference solved.
- **Left out: every task with the glass rod** (`level1_stir`, `level2_StirGlassrod`, `level4_LiquidMixing`,
  `level4_OpenTransportPour`). LabUtopia's controllers do not hold the rod in the gripper: once the pick primitive has
  closed the fingers, they write the rod's position every step so that it follows the hand
  (`controllers/robot_controllers/grapper_manager.py`). A trajectory of joint targets cannot repeat that, and without
  it the reference does not exist.
- **Left out: `level4_CleanBeaker`.** Its success check looks only at where the two beakers stand at the end, and one
  of them starts there; the pouring and shaking on the way are not checked.
- **Left out: `level4_DeviceOperation`.** Its seven checks are tied to the controller's own phase counter; it needs a
  rule written here, and then human review (PROTOCOL §4).
- **Left out: level 5** (`level5_Navigation`, `level5_Mobile_manipulation`): a Franka on a Ridgeback base, a different
  robot and action.

## Task definition
- **Instance.** One frozen instance per family: LabUtopia's scene built the way its `main.py` builds it (the Franka, the
  laboratory's USD stage, the task object of the family's config), then its own `reset()` with numpy's and Python's
  random generators seeded with the instance's seed (LabUtopia draws its placements from both and seeds neither), then
  5 physics steps without a command (the steps its loop runs before the first action). The seed of a family is the
  smallest of 0 to 4 on which LabUtopia's controller succeeds and the rule here agrees with its verdict (table under
  "Reference solutions"). The task's `instance.json` records the seed and two hashes: of the placements LabUtopia's
  reset authored (a function of the config and the seed alone; every load compares it, `instance_ok`) and of the start
  state (reported as `start_state_exact`).
- **The arm is not at rest at the start.** LabUtopia's reset leaves the Franka straight up with the drive targets of
  its home pose; held, they bring it there in about two seconds. That is LabUtopia's start, kept as it is.
- **Action.** 18 numbers per control step: a position target and a velocity target for each of the Franka's 9 joints
  (7 arm joints, 2 finger joints). This is what LabUtopia's controllers send (RMPflow gives both; the joints' drives
  apply stiffness x position error + damping x velocity error). A position target may lie beyond a joint's range (the
  joint stops, the drive keeps pushing): LabUtopia closes the fingers with targets down to -0.08 m, which is how its
  grasps squeeze. Accepted ranges: an arm joint's limits widened by 0.1 rad, -0.1 .. 0.1 m for a finger, +-10 for a
  velocity target; values outside are clipped. In the 6.1 asset `panda_finger_joint2` mirrors `panda_finger_joint1`
  (a mimic joint): its targets are ignored.
- **Control step = one physics step, 1/60 s**, LabUtopia's own physics and controller rate.
- **Success** is the family's rule, a copy of the success check of LabUtopia's controller for the task
  (`rcb_labutopia.py`, one class per rule, each with its source), evaluated after every control step; the first step
  at which it is met ends the episode in success ("success at any step": LabUtopia ends its episodes the same way).
  The readings are LabUtopia's own (`utils/object_utils.py`, in the image): an object's *centre* is the centre of its
  bounding box, the *hand* is the point between the fingertips.

  | family | rule (LabUtopia's thresholds) | source |
  |---|---|---|
  | `pick` | the flask's centre more than 0.10 m above where it started, for 60 consecutive control steps | `pick_controller._check_success` |
  | `press` | the red button's cap beyond x = 0.405 m (it starts at 0.40 and goes in along +x), for 60 consecutive steps | `press_controller._check_success` |
  | `open_door`, `open_drawer` | the handle's centre more than 0.12 m from where it started and the hand more than 0.04 m from it, for 60 consecutive steps | `open_controller._check_success` |
  | `place` | the beaker lifted more than 0.10 m; then its centre within 0.05 m (horizontally) of the plate's and within 0.05 m of its initial height, the hand more than 0.05 m from it, for 60 consecutive steps | `place_controller._check_phase_success`; the release distance from `pickplace_controller.is_success` |
  | `pour` | the small beaker lifted more than 0.12 m; then, counted only while its centre is within the pour distance of the large beaker's (horizontally; 0.0776 m): turned more than 50 degrees, turned back to within 30 degrees, then more than 0.05 m above its start for 84 steps | `pour_controller._check_phase_success`, step for step |
  | `shake` | counted only while the beaker's centre is 0.05 m or more above its start: five times, the centre gets 0.05 m or more (horizontally) from where that count began; then it stays within 0.01 m in x and in y over 60 steps | `shake_controller.is_success`, step for step |
  | `heat_liquid` | the beaker's centre above z = 0.82 m; then the beaker on the plate (centre at or below z = 0.86 m, within 0.05 m in x and in y of the plate's frame); then that and the button's frame below z = 0.761 m | `placepress_controller._check_phase_success`, in its order |
  | `open_close` | the open rule with 0.13 m for 60 consecutive steps; then the handle's centre more than 0.13 m from where it is at that step and nearer to where it started than it is at that step, and the hand more than 0.04 m from it, for 60 consecutive steps | `openclose_controller._check_open_success`, `_check_close_success`; the direction is added here |

- **Where the rules differ from LabUtopia's use of its checks.** LabUtopia evaluates a check while its script runs and
  reads the verdict when the script (or a phase of it) has ended; a rule here cannot refer to a script, so:
  - a counter of 60 consecutive steps is complete the moment it reaches 60, not when the script ends. On seeds 0 and
    3 of `open_drawer` LabUtopia's frame limit (1000) cuts the script short with the drawer open and released for
    more than a second: a failure by its verdict, a success by the rule;
  - phases advance at the first step their check holds (`place`, `heat_liquid`, `open_close`) instead of when the
    scripted motion of the phase has ended. For `place`, whose last check LabUtopia reads once the gripper has opened
    and withdrawn, the rule adds what that timing implied: the hand more than 0.05 m from the beaker (the release
    condition of LabUtopia's other pick-and-place controller) for 60 consecutive steps;
  - `shake` counts from the start of the episode, not from the end of the scripted pick (nothing is counted below
    0.05 m of lift in either case);
  - `open_close`: LabUtopia's second check asks for a handle 0.13 m from where it was when the opening ended, in
    whichever direction, which its script only ever moves one way. Without the script a drawer pulled a further
    0.13 m out would pass, so the rule also asks for the handle to be nearer to where it started than it was at that
    step. The reference and the verdicts on seeds 0 to 4 are the same with and without that condition.
- **LabUtopia's frame limits** (800 to 2500 frames per task) are lifted: the wall clock is the budget. One technical
  cap bounds an episode: it ends after 36000 control steps (600 s of simulated time), stated in the instructions and in
  `/spec` (`max_control_steps`).
- **World-frame information.** A privileged instruction gives the rule with LabUtopia's numbers, world heights and USD
  paths included: that mode reads the simulator anyway. A standard instruction states the same goal with every quantity
  relative to where things start ("more than 10 cm above where it stood", "pushed in more than 5 mm", "along the
  forward axis of the arm's base") and never a world coordinate or an object pose; the arm's base pose is in `/spec`
  (`robot_spec.base`). `ci_checks/benchmarks/labutopia/advisory-world-frame.sh` checks the standard texts.
- **Budget: 3600 s**, both modes (each task's `[agent] timeout_sec`, stated in its instruction's closing
  `## Time limit` section), the same as RoboLab's (also on Isaac Sim).

## Simulator version: Isaac Sim 6.1.0
LabUtopia's README installs Isaac Sim 5.1.0. The host this benchmark was built on has NVIDIA's R595 driver (595.91.07,
RTX PRO 6000 Blackwell Server Edition), on which 5.1.0 crashes at start-up in its RTX renderer (a known
incompatibility; NVIDIA's answer is the 580 driver branch); 6.1.0 is the first release whose requirements list an R595
driver. So the image has 6.1.0, and every instance and reference here is for it.
- LabUtopia's code runs unchanged. The tooling adjusts three things before importing it (`rcb_labutopia._compat`): the
  interfaces LabUtopia imports are deprecated extensions in 6.x and have to be enabled; one removed helper
  (`add_update_semantics`, used only for segmentation cameras) gets a stand-in; the contact sensors LabUtopia's Franka
  puts on the fingers and never reads are created the way 5.1 created them (6.x refuses the parent prim).
- The robot is Isaac Sim 6.1's Franka asset (LabUtopia references the robot under the Isaac asset root, whichever
  version is installed).
- **Nothing is loaded from the network at run time.** As published, LabUtopia loads the robot from NVIDIA's asset
  server, and its laboratory stages reference more there by URL: the cabinet of the drawer tasks (in the Isaac 4.2
  asset tree) and four materials. The image mirrors these 64 files under the server's own paths (fetched at build,
  each checked by sha256: `images/labutopia/nvidia_assets.sha256`) and the tooling redirects the server's URLs to the
  mirror (`omni.client.set_alias`), so LabUtopia's files stay as they are. Without them the cabinet is simply missing;
  the instance check notices (`instance_ok`).
- 6.1.0 also runs on a 580-branch driver (580.178.04, RTX 4090: every oracle and nop scored as expected, see
  Verification). Not checked: what LabUtopia's controllers do on 5.1.0 (it does not start here).

## Determinism
PhysX runs on the CPU (LabUtopia's default backend, `numpy`). Measured in the image on the authoring host:
- a fresh process repeats an episode bit for bit: the same rows give the same state hash (the robot's joints and
  targets, every rigid body's pose and velocity), in the same container or in another one, with empty or filled
  caches, with or without rendering, with or without cameras;
- `reset()` inside a process does not: the start state then differs by about 1e-5. So the privileged grader replays in
  fresh processes and compares two of them, and the privileged instruction tells the agent to check its final
  trajectory with the same command;
- outside the image the last bits can differ (the same rows on the host's own Python environment end in another
  state hash, with the same verdict), as RoboLab's notes report between hosts. A trial is graded on the host it ran on.

## Modes
- **Privileged:** `rcb_labutopia.Session` in the agent's container: LabUtopia's task object and config, the USD stage,
  the robot, LabUtopia's readers, the rule's quantities, reset, step, recording, self-replay, the tool frame, forward
  and inverse kinematics of the arm (a numpy chain read from the stage), rendering (RGB and depth, every camera).
  Deliverable `/app/output/trajectory.npz`, `(T, 18)`. LabUtopia's code other than the controllers is in the image, and
  so is Isaac Sim's own motion generation for the Franka (RMPflow, Lula kinematics). The verifier replays the rows in
  two fresh processes in its own sandbox: both must succeed and end in the same state.
- **Standard (`eai-standard/2.2`):** the shared layer of `embodied_first_exam/standard/` and the adapter
  `environment/sim/server.py`, the same in all nine families:
  - action types `joint_position` (9 position targets within the joints' ranges; velocity targets zero) and
    `joint_position_velocity` (the 18 targets above, with their wider ranges); rows `dt` apart, a multiple of 1/60 s,
    `linear` or `hold`; clipped values reported;
  - LabUtopia's cameras for the task at 512 x 512 (LabUtopia records 256 x 256), depth on request: `camera_1` (fixed,
    from the front), `camera_2` (fixed, straight down) and `wrist_cam` (on the hand);
  - proprioception = the robot's own joints (`q_`, `qd_`, `effort_`), the gripper's opening, the tool-frame pose and
    the targets in effect (`cmd_`); never an object or an instrument;
  - `/kinematics` = the tool frame (the point between the fingertips) and the hand link, for arm joint positions, and
    damped-least-squares IK; `robot_spec` with the base pose, joint limits, drive gains and the gripper's command;
  - `meta["time_s"]` / `meta["time_left_s"]` count from the agent's first request to the service. What `time_left_s`
    does not hold is the time the agent waits for the service before its first request is answered: the minutes of
    start-up that fall inside the agent's phase are part of its budget, and the instruction says so;
  - crash recovery with resume class `exact` (a resumed service is a fresh process);
  - a request is checked in full before anything is executed: a malformed field (null or a wrong type for `dt`,
    `seconds`, `cameras`, `note`, `video`, `interpolate`, `depth`; a `dt` that is not finite or not a whole multiple of
    1/60 s) is a 400 and the episode goes on. Null for `dt`, `seconds`, `video_fps`, `cameras` or `note` means the
    default.
- **Grading, standard mode.** The trial is graded by its live episode (docs/protocol/README.md H.4): `success` = the
  live episode's success, judged by the sim service on the episode the agent ran, with no grading replay; an
  episode that ended in a simulator error scores 0. The collect
  hook (`environment/sim/finalize.sh`) ends the episode, writes `final.json` from the service's record and then, after
  the verdict is on disk, replays the recorded trajectory once to render `replay.mp4` (a failed video replay costs the
  video only). Its `timeout_sec` is 4800 = 2700 (the episode's end, through a resume) + the video replay (at most
  1800 s) + 300 s.
- **Time limits, privileged mode.** A verdict replay only simulates: under a minute to start, then at most 36000 rows
  at about 200 control steps/s (180 s); it may take 2400 s and is killed at that limit. `[verifier] timeout_sec` 5400 =
  2 x 2400 + the video replay, whose renderer starts cold (what is left; skipped under 120 s) + 300 s, so
  `tests/grade.py` always writes a reward before Harbor's timeout.
- **What is not the agent's 0** (`infra_error = 1` in `reward.json`, PROTOCOL §4). Standard: `final.json` missing
  (the service writes it as soon as its scene is up), unreadable, or not finalized (the collect hook was killed before
  it wrote the verdict); the service never ending its episode for the hook; a give-up after crashes between calls or a
  failed resume; a live episode that did not rebuild the instance's placements (`instance_mismatch`); no
  `episode.json`. A crash inside a call (`sim_crashed_on_call`) stays the agent's failure. `final.json` is written
  whole (temporary file, then rename). Privileged: a replay without a result and an instance mismatch set
  `grader_error` and `infra_error`; a deliverable that cannot be read (not an npz, no `actions`, object arrays, the
  wrong shape, more than 36000 rows) is the agent's 0 (`bad_trajectory`), never a grader error. A result a replay wrote
  counts whatever the process's exit status (Isaac Sim may fail while it shuts down, after the result is on disk).
- **Two kinds of Session.** With its RTX renderer, Isaac Sim prepares a whole stage for rendering when the stage is
  loaded (a shader pipeline for every material, textures and geometry into its derived-data cache). The first time
  in a container, on eight idle cores: 5 minutes for the stage of six families (`lab_001`: 299 s) and 13 minutes for
  the stage of `press`, `shake` and `heat_liquid` (`lab_003`: 803 s, 21 GB of RAM at the peak). The work is CPU-bound
  and uses every core, so it takes longer when simulators share them: two at a time on eight cores, about 9 minutes
  each for `lab_001` and 20 to 23 minutes each for `lab_003`; on an 8-vCPU L40S host about 27 minutes for `lab_003`.
  The start-up watchdog of a standard task is 2400 s: the number of trials at a time has to fit the cores. It is paid
  once per container: Kit's caches are inside its package directory, each container has its own, none is shared
  between an agent's container, the sim sidecar and the verifier. A process that only simulates does not need any of
  it, so `Session(...)` starts the application without a Vulkan device (the renderer never starts): about 40 s the
  first time in a container, about 20 s later. `Session(..., cameras=True)` starts it with the renderer and the task's
  cameras. The standard service is of the second kind and renders a first frame before it answers; the privileged
  grader's two verdict replays and the oracle are of the first.
- **Looking never changes the physics.** The same rows end in the same state with the renderer and without it.

## Reference solutions
LabUtopia's scripted controllers (`controllers/<task>_controller.py`, state machines over RMPflow), run on the
tooling's Session from the frozen instance, in a checkout that still has them and in LabUtopia's own order (state,
controller, targets, one physics step): the 18 targets in effect at every step, cut at the first step at which the
family's rule is met: `solution/oracle.npz` in every task. The privileged oracle hands the rows in; the standard oracle
streams them through the client as `joint_position_velocity` chunks.
- **One substitution, in `pour`.** LabUtopia's pour primitive turns the wrist joint in velocity mode: it switches that
  drive's stiffness off and commands a velocity. An action here is targets, not drive modes, so the recorder executes
  that command as a position target that advances at the commanded velocity (391 of the reference's 985 rows); the
  controller still succeeds, by its own verdict and by the rule.
- **Seeds.** LabUtopia's controllers do not succeed on every placement. In the image, seeds 0 to 4:

  | family | seed 0 | seed 1 | seed 2 | seed 3 | seed 4 | frozen |
  |---|---|---|---|---|---|---|
  | `pick` | 1 / 1 (478) | 1 / 1 (519) | 1 / 1 (472) | 1 / 1 (513) | 1 / 1 (547) | 0 |
  | `press` | 1 / 1 (328) | 1 / 1 (306) | 1 / 1 (306) | 1 / 1 (307) | 1 / 1 (305) | 0 |
  | `open_door` | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 (687) | 4 |
  | `open_drawer` | 0 / 1 (974) | 0 / 0 | 1 / 1 (641) | 0 / 1 (970) | 1 / 1 (602) | 2 |
  | `place` | 1 / 1 (836) | 1 / 1 (829) | 1 / 1 (779) | 1 / 1 (817) | 1 / 1 (883) | 0 |
  | `pour` | 1 / 1 (985) | 1 / 1 (1042) | 1 / 1 (1015) | 1 / 1 (960) | 1 / 1 (933) | 0 |
  | `shake` | 1 / 1 (1087) | 1 / 1 (1112) | 1 / 1 (1094) | 1 / 1 (1079) | 1 / 1 (1047) | 0 |
  | `heat_liquid` | 0 / 1 (802) | 1 / 1 (1264) | 1 / 1 (1030) | 1 / 1 (1070) | 1 / 1 (976) | 1 |
  | `open_close` | 1 / 1 (1341) | 0 / 0 | 1 / 1 (1242) | 1 / 1 (1340) | 0 / 1 (801) | 0 |

  Each cell: LabUtopia's verdict / the rule's (the control step at which the rule is met). 45 runs: the controller
  succeeds on 35, the rule is met on 39. The four runs in which only the rule is met: `open_drawer` seeds 0 and 3
  (the drawer open and released; LabUtopia's frame limit cuts the script before its own counter is full),
  `heat_liquid` seed 0 and `open_close` seed 4 (Known limits). The rule is never the stricter one.

## Integrity
- **Controllers removed.** `images/labutopia/strip_solutions.py` deletes `controllers/` (the scripted solutions and
  their motion primitives), `policy/`, `data_collectors/`, `main.py` and the two factories that build them, in the same
  image layer as the clone (no layer holds them); the build fails if its check afterwards finds one. What builds a
  scene and reads its state stays: `tasks/`, `robots/`, `utils/`, `config/`, `assets/`.
- **Agent egress is the model APIs and the package registries, in both modes.** The controllers are in LabUtopia's
  public repository; a standard-mode agent could also rebuild the simulator from it.
- **Only rows cross to the verifier.** The privileged grader copies the trajectory's rows into a clean file and replays
  them with its own copy of the tooling and of the instance, in a sandbox the agent never saw, without network.
- **Caches are per container** (above), so nothing an agent's container cached reaches the grader.

## Known limits
- **No liquid.** With LabUtopia's default backend (PhysX on the CPU, used here) nothing liquid is simulated: its
  `lab_003` stage carries a particle set that PhysX only simulates with GPU dynamics (LabUtopia's `--backend gpu`; on
  the CPU, Kit logs `Particles feature is only supported on GPU`), and no success check in LabUtopia reads particles.
  `pour` is judged by the container's tilt above the target, `shake` by the container's motion, `heat_liquid` by a
  beaker on a plate and a button. The instructions say so.
- **The checks are LabUtopia's, with their slack.** `shake` counts five horizontal moves of 5 cm, in any direction;
  `heat_liquid`'s button counts however it got pressed (on seed 0 the hand presses it while it sets the beaker down,
  which is why that family uses seed 1); `open_close` counts a drawer that came back without being pushed, once it
  was opened and released for a second (seed 4: that is how its rule is met while LabUtopia's script reports a
  failed opening).
- **The first simulator with its renderer in a container takes minutes to start** (above): a standard agent waits for
  its service that long, out of its own budget (`Robot()` waits up to 3600 s). Baking Kit's caches into the image would
  remove the wait, but they can only be made with a GPU, which `docker build` does not have.
- **Isaac Sim 6.1.0, not LabUtopia's 5.1.0** (above): the controllers' success rates here are not LabUtopia's.
- **Kit prints one start-up error** (`omni.physx.supportui`, "no running event loop") when LabUtopia's own extension
  bundle is enabled in a script; it has no effect.
- **`reset()` is approximate** inside a process (above).
- **`open_close`'s reference also solves `open_drawer`**: it opens that drawer on the way. It is the one case in
  which another family's reference succeeds.

## Verification
On the authoring host (RTX PRO 6000 Blackwell Server Edition, driver 595.91.07), with the image built locally:
`harbor run -a oracle` scored 1 on all 18 task directories (both fresh-process replays and, in standard mode, the live
episode ending in the reference's recorded state) and `harbor run -a nop` scored 0 on all 18; the reference, its first
half, the reference without its last 30 rows and holding the initial targets for 10 s were run through the grader's
own replay in every family (1, 0, 0, 0).

On an RTX 4090 host (driver 580.178.04), with the standard tasks graded live: `harbor run -a oracle` scored 1 and
`harbor run -a nop` 0 on all 9 standard tasks (live verdicts, no infrastructure, grader or sim error), and the
privileged oracle scored 1 on pick and pour. In 8 of 9 families the live end state equals the reference's recorded
state hash; in pour every run on that host (live and both privileged replays) starts and ends in the same other last
bits (end `2da5a7461d15403e` instead of `4a617cdeb8353c13`) with the same verdict, as "Determinism" describes for
other hosts. The three `lab_003` tasks (press, shake, heat-liquid) peaked at 22-23 GiB in the sim sidecar.

## Files
Every task directory is self-contained: `environment/rcb_labutopia.py` (privileged; the verifier's own copy in
`tests/`) or `environment/sim/` (standard: the adapter `server.py`, `rcb_labutopia.py`, the collect
hook), `instance.json`, `solution/oracle.npz`; the standard tasks take the shared 2.2 layer and the agent's client
(`rcb_limited.py`, `run.sh`, `rcb1.py`, `rcb_client.py`) from the pinned `standard-files` image. `images/labutopia/` has the image recipe (Dockerfile, VERSION,
BUILD_ONLY, requirements.txt, nvidia_assets.sha256, strip_solutions.py).
