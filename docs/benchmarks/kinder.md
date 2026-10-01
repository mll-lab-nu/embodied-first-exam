# KinDER

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), MIT, pinned at `5b2dbac` |
| simulator | MuJoCo 3.3 (Dynamic3D) in KinDER's MimicLabs lab, CPU physics; two tasks in PyBullet (Kinematic3D: no dynamics, a colliding move is refused) |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; delta actions (MuJoCo: 10 Hz) |
| score | pass = KinDER's own goal check within the episode (1000 control steps; PyBullet 3000) |
| tasks | 11 families × 2 modes: `tasks/kinder-<family>-i00-privileged` and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/embodied-agent-interface-v2-internal/eai-kinder:0.1.6` (`images/kinder/`, 4.6 GB with the lab scenes) |
| oracle | `dynamo` (the fixture): full, both modes; the other ten: none, human review (positive examples below) |

## Tasks (one variant each, seed 0)

| family | challenge | the robot must | positive example |
|---|---|---|---|
| tossing | dynamic | get a cube over a wall that spans the room, into a bin | Luna, privileged only |
| balance-beam | tool, dynamic | put three cubes on a seesaw's marked region, level within 5° | Luna, privileged only |
| dynamo | nonprehensile | drive into a floor square that three chairs block (fixture) | oracle, both modes; Luna, both |
| sweep-into-drawer | nonprehensile, tool, dynamic | open a drawer, sweep five cubes into it | none known |
| scoop-pour | nonprehensile, tool, dynamic | move 30 cubes between bins with a scoop | none known |
| shelf | spatial, geometric | two cubes into a cramped cupboard's top compartment | Luna, privileged only |
| constrained-cupboard | geometric | six identical rods, each into the compartment it is owed | Luna, privileged only |
| sweep-simple | nonprehensile, tool | ten cubes into a box marked on the floor, with a wiper | Luna, standard (50 resets): both |
| sort-blocks | spatial | four cubes into the bins of their colours | Luna, both |
| obstruction-3d (PyBullet) | geometric | clear a pad of three blocks, place a block on it | Luna, privileged: both |
| packing-3d (PyBullet) | geometric | pack three flat parts into a tray | Luna, both |

Why these: the first six are the Dynamic3D tasks where physics decides the outcome and a camera can see the goal or a
sentence can name it; the other five are what a screening of every other family (09-29, GPT-6 Luna once per mode) left
unsolved in standard mode. Per-task reasoning: `scripts/kinder/subset.toml`. Positive examples are runs published on the results
site; each scores 1 under today's privileged verifier, and "both" means it also passes when sent through the
standard client. "privileged only": the trajectory moves the base diagonally by up to 0.14 m a step, which standard
mode clips to a 0.1 m disc (the largest move that stays in upstream's per-axis bound after the odometry rotation).

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator, its full state (`get_state`/`set_state`) and the goal check | unlimited | its `trajectory.npz`, replayed twice in a fresh process |
| standard | the robot's own sensors, through `rcb_client.py`; no world coordinates, no goal check | none (optional capability, reported separately) | the recorded episode, replayed in a fresh simulator |

World-frame information (PROTOCOL D7): privileged mode gives KinDER's world state; standard mode gives none -- odometry
starts at the robot's start pose, and the goal is named by what the cameras see.

| standard mode: given (a real TidyBot++ has it) | not given |
|---|---|
| the task sentence: goal and success condition | any object's or goal region's position |
| `robot_base` RGB, `robot_wrist` RGB-D (the Gen3's RealSense D410), 480×640 | world coordinates; a room camera (`RCB_OBS_ROOM_CAMERA=1`, never overhead) is a knob, off |
| base odometry (pose, velocity), arm joint angles and velocities, finger position | the goal check before the episode ends (`success` / `failed` only) |
| `spec()`: action layout and bounds, arm joint axes, positions, limits and torques, the grasp point, camera fields of view and poses, control rate, episode length, budget | masses, friction, the simulator |

In obstruction-3d and packing-3d (PyBullet) the robot is the same, kinematic: no velocities, and a refused move comes
back `blocked` and stops the chunk there.

## Run

```bash
harbor run -c scripts/kinder/configs/codex-openrouter.yaml --env-file .env -p tasks/kinder-tossing-i00-standard
harbor run -p tasks/kinder-dynamo-i00-privileged -a oracle      # or -a nop: scores 0
```
`codex-openrouter.yaml` is Harbor's own Codex agent with OpenRouter as its model provider (run id
`codex-gpt6_luna-medium`); `RCB_RESET_BUDGET=50 harbor run ...` turns on the optional reset capability, whose results are
reported separately. Build the image: `docker build -f images/kinder/Dockerfile -t
ghcr.io/embodied-agent-interface-v2-internal/eai-kinder:$(cat images/kinder/VERSION) .` (from the repository root).

## Results

Agent results are not kept in this repository (PROTOCOL D3): per-run READMEs (verdict, cost, what happened),
`reward.json`, the replay's last frame and videos are published on the results site, keyed by run id. Standard-mode
runs with the optional reset capability (50 resets) are reported separately from the standard configuration (no
reset, PROTOCOL D1), and runs recorded before protocol v1.0 are marked as such.
