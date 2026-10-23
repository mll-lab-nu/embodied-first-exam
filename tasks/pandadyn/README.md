# Panda Dynamic Scenes

Panda Dynamic Scenes (MLL Lab; this repository's copy of its environment package is `images/pandadyn/panda_dynamics/`):
25 continuous, multi-stage **dynamic** manipulation tasks for stock Franka Panda (FER) arms on ManiSkill 3.0.1 / SAPIEN
3.0.3, rigid-body CPU PhysX at 1000 Hz. In every task something moves by itself (a tossed ball, a sliding puck, a
conveyor, a pendulum, a spring gate, a moving cart or ramp), and the robot must catch, strike, carry, hand over, flip or
release at the right moment, several times in one episode. `simulator = "maniskill"`; `robot = "franka-panda"` (S01-S12,
one arm) or `"franka-panda-bimanual"` (D01-D13, two arms). Each arm has its standard hand and, in most tasks, a rigid task
tool on it (a plate, a cup, a paddle, a scoop, a fork, a receiver, a pusher).

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/pandadyn -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

One frozen instance per task (i00), each a privileged task `pandadyn-<code>-<name>-i00-privileged` and its standard twin
`pandadyn-<code>-<name>-i00-standard` (`eai-standard/2.1`): 50 task directories; the 19 dynamic families (all but D05, D08,
D11, D12, D13, S06) also have a standard-realtime twin `pandadyn-<code>-<name>-i00-standard-realtime` (`eai-standard/2.3`): 69
task directories.

| Code | Task | Arms | Phases | Seed (i00) | Oracle |
|---|---|---|---|---|---|
| D01 | Reciprocal two-cup air relay (`ReciprocalCupRelay`) | 2 | 6: left_initial_catch, left_to_right_flight, right_catch, second_region, right_to_left_flight, left_catch_and_deliver | 0 | 1560 rows, 15.6 s of 25 s |
| D02 | Strike, catch and merge two balls (`StrikeCatchMerge`) | 2 | 6: first_redirect, first_catch, loaded_cup_relocation, second_redirect, second_catch, both_delivery | 0 | 1755 rows, 17.55 s of 25 s |
| D03 | Cooperative puck course (`CooperativePuckCourse`) | 2 | 4: left_first_pass, right_return_route, left_diagonal_pass, right_terminal_shot | 0 | 2278 rows, 22.78 s of 25 s |
| D04 | Shared tray transport and discharge (`SharedTrayTransportDischarge`) | 2 | 5: shared_support, transport_turn, disturbance_recovery, exit_alignment, natural_discharge | 1 | 560 rows, 5.6 s of 25 s |
| D05 | Moving ramp relay (`MovingRampRelay`) | 2 | 6: first_channel_entry, first_moving_exit, first_catch, second_channel_entry, second_moving_exit, second_catch_and_delivery | 0 | 2393 rows, 23.93 s of 25 s |
| D06 | Moving bank relay (`MovingBankRelay`) | 2 | 5: right_first_strike, left_first_rebound, right_recovery_strike, left_changed_rebound, terminal_goal | 0 | 1696 rows, 16.96 s of 25 s |
| D07 | Spring gate switchyard (`SpringGateSwitchyard`) | 2 | 5: left_gate_open, right_loop_shot, gate_reconfiguration, return_interception, final_gate_shot | 0 | 2526 rows, 25.26 s of 35 s |
| D08 | Pendulum energy relay (`PendulumEnergyRelay`) | 2 | 5: left_excitation, right_braking, right_return_impulse, left_recovery, low_energy_hold | 0 | 565 rows, 5.65 s of 25 s |
| D09 | Lever launch, catch and reload (`LeverLaunchCatchReload`) | 2 | 6: physical_loading, first_launch, right_catch, reload_and_clear, second_launch, moving_receptacle_retention | 0 | 1625 rows, 16.25 s of 25 s |
| D10 | Moving grasp handover (`MovingGraspHandover`) | 2 | 5: moving_pickup, moving_presentation, overlapping_grips, donor_release, receiver_slot_delivery | 0 | 1554 rows, 15.54 s of 25 s |
| D11 | Moving fixture unlock (`MovingFixtureUnlock`) | 2 | 5: moving_fixture_presentation, relative_pin_insertion, mechanical_latch_open, follow_and_withdraw, gravity_delivery | 0 | 1563 rows, 15.63 s of 25 s |
| D12 | Reciprocal sliding transfer (`ReciprocalSlidingTransfer`) | 2 | 5: left_inertial_slip, right_receive_and_brake, reverse_geometry, left_receive_and_brake, final_support_deposit | 0 | 1251 rows, 12.51 s of 25 s |
| D13 | Supported cube flip relay (`SupportedCubeFlipRelay`) | 2 | 5: support_presentation, first_inertial_flip, second_contact_geometry, second_inertial_flip, oriented_output | 0 | 883 rows, 8.83 s of 25 s |
| S01 | Cup catch, route pour, rebound recatch and cart delivery (`CupRouteDelivery`) | 1 | 5: incoming_catch, selected_route_entry, track_and_rebound, downstream_catch, moving_cart_delivery | 0 | 1910 rows, 19.1 s of 25 s |
| S02 | Plate catch, transport and release (`PlateCatchTransportRelease`) | 1 | 5: airborne_plate_catch, recenter, turning_transport, rolling_recovery, moving_basin_release | 0 | 1118 rows, 11.18 s of 25 s |
| S03 | Clear the blocker, recover and bank into the goal (`ClearGateHockey`) | 1 | 5: first_strike, clear_blocker, recover_deflection, second_strike, bank_and_goal | 0 | 3025 rows, 30.25 s of 35 s |
| S04 | Impact release, interception and passage relay (`ImpactReleaseRelay`) | 1 | 5: cue_strike, mechanical_unlatch, payload_interception, passage_redirection, payload_braking | 0 | 441 rows, 4.41 s of 25 s |
| S05 | Sliding receive, inertial staging and moving hand-off (`SlidingReceiveAlignDeliver`) | 1 | 5: source_to_tray, inertial_staging, transport_turn, match_receiver, support_transfer | 0 | 1021 rows, 10.21 s of 25 s |
| S06 | Inertial cube flip, chute run and pocket recovery (`CubeFlipRouteRecover`) | 1 | 4: momentum_face_flip, oriented_chute_entry, downstream_intercept, pocket_delivery | 0 | 1295 rows, 12.95 s of 25 s |
| S07 | Conveyor pick, carriage load, braking and dock unload (`ConveyorLoadBrakeUnload`) | 1 | 5: moving_acquisition, loaded_carriage_release, handle_braking, payload_regrasp, dock_deposit | 0 | 1303 rows, 13.03 s of 25 s |
| S08 | Load a coasting cart, throw the switch, recover the part (`LoadSwitchRecover`) | 1 | 5: moving_part_pickup, load_coasting_cart, physical_switch_operation, selected_branch, payload_recovery | 0 | 2189 rows, 21.89 s of 25 s |
| S09 | Catch, self-toss, recatch and deliver (`TossRecatchDelivery`) | 1 | 5: initial_catch, launch_region, self_toss, displaced_recatch, moving_receiver_delivery | 0 | 1241 rows, 12.41 s of 25 s |
| S10 | Swinging load transit and dock (`SwingingLoadTransitDock`) | 1 | 5: grasp_settle_and_damp, obstacle_transit, turn_and_brake, residual_swing_cancel, load_dock | 0 | 1456 rows, 14.56 s of 25 s |
| S11 | Cylinder rescue, guide route and oriented delivery (`CylinderRescueRouteDeliver`) | 1 | 5: rolling_interception, axial_alignment, guide_rail_traverse, exit_reception, oriented_moving_delivery | 0 | 1782 rows, 17.82 s of 25 s |
| S12 | Spinning bridge puck relay and goal (`MovingBridgePuckRelay`) | 1 | 5: incoming_strike, physical_bridge_transfer, exit_interception, second_strike, closing_gate_goal | 0 | 2171 rows, 21.71 s of 32 s |

## Instances
An instance is the benchmark's own: one task at difficulty `nominal` (the task's configuration, `common` updated by its
`nominal` overrides) and a seed, from which the task's reset draws its per-instance variation (an incoming lateral
offset, a route, a fixture phase, ...). The environment rebuilds the whole scene on every reset (`reconfigure`), so a
seed reset is exact; `instance.json` holds the task, the resolved parameters, the seed and the hash of the rebuilt start
(`initial_sha`), which the privileged verifier's replays and the standard services' scene build check.

The benchmark keeps a bank of verified instances (20 nominal + 10 hard per task), each with a recorded rollout of its
reference controller and an independent action replay. For each task, the frozen instance is the lowest-seed
nominal instance of the bank whose rollout passes here, in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`:
1. the instance rebuilt from its parameters and seed;
2. the rollout replayed here reproduces the physical state it recorded after **every** control step, bit for bit (joint
   positions and velocities of every arm, every object's pose and velocities, every fixture's joint): this image's
   physics is the physics the bank was verified on;
3. the rollout's rows succeed through the tooling, and two `replay`s in fresh processes end in the same state hash.
These rows, float64 as recorded, are the oracle of both twins.

Seeds (PROTOCOL §2): every task allows its frozen instance's seed only (`[metadata.seeds]`: default = allowed = oracle =
the instance's seed, written by `normalize`). The bank holds 19 more verified nominal seeds per task with their reference
rows, so `allowed` can grow by freezing them under `tests/seeds/<seed>/` (the same three checks); S01's designated channel,
S03's designated rail and S08's selected branch are drawn per seed and named in the instruction, so those three need an
instruction per seed first.

All 25 tasks passed with their first candidate: seed 0, except D04 (seed 1, the lowest nominal seed its bank holds). `instance.json`, which the agent reads in privileged mode, names no rollout.

## Tasks
Every instance has both twins; the instance files live only in the tasks (privileged: `environment/instance.json`,
`solution/oracle_actions.npy`; standard: `environment/sim/instance.json`, `solution/oracle_qpos.npy`). The texts say what
the task asks and exactly what its check tests, written from the task's code. The task directories are the deliverable;
the tooling that built them is kept outside this repository.
`images/pandadyn/sync_env.py` copies the environment package into `images/pandadyn/` (below).

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
workspace, or the task's horizon (25 s of simulated time; 32 s for S12, 35 s for S03 and D07). Every instruction lists all of them with their
numbers.

## Oracle (PROTOCOL §4)
`oracle = "full"`. The reference rows of an instance are the benchmark's recorded rollout of it by its reference
controller (the benchmark's per-task closed-loop controllers, which read the simulator's true state), verified here
(Instances). `solution/oracle_actions.npy` (privileged: run through the agent's own tooling,
`solution/oracle.py`) and `solution/oracle_qpos.npy` (standard: after one-second scouting episodes that spend the reset
budget, streamed in the last episode as one-second `joint_position` chunks, `hold`, float64, `solution/oracle_replay.py`;
standard-realtime: planned from step 0, `solution/oracle_plan.py`) hold the same rows, so all oracles end in the same state. The controllers and the bank are not in the image, not in the
repository and not published; only the rows of the 25 frozen instances are, under `solution/`.

`nop`: privileged, no trajectory (reward 0); standard, no control step runs (reward 0). The benchmark's parked controls
(the arms holding their start pose, one run per verified instance of its bank, 750 runs) never succeeded.

## Tooling (`rcb_pandadyn.py`)
`Session(instance=...)`: builds the scene and resets it to the frozen instance; `step(row)` (one 10 ms control step),
`reset()` (exact), `snapshot()` / `restore()` (the environment's own exact checkpoints), `state()` / `objects()` /
`fixtures()` / `params()` (privileged state), `proprio()`, `fk()` / `ik()` (the arm's own Pinocchio model), `actions()`,
`replay()`, `save_trajectory()`, `render_frame()` / `render_depth()` / `camera_info()` / `render_video()`, `status()`,
`state_sha()`. The CLI `replay` is the privileged verifier's fresh-process replay; `make-instance` and
`run-actions` are the freezing steps. Thin wrappers only: joint targets, kinematics and state; catching, striking,
carrying and timing are the agent's (Declarations).

## Determinism (measured on one host: AMD Ryzen 9 7950X, RTX 4090, driver 580.159.03; efe:pandadyn-0.2.0 unless noted)
CPU PhysX with `enable_enhanced_determinism`, one simulated scene per process, one thread for every numeric library
(`OMP_NUM_THREADS=1`, set in the image), the scene rebuilt on every reset. Measured:
- all 25 frozen instances: the benchmark's recorded rollout, replayed here, reproduces the physical state it recorded after
  every control step bit for bit (24/25, largest difference 0), so this image (with torch's CPU build) runs the physics the
  bank was verified on; the 25th, S06, is frozen with the BLAS kernel its containers pin (below), under which its start
  differs from the bank's recording in the last bits, and its rows succeed here. The oracle run and two fresh-process
  replays end in the same state hash (25/25);
- the benchmark's own record: every verified instance of its bank (20 nominal + 10 hard per task) has an independent
  action replay with zero state error and the same events and outcome;
- a seed reset alone rebuilds the recorded start (`initial_state.pkl` of the bank adds nothing), and rendering, the render
  backend (`render_backend="cpu"`, below) and the cameras do not change the physics (same hashes);
- across hosts (measured for pandadyn 0.1.0, 2026-10-17; not repeated for 0.2.0): S06's arm start comes from the IK fallback (scipy `least_squares`: Pinocchio's
  IK does not converge there, joint 4 ends on its bound), whose last bits follow the BLAS kernel OpenBLAS picks for the
  CPU. Frozen under the AVX-512 kernel, its start never rebuilt on the pool's AVX2 hosts (AWS EPYC 7R13, cluster EPYC 7402,
  cluster EPYC 7763; 4 joints differ in the last float32 bit: `instance_mismatch`). Its containers now pin the kernel
  (`OPENBLAS_CORETYPE=Haswell`; frozen with it, in 0.2.0 too): the start and the oracle's final state are
  the same on a Ryzen 9 7950X and an EPYC 7R13. The other 24 starts come from Pinocchio's IK and rebuild on both
  (all 25 checked on aws:rcb-gpu8), and every oracle succeeds on both; 6 oracles (D03, D08, D10, D13, S05, S07) end in
  another state hash there than the README's (measured here): a trajectory and its grading replay always run on one
  host, so no verdict depends on it;
- standard mode: the live episode equals a fresh-process replay of its rows (the video pass records the comparison,
  `video_matches_live`, for information only), and a service killed in the middle of a call resumes the same episode with
  the same state hash (Crash recovery).

The tasks are sensitive to the last bits of the actions: the oracle rows rounded to float32 (a relative change of about
1e-7) failed on 4 of the 13 pandadyn 0.1.0 instances tried (D04 seed 1, D07, D09, D11: a limit violation or an episode that no longer
completes), and the benchmark measured that the same rows do not succeed at a 2000 Hz physics step either. Grading
therefore never accepts an approximate replay; the standard oracle sends its rows as float64 (the service executes the
rows it receives as float64; the shipped client's `submit` rounds to float32, which costs an agent nothing, since its own
episode is what is graded).
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
- **Standard and standard-realtime** (one adapter: `environment/sim/server.py`, an `rcb_service.Sim` on
  `rcb_pandadyn.Session`, on the shared service layer `rcb_service.py`; the realtime twin adds `rcb_realtime.py`'s clock;
  then `tests/grade.py`, the shared one): graded by the live episode, nothing replayed (PROTOCOL H.4). `success` = the task's own check as the last episode ended (rcb_service's finalize; the
  adapter's `live_verdict` adds the phase and the end reason and takes nothing away): every phase in order with no
  failure event, no forbidden contact and no safety-limit violation. The check is evaluated after every physics step and
  the episode ends at the first control step where the task has succeeded or failed, so the live predicate already is the
  whole rule (no settle or hold window). The collect hooks stop the agent's programs (`kill -9 -1` in its container,
  after the monitor's seal), then signal the service (SIGUSR1), which writes the verdict into `final.json` (`graded_by`
  = `live`, `replays` = 0, `live_success`, `episodes`, `resets`) and then films the graded episode's rows in the same
  process (`replay.mp4`, overview camera, 25 fps; `video_pending` while it runs). The frozen start is checked when the
  first episode begins and after every reset (`start_sha` = the instance's `initial_sha`; a mismatch is
  `instance_mismatch`, infrastructure). Infrastructure (`infra_error` = 1, no verdict on the agent): an unreadable or
  unfinalized `final.json`, `instance_mismatch`, a reset whose scene does not rebuild, a give-up after crashes not all the
  agent's (`sim_crashed`, `resume_failed`). The agent's 0: a failure of the task, a timeout, no actions, a simulator
  error from a call (`sim_error`), crashes all inside the agent's calls (`sim_crashed_on_call`). A failed or slow video
  costs only the video.

## Crash recovery (both standard modes)
The shared service layer's (`rcb_service.py`): every executed control step is journaled (`trajectory_live.f64`, the
float64 row the servo received), every completed call checkpointed with the state hash; after a crash compose restarts the
service, which rebuilds the instance, replays the journal of the running episode (at most 3,500 control steps, seconds
to a minute), checks the hash and continues the same episode (never a reset; the realtime twin resumes it paused).
Killed with SIGKILL in the middle of a call during a standard task's oracle run, the service resumes the same episode
with the same state hash.

## Time budget
3600 s for every task of both modes (each task's `[agent] timeout_sec`; the benchmark's own text names no number). A scene
builds in 5-15 s and runs ~40-150 control steps per second, so the budget is the agent's own work, not the simulator's.

## Standard mode (eai-standard/2.1)
Standard and standard-realtime differ only in the clock. Both run
the same adapter (each twin's `environment/sim/server.py`: the same code, each copy with its own docstring) on the same
shared service layer (`rcb_service.py`, with `grade.py` and the 2.1 client: the same files as HumanoidBench's, BiGym
2.0's and Embodied Olympics - Fun's), with the same reset budget ("Reset budget" below). The static families (D05, D08, D11, D12, D13, S06) have
only the standard twin and get the same rules.
- **Action.** `joint_position` only (8 per arm: 7 joint targets + the total aperture, the environment's own action;
  clipped to the limits and executed as float64, which the client sends): rows `dt` apart, a whole multiple of the 10 ms
  control step, `hold` or `linear` (from the targets in force), a chunk at most 10 s.
- **Observation.** Cameras `overview` and `closeup` (static, 640×480, RGB, z-depth on request) with their calibration in
  `/spec`; proprioception per arm: joints and fingers, hand TCP pose, velocities, aperture, motor torques, tool pose, the
  targets in force (`spec["proprio_groups"]`); `video_fps` 1-30, at most 3,000 images per call; watches (`observe` with
  `seconds`) up to 30 s, holding the last targets.
- **Clock.** The simulated clock advances only with the agent's calls (submit rows, observe watches): between calls the
  world is frozen, so the agent can look between control steps at a cost in calls, as on a robot whose controller it
  pauses. The standard-realtime twin runs the same steps on a clock that does not stop (below).
- **Episode.** The only step bound is the task's own horizon (2,500, 3,200 or 3,500 control steps: 25, 32 or 35 s of
  simulated time; `/spec` `max_control_steps` is the environment's cap, 4,500), a failure of the task, stated in `/spec`
  (`episode`), both instructions and the README; resets as in
  the realtime twin; only the last episode is graded.

## Standard-realtime (eai-standard/2.3)
The dynamic families (`[metadata] dynamics`, declared by each task; D05, D08, D11, D12, D13 and S06 are static: nothing in
them moves by itself) get a `-standard-realtime` twin, sharing the standard twin's adapter, service layer and reset budget
("Standard mode" above).
- **Service.** The shared realtime layer of HumanoidBench, BiGym 2.0 and Embodied Olympics - Fun, unchanged (`rcb_realtime.py`
  and `rcb_client.py` from `embodied_first_exam/standard/realtime/`, `rcb_service.py`, `grade.py`), with the twin's
  `environment/sim/server.py`, an `rcb_service.Sim` adapter on `rcb_pandadyn.Session`: the standard
  twin's frozen instance, `joint_position` action (clipped to the limits, executed as float64), success check, cameras
  (`overview`, `closeup`, RGB and z-depth, with their calibration in `/spec`) and proprioception columns. Not served: the
  2.2 additions (`/kinematics`, per-frame camera poses, depth modes), all MAYs in 2.3. Resets: `Session.reset()`, the
  scene rebuilt and reset with the instance's seed (exact, about 1 s); 3 per trial ("Reset budget" below).
- **Grading.** The live episode: success = the task's own check as the last episode ended
  (rcb_service's `_finalize`; the adapter's `live_verdict` adds the phase and the end reason and takes nothing away), with
  the frozen start checked when the first episode begins (`start_sha` = the instance's `initial_sha`). The video is
  rendered after the verdict from the graded episode's rows by the service's own Session (the scene rebuilt) and never
  decides.
- **Reference solution.** `solution/oracle_plan.py` plans the privileged oracle's rows (one per control step, `hold`)
  into the episode from step 0, 10 s per chunk, each chunk at its own step (`at`), so every row runs at its recorded
  control step whatever the wall clock does: `oracle = "full"`.
- **Slowdown S per family.** CPU PhysX at 1000 Hz with two servos in Python runs slower than real time here, so no
  family runs at S = 1. Measured on an RTX 4090 workstation (32 cores, the service capped at 4 CPUs): the
  realtime service with its clock flat out (`RCB_SLOWDOWN=0.01`, the oracle's first 10 s planned from step 0; host load
  18-80) and the bare physics loop (`Session.step` over the oracle's first 8 s; load 39-47). S = ceil(1.5 / RTF) with
  the lower of the two (PROTOCOL §2; a busy pool host is slower still: the same service ran 1.4-1.9 x faster at load
  20 than at load 45):

| family | RTF (service, physics) | S | | family | RTF (service, physics) | S |
|---|---|---:|---|---|---|---:|
| D01 ReciprocalCupRelay | 1.00, 0.69 | 3 | | S03 ClearGateHockey | 1.21, 1.18 | 2 |
| D02 StrikeCatchMerge | 0.83, 0.52 | 3 | | S04 ImpactReleaseRelay | 1.06, 1.02 | 2 |
| D03 CooperativePuckCourse | 1.01, 0.71 | 3 | | S05 SlidingReceiveAlignDeliver | 1.21, 1.20 | 2 |
| D04 SharedTrayTransportDischarge | 0.75, 0.42 | 4 | | S07 ConveyorLoadBrakeUnload | 0.46, 0.48 | 4 |
| D06 MovingBankRelay | 0.94, 0.73 | 3 | | S08 LoadSwitchRecover | 0.29, 0.29 | 6 |
| D07 SpringGateSwitchyard | 0.86, 0.51 | 3 | | S09 TossRecatchDelivery | 0.92, 1.14 | 2 |
| D09 LeverLaunchCatchReload | 0.98, 0.61 | 3 | | S10 SwingingLoadTransitDock | 0.84, 0.84 | 2 |
| D10 MovingGraspHandover | 0.55, 0.30 | 6 | | S11 CylinderRescueRouteDeliver | 0.69, 0.94 | 3 |
| S01 CupRouteDelivery | 1.49, 1.22 | 2 | | S12 MovingBridgePuckRelay | 0.68, – | 3 |
| S02 PlateCatchTransportRelease | 1.41, 1.24 | 2 | |  | |  |

- **Checked at the task's S** (pandadyn 0.1.0; one container at a time, 4 CPUs, GPU for SAPIEN): in every one of the 19 twins,
  three aborted attempts (the oracle's first second planned from step 0, then `reset`) and then the oracle planned
  from step 0 in the fourth episode: live success, the same final state in a fresh-process replay, `late_steps` 0; the clock kept time with no stall in 17 of them (largest lag 0.01-0.49 s) and stalled 3 times in D07
  (2.3 s dropped, largest lag 1.1 s) and once in S08 (0.5 s), at host load 24-71; nop (no request): `timeout`, not a
  success, in all 19. A first oracle run of S04 at S = 2 showed one 0.6 s step (a stall) at step 310: the clock re-anchors
  and the robot's time loses nothing; stalls are recorded in `final.json` / `reward.json` and decide nothing. For 0.2.0
  the oracle (planned from step 0) and nop were rerun with Harbor on S03 (S = 2) and D06 (S = 3): live success with
  `late_steps` 0, and reward 0.
- **Reset budget: 3**, in both standard modes (below the standard-realtime mode's default of
  10, the benchmark's choice). Every reset
  restores the same frozen start, and the client lets a program plan up to 10 s ahead (`at`), so the budget is the
  number of times an agent can rerun an open-loop plan on a deterministic scene, watch the outcome and tune it; the
  clock that does not stop adds little once the plan is fixed (with 10 resets, screening successes came in episode 6-11
  and most failures used the whole budget). Three resets keep one or two scouting episodes and a real attempt. The check above (three aborted
  attempts, then the oracle in the fourth episode) uses exactly this budget, and so does the standard oracle
  (`solution/oracle_replay.py`: three one-second scouting episodes, then the oracle's rows).

## Declarations
- **Tooling: thin wrappers only** (above). No task-level skill (catch, strike, carry) is in the agent's tooling.
- **World-frame information.** Both modes give the world conventions (z up, the table top at z = 0, wxyz), the
  robot (arm bases, tools and their mounts, joint, servo and safety limits) and the task's own goal geometry that is not a
  physical object: waypoints and target points of the phase predicates, in world coordinates; a standard agent could not
  know them otherwise, since nothing in the scene marks them. Standard mode never gives where objects or fixtures are,
  their physical parameters (mass, friction, restitution, launch velocities), the seed, or goal values derived from the
  seeded variation; the privileged instruction and tooling give all of them. Panda Dynamic Scenes is therefore not among
  the benchmarks whose own `ci_checks/benchmarks/<bench>/advisory-world-frame.sh` checks for "no world coordinates".
- **Pointers to the reference solution.** None reaches the agent: the image holds the environment package only (its
  command-line front end, which drives the benchmark's validation tooling, is left out, and comments that named that
  tooling are reworded: `images/pandadyn/sync_env.py`, which refuses a copy with such text); `instance.json` names no
  rollout; the reference rows are under `solution/` only. The benchmark is not published, and nothing of it is on PyPI.
- **Contact and safety telemetry.** None is published beyond the robot's own proprioception (motor torques, joint and
  TCP motion), which is what the safety limits are judged on; contact forces stay private (PROTOCOL H.3).

- **Scene motion in the privileged instruction.** The sentence "Things move by themselves from the first
  control step on: the scene does not wait for the robot." is written for the 19 dynamic families only; the six static ones say "Nothing moves by itself".

## Notes on the tasks' checks
The instructions describe each check exactly as the task's code implements it (written from
the code alone, never from the reference controllers). Writing them brought up properties of the benchmark's own checks
that a reader of results should know. pandadyn 0.2.0 (a new source and new instances) tightened several of them (the
tasks' Change Logs say what changed): D05's moving outlet must now move at 0.10 m/s or more, D07's gate must be held by its
handle at every judged moment, D08's braking is a catch at 1 rad/s or more that takes 60 % of the energy out, and S12's
gate opens and closes and must be passed through its doorway. What remains:
- some phase conditions are looser than their names: D02's redirects need only a paddle touch after a free flight; D04's
  first phase (shared support) holds from the start; D05's channel exit is a half-space test; S05's speed match is met
  by a tray held still while the platform passes; the goal crossings of D06, D07 and S12 check the paddle's contact only
  at the moment of crossing;
- S11's moving pocket rests against the side of the raised lane for about 1.5-14.3 s, which leaves 14.3-20.9 s for the
  delivery; S08's docks lie beyond its failure line (only the branch and the recovery count);
- S01's designated channel and S08's selected branch are drawn at reset and nothing in the scene marks them; S03's
  designated rail is drawn per seed and coloured green. All three instructions name this instance's choice (by
  direction, not by coordinates).
No task is satisfied without completing every phase in order; the benchmark's own acceptance withholds each stage in
turn (stage-withholding diagnostics on the current source) and found no shortcut (a passive last stage, such as D11's
gravity delivery, completes by itself once the stage before it is done, and is not counted).

## Image and host
`images/pandadyn/` → `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` (~2.4 GB): Python 3.11.16, ManiSkill 3.0.1, SAPIEN 3.0.3,
torch 2.14.1 (CPU build), Ruckig 0.12.2 (`requirements.lock`, the versions of the benchmark's own lock file; torch is its
CPU build, which reproduces the bank's physics bit for bit), and the environment package. Public (every component is
redistributable). SAPIEN needs a Vulkan device to build a scene and render, so every container that builds one reserves
an NVIDIA GPU (`gpu_class = "any"`); physics runs on one CPU core. Measured for 0.1.0 over the 50 oracle trials (rcb_monitor samples every 5 s, RTX 4090 host): privileged, the whole trial at most 0.79 GiB of memory and 0.05 GiB of GPU memory; standard, the sim service at most 0.94 GiB and 0.35 GiB (its cameras), the agent's container 0.03 GiB; about one core per container (p90). One filmed scene (`render_video`): 1.2-1.3 GiB RSS, 0.25 GiB of GPU memory. The limits (`scripts/task_resources.toml`) leave room for an agent that runs several scenes at once: privileged 16 GiB and 5 GiB of GPU memory for the trial, standard 8 GiB for the agent's container.

## Change Log
- 2026-10-23 (owner): pandadyn 0.2.0, base image `efe:pandadyn-0.2.0` (the environment package as of 2026-10-22). Every
  task changed in place (new DIGEST; its README's Change Log says what): stricter or redesigned checks in S03, S07, S08,
  S10, S12, D01, D05, D06, D07, D08, D10, D11, D12 and D13 (S03 also has a designated rail per instance and a 35 s horizon);
  the thin tools' adapters are now joined to the tools (S03, S06, S12, D03, D06, D07, D08, D09, D11, D13); unused
  configuration parameters are gone from the instances; the instructions say that closing a tool arm's gripper touches its
  adapter (`self_collision`). Re-frozen from the benchmark's re-verified bank by the same rule (Instances): S12 is now
  seed 0 (was 1), and 16 instances have new reference rows (the other 9 keep theirs). Results from 0.1.0 are under the earlier digests.

## Licences
ManiSkill 3 (and its Panda model): Apache-2.0. SAPIEN: MIT. Ruckig (community version): MIT. PyTorch: BSD-3-Clause.
The Panda Dynamic Scenes environment package: MLL Lab, released with this repository under its licence.

## Standard-mode service details

Serves `eai-standard/2.1` with the optional reset capability (3 resets). Resume by journal replay to the logged state hash (ManiSkill / SAPIEN, CPU PhysX with enhanced determinism, one thread; every reset rebuilds the scene; ten physics steps per control step).

## Screening

The screening below ran on pandadyn 0.1.0 (task digests from before 2026-10-23). 0.2.0 changed every task (new digests; results are attributed by digest), so it describes 0.1.0 and has not been rerun yet.

The benchmark owner's screening (ten runs, one trial per run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders (for this benchmark mostly from the grading records only: the log review
was partial). It is **hard** when GPT-6 Luna and every later run that attempted it failed, GPT-6 Astra and Claude Opus
5.5 among them; a standard directory that only Astra solved is hard as well. It is **unverified** when only Luna
attempted it and failed (the later runs only take bases Luna solved in no mode), and **pending** without a Luna verdict.
A base whose every mode is easy, and every base Luna solved in some mode, is left out of the core set (`docs/core_set.toml`); its tasks keep their names.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

By directory: 33 easy, 11 hard, 24 unverified, 1 pending.

| base | privileged | standard | standard-realtime |
|---|---|---|---|
| `pandadyn-d01-reciprocal-cup-relay-i00` | easy: Astra, Opus, GLM 5.3 Flash | hard | easy: Astra (3), Opus (9) |
| `pandadyn-d02-strike-catch-merge-i00` | easy: Luna | unverified | unverified |
| `pandadyn-d03-cooperative-puck-course-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon | hard | easy: Astra (10) |
| `pandadyn-d04-shared-tray-transport-discharge-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Gemini 4 Argon | easy: Astra (1), Opus (1), GLM 5.3 Flash (7) |
| `pandadyn-d05-moving-ramp-relay-i00` | easy: Astra, Opus | hard | — |
| `pandadyn-d06-moving-bank-relay-i00` | easy: Luna | unverified | unverified |
| `pandadyn-d07-spring-gate-switchyard-i00` | easy: Astra, Opus, Gemini 4 Argon, DeepSeek V4.1 Flash | hard | easy: Opus (7) |
| `pandadyn-d08-pendulum-energy-relay-i00` | easy: Luna | unverified | — |
| `pandadyn-d09-lever-launch-catch-reload-i00` | easy: Astra, Opus | hard | hard |
| `pandadyn-d10-moving-grasp-handover-i00` | easy: Luna | unverified | unverified |
| `pandadyn-d11-moving-fixture-unlock-i00` | easy: Luna | unverified | — |
| `pandadyn-d12-reciprocal-sliding-transfer-i00` | easy: Luna | unverified | — |
| `pandadyn-d13-supported-cube-flip-relay-i00` | easy: Luna | unverified | — |
| `pandadyn-s01-cup-route-delivery-i00` | easy: Astra, Opus | hard | easy: Astra (9) |
| `pandadyn-s02-plate-catch-transport-release-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s03-clear-gate-hockey-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s04-impact-release-relay-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s05-sliding-receive-align-deliver-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s06-cube-flip-route-recover-i00` | pending | hard | — |
| `pandadyn-s07-conveyor-load-brake-unload-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s08-load-switch-recover-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s09-toss-recatch-delivery-i00` | easy: Astra, Opus, Gemini 4 Argon | hard | easy: Astra (7), Opus (10) |
| `pandadyn-s10-swinging-load-transit-dock-i00` | easy: Luna | unverified | unverified |
| `pandadyn-s11-cylinder-rescue-route-deliver-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | hard | easy: Astra (3), Gemini 3.8 Flash (6) |
| `pandadyn-s12-moving-bridge-puck-relay-i00` | easy: Astra, Opus | hard | easy: Astra (7), Opus (5) |

Standard-realtime cells name each solving run with the resets it used (the screening allowed 10; a solve that used more
than 3 would not count under today's budget). The standard cells are from standard twins with no reset, a configuration
being rerun under today's. `pandadyn-d04-shared-tray-transport-discharge-i00`, easy in every mode and so left out of the core set, has realtime solves with 1 reset (Astra, Opus).
