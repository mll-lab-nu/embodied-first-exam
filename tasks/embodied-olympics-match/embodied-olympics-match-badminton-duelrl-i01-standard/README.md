# embodied-olympics-match-badminton-duelrl-i01-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-lockstep/1.0`) |
| Twin | `embodied-olympics-match-badminton-duelrl-i01-privileged` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_duel` / seed 1001 (allowed seeds: [1001, 1, 2]; PROTOCOL §2) |
| Oracle | `partial` — RLBM 2026-10-16, policy bm_cem_v1 with the true shuttle state (v1.1; the shipped policy has no swing option): on this instance (seed 1001, vanilla Harbor 0.23.0) our camera-only reference lost 1:11 (valid, deterministic) and an Azure Astra precheck was 5:5 when Astra forfeited by ready_timeout; live service batch (built-in RL on B, camera reference over HTTP on A, seeds 1-10 x both first servers): reference 0/20 (16 valid, 40:176); in-process (truth, S = 20): mirror RL vs RL seat A 21/40, first server 15/40; as seat A of match-wallclock it beat level 3 in 19 of 20 seeds (217:124) and levels 4 and 5 in 20 of 20; against it on seat B the truth reference won 1/20, short-random, centre, random and nop 0/20; replays identical; limits as the reference |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0` |

## Task
Robot badminton against a built-in opponent player (seat B, builtin_players:RLOpponent), program play: robot singles badminton on a small court (the BWF court's lengths x 0.4, the net at its BWF height 1.524 m) in real time (slowed down): a Franka Panda arm held to the real Panda's limits, with a racket, on an x-y gantry of ball-screw axes (2 m/s, 15 m/s^2), a point-mass shuttle with the real shuttle's high quadratic drag (terminal speed 6.8 m/s) and no bounce, a racket contact law of gain 4 (shuttles leave the racket at up to about 10 m/s); rally scoring, one game to 11 points; the players' robots serve (the rally winner serves next): the server tosses the shuttle (from rest or rising up to 0.5 m) at a point it chooses and hits it underhand, below 1.15 m, into the diagonal service court; format match-wallclock: you against a scripted computer opponent (levels 1-3, `game spec` match.opponent_level), format duel-wallclock: two players.

## Difficulty
Frozen development instance: seed 1001, a built-in opponent, in lockstep (its realtime twin: S = 20). Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. RLBM 2026-10-16, policy bm_cem_v1 with the true shuttle state (v1.1; the shipped policy has no swing option): on this instance (seed 1001, vanilla Harbor 0.23.0) our camera-only reference lost 1:11 (valid, deterministic) and an Azure Astra precheck was 5:5 when Astra forfeited by ready_timeout; live service batch (built-in RL on B, camera reference over HTTP on A, seeds 1-10 x both first servers): reference 0/20 (16 valid, 40:176); in-process (truth, S = 20): mirror RL vs RL seat A 21/40, first server 15/40; as seat A of match-wallclock it beat level 3 in 19 of 20 seeds (217:124) and levels 4 and 5 in 20 of 20; against it on seat B the truth reference won 1/20, short-random, centre, random and nop 0/20; replays identical; limits as the reference.

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
Source: Embodied Olympics task `badminton-duel-wallclock-program-standard`, revision `badminton-wallclock-12+duel-14+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

Standard twin of `embodied-olympics-match-badminton-duelrl-i01-realtime`: the same export, the world in lockstep (`environment/sim/core/lockstep.py`; `eai-standard-lockstep/1.0` in tasks/embodied-olympics-match/README.md).
