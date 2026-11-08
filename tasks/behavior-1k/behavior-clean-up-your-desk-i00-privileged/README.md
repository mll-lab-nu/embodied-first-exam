# behavior-clean-up-your-desk-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-clean-up-your-desk-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `clean_up_your_desk` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (714 s on average); demonstration video (714 s): https://player.vimeo.com/video/1114059839 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §4). |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` |

## Task
Clean up the desk in the child's room. A folder, a pencil, two pens, two paperback books and a pencil box lie on the desk; the other folder lies on the chair, the stapler is inside the bookcase, and the open laptop lies on the bed. Put both folders and both paperback books into the bookcase and the pencil and both pens into the pencil box, which stays on the desk; take the stapler out of the bookcase and put it on the desk; and put the laptop on the desk, closed.

**Success**, all at the same time, held for 1 s with no goal object in a gripper and every goal object at rest:
- both folders (`folder.n.02_1`, `_2`) and both paperback books (`paperback_book.n.01_1`, `_2`) are inside the bookcase (`bookcase.n.01_1`)
- the pencil (`pencil.n.01_1`) and both pens (`pen.n.01_1`, `_2`) are inside the pencil box (`pencil_box.n.01_1`)
- the pencil box, the stapler (`stapler.n.01_1`) and the laptop (`laptop.n.01_1`) are on top of the desk (`desk.n.01_1`)
- the laptop is closed

## Difficulty
First-pass rating on the task-list site: hard. The 2026 challenge's 200 teleoperated demonstrations took 714 s on average (21,418 control steps at 30 Hz) and drove 60.51 m; the scene loads 7 rooms, and the goal uses `inside`, `ontop`, `open`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (714 s on average; video https://player.vimeo.com/video/1114059839); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json`, up to 3 times (`[metadata] replays`), each in
a fresh process, stopping at the first success; pass iff the BDDL goal holds after a replay and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process starts from the loaded state (no reset;
an in-process reset is only approximate, hence a fresh process); fresh replays are not always bit-identical, hence up to 3. A file the
grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen
instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §4) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; the task is marked unvalidated (PROTOCOL §2 `validated`).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 8192 | 22 GiB | 32 GiB |
| verifier | no cap | no cap | no cap | 22 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_single_floor`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` = `stanfordvl/behavior:3.9.2` + ffmpeg (`images/behavior/`): the task builds it from public sources, or reuses our prebuilt copy when you can pull it |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | the agent's time (the `Agent time budget` row; the number is this task's `[agent] timeout_sec`): every Python process pays ~3 min of Isaac Sim + scene load out of it; ~7-11 control steps/s (tasks/behavior-1k/README.md) |
| Verifier time | at most 40,000 rows accepted; each graded replay min(28000 s, max(3600 s, 1200 s + steps / 1.5)), and the video replay after the verdict the same; `[verifier] timeout_sec` 113800 s (four capped replays + 30 min) |
