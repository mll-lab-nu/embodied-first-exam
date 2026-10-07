# behavior-preparing-lunch-box-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-preparing-lunch-box-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `preparing_lunch_box` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (275 s on average); demonstration video (275 s): https://player.vimeo.com/video/1114057330 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-07); human review in PR #71 (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Pack the lunch box on the kitchen countertop. The two apple halves, the club sandwich and the chocolate chip cookie lie on the chopping board on the countertop; the bottle of tea is inside the kitchen refrigerator. Put all five into the packing box and leave the refrigerator closed.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both apple halves (`half__apple.n.01_1`, `half__apple.n.01_2`) are inside the packing box (`packing_box.n.02_1`)
- the club sandwich (`club_sandwich.n.01_1`) is inside the packing box
- the chocolate chip cookie (`chocolate_chip_cookie.n.01_1`) is inside the packing box
- the bottle of tea (`bottle__of__tea.n.01_1`) is inside the packing box
- the refrigerator (`electric_refrigerator.n.01_1`) is closed

## Difficulty
First-pass rating on the task-list site: hard. The 2026 challenge's 200 teleoperated demonstrations took 275 s on average (8,245 control steps at 30 Hz) and drove 21.4 m; the scene loads 7 rooms, and the goal uses `inside`, `open`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (275 s on average; video https://player.vimeo.com/video/1114057330); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle; human review in PR #71 (PROTOCOL §2.7), on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_single_floor`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
