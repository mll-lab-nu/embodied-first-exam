# AM-Bench

## Overview
[AM-Bench](https://github.com/ambench/ambench) (Wang et al., 2026) on Isaac Lab @ `f4aa17f` / Isaac Sim 5.1.0: aerial
manipulation. The robot is AM-Bench's FA-Hexa, a fully actuated hexarotor (six tilted rotors: it can hold any attitude
while hovering) carrying a 4-joint arm (three pitch joints and a roll joint) with a two-finger gripper, driven by
AM-Bench's own whole-body controller (floating-base inverse kinematics with Pyroki, a PID for the airframe).
`simulator = "ambench"`, `robot = "ambench-fahexa"`.

Nine of AM-Bench's twelve tasks, one frozen instance each (seed 0): eight in both modes,
`ambench-<task>-fahexa-i00-privileged` and `-standard`, and PullLever in standard mode only: 17 task directories,
`oracle = "full"`.

```bash
harbor run -d embodied-first-exam@all -p tasks/ambench -a codex -m <model>
```

**Before you run.**
- **Licence.** The simulator image contains NVIDIA Isaac Sim 5.1 / Omniverse Kit, which NVIDIA licenses for use and not
  for redistribution, so it is not on a public registry: the first run builds it on your machine. That build accepts
  the NVIDIA Isaac Sim / Omniverse licence agreement and NVIDIA's terms for the Isaac Sim wheels on pypi.nvidia.com and
  for the files of NVIDIA's public asset bucket that the image bakes in (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES` and
  `ACCEPT_EULA=Y`). No account, login or token is needed.
- **Host.** Linux x86_64, Docker with BuildKit (the `buildx` plugin) and the NVIDIA Container Toolkit, one RTX-class
  NVIDIA GPU (Isaac renders with RTX even headless) with a driver Isaac Sim 5.1 supports (checked: 580.159 on an RTX
  4090). `gpu_types` lists the verified models: RTX 4090, L40 and L40S, and for the standard tasks also the RTX PRO 6000
  Blackwell. Other RTX-class GPUs are not verified (the end-state hashes are per GPU model).
- **Disk.** About 60 GB free for the first build (the image is about 22 GB, plus BuildKit's cache while it builds).
- **First run.** Harbor builds the simulator image from public sources only (Docker Hub `nvidia/cuda`,
  snapshot.ubuntu.com, github.com, pypi.org, download.pytorch.org, pypi.nvidia.com, NVIDIA's public asset bucket on
  S3), about 25 min on a fast link, once per machine: every later AM-Bench task reuses its layers. The tasks allow
  90 min for the build (`[environment] build_timeout_sec`); on a slow link raise it with
  `--environment-build-timeout-multiplier`. Organization members who can read `ghcr.io/mll-lab-nu/efe-private` pull the
  prebuilt layers instead (compose `cache_from`); without that access the build prints a warning that it cannot read
  the cache image and goes on building. To build ahead of a batch:
  `docker build --target ambench-base tasks/ambench/ambench-press-button-fahexa-i00-privileged/environment`.
- **Time.** 3600 s for every task of both modes (`[agent] timeout_sec`). Every Python process pays about 2 to 6 min of
  Isaac Sim launch and scene build; stepping runs at about 9 to 15 control steps/s.

## Upstream and license
[AM-Bench](https://github.com/ambench/ambench) at commit `60bf5b73041df4eab571f7d9f0a297aeecbf2e0d`, Apache License
2.0 (third-party notices in its `THIRD_PARTY_NOTICES.md`). Isaac Lab at `f4aa17f` (BSD-3-Clause) on NVIDIA Isaac Sim
5.1.0, which may be used but not redistributed: the image is built locally (`images/ambench/BUILD_ONLY` has the
licences, the host and the checks of a build). Thirteen of AM-Bench's USDs load files from NVIDIA's asset buckets by
URL, and NDT's scene is an Isaac sample warehouse: the image holds every file (2269, about 0.95 GB, sha256-checked),
under NVIDIA's terms. No non-commercial terms apply to AM-Bench itself.

## Changes from upstream
- **RotateValve: the unwrapped angle.** `base_to_shaft` has no limits, and omni.physx creates a revolute joint without
  limits as a wrapped joint, whose position PhysX reports in [-π, π]. AM-Bench's check `joint_pos >= 17π/18` on that
  value also passes a counter-clockwise turn of 190° (reported as +170°), while the task is a clockwise turn of 170°.
  The tooling, the same file in the agent's environment and in the grader, replaces RotateValve's `_get_success` with
  the same comparison on the unwrapped angle: the sum of the joint's per-step changes since the reset, each wrapped
  into [-π, π) (the joint's velocity limit, 5 rad/s, moves it at most 0.042 rad per 1/120 s step, so the sum is exact).
  For a clockwise turn below π the two readings agree. The threshold, direction and timing are upstream's.
- **Every other success check is AM-Bench's own** `_get_success` (its `terminated` signal), unchanged. Weak checks are
  kept as AM-Bench wrote them: CabinetPickPlace only tests the can's height and speed (a can still held at that height
  passes).
- **Changes to the environment's behaviour**, each measured, none changing a task: the controller's IK solve, every
  phase of a control step and every call on PhysX's tensor views are synchronized with the GPU; the propellers'
  animation is switched off, so they stand still in the images; the onboard cameras are drawn by a render worker,
  never in the physics process; PullLever's colour randomization (`randomize_visual_color`, a Replicator API this Isaac
  Sim lacks) is dropped. Isaac Lab's PhysX GPU buffers are sized for one environment instead of thousands (a
  camera-free process takes 1.2 GB of GPU memory instead of 3.2 GB); all eight frozen references replay to their frozen
  end states with them.
- **Experts removed.** The Dockerfile copies AM-Bench without `policies/scripted/` (the scripted experts),
  `ambench_learn`, its scripts, documentation and git history, blanks the task registrations'
  `scripted_policy_entry_point`, and fails if anything left names them.
- **Assets localized.** `images/ambench/localize_assets.py` rewrites the scenes' asset URLs to the files in the image.
- **Added.** Frozen instances, the tooling `rcb_ambench.py`, and the standard-mode service.

## Interface
- **Action.** AM-Bench's absolute end-effector pose action of the `Abs-PID` profile, 8 numbers per control step: the
  ee_link target position (x, y, z, m, relative to the environment's origin), its orientation (qw, qx, qy, qz; the
  command frame is the ee_link frame) and the gripper (-1 closed to +1 open). The tooling clips only the gripper to
  [-1, 1] and refuses a zero quaternion; it does not normalise the quaternion. 120 Hz control, one physics step of
  1/120 s per action.
- **Instance.** AM-Bench's seeded reset with seed 0 (`cfg.seed = 0`, `env.reset(seed=0)`). `instance.json` holds the
  environment id, the seed and `initial_sha` (the sha256 of every articulation's and rigid object's root state, joint
  positions and velocities after the reset); every replay rebuilds the start and checks it.
- **Privileged mode.** `rcb_ambench.Session` (frozen instance, reset, step, `hold_action`, status, `actions`, replay,
  `save_trajectory`), the privileged state (`state()`, `objects()`, `proprio()`), the two onboard cameras on request
  (`Session(cameras=True, depth=True)`) and `env` (the Isaac Lab environment itself). No motion primitives.
  Deliverable: `/app/output/trajectory.npz`.
- **End state.** Isaac Lab resets an environment whose episode ended inside that very step; the tooling hashes the state
  just before that reset and keeps what the robot sensed then, so observations after the end show the end.

### Standard mode
The standard service (`eai-standard/3.0`) is `embodied_first_exam/benchmarks/ambench/sim/server.py`:
- **Action**: `ee_pose` (8: AM-Bench's own action), rows `dt` apart (a multiple of 1/120 s, at most 0.5 s), `hold` or
  `linear` (positions linear, orientation slerp, gripper linear). There is no `joint_position`: the arm alone is not
  AM-Bench's action space, since the controller moves the airframe too.
- **Cameras**: `ee_camera` (on ee_link) and `base_camera` (on base_link), 384 × 384 RGB + z-depth, `mount.type: link`;
  drawn by the render worker (`rcb_ambench.Renderer`) in the same `sim` sidecar.
- **Proprio** (45 columns): joint_pos / joint_vel (the arm's four joints, the two fingers), tcp_pose (ee_link),
  gripper_opening, gripper_cmd, joint_effort (the arm's four drives), base_pose / base_vel (the airframe), ee_cmd (the
  target in force).
- **Kinematics**: frame `base` (the airframe), world with `base_pose`; FK of the chain base_link → arm → ee_link and
  damped-least-squares IK of the arm alone (a stateless numpy model, checked against the simulator's link poses to
  2e-7 m).
- **Robot spec**: the limits PhysX enforces. AM-Bench's asset gives three arm joints (link2/link3 pitch, link4 roll)
  ±10 rad, more than a turn each way: they are reported as `continuous` (`position_limits: null`) with the asset's range
  in `note`.
- **Episode**: one, no reset. AM-Bench's own time-out stays (the task's episode length); simulated time advances only
  with the agent's calls; the wall clock is the budget.
- **Crash recovery**: resume class `approx` for every task: a resumed service replays the journal to a TCP about
  1e-6 m from its checkpoint (the race under Determinism). `approx` records the deviation and ends the episode only
  beyond `RCB_RESUME_MAX_DEV_M` (5 cm).

### World-frame information
The privileged instructions give the full scene (the reset distributions and the frozen instance's state through the
tooling). Standard texts give no position of anything (sizes and layout only); NDT's inspection point, which nothing in
the scene marks, is given as goal geometry. For some tasks AM-Bench's controller caps the airframe's position using
object poses (e.g. CabinetPickPlace's cabinet): part of the environment in both modes; the agent never receives those
poses.

## Grading
- **Privileged: up to three replays.** `tests/grade.py` replays `/app/output/trajectory.npz` up to 3 times
  (`[metadata] replays`), each in a fresh process (`rcb_ambench.py replay`), and stops at the first success. Success =
  AM-Bench's check held in a replay whose rebuilt start matches `initial_sha`. In a replay the episode ends at the first
  step where the check holds, or at AM-Bench's time-out (control step 120 × episode length − 1), a failure. An
  unreadable deliverable is `bad_trajectory`, another task's file `wrong_task`, and so is a row whose quaternion has
  zero or non-finite length (the agent's 0). A replay without a result, a replay time-out, a replay with GPU faults
  (`replay_gpu_fault`) or `instance_ok = 0` is `grader_error = infra_error = 1`; a replay process that ends without a
  result or with GPU faults is run once more. Each process has max(1800 s, 1500 s + runnable rows / 4);
  `[verifier] timeout_sec` is five of those. The verdict is written first; then another process films the rows
  (`/logs/verifier/replay.mp4`).
- **Standard: the live episode, agent-ended.** The agent never sees a success, and a success never ends the episode
  (`rcb_ambench.py` `hide_success`: AM-Bench's `terminated` is recorded and suppressed). The episode ends at
  `POST /finish`, when the agent's time runs out, at AM-Bench's time-out (reason `step_limit`, judged on the state
  instead of a failure), or on a simulator error (a 0). PressButton is judged as an event (the button springs back: a
  press seen during the episode counts); NDT holds the robot still for up to 1 s at the end so a hold that is completing
  can finish; every other task is judged on its end state. The hook (`environment/sim/finalize.sh`) writes `final.json`
  from `episode.json` (`graded_by` "live", `replays` 0), then films the rows once (`rcb_ambench.py film`) as the video
  only. GPU PhysX does not replay every episode bit for bit, so the film is compared with the live record, for the
  video only (`video_matches_live`, `video_outcome_matches_live`); a film with another outcome is dropped. The verdict
  is on disk before the film and never changes (`ci_checks/benchmarks/ambench/advisory-finalize-video.py` tests this).
  No verdict on the agent (`infra_error`): a missing, unreadable or unfinalized `final.json`, no `episode.json`, a
  give-up after crashes between calls, the episode never ending, GPU faults in the live episode's physics
  (`live_gpu_faults` > 0), and a rebuilt scene whose state hash is not `initial_sha` (`instance_mismatch`). The collect
  hook has 4800 s; the `main` kill hook (`kill -9 -1`) runs before the sim's.
- Both verifiers run with `network_mode = "no-network"`; every web asset the scenes load is in the image.

### Determinism
Isaac Sim 5.1, GPU PhysX, RTX 4090. A fresh process replays a frozen instance's rows to the same end state; every
frozen instance was replayed at least twice to identical end states. The tooling's five fixes make that hold:
1. **SYNC (IK).** AM-Bench's controller solves its floating-base IK on the CPU (Pyroki / jaxls) from GPU tensors and
   hands the result back to the GPU every step; a device synchronization brackets that solve.
2. **SYNC (phases).** Every phase of a control step is bracketed by a synchronization, at no measurable cost.
3. **PROPELLERS.** AM-Bench's propeller animation (orientations written into the robot's USD prims every step) is off.
4. **CAMERAS.** Rendering inside the physics process makes runs part, so the onboard cameras are drawn by a second,
   render-only Isaac process from the physics state (`Renderer`): the physics process is the same with or without
   cameras.
5. **SYNC (views).** Every `get_*` / `set_*` / `apply_*` call on PhysX's tensor views is bracketed by a synchronization
   too (`sync_views`).

What is left: with other jobs on the GPU, about 1 in 8 replays still ends one step later or in another end state while
succeeding; none changed an outcome. So the graders decide on the outcome and report the hashes. On a crowded GPU,
PhysX can fail to launch its kernels or CUDA can fail to allocate, and PhysX steps on without them; the tooling knows
the pattern (`rcb_ambench.GPU_FAULT`), and a run that shows it is no result (an infrastructure error, above).
PullLever stays non-reproducible with all five fixes: its states and controller outputs are identical up to the step
where the gripper first touches the lever, and that step resolves the contact differently in different processes.
Only a process's first episode is guaranteed bit-identical; later resets in the same process need not be. The hashes
are those of this GPU model.

## Tasks
| Family | AM-Bench environment (`…-Am-FAHexa-Abs-PID-Direct-v0`) | Task | Episode | Reference: success at control step (end state) |
|---|---|---|---|---|
| `press_button_fahexa` | `PressButton` | press a spring-loaded button on a (tilted) wall by ≥ 4 mm | 20 s | 1027 (`fcd4de9b60a77009`) |
| `push_slider_fahexa` | `PushSlider` | push a knob 0.95 m along a rail on a wall | 26 s | 1353 (`01a85d356fead490`) |
| `rotate_valve_fahexa` | `RotateValve` | turn a valve wheel on a wall ≥ 170° clockwise | 20 s | 1002 (`1b976104a88384d6`) |
| `open_door_fahexa` | `OpenDoor` | push a hinged door open by > 20° | 15 s | 395 (`f778f7c7a8593239`) |
| `peg_in_hole_fahexa` | `PegInHole` | insert the held peg into a socket on a (tilted) wall | 20 s | 1041 (`88054491e8410ae5`) |
| `ndt_fahexa` | `NDT` | hold the end effector at an inspection point high on a warehouse wall for 100 steps | 20 s | 1212 (`bd8da2528c86e757`) |
| `lemon_harvesting_fahexa` | `LemonHarvesting` | pick the lemon off its stem and drop it into the tote | 30 s | 1739 (`a0426217ca460de2`) |
| `cabinet_pick_place_fahexa` | `CabinetPickPlace` | lift a can onto the top of the cabinet | 60 s | 2752 (`c8c72a8b2031348e`) |
| `pull_lever_fahexa` (standard only) | `PullLever` | pull a spring-loaded lever on a (tilted) wall up by > 40° | 20 s | 899 (no single end state) |

- **PullLever, standard only.** GPU PhysX does not replay it bit for bit (Determinism): its reference rows succeed in
  every fresh replay, at control step 899, but end in three different states, so an open-loop trajectory of it cannot
  be graded by its end state. It ships in standard mode only and is graded by its live episode (its `instance.json`
  says `"determinism": "verdict"`).
- **Not in this set.** FrameAssembly, WipeWindow and TossBall: AM-Bench's scripted experts did not succeed on the
  seed-0 instances, so there is no reference solution. AM-Bench's other robot and controller profiles (the quadrotor,
  the omnidirectional hexa, the under-actuated hexa, the end-effector-only robot; L1 and MPC controllers) are variants
  of the same tasks.
- **Reference solutions.** AM-Bench's scripted expert for the task (`policies/scripted/<task>.py`,
  `inject_noise=False`), run in closed loop on the frozen instance and recorded as the rows the tooling executed,
  followed by 2 s of holding its last command (`solution/oracle_actions.npy`). The privileged oracle replays them
  through the agent's own tooling and hands in all of them; the standard oracle streams them as one-second `ee_pose`
  chunks. The expert reads the simulator's state between steps, so two fresh-process replays with the grader's CLI
  must both succeed and end in the same state before an instance is frozen. The end-state hashes in the table
  (`state_sha`, its first 16 hex digits) are what a camera-free fresh-process replay of the reference ends in on an
  RTX 4090: the check of a build (`images/ambench/BUILD_ONLY`, "Check a build") compares with them.

## Others
- **Tooling: thin wrappers only.** The environment's own action, its state, its cameras, recording and replay. No
  task-level skills.
- **Egress.** AM-Bench is public on GitHub and not on PyPI; the agent's egress is the model APIs and the package
  registries (`network_mode = "allowlist"`), so the experts cannot be fetched during a trial. `instance.json` names no
  expert.
