# behavior-make-gift-bags-for-baby-showers-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-make-gift-bags-for-baby-showers-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `make_gift_bags_for_baby_showers` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (322 s on average); demonstration video (242 s): https://www.youtube.com/embed/EY42jyNoEh8 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-07); human review in PR #71 (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Make two gift bags in the living room. The two sacks lie on the breakfast table, the two toy dice stand on the cabinet, and the two wafers are inside that cabinet. Move both sacks onto the coffee table and put one toy die and one wafer into each sack.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both sacks (`sack.n.01_1`, `sack.n.01_2`) are on top of the coffee table (`coffee_table.n.01_1`)
- each sack holds a different one of the two toy dice (`toy_dice.n.01_1`, `toy_dice.n.01_2`), one die inside each sack
- each sack holds a different one of the two wafers (`wafer.n.02_1`, `wafer.n.02_2`), one wafer inside each sack

## Difficulty
First-pass rating on the task-list site: medium. The 2026 challenge's 200 teleoperated demonstrations took 322 s on average (9,651 control steps at 30 Hz) and drove 16.79 m; the scene loads 4 rooms, and the goal uses `inside`, `ontop`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (322 s on average; video https://www.youtube.com/embed/EY42jyNoEh8); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle; human review in PR #71 (PROTOCOL §2.7), on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `Rs_int`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
