# roboolympics-match-soccerssl-match-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics-Match |
| Mode | privileged |
| Twin | `roboolympics-match-soccerssl-match-i00-standard-realtime` |
| Simulator / robot | `mujoco` / `ssl-robot` |
| Family / instance | `soccer_ssl_match` / seed 7 |
| Oracle | `partial` — full-state reference program (solution/): the sport's reference team (the camera-only reference player's decision code) fed the true state; its formal S = 10 results and its results across levels 1-3 against the camera reference are in the RoboOlympics privileged report (tools/fullsim/calibrate.py); not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false) |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:olympiad-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
The privileged twin of `roboolympics-match-soccerssl-match-i00-standard-realtime`: wheeled robot soccer 5 v 5 (RoboCup SSL Division B): you command the blue team (five omnidirectional SSL robots, the skills move / kick / dribble / substitute) against the scripted yellow team; level 2, seed 7, S = 10.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 10 (the verdict depends on the host's speed, as in the
standard-realtime twin: the verifier runs on 4 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 6 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle trials (ws-1 / ws-2, 2026-10-17): CPU-only MuJoCo, no cameras in the match; the verifier holds the service, the program (2 GiB address space), one replay and the video renderer; 4 CPUs pinned (the match runs on the wall clock)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
