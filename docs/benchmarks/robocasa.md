# RoboCasa

[RoboCasa](https://github.com/robocasa/robocasa) v0.2 kitchen tasks with a mobile manipulator (Franka Panda on an
Omron mobile base), each on one frozen instance, in both modes: 58 tasks.

| | |
|---|---|
| upstream | robocasa/robocasa @ `756598a5be52e052339bb2d957426e39015c2afb` (MIT), robosuite 1.5.1, MuJoCo 3.2.6 |
| tasks | `tasks/robocasa-<task>-i00-privileged` and `tasks/robocasa-<task>-i00-standard`, 29 each |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda-omron"`, `family = "robocasa/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-robocasa:0.1.0` (`images/robocasa/`), CPU only, ~24 GB |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py`: the HumanoidBench tasks' code, the client with a docstring of its own that describes this service |
| generator | `scripts/robocasa/` (`import_references.sh` -> `frozen/`, `generate.py` -> `tasks/`) |

## Scope
All 29 of RoboCasa v0.2's 111 kitchen environments that have an official demonstration in the dataset registry
at the pinned commit (`robocasa/utils/dataset_registry.py`, `v0.1/...` human demonstrations) and whose
demonstration-based reference verifies: ArrangeVegetables, CloseDoubleDoor, CloseDrawer, CloseSingleDoor, CoffeePressButton, CoffeeServeMug, CoffeeSetupMug, MicrowaveThawing, OpenDoubleDoor, OpenDrawer, OpenSingleDoor, PnPCabToCounter, PnPCounterToCab, PnPCounterToMicrowave, PnPCounterToSink, PnPCounterToStove, PnPMicrowaveToCounter, PnPSinkToCounter, PnPStoveToCounter, PreSoakPan, PrepareCoffee, RestockPantry, TurnOffMicrowave, TurnOffSinkFaucet, TurnOffStove, TurnOnMicrowave, TurnOnSinkFaucet, TurnOnStove, TurnSinkSpout.

Not included (82):
- `NavigateKitchen`: navigation only, with a different (3-D base) action interface; no reference trajectory.
- 2 whose scene could not be frozen bit-exactly (reset not reproducible): CupcakeCleanup, PastryDisplay.
- 79 without an official demonstration at the pinned commit, hence without a reference: AfterwashSorting, ArrangeBreadBasket, ArrangeTea, AssembleCookingArray, BeverageOrganization, BeverageSorting, BowlAndCup, BreadAndCheese, BreadSelection, BreadSetupSlicing, CandleCleanup, CerealAndBowl, CheesyBread, CleanMicrowave, ClearClutter, ClearingCleaningReceptacles, ClearingTheCuttingBoard, ColorfulSalsa, CondimentCollection, CountertopCleanup, DateNight, DefrostByCategory, DessertAssembly, DessertUpgrade, DrainVeggies, DrawerUtensilSort, DrinkwareConsolidation, DryDishes, DryDrinkware, FillKettle, FoodCleanup, FryingPanAdjustment, HeatMug, HeatMultipleWater, KettleBoiling, MakeFruitBowl, MakeLoadedPotato, MealPrepStaging, MeatTransfer, MultistepSteaming, OrganizeBakingIngredients, OrganizeCleaningSupplies, OrganizeVegetables, PanTransfer, PantryMishap, PlaceFoodInBowls, PrepForSanitizing, PrepForTenderizing, PrepMarinatingMeat, PrepareSoupServing, PrepareToast, PrewashFoodAssembly, PushUtensilsToSink, QuickThaw, RestockBowls, SearingMeat, SeasoningSpiceSetup, ServeSteak, SetBowlsForSoup, SetupFrying, SetupJuicing, ShakerShuffle, SimmeringSauce, SizeSorting, SnackSorting, SortingCleanup, SpicyMarinade, StackBowlsInSink, SteamInMicrowave, SteamVegetables, StockingBreakfastFoods, SweetSavoryToastSetup, ThawInSink, VeggieBoil, VeggieDipPrep, WaffleReheat, WarmCroissant, WineServingPrep, YogurtDelightPrep.

## Task definition
- **Instance.** The initial state of the first official demonstration episode of the task (episode 0 of its
  `v0.1/...` dataset; the README of each task names it), frozen in `instance.npz` (~0.1–0.3 MB): the MuJoCo
  integration state, the model arrays the kitchen's reset rewrites, the env's Python task state (every JSON-encodable
  attribute of the env, its fixtures, robot, controllers and observables) and the NumPy / Python RNG states, with a
  SHA-256 checked on every load. Rebuilding is bit-exact (`reset_exact` in `frozen/report.json`). Copied into
  `environment/`, `tests/` and `environment/sim/`.
- **Actions.** The robot's native composite-controller command, one per control step (20 Hz), in both modes: 12
  channels, arm end-effector deltas (OSC, base frame), grip, base velocities, torso and the hybrid-mode switch
  (`casa_tool.action_spec`). This is the controller the demonstrations were recorded with. In standard mode the type is
  `ee_delta`; a `joint_position` type is not offered (PROTOCOL §4.4 SHOULD): the arm's demonstrations, and so the
  references, are OSC commands. Scales (robosuite 1.5.1 `default_pandaomron.json`, `omron_mobile_base.xml`): arm 1.0 =
  5 cm / 0.5 rad per step; base 1.0 = a target velocity of 1 m/s (`base_x`, `base_y`) or 1.5 rad/s (`base_yaw`),
  force-limited velocity servos; torso a delta joint-position command, 1.0 = height target 5 cm above the current
  height (lift range 0–0.34 m). Both instructions state them.
- **Success.** The environment's own `_check_success` on the state after the last action (PROTOCOL §3), and not
  already at the start. The check runs twice after every control step and once at reset, in the agent's session, the
  verifier and the service alike: some checks keep timers, so the call pattern is part of the task (the pattern the
  instances and references were validated with). Every reference's success also holds for 10 more still steps.
  Both instructions list what the check requires for the task (`SUCCESS` in `scripts/robocasa/envs.py`, read off the
  upstream predicates): thresholds (doors ≥ 90% / ≤ 5% open, drawers ≥ 95%, knob ≥ 0.35 rad, handle 0.40 rad–π,
  spout 30°–180°, placement radii) and implicit conditions (the gripper more than 25 cm from the placed object, or
  15 cm from a pressed button; the microwave only switches on with its door closed). Text only: the grader is the
  upstream check, unchanged.
- **Determinism.** Physics is CPU-only and bit-exact. `casa_tool` turns MuJoCo's process-wide mesh cache off
  (`mj_setCacheSize(mj_globalCache(), 0)`): a mesh served from that cache can differ from a freshly compiled one
  (`mesh_polynormal`), so a scene built a second time in one process could step differently (seen on RoboCasa365 with
  MuJoCo 3.3.1). With the cache off every build is the cold build a fresh process makes, for the agent's `reset()`, the
  privileged verifier, the standard service's start and its video pass alike.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 3000 control steps (the references' authoring cap; the longest
  reference has 1007). Standard episodes have no step limit (D1): only the wall clock.
- **Standard-mode observations.** The robot's four cameras (`robot0_agentview_center/left/right`,
  `robot0_eye_in_hand`; RGB, depth, intrinsics and the current camera-to-world pose, since they move with the robot),
  its joints (positions, velocities), end-effector position and last command, and the instruction. No object poses,
  scene layout, reward or success signal. RoboCasa's goals are relational (an object onto a fixture), so there is no
  target point to give. Camera images (RGB and depth, in both modes and in replay videos) draw the visual meshes only,
  as robosuite's own cameras do; the collision geoms (geom group 0) are hidden.

## Standard-mode service (`images/robocasa/standard/server_casa.py`)
Derived from `images/mujoco/limited/server_mj.py` (via MetaWorld+'s `server_mw.py`) and identical in protocol and
lifecycle: four endpoints, RCB1, no reset, journal + per-call checkpoints with at most two resumes, startup watchdog,
SIGUSR1 collect hook, `/data` evidence, verdict before video. Differences (items 6, 7 and 11: the grading):
1. The action type, channels and limits come from the instance (`casa_tool.action_spec`), not a fixed `joint_position`.
2. Watching (`/observe` with `seconds > 0`) holds the robot still (delta channels zero; targets, grip and mode kept).
3. Camera calibration is computed for every response (robot-mounted cameras move); `meta.task` is the instruction.
4. The protocol is reported as `eai-standard/2.1`, with HumanoidBench's client (accepts both spellings); a simulator
   error (500) ends the episode with `reason = "error"`; a body over 64 MB gets 413; the grader writes numeric fields.
5. A first collect hook stops every process in the agent's container before the episode is ended (as HumanoidBench).
6. **Graded by the live episode** (since 2026-10-17, owner, boards 0150 / 0151; `finalize()`). When the episode ends
   (the collect hook's SIGUSR1 after the agent's container was stopped) the service judges the episode it ran:
   `success = live_success ∧ ¬initial_success ∧ reason ≠ "error"`, where `live_success` is the environment's own
   `_check_success` as the live episode last ran it (after the last executed control step; the check's call pattern,
   twice per step, is the privileged verifier's) and `initial_success` is the check at the scene's start. No settle or
   hold window: the privileged rule has none, and the replay it replaces ran the same steps and nothing more. An
   episode ended by a simulator error is no success (its last state is a partial step's). Nothing is replayed to grade
   it. It writes the trajectory and the verdict together with `"finalized": true` in one atomic write of `final.json`
   (`graded_by = "live"`, `replays = 0`, `live_state_sha` = `state_sha`, `video_source = "render"`). Only then it
   renders `replay.mp4` / `replay.last.png`: one render pass, the live session rebuilt from the frozen instance runs the
   trajectory with its camera on (at most about 300 frames, under a temporary name, renamed when complete;
   `/data/video.pending` exists and `final.json` says `"video_pending": true` meanwhile). It can add `"video": true`
   and nothing else, and compares nothing. An exception, a crash (the restarted service finds the verdict and idles:
   nothing is replayed or rewritten; `video_pending` is cleared) or the hook giving up on the video leave the verdict
   as it is. `_give_up` never overwrites a `final.json` that has a verdict. `tests/grade.py` passes iff the service's
   verdict is a success, `live_success` holds and nothing is infrastructure; `reward.json` has `graded_by_live = 1`,
   `replays = 0` and no `deterministic` / `replay_success`. Infrastructure (`infra_error = 1`, H.5's one retry): no,
   an unreadable or an unfinalized `final.json`; a give-up after crashes not all inside the agent's calls
   (`sim_crashed`, `resume_failed`); `instance_mismatch` (item 11); `finalize_error`. The agent's own result (0, never
   infra): a crash inside its calls (`sim_crashed_on_call`), a simulator error from its actions (`sim_error`), the
   timeout. Before 2026-10-17 a fresh `casa_tool.Session` in the same process replayed the trajectory and
   `success = live ∧ replay ∧ deterministic ∧ ¬initial` (2026-10-10 to 2026-10-17: verdict before video; before
   2026-10-10 verdict and video in one window).
7. **Collect hook** `environment/sim/finalize.sh` (`scripts/robocasa/shared/finalize.sh`; `timeout_sec = 3600`). It
   sends SIGUSR1 (again every 30 s) and waits for the verdict, then for the video, up to 3450 s in all on the clock
   (`RCB_COLLECT_WAIT_S`). The verdict takes a second; the wait is long only for a service that crashed late in the
   episode and resumes it from its journal first (crash recovery replays the journal, at most the episode's physics):
   a wait cut short there would turn a live result into an infrastructure failure (RoboCasa365's lesson of board 0136,
   where the pre-2026-10-10 hook gave up on its grading replay). Without any episode (the service never became ready)
   it stops after 600 s. Budget of the video's render pass: one scene build (20–60 s), the episode's physics once more
   at about 0.035 s per control step (oracle trials, 2026-10-02: replay and video passes together 0.064–0.078 s per
   step; the live service takes 0.047–0.062 s per step with its cameras) and at most about 300 frames (OSMesa,
   320 x 240), so 3450 s covers about 95,000 control steps, 48,000 on a host twice as slow; the live episode ran the
   same physics plus its cameras within the agent's hour. Cost per trial: about one replay's worth of CPU time
   (0.035 s per step, about 3 minutes for a 5,000-step episode, 30–60 minutes at most for an hour-long one) on the
   sidecar's CPUs, no GPU; the grading replay it replaces cost the same again (2026-10-02 to 10-17: replay + video
   pass ≈ 2 × that). The hook's 3600 s is a number of its own, sized for the agent cutoff of 3600 s (the cutoff is
   each task's own `[agent] timeout_sec`, history in `docs/CUTOFFS.md`, and every instruction states it in its
   closing `## Time limit` section): lowering the cutoff keeps it safe, raising it means raising `COLLECT_TIMEOUT_S` in
   the three RoboCasa generators too. Before 2026-10-17 the video waited at most as long again as the verdict took
   + 120 s; before 2026-10-10 the hook waited 980 s of a 1500 s timeout for verdict and video together, which lost
   episodes over about 10,000 control steps.
8. **Request validation.** A request is checked as a whole before any physics (`parse_submit` / `parse_observe`):
   a `dt`, `seconds` or `video_fps` that is not a finite number in range, `cameras` that is not a list of names,
   a `note` that is not a string, actions that are not a `(T, N)` array of finite numbers are a 400 and nothing ran
   (PROTOCOL §4.6); `null` means "not given". Only an error while the simulator executes is a 500 and ends the
   episode. Kept as it was: camera names the robot does not have are ignored, and an unknown `video` value means
   "last frame only". `dt = 0` used to mean `control_dt` and is now a 400.
9. Since 2026-10-13 `time_s` and `time_left_s` count from the agent's first request to the service (any endpoint;
   logged as `first_request` in `episode.jsonl`, which a resume reads back), as in every other benchmark
   (STANDARD_MODE.md, "The agent's clock"). The rule of 2026-10-10 below started the clock too early: Harbor counts
   the agent's cutoff around the agent's run only, and the sidecar starts with the environment, before the harness
   is installed (a median of 79 s earlier over the recorded trials, board 0085), so `time_left_s` reached 0 while the
   agent still had that time. 2026-10-10 to 2026-10-13:
   `time_left_s` counts from the first start of the service's process (the first line of `startups.jsonl`). The
   sidecar starts together with the agent's container, so this is the agent's own clock to within a second or two
   (oracle trial: 1.1 s after it; earlier when the harness sets the agent up first). Before, it counted from the end
   of the scene build (27 s later in that trial, more after a failed start) and overstated what was left by that
   much. `time_s` and `elapsed_s` count from the episode's start (the service ready), as before.

Tests: `scripts/robocasa/tests/test_graders.py` (CI `unit-tests`): the grader on forged records and, with numpy, the
service and its collect hook on a stand-in tool module (live success / failure, a success lost before the end, a
failed video, a simulator error, crashes inside and between calls, the start check; no replay runs);
`scripts/mujoco-playground/tests/test_standard_2_1_servers.py` (`TestServerCasa`): request handling, the agent's clock,
the camera pose.

10. **Camera calibration = the rendered viewpoint** (2026-10-13, board 0093; found in board 0086). `cam2world_gl` is
   `data.cam_xpos` / `data.cam_xmat` of the camera, the pose the renderer draws the mono RGB and depth images from
   (`cam2world()`, as `server_mj.py` since #135). Until 2026-10-13 it was MuJoCo's left-eye camera `scene.camera[0]`,
   which sits half the camera's interpupillary distance (`cam_ipd` 0.068 m) to its left: 3.4 cm off, in all three
   RoboCasa benchmarks. Checked with MuJoCo's own renders of 4 mm marker spheres at known world points (nothing else
   drawn), every served camera, at the start and after the robot had moved: the marker's projection through the
   reported calibration was 10.5–10.7 px median (up to 28 px for near points, always to the same side) from where it was
   drawn, and is now 0.15 px median, at most 0.4 px. The intrinsics (`fx = fy = (H / 2) / tan(fovy / 2)`, principal
   point at the image centre) were already right: every camera of these models is given by its `fovy` (no
   `sensorsize`, checked on the RoboCasa, RoboCasa365 and RoboCasa-GR1 models), unlike ALOHA's (#164). **Standard-mode
   results from before 2026-10-13 used the offset calibration** (a point located from the images came out about
   3.4 cm to the side; agents missed a microwave button by 3.5 cm) and are not strictly comparable with later ones.
   The service is copied into each task (`environment/sim/server_casa.py`, mounted into the sidecar): no image rebuild.
11. **Start-state check** (2026-10-17, board 0151; `_start_mismatch()`). With no replay from the frozen instance, the
   start is checked when a fresh episode begins, before the port is bound: the instance file's own hash against
   `RCB_INSTANCE_SHA` (frozen/report.json; `casa_tool` also checks the file against its embedded hash on load), the
   start state's hash (`casa_tool.state_hash`: MuJoCo integration state, the model arrays the kitchen rewrites, the
   task's Python state) against `RCB_START_SHA` (`scripts/<benchmark>/frozen/start_state.json`: the hash every
   archived standard episode of the instance logged at its start, 776 episodes of 102 instances of the three
   benchmarks, 2026-10-02 to 10-17, every runner host, never two values for one instance; `import_references.py`
   records it for an instance imported from now on), and the scene must not be solved at the start (no frozen
   instance is). A mismatch gives up as `instance_mismatch`, `infra_error = 1`; the agent is never served. Both
   variables are in the task's `environment/docker-compose.yaml` (the sidecar's environment; the agent never sees
   it). Not checked: an instance without an archived episode (RoboCasa365 `PortionInTupperware`) has no start hash,
   only the file's; re-record `start_state.json` whenever the image or `casa_tool` changes how a scene is built.

## Change log
- 2026-10-17 (owner, boards 0150/0151): standard mode graded by the live episode (items 6, 7, 11); no grading replay;
  video by one render pass from the trajectory after the verdict; the start checked against the frozen instance at
  the episode's start. 103 standard task directories of the RoboCasa series regenerated (and RoboCasa365's
  standard-realtime twin); scene, instances, success check, cutoff and what the agent sees except the instruction's
  scoring sentence unchanged, so the tasks keep their names. Archived results: re-score with `live_success` (see the
  board 0151 report).

## Egress
The demonstrations (the references) are public, so `task.toml` closes agent egress to the model APIs and the package registries
(`network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`), as DexToolBench and HumanoidBench do.
The image contains no demonstration data and no pointer to it: the Dockerfile deletes RoboCasa's
`robocasa/scripts/download_datasets.py` and the clone's `.git`, and blanks the demonstration links (`*.hdf5`) in
`robocasa/utils/dataset_registry.py`, in the clone's own layer, with build-time assertions. Nothing the tasks import
uses the registry (only `robocasa/demos`, `robocasa/scripts` and `utils/{env,eval}_utils` import it).

## Image
`images/robocasa/Dockerfile` pins the base image by digest, every pip package, the RoboCasa commit and every asset
archive by SHA-256 (`fetch_objects.sh` for the object meshes). It reproduces the content of the image the tasks were
validated with, which was built in the PR #4 era from the same pins in several steps; that build is the one tagged
`eai-robocasa:0.1.0` on the authoring machine. **That build predates the §2.7 scrub above (it still has the
downloader, the links and `.git`): the image must be rebuilt from this Dockerfile before it is pushed or used for
runs.** The scrub touches no file the simulation loads, so the hashes below should not move. **A clean rebuild from this Dockerfile has not been run yet** (it
downloads ~12 GB and needs ~50 GB of free disk; the authoring machine had ~30 GB): run it, then `freeze`-check the
hashes (`import_references.sh`, which must report the same `instance_sha`, `live_state_sha` for every task), before
publishing. Licences: RoboCasa code MIT, robocasa/robocasa-assets CC-BY-4.0, jianzhang96/robocasa-assets Apache-2.0,
RoboCasa's own object archives on UT Box (CC-BY-4.0, as RoboCasa licenses its assets on robocasa/robocasa-assets), NVIDIA PhysicalAI-DigitalCousin-Assets (lightwheel, sketchfab meshes)
**CC-BY-NC-4.0** (non-commercial; maintainers to confirm the image may be published, otherwise `BUILD_ONLY`).

## Rebuilding the tasks
```bash
docker build -t ghcr.io/mll-lab-nu/eai-robocasa:$(cat images/robocasa/VERSION) images/robocasa
bash scripts/robocasa/import_references.sh <PR #4 checkout>   # instances + references -> scripts/robocasa/frozen/
python3 scripts/robocasa/generate.py                            # -> tasks/robocasa-* (ends with scripts/task_conventions.py normalize); re-running reproduces them
python3 scripts/robocasa/generate.py --check                    # tasks/ equals a fresh render (no simulator needed)
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/robocasa-*
```
The instances and references were authored in PR #4 (`scripts/coverage/author_demo.py` there: freeze the
demonstration's initial state, execute its actions with the native controller, validate in fresh processes);
`frozen/` keeps them, and `import_references.sh` re-verifies them with this benchmark's tooling.

## Evidence
`scripts/robocasa/frozen/report.json`, for all 29: not solved at the start; `reset()` bit-exact; the reference
(87–1007 actions) succeeds on its final state without truncation; two replays in fresh processes end in the live
state's hash and succeed; the success survives 10 more still steps.

Harbor runs on the generated tasks (AMD Ryzen 9 7950X, Docker, no GPU): `-a oracle` 29/29 privileged and 6/6 standard
score 1; `-a nop` scores 0 on four tasks per mode; on the final task digests (protocol v1.0.1 names and READMEs) oracle
and nop again on a sample. Scripted cheat attempts and two Codex red-team trials score 0. Agent results are not kept in
the repository (PROTOCOL D3).

## Easy set

The benchmark owner's screening of 2026-10-17 (results dashboard snapshot 2026-10-17T05:59:33Z; ten runs, one trial per
run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy is in the easy set (`docs/easy_set.toml`, reason
`solved`): kept under its name and reported apart from the main table.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

9 of 29 bases are in the easy set; by directory: 38 easy, 1 hard, 19 unverified, 0 pending.

| base | easy set | privileged | standard |
|---|---|---|---|
| `robocasa-arrange-vegetables-i00` |  | easy: Luna | unverified |
| `robocasa-close-double-door-i00` |  | easy: Luna | unverified |
| `robocasa-close-drawer-i00` |  | easy: Luna | unverified |
| `robocasa-close-single-door-i00` |  | easy: Luna | unverified |
| `robocasa-coffee-press-button-i00` | yes | easy: Luna | easy: Luna |
| `robocasa-coffee-serve-mug-i00` |  | easy: Luna | unverified |
| `robocasa-coffee-setup-mug-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash, Qwen3.8 27B | easy: Opus, Sol 6.1 |
| `robocasa-microwave-thawing-i00` |  | easy: Astra, Sol 6.1, Sol, Gemini 4 Argon | hard (only Astra) |
| `robocasa-open-double-door-i00` |  | easy: Luna | unverified |
| `robocasa-open-drawer-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon |
| `robocasa-open-single-door-i00` |  | easy: Luna | unverified |
| `robocasa-pnp-cab-to-counter-i00` |  | easy: Luna | unverified |
| `robocasa-pnp-counter-to-cab-i00` | yes | easy: Luna | easy: Luna |
| `robocasa-pnp-counter-to-microwave-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash, Qwen3.8 27B | easy: Astra, Gemini 3.8 Flash, Gemini 4 Argon |
| `robocasa-pnp-counter-to-sink-i00` | yes | easy: Luna | easy: Luna |
| `robocasa-pnp-counter-to-stove-i00` |  | easy: Luna | unverified |
| `robocasa-pnp-microwave-to-counter-i00` |  | easy: Luna | unverified |
| `robocasa-pnp-sink-to-counter-i00` | yes | easy: Luna | easy: Luna |
| `robocasa-pnp-stove-to-counter-i00` |  | easy: Luna | unverified |
| `robocasa-pre-soak-pan-i00` |  | easy: Luna | unverified |
| `robocasa-prepare-coffee-i00` |  | easy: Luna | unverified |
| `robocasa-restock-pantry-i00` |  | easy: Luna | unverified |
| `robocasa-turn-off-microwave-i00` |  | easy: Luna | unverified |
| `robocasa-turn-off-sink-faucet-i00` |  | easy: Luna | unverified |
| `robocasa-turn-off-stove-i00` |  | easy: Luna | unverified |
| `robocasa-turn-on-microwave-i00` | yes | easy: Luna | easy: Luna |
| `robocasa-turn-on-sink-faucet-i00` |  | easy: Luna | unverified |
| `robocasa-turn-on-stove-i00` |  | easy: Luna | unverified |
| `robocasa-turn-sink-spout-i00` | yes | easy: Luna | easy: Luna |

Judgment calls: `robocasa-pnp-counter-to-cab-i00`: the one standard solve hit the 3600 s agent timeout after its episode
was recorded (graded as a success).
