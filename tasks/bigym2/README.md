# BiGym 2.0

## Overview

Household loco-manipulation on a walking humanoid: a Unitree G1 with two parallel grippers, kept balanced and walking
by NVIDIA's GR00T-WBC lower-body policy inside every step. The agent commands what a real G1 running that controller
takes: walking velocity, pelvis height, torso lean, arm joints, grippers. 13 families in three modes: 39 task
directories, `tasks/bigym2/bigym2-<family>-i00-privileged`, `-standard` and `-realtime`.

| | |
|---|---|
| upstream | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Zhang et al., 2026, [arXiv 2610.07594](https://arxiv.org/abs/2610.07594)), `bigym` 1.0.0 at `93ad4b3` (first published as `6a6632b`; upstream rewrote its history, the package is unchanged and the image checks its git tree); a fork of [BiGym](https://github.com/NeuracoreAI/bigym) (Chernyadev et al., 2024) |
| simulator | MuJoCo 3.8.1 (pinned `<3.9`, Newton solver), CPU physics; GR00T-WBC's two ONNX policies on onnxruntime (CPU); EGL rendering; Python 3.12 |
| robot | Unitree G1 29-DoF with Dex1-1 two-finger grippers (no palm); legs and waist belong to the controller |
| action (50 Hz) | `vx`, `vy` (±1 m/s), pelvis `height` (0.4–1.0 m), `wz` (±1 rad/s), torso `pitch` (−0.2–0.8 rad; 11 of the 13 tasks), 14 arm joint targets (rad), 2 grippers (0 open – 1 closed): 20 or 21 floats |
| sensors | three RGB cameras on the robot (`head`, `left_wrist`, `right_wrist`, 60° fovy; upstream renders 84×84); arm and finger (+ waist) joints, gripper states, pelvis x, y, z, yaw from the base controller |
| score | upstream's success predicate held for 1 s (50 control steps) **and** no fall during the episode (pelvis tilt past ~53° or height below 0.30 m); fail-fast: an object on the floor (plates, blocks), a gripper on the sandwich |
| horizon | per task, 700–8750 control steps (14–175 s): twice the longest of 60 human demonstrations |
| image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` (`images/bigym2/`, 1.5 GB; dependencies at upstream's `uv.lock`, plus imageio-ffmpeg for the service's mp4 videos) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/bigym2 -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | graded |
|---|---|---|
| privileged | the `bigym` package (`Session`: step, reset, replay, MuJoCo model and data, onboard images) | `/app/output/trajectory.npz`, replayed in one fresh process |
| standard | the robot's three onboard cameras (84×84 as upstream renders them), upstream's proprioception, `whole_body` chunks; one episode, no reset | the live episode, as it ran (nothing replayed) |
| realtime | the same on a clock that does not stop | as standard |

## Upstream and license

- Upstream: BiGym 2.0, [swirl-uk/BiGym2](https://github.com/swirl-uk/BiGym2) at `93ad4b3`, Apache License 2.0.
- Robot model: the Unitree G1 description (BSD 3-Clause) in AMO's MuJoCo packaging (Apache License 2.0).
- Scene props: CC0 or CC BY 4.0 (upstream's `bigym/envs/xmls/3D_MODELS_ATTRIBUTION.md`).
- GR00T-WBC weights: NVIDIA's, redistributed under the NVIDIA Open Model License (upstream's `NOTICE`,
  `THIRD_PARTY_NOTICES.md`). No non-commercial terms apply: the image can be published.

## Changes from upstream

- The instance is upstream's official `make(task)` reset with seed 0 (its deterministic reset and 200-step controller
  warm-up). One control step is one upstream env step of a physical action row (upstream's `EnvTools` contract);
  success is upstream's `is_success`. Physics, controller and predicates are upstream's.
- A load accepts the instance when the state matches bit for bit, or when the scene matches and every joint is within
  5e-4 (upstream's golden-test tolerance for CPU kernel differences in the controller).
- Standard and realtime episodes are agent-ended: upstream's end on the held success alone is passed over
  (`Episode.run_on`), and the episode is judged on its end state after upstream's 1 s hold window, run from that state
  with the robot standing still (`end_window_steps = success_hold_steps`). A task failure, a physics error, the pelvis
  10 m from the scene's origin and the horizon still end the episode as upstream ends it.
- Upstream behaviour kept as it is: `sandwich_remove`'s check does not ask that the spatula was used or that the
  sandwich left the pan; the reach tasks light a sphere up when a gripper is inside it, in every camera; `put_cups`'s
  check asks only that each cup touch the wall cabinet's bottom shelf and not be held; `flip_cutlery`'s check asks
  neither that the spoon end inside the mug nor that the mug stay upright.
- Upstream's reward shaping for the plate tasks (`event_progress`) is off by default and never graded.

## Interface

One module, `rcb_bigym2.py`, in every task's `environment/` and `tests/`. "Held" in every text is upstream's
`is_gripper_holding_object`: a finger touching the object. On the G1, upstream's `pinch_position` is the wrist link's
origin, 0.148 m behind the finger pads; the point between the pads is the `*_end_effector` site (`wrist_position`, what
`tools.ik` and the reach check use).

- **Privileged.** `Session(instance)`: `layout`, `hold_row()`, `step(row)`, `done`, `status()`, `task` (BiGym's task
  env and its props), `env`, `tools` (upstream's `EnvTools`, `tools.ik`), `model` / `data`, `image(cam, h, w)`,
  `proprio()`, `held(obj)`, `reset()` (unlimited), `replay(rows)`, `save_trajectory(rows, path)`. The success check
  stays visible: it is sparse, and every instruction states its rule.
- **Standard.** The `sim` sidecar serves `whole_body` chunks, the three onboard cameras and upstream's low-dimensional
  observation through `rcb_client.py` and the `efe-robot` MCP tools (wire protocol `eai-standard/3.0`). `spec()` adds
  the robot's description: joint axes and positions, the point between each gripper's pads, camera mounts. Never an
  object's pose, the success check or its parts. Every instruction states, besides upstream's task sentence and
  success rule, where the named objects are at the start (one sentence measured on the frozen scene), the action
  table, and upstream's notes on the whole-body controller (`bigym/loco/agent/templates/api_strict.md`).
- **Realtime.** The standard interface on a clock that does not stop (the shared realtime layer): between commands
  the plan's last row is held, walking velocity included; requests cannot slow the clock.

## Grading

- **Privileged.** `tests/grade.py` replays `trajectory.npz` once in a fresh process (`rcb_bigym2.py replay`): one
  upstream step per row until upstream ends the episode or the rows run out, then upstream's `is_success`. A file
  over 64 MB, not an npz, for another task, of the wrong width, with NaN or inf, or longer than the horizon is the
  agent's 0. A replay that fails or times out, or an instance that does not rebuild, is `grader_error`.
- **Standard and realtime.** The sidecar judges the live episode; `rcb_service.py` writes the verdict
  (`graded_by = "live"`, `replays = 0`). The episode ends at `/finish`, a task failure, a physics error, the pelvis
  10 m away, the horizon (`step_limit`) or the end of the session; an end-state end is judged after the 1 s hold window.
  The frozen start is checked when the scene is built (`instance_mismatch`, infrastructure). Reset budget: 0 in both
  service modes (one episode); `RCB_RESET_BUDGET=N` runs a configuration with N resets, reported separately.
- In realtime, once the agent's first command has run, a simulator error or crash inside a control step is the
  agent's 0; a crash outside a step, anything before the first command, a kill and a failed resume are
  infrastructure.
- The video is one render pass over `trajectory.npz` after the verdict and never changes it.

## Tasks

| group | task | the robot must | horizon | ours | note |
|---|---|---|---|---|---|
| reaching | reach_target_single | touch a ball with the left gripper | 18 s | ⬜ | reach_target_dual's predicate, one hand |
| | reach_target_multi_modal | touch a ball with either gripper | 14 s | ⬜ | the same |
| | reach_target_dual | touch two balls at once, one per gripper | 14 s | ✅ | |
| table-top | move_plate | move a plate between two draining racks | 34 s | ⬜ | move_two_plates' predicate, one plate |
| | move_two_plates | move two plates at once: in a slot, upright within 20°, released | 46 s | ✅ | |
| | flip_cup | turn an upside-down cup upright (within 5°) | 37 s | ✅ | |
| | flip_cutlery | take a spoon out of a mug, flip it, put it back | 39 s | ✅ | |
| | stack_blocks | carry three blocks to the far table and stack them | 175 s | ✅ | walks across |
| dishwasher | dishwasher_close | push both trays in and close the door | 93 s | ✅ | three joints |
| | dishwasher_load_cups | two cups into the upper tray | 40 s | ⬜ | load_plates' scene and predicate, no orientation clause |
| | dishwasher_load_cutlery | a knife and a fork from a mug into the basket | 53 s | ⬜ | the same |
| | dishwasher_load_plates | two plates from a drainer into the lower tray, upright | 63 s | ✅ | |
| kitchen counter | drawer_top_open | open the top drawer | 27 s | ✅ | |
| | drawer_top_close | close the top drawer | 17 s | ⬜ | the closing counterpart of drawer_top_open |
| | wall_cupboard_open | open both doors of the wall cabinet | 29 s | ✅ | |
| | wall_cupboard_close | close both doors | 34 s | ⬜ | the closing counterpart of wall_cupboard_open |
| | pick_box | carry a 3 kg box from a low side table to the counter | 88 s | ✅ | |
| | put_cups | two cups into the closed wall cabinet | 60 s | ✅ | |
| | saucepan_to_hob | the saucepan from the closed cabinet onto the hob | 93 s | ✅ | |
| | sandwich_remove | move the sandwich from the pan onto the board with a spatula | 63 s | ✅ | a gripper on the sandwich fails |

Each task's README states its exact success predicate with its thresholds.

Selection rule:
- **Valid (20 of 20):** holding the start pose for the whole horizon scores 0 and does not fall; replay is
  deterministic; every goal is an object state a sentence names.
- **One per success predicate (13):** a task whose predicate is another's on fewer objects or one hand goes; of an
  open/close pair the opening task stays; of the three dishwasher loads (one scene, one "in the rack, released"
  predicate) the plates stay, the only one with an orientation clause.
- **Instance:** seed 0. No published demonstration uses it (their seeds are 1–199), and it is outside upstream's
  reserved evaluation range 620000–629999, whose rollouts upstream publishes.

## Others

Where upstream holds answers, and how each is kept from the agent:

| where | what | handling |
|---|---|---|
| `bigym/envs/*.py` (`_success`, `_fail`), `bigym/loco/eval/` | predicates, tolerances, fall check | privileged: kept; standard: sidecar only |
| HF `SWIRL-Lab/bigym-g1-native60` (public) | 60 successful demonstrations per task with full simulator state | seed 0 is none of them; the dataset is not in the image; the agent reaches the model APIs and the package registries only |
| HF `SWIRL-Lab/bigym2-agent-rollouts` (public) + the project page | coding-agent programs (`policy.py`) and their rollouts on seeds 620000–620099 for 9 tasks (5 of ours: reach_target_dual, move_two_plates, dishwasher_close, drawer_top_open, pick_box) | only the egress rule keeps them out |
| `tests/fixtures/demo_endpoints.npz` | the final state of one demonstration per task | not shipped: the wheel installs `bigym/` only |

There is no scripted expert or planner upstream; IK exists only as teleoperation and agent tooling (`bigym/vr/ik/`,
`tools.ik` in `bigym/loco/agent/`). Build the image from the repository root:
`docker build -f images/bigym2/Dockerfile -t ghcr.io/mll-lab-nu/efe:bigym2-$(cat images/bigym2/VERSION) .`
