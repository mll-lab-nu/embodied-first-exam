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
  verifier and the service's verification replay alike.
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
SIGUSR1 collect hook, `/data` evidence, verdict before video. Differences:
1. The action type, channels and limits come from the instance (`casa_tool.action_spec`), not a fixed `joint_position`.
2. Watching (`/observe` with `seconds > 0`) holds the robot still (delta channels zero; targets, grip and mode kept).
3. Camera calibration is computed for every response (robot-mounted cameras move); `meta.task` is the instruction.
4. The protocol is reported as `eai-standard/2.1`, with HumanoidBench's client (accepts both spellings); a simulator
   error (500) ends the episode with `reason = "error"`; a body over 64 MB gets 413; the grader writes numeric fields.
5. A first collect hook stops every process in the agent's container before the episode is ended (as HumanoidBench).
6. **The verdict is final before the video** (2026-10-10). At the end of the episode the service replays it in a fresh
   simulator and writes the verdict together with `"finalized": true` in one atomic write of `final.json` (temporary
   file + rename). Only then it renders `replay.mp4` / `replay.last.png` (a second replay, under a temporary name,
   renamed when complete; `/data/video.pending` exists meanwhile): optional, it can add `"video": true` and nothing
   else. An exception, a crash (the restarted service finds the verdict and idles: nothing is replayed or rewritten)
   or the hook giving up on the video leave the verdict as it is. `_give_up` never overwrites a `final.json` that has
   a verdict (`deterministic`), finalized or not.
7. **Collect hook** `environment/sim/finalize.sh` (`scripts/robocasa/shared/finalize.sh`; `timeout_sec = 3600`). It
   sends SIGUSR1 (again every 30 s) and waits for the verdict for up to 3450 s on the clock (`RCB_COLLECT_WAIT_S`),
   then for the video for at most as long again as the verdict took + 120 s. Without any episode (the service never
   became ready) it stops after 600 s. Budget: the verdict costs one scene build (20–60 s) and one replay at about
   0.035 s per control step (oracle trials, 2026-10-02: both passes together 0.064–0.078 s per step; the live service
   takes 0.047–0.062 s per step with its cameras), so 3450 s covers about 97,000 control steps, 48,000 on a host
   twice as slow. Episodes have no step limit (D1), but the replay runs the episode's own physics once more without
   its cameras, in the same container: it cannot take longer than the agent's hour did. Before, the hook waited
   980 s of a 1500 s timeout for verdict and video together, which lost episodes over about 10,000 control steps.
8. **Request validation.** A request is checked as a whole before any physics (`parse_submit` / `parse_observe`):
   a `dt`, `seconds` or `video_fps` that is not a finite number in range, `cameras` that is not a list of names,
   a `note` that is not a string, actions that are not a `(T, N)` array of finite numbers are a 400 and nothing ran
   (PROTOCOL §4.6); `null` means "not given". Only an error while the simulator executes is a 500 and ends the
   episode. Kept as it was: camera names the robot does not have are ignored, and an unknown `video` value means
   "last frame only". `dt = 0` used to mean `control_dt` and is now a 400.
9. `time_left_s` counts from the first start of the service's process (the first line of `startups.jsonl`). The
   sidecar starts together with the agent's container, so this is the agent's own clock to within a second or two
   (oracle trial: 1.1 s after it; earlier when the harness sets the agent up first). Before, it counted from the end
   of the scene build (27 s later in that trial, more after a failed start) and overstated what was left by that
   much. `time_s` and `elapsed_s` count from the episode's start (the service ready), as before.

Synthetic tests of 6–8 (a stub in place of the simulator; no MuJoCo) were run for the change; they are not part of the
repository's checks.

## Egress
The demonstrations (the references) are public, so `task.toml` closes agent egress to the model APIs
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
