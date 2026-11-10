# embodied-olympics-match-tabletennis-match-i04-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-lockstep/1.0`) |
| Twin | `embodied-olympics-match-tabletennis-match-i04-privileged` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_match` / seed 34 (allowed seeds: [34, 404, 414]; PROTOCOL §2) |
| Oracle | `partial` — level 4 (the strongest official level, unchanged): a mirror match (the level-4 opponent copied onto the player's side, same limits, same true-state prediction) won 18 of 40 (seeds 1-20, each side serving first), so level 4 is beatable by a player of its own ability; our truth-state reference beat level 4 in 2 of 40 seeds (re-screen 2026-10-12, revision 15), this seed 5:3; our camera-only reference 0 of 40; every simple baseline 0 of 20; the live oracle run is in the export report |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0` |

## Task
Table tennis against the scripted opponent (level 4), program play: robot table tennis in a continuous world slowed by a factor S (MuJoCo Franka Panda + paddle on an x-y rail base behind the end line, both held to the real robot's limits: the Panda's joint velocity, acceleration, jerk, torque and torque rate, the rail's speed, acceleration and jerk; DeepMind ball and table model), seen only through two cameras of four frames each; one game to 5 points (lead by 2 from 4:4, at 6:6 the next point wins); the players' robots serve by the ITTF service laws (a toss device on the robot projects the ball at least 16 cm up from a point you choose behind your end line, you strike it as it falls; 2 serves each, from 4:4 one each); format match: you against a scripted opponent (level 1-4; you serve first), format duel: two players.

## Difficulty
Frozen development instance: seed 34, level 4, in lockstep (its realtime twin: S = 10). Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. level 4 (the strongest official level, unchanged): a mirror match (the level-4 opponent copied onto the player's side, same limits, same true-state prediction) won 18 of 40 (seeds 1-20, each side serving first), so level 4 is beatable by a player of its own ability; our truth-state reference beat level 4 in 2 of 40 seeds (re-screen 2026-10-12, revision 15), this seed 5:3; our camera-only reference 0 of 40; every simple baseline 0 of 20; the live oracle run is in the export report.

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
Source: Embodied Olympics task `tabletennis-match-wallclock-program-standard`, revision `wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

Standard twin of `embodied-olympics-match-tabletennis-match-i04-realtime`: the same export, the world in lockstep (`environment/sim/core/lockstep.py`; `eai-standard-lockstep/1.0` in tasks/embodied-olympics-match/README.md).
