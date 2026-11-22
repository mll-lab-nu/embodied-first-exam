# humanoidbench-manip-window-i00-standard

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `humanoidbench-manip-window-i00-privileged` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `window` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 94% of the bar (paper 227, FastTD3 613, bar 650); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `humanoidbench-manip-window-i00-privileged`: the
same frozen instance and the same success rule. HumanoidBench runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar for rendering), which holds the reward, judges the
episode as it runs, records it and, after the verdict, renders its video from the recorded trajectory; the
verifier grades the sidecar's record in a container of its own (`tests/Dockerfile`, no network).

Note: the head cameras see the window. `room_camera` (the recording camera frozen at its starting pose) sees
the window, the wiping tool and the robot.

## Difficulty
See `humanoidbench-manip-window-i00-privileged`'s README; here the agent also has no state, no reward and no
simulator of its own, and 50 resets instead of unlimited ones: every try is a real episode on the one robot.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically removes the
interesting tasks. What replaces it (docs/protocol/README.md §4): the floor above (doing nothing cannot
pass), the evidence that the task has a solution (`oracle_evidence` in task.toml), and a human reviewer.

## Verification
`success` = live success: the episode the sim service ran reached the pass mark (HumanoidBench's own rule,
judged on the live simulator; the episode ends there), for the last episode (the one after the last reset;
earlier episodes are in `trajectory_live.f64` and `episode.jsonl`, not graded). Nothing is replayed to grade
it (owner, 2026-10-17). The scene's start is checked against the frozen instance's recorded state
when an episode begins (a mismatch is `instance_mismatch`, infrastructure). `tests/grade.py` reads
`/data/final.json` and copies the evidence to `/logs/verifier/`: `trajectory.npz` (the deliverable,
replayable) and `replay.mp4`, rendered from it in one pass after the verdict (a lost video never changes the
verdict). No oracle; human review in PR #9. `nop` scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 4 GiB | 1024 | 5 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| mode / sensors | standard: head-camera RGB + joint angles and velocities (HumanoidBench's own `image` and `proprio` sensors), a pelvis IMU and a camera fixed in the room; no root pose, no tool pose, no reward; 50 resets (a new episode from the frozen start each; only the last episode is graded) |
| action space | HumanoidBench's own: 61 normalised position targets, 50 Hz, sent in chunks |
| knobs (compose env) | `RCB_RESET_BUDGET` (50: HumanoidBench's standard configuration, tasks/humanoidbench/README.md), `RCB_OBS_PROPRIO` (1), `RCB_OBS_IMU` (1), `RCB_OBS_ROOM_CAMERA` (1), `RCB_OBS_DEPTH` (0): the defaults are the standard configuration; a run that changes one (`RCB_RESET_BUDGET=0 harbor run ...`: one episode, no reset) is reported separately, and `episode.jsonl` records the `/spec` it ran under |
| agent API | `environment/rcb_client.py` (its docstring is the reference); `instruction.md` lists the endpoints |
| physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (tasks/humanoidbench/README.md, Physics). |
