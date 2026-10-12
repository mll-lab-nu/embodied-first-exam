# KinDER

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), MIT, pinned at `5b2dbac` |
| simulator | MuJoCo 3.3 (Dynamic3D) in KinDER's MimicLabs lab, CPU physics |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; delta actions (MuJoCo: 10 Hz) |
| score | pass = KinDER's own goal check within the episode (1000 control steps) |
| tasks | 5 families × 2 modes: `tasks/kinder-<family>-i00-privileged` and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/mll-lab-nu/eai-kinder:0.1.6` (`images/kinder/`, 4.6 GB with the lab scenes) |
| oracle | `dynamo` (the fixture): full, both modes; the other four: none, human review (positive examples below) |

## Tasks (one variant each, seed 0)

| family | challenge | the robot must | positive example |
|---|---|---|---|
| dynamo | nonprehensile | drive into a floor square that three chairs block (fixture) | oracle, both modes; Luna, both |
| sweep-into-drawer | nonprehensile, tool, dynamic | open a drawer, sweep five cubes into it | Luna, privileged (2026-10-04); run `codex-gpt6_1_sol-high`, standard (2026-10-03, no reset) |
| scoop-pour | nonprehensile, tool, dynamic | move 30 cubes between bins with a scoop | runs `codex-gpt6_astra-high` and `codex-gpt6_sol-high`, privileged only (2026-10-04); standard: none known |
| constrained-cupboard | geometric | six identical rods, each into the compartment it is owed | Luna, privileged only |
| sweep-simple | nonprehensile, tool | ten cubes into a box marked on the floor, with a wiper | Luna, privileged only (2026-10-04); Luna, standard (50 resets): both |

Why these (no model's results enter the choice):
- **Valid:** KinDER's 3D families whose goal a camera can see or a sentence can name (the 2D ones move an abstract
  planar robot with no real counterpart; LimbRepositioning3D's IKFast module cannot be built in our image).
- **Most task objects (upstream's `oN`):** scoop-pour 30, sweep-simple 10, constrained-cupboard 6, sweep-into-drawer 5;
  every other 3D family has at most 4.
- Per-task reasons: `scripts/kinder/subset.toml`.

Positive examples are runs published on the results
site; each scores 1 under today's privileged verifier, and "both" means it also passes when sent through the
standard client. "privileged only": the trajectory moves the base diagonally by up to 0.14 m a step, which standard
mode clips to a 0.1 m disc (the largest move that stays in upstream's per-axis bound after the odometry rotation).
Scoop-pour's two are the graded trials of the runs named in the table (845 and 770 steps, two replays each, the same
final state; the privileged verifier and the instance have not changed since): their base moves stay inside the disc,
but they are privileged only for another reason, below.

### Open: tasks without a positive example in their own mode (PROTOCOL §2.7, §7 Open 4)

Every family has a positive example (human review, §2.7: per family, at least one), so the predicate and the instance
are known to be solvable. Two standard twins have none of their own yet; until they do, their results are reported
apart from the tasks with a verified solution (§7 Open 4):

- `kinder-scoop-pour-i00-standard`. Astra's privileged rows were sent through the standard client on 2026-10-10
  (board 0067): nothing was clipped, and the rows the simulator executed differ from the trajectory's by at most
  7e-18 (the base moves are turned into the odometry frame by the sender and back by the service, and a chunk's
  `linear` default adds its own last-bit arithmetic), yet the episode did not reach the goal: 30 cubes poured from a
  scoop do not land the same way after a last-bit change. A standard-mode example therefore has to be an episode run
  in standard mode, not a converted privileged one. This explanation is open: the second review of 2026-10-10 (board
  0067, minor 13) sent 400 random rows through the same path and found that the tooling casts actions to float32, that
  none of the 4,400 executed values differed after that cast and that the service's final-state hash equalled the
  privileged replay's, so a difference of 7e-18 cannot be what made that conversion fail; its cause is not known, and a
  converted privileged example may work when the conversion is redone.
- `kinder-constrained-cupboard-i00-standard`. Its privileged example moves the base by up to 0.14 m a step.

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator, its full state (`get_state`/`set_state`) and the goal check | unlimited | its `trajectory.npz`, replayed twice in a fresh process |
| standard | the robot's own sensors, through `rcb_client.py`; no world coordinates, no goal check | 10 (owner, 2026-10-11; PROTOCOL §4.5); `RCB_RESET_BUDGET=0`: none | the last episode, replayed in a fresh simulator |

World-frame information (PROTOCOL D7): privileged mode gives KinDER's world state; standard mode gives none -- odometry
starts at the robot's start pose, and the goal is named by what the cameras see.

| standard mode: given (a real TidyBot++ has it) | not given |
|---|---|
| the task sentence: goal and success condition | any object's or goal region's position |
| `robot_base` RGB, `robot_wrist` RGB-D (the Gen3's RealSense D410), 480×640 | world coordinates; a room camera (`RCB_OBS_ROOM_CAMERA=1`, never overhead) is a knob, off |
| base odometry (pose, velocity), arm joint angles and velocities, finger position | the goal check before the episode ends (`success` / `failed` only) |
| `spec()`: action layout and bounds, arm joint axes, positions, limits and torques, the grasp point, camera fields of view and poses, control rate, episode length, budget | masses, friction, the simulator |

## Run

```bash
harbor run -p tasks/kinder-scoop-pour-i00-standard -a codex -m openai/gpt-6-luna --env-file .env
harbor run -p tasks/kinder-dynamo-i00-privileged -a oracle      # or -a nop: scores 0
```
Agent, provider and effort settings: docs/RUNNING.md. Standard tasks grant 10 resets by default (owner, 2026-10-11:
the 1000 control steps bound each episode, so without a reset the practice and the graded attempt share them; all 4
GPT-6 Astra standard runs of 2026-10-03/04 ended with the steps spent and most of the hour unused);
`RCB_RESET_BUDGET=0 harbor run ...` runs the single-episode configuration, whose results are reported separately. Build the image: `docker build -f images/kinder/Dockerfile -t
ghcr.io/mll-lab-nu/eai-kinder:$(cat images/kinder/VERSION) .` (from the repository root).

## Results

Agent results are not kept in this repository (PROTOCOL D3): per-run READMEs (verdict, cost, what happened),
`reward.json`, the replay's last frame and videos are published on the results site, keyed by run id. Standard-mode
runs with 10 resets (the default from 2026-10-11), with 50 (the optional capability before it) and with none are
reported separately (PROTOCOL D1), and runs recorded before protocol v1.0 are marked as such.
