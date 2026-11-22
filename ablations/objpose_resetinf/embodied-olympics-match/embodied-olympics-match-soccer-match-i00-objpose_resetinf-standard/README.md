# embodied-olympics-match-soccer-match-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-lockstep/1.0`) |
| Twin | `embodied-olympics-match-soccer-match-i00-privileged` |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_match` / seed 7 |
| Oracle | `partial` — screening 2026-10-12 (soccer-2v2-9): our built-in camera reference does not beat level 2 (0/10; it cannot kick while walking); a model did (Astra 12:2 at level 2, camera only). The oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 (an official match slowdown) so that 2 x 5 min of game time (3000 s of wall time) and the reviews fit the hub's 7200 s |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0` |

## Task
Robot soccer 2 v 2 against the scripted opponent (level 2), program play: robot soccer 2 v 2 under the RoboCup Humanoid Soccer League rules: four simulated Booster T1 humanoids (lower bodies on the released walking policy, held to the real robot's joint limits) and one ball on a boarded 10 x 7 m pitch with two goals, two halves of 5 minutes of game time, a penalty shoot-out when level; each robot takes a walk velocity command, stand or a swing-leg kick, and you see the game only through your robots' head cameras; in the `match` format you command both robots of team A against a scripted team, in the `duel` format another player commands team B, in the `team` format each robot has its own player and teammates talk only through the team channel, in the `team_match` format each robot of team A has its own player against the scripted team; `match_overhead` and `duel_overhead` are match and duel seen through fixed overhead cameras instead of the head cameras.

## Difficulty
Frozen development instance: seed 7, level 2, in lockstep (its standard-realtime twin: S = 5). Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. screening 2026-10-12 (soccer-2v2-9): our built-in camera reference does not beat level 2 (0/10; it cannot kick while walking); a model did (Astra 12:2 at level 2, camera only). The oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 (an official match slowdown) so that 2 x 5 min of game time (3000 s of wall time) and the reviews fit the hub's 7200 s.

## Verification
Separate sandbox, no network. The match is graded live (owner, 2026-10-17): the sim service records the
match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,
`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies
the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 6 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Notes
Source: Embodied Olympics task `soccer-match-wallclock-program-standard`, revision `soccer-2v2-10+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

Standard twin of `embodied-olympics-match-soccer-match-i00-standard-realtime`: the same export, the world in lockstep (`environment/sim/core/lockstep.py`; `eai-standard-lockstep/1.0` in tasks/embodied-olympics-match/README.md).
