# MolmoSpaces

## Overview

The benchmark episodes Ai2 uses to evaluate robot policies zero-shot in unseen houses: picking, placing, articulated
objects and navigation, on a fixed-base arm and a mobile manipulator. Eight families, one frozen upstream episode each,
in two modes: 16 task directories, `tasks/molmospaces/molmospaces-<family>-i00-privileged` and `-standard`.

| | |
|---|---|
| upstream | [Ai2 MolmoSpaces](https://github.com/allenai/molmospaces) (Kim et al., 2026), molmo-spaces 0.2.9 (tag `v0.2.9`, `7351388`), packages `molmospaces-bench-v2/20260415` |
| simulator | MuJoCo 3.5.0, CPU physics, EGL rendering on a GPU (OSMesa without one, about 15 times slower) |
| robots | `franka-robotiq-2f85` (Franka FR3 + Robotiq 2F-85 on a fixed base, the DROID setup); `rainbow-rby1` (RB-Y1: holonomic base, 6-joint torso, two 7-joint arms) |
| score | upstream's `judge_success()` on the state at the episode's end |
| image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` (`images/molmospaces/`, about 1.8 GB of assets) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/molmospaces -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | `Session`: full state (`s.state()`, `s.model` / `s.data`), any camera, upstream's kinematics, reward and success code | unlimited | `trajectory.npz`, replayed once in a fresh process |
| standard | `joint_position` rows (Franka 8, RB-Y1 25) and `done`; the robot's cameras, proprioception, `/kinematics` | none | the live episode: upstream's `judge_success()` on the state it ends in |

## Upstream and license

- Upstream: MolmoSpaces, [allenai/molmospaces](https://github.com/allenai/molmospaces), molmo-spaces 0.2.9 from PyPI
  (tag `v0.2.9`, `735138876887eb64650742631b8dda841dd264bf`), installed with every dependency pinned in
  `images/molmospaces/requirements.txt`. Apache License 2.0 (Allen Institute for Artificial Intelligence).
- Assets: the scenes and AI2-THOR objects are CC BY 4.0; Objaverse objects are ODC-BY 1.0 and each its creator's CC
  BY, CC BY-SA or CC0, listed with their attributions in the image's `/opt/molmospaces/ATTRIBUTION.md`. The build fails
  on an asset with non-commercial terms, so none is included. Objaverse version `20251016_from_20250610`, the one the
  benchmark was made with (0.2.9 defaults to `20260131`), pinned with upstream's `MLSPACES_PINNED_ASSETS_FILE`.
- Simulator: MuJoCo 3.5.0 (Apache License 2.0).

## Changes from upstream

- The tooling, `rcb_molmospaces.py` (`embodied_first_exam/benchmarks/molmospaces/`, in every task from the pinned
  files-only image `images/molmospaces-files/`), builds the frozen episode through upstream's evaluation path
  (`JsonEvalRunner` → `JsonEvalTaskSampler` → `task.reset`, action noise off). One control step is one upstream
  `Task.step` with every move group's targets; each step also polls every camera, as upstream's evaluation does.
  Physics, controllers, kinematics and the success checks are upstream's.
- One loader change: upstream's `set_joint_values` raises unless the articulated target has a grasp file. Grasp files
  are not shipped, and the check only tests that the file exists, so it answers "exists" while the episode is built.
- Upstream's scripted experts are replaced by stubs that raise (`images/molmospaces/scrub_experts.py`); no grasp file
  is shipped. Only the assets the instances open are kept. Upstream's generic A* and grasp-generation library code
  stay installed.
- The episode ends at upstream's `is_done()` (the horizon) or when the agent ends it. Success is judged at the end
  (`terminate_upon_success = False`, upstream's evaluation default).
- Control rates: the Franka's from upstream's evaluation config; the RB-Y1's from its data-generation configs (it has
  no evaluation config). Navigation uses the Holodeck package (the ProcTHOR-10k one misses objects on 0.2.9's scene
  version).
- Each instance is the upstream episode with `source` (its expert trajectory's path) removed; navigation's text is
  upstream `NavToObjTask`'s own.

## Interface

Trajectory rows (both modes): the controlled move groups in upstream order, each the target upstream's joint-position
controller receives. Franka (8): 7 arm joints (rad) + the Robotiq command (0 open .. 255 closed). RB-Y1 (25): base x,
y (m) and yaw (rad), torso 6, left arm 7, right arm 7 (rad), left and right gripper (the finger motor's force, -100 ..
100: positive closes).

- **Privileged.** `/opt/tools/rcb_molmospaces.py` (`from rcb_molmospaces import Session`): `Session(instance)` builds
  the frozen episode (10-40 s); `layout`, `hold_row()`, `step(row)`, `done`, `status()`, `state()`, `model` / `data`,
  `render(cam)`, `render_depth(cam)`, `camera_info(cam)`, `proprio()`, `robot_spec()`, `kinematics(...)` (upstream's
  kinematic model), `reset()` (unlimited), `replay(rows)`, `save_trajectory(rows, path)`. A trajectory holds at most
  100,000 rows.
- **Standard.** The `sim` sidecar serves `GET /spec`, `GET /status`, `POST /observe`, `POST /submit`, `POST /finish`
  and `POST /kinematics` through `rcb_client.py` and the `efe-robot` MCP tools (wire protocol `eai-standard/3.0`).
  Actions: `joint_position` rows streamed at the control rate (Franka 15.15 Hz; RB-Y1 5 Hz for navigation, 10 Hz for
  the door), and `done`, which is the same as `/finish`; `ee_pose` is not offered. A hold chunk runs whole control
  steps, and `meta["duration_s"]` is what ran. Cameras: Franka wrist and shoulder (moving) and three randomised static
  ones; RB-Y1 head and two wrist cameras; MuJoCo depth. `/kinematics` is upstream's `MlSpacesKinematics` on the
  robot's model (Franka 7 joints, RB-Y1 23 with the base). Proprioception: 29 columns (Franka), 85 (RB-Y1). One call
  returns at most 1812 images. A request is checked completely before anything moves: a null or wrongly typed field
  is a 400.

World-frame information: standard mode's texts name objects and the goal only, never where they are
(`ci_checks/check-world-frame-texts.sh`). The robot's pose and camera calibration come from the
service; object poses never do.

## Grading

- **Privileged.** `tests/grade.py` replays `/app/output/trajectory.npz` once, open-loop, in a fresh process
  (`rcb_molmospaces.py replay`): the rows in order until the last row or the horizon, then upstream's
  `judge_success()` on the final state. The replay checks that it starts in the instance's t = 0 state; a start that
  does not rebuild, a replay that dies or times out, or any other grader exception is `grader_error` with
  `infra_error`. A file that is not a trajectory of this task (not an npz, pickled or non-numeric `actions`, a wrong
  width, NaN or inf, more than 100,000 rows, an entry that unpacks to more than that many rows can hold, checked before
  it is read) is `bad_trajectory`, the agent's 0. The verdict replay and a second, video-only replay share the
  verifier's 1800 s.
- **Standard.** The service judges the live episode: it ends at `/finish` or `done`, at the horizon
  (`RCB_STEP_LIMIT`), or when the agent's time runs out, and is judged by upstream's `judge_success()` on the state it
  ends in. A simulator error raised by the agent's actions is the agent's 0 (reason `error`). The service checks its
  frozen start against the instance's hash before the agent is served (`instance_mismatch`, `infra_error`).
  `tests/grade.py` transcribes the verdict. One video-only pass renders `replay.mp4` after `final.json` is written; it
  never changes the verdict.

## Tasks

| family | upstream package | robot, control period | kept episode (i00) | horizon |
|---|---|---|---|---|
| pick | `procthor-objaverse/FrankaPickHardBench` | Franka, 66 ms | #806: a pie slice among goblets | 303 steps (20 s) |
| pick-and-place | `procthor-objaverse/FrankaPickandPlaceHardBench` | Franka, 66 ms | #228: a purple bottle into a clear ashtray | 606 (40 s) |
| pick-and-place-next-to | `procthor-objaverse/FrankaPickandPlaceNextToHardBench` | Franka, 66 ms | #479: a black rail mount beside the bread | 455 (30 s) |
| pick-and-place-color | `procthor-objaverse/FrankaPickandPlaceColorHardBench` | Franka, 66 ms | #299: a small dark bird figurine into the red bowl | 606 (40 s) |
| open | `ithor/FrankaOpenHardBench` | Franka, 66 ms | #52: a dishwasher's door (any dishwasher joint counts) | 455 (30 s) |
| close | `ithor/FrankaCloseHardBench` | Franka, 66 ms | #346: an upper cabinet's hinged door | 455 (30 s) |
| navigate-to | `holodeck-objaverse/NavToObjDataGenConfig` | RB-Y1, 200 ms | #237: a table lamp (two in the house; the nearest counts) | 500 (100 s) |
| open-door | `procthor-10k/rby1_benchmarks/door_opening_benchmark` | RB-Y1 (RBY1M), 100 ms | #0: a door to pull | 400 (40 s) |

Each task's README states its exact success check with its thresholds.

Per family, the first episode in the package's order that passes every filter ships as `i00`:
- **Valid:** no public MolmoBot trajectory of the house (`allenai/molmobot-data`, val); upstream builds every listed
  object; not done at t = 0; no asset whose licence forbids commercial use.
- **Named unambiguously:** no identical copy of the target or receptacle, and no other object of a named object's
  WordNet synset within 1 m of it (colour's second receptacle differs by colour, by design); navigation: every
  candidate target has the target's synset.
- **Hard**, measurable and the same for every agent:

| families | rule |
|---|---|
| pick, pick-and-place(-next-to, -color) | at least 5 other objects within 30 cm of the target |
| pick-and-place(-color) | the receptacle at least 0.25 m from the target (the packages' median) |
| pick, pick-and-place(-next-to, -color) | the target small in the robot's fixed cameras at t = 0: at most 1200 / 630 / 1100 / 670 pixels (pick / pick-and-place / -next-to / -color) in the best one, the packages' lower quartiles; it and the receptacle or reference object at least 200 pixels in one |
| open, close | upstream's Hard packages: arm start posture randomised (±0.26 rad per joint, wrist ±90°), base up to ±30° off facing the fixture, 5 randomised cameras; the fixture at least 0.75 m (horizontally) from the robot base |
| open | at most 3 joints count toward upstream's success |
| open, close | the moving part has to travel at least 6 cm (open) / 14 cm (close) to reach upstream's success threshold (the packages' upper quartiles) |
| navigate-to | the nearest target at least 8 m from the base and out of `head_camera`'s view at t = 0 |
| open-door | none beyond the package |
