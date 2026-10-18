# roboolympics-soccer-jointgpu-i01-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c; its resource-tier twin is `roboolympics-soccer-jointcpu-i01-standard-realtime`) |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_jointmatch` / seed 101 |
| Oracle | `partial` — soccer-2v2-11, level 5 = our joint-level RL team (sports/soccer/rl/joint/v2: an omnidirectional gait trained with PPO at the joint level, about 1e9 steps, and an RL-trained strategy layer). The three frozen GPU-tier programs of GPT-6 Astra from our v5 pilot (developed on soccer-2v2-10 against level 2, unchanged) win 30 % of 90 practice matches against level 5 v2 (40 % against v1; against v1 on further seeds 48/150 = 32 % and 43 % of 150); a mirror match of v1 is even (24/50); scripted levels 2 and 3 never beat it (0/20, 0/40). Our joint-level reference team (the oracle) lost to level 5 v1 0:10 in both tasks on vanilla Harbor 0.23.0 (valid, replay identical, replay.mp4) |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 10 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0` |

## Task
Humanoid robot soccer 2 v 2 at the joint level, coach format: the agent commands both Booster T1s (lower bodies) of its
team with 12 leg joint targets per robot every 20 ms (no walking policy, no kick skill), against a learned opponent team at the joint level (level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint interface and limits as yours; a learned strategy layer decides what each robot does),
under the RoboCup Humanoid Soccer League rules with stated deviations. Any method: hand-written control, planning,
optimisation or learning. A practice service runs full copies of the match world (the opponent as a black box).

## Difficulty
Frozen development instance: seed 101, a learned opponent team at the joint level (level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint interface and limits as yours; a learned strategy layer decides what each robot does), S = 10. Not one of the sport's official
(hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our joint-level reference team (capture-point walking, `joint_oracle.py` on `team.py`, `walker.py`, `dcm.py`)
through the same HTTP interface, after a short check of the practice service. soccer-2v2-11, level 5 = our joint-level RL team (sports/soccer/rl/joint/v2: an omnidirectional gait trained with PPO at the joint level, about 1e9 steps, and an RL-trained strategy layer). The three frozen GPU-tier programs of GPT-6 Astra from our v5 pilot (developed on soccer-2v2-10 against level 2, unchanged) win 30 % of 90 practice matches against level 5 v2 (40 % against v1; against v1 on further seeds 48/150 = 32 % and 43 % of 150); a mirror match of v1 is even (24/50); scripted levels 2 and 3 never beat it (0/20, 0/40). Our joint-level reference team (the oracle) lost to level 5 v1 0:10 in both tasks on vanilla Harbor 0.23.0 (valid, replay identical, replay.mp4).

## Verification
Separate sandbox, no network. The match is graded live (owner, 2026-10-17, board 0151): the sim service records the
match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,
`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies
the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`, `gpu_tier`, `replay_video`). The replay video `replay.mp4` comes with every finished match.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 16 | 2 |
| Memory | 24 GB | 2 GB |
| GPU memory | 10 GB | 0 GB |

- GPU: required, any NVIDIA GPU; recommended: RTX 4090 24GB / L4 24GB / L40S 48GB.
- Measured: RoboOlympics' joint-level soccer pilot v5 (ws-1, 2026-10-15/16, nvidia-smi every 30 s): the agents trained with rsl_rl on the GPU worlds at 3-10 GB of GPU memory (one RTX 4090); the sim and the practice service as the CPU tier
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: 12 GiB GPU memory, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 12 GiB GPU memory, 32 GiB memory. Limits measured: the v5 pilot's seat caps (6 cores, 16 GB, processes 512: design default); whole trial: + the sim's and the practice service's 8 GB caps; provisional.

## Details
| | |
|---|---|
| Resource tier | **CPU + GPU**: 6 cores, 16 GB, 1 NVIDIA GPU (mjlab + rsl_rl, PyTorch CUDA) |
| Images | agent `ghcr.io/mll-lab-nu/eai-soccer-joint-gpu:0.1.3@sha256:7dee4b99af4bd5ec5c0d974176d09c6452c581645fc07295889c8fb4c8b22c69`; sim and practice `ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0` |

### The pair
This task and roboolympics-soccer-jointcpu-i01-standard-realtime are the same frozen match (seed, opponent, slowdown, start window, review limit, cutoff)
and differ only in the agent's resources: the CPU tier has 6 cores and numpy / SciPy / MuJoCo; the GPU tier adds one
NVIDIA GPU with mjlab 1.6.0 + rsl_rl 5.4.2, the full 2 v 2 match world on the GPU (thousands of matches in parallel,
the scripted levels compiled) and a single-T1 GPU environment. The pair measures what a GPU and the time to use it are
worth to an agent that builds a robot controller.

### Notes
Source: RoboOlympics joint-level soccer pilot v5 (`pilots/soccer_joint/make_v5_tasks.py` on task `soccer-match-wallclock-program-lowlevel-standard`), physics revision
`soccer-2v2-11` (near-rigid foot-turf contact). The rules, the referee, the opponent, the observation, the reviews and
the grader are ours, unchanged; the seat is unmetered (Harbor records the model's usage), the instance is frozen, and the
session is the hub's 4 h (v5 had 9 h with 30 min reviews). The agent image is the v5 seat image, prebuilt
(`pilots/soccer_joint/make_v5_tasks.py`'s Dockerfile; `environment/Dockerfile` pins it by digest).
