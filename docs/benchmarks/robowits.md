# RoboWits

[RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ 9cc30ae on Genesis 0.4.7: physical-reasoning puzzles for the
bimanual Marvin robot. `simulator = "robowits"`, `robot = "marvin-bimanual"`. Each family (one RoboWits seed task, one
success predicate) is a privileged task `robowits-<family>-i00-privileged` and its standard twin
`robowits-<family>-i00-standard`, on the same frozen evaluation scene (entry 0 of RoboWits' `eval_dataset_50/<NN>.json`).
On 2026-10-14 the verifier changed in place (Grading and determinism, The verdict; PROTOCOL v2.0 §1, H.8: a new DIGEST,
results are attributed by digest): results recorded under the earlier DIGESTs are not comparable with the current ones.

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

**Not in the repository: 11 families** without a valid positive. A later PR can add one (an entry in
`scripts/robowits/families.py`, its predicate with `mk_tasks.py --extract-predicate`, a written success criterion) once it
has a positive; their frozen instances are in dev/qineng 9eb18edf (`mk_tasks.py --instance`).
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
  (`scripts/robowits/fetch_blenderkit_encrypted.sh`); the tasks mount the folder read-only from `$RCB_ROBOWITS_BLENDERKIT`
  into the verifier and the standard `sim` sidecar. The privileged agent's container never sees that folder or the
  bundle's key (since 2026-10-14): the task's `blenderkit` service runs `rcb_robowits.py blenderkit-serve`, which decrypts the
  models of this family alone and serves them on localhost:8765; the tooling in `main` fetches them for each scene build
  (`RCB_BLENDERKIT_URL`) into a private tmpfs dir and deletes them after it. Before, `main` mounted the whole folder,
  the key included, and two agents decrypted models with it.
  dominos, stand_pages and stack_cubes need only the image.

## Hosts: one CPU vendor
Genesis' CPU backend is bit-exact only within one CPU vendor. The instances were frozen on Intel (the laptop). On AMD
hosts (ws, ws3, lab) the rebuilt instance's state hash differs; the grader's tolerance check (every object and joint
pose within tolerance) still accepts it, except for stand_bulb (and differentiate_cubes and ball_into_jar, which are not in the repository),
which therefore run on Intel hosts only. A trajectory recorded on one vendor can fail on the other, so a positive is
re-graded on the vendor it was graded on: the Intel laptop for every positive in the review table except stack_bowls,
which was graded on ws (AMD, with `instance_exact = 1`).
- **Machine-readable:** both stand_bulb tasks carry `host_cpu_vendor = "GenuineIntel"` in `[metadata]` of `task.toml`
  (a RoboWits field, docs/TAXONOMY.md; `families.py` `host_cpu_vendor`), and
  their READMEs a `Host CPU` row. A scheduler runs such a task only on a host whose `/proc/cpuinfo` `vendor_id` equals
  the value; a task without the key runs on either vendor. The key is not in `[metadata.resources]`, whose fields are
  fixed by PROTOCOL §2.9.
- **A host that cannot rebuild the instance is an infrastructure error, never a result** (2026-10-10). Privileged: the
  verifier writes `success = 0`, `instance_ok = 0`, `infra_error = 1` (and `instance_build_failed = 1` with
  `grader_error = 1` when the scene does not build at all). Standard: the service checks the rebuilt instance once, at
  its first start, and gives up at once with a record (`final.json`: `finalized`, `gave_up`, `reason =
  "instance_mismatch: ..."`, `infra_error = 1`) instead of raising into six restarts; the agent's client then never
  gets a service, and `reward.json` has `infra_error = 1`, `instance_mismatch = 1`.

## Time budget (D8)
**Since 2026-10-12: 3600 s** for every task of both modes (owner: stricter cutoffs in 30-minute steps, one number for both modes; history in [`../CUTOFFS.md`](../CUTOFFS.md)). The text below describes the budget before that, 5400 s, and why it was chosen; results are grouped by budget.

5400 s for every task of both modes, longer than the 3600 s default: the families are bimanual physical puzzles that
take several attempts (a failed push or a dropped object is reset in privileged mode and must be recovered in standard
mode), every Python process pays about a minute of scene build before its first step, and a standard-mode crash resume
replays the episode on the agent's clock. Results are reported with this budget. The number lives in
each task's own `[agent] timeout_sec`, written by the generator (history in [`docs/CUTOFFS.md`](../CUTOFFS.md)), and every instruction states it in its closing `## Time limit` section (PROTOCOL §2.12).

## Grading and determinism
- **The verdict (since 2026-10-14).** RoboWits' predicates are instantaneous and most have no release or speed term; the
  failure analysis of the 10-14 results found 25 of 84 successes that did not do the task (an object held in the goal
  region at the end, a trajectory cut while things still moved, a gripper propping the pages from just outside the 3 cm
  "held" zone, a cube knocked off the table). Both modes now take the verdict after a settle window
  (`rcb_robowits.Session.settle_check`): the last command is held for 1 s (`SETTLE_STEPS` 30, nothing checked), then for
  2 s (`CHECK_STEPS` 60) the goal must hold at every 6th control step and at the last one, and every graded object must
  stay within 2 mm (`REST_M`) of where it was when those 2 s began. The goal (`Session.goal`) is RoboWits' predicate,
  unchanged, AND no robot contact with the family's graded objects (`GRADED`: Genesis' contact list; stand_pages also the
  bar) AND, for move_cube, the cube past the line still on the table (its bounding box's bottom no more than 2 cm below
  the table top). Privileged: the verifier runs the window after the trajectory's last row (`replay`); its state hash is
  taken after the window. Standard: after a call that leaves the goal holding, the service runs the window inside that
  call (its steps are part of the episode, journaled and recorded) and ends the episode only if it passes
  (`meta["settle"]` says why not); when the agent's phase ends the window decides once more, after the agent's last
  command (journaled and recorded too). The grading replay (`server.py` `grading_replay`, since 2026-10-17) must end
  the recorded rows in the live state (`state_sha_rows`) and checks ONE window: the one that ended the episode, over its
  recorded rows (the last `final_window` rows; `final.json` and the episode log's `end` event carry the length). Before
  2026-10-17 it replayed those rows and then ran a second window after them, which the instruction did not state
  (instruction audit M5: robowits-hold-cup-i00-standard, 10-15, passed live with 0.13 mm of motion and failed the
  replay's second window). An episode without a completed live window (a simulator error, a window that raised) gets
  the window after its last row; one that ended at the step cap gets none (below). Re-grades of the recorded positives:
  the pull requests that made these changes, and `scripts/robowits/regrade.py` re-grades recorded trials (Re-grading).
- Physics on Genesis' CPU backend (single-threaded): bit-exact, in-process repeats included. The privileged verifier
  replays the trajectory twice in a fresh process and compares the final-state hashes and the rebuilt frozen scene; it
  writes the verdict before it renders the video. The standard service grades in-process (its replay of the recorded
  episode must end in the live final state); the separate verifier reads `final.json`.
- Whose failure (2026-10-10; `reward.json` always has `infra_error` and `grader_error`). The agent's: no trajectory
  (`missing_trajectory`), a file that is not the tooling's `.npz` or has no finite (T, 16) `actions` of at most
  200000 rows (`bad_trajectory`), another family's file (`wrong_family`), a trajectory that does not complete the
  task; in standard mode also an episode that ended with a simulator error (`sim_error = 1`). The infrastructure's
  (`infra_error = 1`, not a result): an instance the host cannot rebuild (Hosts, above), a service that gave up after
  crashes it caused or never finished grading, and a grading replay that raised after an episode that ended normally
  (`final.json` `grade_error`, `grader_error = 1`: the record is still a complete verdict, `deterministic` false, so
  the collect hook does not wait its timeout for one). A video that fails, or a service that dies while it renders
  the video, never changes a written verdict: the restarted service sets `video_done` and idles.
- Both verifiers run without network (`network_mode = "no-network"`): every asset is in the image or the mounted
  BlenderKit folder, RoboWits resolves assets from local paths only, and Genesis' convex-decomposition and particle
  caches are seeded from `instance.json`.
- The technical cap: 200000 control steps per episode or trajectory (`rcb_robowits.MAX_STEPS`, about 1.85 h of
  simulated time at 30 Hz), stated in both instructions and, in standard mode, in `/spec` as `max_control_steps`
  (PROTOCOL §4.5; `budget.steps` stays null: the wall clock is the budget). A standard episode ends there (reason
  `step_guard`) without a settle window (none fits under the cap), so it is graded a failure (since 2026-10-17; before,
  the replay's window raised past the cap and the trial was recorded as a grading error); the privileged grader scores
  a longer trajectory 0 (`bad_trajectory`).
- The GPU backend (`RCB_ROBOWITS_BACKEND=gpu`, the particle families stabilize_bottle and the dropped
  separate_marbles_and_sand: their CPU-backend builds take 39-86 min) is not bit-exact: their graders report determinism
  without requiring it. None of them is in the repository.

## Network policy
The agent's egress is the model APIs and, since 2026-10-11, the package registries, in both modes (`[agent] network_mode = "allowlist"`, the hosts of
`scripts/set_agent_egress.py`; owner decision 2026-10-10, board 0072). The tasks used Harbor's default (public) until
then, because RoboWits ships no expert or planner; nothing in a trial needs the network. With open egress an agent could
fetch RoboWits' source and robot models from its own shell, and RoboWits does publish human demonstrations of its seed
tasks (the LeRobot dataset its README names; the image's `/opt/robowits/README.md` and `.git/config` carry the
addresses, which the allowlist makes unreachable).
- Privileged `main` (the simulator image): RoboWits resolves assets from local paths only (the image's asset bundle and
  the BlenderKit folder mounted read-only from the host; `scripts/robowits/fetch_blenderkit*.sh` run on the host, never
  in a container), Genesis' convex-decomposition and particle caches are seeded from `instance.json`, and
  `QD_OFFLINE_CACHE=0` only turns off Quadrants' on-disk kernel cache. The image's Python has no `pip`; `uv pip install`,
  `git` and `curl` fail for any host outside the allowlist (`uv pip install` from PyPI works).
- Standard `main` (the pinned client image): Python, the client and its pins; nothing to download.
- Standard `sim`: Harbor's egress control puts it in the same network namespace as `main` (that is how the client reaches
  `localhost:8000`), so it is public while the environment starts and on the allowlist during the agent phase, a restart
  after a crash included. It needs neither: the same image and assets as the privileged simulator.
- Both verifiers: `no-network` (Grading and determinism), unchanged.

Verified on a pool host (2026-10-11 UTC, dominos, both modes, Harbor's oracle agent): reward 1 and `deterministic` 1 as
before, the privileged oracle running the simulator inside the allowlisted agent container; from inside the agent's
container github.com, huggingface.co, blenderkit.com and (then: the list had no registries yet) pypi.org failed at the
TLS handshake while the model API hosts answered.

## Standard mode (eai-standard/2.2)
`joint_position` (16) and `ee_pose` (16, right arm first, IK per row on RoboWits' pink/pinocchio IK, gripper-tip frame);
cameras `ego` (static) and `wrist_right` / `wrist_left` (link-mounted); Genesis rasterizer depth; `/kinematics` on
pinocchio (14 arm joints); 80 proprio columns; the end condition in `/spec` (`episode`). STANDARD_MODE.md §16.
- Requests (PROTOCOL §4.6; 2026-10-10): the adapter checks the type and range of every field of a `/submit` header
  and an `/observe` body before it executes or counts anything, and answers 400: `type`, `dt` (a finite number in
  [1/30, 0.5] s and, for `joint_position`, a whole number of 1/30 s periods within 1e-6 of a period: never rounded),
  `interpolate`, `video`, `video_fps` (a whole number in 1..30), `seconds` (a finite number in [0, 30]), `cameras`
  (null or a list of names; names that are not cameras are ignored), `note` (null or a string), `depth`, the actions
  (finite, (T, 16), at most 10 s or 50 `ee_pose` rows). `ee_pose` gripper widths outside 0 .. 0.1 are clipped and
  listed in `meta.clipped`, like out-of-limit joint targets; an IK result that is not finite counts as an IK failure
  (the arm holds). Before this date a null or mistyped field, a huge `video_fps` or a non-string `note` ended the
  episode with a 500 (some after the chunk had run), and a `dt` between two periods was rounded.
- Crash recovery (STANDARD_MODE.md §13): `restart: on-failure:6`, `command: sh /srv/run.sh`; the adapter declares the
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
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE.md §10,
  `scripts/robowits/ci/advisory-world-frame.sh`): no object poses or positions, no world coordinates of workspace items. Their success
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


## Re-grading recorded trials (2026-10-14)
`scripts/robowits/regrade.py JOBS_DIR ... [--parallel N] [--out regrade.jsonl]` re-grades recorded trials under the
current verdict without re-running them. It finds every RoboWits trial in a Harbor jobs tree and reads two things from it:
the recorded trajectory (privileged: `artifacts/app/output/trajectory.npz`; standard: the sidecar's `trajectory.npz`, or
its `journal.f64`) and the recorded verdict. Per family it starts one container of the image with the current task's own
grader copies (`tests/`). It replays each trajectory twice from the frozen instance and reports three things: the old
verdict (RoboWits' predicate after the last row), the new verdict (the settle window, deterministic, instance ok) and the
window's reason. Standard trials are replayed as the service's grading replay does (`replay_standard`, since 2026-10-17):
the window that ended the episode over its recorded rows, its length and the episode's reason read from the trial's
episode log (`verifier/episode.jsonl`), else `artifacts/data/final.json`, else the trajectory's meta; with
`artifacts/data/final.json` it also reports `replay_matches_live`. The 12 BlenderKit families need `$RCB_ROBOWITS_BLENDERKIT`.
- **Same CPU vendor.** Genesis' CPU backend is bit-exact within one vendor only (Hosts). The tool prints the host's
  vendor and flags a trial `inconclusive` when its recorded success does not reproduce under the old rule here.
- **Standard trials.** A trial recorded with the live settle window (from 2026-10-14) is re-graded exactly: the same
  window over the same rows; the label is "re-graded under 2026-10-17 rules". An earlier trial had no live window (its
  episode ended at the first call after which the predicate held) and gets the window after its last row; that is
  conservative: under the current rule a failed window does not end the episode, and the agent could have gone on. Its
  label is "re-graded under 2026-10-17 rules (conservative)". The stand_pages and hold_cup texts also changed, and the
  recorded agents never read them.
- **Privileged trials are close to exact.** The deliverable is the trajectory; only the window after its last row is new.

## Licences
RoboWits: MIT (declared in its pyproject.toml); Genesis: Apache-2.0; RoboWits' asset bundle: Apache-2.0; BlenderKit models:
licensed to whoever downloads them, never in the image or the repository (`images/robowits/NOTICE`).

## Known issues
- A JSON `/submit` body (not RCB1) whose `actions` is an object, or an RCB1 header whose `meta` is not an object with
  no `actions` part, fails in the shared layer before the adapter sees it (`rcb_limited.py`: 500, the episode ends).
  The official client always sends an RCB1 `actions` array, so only a hand-written request can do this.
- The response of one call is built in memory, so one call returns at most 1500 images (`/spec` `max_frames_per_call`,
  `shared/server.py` `MAX_FRAMES`: cameras x frames, a frame with per-frame depth counts 4): over it a 400 before anything
  runs, and `ee_pose` rows that take longer than counted (up to 400 control steps each) stop adding frames there
  (`meta["frames_skipped"]`; `scripts/robowits/tests/test_server_frames.py`). Until 2026-10-10 there was no limit: a
  long chunk or watch with per-frame video or depth of three cameras could exhaust the sidecar's memory.
- `ball_into_bottle`: the red bottle's base collides as a thin shell (about 3.5 mm), so a ball that falls fast down the
  bottle can pass through it onto the table (board 0086: 9 of 16 slightly perturbed replays of one pour). The
  instruction says so since 2026-10-14; a thicker collision base would change the frozen scene and has not been made.
- During the standard service's in-process grading replay, a late `/status` reports the replay's counter.
- The predicates are RoboWits' own and some are looser than their task text (the criterion sections say where); the
  review checks each family's predicate (PROTOCOL §2.7). Since 2026-10-14 the verdict adds the release and rest window to
  every family (Grading and determinism); what it still does not check (stack_bowls' nesting order, the stand_pages
  hinge, the hold_cup coaster) is in each criterion's "Not checked".
- Standard `final.json` `reason` (since 2026-10-14): "agent_exit" when the collect hook ended the episode while the service's
  clock of the agent (`meta["time_left_s"]`) still had more than 60 s, "timeout" otherwise; `agent_time_s` is that clock.
  docs/STANDARD_MODE.md still names the end of the agent's phase `timeout` for every service.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Resume class `exact` on Genesis' CPU backend; `approx` on the GPU backend (the particle families separate_marbles_and_sand and stabilize_bottle, `RCB_ROBOWITS_BACKEND=gpu`).

`max_frames_per_call` = 1500, per-frame depth counted as four images; where a call's length is known only while it runs (`ee_pose` rows) the call stops taking frames at the bound and `meta.frames_skipped` counts them. The service refuses the episode at its start when the frozen instance does not rebuild; its collect hook waits with `--wait-key video_done`.

A resume replays the episode so far without rendering at ~700 steps/s (CPU). Grading: in-process (Genesis' CPU backend repeats exactly); the GPU-backend families report determinism, not require it.

Known issue: during the in-process grading replay, `/status` and a late `/observe` report the replay's counter and scene; the episode is over by then and the grade is unaffected.

Per-simulator notes (former STANDARD_MODE §16):

| | |
|---|---|
| simulator | Genesis 0.4.7 |
| rows streamed at | 30 Hz control (4 substeps) |
| `joint_position` | 16: per arm 7 joints + gripper width (m) |
| `ee_pose` | 16 (right first), IK per row, gripper-tip frame |
| cameras | `ego` (static), `wrist_right`, `wrist_left` |
| depth | Genesis rasterizer |
| `/kinematics` | pinocchio on the URDF (14 arm joints) |
| proprio columns (2.0 → 2.2) | 30 → 80 |
| grading replays | in-process (exact) |
| resume class (STANDARD_MODE §13.1) | `exact` (CPU backend), `approx` (GPU backend) |

Measured scene builds (former STANDARD_MODE §13.4; episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| RoboWits, CPU backend | 29 families (94 trials) | 47–234 s (median ~60 s) | default 900 s is enough |
| RoboWits, particle families | separate_marbles_and_sand, stabilize_bottle | 39–56 min on the CPU backend; ~140 s on the GPU backend | they run on the GPU backend; a CPU-backend build needs `RCB_STARTUP_TIMEOUT_S` ≥ 7200 |
