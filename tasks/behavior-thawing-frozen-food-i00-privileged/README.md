# behavior-thawing-frozen-food-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-thawing-frozen-food-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `thawing_frozen_food` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (274 s on average); demonstration video (348 s): https://www.youtube.com/embed/FF3HiYSHGdc (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Thaw the frozen food. A frozen chicken breast and a frozen slice of bread lie on two plates inside the kitchen refrigerator. Put the chicken breast, on a plate, into the microwave oven, close the microwave and switch it on; put the bread slice, on a plate, on the countertop; close the refrigerator; neither food may still be frozen.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- the chicken breast (`chicken_breast.n.02_1`) is not frozen and lies on top of a plate (`plate.n.04_1` or `_2`) that is itself inside the microwave oven (`microwave.n.02_1`)
- the microwave oven is switched on and closed
- the bread slice (`bread_slice.n.01_1`) is not frozen and lies on top of a plate that is itself on top of the countertop (`countertop.n.01_1`)
- the refrigerator (`electric_refrigerator.n.01_1`) is closed

## Difficulty
First-pass rating on the task-list site: hard. The 2026 challenge's 200 teleoperated demonstrations took 274 s on average (8,230 control steps at 30 Hz) and drove 17.45 m; the scene loads 4 rooms, and the goal uses `frozen`, `inside`, `ontop`, `open`, `toggled_on`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (274 s on average; video https://www.youtube.com/embed/FF3HiYSHGdc); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
