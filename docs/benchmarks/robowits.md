# RoboWits

[RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ 9cc30ae on Genesis 0.4.7: physical-reasoning puzzles for the
bimanual Marvin robot. `simulator = "robowits"`, `robot = "marvin-bimanual"`. Each family (one RoboWits seed task, one
success predicate) is a privileged task `robowits-<family>-i00-privileged` and its standard twin
`robowits-<family>-i00-standard`, on the same frozen evaluation scene (entry 0 of RoboWits' `eval_dataset_50/<NN>.json`).

## Families
**In the repository: 15 families, 30 tasks.** The `oracle` level and its evidence are in each `task.toml` (PROTOCOL §2.7);
every task goes through the human review in PR #3.
- `oracle = "partial"`: dominos, stack_cubes. A written reference solution (`solution/`) scored 1 under `harbor -a oracle`
  in both modes, on earlier versions of these tasks with the same frozen instance and oracle code (`oracle_evidence` cites
  the runs). The grader, the tooling and (standard) the service have changed since, and this version was validated
  statically only (2026-10-01), so the oracle was not re-run on it: `full` needs a run on byte-identical files.
- `oracle = "none"`, with a graded positive (the PR's review table cites each trial; the runs are on the results site):
  align_blocks, ball_into_bottle, ball_onto_tower, collect_screws, cover_with_lid, gap_retrieve, hold_cup, move_cube,
  raise_platform, retrieve_cube, stack_bowls, stand_bulb, stand_pages. The positives are from earlier versions too (same
  frozen instance and predicate).

**Pending: 11 families**, kept in the generator's table (`scripts/robowits/families.py`, status `pending`) so that a later PR
can render them once each has a valid positive and a written success criterion. Their frozen instances are in dev/qineng
9eb18edf (`mk_tasks.py --instance`).
- No graded positive: balance_board, ball_into_jar, differentiate_cubes, pinch_card, place_book, retrieve_roll,
  round_dough_sheet, seal_colander, water_into_mug. place_book can pass only with the thin book stood on its edge: the book
  (22 x 19 cm) is larger than the mat (12 x 20 cm), so a flat book has at most about 57 % of its footprint over the mat,
  and the predicate needs 95 %.
- stabilize_bottle: its only positive is nondeterministic (GPU backend, `deterministic = 0`), so it cannot meet the review's
  determinism item, and the predicate has no release check (in that positive the tube is still between the fingers).
- place_tall_box: its only positive exploits a missing height check (the box stands on the beam plank above the target,
  which footprint overlap alone accepts).

**Dropped: 4 families** (`families.py` DROPPED; user decision 2026-10-01).
- roll_up_ball: unsolvable in the frozen scene. The 10 cm box must fit inside the high basket's bounding box shrunk by 1 cm,
  but the basket is 9.2 cm tall, so the height test can never pass.
- cylinder_through_hole: unsolvable in the frozen scene. Half of the 9.1 cm peg must reach below the fixed hole plate's
  bounding box, whose bottom is already under the table top: the peg would end about 5 cm inside the table.
- separate_marbles_and_sand: broken frozen instance. The five marbles lie on the table under the fixed jar, below its
  bounding box, while the sand is still in the jar, so "keep the marbles in the jar" means putting all five back in.
- align_chopsticks: its frozen scene hits NaN constraint forces in Genesis within a few steps (excluded before v1.0).

## Tasks and generator
- `scripts/robowits/mk_tasks.py` renders both tasks of every family whose status is `pr`; `--check` writes nothing and
  fails if a task would change (re-running it gives no diff); `--list` prints the table. Inputs, all in the repository:
  - `scripts/robowits/shared/`: the D9 shared sources, copied unchanged into every task: the tooling `rcb_robowits.py`, the
    standard sim adapter `server.py`, the graders `grade_privileged.py` / `grade_standard.py` (as `tests/grade.py`), the
    standard oracle player `oracle_replay.py`;
  - `scripts/eai_standard/`: the eai-standard/2.2 layer (`rcb_limited.py`, `rcb_client.py`, `rcb1.py`, `run.sh`);
  - `scripts/robowits/families.py`: per family the texts (task text, objects, difficulty), flags (BlenderKit, physics
    backend, oracle and its evidence), measured scene builds and the success criterion;
  - `scripts/robowits/predicates/<NN>_<family>.py`: RoboWits' `_check_success`, verbatim (MIT, RoboWits @ 9cc30ae), which the
    privileged instruction quotes; `predicate_sha` in `families.py` pins the criterion text to it;
  - `scripts/robowits/oracles/<family>/`: the reference solutions (the privileged oracle script; the standard oracle's
    joint rows, recorded from it).
  The frozen instance is the one input kept in the task: `tasks/robowits-<family>-i00-privileged/environment/instance.json`
  (copied to `tests/` and to the standard twin's `environment/sim/`). Both twins are rendered side by side into a scratch
  directory and passed through `scripts/task_conventions.normalize()` (the protocol's conventions: names, `mode`, the
  README layout, no `results/`) before they are written, so `--check` compares against the normalized tasks and
  `python3 scripts/task_conventions.py --check tasks/robowits-*` passes. After rendering: `cd tasks && harbor add --scan .`.
- One frozen input is over 2 MB: ball_into_bottle's `instance.json`, 2,047,384 bytes (2.05 MB; 1.95 MiB), in its three
  copies. It is the frozen scene: almost all of it is the frozen Genesis convex decomposition of its meshes
  (`genesis_cvx`, 2.04 MB), a task input and not a result, so D3's 2 MB limit for
  results does not apply; shrinking it would change the instance.
- A new family: register it in `shared/rcb_robowits.py` (TASKS), freeze its instance with `rcb_robowits.py make-instance` in
  the image (`mk_tasks.py --help`), add its `families.py` entry, vendor its predicate (`--extract-predicate`), write its
  criterion, render, run the oracle (if any) and `nop`, register it.
- Every instruction carries a section "Success criterion (as graded)", written from the family's predicate: what is checked,
  with every threshold, what is not checked, and where the task text differs from the code (the code wins, and the section
  says so). The privileged instruction also quotes the predicate's source.
- RoboWits ships no expert: reference solutions exist where we wrote one (`solution/`, with the skills they were written
  with in `solution/ref_primitives.py`; `oracle = "partial"` until re-run on this version); the other families declare
  `oracle = "none"` and no `solution/`.

## Image
- `images/robowits/`: RoboWits @ 9cc30ae, Genesis 0.4.7 and RoboWits' locked stack, RoboWits' Apache-2.0 asset bundle.
  `ghcr.io/mll-lab-nu/eai-robowits:<images/robowits/VERSION>`, public; a copy of the image
  published on 2026-09-20 as `rcb-robowits:0.1.1`, unchanged (digest sha256:62688073fee9...); the Dockerfile pins the uv,
  huggingface_hub, imageio and asset-bundle versions that image contains. The GPU renders the three cameras; physics runs
  on the CPU.
- `scripts/build_images.sh` builds it as `eai-robowits` (docs/RUNNING.md, "Base images").
- Standard agent containers and verifiers use the shared client base, pinned by digest, and the shared pip pins
  (`scripts/eai_standard/client.env`, `client-requirements.txt`, copied into `environment/`; `check-standard-client.sh`).
- 12 of the 15 families load BlenderKit models, which may not be redistributed (`images/robowits/NOTICE`). Each user
  fetches them with their own key (`scripts/robowits/fetch_blenderkit.sh`) or uses the encrypted research bundle
  (`scripts/robowits/fetch_blenderkit_encrypted.sh`); the tasks mount the folder read-only from `$RCB_ROBOWITS_BLENDERKIT`.
  dominos, stand_pages and stack_cubes need only the image.

## Hosts: one CPU vendor
Genesis' CPU backend is bit-exact only within one CPU vendor. The instances were frozen on Intel (the laptop). On AMD
hosts (ws, ws3, lab) the rebuilt instance's state hash differs; the grader's tolerance check (every object and joint
pose within tolerance) still accepts it, except for stand_bulb (and the pending differentiate_cubes and ball_into_jar),
which therefore run on Intel hosts only. A trajectory recorded on one vendor can fail on the other, so a positive is
re-graded on the vendor it was graded on: the Intel laptop for every positive in the review table except stack_bowls,
which was graded on ws (AMD, with `instance_exact = 1`).

## Time budget (D8)
5400 s for every task of both modes, longer than the 3600 s default: the families are bimanual physical puzzles that
take several attempts (a failed push or a dropped object is reset in privileged mode and must be recovered in standard
mode), every Python process pays about a minute of scene build before its first step, and a standard-mode crash resume
replays the episode on the agent's clock. Results are reported with this budget.

## Grading and determinism
- Physics on Genesis' CPU backend (single-threaded): bit-exact, in-process repeats included. The privileged verifier
  replays the trajectory twice in a fresh process and compares the final-state hashes and the rebuilt frozen scene; it
  writes the verdict before it renders the video. The standard service grades in-process (its replay of the recorded
  episode must end in the live final state); the separate verifier reads `final.json`.
- The GPU backend (`RCB_ROBOWITS_BACKEND=gpu`, the particle families stabilize_bottle and the dropped
  separate_marbles_and_sand: their CPU-backend builds take 39-86 min) is not bit-exact: their graders report determinism
  without requiring it. None of them is in the repository.

## Standard mode (eai-standard/2.2)
`joint_position` (16) and `ee_pose` (16, right arm first, IK per row on RoboWits' pink/pinocchio IK, gripper-tip frame);
cameras `ego` (static) and `wrist_right` / `wrist_left` (link-mounted); Genesis rasterizer depth; `/kinematics` on
pinocchio (14 arm joints); 80 proprio columns; the end condition in `/spec` (`episode`). STANDARD_MODE_2_2.md §16.
- Crash recovery (STANDARD_MODE_2_2.md §13): `restart: on-failure:6`, `command: sh /srv/run.sh`; the adapter declares the
  resume class `exact` on the CPU backend and `approx` on the GPU backend. A smoke test of the sidecar outside Harbor
  (laptop, 2026-10-01, stack_cubes): the service killed between calls came back in 28 s, replayed its 90-row journal with
  the state hash matching, continued the same episode and was graded in-process (`deterministic` 1, `resumes` 1,
  `infra_error` 0). The Harbor acceptance test (kill the sidecar of a running trial) is not run yet: this version was
  validated statically.
- `RCB_STARTUP_TIMEOUT_S` = max(900, 2 x the slowest measured scene build), per family in `families.py` (`build_s`): 900 s
  for all 15 families (builds of 48-71 s on the laptop; 47-234 s across 94 standard trials on every host). When the
  particle families come back: about 150 s on the GPU backend (900 s), 13-22 min for water_into_mug's SPH scene on the CPU
  (3600 s), and at least 7200 s for a particle scene built on the CPU backend.
- The standard grader copies the crash-recovery fields into `reward.json` (`sim_startups`, `resumes`,
  `resume_state_mismatch`, `resume_max_tcp_dev_m`, `resume_max_joint_dev`) with `infra_error` (a give-up the service
  caused, or a record that never finished grading).

## Tooling (file names)
| main's convention | RoboWits |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_robowits.py` (`Session`: the frozen instance in `instance.json`, thin primitives, rendering, recording, replay) |
| `tests/rcb_traj.py` (the verifier's copy) | `tests/rcb_robowits.py` |
| standard sidecar (`environment/sim/server.py`) | `environment/sim/server.py` (the 2.2 adapter) + `environment/sim/rcb_robowits.py` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records (T, 16) JOINT_ABS rows (per arm 7 joints + gripper width) at the 30 Hz control rate. Every copy of
`rcb_robowits.py`, of the standard sidecar files and of each mode's grader is byte-identical across the benchmark
(`check-tooling-identity.sh`; their source is `scripts/robowits/shared/`).

## Declarations
- **Tooling: thin wrappers only.** The agent's tooling gives the frozen instance, the privileged state, recording and
  replay, rendering (`render_frame` / `render_grid` / `render_video`) and thin wrappers of the low-level action (joint
  moves, IK moves without collision checking, gripper, hold). Task-level skills (grasp, place, navigate) are never added
  to it; reference solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`): no object poses or positions, no world coordinates of workspace items. Their success
  criterion is stated in words and distances relative to the objects and the table top; the corners of the predicate's
  table-bounds rectangle and the goal line's coordinate are withheld. Given: object names, sizes and colours, the robot
  (its base pose included), the cameras' calibration, the world frame's convention. Privileged tasks give the privileged
  state through the tooling, and their criterion gives world coordinates.

## Results
Not in the repository (D3): agent results are published on the results site and the Hugging Face dataset
`eai-v2-internal/agent-runs`, keyed by run id. The PR's review table cites, per family, the positive trials (batch, trial
id, host, version class) with their run-log and replay links. Every RoboWits result so far is from before protocol v1.0,
recorded through custom Harbor agent adapters (removed by D11):
- `codex-gpt6_luna-xhigh` (ChatGPT login) and `codex-gpt6_luna-high` (stand_pages): the positives of the review table;
- `codex-gpt6_luna-medium` (OpenRouter, provider route `openai/flex`, 2026-09-25): the earlier runs of six families.

## Licences
RoboWits: MIT (declared in its pyproject.toml); Genesis: Apache-2.0; RoboWits' asset bundle: Apache-2.0; BlenderKit models:
licensed to whoever downloads them, never in the image or the repository (`images/robowits/NOTICE`).

## Known issues
- During the standard service's in-process grading replay, a late `/status` reports the replay's counter.
- The predicates are RoboWits' own and some are looser than their task text (the criterion sections say where); the
  review checks each family's predicate (PROTOCOL §2.7).
