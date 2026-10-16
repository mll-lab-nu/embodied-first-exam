# roboolympics-curling-match-i01-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `curling-fcv1` / `stone-delivery-mechanism` |
| Family / instance | `curling_match` / seed 7 |
| Oracle | `full` — level 3 is the strongest scripted team, chosen as the hardest level (hub target: standard below 50 %). Vanilla Harbor 0.23.0 on mll-4090-1, 2026-10-16: our camera-only reference player won this instance 2:1 in repeated oracle runs with the same stones (equal state_sha; curling's stepping is bit-exact across machines); it won 2 of the 8 development seeds 7-9, 11-15 tried at level 3 (the screening: the truth-state reference 45 % at level 3, docs/screening/curling.md) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Curling against the scripted opponent (level 3), program play: two teams slide granite stones down a sheet of ice towards the house, 4 ends of 5 stones per team; you skip one team and throw every one of its stones (release speed, direction and spin); in the `match` format the other team is a scripted computer team, in the `duel` format another player.

## Difficulty
Frozen development instance: seed 7, level 3; turn-based (nothing moves while a player thinks), a chess clock of 60 minutes of real time per side on its own turns, no
limit per move, no slowdown. Not one of the sport's official (hidden) seeds, so results here are previews, not
official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. level 3 is the strongest scripted team, chosen as the hardest level (hub target: standard below 50 %). Vanilla Harbor 0.23.0 on mll-4090-1, 2026-10-16: our camera-only reference player won this instance 2:1 in repeated oracle runs with the same stones (equal state_sha; curling's stepping is bit-exact across machines); it won 2 of the 8 development seeds 7-9, 11-15 tried at level 3 (the screening: the truth-state reference 45 % at level 3, docs/screening/curling.md).

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
Source: RoboOlympics task `curling-match-program-standard`, revision `curling-4`. The rules, the referee, the scripted
opponent, the observation, the review after each action, the chess clocks and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen. How it differs from the hub's own standard mode: our `game` CLI / HTTP service instead of the `eai-standard` client; the opponent is a scripted player inside the service; the players take turns and the world waits for the player on turn; each side has a chess clock (out of time = the match is lost) and sends a short review after each of its actions; no resets; success is binary: 1 = a valid match won against the scripted opponent, else 0 (the score is an extra field).
