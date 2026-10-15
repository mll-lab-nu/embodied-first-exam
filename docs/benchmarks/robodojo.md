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
standard `general_pickup` succeeded (graded by the task's verifier as it was then: two fresh-process replays, identical end states);
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
the reason) are **standard only, graded by the live episode** (since 2026-10-11, PROTOCOL §4.8's live grading for declared
non-reproducible physics). An open-loop trajectory of them cannot be graded reproducibly: the same file can succeed in one
fresh replay and fail in the next, so a privileged twin, whose only evidence is replay, would score chance, and the
replays of a standard episode cannot decide either (the `fold_clothes` trial above succeeded live and was scored 0). In
standard mode the trusted service ran the episode and the agent never held the simulator, so the live result is the
verdict: `success = live_success` (`graded_by_live` = 1). The collect hook still replays the episode in a fresh process
(once since 2026-10-12, twice before) and reports `replay_success`, `state_identical` (the replay ended in the live
episode's state) and `deterministic` (the replay reached the live episode's verdict); they
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
**One replay** (the owner's decision of 2026-10-12, to save grading time: "one successful replay is enough"; PROTOCOL §3
and §4.8 record the exception). Until then both modes replayed the trajectory in two fresh processes and required both to
succeed and to end in the same state hash. The second replay was the determinism check; on the 48 tasks that replay bit
for bit it had never disagreed (below), and it cost 29-48 % (median 44 %) of the replay time of a trial.
- privileged: `tests/grade.py` replays `/app/output/trajectory.npz` once, in a fresh process (`test.sh`: `--repeat 1`);
  reward 1 iff that replay succeeds. `no-network`. A file that is not a trajectory of
  the task (not an npz, pickled or object arrays, another shape, NaN/inf, more than 15,000 rows) is the agent's 0
  (`bad_trajectory`, `wrong_task`); a replay process that ends without a result or runs out of its time is the verifier's
  (`grader_error` = `infra_error` = 1, `replay_failed` / `replay_timed_out`: no verdict on the agent). Only the file's
  `task` and `actions` entries are read (their sizes checked in the archive before anything is decompressed); any other
  entry is ignored. With one replay there is no second end state: `deterministic` and `state_identical` are written as 1
  (nothing disagreed) next to `determinism_checked` = 0 and `replays` = 1, which say that nothing was compared; a reader
  that asks for `success` and `deterministic` keeps working. `replay_success` = `all_success` = the replay's own result.
  What two replays showed by starting from the same state (`instance_unstable` otherwise) is now shown against the
  recorded hash: a replay whose process rebuilt the frozen layout to another state than `instance.json` records
  (`instance_exact` = 0) did not start from the frozen state and gives no verdict, whatever it ended in
  (`instance_mismatch`, `grader_error` = `infra_error` = 1), as in standard mode. Every graded trial so far rebuilt it
  exactly, on every host. `grade.py --repeat 2` is still the two-replay check, for a determinism measurement by hand.
- standard: the service ends and dumps the episode on the collect hook's signal; `finalize.sh` replays it once, in a
  fresh process, with the privileged replay's allowance for the episode's length inside the hook's budget, and runs it
  once more when it dies without a result or runs out of that allowance while the hook has time left (Isaac does not exit
  after a fatal GPU error, it waits on a crash dialog, so only a time limit ends it); a replay that still gives no
  result is `replay_error` / `infra_error`, never the agent's 0; `final.json` is replaced atomically.
  `success = live_success ∧ replay_success`: one successful replay is enough. The two halves guard each other: a live
  success that does not repeat in the replay is 0, and so is a replay that succeeds where the live episode did not. The
  replay still has something to be compared with, the live episode's end state: `deterministic` = `state_identical` =
  `live_matches_replay` = the replay ended in that state (`determinism_checked` = 1). It is reported and no longer
  decides: a replay that succeeds in another end state than the live episode passes. For the six standard-only tasks
  `success = live_success` (Determinism, above; a replay without a result is recorded, never `infra_error`). `no-network`.
  A missing, unreadable or unfinalized `final.json` is `infra_error`. The live episode starts from the frozen instance
  (the service is strict); a replay whose process rebuilt the layout to another state is `instance_mismatch` (a
  `replay_error`: `infra_error`), not for the six standard-only tasks. `final.json` says `replays` = 1 and has one
  `replay_rc`; `replay_sha2` and `replay2.log` are gone.
- The one replay is the filmed one (`replay.mp4`). A filmed replay never decides a result: a video that cannot be written
  gives `video_ok` false and the replay stands. Filming slows the replay (below); the limits are sized for it.
- What one replay gives up: a trajectory whose outcome differs between fresh processes is no longer caught by the grader
  (privileged: it scored 0 as not deterministic; now the one replay's result stands. Standard: the live episode and the
  replay must still both succeed). On the 48 tasks graded this way the physics replays bit for bit: in the first 38
  graded trials of the run that began on 2026-10-11 (36 on these tasks, on AWS and both Slurm clusters) the two replays
  ended in the same state every time, and so did the live episode and its replay; no verdict changes when they are
  re-read under this rule (`all_success` / `replay_success` with `state_identical` in the saved `reward.json`), and no
  trial is rerun.
- Unit tests with stand-ins for the simulator (CI: check-unit-tests.sh): `scripts/robodojo/tests/test_standard_grading.py`
  runs the collect hook and the standard grader on both rules, `test_privileged_grading.py` the privileged grader; both
  check that exactly one replay process runs (in the hook two when the first gave no result and was run again; the
  privileged grader never runs one again), and that it is the filmed one.
- Time limits (wall clock only; the verdict rules do not depend on them), for ONE replay since 2026-10-12. Measured in
  the pool on 2026-10-11/12 (35 graded trials on loaded hosts, trajectories of up to 6,241 actions): 47-427 s from the
  start of a replay process until the layout is ready (427 s: a cold first start, which every privileged verifier's
  replay is); the filmed replay at about 4.9-10.8 actions/s (median 7.1), an unfilmed one at 5.6-14.7 (median 10.0;
  from the file times of the 18 standard trials). A replay's allowance is unchanged, max(1800 s, 1200 s + rows / 2.5):
  2.8 times the slowest start and twice the time the slowest filmed rate needs, so 7200 s for the 15,000 rows a
  trajectory may have (the slowest measured start and rate would need 427 + 15,000 / 4.9 = 3490 s). What came down is
  what was sized for two: `[verifier] timeout_sec` (privileged) 15000 s -> **7800 s** (one replay of 15,000 rows + 600 s
  for the grader and the resource step); the standard collect hook 18000 s -> **10800 s** (`finalize.sh`'s
  `HOOK_BUDGET_S`, equal to `[[verifier.collect]] timeout_sec`: the episode end, up to 2700 s through a resume, one
  replay of up to 7200 s, 900 s to spare). Inside it the hook's replay now has the same allowance for its length as the
  privileged one, never more than what is left before the deadline minus 300 s; until 2026-10-12 a replay had its share
  of the whole remaining budget whatever the episode's length, so a hung Isaac held the hook for about 2.5 h; now it is
  ended after the allowance (1800 s for an episode of up to 1,500 actions) and run once more if time is left. An episode
  whose length cannot be read keeps the whole remaining budget. The standard verifier keeps 1200 s (it only reads files). A trial
  can now take at most 3600 + 7800 = 11400 s (privileged; 18600 before) and 3600 + 10800 + 1200 = 15600 s (standard;
  22800 before). Typical, from the same trials: the privileged verifier took 3.9-27 min with two replays and the
  collect hook 6-25 min; the filmed replay of the standard trials alone took 3-15 min.

## Crash recovery (standard mode, docs/STANDARD_MODE.md §13)
Resume class `exact` (the resumed service is a fresh process whose journal replay is that process's first run), `approx` for
the six standard-only tasks graded by the live episode. `RCB_STARTUP_TIMEOUT_S = 1800`. Acceptance test `scripts/robodojo/kill_test.sh`: RoboDojo
has no oracle, so a driver client (12 joint_position chunks; not a solution) runs as Harbor's oracle on a copy of
`robodojo-general-pickup-i00-standard`, and the service is killed with SIGKILL inside the 6th call, after 5 checkpoints.
Result (2026-10-10, RTX 4090): resumed once, exactly (state hash `224d592a77d3c27f` = the checkpoint's; TCP deviation
2e-7 m), 73 s of downtime, the killed call rolled back and the driver's 11 other chunks ran; finalized, live = both
fresh-process replays, deterministic, no infrastructure error. The driver does not solve the task (success 0 is expected).

## Time budget (D8)
The number is each task's own `[agent] timeout_sec`, written by the generator ([`../CUTOFFS.md`](../CUTOFFS.md); PROTOCOL
§2.12): 3600 s (one hour) for every task of both modes on 2026-10-11, the owner's decision of that day (5400 s before,
from #142 on 2026-10-10; no official result was published with 5400 s, and the trials recorded with it are kept apart).
The cost that had argued for the longer budget is unchanged and is what an agent has to plan around: every Python process
pays ~2.5-4 min of Isaac Sim launch, scene build and RoboDojo's settling (a trial's first start also compiles shaders and
materials), and many tasks are long (RoboDojo gives policies up to 1900 actions), so an hour holds about a dozen simulator
starts at most.
Every instruction states the cutoff in the closing `## Time limit` section (written by `task_conventions.normalize`
from the table, like `[agent] timeout_sec`, the README row and the standard service's `RCB_WALL_CLOCK_S`, which only
reports the budget: `spec["budget"]`, `meta["time_left_s"]`; the service never ends an episode on it). RoboDojo's own
text adds, right after the task's introduction and without a number: privileged, `/app/output/trajectory.npz` must be
written before the time limit is up and every `Session` start counts; standard, the task must be completed before it and
the wait for the service counts. `mk_tasks.py` keeps no copy of the number (`agent_timeout()` reads the table for what it
renders), and `ci_checks/check-cutoffs.py` fails a task whose files disagree with the table or whose instruction states
the limit a second time. Nothing else is derived from the agent's limit: the verifier and collect-hook
limits above come from the 15,000-action cap and the replay speed, `RCB_STARTUP_TIMEOUT_S` from the scene build.

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

## Known issues (board 0086, 2026-10-14)
- **Joint limits in `/spec` and `robot_spec()`** are the articulation's soft limits as Isaac Lab reports them (about
  +-10 rad for several joints). Two trials found the arm's joint4 stopping at about +-1.78 rad. Not verified in the
  simulator here, so neither the instructions nor the limits have been changed.
- **Privileged `s.reset()`** in a long-lived process is not always reliable after an articulated object moved ("articulation
  not found", or "All scene Unstable Error"); a fresh process (as the verifier uses) always builds the frozen start.
- **`pack_objects_into_box(_random)`**: "front sides facing left" is the assets' own axis convention (the checkpoint
  point's -x, the shoe's root +x), which images do not show; every standard run failed it.
- Fixed in the instructions on 2026-10-14 (text only, RoboDojo's checks unchanged): `sort_nesting_dolls_by_size(_random)`
  had the size order reversed (the config's comments call index mod 5 = 4 the largest doll; the dolls' measured sizes say
  it is the smallest); `swap_blocks`' button rests at about 0.79 of its travel, below the 0.9 / 0.95 its stages and press
  counter need; `hang_mugs(_random)`' orientation conditions use the first functional point of each tag.

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

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Serves `eai-standard/2.2`. Resume class `exact` (Isaac Lab, GPU PhysX: the resumed service is a fresh process, whose first run is bit-exact, measured on 48 of its 54 tasks; `make_toast` with PhysX enhanced determinism); `approx` for its six standard-only tasks graded by the live episode (`make_toast_random`, the three liquid tasks and the two cloth tasks: GPU PhysX particles and cloth do not replay bit for bit). For those six the verdict after a resume is the live state the resumed service continued from; `reward.json` reports `resumes` and `resume_state_mismatch`, at most two resumes are allowed as everywhere, and a success with `resumes > 0` is reported with those fields. `max_frames_per_call` = 3000.
