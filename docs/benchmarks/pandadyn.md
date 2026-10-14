# Panda Dynamic Scenes

Panda Dynamic Scenes (MLL Lab; this repository's copy of its environment package is `images/pandadyn/panda_dynamics/`):
25 continuous, multi-stage **dynamic** manipulation tasks for stock Franka Panda (FER) arms on ManiSkill 3.0.1 / SAPIEN
3.0.3, rigid-body CPU PhysX at 1000 Hz. In every task something moves by itself (a tossed ball, a sliding puck, a
conveyor, a pendulum, a spring gate, a moving cart or ramp), and the robot must catch, strike, carry, hand over, flip or
release at the right moment, several times in one episode. `simulator = "maniskill"`; `robot = "franka-panda"` (S01-S12,
one arm) or `"franka-panda-bimanual"` (D01-D13, two arms). Each arm has its standard hand and, in most tasks, a rigid task
tool on it (a plate, a cup, a paddle, a scoop, a fork, a receiver, a pusher).

One frozen instance per task (i00), each a privileged task `pandadyn-<code>-<name>-i00-privileged` and its standard twin
`pandadyn-<code>-<name>-i00-standard` (`eai-standard/2.2`): 50 task directories.

| Code | Task | Arms | Phases | Seed (i00) | Oracle |
|---|---|---|---|---|---|
| D01 | Reciprocal two-cup air relay (`ReciprocalCupRelay`) | 2 | 6: left_initial_catch, left_to_right_flight, right_catch, second_region, right_to_left_flight, left_catch_and_deliver | 0 | 1478 rows, 14.78 s of 25 s |
| D02 | Strike, catch and merge two balls (`StrikeCatchMerge`) | 2 | 6: first_redirect, first_catch, loaded_cup_relocation, second_redirect, second_catch, both_delivery | 0 | 1755 rows, 17.55 s of 25 s |
| D03 | Cooperative puck course (`CooperativePuckCourse`) | 2 | 4: left_first_pass, right_return_route, left_diagonal_pass, right_terminal_shot | 0 | 2261 rows, 22.61 s of 25 s |
| D04 | Shared tray transport and discharge (`SharedTrayTransportDischarge`) | 2 | 5: shared_support, transport_turn, disturbance_recovery, exit_alignment, natural_discharge | 1 | 560 rows, 5.6 s of 25 s |
| D05 | Moving ramp relay (`MovingRampRelay`) | 2 | 6: first_channel_entry, first_moving_exit, first_catch, second_channel_entry, second_moving_exit, second_catch_and_delivery | 0 | 2365 rows, 23.65 s of 25 s |
| D06 | Moving bank relay (`MovingBankRelay`) | 2 | 5: right_first_strike, left_first_rebound, right_recovery_strike, left_changed_rebound, terminal_goal | 0 | 2014 rows, 20.14 s of 25 s |
| D07 | Spring gate switchyard (`SpringGateSwitchyard`) | 2 | 5: left_gate_open, right_loop_shot, gate_reconfiguration, return_interception, final_gate_shot | 0 | 2434 rows, 24.34 s of 35 s |
| D08 | Pendulum energy relay (`PendulumEnergyRelay`) | 2 | 5: left_excitation, right_braking, right_return_impulse, left_recovery, low_energy_hold | 0 | 487 rows, 4.87 s of 25 s |
| D09 | Lever launch, catch and reload (`LeverLaunchCatchReload`) | 2 | 6: physical_loading, first_launch, right_catch, reload_and_clear, second_launch, moving_receptacle_retention | 0 | 1628 rows, 16.28 s of 25 s |
| D10 | Moving grasp handover (`MovingGraspHandover`) | 2 | 5: moving_pickup, moving_presentation, overlapping_grips, donor_release, receiver_slot_delivery | 0 | 1316 rows, 13.16 s of 25 s |
| D11 | Moving fixture unlock (`MovingFixtureUnlock`) | 2 | 5: moving_fixture_presentation, relative_pin_insertion, mechanical_latch_open, follow_and_withdraw, gravity_delivery | 0 | 1558 rows, 15.58 s of 25 s |
| D12 | Reciprocal sliding transfer (`ReciprocalSlidingTransfer`) | 2 | 5: left_inertial_slip, right_receive_and_brake, reverse_geometry, left_receive_and_brake, final_support_deposit | 0 | 1726 rows, 17.26 s of 25 s |
| D13 | Supported cube flip relay (`SupportedCubeFlipRelay`) | 2 | 5: support_presentation, first_inertial_flip, second_contact_geometry, second_inertial_flip, oriented_output | 0 | 703 rows, 7.03 s of 25 s |
| S01 | Cup catch, route pour, rebound recatch and cart delivery (`CupRouteDelivery`) | 1 | 5: incoming_catch, selected_route_entry, track_and_rebound, downstream_catch, moving_cart_delivery | 0 | 1910 rows, 19.1 s of 25 s |
| S02 | Plate catch, transport and release (`PlateCatchTransportRelease`) | 1 | 5: airborne_plate_catch, recenter, turning_transport, rolling_recovery, moving_basin_release | 0 | 1118 rows, 11.18 s of 25 s |
| S03 | Clear the blocker, recover and bank into the goal (`ClearGateHockey`) | 1 | 5: first_strike, clear_blocker, recover_deflection, second_strike, bank_and_goal | 0 | 1805 rows, 18.05 s of 25 s |
| S04 | Impact release, interception and passage relay (`ImpactReleaseRelay`) | 1 | 5: cue_strike, mechanical_unlatch, payload_interception, passage_redirection, payload_braking | 0 | 441 rows, 4.41 s of 25 s |
| S05 | Sliding receive, inertial staging and moving hand-off (`SlidingReceiveAlignDeliver`) | 1 | 5: source_to_tray, inertial_staging, transport_turn, match_receiver, support_transfer | 0 | 1021 rows, 10.21 s of 25 s |
| S06 | Inertial cube flip, chute run and pocket recovery (`CubeFlipRouteRecover`) | 1 | 4: momentum_face_flip, oriented_chute_entry, downstream_intercept, pocket_delivery | 0 | 1297 rows, 12.97 s of 25 s |
| S07 | Conveyor pick, carriage load, braking and dock unload (`ConveyorLoadBrakeUnload`) | 1 | 5: moving_acquisition, loaded_carriage_release, handle_braking, payload_regrasp, dock_deposit | 0 | 2050 rows, 20.5 s of 25 s |
| S08 | Load a coasting cart, throw the switch, recover the part (`LoadSwitchRecover`) | 1 | 5: moving_part_pickup, load_coasting_cart, physical_switch_operation, selected_branch, payload_recovery | 0 | 2189 rows, 21.89 s of 25 s |
| S09 | Catch, self-toss, recatch and deliver (`TossRecatchDelivery`) | 1 | 5: initial_catch, launch_region, self_toss, displaced_recatch, moving_receiver_delivery | 0 | 1241 rows, 12.41 s of 25 s |
| S10 | Swinging load transit and dock (`SwingingLoadTransitDock`) | 1 | 5: grasp_settle_and_damp, obstacle_transit, turn_and_brake, residual_swing_cancel, load_dock | 0 | 2107 rows, 21.07 s of 25 s |
| S11 | Cylinder rescue, guide route and oriented delivery (`CylinderRescueRouteDeliver`) | 1 | 5: rolling_interception, axial_alignment, guide_rail_traverse, exit_reception, oriented_moving_delivery | 0 | 1782 rows, 17.82 s of 25 s |
| S12 | Spinning bridge puck relay and goal (`MovingBridgePuckRelay`) | 1 | 5: incoming_strike, physical_bridge_transfer, exit_interception, second_strike, closing_gate_goal | 1 | 3074 rows, 30.74 s of 32 s |

## Instances
An instance is the benchmark's own: one task at difficulty `nominal` (the task's configuration, `common` updated by its
`nominal` overrides) and a seed, from which the task's reset draws its per-instance variation (an incoming lateral
offset, a route, a fixture phase, ...). The environment rebuilds the whole scene on every reset (`reconfigure`), so a
seed reset is exact; `instance.json` holds the task, the resolved parameters, the seed and the hash of the rebuilt start
(`initial_sha`), which every replay checks.

The benchmark keeps a bank of verified instances (20 nominal + 10 hard per task), each with a recorded rollout of its
reference controller and an independent action replay. For each task, `scripts/pandadyn/freeze.py` took the lowest-seed
nominal instance of the bank (source of 2026-10-13) whose rollout passes here, in `eai-pandadyn`:
1. the instance rebuilt from its parameters and seed;
2. the rollout replayed here reproduces the physical state it recorded after **every** control step, bit for bit (joint
   positions and velocities of every arm, every object's pose and velocities, every fixture's joint): this image's
   physics is the physics the bank was verified on;
3. the rollout's rows succeed through the tooling, and two `replay`s in fresh processes end in the same state hash.
These rows, float64 as recorded, are the oracle of both twins.

Seeds (PROTOCOL §2.13): every task allows its frozen instance's seed only (`[metadata.seeds]`: default = allowed = oracle =
the instance's seed, written by `normalize`). The bank holds 19 more verified nominal seeds per task with their reference
rows, so `allowed` can grow by freezing them under `tests/seeds/<seed>/` (the same three checks); S01's designated channel
and S08's selected branch are drawn per seed and named in the instruction, so those two need an instruction per seed first.

All 25 tasks passed with their first candidate: seed 0, except D04 and S12 (seed 1, the lowest seed their bank holds). The choice and its provenance (the rollout's path in the benchmark checkout, its source digest, the hashes)
are in `scripts/pandadyn/instances.json`; `instance.json`, which the agent reads in privileged mode, names no rollout.

## Tasks and generator
`scripts/pandadyn/mk_tasks.py` (`--check`) writes both twins of every instance in `instances.json` from
`scripts/pandadyn/descr/<code>.json` (what the task asks and exactly what its check tests, written from the task's code;
`scene` is what both modes may read, `scene_privileged` privileged mode only), `frozen/`, `template/<mode>/`, `shared/`
and `scripts/eai_standard/`, and passes them through `scripts/task_conventions.py`'s `normalize()`.
`scripts/pandadyn/sync_env.py` copies the environment package into `images/pandadyn/` (below).

## Success (the task's own)
Every task is a sequence of phases, each with its own physical predicate (a catch, a hold for a stated time, a crossing,
a containment, a release), checked after every physics step (1 ms) and completed strictly in order. The task succeeds at
the first moment the last phase is complete, with no failure recorded; the episode ends there, live and in every replay
(the environment's own termination: ManiSkill's `terminated` = success or fail), so rows after it are never executed.
This is "success at a step", not "success at the end of the replay" (PROTOCOL §3 SHOULD): the phases are events in time
(a ball caught, a puck through a gate), which a final state alone cannot show, and the episode ends at the success.

A task fails, ending the episode, at the first failure event: its own (a ball off a rimless plate, a spill, a dropped
load, ...), a forbidden contact (an arm touching the other arm, itself, the table, an object or a fixture it may not
touch; a tool touching a fixture the task does not allow; an interpenetration deeper than 4 mm), a safety-limit violation
(the Panda's joint position, speed, acceleration and jerk limits, its Cartesian speed and acceleration limits at the TCP,
its torque and torque-rate limits, measured and in the servo's reference; checked every 1 ms), an object leaving the
workspace, or the task's horizon (25 s of simulated time; 32 s for S12, 35 s for D07). Every instruction lists all of them with their
numbers.

## Oracle (PROTOCOL §2.7)
`oracle = "full"`. The reference rows of an instance are the benchmark's recorded rollout of it by its reference
controller (the benchmark's per-task closed-loop controllers, which read the simulator's true state), verified here
(Instances). `solution/oracle_actions.npy` (privileged: run through the agent's own tooling,
`solution/oracle.py`) and `solution/oracle_qpos.npy` (standard: streamed as one-second `joint_position` chunks,
`hold`, sent as a float64 array part, `solution/oracle_replay.py`) hold the same rows, so both oracles end in the same state. The controllers and the bank are not in the image, not in the
repository and not published; only the rows of the 25 frozen instances are, under `solution/`.

`nop`: privileged, no trajectory (reward 0); standard, no control step runs (reward 0). The benchmark's parked controls
(the arms holding their start pose, 1,588 runs over its bank) never succeeded.

## Tooling (`rcb_pandadyn.py`)
`Session(instance=...)`: builds the scene and resets it to the frozen instance; `step(row)` (one 10 ms control step),
`reset()` (exact), `snapshot()` / `restore()` (the environment's own exact checkpoints), `state()` / `objects()` /
`fixtures()` / `params()` (privileged state), `proprio()`, `fk()` / `ik()` (the arm's own Pinocchio model), `actions()`,
`replay()`, `save_trajectory()`, `render_frame()` / `render_depth()` / `camera_info()` / `render_video()`, `status()`,
`state_sha()`. The CLI `replay` is the verifier's and the collect hook's fresh-process replay; `make-instance` and
`run-actions` are the freezing steps. Thin wrappers only: joint targets, kinematics and state; catching, striking,
carrying and timing are the agent's (Declarations).

## Determinism (measured on one host: AMD Ryzen 9 7950X, RTX 4090, driver 580.159.03; eai-pandadyn:0.1.0)
CPU PhysX with `enable_enhanced_determinism`, one simulated scene per process, one thread for every numeric library
(`OMP_NUM_THREADS=1`, set in the image), the scene rebuilt on every reset. Measured:
- all 25 frozen instances: the benchmark's recorded rollout, replayed here, reproduces the physical state it recorded after
  every control step bit for bit (25/25, largest difference 0), so this image (with torch's CPU build) runs the physics the
  bank was verified on; the oracle run and two fresh-process replays end in the same state hash (25/25);
- the benchmark's own record: 3,177 independent replays of its bank with zero state error, and no verdict that changed
  between two replays of the same rollout (226 rollouts replayed at least twice);
- a seed reset alone rebuilds the recorded start (`initial_state.pkl` of the bank adds nothing), and rendering, the render
  backend (`render_backend="cpu"`, below) and the cameras do not change the physics (same hashes);
- standard mode: the live episode equals its two fresh-process replays (`live_matches_replay`), and a service killed in
  the middle of a call resumes the same episode with the same state hash (Crash recovery).

The tasks are sensitive to the last bits of the actions: the oracle rows rounded to float32 (a relative change of about
1e-7) fail on 4 of the 13 instances tried (D04 seed 1, D07, D09, D11: a limit violation or an episode that no longer
completes), and the benchmark measured that the same rows do not succeed at a 2000 Hz physics step either. Grading
therefore never accepts an approximate replay; the standard oracle sends its rows as float64 (the service executes the
rows it receives as float64; the shipped client's `submit` rounds to float32, which costs an agent nothing, since its own
episode is what is replayed).
This sensitivity is not a reproducibility problem: grading always runs the same 1000 Hz physics in the same image, and a
different CPU that rebuilt the start differently would be caught by the `initial_sha` check (`instance_ok` = 0 / `instance_mismatch`,
`infra_error`: no verdict), as on a different GPU for the Isaac benchmarks. A hash check on new hardware is recommended
before official runs there (PROTOCOL §3).

## Grading
- **Privileged** (`tests/grade.py`): the trajectory (`task`, `actions` (T, 8 per arm) float, at most 4,500 rows) is
  replayed open-loop from the verifier's own copy of the instance in two fresh processes; success iff both succeed, both
  end in the same state hash (`deterministic`) and both rebuilt the frozen start (`instance_ok`). A replay that gives no
  result or runs out of its time limit (300 s + rows / 10) is `grader_error` = `infra_error` = 1. Then a filmed replay
  (`replay.mp4`, overview camera) that never changes the verdict.
- **Standard** (`environment/sim/finalize.sh`, then `tests/grade.py`): the service records the episode; the collect hook
  ends it, lets the service exit and replays the trajectory in two fresh processes (the first filmed);
  `success = live_success ∧ replay_success ∧ deterministic` (PROTOCOL §4.8), with no infrastructure error (a replay
  without a result, a replay that did not rebuild the frozen start, an unfinished hook).

## Crash recovery (standard mode, docs/STANDARD_MODE.md §13)
Resume class `exact`: every executed control step is journaled (the float64 row the servo received), every completed call
checkpointed with the state hash; after a crash the restarted service rebuilds the instance, replays the journal (at most
3,500 control steps, seconds to a minute) and checks the hash. `scripts/pandadyn/kill_test.sh` runs the oracle with
Harbor and kills the service with SIGKILL in the middle of a call: on D04 (2026-10-13) the service resumed after 400
control steps with the same state hash (`exact`, 12.9 s of journal replay, 31.8 s down), the oracle continued, and the
episode was graded as usual (success, `live_matches_replay`, `resumes` = 1).

## Time budget (D8)
3600 s for every task of both modes (`scripts/task_cutoffs.toml`; the benchmark's own text names no number). A scene
builds in 5-15 s and runs ~40-150 control steps per second, so the budget is the agent's own work, not the simulator's.

## Standard mode (eai-standard/2.2)
`joint_position` only (8 per arm: 7 joint targets + the total aperture, the environment's own action; rows `dt` apart, a
multiple of 0.01 s, at most 0.5 s; `hold` or `linear`; executed as float64, which the client's `submit` rounds to float32); cameras `overview` and `closeup` (static,
640×480, RGB and z-depth); `/kinematics` (FK / IK of the arms' own Pinocchio models, the hand TCP, the tool and the hand);
proprioception per arm: joints and fingers, hand TCP pose, velocities, aperture, motor torques, tool pose, the targets in
force (`spec["proprio_groups"]`). The simulated clock advances only with the agent's calls (submit rows, observe
watches): between calls the world is frozen, so the agent can look between control steps at a cost in calls, as on a
robot whose controller it pauses; standard-realtime mode (§4b) is not offered.

The episode's only step bound is the task's own horizon (`max_control_steps` = 2,500, 3,200 or 3,500: 25, 32 or 35 s of
simulated time), a failure of the task, stated in `/spec` (`episode`), both instructions and the README.

## Declarations
- **Tooling: thin wrappers only** (above). No task-level skill (catch, strike, carry) is in the agent's tooling.
- **World-frame information (D7).** Both modes give the world conventions (z up, the table top at z = 0, wxyz), the
  robot (arm bases, tools and their mounts, joint, servo and safety limits) and the task's own goal geometry that is not a
  physical object: waypoints and target points of the phase predicates, in world coordinates; a standard agent could not
  know them otherwise, since nothing in the scene marks them. Standard mode never gives where objects or fixtures are,
  their physical parameters (mass, friction, restitution, launch velocities), the seed, or goal values derived from the
  seeded variation; the privileged instruction and tooling give all of them. Panda Dynamic Scenes is therefore not among
  the benchmarks `ci_checks/check-standard-texts.sh` checks for "no world coordinates".
- **Pointers to the reference solution.** None reaches the agent: the image holds the environment package only (its
  command-line front end, which drives the benchmark's validation tooling, is left out, and comments that named that
  tooling are reworded: `scripts/pandadyn/sync_env.py`, which refuses a copy with such text); `instance.json` names no
  rollout; the reference rows are under `solution/` only. The benchmark is not published, and nothing of it is on PyPI.
- **Contact and safety telemetry.** None is published beyond the robot's own proprioception (motor torques, joint and
  TCP motion), which is what the safety limits are judged on; contact forces stay private (PROTOCOL §4.5).

## Notes on the tasks' checks
The instructions describe each check exactly as the task's code implements it (`scripts/pandadyn/descr/`, written from
the code alone, never from the reference controllers). Writing them brought up properties of the benchmark's own checks
that a reader of results should know; none was changed here (a change would be a new benchmark source and new instances):
- some phase conditions are looser than their names: D02's redirects need only a paddle touch after a free flight; D04's
  first phase (shared support) holds from the start; D05's channel exit is a half-space test and its moving-outlet speed
  threshold is 0 at the nominal parameters; S05's speed match is met by a tray held still while the platform passes;
  several crossings (D06, D07, S12) check the tool's contact only at the moment of crossing; D08's braking needs one touch
  while the pendulum is slow;
- S11's moving pocket rests against the side of the raised lane for about 1.5-14.3 s, which leaves 14.3-20.9 s for the
  delivery; S08's docks lie beyond its failure line (only the branch and the recovery count);
- S01's designated channel and S08's selected branch are drawn at reset and nothing in the scene marks them: both
  instructions name this instance's choice (by direction, not by coordinates).
No task is satisfied without completing every phase in order; the benchmark's own acceptance lists its stage-wise shortcut
diagnostics as unfinished.

## Image and host
`images/pandadyn/` → `ghcr.io/mll-lab-nu/eai-pandadyn:0.1.0` (~2.4 GB): Python 3.11.16, ManiSkill 3.0.1, SAPIEN 3.0.3,
torch 2.14.1 (CPU build), Ruckig 0.12.2 (`requirements.lock`, the versions of the benchmark's own lock file; torch is its
CPU build, which reproduces the bank's physics bit for bit), and the environment package. Public (every component is
redistributable). SAPIEN needs a Vulkan device to build a scene and render, so every container that builds one reserves
an NVIDIA GPU (`gpu_class = "any"`); physics runs on one CPU core. Measured over the 50 oracle trials (rcb_monitor samples every 5 s, RTX 4090 host, 2026-10-13): privileged, the whole trial at most 0.79 GiB of memory and 0.05 GiB of GPU memory; standard, the sim service at most 0.94 GiB and 0.35 GiB (its cameras), the agent's container 0.03 GiB; about one core per container (p90). One filmed scene (`render_video`): 1.2-1.3 GiB RSS, 0.25 GiB of GPU memory. The limits (`scripts/task_resources.toml`) leave room for an agent that runs several scenes at once: privileged 16 GiB and 5 GiB of GPU memory for the trial, standard 8 GiB for the agent's container.

## Licences
ManiSkill 3 (and its Panda model): Apache-2.0. SAPIEN: MIT. Ruckig (community version): MIT. PyTorch: BSD-3-Clause.
The Panda Dynamic Scenes environment package: MLL Lab, released with this repository under its licence.
