# roboolympics-darts-501-i01-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `dart-release-mechanism` |
| Family / instance | `darts_501` / seed 7 |
| Oracle | `full` — level 4 is the strongest scripted thrower (0.9 x your scatter), chosen as the hardest level (hub target: standard below 50 %). Vanilla Harbor 0.23.0 on mll-4090-1, 2026-10-16: our camera-only reference player won this instance 2:0 in repeated oracle runs with the same darts (equal state_sha; turn-based play is deterministic); it won 2 of the 8 development seeds 7-9, 11-15 tried at level 4 (the screening: the truth-state reference 25 % at level 4, docs/screening/darts.md section 6) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Darts (501) against the scripted opponent (level 4), program play: best of 3 legs of 501 double-out at a regulation board, each dart a release command (yaw, pitch, speed) with seeded scatter under gravity and quadratic drag; format 501: you against a built-in scripted thrower (opponent level 1-4, `game spec` opponent), format duel: two players at one board.

## Difficulty
Frozen development instance: seed 7, level 4; turn-based (nothing moves while a player thinks), a chess clock of 60 minutes of real time per side on its own turns, no
limit per move, no slowdown. Not one of the sport's official (hidden) seeds, so results here are previews, not
official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. level 4 is the strongest scripted thrower (0.9 x your scatter), chosen as the hardest level (hub target: standard below 50 %). Vanilla Harbor 0.23.0 on mll-4090-1, 2026-10-16: our camera-only reference player won this instance 2:0 in repeated oracle runs with the same darts (equal state_sha; turn-based play is deterministic); it won 2 of the 8 development seeds 7-9, 11-15 tried at level 4 (the screening: the truth-state reference 25 % at level 4, docs/screening/darts.md section 6).

## Verification
Separate sandbox, no network. The sim service replays the recorded match in a fresh process; the verifier
(`tests/grade.py`, our core's grader) checks that the replay agrees with the live match, applies the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`clock_s`, `clock_used_s`, `opponent_level`).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 7 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: RoboOlympics' exported turn-based matches (scripts/roboolympics/exported.toml): the same sim service and agent image as its exported realtime matches (sim up to 6 CPUs, agent 2; turn-based play needs no real-time cores, so these are upper bounds); CPU only
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: as RoboOlympics' exported realtime matches (the same agent image and sim service): agent 4 GiB, whole trial + the sim service's 8 GiB; processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Notes
Source: RoboOlympics task `darts-501-program-standard`, revision `darts-7+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review after each action, the chess clocks and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen. How it differs from the hub's own standard mode: our `game` CLI / HTTP service instead of the `eai-standard` client; the opponent is a scripted player inside the service; the players take turns and the world waits for the player on turn; each side has a chess clock (out of time = the match is lost) and sends a short review after each of its actions; no resets; success is binary: 1 = a valid match won against the scripted opponent, else 0 (the score is an extra field).
