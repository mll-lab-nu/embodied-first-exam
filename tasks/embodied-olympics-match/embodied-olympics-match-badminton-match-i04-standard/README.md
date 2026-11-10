# embodied-olympics-match-badminton-match-i04-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-lockstep/1.0`) |
| Twin | `embodied-olympics-match-badminton-match-i04-privileged` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_match` / seed 1034 (allowed seeds: [1034, 1, 2]; PROTOCOL §2) |
| Oracle | `partial` — TOPBM calibration 2026-10-16 (a CPU cluster, S = 20, perception-free players, seeds 1001-1040): the reference's own prediction and strokes placing every shot short to a random front corner won 5 of 40 (this seed 11:8), the reference itself 0 of 40 (this seed 1:11), short alternating 0 of 40 (the other simple baselines: Embodied Olympics PR #181); our camera-only reference does not win level 2, so the oracle run checks the pipeline (a valid, replayed match), not a win |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0` |

## Task
Robot badminton against the scripted opponent (level 5), program play: robot singles badminton on a small court (the BWF court's lengths x 0.4, the net at its BWF height 1.524 m) in real time (slowed down): a Franka Panda arm held to the real Panda's limits, with a racket, on an x-y gantry of ball-screw axes (2 m/s, 15 m/s^2), a point-mass shuttle with the real shuttle's high quadratic drag (terminal speed 6.8 m/s) and no bounce, a racket contact law of gain 4 (shuttles leave the racket at up to about 10 m/s); rally scoring, one game to 11 points; the players' robots serve (the rally winner serves next): the server tosses the shuttle (from rest or rising up to 0.5 m) at a point it chooses and hits it underhand, below 1.15 m, into the diagonal service court; format match-wallclock: you against a scripted computer opponent (levels 1-3, `game spec` match.opponent_level), format duel-wallclock: two players.

**Opponent level 5.** Level 5 is a tier of this exported task only (the sport's own levels 1-3 are described under Rules): the level 2 opponent (reach 0.85 m, level 2's attacks, 0.25 s to spare on its shots except its kills) with a reaction of 0.22 s (level 2: 0.25 s, level 3: 0.20 s), level 3's walk back after its own stroke (2 m/s instead of 0.6 m/s) and level 3's kills, in 90 % of its attacks (level 2: 50 %). Like every level it predicts the shuttle's flight exactly; its base and arm obey the same limits as yours. `game spec` match.opponent_level is 5.

## Difficulty
Frozen development instance: seed 1034, level 5, in lockstep (its realtime twin: S = 20). Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. TOPBM calibration 2026-10-16 (a CPU cluster, S = 20, perception-free players, seeds 1001-1040): the reference's own prediction and strokes placing every shot short to a random front corner won 5 of 40 (this seed 11:8), the reference itself 0 of 40 (this seed 1:11), short alternating 0 of 40 (the other simple baselines: Embodied Olympics PR #181); our camera-only reference does not win level 2, so the oracle run checks the pipeline (a valid, replayed match), not a win.

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
Source: Embodied Olympics task `badminton-match-wallclock-program-standard`, revision `badminton-wallclock-12+duel-14+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

Standard twin of `embodied-olympics-match-badminton-match-i04-realtime`: the same export, the world in lockstep (`environment/sim/core/lockstep.py`; `eai-standard-lockstep/1.0` in tasks/embodied-olympics-match/README.md).
