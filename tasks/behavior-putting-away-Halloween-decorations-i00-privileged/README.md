# behavior-putting-away-Halloween-decorations-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-putting-away-Halloween-decorations-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `putting_away_Halloween_decorations` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (460 s on average); demonstration video (460 s): https://player.vimeo.com/video/1114054409 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Put the Halloween decorations away. Two pumpkins, three candles and a cauldron stand on the living-room floor. Put the pumpkins and the candles inside the living-room cabinets (any of them), close every living-room cabinet, and leave the cauldron next to a living-room table.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both pumpkins (`pumpkin.n.02_1`, `_2`) and all three candles (`candle.n.01_1` to `_3`) are inside living-room cabinets (`cabinet.n.01_*`: any of them)
- the cauldron (`caldron.n.01_1`) is next to a living-room table (`table.n.02_*`: any of them)
- every living-room cabinet is closed

## Difficulty
First-pass rating on the task-list site: medium. The 2026 challenge's 200 teleoperated demonstrations took 460 s on average (13,788 control steps at 30 Hz) and drove 47.14 m; the scene loads 4 rooms, and the goal uses `inside`, `nextto`, `open`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (460 s on average; video https://player.vimeo.com/video/1114054409); `task.toml` `oracle_evidence`.

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
