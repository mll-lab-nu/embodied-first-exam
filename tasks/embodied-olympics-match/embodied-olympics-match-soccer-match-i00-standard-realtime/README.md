# embodied-olympics-match-soccer-match-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | `embodied-olympics-match-soccer-match-i00-privileged` |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_match` / seed 7 |
| Oracle | `partial` — screening 2026-10-12 (soccer-2v2-9): our built-in camera reference does not beat level 2 (0/10; it cannot kick while walking); a model did (Astra 12:2 at level 2, camera only). The oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 (an official match slowdown) so that 2 x 5 min of game time (3000 s of wall time) and the reviews fit the hub's 7200 s |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 5 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:olympiad-soccer-0.1.0` |

## Task
Robot soccer 2 v 2 against the scripted opponent (level 2), program play: robot soccer 2 v 2 under the RoboCup Humanoid Soccer League rules: four simulated Booster T1 humanoids (lower bodies on the released walking policy, held to the real robot's joint limits) and one ball on a boarded 10 x 7 m pitch with two goals, two halves of 5 minutes of game time, a penalty shoot-out when level; each robot takes a walk velocity command, stand or a swing-leg kick, and you see the game only through your robots' head cameras; in the `match` format you command both robots of team A against a scripted team, in the `duel` format another player commands team B, in the `team` format each robot has its own player and teammates talk only through the team channel, in the `team_match` format each robot of team A has its own player against the scripted team; `match_overhead` and `duel_overhead` are match and duel seen through fixed overhead cameras instead of the head cameras.

## Difficulty
Frozen development instance: seed 7, level 2, slowdown S = 5. Not one of
the sport's official (hidden) seeds, so results here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. screening 2026-10-12 (soccer-2v2-9): our built-in camera reference does not beat level 2 (0/10; it cannot kick while walking); a model did (Astra 12:2 at level 2, camera only). The oracle run checks the pipeline (a valid, replayed match), not a win. S = 5 (an official match slowdown) so that 2 x 5 min of game time (3000 s of wall time) and the reviews fit the hub's 7200 s.

## Verification
Separate sandbox, no network. The match is graded live (owner, 2026-10-17, board 0151): the sim service records the
match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,
`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies
the validity rule
(technical failures void the trial, a player's own problems are a valid loss), and writes reward.json; success = a
valid, finished match that the agent won. `tests/fexam_reward.py` adds the hub's fields (`infra_error`, `realtime`,
`slowdown`, `opponent_level`).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 7 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Embodied Olympics' exported matches (scripts/embodied-olympics/exported.toml): the values of the matches it measured on the 2.3 adapter (tasks/embodied-olympics-fun/README.md): the sim takes up to 6 CPUs, the agent 2; memory: sim 0.7-1.4 GB, agent 2.2 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU-only, real time needs the cores
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, 4090-ws1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 4 GiB cap; whole trial: + the sim service's 8 GiB (docker peak 0.7 GiB, 5 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Notes
Source: Embodied Olympics task `soccer-match-wallclock-program-standard`, revision `soccer-2v2-10+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

### Change Log
- 2026-10-16 (board 0136): the replay video only. The sim's spectator render (`core.spectator`, after the verdict) may take 1800 s (`RCB_VIDEO_TIMEOUT_S`, was 300 s) and the collect hook waits as long for `video.json`; `[[verifier.collect]]` `timeout_sec` 2580 s (was 1080 s), `[verifier]` `timeout_sec` 2760 s (was 1260 s). A full match (2 x 5 min, about 30,000 control steps) takes about 8-10 min to replay and draw on a 64-vCPU host, so every trial before this date ended without its video. The match, the replay check, the grader and the pass rule are unchanged (`core/` and `sport/`, the match's `source_sha`, are untouched): earlier results stand.
