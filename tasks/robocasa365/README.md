# RoboCasa365

## Overview

50 of [RoboCasa365](https://github.com/robocasa/robocasa)'s kitchen tasks (robocasa 1.0.1) with a mobile manipulator
(Franka Panda on an Omron mobile base with a torso lift), each on one frozen instance, in the privileged and standard
modes (100 task directories), and one realtime task, `robocasa365-turn-on-toaster-oven-i00-realtime`: 101 task
directories.

- **privileged**: the agent has the full simulator (`casa_tool.Session`: the RoboCasa365 environment rebuilt from the
  frozen instance, its state, unlimited resets) and hands in one trajectory of control-step commands, which the
  verifier replays open-loop.
- **standard**: the simulator runs in a `sim` sidecar the agent cannot open. The agent gets only the client (and the
  same service as MCP tools): the robot's four cameras, proprioception and action chunks of the robot's native command;
  one episode, no reset, no object poses, no success signal.
- **realtime**: the standard interface on a clock that does not stop.

Every task is graded by the environment's own `_check_success`. The task directories are the deliverable; the tooling
that built them is kept outside this repository.

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/robocasa365 -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it. Base image: `ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0` (`images/robocasa365/`),
CPU only (rendering with OSMesa), about 27 GB. To build it yourself instead, from the repository root:

```bash
docker build -f images/robocasa365/Dockerfile -t ghcr.io/mll-lab-nu/efe:robocasa365-$(cat images/robocasa365/VERSION) images/robocasa365
```

A clean build needs about 11 GB of downloads and 55 GB of disk.

## Upstream and license

- Upstream: RoboCasa365, [robocasa/robocasa](https://github.com/robocasa/robocasa) pinned at
  `4f8a2980def75a55dff96b990745b83540425f09` (robocasa 1.0.1), MIT License (Copyright (c) 2026 the RoboCasa Team).
  Citation: Nasiriany et al., 2026, "RoboCasa365: A Large-Scale Simulation Framework for Training and Benchmarking
  Generalist Robots", ICLR 2026; RoboCasa: Nasiriany et al., 2024, RSS 2024.
- Simulation framework: [robosuite](https://github.com/ARISE-Initiative/robosuite) pinned at `5ce6643` (1.5.2, MIT
  License), on MuJoCo 3.3.1 (Apache License 2.0).
- Assets: RoboCasa's assets (robocasa/robocasa-assets on Hugging Face: textures, generative textures, Objaverse and
  AI-generated objects; the Lightwheel fixtures and objects of RoboCasa's UT Box links) are under CC BY 4.0, as RoboCasa
  states (credit: RoboCasa, robocasa.ai). No non-commercial terms apply. `images/robocasa365/fetch_assets.sh` downloads
  the four archives from RoboCasa's Hugging Face mirror (byte-identical to the UT Box ones) and checks each by SHA-256;
  nothing of them is committed here.
- `images/robocasa365/Dockerfile` pins the base image by digest, every pip package, the robosuite and RoboCasa commits
  and every asset archive.

## Changes from upstream

- **Frozen instances.** Each task starts from the initial state of one official demonstration episode, frozen in
  `instance.npz` (about 0.2 to 0.3 MB): the MuJoCo integration state, the model arrays the kitchen's reset rewrites, the
  environment's Python task state and the NumPy and Python random states, with a SHA-256 checked on every load.
  Rebuilding is bit-exact.
- **MuJoCo's mesh cache is off.** With the process-wide mesh cache on, a scene built a second time in one process stepped
  differently in 14 of 61 candidate families (a mesh served from the cache differs in `mesh_polynormal` from a freshly
  compiled one). `casa_tool` turns the cache off, so every build is the cold build a fresh process makes. If the pinned
  MuJoCo lacks the cache symbols, `casa_tool` raises on import rather than run without it.
- **Task sentences.** Where upstream's language sentence for an instance is wrong or unclear, `casa_tool`'s
  `TEXT_ERRATA` replaces it. The success checks are upstream's, unchanged.
- **Cameras draw visual geoms only**, as robosuite's own cameras do: the collision geoms (geom group 0) are hidden in
  every image and video.
- **No episode termination.** The environment runs with `ignore_done`, so upstream's horizon never ends an episode, and
  a success never ends one either. Privileged trajectories are capped at 3,000 control steps; standard episodes have no
  step limit; the realtime episode ends after 3,000 control steps.

## Interface

The robot's native composite-controller command, one per control step (20 Hz), in every mode: 13 channels, the arm's
7 absolute joint position targets, the gripper, 3 base velocities, the torso and the base / arm mode
(`casa_tool.action_spec`). Each row is clipped to the controller's limits.

- **Privileged.** `casa_tool.Session` (in `/opt/tools`) rebuilds the environment from `/app/instance.npz`, steps it,
  resets it and exposes its full state. The deliverable is `/app/output/trajectory.npz` with `actions` of shape (T, 13),
  1 ≤ T ≤ 3,000.
- **Standard** (`eai-standard/3.0`): the service `embodied_first_exam/benchmarks/robocasa365/sim/server_casa.py` in the
  `sim` sidecar, taken from the files-only image `robocasa365-files`. The action type is `joint_position` (the arm
  channels are joint targets; the base and torso stay velocity-controlled). Observations: the robot's four cameras
  (`robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand`; RGB and depth,
  320 × 240, with intrinsics and current poses), its joints, the end-effector position, the last command and the
  instruction. No object poses, scene layout, reward or success signal.
- **Realtime**: the task's own adapter `environment/sim/server.py` (an `rcb_service.Sim` on `casa_tool.Session`, with the
  same frozen instance, command, cameras and success check as the standard tasks) on the shared realtime service. Slowdown
  S = 2: the measured real-time factor is 1.29 with the service capped at 4 CPUs, so S = ceil(1.5 / 1.29) = 2, one control
  step every 0.1 s of wall time. The adapter makes the renderer at start, so the first image does not stall the clock.
  The robot's cameras move with it: their intrinsics are in `/spec`, their current poses in every proprioception row
  (`cam_<camera>_*`).

## Grading

Every mode uses the environment's `_check_success`. It runs three times per control step: once inside robosuite's
`step` (the reward), before the kitchen's fixtures update their state (microwave on / off, toaster-oven and stand-mixer
readings, the scrub count), and twice more in `casa_tool.Session.step`, which keeps the last result. It also runs once at
the start. Checks with timers or counters (DrainVeggies, OvenBroilFish) count these runs, so 10 runs are about
4 control steps. A scene solved at the start is never a success.

- **Privileged** (`tests/grade.py`, from the files-only image `robocasa-files`; `tests/casa_tool.py`): one open-loop
  replay in a fresh process from the verifier's own copy of the frozen instance; pass when the check holds after the
  last row and did not hold at the start. A missing file, an invalid file (over 8 MB, not plain `.npy` arrays, no
  `actions`, a shape other than (T, 13), a non-finite value, T outside 1 to 3,000) or a replay that fails scores 0.
- **Standard** (`server_casa.py`, `tests/grade.py` from `robocasa-files`): the live episode, nothing replayed. The
  agent ends it with `POST /finish`, or the agent's time ends it; the verdict is the check's result after the last
  control step. The start is checked against the frozen instance (`RCB_INSTANCE_SHA` and `RCB_START_SHA` in each task's
  `environment/docker-compose.yaml`); a mismatch, or a scene already solved, is an infrastructure error.
- **Realtime**: the live episode, judged the same way on the state it ends in; the adapter's `live_verdict` applies the
  rule that the scene was not solved at the start. The episode also ends after 3,000 control steps (150 s of robot time).
  No reset.

Each task's README states its exact success condition, with its thresholds, from upstream's `_check_success` and the
helpers it calls.

## Tasks

The candidates are the 256 RoboCasa365 families with a validated demonstration-based reference (63 atomic, 193
composite). This benchmark takes 50 of them, deterministically. The slots are shared between atomic and composite tasks
in proportion to their sizes (12 atomic, 38 composite; the group is the module the environment class lives in). Within a
group, families are taken in the order of the SHA-256 of their environment name, skipping any whose reference does not
verify with this benchmark's tooling, until the group's slots are filled. One candidate was skipped:
`OrganizeMugsByHandle` (its reference does not reach success when replayed with the mesh cache off).

- Atomic (12): PickPlaceSinkToCounter, PickPlaceCabinetToCounter, CloseDrawer, TurnOnMicrowave, CloseOven, TurnOnStove,
  TurnOnToasterOven, OpenDishwasher, TurnOffMicrowave, PackDessert, TurnOnSinkFaucet, CloseStandMixerHead.
- Composite (38): RetrieveMeat, DrainVeggies, SanitizePrepCuttingBoard, AssembleCookingArray, ClearSink,
  CookieDoughPrep, DisplayMeatVariety, CandleCleanup, DivideBasins, BeverageSorting, StockingBreakfastFoods,
  BreadAndCheese, DeliverBrewedCoffee, PortionInTupperware, OvenBroilFish, MakeIceLemonade, TongBuffetSetup,
  AddLemonToFish, MicrowaveDefrostMeat, MealPrepStaging, MakeLoadedPotato, PrepForSanitizing, SeasoningSpiceSetup,
  PrepMarinatingMeat, PreRinseStation, SetUpCuttingStation, DessertUpgrade, SweetenCoffee, CerealAndBowl, SearingMeat,
  ThawInSink, ScrubBowl, PlateSteakMeal, DrinkwareConsolidation, ReheatMeal, ClearFoodWaste, ChooseMeasuringCup,
  OrganizeCoffeeCondiments.

Task directories: `robocasa365-<task>-i00-privileged` and `robocasa365-<task>-i00-standard` (50 each, `[metadata]
family = "robocasa365/<Env>"`, robot `franka-panda-omron`), and `robocasa365-turn-on-toaster-oven-i00-realtime`. Each
instance and reference is in its task (`environment/instance.npz`, `solution/`). Privileged references have 85 to 2,189
control steps.

## Others

- **Egress.** The demonstrations are public, so agent egress is limited to the model APIs and the package registries
  (`[agent] network_mode = "allowlist"`). The image contains no demonstration data.
- **Toaster-oven timer.** Upstream's `ToasterOven.update_state` (robocasa/models/fixtures/toaster_oven.py L232-252) has
  code that turns a set timer back by itself. In this kitchen's toaster oven it never takes effect: the door and
  temperature-knob entries of the same loop clear the timer's time stamp on every update. A
  set timer stays where it was set. The success check reads the timer after every control step.
