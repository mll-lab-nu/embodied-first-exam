# Panda Dynamic Scenes

## Overview

Panda Dynamic Scenes is MLL Lab's benchmark of 25 continuous, multi-stage dynamic manipulation tasks for stock Franka
Panda (FER) arms. It runs on ManiSkill 3.0.1 / SAPIEN 3.0.3, with rigid-body CPU PhysX at 1000 Hz and a 100 Hz control
step. In every task something moves by itself (a tossed ball, a sliding puck, a conveyor, a pendulum, a spring gate, a
moving cart or ramp). The robot must catch, strike, carry, hand over, flip or release at the right moment, several times
in one episode. No language.

| | |
|---|---|
| simulator | `maniskill`: ManiSkill 3.0.1, SAPIEN 3.0.3, CPU PhysX at 1000 Hz (10 physics steps per 10 ms control step) |
| robots | `franka-panda` (S01-S12, one arm) · `franka-panda-bimanual` (D01-D13, two arms); each arm has its standard hand and, in most tasks, a rigid task tool on it (a plate, a cup, a paddle, a scoop, a fork, a receiver, a pusher) |
| tasks | 25 families, one frozen instance each (i00): 25 privileged, 25 standard and 19 realtime tasks, 69 task directories |
| score | binary: every phase of the task completed in order, with no failure |
| image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` (`images/pandadyn/`) |
| oracle | `full` in every mode: the benchmark's recorded reference rows for the frozen instance |

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator and its full state | unlimited | its `trajectory.npz`, replayed once in a fresh process |
| standard | two static cameras, the arms' proprioception, the world conventions and the task's goal geometry; the world is frozen between calls | 3 | the last episode, as it ran (live; nothing replayed) |
| realtime | the same as standard on a clock that does not stop (one control step every 10 ms × S of wall time) | 3 | the last episode, as it ran (live; nothing replayed) |

## Upstream and license

The benchmark and its environment package are MLL Lab's. This repository's copy of the package is
`images/pandadyn/panda_dynamics/` (copied by `images/pandadyn/sync_env.py`), released with this repository under its MIT
License. The benchmark's validation tooling, its reference controllers and its instance bank are not published.

Components in the image: ManiSkill 3 and its Panda model (Apache License 2.0), SAPIEN (MIT), Ruckig community version
(MIT), PyTorch (BSD 3-Clause). Every component is redistributable, and the image is public. No non-commercial terms
apply.

## Changes from upstream

- **Image without the solution tooling.** The image holds the environment package only. Its command-line front end,
  which drives the benchmark's validation tooling, is left out, and comments that named that tooling are reworded
  (`images/pandadyn/sync_env.py` refuses a copy with such text).
- **Frozen instances.** The benchmark keeps a bank of verified instances (20 nominal + 10 hard per task), each with a
  recorded rollout of its reference controller and an independent action replay. For each task the frozen instance is
  the lowest-seed nominal instance of the bank that passes three checks in this image:
  1. the instance rebuilds from its parameters and seed;
  2. the recorded rollout, replayed here, reproduces the physical state it recorded after every control step, bit for
     bit (joint positions and velocities of every arm, every object's pose and velocities, every fixture's joint);
  3. the rollout's rows succeed through the tooling, and two `replay`s in fresh processes end in the same state hash.

  All 25 tasks passed with their first candidate: seed 0, except D04 (seed 1, the lowest nominal seed its bank holds).
  `instance.json` holds the task, the resolved parameters, the seed and the hash of the rebuilt start (`initial_sha`),
  and names no rollout.
- **S06 BLAS pin.** S06's arm start comes from an IK fallback (scipy `least_squares`) whose last bits follow the BLAS
  kernel OpenBLAS picks for the CPU. Its containers pin the kernel (`OPENBLAS_CORETYPE=Haswell`) and the instance is
  frozen with it.
- **Added.** The standard and realtime modes (a simulator service with cameras and proprioception), the 3-reset budget
  and agent-ended episodes.

## Interface

**Privileged.** `rcb_pandadyn.py` (`from rcb_pandadyn import Session`): `Session(instance=...)` builds the scene and
resets it to the frozen instance; `step(row)` (one 10 ms control step), `reset()` (exact), `snapshot()` / `restore()`
(the environment's own exact checkpoints), `state()` / `objects()` / `fixtures()` / `params()` (privileged state),
`proprio()`, `fk()` / `ik()` (the arm's own Pinocchio model), `actions()`, `replay()`, `save_trajectory()`,
`render_frame()` / `render_depth()` / `camera_info()` / `render_video()`, `status()`, `state_sha()`. These are thin
wrappers only: joint targets, kinematics and state. No task-level skill (catch, strike, carry) is in the tooling.

**Action.** `joint_position`, 8 values per arm: 7 joint-position targets and the total gripper aperture (the
environment's own action), clipped to the limits and executed as float64. One row is one 10 ms control step.

**Standard and realtime** (`eai-standard/3.0`). The robot is a service in the `sim` sidecar (`environment/sim/server.py`,
an adapter on `rcb_pandadyn.Session` and the shared service layer `rcb_service.py`; realtime adds `rcb_realtime.py`'s
clock), reached through `rcb_client.py`. Rows are sent in chunks `dt` apart (a whole multiple of 10 ms, `hold` or
`linear`, at most 10 s per chunk; realtime chunks can be planned at a future step with `at`).

- Observation: cameras `overview` and `closeup` (static, 640×480, RGB, z-depth on request) with their calibration in
  `/spec`; per arm: joints and fingers, hand TCP pose, velocities, aperture, motor torques, tool pose and the targets in
  force (`spec["proprio_groups"]`).
- Clock: in standard mode the simulated clock advances only with the agent's calls, so the world is frozen between
  them. In realtime mode an episode starts paused, and from the first `submit` one control step runs every 10 ms × S of
  wall time (S per family in Tasks); when the planned rows run out, the last targets are held.
- Episode: it ends at the agent's `/finish`, at the first failure, at the task's horizon (25 s of simulated time; 32 s
  for S12, 35 s for S03 and D07), at the environment's cap of 4,500 control steps, or at the end of the session.
  Completing the task neither ends the episode nor is shown to the agent.

**World-frame information.** Both modes give the world conventions (z up, the table top at z = 0, quaternions wxyz),
the robot (arm bases, tools and their mounts, joint, servo and safety limits) and the task's own goal geometry that is
not a physical object: waypoints and target points of the phase checks, in world coordinates. Nothing in the scene marks
them. Standard mode never gives where objects or fixtures are, their physical parameters (mass, friction, restitution,
launch velocities), the seed, or goal values derived from the seeded variation; the privileged instruction and tooling
give all of them. Contact forces stay private; the robot's own proprioception (motor torques, joint and TCP motion) is
what the safety limits are judged on.

### Reset budget

3 resets in standard and realtime mode (`RCB_RESET_BUDGET`, default 3 in each task's `environment/docker-compose.yaml`;
0 gives one episode). Every reset restores the same frozen start; only the last episode is graded. The budget allows
one or two scouting episodes and a real attempt. The standard reference solution (`solution/oracle_replay.py`) uses it
the same way: three one-second scouting episodes, then the reference rows.

## Grading

Every task is a sequence of phases, each with its own physical condition (a catch, a hold for a stated time, a
crossing, a containment, a release). The conditions are checked after every 1 ms physics step and completed strictly
in order. A task fails at its first failure event: its own (a ball off a rimless plate, a spill, a dropped load), a
forbidden contact, a violation of the Panda's safety limits (checked every 1 ms, measured and in the servo's
reference), an object leaving the workspace, or the task's horizon. Each task README gives the phases, the failures and
the numbers.

- **Privileged** (`tests/grade.py`): the trajectory (`task`, `actions` with 8 values per arm, at most 4,500 rows) is
  replayed open-loop in one fresh process from the verifier's own copy of the instance. The replay stops at the first
  control step where the task succeeds or fails. Success means it succeeded there and rebuilt the frozen start. A
  simulator error on the agent's rows scores 0. A replay that gives no result or exceeds its time limit (300 s plus 0.1 s
  per row) is an infrastructure error.
- **Standard and realtime** (the shared `tests/grade.py` on the service's verdict): the live episode is graded; nothing
  is replayed. Judgement is by events: once every phase is done in order with no failure, the episode is a success,
  and a later failure does not take it back. A failure, or the horizon, before that scores 0. The frozen start is
  checked when the first episode begins and after every reset; a mismatch is an infrastructure error.

### Determinism

CPU PhysX with `enable_enhanced_determinism`, one simulated scene per process, one thread for every numeric library
(`OMP_NUM_THREADS=1`, set in the image), and the scene rebuilt on every reset. Measured in
`ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`:

- For 24 of the 25 frozen instances, the benchmark's recorded rollout reproduces the recorded physical state after
  every control step bit for bit. S06 is frozen with the pinned BLAS kernel; its start differs from the bank's recording
  in the last bits, and its rows succeed. The oracle run and two fresh-process replays end in the same state hash
  (25/25).
- A seed reset alone rebuilds the recorded start. Rendering, the render backend and the cameras do not change the
  physics (same hashes).
- A trajectory and its grading replay always run on one host, so no verdict depends on a host's last bits. A CPU that
  rebuilt a start differently is caught by the `initial_sha` check (an infrastructure error, not a verdict).
- In standard mode the live episode equals a fresh-process replay of its rows.

The tasks are sensitive to the last bits of the actions: the oracle rows rounded to float32 (a relative change of
about 1e-7) failed on some instances, and the same rows do not succeed at a 2000 Hz physics step. Grading therefore
never accepts an approximate replay, and the standard reference solution sends its rows as float64. The shipped
client's `submit` rounds to float32; this costs an agent nothing, since its own episode is what is graded.

## Tasks

Task directories: `tasks/pandadyn/pandadyn-<code>-<name>-i00-{privileged,standard,realtime}`. The six static families
(nothing in them moves by itself: D05, D08, D11, D12, D13, S06) have no realtime task. Every family
allows its frozen instance's seed only. S01's designated channel, S03's designated rail and S08's selected branch are
drawn per seed; each instruction names this instance's choice (by direction, not by coordinates), and S03's rail is
coloured green.

| Code | Task | Arms | Phases | Seed | Reference rows | Horizon | S (realtime) |
|---|---|---|---|---|---|---|---|
| D01 | Reciprocal two-cup air relay (`ReciprocalCupRelay`) | 2 | 6 | 0 | 1,560 | 25 s | 3 |
| D02 | Strike, catch and merge two balls (`StrikeCatchMerge`) | 2 | 6 | 0 | 1,755 | 25 s | 3 |
| D03 | Cooperative puck course (`CooperativePuckCourse`) | 2 | 4 | 0 | 2,278 | 25 s | 3 |
| D04 | Shared tray transport and discharge (`SharedTrayTransportDischarge`) | 2 | 5 | 1 | 560 | 25 s | 4 |
| D05 | Moving ramp relay (`MovingRampRelay`) | 2 | 6 | 0 | 2,393 | 25 s | – |
| D06 | Moving bank relay (`MovingBankRelay`) | 2 | 5 | 0 | 1,696 | 25 s | 3 |
| D07 | Spring gate switchyard (`SpringGateSwitchyard`) | 2 | 5 | 0 | 2,526 | 35 s | 3 |
| D08 | Pendulum energy relay (`PendulumEnergyRelay`) | 2 | 5 | 0 | 565 | 25 s | – |
| D09 | Lever launch, catch and reload (`LeverLaunchCatchReload`) | 2 | 6 | 0 | 1,625 | 25 s | 3 |
| D10 | Moving grasp handover (`MovingGraspHandover`) | 2 | 5 | 0 | 1,554 | 25 s | 6 |
| D11 | Moving fixture unlock (`MovingFixtureUnlock`) | 2 | 5 | 0 | 1,563 | 25 s | – |
| D12 | Reciprocal sliding transfer (`ReciprocalSlidingTransfer`) | 2 | 5 | 0 | 1,251 | 25 s | – |
| D13 | Supported cube flip relay (`SupportedCubeFlipRelay`) | 2 | 5 | 0 | 883 | 25 s | – |
| S01 | Cup catch, route pour, rebound recatch and cart delivery (`CupRouteDelivery`) | 1 | 5 | 0 | 1,910 | 25 s | 2 |
| S02 | Plate catch, transport and release (`PlateCatchTransportRelease`) | 1 | 5 | 0 | 1,118 | 25 s | 2 |
| S03 | Clear the blocker, recover and bank into the goal (`ClearGateHockey`) | 1 | 5 | 0 | 3,025 | 35 s | 2 |
| S04 | Impact release, interception and passage relay (`ImpactReleaseRelay`) | 1 | 5 | 0 | 441 | 25 s | 2 |
| S05 | Sliding receive, inertial staging and moving hand-off (`SlidingReceiveAlignDeliver`) | 1 | 5 | 0 | 1,021 | 25 s | 2 |
| S06 | Inertial cube flip, chute run and pocket recovery (`CubeFlipRouteRecover`) | 1 | 4 | 0 | 1,295 | 25 s | – |
| S07 | Conveyor pick, carriage load, braking and dock unload (`ConveyorLoadBrakeUnload`) | 1 | 5 | 0 | 1,303 | 25 s | 4 |
| S08 | Load a coasting cart, throw the switch, recover the part (`LoadSwitchRecover`) | 1 | 5 | 0 | 2,189 | 25 s | 6 |
| S09 | Catch, self-toss, recatch and deliver (`TossRecatchDelivery`) | 1 | 5 | 0 | 1,241 | 25 s | 2 |
| S10 | Swinging load transit and dock (`SwingingLoadTransitDock`) | 1 | 5 | 0 | 1,456 | 25 s | 2 |
| S11 | Cylinder rescue, guide route and oriented delivery (`CylinderRescueRouteDeliver`) | 1 | 5 | 0 | 1,782 | 25 s | 3 |
| S12 | Spinning bridge puck relay and goal (`MovingBridgePuckRelay`) | 1 | 5 | 0 | 2,171 | 32 s | 3 |

The slowdown S is `RCB_SLOWDOWN` in each realtime task's `environment/docker-compose.yaml`. CPU PhysX at 1000 Hz with
two servos in Python runs slower than real time, so no family runs at S = 1. S = ceil(1.5 / RTF), from the lower of the
measured real-time factors of the realtime service with its clock flat out and of the bare physics loop.

Reference solutions: `solution/oracle_actions.npy` (privileged, run through the agent's own tooling by
`solution/oracle.py`), `solution/oracle_qpos.npy` (standard, `solution/oracle_replay.py`; realtime, planned from step
0 by `solution/oracle_plan.py`) hold the same rows, so all of them end in the same state. With no action, no task
succeeds.

## Others

- Image: `images/pandadyn/` → `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` (~2.4 GB): Python 3.11.16, ManiSkill 3.0.1,
  SAPIEN 3.0.3, torch 2.14.1 (CPU build, which reproduces the bank's physics bit for bit), Ruckig 0.12.2
  (`requirements.lock`). SAPIEN needs a Vulkan device to build a scene and render, so every container that builds one
  reserves an NVIDIA GPU (any model; its memory is capped by `x-gpu-memory-gb`). Physics runs on one CPU core.
- Some phase conditions are looser than their names: D02's redirects need only a paddle touch after a free flight;
  D04's first phase (shared support) holds from the start; D05's channel exit is a half-space test; S05's speed match is
  met by a tray held still while the platform passes; the goal crossings of D06, D07 and S12 check the paddle's contact
  only at the moment of crossing.
- S11's moving pocket rests against the side of the raised lane for about 1.5-14.3 s, which leaves 14.3-20.9 s for the
  delivery. S08's docks lie beyond its failure line (only the branch and the recovery count).
- The privileged instruction's sentence "Things move by themselves from the first control step on: the scene does not
  wait for the robot." is written for the 19 families with a realtime task only; the six others say "Nothing moves by
  itself".
