# RoboARC (MuJoCo release)

RoboARC's topological puzzle families on MuJoCo 3.14.0 physics, run by the simulator package `topogym`. This release
**replaces** the Genesis release of these puzzles (user decision, 2026-10-13): the previous Genesis tasks
`<family>-<tier>-i00` (52 bases, image `eai-robotangle:0.2.22`), their generator, their dataset entries and their
benchmark page are removed from the repository; their results are not comparable with this release's and are not
carried over. The new image is built FROM that published image (pinned by digest), whose recipe is kept as
`images/roboarc/Dockerfile.genesis-0.2.22`.

- Name: RoboARC (display) / `roboarc` (task prefix, image `eai-roboarc`, `scripts/roboarc/`, `images/roboarc/`, this
  page; owner, 2026-10-13). Until then the release was prepared under the working names `robotangle-new` and
  `robotangle`; Harbor records and image tags of those runs keep the names they had. Code identifiers keep the
  simulator's name: the package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables, the family keys
  (`interlocked_claws`), and the development branch dev/robotangle_mujoco with its `scripts/robotangle/` and
  `images/robotangle/`; inside the image, `/opt/robotangle/` (the instances and `stage_instance.py`).

## Tasks

`roboarc-<family>-<NN>-i01-{privileged,standard}` (PROTOCOL §2.2):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<NN>`: two digits, the base's number in its family. A number is never reused: removing a task leaves a gap. The
  difficulty is not in the name: it is `[metadata].difficulty` in task.toml (TAXONOMY).
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<NN>-i01/`).
- `scripts/roboarc/roboarc_names.json` maps every base of the working names to its RoboARC name: old base -> new base,
  family, number, difficulty.

Every task is RoboARC's task contract (the same tooling `rcb_topogym.py`, graders, sim service and eai-standard/2.4
layer as RoboARC; docs/benchmarks/roboarc.md, "Grading and determinism", "Standard mode") with these differences:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Generator and release

- `scripts/roboarc/mk_tasks.py` (`--check` in CI) renders the task dirs from this directory: `release.json`,
  `packages/` (the texts of the RoboARC base each task ports, renamed, with the family's own texts over them),
  `oracles/`, `assets.json`, `shared/` (the tooling and the graders). Generated tasks end with
  `scripts/task_conventions.py` normalize.
- The release files are written by `scripts/robotangle/release_rebuild.py --onto <main>` on dev/robotangle_mujoco
  (its `mujoco_release.json` names each base: a tier through its family's `numbers`, a new design by its key): image,
  instances made in the image, release files, render, checks, Harbor oracle / nop.
- Large files: the frozen instances are in the private HF dataset `eai-v2-internal/robotangle-assets` (shared with the
  Genesis release), under `instances/<base>/`, pinned file by file in `scripts/roboarc/assets.json`.
- Image: `ghcr.io/mll-lab-nu/eai-roboarc:<images/roboarc/VERSION>`, built FROM the published
  `eai-robotangle:0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/roboarc/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `scripts/roboarc/fetch_image_context.sh`).

## Time budget (D8)

10800 s (3 h) wall clock in both modes and every family (user, 2026-10-13; 7200 s from 2026-10-12; each task's `[agent] timeout_sec`), within the default cap: no exception.
(The Genesis release had 21600 s, then 7200 s from 2026-10-12.) The texts say "the time limit (`## Time limit`)". The standard service's clock
(`meta["time_left_s"]`, `RCB_WALL_CLOCK_S` follows the table) counts from the agent's first request to the service (PROTOCOL §2.12;
logged in `episode.jsonl`, kept over a restart), so the instruction has the common closing sentence and no sentence of its own about the
service's clock (2026-10-13; the Genesis release's "has run since the service first started" is not carried over). The service still ends the
episode with reason `timeout` when that count reaches 0; counted from the first request, that is never before the harness's cutoff.
The plan (2026-10-13, moved from PROTOCOL §2.12 on 2026-10-14): that end becomes report-only at RoboARC's next task update.

## Grading replays (privileged: the strict goal within the agent's rows, 2026-10-14)

The six families with a grading hold (blanket-flatten, knot-untying, lock-picking, orbits, rope-threading, slotted-post-ring;
`rcb_topogym.REPLAY_TOLERANCES`) replay a trajectory with the instance's own thresholds and, if the episode has not ended after
the last row, hold the final targets for up to 2 s; during that hold blanket-flatten accepts 92 % coverage and 80 mm/s cloth
speed (95 % and 30 mm/s in the rows) and knot-untying a rope speed 0.25 mm/s higher. Standard mode grades the live episode
strictly and lets its replay confirm in the hold.

**The rule.** Privileged success needs both grading replays to succeed AND at least one of them to reach the goal with the
instance's own thresholds within the trajectory's rows (`tests/grade.py`: `strict_replay_required` 1, `strict_goal_reached`,
`strict_goal_row`; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). This
is tooling v16's rule; the packages' texts always stated it, and the instruction now says where `s.replay(actions,
grading=True)` reports it (`["grading"]["strict_success"]`).

**Why it changed back.** From 2026-10-05 to 2026-10-14 (R-hold) every privileged replay could confirm within the hold and no
strict goal was required, because on the Genesis release's non-deterministic GPU physics the replay of a recording that
stopped on its own success had no margin. Privileged mode has no graded live run, so the hold's relaxed thresholds became
the effective goal: GPT-6 Luna's two privileged blanket-flatten successes of 2026-10-14 (`…blanket-flatten-01…__gHEcmjR`,
`…blanket-flatten-06…__WJTFiD9`) never reached 95 % (`strict_goal_reached` 0, `replay_tolerance_needed` 1); one said so
("this pass uses the benchmark's documented 92% replay threshold"), the other appended two seconds of still rows "for the
verifier's stated 92%" (failure analysis 2026-10-14, item 12). The MuJoCo release replays deterministically on the same
host (the cloth step on a deterministic GPU solver, the rest on the CPU), so a recording that stops on its own success
reaches it within its rows. Requiring the strict goal makes privileged mode ask for what the task text and standard mode
ask for; stating 92 % as the goal instead would have lowered the goal in privileged mode only.

**Consequences.** Same task names and frozen instances. Every privileged task gets a new digest (`tests/grade.py` is one
file shared by all 94); the verdicts can change only in the 30 tasks of the six families with a hold, since a replay of the
other families succeeds only within the rows. The standard twins are unchanged. Of the privileged results on record
(GPT-6 Luna, 10-14), the two blanket-flatten successes above become failures; every other privileged success had
`strict_goal_reached` 1.

**Re-grading existing results** (nothing is re-run). `scripts/roboarc/regrade.py JOBS_DIR ... [--replay] --out
regrade.jsonl` reads every RoboARC privileged trial under the Harbor jobs trees and gives its recorded verdict, the old
rule's and the new rule's:
- without `--replay`, from the trial's recorded `verifier/reward.json` alone: the new verdict is the recorded success AND
  `strict_goal_reached` (the grader before this change recorded it next to the verdict). This is exact: the replays are
  deterministic on the host class they ran on, and the rule only adds that condition;
- with `--replay`, it also replays the recorded `artifacts/app/output/trajectory.npz` with the current task's own
  `tests/grade.py` in the task's verifier image (docker, GPU), the verifier's two replays, and reports both verdicts from that
  run (old = the replays succeed; new = the current `success`); a trial whose recorded success the replay does not reproduce
  under the old rule is `inconclusive` (re-grade it on the host class it ran on).

Only the 94 tasks of the RoboARC 0.1.0 release are re-graded; a trial of any other task (a later RoboARC task, a Genesis
`robotangle-*` task) is listed as `skipped` with the reason. Standard trials are skipped too: their grading did not change.

**Validation.** 2026-10-14, ws (RTX 4090, `eai-roboarc:0.1.0`, Harbor `-a oracle` / `-a nop`, jobs
`rav1-{oracle,nop}-<task>`) with this version's privileged `tests/`: the privileged oracle scores 1 with
`strict_goal_reached` 1 on blanket-flatten-01, knot-untying-01, lock-picking-01, orbits-01, rope-threading-01,
slotted-post-ring-01 (one task of each family with a hold) and interlocked-claws-01 (a family without one), deterministic, no
infra or grader errors; nop scores 0 on blanket-flatten-01 and slotted-post-ring-01 privileged. The rule change itself, by
construction (the recorded trials' trajectories are not retrievable): blanket-flatten-01's reference without its last 8 rows
(a recording that stops 8 control steps before its own success; the replay confirms after 8 steps of hold) is graded 1 by the
previous `grade.py` (`all_success` 1, `strict_goal_reached` 0) and 0 by this one (`all_success` 1, `success_in_hold_only` 1),
both deterministic. Without its last 40 rows it fails both (the hold's 2 s do not complete the confirmation).

## Safety readings in standard mode (`meta["safety"]`)

Owner decision, 2026-10-10: the standard service keeps publishing `meta["safety"]` in every response, and the protocol
records it as a declared exception to "no object contact forces". Why: the benchmark's physical-validity policy judges
the agent on these readings -- a success with a deep task contact is held for human review instead of credited, a
soft body that stays collapsed ends the episode, a simulator breakdown shortly after forcing is the agent's failure --
so an agent that could not see them would be judged on something it cannot measure. The fields are exactly what
`rcb_topogym._SafetyMonitor.read` returns (maxima since the previous response, each next to its limit), and nothing
else of the simulator's contact state is published:

| Field of `meta["safety"]` | What it is | Families |
|---|---|---|
| `rules`, `scope` | the policy's revision; "since the previous read" | all |
| `forcing` | `max_press_force_n` (the largest total contact force an arm's gripper, or a part it holds, pressed on anything else with), `max_drive_fraction_while_pressing`, `longest_forcing_s`, `events`, the last three events (each: the arm and joint, the control step, the drive fraction and cap, the force, and in words what pressed on what, e.g. "a part it holds" on a named task part), and the thresholds (`contact_n`, `near_cap_fraction`, `event_after_s`) | all |
| `task_contact_mm` | the deepest contact between task parts (`max`), the longest time above the sustained limit, and the review and breakdown limits | rigid |
| `held_finger_contact_mm` | the deepest contact between a finger and the part it holds, with its review limits | rigid |
| `review` | the count of review events and the last three (each: the kind, the control step, the names of the two task parts in contact, the depth in mm and the force in N); a success with one is held for review | rigid |
| `soft_volume_ratio` | the lowest volume ratio of each soft body and the longest time at or below 0 | soft (rope, cord, cloth) |
| `attachment_stretch_mm` | the worst cord attachment stretch and the longest time above its limit | soft |
| `table_guard` | the control steps whose gripper target the table guard stopped, with the last events | where the guard applies |
| `ik_jumps` | the last IK solutions that lay far from the current joints (`ee_pose` actions) | when one occurred |

These are forces, depths, ratios and the names of the parts involved, never a pose: no field says where an object is.
A change to this list is a change of the declaration and goes through the protocol-change process (PROTOCOL §6).

User decision 2026-10-13: this release publishes main's declared fields again, with the names of the parts involved (names are allowed in standard mode; only positions / poses in the simulator's world frame, the table height and physics parameters are withheld). The service's `robot_felt` passes exactly these fields (`SAFETY_PUBLISHED`); `scripts/roboarc/tests/test_server_requests.py` checks the list and the names.

## Standard mode, world frame, network

`eai-standard/2.4` (as the Genesis release); no world coordinates in standard texts (D7,
`scripts/roboarc/ci/advisory-world-frame.sh`); agent egress on the allowlist (PROTOCOL Appendix H.6).

Every text the agent sees calls the service's frame the world frame, as main's other services call theirs, and defines it in
words; it is the robot frame: 
The agent-facing frame of the standard service is the robot frame (user, 2026-10-13: the table height and the robot base's
world position are never disclosed): origin at the robot's kinematic root link on its mounting, axes as the simulator's world
(+z up). The proprio TCP poses, `ee_pose` targets, `/kinematics` (ik targets, fk poses) and the camera extrinsics (static
mounts, per-observe calibration, per-frame `extrinsic_cv`) are in it; `robot_spec.base.pose` is the identity; no text and no
`/spec` field states a world coordinate of the mounting. `joint_position` rows, physics, graders and state hashes do not depend
on the frame. Privileged mode keeps the simulator's world frame (its tooling is the simulator); its texts state no table height
or robot base position either.

## Registration (the lines a rename changes)

`BENCH` in `scripts/roboarc/mk_tasks.py` and `--bench` of dev/robotangle_mujoco's `scripts/robotangle/release_rebuild.py`;
`git mv` of `scripts/roboarc/`, `images/roboarc/` and this page; then the registration lines: `scripts/task_conventions.py`
(`BENCHMARKS`), `scripts/task_resources.toml`
(the `^roboarc-` rules), `docs/TAXONOMY.md`, `README.md`, the checks that name a benchmark's prefix or generator
(`ci_checks/check-tooling-identity.sh` `MODULE`, `scripts/roboarc/ci/advisory-world-frame.sh`, `check-generated-tasks.sh`,
`check-unit-tests.sh`); the cutoff is each task's own `[agent] timeout_sec` (the generator's constant).

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Serves `eai-standard/2.4` (STANDARD_MODE Part 4; it was first served by RoboTangle's standard tasks, whose release called it "2.3"). Contact and safety telemetry is published in `meta["safety"]`, declared field by field in this doc. `max_frames_per_call` = 2000, per-frame depth counted as four images; where a call's length is known only while it runs (`ee_pose` rows) the call stops taking frames at the bound and `meta.frames_skipped` counts them. Its service ends the episode when `time_left_s` reaches 0 until its next task update; since its MuJoCo release (2026-10-13) the clock counts from the agent's first request like the others.
