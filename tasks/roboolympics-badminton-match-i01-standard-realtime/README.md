# roboolympics-badminton-match-i01-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_match` / seed 7 |
| Oracle | `partial` — screening round 16 (2026-10-13, revision 12, S = 20): our camera-only reference player beat level 1 in 17 of 20 seeds; on this instance at S = 20 it lost 10:12 (vanilla Harbor 0.23.0, 2026-10-13: a valid, replayed match, 78 min) |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 20 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Robot badminton against the scripted opponent (level 1), program play: robot singles badminton on a small court (the BWF court's lengths x 0.4, the net at its BWF height 1.524 m) in real time (slowed down): a Franka Panda arm held to the real Panda's limits, with a racket, on an x-y gantry of ball-screw axes (2 m/s, 15 m/s^2), a point-mass shuttle with the real shuttle's high quadratic drag (terminal speed 6.8 m/s) and no bounce, a racket contact law of gain 4 (shuttles leave the racket at up to about 10 m/s); rally scoring, one game to 11 points; the players' robots serve (the rally winner serves next): the server tosses the shuttle (from rest or rising up to 0.5 m) at a point it chooses and hits it underhand, below 1.15 m, into the diagonal service court; format match-wallclock: you against a scripted computer opponent (levels 1-3, `game spec` match.opponent_level), format duel-wallclock: two players.

## Difficulty
Frozen development instance: seed 7, level 1, slowdown S = 20. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. screening round 16 (2026-10-13, revision 12, S = 20): our camera-only reference player beat level 1 in 17 of 20 seeds; on this instance at S = 20 it lost 10:12 (vanilla Harbor 0.23.0, 2026-10-13: a valid, replayed match, 78 min).

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
| CPU cores | 8 | 7 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: RoboOlympics' exported matches (scripts/roboolympics/exported.toml): the values of the matches it measured on the 2.3 adapter (docs/benchmarks/roboolympics.md): the sim takes up to 6 CPUs, the agent 2; memory: sim 0.7-1.4 GB, agent 2.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only, real time needs the cores
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 4 GiB cap; whole trial: + the sim service's 8 GiB (docker peak 0.7 GiB, 5 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Notes
Source: RoboOlympics task `badminton-match-wallclock-program-standard`, revision `badminton-wallclock-12+duel-14+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
