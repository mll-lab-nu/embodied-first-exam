# RoboCasa365

50 of [RoboCasa365](https://github.com/robocasa/robocasa)'s kitchen tasks (robocasa 1.0.1) with a mobile manipulator
(Franka Panda on an Omron mobile base), each on one frozen instance, in both modes: 100 tasks; and one standard-realtime twin:
`tasks/robocasa365/robocasa365-turn-on-toaster-oven-i00-standard-realtime`, the benchmark's one dynamic task.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/robocasa365 -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| | |
|---|---|
| upstream | robocasa/robocasa @ `4f8a2980def75a55dff96b990745b83540425f09` (robocasa 1.0.1, MIT), robosuite @ `5ce6643` (1.5.2), MuJoCo 3.3.1 |
| tasks | `tasks/robocasa365/robocasa365-<task>-i00-privileged` and `tasks/robocasa365/robocasa365-<task>-i00-standard`, 50 each |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda-omron"`, `family = "robocasa365/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0` (`images/robocasa365/`), CPU only, ~27 GB |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py`: the HumanoidBench tasks' code, the client with a docstring of its own that describes this service |
| sources | each instance and reference is in its tasks (`environment/instance.npz`, `solution/oracle.npz`); the task directories are the deliverable; the tooling that built them is kept outside this repository |

## Images

The images are public: `ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0` and the files image
`ghcr.io/mll-lab-nu/efe:robocasa365-files-<version>` (pinned by digest), so a task build pulls them. To build the simulator
image yourself instead, from the repository root:

```bash
docker build -f images/robocasa365/Dockerfile -t ghcr.io/mll-lab-nu/efe:robocasa365-$(cat images/robocasa365/VERSION) images/robocasa365
```

## Scope and selection rule
PR #4 accepted 256 RoboCasa365 families with a demonstration-based reference (63 atomic, 193 composite; the 109 others
have no official demonstration at the pinned commit or no validated reference). This benchmark takes 50 of them
(deterministically): the slots are shared between atomic and composite tasks in proportion to their
sizes (12 atomic, 38 composite; the group is the module the environment class lives in); within a group, families are
taken in the order of the SHA-256 of their environment name, skipping any whose reference does not verify with this
benchmark's tooling, until the group's slots are filled. One candidate was skipped:
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
  `reset()` and the service's start hash and video pass. With the cache off every build is the cold build a fresh process
  makes. If the pinned MuJoCo lacks the cache symbols, `casa_tool` raises on import rather than run without it.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 3000 control steps; the references have 85–2189.
  Standard episodes have no step limit (D1).
- **Standard-mode observations.** The robot's four cameras (`robot0_agentview_center/left/right`,
  `robot0_eye_in_hand`; RGB, depth, intrinsics and current poses), its joints, end-effector position, last command and
  the instruction. No object poses, scene layout, reward or success signal. Camera images (RGB and depth, in both modes
  and in replay videos) draw the visual meshes only, as robosuite's own cameras do; the collision geoms (geom group 0)
  are hidden.

## Standard-mode service
`images/robocasa/standard/server_casa.py` and the collect hook `environment/sim/finalize.sh`, the same
service and hook as RoboCasa's, byte for byte (`tasks/robocasa/README.md`: graded by the live episode, nothing
replayed, the start checked against the frozen instance (`RCB_INSTANCE_SHA`, `RCB_START_SHA` in
each task's `environment/docker-compose.yaml`, a mismatch is infrastructure), the video one render pass after the
verdict; the hook's budget; request validation; the camera calibration is the rendered viewpoint).

## Standard-realtime (`eai-standard/2.3`)
The dynamic tasks (PROTOCOL §2: each task's `[metadata] dynamics`) get a `-standard-realtime` twin. In RoboCasa365 that is **TurnOnToasterOven** only: once set, the oven's timer knob turns back
by itself (`ToasterOven.update_state`: 1/3000 of its range per simulated second, on `sim.data.time`, so a replay repeats
it bit for bit). The toaster ovens and electric kettles of other tasks move by themselves too, but no other task uses them.
- **Service.** The shared realtime layer of HumanoidBench, BiGym 2.0 and Embodied Olympics - Fun, unchanged
  (the task's `environment/sim/rcb_realtime.py`, `rcb_service.py`, `environment/rcb_client.py`, `tests/grade.py`: byte-identical
  copies of the HumanoidBench realtime tasks' files; `ci_checks/check-tooling-identity.sh`), with
  `environment/sim/server.py`, an `rcb_service.Sim` adapter on `casa_tool.Session`: the standard
  twin's frozen instance, native controller command (`joint_position`, 13 channels, clipped and reported), success
  check (`_check_success`, twice per control step) and cameras (RGB-D, 320 x 240, OSMesa on the CPU; no GPU). The
  verdict is the live episode's (the shared layer's `graded_by = live`): the last episode's success as it ran, and the
  adapter's `live_verdict()` adds the standard twin's rule that the scene was not solved at that episode's start;
  nothing is replayed. `start_sha` (`RCB_START_SHA`, the standard twin's archived start hash,
  the same value) is checked by the layer when the first episode begins and after every reset (`instance_mismatch`,
  infrastructure). The video is rendered from the trajectory after the verdict (the live session rebuilt, one pass);
  the collect hook waits up to 840 s for the verdict and 870 s for the video. The robot's cameras move with it:
  their intrinsics are in `/spec`, their current poses in every proprioception row (`cam_<camera>_*`, the standard
  twin's `cam2world_gl`). Not served: the 2.1 service's per-response calibration dictionary.
- **Episode.** The standard twin grades the state after the last step of an episode as long as the agent's time; on a
  clock that does not stop that episode would be up to an hour long. Here an episode ends at the first
  control step after which the success check holds (the privileged rule applied to the trajectory up to that step),
  after 3000 control steps (150 s of robot time, the privileged deliverable's cap; `RCB_MAX_CONTROL_STEPS`), when the
  agent's time is up, or on a simulator error. **10 resets** (PROTOCOL §4b); a reset rebuilds the scene (15-20 s,
  clock paused). The instruction tells the agent to reset with `cameras=[]`: the shared layer holds image requests back
  four times as long as the last rendering request took, and a reset that renders counts as one, so after a reset with
  cameras, images come back only much later (open: a shared-layer change would remove this).
- **Slowdown S = 2.** Real-time factor 1.29 with the realtime clock flat out (the service capped at 4 CPUs); PROTOCOL
  §2: S = ceil(1.5 / 1.29) = 2, one control step every 0.1 s of wall time. An OSMesa frame takes about 0.12 s per
  camera; `server.py` makes the renderer at start and after every reset, so the first image does not stall the clock.
- **Checked at S = 2**: the privileged reference planned from step 0 succeeds live; nop: `timeout`, not a success; a
  controller streaming one row per control step with an image every 0.5 s over 3 episodes: no stall, largest lag
  0.05 s.
- **Cutoff** 3600 s, the standard twin's.

## Egress
The demonstrations are public, so `task.toml` closes agent egress to the model APIs and the package registries. The image contains no
demonstration data.

## Image
`images/robocasa365/Dockerfile` pins the base image by digest, every pip package, the robosuite and RoboCasa commits
and every asset archive by SHA-256 (`fetch_assets.sh`; four archives from RoboCasa's Hugging Face mirror, byte-identical
to the UT Box ones). It reproduces the content of the image the tasks were validated with; the published image is that validated image
(a clean rebuild needs ~11 GB of downloads and ~55 GB of disk). Licences: RoboCasa code MIT; RoboCasa's assets
(robocasa/robocasa-assets: textures, generative textures, Objaverse and AI-generated objects; the Lightwheel fixtures and
objects from RoboCasa's UT Box links) CC-BY-4.0, as RoboCasa states (credit: RoboCasa, robocasa.ai), the same asset
terms as the public RoboCasa images.

## Evidence
For all 50: not solved at the start; `reset()` bit-exact; the reference
succeeds on its final state without truncation; two fresh-process replays end in the live state's hash and succeed.

Harbor runs on the generated tasks: `-a oracle` scores 1 (50/50 privileged, 6/6 standard sampled), `-a nop` 0;
scripted cheat attempts score 0 in both modes.

## Screening

The benchmark owner's screening (ten runs, one trial per run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy, and every base Luna solved in some mode, is left out of the core set (`docs/core_set.toml`); its tasks keep their names.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

By directory: 70 easy, 6 hard, 25 unverified, 0 pending.

| base | privileged | standard | standard-realtime |
|---|---|---|---|
| `robocasa365-add-lemon-to-fish-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | easy: Astra, Opus, Sol 6.1 | — |
| `robocasa365-assemble-cooking-array-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | hard (only Astra) | — |
| `robocasa365-beverage-sorting-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | easy: Gemini 4 Argon | — |
| `robocasa365-bread-and-cheese-i00` | easy: Luna | unverified | — |
| `robocasa365-candle-cleanup-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon | — |
| `robocasa365-cereal-and-bowl-i00` | easy: Astra, Sol 6.1, Gemini 3.8 Flash | hard | — |
| `robocasa365-choose-measuring-cup-i00` | easy: Luna | unverified | — |
| `robocasa365-clear-food-waste-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon | — |
| `robocasa365-clear-sink-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash | easy: Astra, Opus, Sol 6.1, Gemini 3.8 Flash, Gemini 4 Argon | — |
| `robocasa365-close-drawer-i00` | easy: Luna | unverified | — |
| `robocasa365-close-oven-i00` | easy: Luna | unverified | — |
| `robocasa365-close-stand-mixer-head-i00` | easy: Luna | unverified | — |
| `robocasa365-cookie-dough-prep-i00` | easy: Luna | unverified | — |
| `robocasa365-deliver-brewed-coffee-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | easy: Sol 6.1, Gemini 4 Argon | — |
| `robocasa365-dessert-upgrade-i00` | easy: Luna | unverified | — |
| `robocasa365-display-meat-variety-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | hard | — |
| `robocasa365-divide-basins-i00` | easy: Luna | unverified | — |
| `robocasa365-drain-veggies-i00` | easy: Astra, Opus, Sol 6.1, Sol | easy: Gemini 4 Argon | — |
| `robocasa365-drinkware-consolidation-i00` | easy: Luna | unverified | — |
| `robocasa365-make-ice-lemonade-i00` | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon | easy: Opus, Gemini 4 Argon | — |
| `robocasa365-make-loaded-potato-i00` | easy: Luna | unverified | — |
| `robocasa365-meal-prep-staging-i00` | easy: Astra, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon | easy: Astra, Opus | — |
| `robocasa365-microwave-defrost-meat-i00` | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon | hard | — |
| `robocasa365-open-dishwasher-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Sol, Gemini 4 Argon, DeepSeek V4.1 Flash | — |
| `robocasa365-organize-coffee-condiments-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 4 Argon | — |
| `robocasa365-oven-broil-fish-i00` | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon | easy: Astra, Opus | — |
| `robocasa365-pack-dessert-i00` | easy: Luna | unverified | — |
| `robocasa365-pick-place-cabinet-to-counter-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Opus, Gemini 4 Argon | — |
| `robocasa365-pick-place-sink-to-counter-i00` | easy: Luna | unverified | — |
| `robocasa365-plate-steak-meal-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | — |
| `robocasa365-portion-in-tupperware-i00` | easy: Luna | unverified | — |
| `robocasa365-pre-rinse-station-i00` | easy: Luna | unverified | — |
| `robocasa365-prep-for-sanitizing-i00` | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon | easy: Astra, Opus | — |
| `robocasa365-prep-marinating-meat-i00` | easy: Luna | unverified | — |
| `robocasa365-reheat-meal-i00` | easy: Astra, Gemini 4 Argon | easy: Opus | — |
| `robocasa365-retrieve-meat-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon | easy: Opus, Gemini 3.8 Flash, Gemini 4 Argon | — |
| `robocasa365-sanitize-prep-cutting-board-i00` | easy: Luna | unverified | — |
| `robocasa365-scrub-bowl-i00` | easy: Luna | unverified | — |
| `robocasa365-searing-meat-i00` | easy: Astra, Opus | hard | — |
| `robocasa365-seasoning-spice-setup-i00` | easy: Luna, Astra, Sol 6.1, Gemini 4 Argon | hard | — |
| `robocasa365-set-up-cutting-station-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash | easy: Astra, Sol 6.1 | — |
| `robocasa365-stocking-breakfast-foods-i00` | easy: Luna | unverified | — |
| `robocasa365-sweeten-coffee-i00` | easy: Luna | unverified | — |
| `robocasa365-thaw-in-sink-i00` | easy: Luna | unverified | — |
| `robocasa365-tong-buffet-setup-i00` | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash | easy: Opus | — |
| `robocasa365-turn-off-microwave-i00` | easy: Luna | unverified | — |
| `robocasa365-turn-on-microwave-i00` | easy: Luna | unverified | — |
| `robocasa365-turn-on-sink-faucet-i00` | easy: Luna | unverified | — |
| `robocasa365-turn-on-stove-i00` | easy: Luna | unverified | — |
| `robocasa365-turn-on-toaster-oven-i00` | easy: Luna | unverified | easy: Luna |

Judgment calls: `robocasa365-beverage-sorting-i00`: the one standard solve hit the 3600 s agent timeout after its
episode was recorded (graded as a success).
