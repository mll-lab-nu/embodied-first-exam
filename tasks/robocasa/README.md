# RoboCasa

## Overview

[RoboCasa](https://github.com/robocasa/robocasa) v0.2 kitchen tasks with a mobile manipulator (a Franka Panda arm on an
Omron mobile base with a torso lift), each on one frozen instance, in both modes: 29 environments, 58 task directories
(`robocasa-<task>-i00-privileged`, `robocasa-<task>-i00-standard`). Both modes of an environment use the same frozen
instance and the same success rule, the environment's own `_check_success`.

- **privileged**: the agent has the full simulator (`casa_tool.Session`: the robosuite env, privileged state, unlimited
  resets, self-replay) and hands in one trajectory of native controller commands, which the verifier replays
  open-loop.
- **standard**: the simulator runs in a `sim` sidecar the agent cannot open; the agent gets the client (and the same
  service as MCP tools): the robot's cameras with their calibration, its own joints, end-effector positions and last
  command, native controller commands in chunks; one episode, no reset, no object poses, no success signal.

```bash
harbor run -d embodied-first-exam@all -p tasks/robocasa -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| | |
|---|---|
| upstream | robocasa/robocasa @ `756598a5be52e052339bb2d957426e39015c2afb` (v0.2, MIT), robosuite 1.5.1, MuJoCo 3.2.6 |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda-omron"`, `family = "robocasa/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe:robocasa-0.1.0` (`images/robocasa/`), CPU only (physics and OSMesa rendering), about 24 GB |
| shared code | `embodied_first_exam/benchmarks/robocasa/` (`casa_tool.py`, the two graders, `sim/server_casa.py`, `sim/finalize.sh`), taken from the files-only image `robocasa-files` (`images/robocasa-files/FILES.json`) |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py` from the `standard-files` image |
| instances | each instance and reference is in its tasks (`environment/instance.npz`, `solution/oracle.npz`); the task directories are the deliverable; the tooling that built them is kept outside this repository |

Each per-task README is rendered from `tasks/robocasa/readme.toml` (benchmark, license, robot, and each environment's
success condition with the upstream source lines it was read from).

## Upstream and license

- Upstream: RoboCasa, [robocasa/robocasa](https://github.com/robocasa/robocasa) at commit
  `756598a5be52e052339bb2d957426e39015c2afb` ("v0.2"), MIT License (Copyright (c) 2024 the RoboCasa Team). Citation:
  Nasiriany et al., 2024, "RoboCasa: Large-Scale Simulation of Everyday Tasks for Generalist Robots", RSS 2024.
- robosuite 1.5.1 (MIT) and MuJoCo 3.2.6 (Apache License 2.0), pinned with every other pip package in
  `images/robocasa/Dockerfile`.
- Assets, downloaded when the image is built (each archive pinned by revision and SHA-256), not in this repository:
  fixtures and textures from `robocasa/robocasa-assets` (CC-BY-4.0); v0.2 fixtures and appliance meshes from the mirror
  `jianzhang96/robocasa-assets` (Apache-2.0); RoboCasa's own objaverse and AI-generated object archives (CC-BY-4.0, as
  RoboCasa licenses its assets); the lightwheel and sketchfab object sets of NVIDIA
  `PhysicalAI-DigitalCousin-Assets` under **CC-BY-NC-4.0: non-commercial use only** (`images/robocasa/fetch_objects.sh`).

## Changes from upstream

- **Physics, models and success checks: none.** The kitchens, the robot and every `_check_success` are RoboCasa's at the
  pinned commit, installed unpatched; the graders call the upstream check unchanged.
- **Removed.** No demonstration data and no pointer to it is in the image (the demonstrations are the references):
  the Dockerfile deletes `robocasa/scripts/download_datasets.py` and the clone's `.git`, and blanks the demonstration
  links (`*.hdf5`) in `robocasa/utils/dataset_registry.py`, in the clone's own layer, with build-time assertions.
  Nothing the tasks import uses the registry. The published `robocasa-0.1.0` image was built before this step was added
  to the recipe; the step touches no file the simulation loads.
- **Frozen instances.** Each instance is the initial state of the first official demonstration episode of its task
  (episode 0 of its `v0.1/...` dataset), frozen in `instance.npz` (about 0.1 to 0.3 MB): the MuJoCo integration state,
  the model arrays the kitchen's reset rewrites, the env's Python task state (every JSON-encodable attribute of the env,
  its fixtures, robot, controllers and observables) and the NumPy / Python RNG states, with a SHA-256 checked on every
  load. Rebuilding is bit-exact. Copied into `environment/`, `tests/` and `environment/sim/`. For every instance: not
  solved at the start, `reset()` bit-exact, the reference (87 to 1007 actions) succeeds on its final state, two replays
  in fresh processes end in the same state, and the success survives 10 more still control steps.
- **Task sentences.** The agent is shown a plain sentence for each instance (`casa_tool.TEXT_ERRATA`) instead of
  RoboCasa's language string, which the instance file keeps unchanged: it names what the check needs (for example the
  hand moved away where the check has that term).
- **Mesh cache off.** `casa_tool` turns MuJoCo's process-wide mesh cache off (`mj_setCacheSize(mj_globalCache(), 0)`):
  a mesh served from that cache can differ from a freshly compiled one (`mesh_polynormal`), so a scene built a second
  time in one process could step differently. With the cache off every build is the cold build of a fresh process.
- **Episode ends.** Upstream's horizon is off in these configs (`ignore_done = True`), and no upstream evaluation step
  limit applies: a privileged deliverable has at most 3000 control steps (the references' authoring cap; the longest
  reference has 1007), a standard episode has no step limit.
- **Scope.** The 29 of RoboCasa v0.2's 111 kitchen environments that have an official demonstration in the dataset
  registry at the pinned commit and whose demonstration-based reference verifies. Not included (82): `NavigateKitchen`
  (navigation only, a different action interface, no reference); CupcakeCleanup and PastryDisplay (their scene could
  not be frozen bit-exactly); 79 environments without an official demonstration at the pinned commit, hence without a
  reference.

## Interface

- **Actions (both modes).** The robot's native composite-controller command, one per control step (20 Hz), the
  controller the demonstrations were recorded with: 12 channels (`casa_tool.action_spec`), every one clipped to [-1, 1].
  `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz`: end-effector deltas (OSC) in the robot's base frame, 1.0 = 5 cm /
  0.5 rad per step; `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw`: target velocities of force-limited
  velocity servos, 1.0 = 1 m/s or 1.5 rad/s; `torso`: a delta joint-position command, 1.0 = a height target 5 cm above
  the current height (lift range 0 to 0.34 m); `hybrid_mode` (> 0 base mode, <= 0 arm mode). Scales from robosuite
  1.5.1 `default_pandaomron.json` and `omron_mobile_base.xml`. In standard mode the type is `ee_delta`; there is no
  `joint_position` type, since the references are OSC commands.
- **Privileged mode.** `/opt/tools/casa_tool.py`: `Session(instance)`, `s.env` / `s.model` / `s.data`, `s.state()`
  (joints, every body's pose, the objects, proprio, success), `step`, `check`, `replay`, `reset`, `save_trajectory`,
  `render`. The success check runs twice after every control step and once at reset, in the agent's session, the
  verifier and the service alike. The deliverable is `/app/output/trajectory.npz`.
- **Standard mode.** The service speaks eai-standard/3.0. Observations: the robot's four cameras
  (`robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand`; RGB 320 × 240,
  depth, intrinsics and the current camera-to-world pose in every response, since the cameras move with the robot), its
  joints (positions, velocities), end-effector position and last command, and the instruction. No object poses, scene
  layout, reward or success signal; RoboCasa's goals are relational (an object onto a fixture), so there is no target
  point to give. A hold chunk (`/submit` with `interpolate: "hold"`, `seconds`, no rows) holds the robot still: the
  delta channels are zero, the grip and mode are kept. Rows may be `dt` apart (a multiple of 0.05 s); a chunk covers at
  most 10 s.
- **Camera calibration** is the rendered viewpoint: `cam2world_gl` is the camera's `data.cam_xpos` / `data.cam_xmat`,
  the pose the mono RGB and depth images are drawn from, not MuJoCo's left-eye camera; the intrinsics are
  `fx = fy = (H / 2) / tan(fovy / 2)` with the principal point at the image centre.
- **Rendering.** Camera images (in both modes and in videos) draw the visual meshes only, as robosuite's own cameras do;
  the collision geoms (geom group 0) are hidden.
- **Egress.** The demonstrations are public, so `task.toml` closes agent egress to everything but the model APIs and the
  package registries (`network_mode = "allowlist"`).

## Grading

- **Success.** The environment's own `_check_success` on one state, and the scene not solved at the start (no frozen
  instance is). Most checks combine a placement test (contact, a horizontal-distance test against a fraction of the
  receptacle's radius, or every corner of the object's bounding box inside a fixture's interior box) with the gripper's
  grip site more than 25 cm from the placed object, or 15 cm from a pressed button; door, drawer, knob, faucet and spout
  checks compare joint angles with fixed fractions or angles. The microwave's and the coffee machine's on/off states are
  updated at the end of every control step from the gripper's contact with their buttons (the microwave only with its
  door closed). Each task's README states its condition exactly, with the thresholds.
- **Privileged mode: one replay.** `tests/grade.py`, in a separate sandbox without network, replays
  `/app/output/trajectory.npz` once in a fresh process from the verifier's own copy of the instance, and grades the
  final state. A missing or invalid file (more than 8 MB, not a plain `.npz` of arrays, no `actions`, a shape other
  than (T, 12), a non-finite value, T outside 1..3000) scores 0; a replay that fails is a `grader_error` and 0.
  `reward.json` (numeric only): `success`, `deterministic`, `determinism_checked`, `replays`, `replay_success`,
  `missing_trajectory`, `invalid_trajectory`, `grader_error`, `n_actions`, `sim_steps`, `final_reward`,
  `video_rendered`, `verifier_wall_s`. The verdict is on disk before the video is rendered.
- **Standard mode: the live episode.** The service (`embodied_first_exam/benchmarks/robocasa/sim/server_casa.py`)
  grades the episode it ran: when the episode ends (the agent's `POST /finish`, or the collect hook's SIGUSR1 after the
  agent's container was stopped), `success = live_success ∧ ¬initial_success ∧ reason ≠ "error"`, where
  `live_success` is `_check_success` as the live episode last ran it, after the last executed control step. No settle
  or hold window, no step limit, nothing replayed. The check runs after every call and is only recorded; it never ends
  the episode. `final.json` gets the verdict in one atomic write (`graded_by = "live"`, `replays = 0`, `finalized`);
  only then the video is rendered from the recorded trajectory (one render pass), which decides nothing.
  `tests/grade.py` passes iff the service's verdict is a success, `live_success` holds and nothing is infrastructure.
- **Start-state check.** Before the port is bound, the service checks the instance file's hash against
  `RCB_INSTANCE_SHA` and the start state's hash (`casa_tool.state_hash`: MuJoCo integration state, the model arrays the
  kitchen rewrites, the task's Python state) against `RCB_START_SHA` (both in each task's
  `environment/docker-compose.yaml`, the sidecar's environment), and that the scene is not solved at the start. A
  mismatch gives up as `instance_mismatch`, `infra_error = 1`; the agent is never served. `RCB_START_SHA` changes
  whenever the image or `casa_tool` changes how a scene is built.
- **Infrastructure vs agent failures** (standard `tests/grade.py`): `infra_error = 1` for a missing, unreadable or
  unfinalized `final.json`, a give-up after crashes not all inside the agent's calls (`sim_crashed`, `resume_failed`),
  `instance_mismatch` or `finalize_error`. The agent's 0: a crash inside its calls (`sim_crashed_on_call`), a simulator
  error from its actions (`reason = "error"`), a failed check at the end.
- **Collect hook budget.** `environment/sim/finalize.sh` (`timeout_sec = 3600`) waits for the verdict, then for the
  video, up to 3450 s in all (`RCB_COLLECT_WAIT_S`). The video's render pass costs one scene build (20 to 60 s), the
  episode's physics once more at about 0.035 s per control step, and at most about 300 frames (OSMesa, 320 × 240), so
  3450 s covers about 95,000 control steps (48,000 on a host twice as slow). The hook's 3600 s is sized for an agent
  time limit of 3600 s: raising a task's time limit means raising the hook's `timeout_sec` too.

## Tasks

29 environments, each with one privileged and one standard task (`i00`, instance seed 0).

| family | environment (upstream file) | what is checked |
|---|---|---|
| `robocasa/ArrangeVegetables` | multi_stage/chopping_food/arrange_vegetables.py | carrot and lemon on the cutting board, hand away from the board |
| `robocasa/CloseDoubleDoor` | single_stage/kitchen_doors.py | both cabinet doors at most 5% open |
| `robocasa/CloseDrawer` | single_stage/kitchen_drawer.py | the drawer at most 5% open |
| `robocasa/CloseSingleDoor` | single_stage/kitchen_doors.py | the microwave door at most 5% open |
| `robocasa/CoffeePressButton` | single_stage/kitchen_coffee.py | the coffee machine on, hand away from the button |
| `robocasa/CoffeeServeMug` | single_stage/kitchen_coffee.py | the mug touching the counter, hand away |
| `robocasa/CoffeeSetupMug` | single_stage/kitchen_coffee.py | the mug under the spout, hand away |
| `robocasa/MicrowaveThawing` | multi_stage/defrosting_food/microwave_thawing.py | the squash inside the microwave, the microwave on, hand away |
| `robocasa/OpenDoubleDoor` | single_stage/kitchen_doors.py | both cabinet doors at least 90% open |
| `robocasa/OpenDrawer` | single_stage/kitchen_drawer.py | the drawer at least 95% open |
| `robocasa/OpenSingleDoor` | single_stage/kitchen_doors.py | the cabinet door at least 90% open |
| `robocasa/PnPCabToCounter` | single_stage/kitchen_pnp.py | the hot dog touching the counter, hand away |
| `robocasa/PnPCounterToCab` | single_stage/kitchen_pnp.py | the cake inside the cabinet, hand away |
| `robocasa/PnPCounterToMicrowave` | single_stage/kitchen_pnp.py | the corn on the plate, the plate touching the microwave, hand away |
| `robocasa/PnPCounterToSink` | single_stage/kitchen_pnp.py | the apple in the sink, hand away |
| `robocasa/PnPCounterToStove` | single_stage/kitchen_pnp.py | the potato in the pan (within 7 cm), hand away |
| `robocasa/PnPMicrowaveToCounter` | single_stage/kitchen_pnp.py | the onion on the plate, hand away |
| `robocasa/PnPSinkToCounter` | single_stage/kitchen_pnp.py | the tomato on the plate, the plate on the counter, hand away |
| `robocasa/PnPStoveToCounter` | single_stage/kitchen_pnp.py | the steak on the plate (within 7 cm), hand away |
| `robocasa/PreSoakPan` | multi_stage/washing_dishes/pre_soak_pan.py | pan and sponge inside the sink, the water on, hand away from the pan |
| `robocasa/PrepareCoffee` | multi_stage/brewing/prepare_coffee.py | the mug under the spout, the machine on, hand away from mug and button |
| `robocasa/RestockPantry` | multi_stage/restocking_supplies/restock_pantry.py | both cans inside the cabinet, next to the can already there, hand away |
| `robocasa/TurnOffMicrowave` | single_stage/kitchen_microwave.py | the microwave off, hand away from the stop button |
| `robocasa/TurnOffSinkFaucet` | single_stage/kitchen_sink.py | the faucet handle at most 0.40 rad |
| `robocasa/TurnOffStove` | single_stage/kitchen_stove.py | the front right knob within 0.35 rad of off |
| `robocasa/TurnOnMicrowave` | single_stage/kitchen_microwave.py | the microwave on, hand away from the start button |
| `robocasa/TurnOnSinkFaucet` | single_stage/kitchen_sink.py | the faucet handle above 0.40 rad |
| `robocasa/TurnOnStove` | single_stage/kitchen_stove.py | the front left knob at least 0.35 rad from off |
| `robocasa/TurnSinkSpout` | single_stage/kitchen_sink.py | the spout between 30° and 180° (right) |

Upstream files are under `robocasa/environments/kitchen/` at the pinned commit.
