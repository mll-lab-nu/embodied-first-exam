# embodied-olympics-match-fencing-bout-i02-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (none: a task Embodied Olympics exports with its own service, PROTOCOL §4c; a turn-based match has no trajectory deliverable) |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `fencing_bout` / seed 35 |
| Oracle | `full` — in process (fencing-7): the oracle beats level 2 on this seed 15:13; over 40 player seeds the reference wins this instance 42.5 %, the equilibrium mix 50 % (fresh-seed means 48.0 %, 53.9 %); none of the nine constant intentions nor a random player wins it; live on vanilla Harbor 0.23.0 (2026-10-15, the exported task) the oracle won 15:13 in 32 phrases, replay identical (the world is deterministic) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:olympiad-0.1.0` |

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

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: vanilla Harbor 0.23.0 on an RTX 4090 workstation (32 cores), 2026-10-15, oracle and nop of both tasks, docker stats every 5 s: the sim peaks at 4.0 CPUs (its cap) and 0.71 GiB (the replay in a fresh process and the video after the bout; a bout is about 20 s of service time), the oracle's container under 0.1 GiB (a model's harness needs more: Embodied Olympics' agent default); turn-based, so fewer CPUs only slow it down; CPU only
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: design defaults of Embodied Olympics' exported matches (the agent 4 GiB under its 6 GiB cap; whole trial: + the sim's 8 GiB cap); measured peaks 2026-10-15: sim 0.71 GiB, oracle container under 0.1 GiB.

## Details

### Notes
Source: Embodied Olympics task `fencing-bout-wallclock-program-standard`, revision `fencing-7+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.
