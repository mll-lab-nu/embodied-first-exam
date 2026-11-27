# RoboCasa-GR1

## Overview
RoboCasa's [GR1 tabletop tasks](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) with a Fourier GR1 humanoid
(two arms, waist and two dexterous Fourier hands; fixed base): all 24 environments, each on one frozen instance, in
both modes, 48 tasks (`robocasa-gr1-<task>-i00-privileged`, `robocasa-gr1-<task>-i00-standard`). Both modes of an
environment use the same frozen instance and the same success rule, the environment's own `_check_success`.

- **privileged**: the agent has the full simulator (`casa_tool.Session`: the robosuite env, privileged state,
  unlimited resets, self-replay) and hands in one trajectory of controller commands, which the verifier replays
  open-loop.
- **standard**: the simulator runs in a `sim` sidecar the agent cannot open; the agent gets only the client (and the
  same service as MCP tools): the robot's cameras, its own joints and grip-site positions, one episode, no reset, no
  object poses, no success signal.

```bash
harbor run -d embodied-first-exam@all -p tasks/robocasa-gr1 -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| | |
|---|---|
| upstream | robocasa/robocasa-gr1-tabletop-tasks @ `4840e671596f93ca03651524b9f72ffb1aadfeff` (MIT), robosuite @ `51cc01785bab80ffeed20da15e67d7dd4140e76a` (1.5.1) with its whole-body mink IK controller (mink 0.0.5), MuJoCo 3.2.6 |
| metadata | `simulator = "robosuite"`, `robot = "fourier-gr1"`, `family = "robocasa-gr1/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0` (`images/robocasa-gr1/`), CPU only (physics and OSMesa rendering), about 24 GB |
| tooling | `embodied_first_exam/benchmarks/robocasa/` (shared with the RoboCasa benchmark, published as `robocasa-files-0.7.0`): `privileged/environment/casa_tool.py`, `privileged/tests/grade.py`, `sim/server_casa.py`, `sim/finalize.sh`, `standard/tests/grade.py` |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py` from `standard-files-0.7.0` |
| instances | each instance and reference is committed in its tasks (`environment/instance.npz`, `solution/oracle.npz`); the task directories are the deliverable; the tooling that built them is kept outside this repository |

## Upstream and license
- Upstream: RoboCasa's GR1 tabletop tasks,
  [robocasa/robocasa-gr1-tabletop-tasks](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) at
  `4840e671596f93ca03651524b9f72ffb1aadfeff`, a fork of [RoboCasa](https://github.com/robocasa/robocasa). MIT License
  (copyright 2025 the NVIDIA GEAR group). Citation: NVIDIA et al., 2025, "GR00T N1: An Open Foundation Model for
  Generalist Humanoid Robots", arXiv:2503.14734.
- Simulator: [robosuite](https://github.com/ARISE-Initiative/robosuite) at `51cc017` (MIT License), its
  `mink_controller.py` example from the same commit, mink 0.0.5, MuJoCo 3.2.6. Other pins in
  `images/robocasa-gr1/requirements.txt`.
- Assets, downloaded when the image is built (`images/robocasa-gr1/fetch_assets.sh`, every archive checked by SHA-256)
  and not in this repository: RoboCasa's fixture, texture and object archives (CC BY 4.0), and NVIDIA's
  [PhysicalAI-DigitalCousin-Assets](https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets) at
  `1b01883` (`lightwheel` and `sketchfab` object meshes), **CC BY-NC 4.0: non-commercial use only**. The public image
  contains these assets under their own licences.

## Changes from upstream
- **Physics, models and success checks: none.** The environments, the GR1 model, the controller and `_check_success`
  are upstream's at the pinned commits, installed unpatched. robosuite's wheel omits its third-party controller
  examples, so the image adds `mink_controller.py` from the same robosuite commit.
- **Frozen instances.** Each task starts from the initial state of one official demonstration episode of its
  environment, frozen in `instance.npz` (about 0.1 MB): the MuJoCo integration state, the model arrays the scene's
  reset rewrites, the env's Python task state (env, fixtures, robot, controllers, observables) and the NumPy / Python
  RNG states, with a SHA-256 checked on every load. Rebuilding is bit-exact. No instance is solved at its start.
- **Determinism.** CPU physics. `casa_tool` turns MuJoCo's process-wide mesh cache off: a mesh served from the cache
  can differ from a cold compile of the same file, which would break bit-exact replay across processes.
- **Check call pattern.** `casa_tool` runs `_check_success` once at reset and twice after every control step, as the
  references were validated. The GR1 tabletop checks keep no timers or latches, so the result depends on the state
  only.
- **Episode end.** Upstream evaluation stops at the first success or at a step horizon; here a success never ends an
  episode. Privileged deliverables have at most 3000 control steps; standard episodes have no step limit.
- **Task text.** Each instruction's Task line is a plain sentence written for the instance (`casa_tool.TEXT_ERRATA`):
  it names what the check needs (the top tier, both hands moved away, the door closed). The instance keeps upstream's
  own language string.
- **Rendering.** Camera images (RGB and depth, in both modes and in replay videos) draw the visual meshes only, as
  robosuite's own cameras do; the collision geoms (geom group 0) are hidden.

## Interface
- **Actions (both modes).** The robot's native whole-body controller command, one per control step (20 Hz): 24
  channels. First the right then the left grip site's absolute pose target in the robot's base frame (XYZ metres,
  axis-angle radians, limits ±10), solved by the whole-body IK controller (mink); then six unscaled Fourier hand
  commands per hand (`little, ring, middle, index, thumb_flexion, thumb_rotation`, limits ±3). Values are clipped to
  the limits. This is the controller the demonstrations were recorded with. In standard mode the action type is
  `ee_pose`; there is no `joint_position` type, since the GR1's arm, waist and finger joints are driven through that
  controller.
- **Frames.** The instructions give the base frame's world pose, read from the frozen instance: the proprio's
  grip-site positions are in the world frame, the commands in the base frame.
- **Privileged mode.** `casa_tool.Session("/app/instance.npz")`: `s.env`, `s.model`, `s.data`, `s.state()` (every
  body's pose, the labelled objects, the success flag), `s.step()`, `s.check()`, `s.reset()`, `s.replay()`,
  `s.render()`, `s.save_trajectory()`. The deliverable is `/app/output/trajectory.npz`.
- **Standard mode** (`eai-standard/3.0`). Six robot-mounted cameras (`robot0_agentview_center`, `_left`, `_right`,
  `egoview`, `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand`): RGB, depth, intrinsics and their current poses in
  every response, since they move with the robot. Proprioception: joint positions and velocities, both grip sites'
  positions, the last command. A hold chunk keeps applying the last command (before the first, the grip sites' current
  poses and hand commands): the grip sites stay within about a millimetre, while the IK's posture term may still move
  the waist and elbows by a few hundredths of a radian. Not given: object poses, the scene layout, reward or any
  success signal; there is no reset.

## Grading
- **Success.** The environment's own `_check_success` on one state, the state after the last action, and not already
  true at the start. Each task's README states the check of its family exactly, with its thresholds, read from
  upstream at the pinned commit (`tasks/robocasa-gr1/readme.toml` cites the lines). Two kinds:
  - the 6 `PnP*Close` environments (`tabletop_{cabinet,drawer,microwave}_pnp.py`): the object's origin inside the
    fixture's interior box and its door or drawer shut (opening fraction at most 0.005);
  - the 18 `PosttrainPnPNovel*` environments (`tabletop_24dc.py`): the object in the target container (for the tiered
    basket and shelf: on the top tier), not touching the counter, the container upright, both grip sites more than
    0.25 m from the object and from the container, and, in the 9 environments that place one, the other item from the
    source container not in the target.
- **Privileged mode.** `tests/grade.py` in a separate sandbox without network replays `/app/output/trajectory.npz`
  once, open-loop, in a fresh process, from the verifier's own copy of the instance, and grades the final state. A
  missing or invalid file (not a plain `.npz` of at most 8 MB with arrays only and at most 64 members, no `actions`, a
  shape other than (T, 24), a non-finite value, T outside 1 to 3000) scores 0, and so does a replay that fails.
- **Standard mode.** The sim service (`server_casa.py`) grades the live episode; nothing is replayed. The episode ends
  at the agent's `POST /finish` or at the end of its session, and the check runs once on the state after the last
  executed control step; no step limit, no settle window. A simulator error raised by an agent's call ends the episode
  with 0. The start is checked against the frozen instance before the agent is served (`RCB_INSTANCE_SHA`,
  `RCB_START_SHA` in each task's `environment/docker-compose.yaml`); a mismatch is an infrastructure error.
  `tests/grade.py` transcribes the service's `final.json`.

## Tasks
24 environments, each as `robocasa-gr1-<task>-i00-privileged` and `robocasa-gr1-<task>-i00-standard` (instance seed 0).

| task | environment | object | into | extra terms |
|---|---|---|---|---|
| `bottle-to-cabinet-close` | PnPBottleToCabinetClose | bottled water | cabinet | door shut |
| `wine-to-cabinet-close` | PnPWineToCabinetClose | wine | cabinet | door shut |
| `can-to-drawer-close` | PnPCanToDrawerClose | can | drawer | drawer shut |
| `cup-to-drawer-close` | PnPCupToDrawerClose | cup | drawer | drawer shut |
| `milk-to-microwave-close` | PnPMilkToMicrowaveClose | milk | microwave | door shut |
| `potato-to-microwave-close` | PnPPotatoToMicrowaveClose | potato | microwave | door shut |
| `cuttingboard-to-basket` | PosttrainPnPNovelFromCuttingboardToBasketSplitA | croissant (cutting board) | basket | |
| `cuttingboard-to-cardboardbox` | PosttrainPnPNovelFromCuttingboardToCardboardboxSplitA | squash (cutting board) | cardboard box | other item not in it |
| `cuttingboard-to-pan` | PosttrainPnPNovelFromCuttingboardToPanSplitA | bell pepper (cutting board) | pan | |
| `cuttingboard-to-pot` | PosttrainPnPNovelFromCuttingboardToPotSplitA | bell pepper (cutting board) | pot | |
| `cuttingboard-to-tieredbasket` | PosttrainPnPNovelFromCuttingboardToTieredbasketSplitA | sweet potato (cutting board) | tiered basket, top tier | other item not on the top tier |
| `placemat-to-basket` | PosttrainPnPNovelFromPlacematToBasketSplitA | croissant (placemat) | basket | |
| `placemat-to-bowl` | PosttrainPnPNovelFromPlacematToBowlSplitA | can (placemat) | bowl | other item not in it |
| `placemat-to-plate` | PosttrainPnPNovelFromPlacematToPlateSplitA | tomato (placemat) | plate | other item not on it |
| `placemat-to-tieredshelf` | PosttrainPnPNovelFromPlacematToTieredshelfSplitA | tomato (placemat) | tiered shelf, top tier | other item not on the top tier |
| `plate-to-bowl` | PosttrainPnPNovelFromPlateToBowlSplitA | bell pepper (plate) | bowl | other item not in it |
| `plate-to-cardboardbox` | PosttrainPnPNovelFromPlateToCardboardboxSplitA | lemon (plate) | cardboard box | other item not in it |
| `plate-to-pan` | PosttrainPnPNovelFromPlateToPanSplitA | pear (plate) | pan | other item not in it |
| `plate-to-plate` | PosttrainPnPNovelFromPlateToPlateSplitA | sweet potato (plate) | the empty plate | |
| `tray-to-cardboardbox` | PosttrainPnPNovelFromTrayToCardboardboxSplitA | squash (tray) | cardboard box | |
| `tray-to-plate` | PosttrainPnPNovelFromTrayToPlateSplitA | cupcake (tray) | plate | |
| `tray-to-pot` | PosttrainPnPNovelFromTrayToPotSplitA | lemon (tray) | pot | |
| `tray-to-tieredbasket` | PosttrainPnPNovelFromTrayToTieredbasketSplitA | lemon (tray) | tiered basket, top tier | |
| `tray-to-tieredshelf` | PosttrainPnPNovelFromTrayToTieredshelfSplitA | bell pepper (tray) | tiered shelf, top tier | other item not on the top tier |

The 18 `PosttrainPnPNovel*` tasks also require the counter not touched by the object, the container upright and both
hands moved away. Every reference (123 to 393 actions) succeeds on its final state from a fresh-process replay, and the
success still holds after 10 more still control steps.

## Others
- **References and egress.** `solution/` holds the actions of each instance's official demonstration, replayed from
  the frozen start; they are not in the image. The demonstrations are public, so `task.toml` closes agent egress to
  everything but the model APIs and the package registries.
