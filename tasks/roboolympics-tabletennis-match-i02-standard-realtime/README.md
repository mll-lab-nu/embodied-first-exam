# roboolympics-tabletennis-match-i02-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_match` / seed 12 |
| Oracle | `partial` — re-screen 2026-10-12 (revision 15, D = 5, S = 20): our camera-only reference player beat level 3 in 7 of 40 seeds, this seed 5:1; S = 10 since 2026-10-14 (PR #138); the live oracle run is in the export report |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 10 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Table tennis against the scripted opponent (level 3), program play: robot table tennis in a continuous world slowed by a factor S (MuJoCo Franka Panda + paddle on an x-y rail base behind the end line, both held to the real robot's limits: the Panda's joint velocity, acceleration, jerk, torque and torque rate, the rail's speed, acceleration and jerk; DeepMind ball and table model), seen only through two cameras of four frames each; one game to 5 points (lead by 2 from 4:4, at 6:6 the next point wins); the players' robots serve by the ITTF service laws (a toss device on the robot projects the ball at least 16 cm up from a point you choose behind your end line, you strike it as it falls; 2 serves each, from 4:4 one each); format match: you against a scripted opponent (level 1-4; you serve first), format duel: two players.

## Difficulty
Frozen development instance: seed 12, level 3, slowdown S = 10. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. re-screen 2026-10-12 (revision 15, D = 5, S = 20): our camera-only reference player beat level 3 in 7 of 40 seeds, this seed 5:1; S = 10 since 2026-10-14 (PR #138); the live oracle run is in the export report.

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
Source: RoboOlympics task `tabletennis-match-wallclock-program-standard`, revision `wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
