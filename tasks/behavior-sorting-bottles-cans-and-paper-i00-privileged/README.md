# behavior-sorting-bottles-cans-and-paper-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-sorting-bottles-cans-and-paper-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `sorting_bottles_cans_and_paper` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (342 s on average); demonstration video (312 s): https://www.youtube.com/embed/h8-XZ85UxSU (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-07); human review in PR #75 (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Sort the recycling in the kitchen. Three buckets stand on the kitchen floor; two wine bottles, two cans of soda, a newspaper and a magazine lie around the kitchen, some on the countertop and some on the floor. Sort them into the buckets: both wine bottles into one bucket, both cans into a second one, and the newspaper and the magazine into the third, with nothing of another kind in any of them.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both wine bottles (`wine_bottle.n.01_1`, `_2`) are inside the same bucket (`bucket.n.01_1` to `_3`), together with no can of soda, newspaper or magazine
- both cans of soda (`can__of__soda.n.01_1`, `_2`) are inside the same other bucket, together with no wine bottle, newspaper or magazine
- the newspaper (`newspaper.n.03_1`) and the magazine (`magazine.n.02_1`) are inside the same third bucket, together with no can of soda or wine bottle

## Difficulty
First-pass rating on the task-list site: medium. The 2026 challenge's 200 teleoperated demonstrations took 342 s on average (10,264 control steps at 30 Hz) and drove 26.76 m; the scene loads 4 rooms, and the goal uses `inside`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (342 s on average; video https://www.youtube.com/embed/h8-XZ85UxSU); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle; human review in PR #75 (PROTOCOL §2.7), on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
