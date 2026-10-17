# roboolympics-tabletennis-matchlow-i01-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | — (none: a task RoboOlympics exports with its own service, PROTOCOL §4c) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_matchlow` / seed 22 |
| Oracle | `partial` — level 1, the easiest level, the low level (the agent's own hit in the loop, no execution scatter): our toolkit-only reference skill with the camera-only reference strategy lost 0:5 on this seed (twice) and on seeds 2-9 (its slow serves bounce twice on its own court; volleys on the receive), so the oracle is partial. Feasibility: the platform's own hit packaged as an uploadable skill (the same sandbox process) with the truth-state reference strategy wins level 1 in 7 of 8 development seeds of our evaluator's competition test (no wall clock), this seed 5:1, where our reference skill wins 0 of 4; through this task's live upload path with the camera-only strategy it scored 2:5, 1:5, 2:5; the platform's hit meets every development request of the contract (118/118) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 10 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Table tennis against the scripted opponent (level 1), program play, LOW LEVEL (Agent as Robotics Engineer: the agent implements the core skill itself from the robot's joint interface and toolkit and uploads it to the simulator, which plays every stroke with it: the skill in the loop, its compute counted in match time): robot table tennis in a continuous world slowed by a factor S (MuJoCo Franka Panda + paddle on an x-y rail base behind the end line, both held to the real robot's limits: the Panda's joint velocity, acceleration, jerk, torque and torque rate, the rail's speed, acceleration and jerk; DeepMind ball and table model), seen only through two cameras of four frames each; one game to 5 points (lead by 2 from 4:4, at 6:6 the next point wins); the players' robots serve by the ITTF service laws (a toss device on the robot projects the ball at least 16 cm up from a point you choose behind your end line, you strike it as it falls; 2 serves each, from 4:4 one each); format match: you against a scripted opponent (level 1-4; you serve first), format duel: two players.

## Difficulty
Frozen development instance: seed 22, level 1, slowdown S = 10. Not one of
the sport's official (hidden) seeds, so results here are previews, not official RoboOlympics results.

## Reference solution
`solution/`: our camera-only reference player through the same HTTP interface. level 1, the easiest level, the low level (the agent's own hit in the loop, no execution scatter): our toolkit-only reference skill with the camera-only reference strategy lost 0:5 on this seed (twice) and on seeds 2-9 (its slow serves bounce twice on its own court; volleys on the receive), so the oracle is partial. Feasibility: the platform's own hit packaged as an uploadable skill (the same sandbox process) with the truth-state reference strategy wins level 1 in 7 of 8 development seeds of our evaluator's competition test (no wall clock), this seed 5:1, where our reference skill wins 0 of 4; through this task's live upload path with the camera-only strategy it scored 2:5, 1:5, 2:5; the platform's hit meets every development request of the contract (118/118).

## Verification
Separate sandbox, no network. Live grading (owner 2026-10-17, board 0151): the verdict is the sim service's own
record of the live match (`final.json`; `RO_VERDICT_REPLAY` 0, no grading replay, `verdict_replay` = 0 in
reward.json). The verifier (`tests/grade.py`, our core's grader) applies the validity rule (technical failures void
the trial, a player's own problems are a valid loss), and writes reward.json; success = a
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
Source: RoboOlympics task `tabletennis-match-wallclock-program-lowlevel-standard`, revision `wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2`. The rules, the referee, the scripted
opponent, the observation, the review between points and the grader are ours, unchanged; only the seat is
unmetered (Harbor records the model's usage) and the instance is frozen.

### Change Log
- 2026-10-17 (robot_coding_bench review, board 0146): before the first result. (1) The uploaded skill could read the simulator's code (`/srv`, readable by `nobody`: the platform's own stroke planner, the scripted opponent, the referee) and return it to the agent in its load error. The sim's code is now mounted at `/root/rosim` (`/root` is 700) and `/srv` is a link to it, so the skill gets `PermissionError` there, as for `/data`. (2) Live grading: `RO_VERDICT_REPLAY` 0 skips the fresh-process grading replay (`core/service.py` `verdict_replay`); the verdict, valid_trial and the winner are those of the live match, and `tests/grade.py` accepts the live record when `final.json` says `verdict_replay` false. The replay video is still drawn after the verdict, and the verdict never depends on it.
