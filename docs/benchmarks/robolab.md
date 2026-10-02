# RoboLab

[NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 on Isaac Lab 2.3.2 / Isaac Sim 5.1: tabletop language-goal tasks
for a Franka with a Robotiq 2F-85 (DROID joint-position actions). `simulator = "robolab"`, `robot = "franka-robotiq-2f85"`.
53 families, each as a privileged task `robolab-<family>-i00-privileged` and its standard twin
`robolab-<family>-i00-standard` (`eai-standard/2.2`), on the same frozen instance.

## Tasks and generator
- One generator: `python3 scripts/robolab/mk_tasks.py` writes every RoboLab task dir (both modes) from
  `scripts/robolab/` alone: `families.json` (per family: RoboLab's task class and file, the goal, the success term's
  source, the texts of both modes, the oracle level, the cited positives), `instances/<family>.json` (the frozen
  instances), `oracles/<family>/` (the reference solutions and the standard oracle's recorded joint targets), `shared/`
  (the tooling `rcb_robolab.py`, the oracles' skills `ref_primitives.py`), `template/<mode>/` (every other task file) and
  `scripts/eai_standard/` (the 2.2 layer and the standard client). Both twins of a family are written to a scratch
  directory, passed through `scripts/task_conventions.py`'s `normalize()` (the v1.0 conventions: names, README layout,
  `rm -rf /logs/verifier/*` first in `test.sh`, no `results/`) and then synced into `tasks/`. Re-running it leaves
  `git diff tasks/` empty; `--check` only compares.
- A family is RoboLab's benchmark task of that name, its success predicate RoboLab's own `success` termination term.
  `families.json` holds 88 frozen families; 53 have tasks (`tasks: true`): the 2 with a reference solution and the 51 with
  a graded positive example. The other 35 have no positive yet (PROTOCOL §2.7 needs one before review) and stay out
  until they do; their entries and instances are kept.
- The frozen instance is the full scene state after RoboLab's canonical seeded reset (`env.reset()` twice, as RoboLab's
  evaluation loop does), with its state hash, made in the image by `rcb_robolab.py make-instance --task <f> --seed 0`;
  the tasks carry it in `environment/` and `tests/` (privileged) and `environment/sim/` (standard). Each instance was
  checked in a second fresh process: the same hash, success false at t = 0 and during a 1 s hold.
- New family: add its entry to `families.json` and `instances/`, then run the generator and `cd tasks && harbor add --scan .`.

## Oracle and review (PROTOCOL §2.7)
- banana_in_bowl and rubiks_cube_left_of_bowl have a reference solution: `solution/oracle_<family>.py`, a human-written
  script on the privileged tooling plus the skills in `solution/ref_primitives.py` (never in the agent image); the
  standard oracle streams the privileged oracle's recorded joint targets through the client in one-second chunks and
  rides through a service crash (`spec.on_service_error`). The labels follow the recorded runs (static validation):
  - privileged `oracle = "full"`: the oracle scored 1 in recorded Harbor runs on a byte-identical grader, frozen instance
    and oracle code, and every tooling change since is off the oracle / replay path (eaf2aff0: other families' registry
    entries; b3c7ca89: additive 2.2 helpers, re-checked with the same final state sha through the same path; cde31660:
    the depth default, which run-oracle and replay pass explicitly); `oracle_evidence` cites the runs;
  - standard `oracle = "partial"`: oracle_replay scored 1 in 6/6 recorded runs on the pre-crash-recovery service with the
    same verdict formula, and has not been re-run on this version.
- `oracle = "none"` (51 families): RoboLab ships no expert or planner. Every such family has at least one model trial that
  the separate verifier scored 1 (run `codex-gpt6_luna-xhigh`), cited by trial id in `oracle_evidence` and in the README
  with its trial log on the results site and its replay video on Hugging Face (results are not kept in task directories,
  PROTOCOL D3; three standard positives of the withdrawn rcb-limited/2.0 batch are unpublished). These tasks have no
  `solution/` and go through human review per family in PR #3 (both modes, a positive, the `nop` result).
- bananas_in_bin_one_more and bananas_in_bin_three_total have the identical predicate (exactly 1 of `banana`,
  `banana_01`, `banana_03` in `grey_bin`, RoboLab's `choose`, K = 1); only their instructions differ.

## Success semantics (instantaneous)
RoboLab evaluates its `success` term after every control step and terminates the episode at the first step where it
holds (its termination freezes the env); the replay stops there and later rows are never executed. So a goal state that
holds at a single control step counts, in both modes. This is "success at any step" rather than "at the end of the
replay" (PROTOCOL §3): we keep RoboLab's own definition so the predicate is upstream's, unchanged. Most predicates require
the gripper to have released the object (`require_gripper_detached`), which rules out holding an object through the goal
region; the instructions state the rule in both modes.

## Image and host
- `images/robolab/` (Isaac Lab 2.3.2 / Isaac Sim 5.1 from the pinned `uv.lock`, RoboLab's Apache-2.0 asset library baked
  in), tagged `ghcr.io/mll-lab-nu/eai-robolab:<images/robolab/VERSION>` (0.1.1, the same build as
  the former `rcb-robolab:0.1.1`). It contains NVIDIA Isaac Sim, whose licence forbids redistribution: **BUILD_ONLY**.
  `images/robolab/BUILD_ONLY` has the licences, the build command
  (`docker build -f images/robolab/Dockerfile -t ghcr.io/mll-lab-nu/eai-robolab:$(cat images/robolab/VERSION) .`),
  the check of a build and how a CI machine builds it. A host that has the old tag only needs `docker tag`.
- Isaac needs an RTX-class GPU even headless (PhysX runs on the CPU). One Isaac simulator at a time per 32 GB of host RAM.
- Standard mode: the agent container and the verifier use the one digest-pinned client image of every standard task and
  its exact pip pins (`scripts/eai_standard/client.env`, `client-requirements.txt`, copied into `environment/`); only the
  `sim` sidecar uses eai-robolab.
- Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own `*_trusted` cache
  volumes, never the agent's; every cache volume is scoped to the trial's compose project (no fixed name).

## Time budget (D8)
5400 s for every task of both modes, longer than the default 3600 s: every Python process pays about 2 minutes of Isaac
launch and scene build, so an agent's iterations cost more than in the other simulators; with 3600 s most failures in
our first sweep were agents running out of time mid-attempt (raised 2026-09-26, uniform since).

## Grading and determinism
- PhysX on the CPU: on one host a fresh process reproduces the live run bit for bit, but a second replay inside one
  process drifts in the last bits, so the verifier replays in **two fresh processes** and compares them. Across hosts the
  final state can differ in the last bits (the banana_in_bowl oracle ends in one of two hashes on our hosts, both
  successes): a trial is graded on the host it ran on.
- Privileged: `tests/grade.py` replays `/app/output/trajectory.npz` twice; success = the predicate held in both, the final
  hashes agree, and the rebuilt frozen scene matches the recorded one.
- Standard: the service dumps the episode and exits on the collect hook's signal; the hook (`environment/sim/finalize.sh`)
  replays it in two fresh processes; success = live ∧ replay ∧ deterministic, `live_matches_replay` reported separately.
  The standard verifier only reads `final.json` and runs with `network_mode = "no-network"`.
- The privileged verifier keeps Harbor's default network (PROTOCOL §2.6 recommends no-network): it starts Isaac Sim, and
  an offline Kit start (extension registry, asset resolvers) has not been tested on our hosts. Grading downloads nothing:
  RoboLab's assets and every package are in the image.
- `scripts/robolab/regrade.sh <task> <trial> <out>` re-grades a finished trial with the current task version in two fresh
  processes (the review's determinism check), on the host the trial ran on.

## Crash recovery (standard mode, docs/STANDARD_MODE_2_2.md §13)
- Resume class `exact`: the resumed service is a fresh process, and replaying the journal is that process's first replay,
  so the state hash at the last checkpoint must match exactly (else the episode ends `resume_failed`, `infra_error`).
- The journal holds the float32 row handed to `Session.step` for every control step; a checkpoint (state hash = sha1 of
  the scene's full state, proprio row) follows every call. Reading the state never steps physics. A resume replays the
  episode so far at about 15-20 control steps/s, on the agent's wall clock.
- `RCB_STARTUP_TIMEOUT_S = 900`: the scene builds measured 99-217 s (the Session build in the service logs of 25 standard
  trials on the laptop and ws3); 900 s is more than four times the slowest, so a host twice as slow keeps a 2x margin.
- Validation in this PR is static (user decision, 2026-10-01). The crash recovery was exercised on the CPU with a test
  double of the tooling under `run.sh` and a restart loop (kills inside and between calls, an exact-hash mismatch, three
  crashes inside calls, the 400s), with the shared layer's own selftest; `scripts/robolab/kill_test.sh` is the acceptance
  test on a GPU host (Harbor oracle, the service killed mid-episode). Per-call state hashing only reads the scene
  (`InteractiveScene.get_state` reads PhysX views into Isaac Lab's timestamped buffers and writes nothing), so it cannot
  change a live run; live == replay with per-call hashing on Isaac is still to be confirmed by a run.

## Tooling (file names)
| main's convention | RoboLab |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_robolab.py` (`Session`: the frozen scene state, thin primitives, rendering, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_robolab.py` |
| standard sidecar | `environment/sim/server.py` (the 2.2 adapter), `finalize.sh`, `rcb_robolab.py`; `run.sh`, `rcb_limited.py`, `rcb1.py` from `scripts/eai_standard/` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records (T, 8) actions (7 joint targets + the binary gripper command) at 15 Hz. Every copy of the tooling and
of the standard sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`); the tooling's TASKS
registry lists all 88 frozen families, so adding a family later does not change existing tasks.

## Declarations
- **Tooling: thin wrappers only.** Differential-IK moves, joint moves, gripper, hold, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills (grasp, place, navigate) are never added to the agent's tooling;
  reference solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the robot's root frame (Franka base at the origin) is the world convention. Privileged tasks
  give the privileged state through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (8: 7 joints + binary gripper, switched at the row; rows `dt` apart, a multiple of 1/15 s, anything else
is a 400) and `ee_pose` (8, closed-loop differential IK, at most 0.25 m/s, fingertip-centre frame); cameras
`egocentric_mirrored_camera`, `over_shoulder_left_camera` (static) and `wrist_cam` (on the Robotiq base link); Isaac
`distance_to_image_plane` depth; `/kinematics` from a numpy model of the USD joints (7); 32 proprio columns.
STANDARD_MODE_2_2.md §16.

## Known issues
- The tooling stops a runaway trajectory at 100,000 control steps (`step_guard`); the live service runs 3-15 steps/s, so
  the 5400 s budget ends an episode long before (it is not in `/spec`).
- An `ee_pose` submit has no frame cap: a long one at a high `video_fps` keeps many frames in memory (the client's
  defaults, 5 fps and mp4, stay small).

## Licences
RoboLab: Apache-2.0 (code and assets); Isaac Lab: BSD-3-Clause on GitHub, its pip wheels and Isaac Sim 5.1 are NVIDIA
proprietary software (no redistribution), hence BUILD_ONLY.
