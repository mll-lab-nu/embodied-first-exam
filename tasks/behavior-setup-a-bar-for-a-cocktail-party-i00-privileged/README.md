# behavior-setup-a-bar-for-a-cocktail-party-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-setup-a-bar-for-a-cocktail-party-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `setup_a_bar_for_a_cocktail_party` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (447 s on average); demonstration video (350 s): https://www.youtube.com/embed/3V0ySKyGKRw (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Set up the bar. On the cabinet in the bar stand three cans of soda, a tray with six ice cubes, an ice bucket, a corkscrew, a wine bottle and two wine glasses. Put the wine bottle on the bar countertop; put the three cans on that countertop, each next to another can; put all six ice cubes inside the bucket and the bucket on the countertop; put both wine glasses on the countertop next to each other, at least one of them next to the wine bottle; and put the corkscrew on the countertop next to the wine bottle.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- the wine bottle (`wine_bottle.n.01_1`) is on top of the bar countertop (`countertop.n.01_1`)
- each of the three cans of soda (`can__of__soda.n.01_1`, `can__of__soda.n.01_2`, `can__of__soda.n.01_3`) is on top of the countertop and next to another one of the cans
- all six ice cubes (`ice_cube.n.01_1`, `ice_cube.n.01_2`, `ice_cube.n.01_3`, `ice_cube.n.01_4`, `ice_cube.n.01_5`, `ice_cube.n.01_6`) are inside the bucket (`bucket.n.01_1`)
- the bucket is on top of the countertop
- both wine glasses (`wineglass.n.01_1`, `wineglass.n.01_2`) are on top of the countertop and next to each other
- at least one of the wine glasses is next to the wine bottle
- the corkscrew (`corkscrew.n.01_1`) is on top of the countertop and next to the wine bottle

## Difficulty
First-pass rating on the task-list site: hard. The 2026 challenge's 200 teleoperated demonstrations took 447 s on average (13,419 control steps at 30 Hz) and drove 22.81 m; the scene loads 4 rooms, and the goal uses `inside`, `nextto`, `ontop`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (447 s on average; video https://www.youtube.com/embed/3V0ySKyGKRw); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `restaurant_diner`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
| Verifier time | each replay min(4 h, max(3600 s, 1200 s + steps / 2)); `[verifier] timeout_sec` 30600 s (two capped replays + 30 min) |

### Change Log
- 2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays min(4 h, max(3600 s, 1200 s + steps / 2)) instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s, so long trajectories hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its name; a trial graded before this date with `grader_error` = 1 can be regraded.
