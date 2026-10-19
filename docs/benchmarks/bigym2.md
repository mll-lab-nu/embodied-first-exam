# BiGym 2.0

Household loco-manipulation on a walking humanoid: a Unitree G1 with two parallel grippers, kept balanced and walking
by NVIDIA's GR00T-WBC lower-body policy inside every step. The agent commands what a real G1 running that controller
takes: walking velocity, pelvis height, torso lean, arm joints, grippers. No benchmark in the set has this: HumanoidBench
controls an H1 joint by joint, RoboCasa-GR1's GR1 has a fixed base, and the kitchen tasks of RoboCasa and BEHAVIOR-1K
run on wheeled bases.

| | |
|---|---|
| upstream | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Imperial College London, S. James; [arXiv 2610.07594](https://arxiv.org/abs/2610.07594)), `bigym` 1.0.0 at `93ad4b3` (first published as `6a6632b`; upstream rewrote its history, the package is unchanged and the image checks its git tree); a fork of [BiGym](https://github.com/NeuracoreAI/bigym) (CoRL 2024) |
| licences | code Apache-2.0; G1 model BSD-3; props CC0 / CC BY 4.0; GR00T-WBC weights NVIDIA Open Model License (redistributable): the image can be published |
| simulator | MuJoCo 3.8.1 (pinned `<3.9`, Newton solver), CPU physics; GR00T-WBC's two ONNX policies on onnxruntime (CPU); EGL rendering; Python 3.12 |
| robot | Unitree G1 29-DoF with Dex1-1 two-finger grippers (no palm); legs and waist belong to the controller |
| action (50 Hz) | `vx`, `vy` (±1 m/s), pelvis `height` (0.4–1.0 m), `wz` (±1 rad/s), torso `pitch` (−0.2–0.8 rad; 11 of the 13 tasks), 14 arm joint targets (rad), 2 grippers (0 open – 1 closed): 20 or 21 floats |
| sensors | three RGB cameras on the robot (`head`, `left_wrist`, `right_wrist`, 60° fovy; upstream renders 84×84); arm and finger (+ waist) joints, gripper states, pelvis x, y, z, yaw from the base controller |
| score | upstream's predicate held for 1 s (50 steps) **and** no fall during the episode (pelvis tilt > ~53° or height < 0.30 m); fail-fast: an object on the floor (plates, blocks, dishwasher loads), a gripper on the sandwich |
| horizon | per task, 700–8750 control steps (14–175 s): twice the longest of 60 human demonstrations |
| tasks | 13 families × 3 modes: `tasks/bigym2/bigym2-<family>-i00-privileged`, `-standard` (`eai-standard/2.1`) and `-standard-realtime` (`eai-standard/2.3`) |
| image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` (`images/bigym2/`, 1.5 GB; dependencies at upstream's `uv.lock`, plus imageio-ffmpeg for the service's mp4 videos) |
| oracle | none: upstream has no expert or planner; human review |

Upstream ships its own coding-agent protocol (`bigym-agent`: one `policy.py` written from a task sentence and a
demonstration video, scored on 100 hidden seeds at 84×84). Here the rcb protocol applies: one frozen instance per task,
no demonstration.

## Tasks: upstream's 20, ours ✅ (13)

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
| kitchen counter | drawer_top_open | open the top drawer | 27 s | ✅ | grasp and pull |
| | drawer_top_close | close the top drawer | 17 s | ⬜ | the closing twin: a push does it |
| | wall_cupboard_open | open both doors of the wall cabinet | 29 s | ✅ | |
| | wall_cupboard_close | close both doors | 34 s | ⬜ | the closing twin |
| | pick_box | carry a 3 kg box from a low side table to the counter | 88 s | ✅ | squat; the box is squeezed between the grippers |
| | put_cups | two cups into the closed wall cabinet | 60 s | ✅ | opens the glass door first |
| | saucepan_to_hob | the saucepan from the closed cabinet onto the hob | 93 s | ✅ | opens the door, squats |
| | sandwich_remove | move the sandwich from the pan onto the board with a spatula | 63 s | ✅ | tool; a gripper on the sandwich fails |

Why these (no model's results enter the choice):
- **Valid (20 of 20):** holding the start pose for the whole horizon scores 0 and does not fall; replay is
  deterministic (below); every goal is an object state a sentence names. At t = 0 the head camera looks down at the
  hands: the balls, racks and blocks are in view, the cups, the box and the wall cabinet only after the robot leans,
  turns or points a wrist camera (upstream has no outside camera).
- **One per success predicate (13):** a task whose predicate is another's on fewer objects or one hand goes; of an
  open/close pair the opening twin stays (a grasp and a pull; the closing twin yields to a push); of the three dishwasher
  loads (one scene, one "in the rack, released" predicate) the plates stay, the only one with an orientation clause.
- **Instance:** seed 0. No published demonstration uses it (their seeds are 1–199), and it is outside upstream's
  reserved evaluation range 620000–629999, whose rollouts upstream publishes.

## Modes
One module, `rcb_bigym2.py`, in every task's `environment/` and `tests/`: the instance is upstream's official
`make(task)` reset with seed 0 (its deterministic reset and 200-step controller warm-up), one control step is one
upstream env step of a physical action row (upstream's `EnvTools` contract), success is upstream's `is_success`. A
load accepts the instance when the state matches bit for bit, or when the scene matches and every joint is within
5e-4 (upstream's golden-test tolerance for CPU kernel differences in the controller): replays on one host stay
bit-exact among themselves either way. "Held" in every text is upstream's `is_gripper_holding_object`: a finger
touching the object. On the G1, upstream's `pinch_position` is the wrist link's origin, 0.148 m behind the
finger pads; the point between the pads is the `*_end_effector` site (`wrist_position`, what `tools.ik` and the reach
check use), as the privileged instruction says.

| mode | the agent gets | graded |
|---|---|---|
| privileged | the `bigym` package (`Session`: step, reset, replay, MuJoCo model and data, onboard images) | `/app/output/trajectory.npz`, replayed in two fresh processes |
| standard | the robot's three onboard cameras (84×84 as upstream renders them; `RCB_IMAGE_HW` for others, reported apart), upstream's proprioception, `whole_body` chunks; one episode, no reset | the live episode, as it ran (`rcb_service.py`, as HumanoidBench and KinDER; nothing replayed) |
| standard-realtime | the same on a clock that does not stop; between commands the robot stands still on the last one | as standard (`rcb_realtime.py`, as HumanoidBench) |

Every instruction states, besides upstream's task sentence and success rule: where the named objects are at the start
(one sentence measured on the frozen scene: distance, direction, height; upstream gives its own agents a demonstration
video instead, which a task here cannot ship), the action table, and upstream's own notes on the whole-body controller
(`bigym/loco/agent/templates/api_strict.md`). Standard `spec()` adds the robot's description: joint axes and positions,
the point between each gripper's pads, camera mounts. Reset budget: 0 in both service modes (the benchmark's choice, PROTOCOL §2): one episode, whose horizon the practice
and the graded attempt share. (The robot itself does not fall: 15 adversarial command patterns of 12 s each, no fall.)
`RCB_RESET_BUDGET=N` runs a configuration with N resets, reported separately.

Grading in both service modes: the live episode. The sim sidecar judges the episode it runs with upstream's
`is_success` at every control step (`step()` in each standard task's `environment/sim/server.py`) and the episode ends where
upstream ends it; `rcb_service.py` writes that verdict (`graded_by = "live"`, `replays = 0`) once the agent's container
is stopped. The 1 s hold is upstream's, inside the episode; nothing is added after it. The frozen start is checked on
the live simulator when the scene is built (`instance_check`: the instance's `t0` state bit for bit, or within
upstream's tolerance); a scene that does not rebuild it is `instance_mismatch`, and `start_sha` (that accepted start)
is checked when an episode begins; both give up as infrastructure (`infra_error = 1`) before the agent is served, and
the service gives up the same way at once if a reset does not return to `start_sha` (untested: BiGym 2.0 grants no
reset by default; upstream's reset with the seed and its warm-up is deterministic on one host, which
`RCB_RESET_BUDGET=N` runs rely on). The video is one render pass over `trajectory.npz` after the verdict
(`render_video`: `rcb_bigym2.replay` with the recorder; CPU physics and controller, EGL rendering; about a minute a
trial at the median); it never changes the verdict. `final.json` is `finalized` the moment the verdict is written,
before the video is rendered (`video_pending` while it renders); the collect hook waits for the verdict and then, as
long as its timeout allows, for the video, so a slow, hung or killed render costs the video and never the verdict.
`reward.json` carries `graded_by_live`, `replays` and `sim_error`.

`infra_error = 1` only for no or an unfinalized `final.json`, a give-up after crashes not all inside the agent's calls,
a reset whose scene does not rebuild and `instance_mismatch`; simulator errors raised by the agent's calls, crashes
inside its calls, timeouts and failures are the agent's 0. In standard-realtime: once the agent's first command has
run, a simulator error raised by a control step is the agent's 0 (`sim_error = 1`, no `infra_error`), and so is a
simulator crash inside a control step (a death whose fatal-signal record in `crash.log` -- SIGSEGV, SIGBUS, SIGFPE,
SIGILL, SIGABRT -- shows the crashing thread in the step; past `RCB_MAX_RESUMES` such crashes the trial ends
`sim_crashed_on_call`); a crash outside a step (building the scene, resuming, resetting, rendering, finalizing),
anything before the first command, a failed reset rebuild, a kill (SIGKILL, SIGTERM, the OOM killer) and a failed
resume are infrastructure. Standard mode keeps its rule: a crash is the agent's only inside its call (`fatal_signal` is
logged as evidence). A simulator that fails inside `POST /reset` ends the episode `error` (`infra_error = 1`: the
agent's reset was legitimate), not `reset`. A negative `Content-Length` is refused unread (400).

Standard-realtime (the shared 2.3 layer): a gap before `at` is the plan's last row, walking velocity included; the
agent's requests cannot slow the clock -- bodies are read, decoded and checked off the simulator's thread, waiting
requests are served once the clock has caught up, the cameras are rendered once per control step
(`docs/protocol/standard_mode.md`, "What a request can cost the clock") -- and `final.json` / `reward.json` carry the clock's
record: `clock_s`, `max_lag_s`, `stalls`, `stalled_s`, `stalled_share`, `held_steps`, `late_steps`, `requests_refused`,
`request_busy_s`. They are evidence and decide no verdict.

The success check stays visible in privileged mode: it is sparse, and every instruction
states its thresholds. Upstream's reward shaping for the plate tasks (`event_progress`) is off by default and never
graded.

## Where upstream holds answers
| where | what | handling |
|---|---|---|
| `bigym/envs/*.py` (`_success`, `_fail`), `bigym/loco/eval/` | predicates, tolerances, fall check | privileged: kept; standard: sidecar only |
| HF `SWIRL-Lab/bigym-g1-native60` (public) | 60 successful demonstrations per task with full simulator state | seed 0 is none of them; the dataset is not in the image; the agent reaches the model APIs and the package registries only |
| HF `SWIRL-Lab/bigym2-agent-rollouts` (public) + the project page | two coding agents' programs (`policy.py`, on the page) and their 5,400 rollouts on seeds 620000–620099, for 9 tasks (5 of ours: reach_target_dual, move_two_plates, dishwasher_close, drawer_top_open, pick_box) | a program that generalises over seeds solves seed 0 too: only the egress rule keeps it out |
| `tests/fixtures/demo_endpoints.npz` | the final state of one demonstration per task | not shipped: the wheel installs `bigym/` only |
| `dishwasher_close`, `wall_cupboard_open` | no reset randomisation: every demonstration starts from this scene | covered by the dataset row |

There is no scripted expert or planner upstream; IK exists only as teleoperation and agent tooling (`bigym/vr/ik/`,
`tools.ik` in `bigym/loco/agent/`).

## Upstream behaviour kept as it is
- `sandwich_remove`'s check does not ask that the spatula was used or that the sandwich left the pan: a sandwich lying
  flat on the board passes (a finger on the sandwich fails the episode).
- The reach tasks light a sphere up when the success check finds a gripper inside it, in every camera.
- `put_cups`'s check asks only that each cup touch the wall cabinet's bottom shelf and not be held: contact from below
  the shelf, outside the closed cabinet, would count.
- `flip_cutlery`'s check asks neither that the spoon end inside the mug nor that the mug stay upright.
These notes stay in this page: no task file the agent sees mentions them.

## Build and run
```bash
docker build -f images/bigym2/Dockerfile -t ghcr.io/mll-lab-nu/efe:bigym2-$(cat images/bigym2/VERSION) .
harbor run -p tasks/bigym2/bigym2-flip-cup-i00-standard -a codex -m openai/gpt-6-luna --env-file .env   # agent settings: docs/protocol/running.md
```
The frozen instances live in the task dirs only (`tasks/bigym2/bigym2-<family>-i00-privileged/environment/instance.json`).
The task directories are the deliverable; the tooling that built them is kept outside this repository.

## Measured (RTX 4090, host load ~25 on 32 cores)
- Every task builds in ~1 s; a reset (with the controller's 200-step warm-up) takes under 1 s; 5–12 ms per control step
  with three 84×84 cameras (1.7–4× real time). Install: a 0.7 GB environment; the GPU only renders.
- Holding the start pose for the whole horizon: 0 of 20 succeed, none falls (seed 620000; the ✅ tasks also at seed 0).
- 300 steps of a fixed arm-and-walk motion in two fresh processes: identical MuJoCo state (`qpos`, `qvel`, `act`,
  `ctrl`) on 20 of 20 (the ✅ tasks also at seed 0); a reset in the same process and a fresh env in the same process
  land on the same state as well (the tooling's hash adds the controller's state and the props' poses).
- The image rebuilds every instance's t = 0 hash offline; no layer of it holds a file of the upstream repository
  outside the package. `nop` scores 0 in all three modes.
- Other CPUs (on the 7950X): every instance rebuilds bit for bit with OpenBLAS forced to its Prescott,
  Haswell or Sapphire Rapids kernels, with numpy's AVX-512 loops off, and on 2 cores. onnxruntime picks its kernels by
  CPU and has no switch: rounding-level noise (±2e-7 relative) on the controller's outputs moves the t = 0 joints by at
  most 2.2e-7, far inside 5e-4. Not yet checked on an Intel or AVX2-only host.
