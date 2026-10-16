# roboolympics-soccer-match-i02-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_match` / seed 7 |
| Oracle | `partial` — level 4 exists only in this export (tools/fexam/soccer/level4.toml): level 3's play at the T1 walking policy's full forward command of 1.0 m/s and 0.6 m/s sideways. Winnable: the same team on the player's side (the mirror) wins 19 of 30 calibration matches against it, this seed 5:1 and 8:2 (both kick-offs, Quest; a seed's outcome depends on the CPU); the truth-state reference (level 3's play) wins 5 of 40; level 1's and level 2's play and a standing team lose every match (0/40). Our camera-only reference does not win level 2, so the oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 as i00 and i01 |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 5 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0` |

## Task
Robot soccer 2 v 2 against the scripted opponent (level 4), program play: robot soccer 2 v 2 under the RoboCup Humanoid Soccer League rules: four simulated Booster T1 humanoids (lower bodies on the released walking policy, held to the real robot's joint limits) and one ball on a boarded 10 x 7 m pitch with two goals, two halves of 5 minutes of game time, a penalty shoot-out when level; each robot takes a walk velocity command, stand or a swing-leg kick, and you see the game only through your robots' head cameras; in the `match` format you command both robots of team A against a scripted team, in the `duel` format another player commands team B, in the `team` format each robot has its own player and teammates talk only through the team channel, in the `team_match` format each robot of team A has its own player against the scripted team; `match_overhead` and `duel_overhead` are match and duel seen through fixed overhead cameras instead of the head cameras.

## Difficulty
Frozen development instance: seed 7, level 4, slowdown S = 5. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.
Opponent level 4 exists only in this export (not an official level): level 3's play (true state, no delay, both robots go for the ball, the in-walk kick) at the T1 walking policy's full forward command (1.0 m/s instead of 0.8) and 0.6 m/s sideways (instead of 0.4), within the same real-robot limits; the same team on the player's side wins 19 of 30 calibration matches against it (the mirror), the truth reference that is level 3's play 5 of 40, level 1's and level 2's play and a standing team none

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. level 4 exists only in this export (tools/fexam/soccer/level4.toml): level 3's play at the T1 walking policy's full forward command of 1.0 m/s and 0.6 m/s sideways. Winnable: the same team on the player's side (the mirror) wins 19 of 30 calibration matches against it, this seed 5:1 and 8:2 (both kick-offs, Quest; a seed's outcome depends on the CPU); the truth-state reference (level 3's play) wins 5 of 40; level 1's and level 2's play and a standing team lose every match (0/40). Our camera-only reference does not win level 2, so the oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 as i00 and i01.

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
- Measured: RoboOlympics' exported matches (scripts/roboolympics/exported.toml): the values of the matches it measured on the 2.3 adapter (docs/benchmarks/roboolympics.md): the sim takes up to 6 CPUs, the agent 2; memory: sim 0.7-1.4 GB, agent 2.2 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU-only, real time needs the cores
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, mll-4090-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 4 GiB cap; whole trial: + the sim service's 8 GiB (docker peak 0.7 GiB, 5 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Notes
Source: RoboOlympics task `soccer-match-wallclock-program-standard`, revision `soccer-2v2-10+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
