# behavior-getting-organized-for-work-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-getting-organized-for-work-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `getting_organized_for_work` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (522 s on average); demonstration video (522 s): https://player.vimeo.com/video/1114059683 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Organize the bedroom desk for work. The monitor and the mouse stand on the desk, the keyboard lies on a notebook on the desk, the computer stands under the desk, and a folder with a pen on it lies on the swivel chair. Leave the computer under the desk and the monitor on it; put the keyboard on the desk next to the monitor and the mouse on the desk next to the keyboard; put the folder next to the mouse, the notebook on the folder and the pen on the notebook; and put the swivel chair next to the desk.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- the monitor (`monitor.n.04_1`) is on top of the desk (`desk.n.01_1`) and the computer (`computer.n.01_1`) is under the desk
- the keyboard (`keyboard.n.01_1`) is on top of the desk and next to the monitor
- the mouse (`mouse.n.04_1`) is on top of the desk and next to the keyboard
- the folder (`folder.n.02_1`) is next to the mouse, the notebook (`notebook.n.01_1`) is on top of the folder and the pen (`pen.n.01_1`) on top of the notebook
- the swivel chair (`swivel_chair.n.01_1`) is next to the desk

## Difficulty
First-pass rating on the task-list site: hard. The 2026 challenge's 200 teleoperated demonstrations took 522 s on average (15,671 control steps at 30 Hz) and drove 47.34 m; the scene loads 3 rooms, and the goal uses `ontop`, `nextto`, `under`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (522 s on average; video https://player.vimeo.com/video/1114059683); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_upper`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
