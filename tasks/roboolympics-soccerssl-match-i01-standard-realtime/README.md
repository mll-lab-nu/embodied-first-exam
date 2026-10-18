# roboolympics-soccerssl-match-i01-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `ssl-robot` |
| Family / instance | `soccer_ssl_match` / seed 7 |
| Oracle | `partial` — RLSSL 2026-10-16 (doc rlssl): L-RL against L3 25 W 5 D 10 L over 40 matches on fresh seeds (64 W 11 D 25 L over 100 with the screening), goals +1.7 per match; mirror match 29 W 5 D 46 L over 80 (two 40-match seed sets: 25 % and 48 %; L3 against itself on the first set 60 %); the truth reference against it 10 W of 20; replay identical; limits through World.execute (0.014 % of commands clipped, as L3). The oracle run checks the pipeline |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 10 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Wheeled robot soccer 5 v 5 (RoboCup SSL Division B) against the opponent team at level 4 (the reinforcement-learned tier), program play: wheeled robot soccer 5 v 5 under the RoboCup Small Size League rules (Division B): ten omnidirectional SSL robots after TIGERs Mannheim's v2020 (kicker, chip kicker, dribbler; their real speed, acceleration, kick and dribbler limits) and an orange golf ball on the 9 x 6 m field, two halves of 300 s of playing time, a shoot-out when level, an automatic referee for every rule an SSL auto-referee judges; you command your robots with three skills (move to a pose, optionally by a time and at a speed; kick flat or chipped along the robot's heading, now or the moment the ball reaches it; spin the dribbler) and see the game through the four overhead cameras of the shared vision, 40 ms late; in the `match` format you command the blue team against a scripted team, in the `duel` format another player commands the yellow team, in the `team` format each robot has its own player.

## Difficulty
Frozen development instance: seed 7, level 4, slowdown S = 10. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. RLSSL 2026-10-16 (doc rlssl): L-RL against L3 25 W 5 D 10 L over 40 matches on fresh seeds (64 W 11 D 25 L over 100 with the screening), goals +1.7 per match; mirror match 29 W 5 D 46 L over 80 (two 40-match seed sets: 25 % and 48 %; L3 against itself on the first set 60 %); the truth reference against it 10 W of 20; replay identical; limits through World.execute (0.014 % of commands clipped, as L3). The oracle run checks the pipeline.

## Verification
Separate sandbox, no network. The match is graded live (owner, 2026-10-17, board 0151): the sim service records the
match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,
`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies
the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 7 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: RoboOlympics' exported matches (scripts/roboolympics/exported.toml): the values of the matches it measured on the 2.3 adapter (docs/benchmarks/roboolympics.md): the sim takes up to 6 CPUs, the agent 2; memory: sim 0.7-1.4 GB, agent 2.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only, real time needs the cores
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 4 GiB cap; whole trial: + the sim service's 8 GiB (docker peak 0.7 GiB, 5 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Notes
Source: RoboOlympics task `soccer_ssl-match-wallclock-program-standard`, revision `soccer_ssl-1`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
