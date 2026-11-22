# robowits-stand-bulb-i00-standard

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robowits-stand-bulb-i00-privileged` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `stand_bulb` / seed 0 |
| Oracle | `none` — No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-stand-bulb-i00__BrTmH6k (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §4). 2026-10-18: the frozen instance is now that scene settled at rest; the positive above was recorded on the earlier instance. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robowits-0.1.1` |

## Task
Stand the tall object with curved bottom stably within the green target area. The same frozen instance as
`robowits-stand-bulb-i00-privileged`, as a robot service (`eai-standard/2.2`): the simulator runs in the `sim`
sidecar, which the agent cannot open; the agent gets one episode, no reset and no privileged state, only the client
(calibrated RGB-D cameras, proprioception, `joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar
judges the live episode, records it as the trajectory and renders the video from it; the success criterion as graded
is in `instruction.md`.

## Difficulty
That of `robowits-stand-bulb-i00-privileged` (its Difficulty), without resets, privileged state or the tooling's
primitives: the agent perceives the scene through calibrated RGB-D cameras and its own proprioception, and every
action it sends is part of the one graded episode.

## Reference solution
None: RoboWits ships no expert or planner, and none is written for this family (`oracle = "none"`). Evidence that it
is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of PR #3 (the trial
is published on the results site).

## Verification
`success` = the live episode's: the settle window that ended it passed on the sidecar's simulator (inside the agent's
last call, or after its last command when its phase is over, once the collect hook has stopped the agent's container),
and no infrastructure failure (`tests/grade.py` reads the sidecar's `final.json`: `graded_by = "live"`, `replays =
0`); nothing is replayed to grade it. The frozen instance is checked when the scene is built, before the agent is
served (`instance_mismatch`, an infrastructure failure). After the verdict the sidecar renders the recorded trajectory
once into `/logs/verifier/replay.mp4`; a failed video never changes the verdict. What is checked, in words:
`instruction.md`, "Success criterion (as graded)".

No oracle; human review in PR #3 (PROTOCOL §4), with its privileged twin: the positive example, the `nop` result and the predicate
summary are in the PR's review table.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 8 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 4 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2` (docs/protocol/standard_mode.md): `submit` chunks of `joint_position` (16, streamed at the 30 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; stateless `kinematics`; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service replays its journal and resumes the same episode (resume class `exact`, docs/protocol/standard_mode.md §13) |
| Agent and verifier image | `docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` with the shared pins (`environment/client-requirements.txt`) |
| Instance | the privileged twin's frozen instance (`environment/sim/instance.json`): entry 0 of RoboWits' `eval_dataset_50/16.json`, settled at rest |
| BlenderKit models | not redistributable, so not in the image: mounted read-only into the `sim` sidecar from `$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |
