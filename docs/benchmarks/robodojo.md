# RoboDojo

[RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) @ cb2a37d (MIT): the simulation part of RoboDojo's
sim-and-real benchmark for generalist manipulation policies, on its Isaac Lab 2.3 fork (@ afca7b0) and Isaac Sim 5.1.0,
with its cuRobo fork (@ d17b54c) for IK. Two ARX X5 arms (6 joints each, parallel two-finger grippers) at a table.
`simulator = "robodojo"`, `robot = "arx-x5-bimanual"`. Every task of the simulation benchmark is included: RoboDojo's 42
tasks over five capability dimensions (Generalization 12, Memory 6, Precision 8, Long-Horizon 8, Open 8) and the 12
`_random` variants of the Generalization tasks (other models, lighting, backgrounds, ~15-20 clutter objects): 54 families.

One frozen instance per task, RoboDojo's own evaluation layout `Assets/Eval_Layout/RoboDojo/arx_x5/0/<task>_0.json`,
each a privileged task `robodojo-<task>-i00-privileged` and its standard twin `robodojo-<task>-i00-standard`
(`eai-standard/2.2`), except the six tasks whose physics does not replay bit for bit (Determinism, below): they are
standard only, graded by the live episode. 48 privileged + 54 standard = 102 task directories. `oracle = "none"` for every
task (below).

## Tasks and generator
`scripts/robodojo/mk_tasks.py [--check]` writes the 102 directories from:
- `scripts/robodojo/descr/<task>.json`: what the task asks and exactly what its check tests (every predicate, threshold,
  stage and end-of-episode requirement), written from RoboDojo's code (`task/RoboDojo/tasks/<task>.py`, its config,
  `env/reward_manager/`); the instructions quote it. The code is the reference.
- `scripts/robodojo/frozen/<task>-i00/instance.json`: the evaluation layout verbatim (with its sha256), the state hash after
  RoboDojo's reset, RoboDojo's language instruction for the layout, and per-task fields from
  `scripts/robodojo/instance_overrides.json` (`physics`, `determinism`), copied in by `sync_frozen.py` from the determinism
  test's output (`rcb_robodojo.py make-instance --task T --seed 0 --layout 0 [--physx key=value]`).
- `scripts/robodojo/dimensions.json` (RoboDojo's documentation), `conventions.json`, `template/<mode>/`.

## Success (RoboDojo's own check)
RoboDojo's reward manager for the task, unchanged: its `run_reward()` check list (registered at the start of every episode,
as RoboDojo's evaluator does), evaluated after every action; stages count in order, at most one per action; a failed
query ends the episode as a failure. The episode ends at the first action where every stage has passed. No task of the 54
registers an end-of-episode check: RoboDojo's per-task `step_lim` only ends a policy's episode in its evaluation, so it is
not applied here (no step caps, PROTOCOL D1); a technical cap ends an episode after 15,000 actions (10 min of simulated
time; reason `step_guard`, standard mode's `spec.max_control_steps`), the most a trajectory may hold. The instructions
give RoboDojo's limit for reference.

## Oracle (PROTOCOL §2.7)
None: RoboDojo releases no expert or planner script, and its training demonstrations (Hugging Face, `data/`) record no
initial state or layout, so none replays on a frozen layout. Every task is `oracle = "none"` and needs human review
(CONTRIBUTING.md; the review is in pull request #142). Positive examples from model trials (Codex + GPT-6 Luna, effort xhigh, web search off, 90 min,
2026-10-10): privileged `general_pickup`, `deposit_coin`, `match_and_pick_from_conveyor`, `stack_blocks_by_language` and
standard `general_pickup` succeeded (graded by the task's verifier: two fresh-process replays, identical end states);
`stack_bowls` and `classify_objects` (privileged) did not. The other tasks are reported separately until they have one.

## Tooling (`rcb_robodojo.py`)
`Session(task, instance=...)` builds RoboDojo's own evaluator environment (`src/eval_client/eval_env.py`: one env, the
policy-server client replaced by a stub) and resets it onto the frozen layout exactly as RoboDojo's evaluator starts an
episode. Action: RoboDojo's 14-D joint action `[left joint1..6, left gripper, right joint1..6, right gripper]` at 25 Hz
(physics dt 4 ms, 10 physics steps per action, RoboDojo's controller interpolating to the targets); grippers are RoboDojo's
normalised command (1 = open, 0 = closed). Privileged helpers: hold, joint moves, gripper ramps, RoboDojo's cuRobo IK
(`ik`, `move_ee`); object poses and bounding boxes; the three cameras (`cam_head` static, `cam_left_wrist`,
`cam_right_wrist`, 640×480, optional z-depth); proprioception; numpy FK/IK of both arms from the X5 URDF; recording,
fresh-process `replay` CLI, video. A reset right after a reset changes nothing, so the first episode in a process is
exactly the grader's; after actions RoboDojo's reset settles the scene again from where it is (same layout and start, not
bit-for-bit the same state), which the instructions say.

## Determinism (measured on Isaac Sim 5.1, RoboDojo's GPU PhysX)
RoboDojo forces PhysX GPU dynamics for every task (`overwrite_gpu_setting(1)`, needed for its cloth and liquids); kept.
Test per task (`make-instance`, then two fresh-process replays of a 120-action trajectory moving both arms and grippers):
- 47 tasks: the three resets and the two replays' end states bit-identical (including the conveyor tasks and the
  support-arm tasks);
- `fold_clothes` and `fold_clothes_random` passed that test too, but the test's trajectory moves the arms without handling
  the garment. Once the cloth is handled it does not replay bit for bit (GPU PhysX cloth): in the first model trial that
  folded it (Codex + GPT-6 Astra, `fold_clothes` standard, 2026-10-10, an L40) the live episode and its two fresh-process
  replays, all started from the exact frozen state (`5fe7775799792961`), ended in three different states (live
  `5d9ed2250495a7d8`, replays `ac5893c4ebbff04c` / `b573a2a98e98f457`), and the trial was scored 0 as not deterministic.
  Both are in the class below since then (their resets are bit-identical, so `instance_exact` stays meaningful for them);
- `make_toast`: 1 of 3 fresh resets differed; with PhysX enhanced determinism (RoboDojo's own sim setting, off by default)
  all agree, so its instance records `"physics": {"enable_enhanced_determinism": true}` and every session, the service and
  the verifier run with it;
- `make_toast_random` (resets differ even with enhanced determinism) and the three liquid tasks (`pour_liquid_into_cup`,
  its random variant, `pour_by_language`: GPU PhysX particles, not bit-reproducible). Their rebuilt layout hashes
  differently in every process by design, so the tooling reports it (`instance_exact` false) and never refuses the
  instance for it (the standard service starts strict otherwise: a rebuilt layout that hashes differently from the
  recorded one is refused on every other task).

**The six tasks whose physics does not replay bit for bit** (`fold_clothes`, `fold_clothes_random`, `make_toast_random`,
`pour_liquid_into_cup`, `pour_liquid_into_cup_random`, `pour_by_language`; instance.json `"determinism": "verdict"` with
the reason) are **standard only, graded by the live episode** (since 2026-10-11, the PROTOCOL exception for declared
non-reproducible physics). An open-loop trajectory of them cannot be graded reproducibly: the same file can succeed in one
fresh replay and fail in the next, so a privileged twin, whose only evidence is replay, would score chance, and the
replays of a standard episode cannot decide either (the `fold_clothes` trial above succeeded live and was scored 0). In
standard mode the trusted service ran the episode and the agent never held the simulator, so the live result is the
verdict: `success = live_success` (`graded_by_live` = 1). The collect hook still replays the episode twice in fresh
processes and reports `replay_success`, `state_identical` and `deterministic` (both replays reach the same verdict); they
never decide, and a replay that gives no result is recorded (`replay_error`) without voiding the live verdict. The cost:
these six scores cannot be recomputed from the trajectory, and a live success may include some luck of the physics. Trials
recorded before 2026-10-11 can be re-scored from their `live_success` without new runs.
Removed on 2026-10-11 (owner; they had been on main for a day, since #142, and their earlier results are kept apart, not
ranked): the six privileged task directories `robodojo-fold-clothes-i00-privileged`,
`robodojo-fold-clothes-random-i00-privileged`, `robodojo-make-toast-random-i00-privileged`,
`robodojo-pour-by-language-i00-privileged`, `robodojo-pour-liquid-into-cup-i00-privileged` and
`robodojo-pour-liquid-into-cup-random-i00-privileged`. The names are not reused. An episode of the six that resumed after a
service crash (resume class `approx`) is graded on its live state after the resume; `reward.json` reports `resumes` and
`resume_state_mismatch` (PROTOCOL §4.8, docs/STANDARD_MODE.md §13.1).
Frozen on one RTX 4090 (driver 580.159). Across GPU models (2026-10-10, the evaluation hosts): the frozen layouts rebuild
to the recorded hashes, and a 120-action driver trajectory ends in the same state as on the 4090, on L40S (drivers
580.178 and 580.82), L40 (driver 610) and L4 (11 instances checked; every graded trial reports `instance_exact`).

## Grading
- privileged: `tests/grade.py` replays `/app/output/trajectory.npz` in two fresh processes; reward 1 iff both succeed and
  end in the same state hash (its verdict branch, both replays succeed, has no RoboDojo task since the six above are
  standard only). `no-network`. A file that is not a trajectory of
  the task (not an npz, pickled or object arrays, another shape, NaN/inf, more than 15,000 rows) is the agent's 0
  (`bad_trajectory`, `wrong_task`); a replay process that ends without a result or runs out of its time is the verifier's
  (`grader_error` = `infra_error` = 1, `replay_failed` / `replay_timed_out`: no verdict on the agent). Only the file's
  `task` and `actions` entries are read (their sizes checked in the archive before anything is decompressed); any other
  entry is ignored. Two replays that did not start from the same state (the frozen layout does not rebuild reproducibly on
  the host) are `instance_unstable`, the verifier's failure too, never a 0 for
  "not deterministic". `instance_exact` reports whether the rebuilt layout hashed as recorded.
- standard: the service ends and dumps the episode on the collect hook's signal; `finalize.sh` replays it in two fresh
  processes, each time-boxed inside the hook's budget and retried once when it dies without a result (Isaac does not exit
  after a fatal GPU error, it waits on a crash dialog, so only the time limit ends it); a replay that still gives no
  result is `replay_error` / `infra_error`, never the agent's 0; `final.json` is replaced atomically.
  `success = live_success ∧ replay_success ∧ deterministic`; for the six standard-only tasks `success = live_success`
  (Determinism, above; a replay without a result is recorded, never `infra_error`). `no-network`. A missing, unreadable or
  unfinalized `final.json` is `infra_error`. `scripts/robodojo/tests/test_standard_grading.py` runs the collect hook and the
  grader on both rules with stand-ins for the simulator (CI: check-unit-tests.sh). The live episode starts from the
  frozen instance (the service is strict); a replay whose process rebuilt the layout to another state is
  `instance_mismatch` (a `replay_error`: `infra_error`), not for the six standard-only tasks.
- Time limits (wall clock only; the verdict rules do not depend on them). Measured on the model trials: Isaac start, scene
  build and RoboDojo's settling 2.5-4 min per process, replays at 7-11 actions/s (the filmed one at the low end). A
  privileged replay has max(1800 s, 1200 s + rows / 2.5) (a third of the slow rate), `[verifier] timeout_sec` = 15000 s
  (two replays of a 15,000-row trajectory + 600 s); the standard collect hook has 18000 s (`finalize.sh`'s
  `HOOK_BUDGET_S`, equal to `[[verifier.collect]] timeout_sec`: the episode end, up to 2700 s through a resume, two
  replays of up to 7200 s, 900 s to spare). A filmed replay never decides a result: a video that cannot be written gives
  `video_ok` false and the replay stands.

## Crash recovery (standard mode, docs/STANDARD_MODE.md §13)
Resume class `exact` (the resumed service is a fresh process whose journal replay is that process's first run), `approx` for
the six standard-only tasks graded by the live episode. `RCB_STARTUP_TIMEOUT_S = 1800`. Acceptance test `scripts/robodojo/kill_test.sh`: RoboDojo
has no oracle, so a driver client (12 joint_position chunks; not a solution) runs as Harbor's oracle on a copy of
`robodojo-general-pickup-i00-standard`, and the service is killed with SIGKILL inside the 6th call, after 5 checkpoints.
Result (2026-10-10, RTX 4090): resumed once, exactly (state hash `224d592a77d3c27f` = the checkpoint's; TCP deviation
2e-7 m), 73 s of downtime, the killed call rolled back and the driver's 11 other chunks ran; finalized, live = both
fresh-process replays, deterministic, no infrastructure error. The driver does not solve the task (success 0 is expected).

## Time budget (D8)
5400 s for every task of both modes: every Python process pays ~2.5-4 min of Isaac Sim launch, scene build and RoboDojo's
settling (a trial's first start also compiles shaders and materials), and many tasks are long (RoboDojo gives policies up to
1900 actions).

## Standard mode (eai-standard/2.2)
`joint_position` (14: RoboDojo's action, rows `dt` apart, a multiple of 1/25 s) and `ee_pose` (16: both arms' link6 targets
+ gripper commands, solved by the arms' kinematic model and executed as a joint move at most 0.25 m/s); cameras `cam_head`,
`cam_left_wrist`, `cam_right_wrist` (640×480, z-depth); `/kinematics` (FK/IK of both arms from the X5 URDF; matches the
simulator's link6 poses); 58 proprio columns. Request checks (PROTOCOL §4.6): every field of a `/submit` or `/observe` is
read and checked before the first action; a malformed request (a wrong type, a value out of range, an `ee_pose` position
more than 3 m from the world origin on any axis, a zero quaternion) is a 400 and executes nothing. Cameras are taken once
each, and one call captures at most 3000 images (cameras × frames, per-frame depth counted again; `/spec`
`max_frames_per_call`): a `joint_position` chunk or an `/observe` that would exceed it is a 400; an `ee_pose` call, whose
length is only known once its IK is solved, keeps executing and stops filming (`meta["frames_capped"]`).

## Declarations
- **Tooling: thin wrappers only.** Joint moves, gripper commands, hold, RoboDojo's IK, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills are never added.
- **World-frame information (D7).** Instructions give the world frame (axes, the arm bases, the table, the head camera) and
  state RoboDojo's check as its code has it, including absolute coordinates where the check uses them (e.g. `make_kong`'s
  target spot); standard tasks never give object poses (privileged tasks give them through the tooling).

## Compute resources (scripts/task_resources.toml)
Measured on the heaviest scene (`pour_liquid_into_cup_random`: GPU PhysX liquid and 15-20 clutter objects), RTX 4090,
2026-10-10, with the trial's monitor and a per-container sampler (docker stats, cgroup anon memory, nvidia-smi every 10 s):
one Isaac Session (privileged main container, or the standard sim sidecar) peaks at 16.0-16.1 GiB of memory and 9.0-9.5 GiB
of GPU memory and uses every core it is given while Isaac starts; a verifier replay (filmed) 15.7 GiB and 9.6 GiB. The
determinism runs over all 54 tasks used 4.6-8.4 GB of GPU memory per process. Minimum per trial: 8 CPUs, 20 GB, 10.5-11
GB of GPU memory, an RTX-class GPU. Limits (PROTOCOL §2.10): privileged, the whole trial 16 GiB of GPU memory and 32 GiB of
memory (the cap every past trial ran under; an agent may run a second Session); standard, the agent's container 8 GiB.
Caps: privileged main 8 CPUs / 39 GiB; standard main 8 CPUs / 16 GiB, sim sidecar 16 CPUs / 25 GiB.

## Image and host
`images/robodojo/` → `ghcr.io/mll-lab-nu/eai-robodojo:0.1.0` (~74 GB, with RoboDojo's 41 GB of assets). It contains Isaac
Sim: **BUILD_ONLY** (`images/robodojo/BUILD_ONLY` has the licences, the build command and the check of a build). Needs an
RTX-class GPU and ~5-10 GB of GPU memory per Isaac process; Isaac hangs instead of exiting when the GPU runs out of memory,
so a shared GPU runs few at once. Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount
their own `*_trusted` cache volumes, scoped to the trial's compose project.

## Licences
RoboDojo: MIT. Its assets (Hugging Face `RoboDojo-Benchmark/RoboDojo`): Apache-2.0. Isaac Lab fork: BSD-3-Clause. cuRobo
fork: NVIDIA's cuRobo licence. Isaac Sim 5.1 and its wheels: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.
