# RoboCasa365

50 of [RoboCasa365](https://github.com/robocasa/robocasa)'s kitchen tasks (robocasa 1.0.1) with a mobile manipulator
(Franka Panda on an Omron mobile base), each on one frozen instance, in both modes: 100 tasks.

| | |
|---|---|
| upstream | robocasa/robocasa @ `4f8a2980def75a55dff96b990745b83540425f09` (robocasa 1.0.1, MIT), robosuite @ `5ce6643` (1.5.2), MuJoCo 3.3.1 |
| tasks | `tasks/robocasa365-<task>-i00-privileged` and `tasks/robocasa365-<task>-i00-standard`, 50 each |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda-omron"` (to be added to TAXONOMY), `family = "robocasa365/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robocasa365:0.1.0` (`images/robocasa365/`), CPU only, ~27 GB |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py` as in the HumanoidBench tasks |
| generator | `scripts/robocasa365/` (`select_instances.py`, `import_references.sh` -> `frozen/`, `generate.py` -> `tasks/`) |

## Scope and selection rule
PR #4 accepted 256 RoboCasa365 families with a demonstration-based reference (63 atomic, 193 composite; the 109 others
have no official demonstration at the pinned commit or no validated reference). This benchmark takes 50 of them
(`select_instances.py`, deterministic): the slots are shared between atomic and composite tasks in proportion to their
sizes (12 atomic, 38 composite; the group is the module the environment class lives in); within a group, families are
taken in the order of the SHA-256 of their environment name, skipping any whose reference does not verify with this
benchmark's tooling (`import_references.py`), until the group's slots are filled. One candidate was skipped:
`OrganizeMugsByHandle` (its reference does not reach success when replayed with MuJoCo's mesh cache off (every build cold); PR #4 had accepted it with the cache on).

- Atomic (12): PickPlaceSinkToCounter, PickPlaceCabinetToCounter, CloseDrawer, TurnOnMicrowave, CloseOven, TurnOnStove, TurnOnToasterOven, OpenDishwasher, TurnOffMicrowave, PackDessert, TurnOnSinkFaucet, CloseStandMixerHead.
- Composite (38): RetrieveMeat, DrainVeggies, SanitizePrepCuttingBoard, AssembleCookingArray, ClearSink, CookieDoughPrep, DisplayMeatVariety, CandleCleanup, DivideBasins, BeverageSorting, StockingBreakfastFoods, BreadAndCheese, DeliverBrewedCoffee, PortionInTupperware, OvenBroilFish, MakeIceLemonade, TongBuffetSetup, AddLemonToFish, MicrowaveDefrostMeat, MealPrepStaging, MakeLoadedPotato, PrepForSanitizing, SeasoningSpiceSetup, PrepMarinatingMeat, PreRinseStation, SetUpCuttingStation, DessertUpgrade, SweetenCoffee, CerealAndBowl, SearingMeat, ThawInSink, ScrubBowl, PlateSteakMeal, DrinkwareConsolidation, ReheatMeal, ClearFoodWaste, ChooseMeasuringCup, OrganizeCoffeeCondiments.

## Task definition
- **Instance.** The initial state of an official demonstration episode, frozen in `instance.npz` (~0.2–0.3 MB): the
  MuJoCo integration state, the model arrays the kitchen's reset rewrites, the env's Python task state and the
  NumPy / Python RNG states, with a SHA-256 checked on every load. Rebuilding is bit-exact.
- **Actions.** The robot's native composite-controller command, one per control step (20 Hz), in both modes: 13
  channels, absolute arm joint position targets (7), grip, base velocities (3), torso, hybrid mode
  (`casa_tool.action_spec`). The references track the demonstrations' recorded arm joint positions with this
  controller (RoboCasa365's demonstrations were recorded with a different arm controller; PR #4 retargeted them, with
  base and torso feedback for some). In standard mode the type is `joint_position` (its arm channels are joint
  targets; the base and torso stay velocity-controlled).
- **Success.** The environment's own `_check_success` on the state after the last action (PROTOCOL §3), and not
  already at the start. PR #4 graded RoboCasa365 by "success at any step"; here every reference succeeds on its final
  state (none had to be cut). The check runs twice per control step and once at reset everywhere. In
  1 task (PlateSteakMeal) the success does not survive 10 more still steps; its instructions (both modes) and README
  say so. Both instructions also state, per task, what `_check_success` requires beyond the task's sentence
  (`envs.SUCCESS`: releasing and moving the gripper away, distance thresholds, timers, joint thresholds), since the
  standard-mode agent cannot read the source.
- **Determinism.** CPU physics, bit-exact, with MuJoCo's process-wide mesh cache turned off in `casa_tool`: with the
  cache on, a scene built a second time in one process stepped differently in 14 of 61 candidates here (a mesh served
  from the cache differs in `mesh_polynormal` from a freshly compiled one), which would have broken the agent's own
  `reset()` and the service's verification replay. With the cache off every build is the cold build a fresh process
  makes. If the pinned MuJoCo lacks the cache symbols, `casa_tool` raises on import rather than run without it.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 3000 control steps; the references have 85–2189.
  Standard episodes have no step limit (D1).
- **Standard-mode observations.** The robot's four cameras (`robot0_agentview_center/left/right`,
  `robot0_eye_in_hand`; RGB, depth, intrinsics and current poses), its joints, end-effector position, last command and
  the instruction. No object poses, scene layout, reward or success signal.

## Standard-mode service
`images/robocasa365/standard/server_casa.py`, the same service as RoboCasa's (`docs/benchmarks/robocasa.md`).

## Egress
The demonstrations are public, so `task.toml` closes agent egress to the model APIs. The image contains no
demonstration data.

## Image
`images/robocasa365/Dockerfile` pins the base image by digest, every pip package, the robosuite and RoboCasa commits
and every asset archive by SHA-256 (`fetch_assets.sh`; four archives from RoboCasa's Hugging Face mirror, byte-identical
to the UT Box ones). It reproduces the content of the image the tasks were validated with (built in the PR #4 era as
`rcb-robocasa365:0.1.0` from the same pins, tagged `eai-robocasa365:0.1.0` on the authoring machine). **A clean rebuild
has not been run yet** (~11 GB of downloads, ~55 GB of disk): run it and re-check the hashes with
`import_references.sh` before publishing. Licences: RoboCasa code MIT, robocasa/robocasa-assets CC-BY-4.0; the
Lightwheel fixtures and objects come from RoboCasa's UT Box links under RoboCasa's asset terms (maintainers to
confirm publishing, otherwise `BUILD_ONLY`).

## Rebuilding the tasks
```bash
docker build -t ghcr.io/embodied-agent-interface-v2-internal/eai-robocasa365:$(cat images/robocasa365/VERSION) images/robocasa365
bash scripts/robocasa365/import_references.sh <PR #4 checkout>
python3 scripts/robocasa365/generate.py      # ends with scripts/task_conventions.py normalize; re-running reproduces the tasks
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/robocasa365-*
```

## Evidence
`scripts/robocasa365/frozen/report.json`, for all 50: not solved at the start; `reset()` bit-exact; the reference
succeeds on its final state without truncation; two fresh-process replays end in the live state's hash and succeed.

Harbor runs on the generated tasks (AMD Ryzen 9 7950X, Docker, no GPU): `-a oracle` 50/50 privileged and 6/6 standard
score 1; `-a nop` scores 0 on four tasks per mode. Scripted cheat attempts score 0 in both modes.

Agent results are not kept in the repository (PROTOCOL D3).
