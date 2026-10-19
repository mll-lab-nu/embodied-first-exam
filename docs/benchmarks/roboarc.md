# RoboARC (MuJoCo release)

RoboARC's topological puzzle families on MuJoCo 3.14.0 physics, run by the simulator package `topogym`. The image is
built FROM the published `eai-robotangle:0.2.22` image (pinned by digest), whose recipe is kept as
`images/roboarc/Dockerfile.genesis-0.2.22`; results of the earlier Genesis release are not comparable with this one.

- Name: RoboARC (display) / `roboarc` (task prefix, image `eai-roboarc`, `images/roboarc/`, this
  page). Code identifiers keep the simulator's name: the package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables, the family keys
  (`interlocked_claws`), and the development branch dev/robotangle_mujoco with its `scripts/robotangle/` and
  `images/robotangle/`; inside the image, `/opt/robotangle/` (the instances and `stage_instance.py`).

## Tasks

`roboarc-<family>-<NN>-i01-{privileged,standard}` (PROTOCOL §2.2):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<NN>`: two digits, the base's number in its family. A number is never reused: removing a task leaves a gap. The
  difficulty is not in the name: it is `[metadata].difficulty` in task.toml (TAXONOMY).
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<NN>-i01/`).

Every task shares the tooling `rcb_topogym.py`, the graders, the sim service and the eai-standard/2.4 layer:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the privileged images (agent `/opt/tools/`, verifier `/tests/`) take `rcb_topogym.py`, `render_bridge.py` and
  `nyx_direct.py` from the files-only image `ghcr.io/mll-lab-nu/efe:roboarc-files-<version>` (`images/roboarc-files/`, built
  from `embodied_first_exam/benchmarks/roboarc/`; `FILES.json` pins its digest and the files' sha256) with
  `COPY --from=<image@digest>`: the privileged task dirs carry no copy. The standard sim service keeps its copies in `environment/sim/` (bind-mounted);
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Release

- The shared task code (the tooling, the graders, the sim service, the standard oracle player) has one source,
  `embodied_first_exam/benchmarks/roboarc/`. A change to a file of `images/roboarc-files/FILES.json` needs a new image
  version: `images/roboarc-files/VERSION`, `python3 scripts/files_image.py build roboarc-files`, push,
  `files_image.py pin roboarc-files <digest>`, then the tasks' `COPY --from` lines name the new digest; until then
  `scripts/files_image.py check` fails.
- The files a task carries are in `tasks/`: the privileged reference
  (`tasks/roboarc/roboarc-<base>-privileged/solution/trajectory.npz`, both modes), the instance's lock (that task's
  `tests/runtime_binding.json`), the goal-state images (its `environment/goal/`) and the standard agent Dockerfile.
  The privileged reference must be the file `images/roboarc/release.json`'s evidence names (`trajectory_sha256`).
  The task directories are the deliverable; the tooling that built them is kept outside this repository.
- The release files are written by `scripts/robotangle/release_rebuild.py --onto <main>` on dev/robotangle_mujoco
  (its `mujoco_release.json` names each base: a tier through its family's `numbers`, a new design by its key): image,
  instances made in the image, release files, render, checks, Harbor oracle / nop.
- Large files: the frozen instances are in the private HF dataset `eai-v2-internal/robotangle-assets` (shared with the
  Genesis release), under `instances/<base>/`, pinned file by file in `images/roboarc/assets.json`.
- Image: `ghcr.io/mll-lab-nu/efe:roboarc-<images/roboarc/VERSION>`, built FROM the published
  `eai-robotangle:0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/roboarc/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `images/roboarc/fetch_image_context.sh`).

## Time budget

10800 s (3 h) wall clock in both modes and every family (each task's `[agent] timeout_sec`), within the default cap.
The texts say "the time limit (`## Time limit`)". The standard service's clock (`meta["time_left_s"]`, `RCB_WALL_CLOCK_S`
= the cutoff) counts from the agent's first request to the service (logged in `episode.jsonl`, kept over a restart), so
the instruction has the common closing sentence. The service still ends the episode with reason `timeout` when that
count reaches 0, never before the harness's cutoff; open: that end becomes report-only at RoboARC's next task update.

## Grading replays (privileged: the strict goal within the agent's rows)

The six families with a grading hold (blanket-flatten, knot-untying, lock-picking, orbits, rope-threading, slotted-post-ring;
`rcb_topogym.REPLAY_TOLERANCES`) replay a trajectory with the instance's own thresholds and, if the episode has not ended after
the last row, hold the final targets for up to 2 s; during that hold blanket-flatten accepts 92 % coverage and 80 mm/s cloth
speed (95 % and 30 mm/s in the rows) and knot-untying a rope speed 0.25 mm/s higher. Standard mode grades the live episode
strictly, with no grading replay (Standard grading, below).

**The rule.** Privileged success needs both grading replays to succeed AND at least one of them to reach the goal with the
instance's own thresholds within the trajectory's rows (`tests/grade.py`: `strict_replay_required` 1, `strict_goal_reached`,
`strict_goal_row`; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). The
instruction says where `s.replay(actions, grading=True)` reports it (`["grading"]["strict_success"]`). Why: the MuJoCo
release replays deterministically on the same host (the cloth step on a deterministic GPU solver, the rest on the CPU), so
a recording that stops on its own success reaches it within its rows; without the strict goal the hold's relaxed
thresholds would become the effective goal in privileged mode only.

**Validation** (Harbor `-a oracle` / `-a nop`, `eai-roboarc:0.1.0`): the privileged oracle scores 1 with
`strict_goal_reached` 1 on one task of each family with a hold and on interlocked-claws-01, deterministic; nop scores 0.
blanket-flatten-01's reference without its last 8 rows (a recording that stops 8 control steps before its own success)
is graded 0 (`all_success` 1, `success_in_hold_only` 1).

## Standard grading: the live episode

`success` = the live success: the task predicate on the live simulator with the instance's own thresholds, confirmation
window included (`server.py`: after every `submit` and every watching `observe`, and as the episode stands at its end),
recorded in `episode.json`. No grading replay runs. `finalize.sh` writes `final.json` from `episode.json` first
(`graded_by` live, `replays` 0, `state_sha` = the live end-state hash, `video_pending` 1), then runs ONE video-only pass
(`replay.py`: a plain fresh-process replay of the live rows on the sidecar's GPU that renders `replay.mp4` and, for a
success held for review, the frames around its live review events; record `replay.video.json`). It never changes the
verdict, and a failed, killed or GPU-less pass loses only the video. `tests/grade.py` transcribes the result. In `final.json`, `live_success` is the live episode's own success and `success` the verdict: false with an infrastructure failure or when the success is held for review (`held_for_review`). A service that dumped its episode but did not exit in time keeps that live verdict (`service_exit_timed_out`, no video). A missing `trajectory.npz` is recorded (`dump_error`) and changes no verdict. Non-finite numbers are written as null.
- **No hold.** The live episode gets no hold (a hold would loosen the rule: the privileged twin needs a strict success
  within the agent's rows).
- **Review, forcing, instability.** The live episode's `review` (deep task contacts: a live success is held for review,
  `success_pending_review`), `forcing` (evidence) and `simulator_instability` (a breakdown without forcing: infrastructure).
- **Start state.** `Session(strict=True)` checks the frozen instance against `runtime_binding.json` when the service builds
  it. A mismatch is `instance_mismatch`, `infra_error 1`, before anything is served. `tests/grade.py` also checks the live
  startup record (`startup_binding.json`) against its own copy of the binding.
- **Infrastructure** (H.5): no, unreadable or unfinalized `final.json`, the end timed out, `instance_mismatch`, a give-up
  after crashes not all inside the agent's calls (`sim_crashed`, `resume_failed`, `call_watchdog`), `simulator_instability`
  in the live episode, a simulator error (reason `error`). The agent's 0: the task's failure predicate,
  `forced_breakdown`, the wall clock, `step_guard`, `sim_crashed_on_call`. A video-pass error or a GPU lost after the
  episode never voids a trial.
- **Re-scoring recorded standard trials.** The verdict is the recorded live fields of `final.json`: the `success` of
  `episode.json`. A live instance mismatch, `infra_error` or `simulator_instability` voids it, and a live `review` holds
  it.

## Safety readings in standard mode (`meta["safety"]`)

The standard service publishes `meta["safety"]` in every response, declared here as allowed by PROTOCOL H.3. Why: the benchmark's physical-validity policy judges
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
A change to this list is a change of the declaration and goes through the protocol-change process (PROTOCOL §7).

Names of the parts involved are allowed in standard mode; positions / poses in the simulator's world frame, the table
height and physics parameters are withheld. The service's `robot_felt` passes exactly these fields (`SAFETY_PUBLISHED`).

## Standard mode, world frame, network

`eai-standard/2.4`; no world coordinates in standard texts (D7,
`ci_checks/benchmarks/roboarc/advisory-world-frame.sh`); agent egress on the allowlist (PROTOCOL Appendix H.6).

Every text the agent sees calls the service's frame the world frame, as the other services call theirs, and defines it in
words; it is the robot frame (the table height and the robot base's world position are never disclosed): origin at the robot's kinematic root link on its mounting, axes as the simulator's world
(+z up). The proprio TCP poses, `ee_pose` targets, `/kinematics` (ik targets, fk poses) and the camera extrinsics (static
mounts, per-observe calibration, per-frame `extrinsic_cv`) are in it; `robot_spec.base.pose` is the identity; no text and no
`/spec` field states a world coordinate of the mounting. `joint_position` rows, physics, graders and state hashes do not depend
on the frame. Privileged mode keeps the simulator's world frame (its tooling is the simulator); its texts state no table height
or robot base position either.

## Registration (the lines a rename changes)

`--bench` of dev/robotangle_mujoco's `scripts/robotangle/release_rebuild.py`;
`git mv` of `images/roboarc/`, `images/roboarc-files/` (a new image name: build, push, pin) and this page; then the registration lines: `scripts/task_conventions.py`
(`BENCHMARKS`), `scripts/task_resources.toml`
(the `^roboarc-` rules), `docs/TAXONOMY.md`, `README.md`, the checks that name a benchmark's prefix
(`ci_checks/check-tooling-identity.sh` `MODULE`, `ci_checks/benchmarks/roboarc/advisory-world-frame.sh`); the cutoff is
each task's own `[agent] timeout_sec`.

## Standard-mode service details

Serves `eai-standard/2.4` (docs/protocol/standard_mode.md Part 4). Contact and safety telemetry is published in `meta["safety"]`, declared field by field in this doc. `max_frames_per_call` = 2000, per-frame depth counted as four images; where a call's length is known only while it runs (`ee_pose` rows) the call stops taking frames at the bound and `meta.frames_skipped` counts them. Its service ends the episode when `time_left_s` reaches 0 (counted from the agent's first request), until its next task update.

