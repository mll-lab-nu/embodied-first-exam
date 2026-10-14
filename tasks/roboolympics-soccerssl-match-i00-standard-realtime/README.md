# roboolympics-soccerssl-match-i00-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `ssl-robot` |
| Family / instance | `soccer_ssl_match` / seed 7 |
| Oracle | `partial` — screening (soccer_ssl-1): the camera reference's result at level 2 is not established for this development seed; a model won level 2 (Opus 4:3, camera only). The oracle run checks the pipeline |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 10 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Wheeled robot soccer 5 v 5 (RoboCup SSL Division B) against the scripted opponent (level 2), program play: wheeled robot soccer 5 v 5 under the RoboCup Small Size League rules (Division B): ten omnidirectional SSL robots after TIGERs Mannheim's v2020 (kicker, chip kicker, dribbler; their real speed, acceleration, kick and dribbler limits) and an orange golf ball on the 9 x 6 m field, two halves of 300 s of playing time, a shoot-out when level, an automatic referee for every rule an SSL auto-referee judges; you command your robots with three skills (move to a pose, optionally by a time and at a speed; kick flat or chipped along the robot's heading, now or the moment the ball reaches it; spin the dribbler) and see the game through the four overhead cameras of the shared vision, 40 ms late; in the `match` format you command the blue team against a scripted team, in the `duel` format another player commands the yellow team, in the `team` format each robot has its own player.

## Difficulty
Frozen development instance: seed 7, level 2, slowdown S = 10. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. screening (soccer_ssl-1): the camera reference's result at level 2 is not established for this development seed; a model won level 2 (Opus 4:3, camera only). The oracle run checks the pipeline.

## Verification
Separate sandbox, no network. The sim service replays the recorded match in a fresh process; the verifier
(`tests/grade.py`, our core's grader) checks that the replay agrees with the live match, applies the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: as the standard twin; the GPU renders the cameras over EGL (board 0112, 2026-10-14): author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details

### Notes
Source: RoboOlympics task `soccer_ssl-match-wallclock-program-standard`, revision `soccer_ssl-1`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
