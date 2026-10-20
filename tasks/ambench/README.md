# AM-Bench

[AM-Bench](https://github.com/ambench/ambench) @ 60bf5b7 (Apache-2.0) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0: aerial
manipulation. The robot is AM-Bench's FA-Hexa, a fully actuated hexarotor (six tilted rotors: it can hold any attitude while
hovering) carrying a 4-joint arm (three pitch joints and a roll joint) with a two-finger gripper, driven by AM-Bench's own
whole-body controller (floating-base inverse kinematics with Pyroki, a PID for the airframe). `simulator = "ambench"`,
`robot = "ambench-fahexa"`.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/ambench -a codex -m openai/gpt-6-astra
```
Read [Before you run](#before-you-run) first: the first run builds the simulator image (about 25 min on a fast link).

## Before you run
- **Licence (your decision).** The simulator image contains NVIDIA Isaac Sim 5.1 / Omniverse Kit, which NVIDIA licenses for use
  and not for redistribution, so it is not on a public registry: your first run builds it on your machine. That build
  accepts, on your behalf, the NVIDIA Isaac Sim / Omniverse licence agreement and NVIDIA's terms for the Isaac Sim wheels
  on pypi.nvidia.com and for the files of NVIDIA's public asset bucket that the image bakes in (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES` and `ACCEPT_EULA=Y`). Read them before you
  run these tasks. No account, login or token is needed.
- **Host.** Linux x86_64, Docker with BuildKit (the `buildx` plugin) and the NVIDIA Container Toolkit, one RTX-class NVIDIA
  GPU (Isaac renders with RTX even headless) with a driver Isaac Sim 5.1 supports (checked: 580.159 on an RTX 4090).
- **Disk.** About 60 GB free for the first build (the image is about 22 GB, plus BuildKit's cache while it builds).
- **First run: the image builds itself (about 25 min on a fast link).** Harbor builds the simulator image from public sources only
  (Docker Hub `nvidia/cuda`, snapshot.ubuntu.com, github.com, pypi.org, download.pytorch.org,
  pypi.nvidia.com, NVIDIA's public asset bucket on S3), once per machine: every later AM-Bench task reuses its layers and
  starts in seconds. The tasks allow 90 min for the build (`[environment] build_timeout_sec`); on a slow link raise it with
  `--environment-build-timeout-multiplier`. Organization members who can read `ghcr.io/mll-lab-nu/efe-private` (`docker
  login ghcr.io`) pull the prebuilt layers instead (compose `cache_from`, about 8 min for 22-27 GB); without that access the build prints a warning
  that it cannot read the cache image and goes on building: expected. To build ahead of a batch:
  `docker build --target ambench-base tasks/ambench/ambench-press-button-fahexa-i00-privileged/environment` (the layers every task then reuses).
- **Nothing to download or accept by hand** beyond the licence above: the first run builds everything.

Nine of AM-Bench's twelve tasks, one frozen instance each (seed 0): eight in both modes, `ambench-<task>-fahexa-i00-privileged`
and `-standard` (`eai-standard/2.2`), and PullLever in standard mode only, graded by its live episode (below): 17 task
directories, `oracle = "full"`.

| Family | AM-Bench environment (`…-Am-FAHexa-Abs-PID-Direct-v0`) | Task | Episode | Oracle: success at control step (end state) |
|---|---|---|---|---|
| `press_button_fahexa` | `PressButton` | press a spring-loaded button on a (tilted) wall by ≥ 4 mm | 20 s | 1027 (`fcd4de9b…`) |
| `push_slider_fahexa` | `PushSlider` | push a knob 0.95 m along a rail on a wall | 26 s | 1353 (`01a85d35…`) |
| `rotate_valve_fahexa` | `RotateValve` | turn a valve wheel on a wall ≥ 170° clockwise | 20 s | 1002 (`1b976104…`) |
| `open_door_fahexa` | `OpenDoor` | push a hinged door open by > 20° | 15 s | 395 (`f778f7c7…`) |
| `peg_in_hole_fahexa` | `PegInHole` | insert the held peg into a socket on a (tilted) wall | 20 s | 1041 (`88054491…`) |
| `ndt_fahexa` | `NDT` | hold the end effector at an inspection point high on a warehouse wall for 100 steps | 20 s | 1212 (`bd8da252…`) |
| `lemon_harvesting_fahexa` | `LemonHarvesting` | pick the lemon off its stem and drop it into the tote | 30 s | 1739 (`a0426217…`) |
| `cabinet_pick_place_fahexa` | `CabinetPickPlace` | lift a can onto the cabinet's top shelf | 60 s | 2752 (`c8c72a8b…`) |
| `pull_lever_fahexa` (standard only) | `PullLever` | pull a spring-loaded lever on a (tilted) wall up by > 40° | 20 s | 899 (no single end state: six replays, three states) |

**PullLever, standard only.** GPU PhysX does not replay it bit for bit (Determinism below): the same rows, from
identical states and identical controller outputs, resolve the gripper's first contact with the lever differently in
fresh processes. With the tooling's fixes its reference rows succeed every time (six fresh replays, all at control step
899, no GPU fault) but end in three different states (`1ef7b812…` 3×, `1abad6ac…` 2×, `420b5617…` 1×), so an open-loop
trajectory of it cannot be graded by its end state. So it ships in standard mode only (PROTOCOL §2: a benchmark offers
any subset of the modes; its README's Twin row says why) and is graded by its live episode, the trusted record of H.4
(its frozen `instance.json` says `"determinism": "verdict"`), as RoboDojo's six non-reproducible tasks. The tooling
switches off its re-colouring of the lever at reset (Tooling, below), so the descriptions say its colours do not change.

Not in this set:
- **FrameAssembly, WipeWindow, TossBall**: AM-Bench's scripted experts did not succeed on the seed-0 instances (FrameAssembly
  0/13, WipeWindow 0/9, TossBall 0/21 runs over the expert's own draw and torch seeds), so there is no reference solution yet.
  They fail on Isaac Lab v2.3.2 too (the release for Isaac Sim 5.1), so the cause is not the Isaac Lab commit.
- AM-Bench's other robot and controller profiles (the quadrotor, the omnidirectional hexa, the under-actuated hexa, the
  end-effector-only robot; L1 and MPC controllers) are variants of the same tasks.

## Tasks
- The task directories are the deliverable; the tooling that built them is kept outside this repository. Each instance's
  `instance.json` and `oracle_actions.npy` are committed in the tasks; PullLever has only its standard task.
- The instance is AM-Bench's seeded reset with seed 0
  (`cfg.seed = 0`, `env.reset(seed=0)`); AM-Bench draws the task's variation from it. `instance.json` holds the environment
  id, the seed and `initial_sha` (the sha256 of every articulation's and rigid object's root state, joint positions and
  velocities after the reset); every replay rebuilds the start and checks it (`instance_matches`).

## Success (AM-Bench's own)
Each task's `_get_success` (its `terminated` signal), unchanged except RotateValve's angle (below), evaluated after
every control step; the episode ends at the first step where it holds, or with AM-Bench's time-out (`episode_length_buf >= max_episode_length - 1`, at decimation 1:
control step 120 × episode length − 1). Each task's description (shown in both instructions) gives the
check exactly. Weak checks are kept as AM-Bench wrote them and stated: CabinetPickPlace only tests the can's height and
speed (a can still held at that height passes); FrameAssembly (not in the set) tests one moment of the frame's centre.

**RotateValve: the unwrapped angle.** `base_to_shaft` has no limits,
and omni.physx (107.3, Isaac Sim 5.1) creates an articulation's revolute joint without limits as a wrapped joint, whose
position PhysX reports in [-π, π] (omni.physx's own tests: "the joint without limits will be created as regular WRAPPED
joint"). AM-Bench's check `joint_pos >= 17π/18` on that value also passes a counter-clockwise turn of 190° (reported as
+170°), while the task (and its instruction) is a clockwise turn of 170°. The tooling, the same file in the agent's
environment and in the grader, replaces RotateValve's `_get_success` with the same comparison on the unwrapped angle: the
sum of the joint's per-step changes since the reset, each wrapped into [-π, π) (the joint's velocity limit, 5 rad/s, moves it
at most 0.042 rad per 1/120 s step, so the sum is exact). Physics, states, `initial_sha` and the end-state hashes are
unchanged; for a clockwise turn below π the two readings agree, so the recorded oracle ends at the same step. The angle is
`s.valve_angle()` in the tooling. This is a correction of a wrap-around, not a stricter rule: the upstream threshold,
direction and timing stay as they are.

## Oracle (PROTOCOL §4)
`oracle = "full"`, 17/17. The reference solution of an instance is AM-Bench's scripted expert for the task
(`policies/scripted/<task>.py`, `inject_noise=False`), run in closed loop on the frozen instance and
recorded as the rows the tooling executed, followed by 2 s of holding its last command (`solution/oracle_actions.npy`);
rows after a replay's own success never run. The privileged oracle (`solution/oracle.py`) replays them through the
agent's own tooling and hands in all of them, the 2 s hold included, not only the rows its own run executed (handing in
only those, OpenDoor's 395, left a replay that needed one step more nothing to run); the standard oracle
(`solution/oracle_replay.py`) streams them as one-second `ee_pose` chunks (`hold`, dt = 1/120 s) through the client. The
expert reads the simulator's state between steps, so its own live episode is not the reference: two fresh-process
replays with the grader's CLI must both succeed and end in the same state before an instance is frozen.

The experts are not in the image: the Dockerfile copies AM-Bench without `policies/scripted/`, `ambench_learn`, its scripts,
documentation and git history, blanks the task registrations' `scripted_policy_entry_point`, and fails if anything left
names them. The recording mounts the expert read-only from a checkout outside the image. AM-Bench is public on GitHub and
not on PyPI; the agent's egress is the model APIs and the package registries (`network_mode = "allowlist"`), so the experts
cannot be fetched during a trial.

## Tooling (`rcb_ambench.py`)
`Session` (frozen instance, reset, step, `hold_action`, status, `actions`, replay, `save_trajectory`), the privileged state
(`state()`, `objects()`, `proprio()`), the two onboard cameras on request (`Session(cameras=True, depth=True)`:
`render_frame`, `render_depth`, `camera_info`, `start_video` / `stop_video`) and `env` (the Isaac Lab environment itself).
No motion primitives. For standard mode the same module provides the 2.2 proprio groups, the robot's spec sheet and a
stateless numpy model of the arm on its airframe (`/kinematics`; checked against the simulator's link poses to 2e-7 m).
- **Actions**: AM-Bench's absolute end-effector pose action of the `Abs-PID` profile, 8 per control step: the ee_link
  target position (x, y, z, m, relative to the environment's origin), its orientation (qw, qx, qy, qz; for the FA-Hexa the
  command frame is the ee_link frame) and the gripper (-1 closed .. +1 open). The tooling clips only the gripper to
  [-1, 1] and refuses a zero quaternion; it does not normalise the quaternion. 120 Hz control, one physics step of 1/120 s
  per action.
- **End state.** Isaac Lab resets an environment whose episode ended inside that very step (`DirectRLEnv.step` →
  `_reset_idx`); the tooling hashes the state just before that reset (the episode's `state_sha`) and keeps what the robot
  sensed then (proprio, the state its cameras draw), so observations after the end show the end.
- **Changes to the environment's behaviour** (each one measured, none changes a task): the controller's IK solve, every
  phase of a control step and every call on PhysX's tensor views are synchronized with the GPU; the propellers' animation (USD writes under the articulation every
  step) is switched off, so they stand still in the images; the onboard cameras are drawn by a render worker, never in the
  physics process; PullLever's colour randomization (`randomize_visual_color`, a Replicator API this Isaac Sim lacks) is
  dropped. See Determinism.
- CLI: `replay` (one fresh-process replay: the grader's), `film` (the same rows, filmed through the render worker),
  `make-instance`, `run-actions`, `render-worker` (internal).

## Determinism (Isaac Sim 5.1, GPU PhysX, RTX 4090)
A fresh process replays a frozen instance's rows to the same end state; every frozen instance was replayed at least twice
to identical end states. The tooling's five fixes make that hold:
1. **SYNC (IK).** AM-Bench's controller solves its floating-base IK on the CPU (Pyroki / jaxls) from GPU tensors and hands
   the result back to the GPU every step; a device synchronization brackets that solve.
2. **SYNC (phases).** Every phase of a control step (pre-physics step, the action's application, the writes to PhysX, the
   physics step, the buffers' update, dones, rewards, resets, observations) is bracketed by a synchronization, at no
   measurable cost.
3. **PROPELLERS.** AM-Bench's propeller animation (orientations written into the robot's USD prims every step) is off.
4. **CAMERAS.** Rendering inside the physics process (Isaac renders after every physics step when cameras exist;
   `render()` also calls `forward()`) makes runs part, so the onboard cameras are drawn by a second, render-only Isaac
   process from the physics state (`Renderer`): the physics process is the same with or without cameras, so a privileged
   agent can look.
5. **SYNC (views).** Every `get_*` / `set_*` / `apply_*` call on PhysX's tensor views of every articulation, rigid object
   and contact sensor is bracketed by a synchronization too (`sync_views`), at no measurable cost.

**What is left: a rare race under GPU contention.** With other jobs on the GPU (three replays at once on a shared card,
or under Harbor), about 1 in 8 replays still ends one step later or in another end state while succeeding (OpenDoor at
396 instead of 395, NDT in other last bits); none changed an outcome. So the graders decide on the outcome and report
the hashes (Grading).

**PhysX buffers.** Isaac Lab sizes PhysX's GPU buffers for thousands of parallel environments; the tooling gives its one
environment one environment's worth (contacts 2^18, aggregate pairs 2^18, ...): a camera-free process takes 1.2 GB of GPU
memory instead of 3.2 GB, the render worker 3.4 GB, so the standard sidecar 4.6 GB instead of 6.5 GB (with another
user's 17.7 GB on the card, the larger one left too little: PhysX kernels failed to launch, `live_gpu_faults`). All
eight tasks' frozen rows replay to their frozen end states with them, no overflow reported.

**GPU faults.** On a crowded GPU, PhysX can fail to launch its kernels (`PhysX error: GPU convexCoreConvexNphase_Kernel fail
to launch`, `prepareLostFoundPairs`, `updateFrictionPatches`) or CUDA can fail to allocate, and PhysX steps on without
them, and a run that logged them can end elsewhere (a PegInHole replay with 237 such errors failed). So the tooling knows the pattern (`rcb_ambench.GPU_FAULT`; not the errors a
trajectory can cause itself, such as non-finite forces), and a replay whose output shows any is no result: both graders
run it once more, then report an infrastructure error (`replay_gpu_fault`), never the agent's 0 or 1. The standard
service's own output (`server.log`; the render worker logs to `render_worker.log`) is counted too (`live_gpu_faults`): a
live episode with any GPU fault is an infrastructure error (Grading).

**PhysX itself (PullLever).** One task stays non-reproducible with all five (its reference rows succeed at step 899 in
every replay but end in different states, no GPU fault): tracing PullLever's replays step by step, the
states and the controller's outputs are identical up to the step where the gripper first touches the lever, and that step
resolves the contact differently in different processes (the lever moves or not); `CUDA_LAUNCH_BLOCKING=1`, a fixed
`PYTHONHASHSEED` and PhysX's enhanced determinism do not change that. PullLever is therefore standard only (above).

Only a process's first episode is guaranteed bit-identical; later resets in the same process need not be. The hashes are
those of this GPU model; another GPU model may differ in the last bits (BUILD_ONLY, "Check a build").

## Grading
- **Privileged**: `tests/grade.py` replays `/app/output/trajectory.npz` twice, each in a fresh process (`rcb_ambench.py
  replay`); success = AM-Bench's check held in both (`deterministic`: the outcome repeats) and the rebuilt start matches
  `initial_sha`. The end states' hashes are reported (`state_identical`) but do not decide: PROTOCOL §4 recommends
  matching final-state hashes, and the rare race above breaks them without changing an outcome; the grading kind is the
  task's to declare (PROTOCOL §2, within H.4), and this is AM-Bench's (RoboDojo's live-graded tasks report the same two
  fields). The verdict is written first; then a third
  process films the rows (`/logs/verifier/replay.mp4`). An unreadable deliverable is `bad_trajectory`, another task's
  file `wrong_task` (the agent's 0); so is a row whose quaternion has zero or non-finite length (`bad_quaternion_rows`,
  checked when the file is read; the replay CLI also reports a row it refuses as `bad_trajectory`, a verdict, never a
  replay without a result); a replay without a result, a replay time-out, a replay with GPU faults
  (`replay_gpu_fault`, above) or `instance_ok = 0` is `grader_error = infra_error = 1`; a replay process that ends
  without a result or with GPU faults is run once more. Each process has max(1800 s, 1500 s + runnable rows / 4);
  `[verifier] timeout_sec` = four of those (7800-13200 s by episode length).
- **Standard**: graded by the **live episode**, with no grading replay, the same rule for all nine tasks: success =
  `live_success`, AM-Bench's check as the service ran it after every control step (no end-of-episode hold: AM-Bench has
  none). The service dumps the episode when the collect hook signals it and exits; the hook
  (`environment/sim/finalize.sh`) writes `final.json` from `episode.json` (`graded_by` "live", `replays` 0), then films
  the rows once (`rcb_ambench.py film`: a fresh process with the render worker, `replay.mp4`) as the video only: nothing
  of the film is compared, it is not run again, its failure or its time limit (`RCB_FILM_LIMIT_S` 1800 s) costs the
  video. The live service does not film: rendering inside the physics process makes AM-Bench's GPU physics
  timing-dependent (Determinism), and its cameras are drawn by the render worker only for the agent's own frames. No
  verdict on the agent (`infra_error`): a missing, unreadable or unfinalized `final.json`, no `episode.json`, a give-up
  after crashes between calls, the episode never ending, GPU faults in the live episode's physics (`live_gpu_faults` >
  0, counted in the service's output from its marker before `EP.begin` to the end of that start, so a start that died
  while building the scene and was restarted does not count; this can cost a retry), and the start check: before it
  serves, the service compares the rebuilt scene's state hash with `instance.json`'s `initial_sha` (`instance_matches`)
  and gives up as infra (`instance_mismatch`) on a mismatch. A crash inside the agent's calls and a simulator error
  raised by them stay its 0. The trajectory is what ran (`hold_pad_rows` = 0). The collect hook has 4800 s; the `main`
  kill hook (`kill -9 -1`) runs before the sim's (PROTOCOL H.4).
  Re-scoring a trial recorded before live grading (two replays and a film decided then) by its live episode:
  `final.json` `success` (merged from episode.json), `infra_error` only for a missing live record, a give-up with
  `infra_error`, or `live_gpu_faults` > 0; `replay_error`, `replay_gpu_faults`, `gpu_lost` and `instance_mismatch` found
  by a replay are not the live episode's.
- Both verifiers run with `network_mode = "no-network"`; every web asset the scenes load is in the image (BUILD_ONLY,
  Data).

## Validation (Harbor, RTX 4090 shared with other users' Isaac jobs)
Oracle 17/17 reward 1, `infra_error` 0 (success at the steps of the task table; two privileged pairs ended in different
states while both replays succeeded: the race of Determinism). Privileged `nop`: 8/8 reward 0 (`missing_trajectory`,
no Isaac process started). Standard `nop`: 9/9 reward 0 (`time_up`, `infra_error` 0). Two privileged trials side by side
on a shared card can run a film out of GPU memory; the films never decide. Conformance: 164 PASS, 0 FAIL (Standard mode,
below).

## Standard mode (eai-standard/2.2)
- **Action**: `ee_pose` (8: AM-Bench's own action) rows `dt` apart (a multiple of 1/120 s, at most 0.5 s), `hold` (each row
  exactly as given) or `linear` (positions linear, orientation slerp, gripper linear); no `joint_position` (the arm alone
  is not AM-Bench's action space: the controller moves the airframe too). `ci_checks/check-standard-protocol.py` tests the
  service's first action type (it assumed `joint_position`).
- **Cameras**: `ee_camera` (on ee_link) and `base_camera` (on base_link), 384×384 RGB + z-depth, `mount.type: link`; drawn by
  the render worker (rcb_ambench.Renderer) in the same `sim` sidecar.
- **Proprio** (45 columns): joint_pos / joint_vel (the arm's four joints, the two fingers), tcp_pose (ee_link), gripper_opening,
  gripper_cmd, joint_effort (the arm's four drives), base_pose / base_vel (the airframe), ee_cmd (the target in force).
- **Kinematics**: frame `base` (the airframe), world with `base_pose` (`base_pose_proprio` names the columns); FK of the
  chain base_link → arm → ee_link, damped-least-squares IK of the arm alone.
- **Robot spec**: the limits PhysX enforces. AM-Bench's asset gives three arm joints (link2/link3 pitch, link4 roll) ±10 rad,
  more than a turn each way and no joint stop an arm meets: they are reported as `continuous` (`position_limits: null`)
  with the asset's range in `note` (the conformance check reads three equal ranges beyond ±2π as placeholders).
- **Conformance** (`ci_checks/check-standard-protocol.py --launch`, PressButton): 164 PASS, 0 FAIL; the sidecar peaks at
  4.6 GB of GPU memory (PhysX buffers, above).
- **Episode**: one, no reset; AM-Bench's own time-out stays (the task's episode length; reason `episode_timeout`); simulated
  time advances only with the agent's calls; the wall clock (3600 s) is the budget.
- **Crash recovery**: resume class `approx` for every task: the resumed service replays
  the journal to a TCP about 1e-6 m from its checkpoint (the race of Determinism), which `exact` would make
  `resume_failed`. `approx` records the deviation (`resume_state_mismatch`, `resume_max_tcp_dev_m`) and ends the episode
  only beyond `RCB_RESUME_MAX_DEV_M` (5 cm); the verdict is the resumed live episode's. Kill test (PushSlider, kill -9
  during the fifth call): resumed at control step 480, the oracle carried on, success at 1353, `infra_error` 0.

## Time budget
3600 s for every task of both modes (each task's `[agent] timeout_sec`), stated in each instruction's closing `## Time limit` section. Every Python
process pays ~2-6 min of Isaac Sim launch and scene build (the upper end with other Isaac jobs on the GPU); stepping runs
at about 9-15 control steps/s.

## Declarations
- **Tooling: thin wrappers only.** The environment's own action, its state, its cameras, recording and replay. Task-level
  skills are never added.
- **World-frame information.** The privileged instructions give the full scene (the reset distributions and the frozen
  instance's state through the tooling). Standard texts give no position of anything (sizes and layout only); NDT's
  inspection point, which nothing in the scene marks, is given as goal geometry.
- **Pointers to the reference solution.** The reference rows come from AM-Bench's public scripted experts; the image has
  none and the agent's egress cannot reach GitHub. `instance.json` names no expert.
- **Upstream data.** Thirteen of AM-Bench's USDs load files from NVIDIA's asset buckets by URL, and NDT's scene is an Isaac
  sample warehouse: the image holds every file (2269, ~0.95 GB, sha256-checked) and `images/ambench/localize_assets.py`
  rewrites the URLs to them.
- **AM-Bench's controller sees the scene.** For some tasks the IK caps the airframe's position using object poses (e.g.
  CabinetPickPlace's cabinet): part of the environment in both modes; the agent never receives those poses.

## Screening

A base whose every mode a screening run solved (a graded success within the task's time limit; logs of solves by runs
other than GPT-6 Luna checked for shortcuts and for access to tests, solutions or graders), and every base GPT-6 Luna
(`codex-gpt6_luna-xhigh`) solved in some mode, is left out of the core set (`docs/core_set.toml`); its tasks keep their
names. Luna solved 8 of the 9 bases in every mode they ship and `ambench-peg-in-hole-fahexa-i00` in privileged mode
(standard unverified: only Luna attempted it, and failed), so no AM-Bench task is in the core set.
