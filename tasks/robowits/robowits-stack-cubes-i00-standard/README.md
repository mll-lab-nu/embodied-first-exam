# robowits-stack-cubes-i00-standard

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robowits-stack-cubes-i00-privileged` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `stack_cubes` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `partial` — Reference solution solution/oracle_replay.py, which streams the privileged oracle's recorded joint rows (solution/oracle_qpos.npy) through the client. It scored 1 under Harbor -a oracle on the dev branch 9eb18edf version of this task (protocol 2.2, then named rcb-limited): job v22-laptop-oracle-stack-cubes-0413, trial robowits-stack-cubes-i00-limited__Yw2oaio, 2026-09-29 (laptop, Intel; success=1, live 1, replay 1, deterministic 1). Same since then: the frozen instance (state hash 41c4d7e7d7193b0d), the joint rows (equal to that run's recorded trajectory) and the tooling rcb_robowits.py. Changed since then, so the label is partial: the grader (this PR: the crash-recovery fields and infra_error), the sim adapter server.py and the shared layer rcb_limited.py / rcb_client.py (this PR: crash recovery), the collect hook, the client image and pins, and the oracle player (this PR: it recovers from a crash). Not re-run on this version (static validation only, 2026-10-01). -i01 (2026-10-14, an AMD workstation): Harbor -a oracle scored 1 on a pre-final tree of this change (under a temporary -i01 task name) (trial robowits-stack-cubes-i01-standard__MRgjkTT: live 1, replay 1, deterministic 1), nop 0; since then the service's end-of-phase reason and the instruction's busy-service note changed. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robowits-0.1.1` |

## Task
Build a stable two-layer stack so the red cube's center is above the green colored dot. The same frozen instance as
`robowits-stack-cubes-i00-privileged`, as a robot service (`eai-standard/2.2`): the simulator runs in the `sim`
sidecar, which the agent cannot open; the agent gets one episode, no reset and no privileged state, only the client
(calibrated RGB-D cameras, proprioception, `joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar
judges the live episode, records it as the trajectory and renders the video from it; the success criterion as graded
is in `instruction.md`.

## Difficulty
That of `robowits-stack-cubes-i00-privileged` (its Difficulty), without resets, privileged state or the tooling's
primitives: the agent perceives the scene through calibrated RGB-D cameras and its own proprioception, and every
action it sends is part of the one graded episode.

## Reference solution
`solution/oracle_replay.py` replays the privileged oracle's recorded joint targets (`solution/oracle_qpos.npy`, one
row per control step, `hold`) through the client, with no privileged information at run time; `solution/solve.sh` runs
it. The rows are the trajectory of the privileged reference solution (`robowits-stack-cubes-i00-privileged`,
`solution/`).

## Verification
`success` = the live episode's: the settle window that ended it passed on the sidecar's simulator (inside the agent's
last call, or after its last command when its phase is over, once the collect hook has stopped the agent's container),
and no infrastructure failure (`tests/grade.py` reads the sidecar's `final.json`: `graded_by = "live"`, `replays =
0`); nothing is replayed to grade it. The frozen instance is checked when the scene is built, before the agent is
served (`instance_mismatch`, an infrastructure failure). After the verdict the sidecar renders the recorded trajectory
once into `/logs/verifier/replay.mp4`; a failed video never changes the verdict. What is checked, in words:
`instruction.md`, "Success criterion (as graded)".

Oracle partial: the reference solution scored 1 on an earlier version of this task and was not re-run on this one
(`oracle_evidence` in `task.toml`); human review in PR #3 (PROTOCOL §4), with its privileged twin.

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
| Instance | the privileged twin's frozen instance (`environment/sim/instance.json`): entry 0 of RoboWits' `eval_dataset_50/14.json` |
