# roboolympics-soccer-match-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-soccer-match-i00-standard-realtime` |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_match` / seed 7 |
| Oracle | `partial` — full-state reference program (solution/): the screening's truth reference (the frozen scripted coach at the reference level: both robots go for the ball, in-walk kick) as a program reading the declared truth; in step timing it reproduces the in-world truth reference bit for bit; its results at levels 2 and 3 and on this instance are in the RoboOlympics privileged report (soccer section); not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b` |

## Task
The privileged twin of `roboolympics-soccer-match-i00-standard-realtime`: robot soccer 2 v 2 (RoboCup Humanoid Soccer League rules, soccer-2v2-10): two simulated Booster T1 humanoids of team A, commanded by one program, against the scripted team B on a boarded 10 x 7 m pitch, two halves of 5 minutes of game time; level 2, seed 7, S = 5.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 5 (the verdict depends on the host's speed, as in the
standard-realtime twin: the verifier runs on 6 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 6 |
| Memory | 8 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle trial (ws-2, 2026-10-17): CPU-only MuJoCo with two Booster T1 humanoids per team; the verifier holds the service, the program, one replay and the video renderer; 6 CPUs pinned (the match runs on the wall clock)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
