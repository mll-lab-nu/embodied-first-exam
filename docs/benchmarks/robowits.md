# RoboWits

[RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ 9cc30ae on Genesis 0.4.7: physical-reasoning puzzles for the
bimanual Marvin robot. `simulator = "robowits"`, `robot = "marvin-bimanual"`. Each family (one RoboWits seed task, one
success predicate) is a privileged task `robowits-<family>-i00-privileged` and its standard twin
`robowits-<family>-i00-standard`, on the same frozen evaluation scene (entry 0 of RoboWits' `eval_dataset_50/<NN>.json`).
Results are attributed by DIGEST (PROTOCOL H.8).

## Families
**In the repository: 15 families, 30 tasks.** The `oracle` level and its evidence are in each `task.toml`;
every task goes through the human review in PR #3.
- `oracle = "partial"`: dominos, stack_cubes. A written reference solution (`solution/`) scored 1 under `harbor -a oracle`
  in both modes, on earlier versions of these tasks with the same frozen instance and oracle code (`oracle_evidence` cites
  the runs). The grader, the tooling and (standard) the service have changed since and the oracle was not re-run on
  this version: `full` needs a run on byte-identical files.
- `oracle = "none"`, with a graded positive (the PR's review table cites each trial; the runs are on the results site):
  align_blocks, ball_into_bottle, ball_onto_tower, collect_screws, cover_with_lid, gap_retrieve, hold_cup, move_cube,
  raise_platform, retrieve_cube, stack_bowls, stand_bulb, stand_pages. The positives are from earlier versions too (same
  frozen instance and predicate).

**Not in the repository: 11 families** without a valid positive. A later PR can add one once it
has a positive; their frozen instances are in dev/qineng 9eb18edf.
- No graded positive: balance_board, ball_into_jar, differentiate_cubes, pinch_card, place_book, retrieve_roll,
  round_dough_sheet, seal_colander, water_into_mug. place_book can pass only with the thin book stood on its edge: the book
  (22 x 19 cm) is larger than the mat (12 x 20 cm), so a flat book has at most about 57 % of its footprint over the mat,
  and the predicate needs 95 %.
- stabilize_bottle: its only positive is nondeterministic (GPU backend, `deterministic = 0`), so it cannot meet the review's
  determinism item, and the predicate has no release check (in that positive the tube is still between the fingers).
- place_tall_box: its only positive exploits a missing height check (the box stands on the beam plank above the target,
  which footprint overlap alone accepts).

**Dropped: 4 families**.
- roll_up_ball: unsolvable in the frozen scene. The 10 cm box must fit inside the high basket's bounding box shrunk by 1 cm,
  but the basket is 9.2 cm tall, so the height test can never pass.
- cylinder_through_hole: unsolvable in the frozen scene. Half of the 9.1 cm peg must reach below the fixed hole plate's
  bounding box, whose bottom is already under the table top: the peg would end about 5 cm inside the table.
- separate_marbles_and_sand: broken frozen instance. The five marbles lie on the table under the fixed jar, below its
  bounding box, while the sand is still in the jar, so "keep the marbles in the jar" means putting all five back in.
- align_chopsticks: its frozen scene hits NaN constraint forces in Genesis within a few steps.

## Tasks
- The task directories are the deliverable; the tooling that built them is kept outside this repository. Every task
  carries the shared sources unchanged: the tooling `rcb_robowits.py`, the standard sim adapter `server.py`, the mode's
  grader (`tests/grade.py`), the standard oracle player `solution/oracle_replay.py`; the eai-standard/2.2 layer
  (`rcb_limited.py`, `rcb_client.py`, `rcb1.py`, `run.sh`) comes from `embodied_first_exam/standard/`. The privileged
  instruction quotes RoboWits' `_check_success` verbatim (MIT, RoboWits @ 9cc30ae).
  The frozen instance is `tasks/robowits/robowits-<family>-i00-privileged/environment/instance.json` (copied to `tests/` and to
  the standard twin's `environment/sim/`). `python3 scripts/task_conventions.py --check tasks/robowits/robowits-*` passes.
- One frozen input is over 2 MB: ball_into_bottle's `instance.json`, 2,047,384 bytes (2.05 MB; 1.95 MiB), in its three
  copies. It is the frozen scene: almost all of it is the frozen Genesis convex decomposition of its meshes
  (`genesis_cvx`, 2.04 MB), a task input and not a result; shrinking it would change the instance.
- Every instruction carries a section "Success criterion (as graded)", written from the family's predicate: what is checked,
  with every threshold, what is not checked, and where the task text differs from the code (the code wins, and the section
  says so). The privileged instruction also quotes the predicate's source.
- RoboWits ships no expert: reference solutions exist where we wrote one (`solution/`, with the skills they were written
  with in `solution/ref_primitives.py`; `oracle = "partial"` until re-run on this version); the other families declare
  `oracle = "none"` and no `solution/`.

## Image
- `images/robowits/`: RoboWits @ 9cc30ae, Genesis 0.4.7 and RoboWits' locked stack, RoboWits' Apache-2.0 asset bundle.
  `ghcr.io/mll-lab-nu/efe:robowits-<images/robowits/VERSION>`, public; the Dockerfile pins the uv, huggingface_hub,
  imageio and asset-bundle versions. The GPU renders the three cameras; physics runs
  on the CPU.
- `scripts/build_images.sh` builds it as `eai-robowits` (docs/protocol/running.md, "Base images").
- Standard agent containers and verifiers use the shared client base, pinned by digest, and the shared pip pins
  (`embodied_first_exam/standard/client.env`, `client-requirements.txt`, copied into `environment/`; `check-standard-client.sh`).
- 12 of the 15 families load BlenderKit models, which may not be redistributed (`images/robowits/NOTICE`). Each user
  fetches them with their own key (`images/robowits/fetch_blenderkit.sh`) or uses the encrypted research bundle
  (`images/robowits/fetch_blenderkit_encrypted.sh`); the tasks mount the folder read-only from `$RCB_ROBOWITS_BLENDERKIT`
  into the verifier and the standard `sim` sidecar. The privileged agent's container never sees that folder or the
  bundle's key: the task's `blenderkit` service runs `rcb_robowits.py blenderkit-serve`, which decrypts the
  models of this family alone and serves them on localhost:8765; the tooling in `main` fetches them for each scene build
  (`RCB_BLENDERKIT_URL`) into a private tmpfs dir and deletes them after it.
  dominos, stand_pages and stack_cubes need only the image.

## Hosts: one CPU vendor
Genesis' CPU backend is bit-exact only within one CPU vendor. The instances were frozen on Intel (the laptop). On AMD
hosts (ws, ws3, lab) the rebuilt instance's state hash differs; the grader's tolerance check (every object and joint
pose within tolerance) still accepts it, except for differentiate_cubes and ball_into_jar (not in the repository), which
run on Intel hosts only. stand_bulb's instance is its dataset scene simulated on until both objects are at rest (the dataset
entry overlaps the ring and the tall object, which were still moving after RoboWits' 10 settle steps and drifted by up to
12 mm between hosts), so it rebuilds within tolerance on either vendor. A trajectory recorded on one vendor can fail on the other, so a positive is
re-graded on the vendor it was graded on: the Intel laptop for every positive in the review table except stack_bowls,
which was graded on ws (AMD, with `instance_exact = 1`).
- **Machine-readable:** a task bound to one vendor carries `host_cpu_vendor = "GenuineIntel"` in `[metadata]` of `task.toml`
  (a RoboWits field, docs/TAXONOMY.md; no task in the repository needs it now), and
  its README a `Host CPU` row. A scheduler runs such a task only on a host whose `/proc/cpuinfo` `vendor_id` equals
  the value; a task without the key runs on either vendor. The key is not in `[metadata.resources]`, whose fields are
  fixed by PROTOCOL §6.
- **A host that cannot rebuild the instance is an infrastructure error, never a result.** Privileged: the
  verifier writes `success = 0`, `instance_ok = 0`, `infra_error = 1` (and `instance_build_failed = 1` with
  `grader_error = 1` when the scene does not build at all). Standard: the service checks the rebuilt instance once, at
  its first start, and gives up at once with a record (`final.json`: `finalized`, `gave_up`, `reason =
  "instance_mismatch: ..."`, `infra_error = 1`) instead of raising into six restarts; the agent's client then never
  gets a service, and `reward.json` has `infra_error = 1`, `instance_mismatch = 1`.

## Time budget
3600 s for every task of both modes: each task's own `[agent] timeout_sec` (PROTOCOL §2,
docs/protocol/running.md "The agent's time"); every instruction states it in its closing `## Time limit` section. The families are
bimanual physical puzzles that take several attempts, every Python process pays about a minute of scene build before
its first step, and a standard-mode crash resume replays the episode on the agent's clock.

## Grading and determinism
- **The verdict.** RoboWits' predicates are instantaneous and most have no release or speed term, so a success could
  fire with an object held in the goal region, a trajectory cut while things still moved, a gripper propping the pages
  from just outside the 3 cm "held" zone, or a cube knocked off the table. Both modes take the verdict after a settle window
  (`rcb_robowits.Session.settle_check`): the last command is held for 1 s (`SETTLE_STEPS` 30, nothing checked), then for
  2 s (`CHECK_STEPS` 60) the goal must hold at every 6th control step and at the last one, and every graded object must
  stay within 2 mm (`REST_M`) of where it was when those 2 s began. The goal (`Session.goal`) is RoboWits' predicate,
  unchanged, AND no robot contact with the family's graded objects (`GRADED`: Genesis' contact list; stand_pages also the
  bar) AND, for move_cube, the cube past the line still on the table (its bounding box's bottom no more than 2 cm below
  the table top). Privileged: the verifier runs the window after the trajectory's last row (`replay`); its state hash is
  taken after the window. Standard: after a call that leaves the goal holding, the service runs the window inside that
  call (its steps are part of the episode, journaled and recorded) and ends the episode only if it passes
  (`meta["settle"]` says why not); when the agent's phase ends the window decides once more, after the agent's last
  command (journaled and recorded too; the collect hook stops the agent's container with `kill -9 -1` first).
  **Standard: graded by the live episode** (PROTOCOL H.4; no grading replay; video by one render pass after the
  verdict). `success` is that live window's result,
  written to `final.json` at once (`graded_by = "live"`, `replays = 0`, `live_success`, `live_sha`, `settle`,
  `final_window`); an episode that ends without a passed window (a simulator error, the step cap, a failed window at
  the end of the agent's phase) is a failure. The window after the agent's last command runs as the end of its last call
  (`call_begin("/settle")`): a simulator crash inside it counts as a crash inside the agent's calls on the resume
  (`sim_crashed_on_call` when it repeats), never as a free infrastructure retry. A service that cannot export the rows or
  hash the end state afterwards keeps the verdict (`finalize_error`; `journal.f64` holds the rows).
- Physics on Genesis' CPU backend (single-threaded): bit-exact, in-process repeats included. The privileged verifier
  replays the trajectory twice in a fresh process and compares the final-state hashes and the rebuilt frozen scene; it
  writes the verdict before it renders the video. The standard service grades the live episode; the separate verifier
  reads `final.json`. After the verdict the service renders the recorded rows once into `replay.mp4` (EGL, ~N/60 s for
  N control steps; `video_pending` while it runs, `video_done` after; the collect hook waits for it); a failed render
  loses only the video (`video_error`). Rendering during the episode was not chosen: every frame would cost the agent's
  calls an EGL render of three cameras.
- Whose failure (`reward.json` always has `infra_error` and `grader_error`). The agent's: no trajectory
  (`missing_trajectory`), a file that is not the tooling's `.npz` or has no finite (T, 16) `actions` of at most
  200000 rows (`bad_trajectory`), another family's file (`wrong_family`), a trajectory that does not complete the
  task; in standard mode also an episode that ended with a simulator error (`sim_error = 1`). The infrastructure's
  (`infra_error = 1`, not a result): an instance the host cannot rebuild (Hosts, above), a service that gave up after
  crashes it caused or never wrote the live verdict, and a service that could not record the end of an episode that
  ended normally (`final.json` `grade_error`, `grader_error = 1`: the record is still a complete verdict, so the
  collect hook does not wait its timeout for one); crashes inside the agent's own calls (`sim_crashed_on_call`) are the
  agent's 0. A video that fails, or a service that dies while it renders
  the video, never changes a written verdict: the restarted service sets `video_done` and idles.
- Both verifiers run without network (`network_mode = "no-network"`): every asset is in the image or the mounted
  BlenderKit folder, RoboWits resolves assets from local paths only, and Genesis' convex-decomposition and particle
  caches are seeded from `instance.json`.
- The technical cap: 200000 control steps per episode or trajectory (`rcb_robowits.MAX_STEPS`, about 1.85 h of
  simulated time at 30 Hz), stated in both instructions and, in standard mode, in `/spec` as `max_control_steps`
  (`budget.steps` stays null: the wall clock is the budget). A standard episode ends there (reason `step_guard`)
  without a settle window (none fits under the cap), so it is graded a failure; the privileged grader scores
  a longer trajectory 0 (`bad_trajectory`).
- The GPU backend (`RCB_ROBOWITS_BACKEND=gpu`, the particle families stabilize_bottle and the dropped
  separate_marbles_and_sand: their CPU-backend builds take 39-86 min) is not bit-exact: their graders report determinism
  without requiring it. None of them is in the repository.

## Network policy
The agent's egress is the model APIs and the package registries, in both modes (`[agent] network_mode = "allowlist"`,
the hosts of `scripts/set_agent_egress.py`); nothing in a trial needs the network. RoboWits publishes human
demonstrations of its seed tasks (the LeRobot dataset its README names; the image's `/opt/robowits/README.md` and
`.git/config` carry the addresses, which the allowlist makes unreachable).
- Privileged `main` (the simulator image): RoboWits resolves assets from local paths only (the image's asset bundle and
  the BlenderKit models served by the task's `blenderkit` service; `images/robowits/fetch_blenderkit*.sh` run on the
  host, never in a container), Genesis' convex-decomposition and particle caches are seeded from `instance.json`, and
  `QD_OFFLINE_CACHE=0` only turns off Quadrants' on-disk kernel cache. The image's Python has no `pip`; `uv pip install`
  from PyPI works, `git` and `curl` fail for any host outside the allowlist.
- Standard `main` (the pinned client image): Python, the client and its pins; nothing to download.
- Standard `sim`: Harbor's egress control puts it in the same network namespace as `main` (that is how the client reaches
  `localhost:8000`), so it is public while the environment starts and on the allowlist during the agent phase, a restart
  after a crash included. It needs neither: the same image and assets as the privileged simulator.
- Both verifiers: `no-network` (Grading and determinism).

## Standard mode (eai-standard/2.2)
`joint_position` (16) and `ee_pose` (16, right arm first, IK per row on RoboWits' pink/pinocchio IK, gripper-tip frame);
cameras `ego` (static) and `wrist_right` / `wrist_left` (link-mounted); Genesis rasterizer depth; `/kinematics` on
pinocchio (14 arm joints); 80 proprio columns; the end condition in `/spec` (`episode`). docs/protocol/standard_mode.md §16.
- Requests: the adapter checks the type and range of every field of a `/submit` header
  and an `/observe` body before it executes or counts anything, and answers 400: `type`, `dt` (a finite number in
  [1/30, 0.5] s and, for `joint_position`, a whole number of 1/30 s periods within 1e-6 of a period: never rounded),
  `interpolate`, `video`, `video_fps` (a whole number in 1..30), `seconds` (a finite number in [0, 30]), `cameras`
  (null or a list of names; names that are not cameras are ignored), `note` (null or a string), `depth`, the actions
  (finite, (T, 16), at most 10 s or 50 `ee_pose` rows). `ee_pose` gripper widths outside 0 .. 0.1 are clipped and
  listed in `meta.clipped`, like out-of-limit joint targets; an IK result that is not finite counts as an IK failure
  (the arm holds).
- Crash recovery (docs/protocol/standard_mode.md §13): `restart: on-failure:6`, `command: sh /srv/run.sh`; the adapter declares the
  resume class `exact` on the CPU backend and `approx` on the GPU backend. A smoke test outside Harbor (the service
  killed between calls) resumes with the state hash matching; the Harbor acceptance test (kill the sidecar of a running
  trial) has not been run.
- `RCB_STARTUP_TIMEOUT_S` = max(900, 2 x the slowest measured scene build), per family: 900 s
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
| `rcb_client.py`, `rcb1.py` | the same names (`embodied_first_exam/standard/`) |

The tooling records (T, 16) JOINT_ABS rows (per arm 7 joints + gripper width) at the 30 Hz control rate. Every copy of
`rcb_robowits.py`, of the standard sidecar files and of each mode's grader is byte-identical across the benchmark
(`check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** The agent's tooling gives the frozen instance, the privileged state, recording and
  replay, rendering (`render_frame` / `render_grid` / `render_video`) and thin wrappers of the low-level action (joint
  moves, IK moves without collision checking, gripper, hold). Task-level skills (grasp, place, navigate) are never added
  to it; reference solutions keep theirs under `solution/`.
- **World-frame information.** Standard tasks never say where things are in the world (docs/protocol/standard_mode.md §10,
  `ci_checks/benchmarks/robowits/advisory-world-frame.sh`): no object poses or positions, no world coordinates of workspace items. Their success
  criterion is stated in words and distances relative to the objects and the table top; the corners of the predicate's
  table-bounds rectangle and the goal line's coordinate are withheld. Given: object names, sizes and colours, the robot
  (its base pose included), the cameras' calibration, the world frame's convention. Privileged tasks give the privileged
  state through the tooling, and their criterion gives world coordinates.

## Licences
RoboWits: MIT (declared in its pyproject.toml); Genesis: Apache-2.0; RoboWits' asset bundle: Apache-2.0; BlenderKit models:
licensed to whoever downloads them, never in the image or the repository (`images/robowits/NOTICE`).

## Known issues
- A JSON `/submit` body (not RCB1) whose `actions` is an object, or an RCB1 header whose `meta` is not an object with
  no `actions` part, fails in the shared layer before the adapter sees it (`rcb_limited.py`: 500, the episode ends).
  The official client always sends an RCB1 `actions` array, so only a hand-written request can do this.
- The response of one call is built in memory, so one call returns at most 1500 images (`/spec` `max_frames_per_call`,
  `environment/sim/server.py` `MAX_FRAMES`: cameras x frames, a frame with per-frame depth counts 4): over it a 400 before anything
  runs, and `ee_pose` rows that take longer than counted (up to 400 control steps each) stop adding frames there
  (`meta["frames_skipped"]`).
- `ball_into_bottle`: the red bottle's base collides as a thin shell (about 3.5 mm), so a ball that falls fast down the
  bottle can pass through it onto the table (9 of 16 slightly perturbed replays of one pour). The instruction says so;
  a thicker collision base would change the frozen scene and has not been made.
- During the standard service's video pass (after the verdict), a late `/status` reports the pass's counter.
- The predicates are RoboWits' own and some are looser than their task text (the criterion sections say where); the
  review checks each family's predicate. The verdict adds the release and rest window to every family (Grading and determinism); what it still does not check (stack_bowls' nesting order, the stand_pages
  hinge, the hold_cup coaster) is in each criterion's "Not checked".
- Standard `final.json` `reason`: "agent_exit" when the collect hook ended the episode while the service's
  clock of the agent (`meta["time_left_s"]`) still had more than 60 s, "timeout" otherwise; `agent_time_s` is that clock.
  docs/protocol/standard_mode.md still names the end of the agent's phase `timeout` for every service.

## Standard-mode service details

Resume class `exact` on Genesis' CPU backend; `approx` on the GPU backend (the particle families separate_marbles_and_sand and stabilize_bottle, `RCB_ROBOWITS_BACKEND=gpu`).

`max_frames_per_call` = 1500, per-frame depth counted as four images; where a call's length is known only while it runs (`ee_pose` rows) the call stops taking frames at the bound and `meta.frames_skipped` counts them. The service refuses the episode at its start when the frozen instance does not rebuild; its collect hook waits with `--wait-key video_done`.

A resume replays the episode so far without rendering at ~700 steps/s (CPU). Grading: the live episode.

Known issue: during the video pass after the verdict, `/status` and a late `/observe` report the pass's counter and scene; the episode is over by then and the grade is unaffected.

Per-simulator notes:

| | |
|---|---|
| simulator | Genesis 0.4.7 |
| rows streamed at | 30 Hz control (4 substeps) |
| `joint_position` | 16: per arm 7 joints + gripper width (m) |
| `ee_pose` | 16 (right first), IK per row, gripper-tip frame |
| cameras | `ego` (static), `wrist_right`, `wrist_left` |
| depth | Genesis rasterizer |
| `/kinematics` | pinocchio on the URDF (14 arm joints) |
| proprio columns | 80 |
| grading replays | none (live verdict); one render pass for the video |
| resume class (docs/protocol/standard_mode.md §13.1) | `exact` (CPU backend), `approx` (GPU backend) |

Measured scene builds (episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| RoboWits, CPU backend | 29 families (94 trials) | 47–234 s (median ~60 s) | default 900 s is enough |
| RoboWits, particle families | separate_marbles_and_sand, stabilize_bottle | 39–56 min on the CPU backend; ~140 s on the GPU backend | they run on the GPU backend; a CPU-backend build needs `RCB_STARTUP_TIMEOUT_S` ≥ 7200 |
