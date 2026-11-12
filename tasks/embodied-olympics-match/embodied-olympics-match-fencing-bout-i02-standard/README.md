# embodied-olympics-match-fencing-bout-i02-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | `embodied-olympics-match-fencing-bout-i02-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `fencing_bout` / seed 35 (allowed seeds: [35, 202, 212]; PROTOCOL §2) |
| Oracle | `full` — in process (fencing-7): the oracle beats level 2 on this seed 15:13; over 40 player seeds the reference wins this instance 42.5 %, the equilibrium mix 50 % (fresh-seed means 48.0 %, 53.9 %); none of the nine constant intentions nor a random player wins it; live on vanilla Harbor 0.23.0 (2026-10-15, the exported task) the oracle won 15:13 in 32 phrases, replay identical (the world is deterministic) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0` |

## Task
Robot epee fencing against the scripted opponent (level 2), program play: two Unitree G1 humanoids (the robot library's, NVIDIA's SONIC whole-body policy on the legs, waist and free arm, the point skill on the sword arm) holding real epees fence one FIE direct-elimination bout (15 touches or 9 minutes of fencing time, no draws; unwillingness to fight, FIE t.124) phrase by phrase: every phrase starts on guard 1.95 m apart, both fencers choose one of nine tactical intentions (lunge, low lunge, point in line, reactive line, stop-hit, counter-attack, delayed lunge, retreat, draw), each starts after a random 0-50 ms, and the phrase is played out as it was measured in MuJoCo (2916 phrases: every pair of intentions and delays); format bout: you against a scripted fencer that reads your choices (levels 1-2, `game spec` opponent), format duel: two players choosing at the same time.

## Difficulty
Frozen development instance: seed 35, level 2, chess clock 3600 s per player. Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. in process (fencing-7): the oracle beats level 2 on this seed 15:13; over 40 player seeds the reference wins this instance 42.5 %, the equilibrium mix 50 % (fresh-seed means 48.0 %, 53.9 %); none of the nine constant intentions nor a random player wins it; live on vanilla Harbor 0.23.0 (2026-10-15, the exported task) the oracle won 15:13 in 32 phrases, replay identical (the world is deterministic).

## Verification
Separate sandbox, no network. The match is graded live (owner, 2026-10-17): the sim service records the
match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,
`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies
the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`; `realtime` = 0 for a turn-based match).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Notes
Source: Embodied Olympics task `fencing-bout-wallclock-program-standard`, revision `fencing-7+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
