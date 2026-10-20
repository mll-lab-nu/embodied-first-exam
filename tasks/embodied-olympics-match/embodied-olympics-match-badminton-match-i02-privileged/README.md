# embodied-olympics-match-badminton-match-i02-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-badminton-match-i02-standard-realtime` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_match` / seed 8 |
| Oracle | `partial` — full-state reference program (solution/): the camera-only reference player's planner fed the true state; its results on this instance and across the levels are in the Embodied Olympics privileged report; not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false) |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:olympiad-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
The privileged twin of `embodied-olympics-match-badminton-match-i02-standard-realtime`: singles badminton on a 0.4-scale court (BWF Laws, one game to 11): Franka Panda with a racket on a gantry base against the scripted opponent; level 2, seed 8, S = 20.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 20 (the verdict depends on the host's speed, as in the
standard-realtime twin: the verifier runs on 4 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 6 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle trials (two RTX 4090 workstations, 2026-10-17): CPU-only MuJoCo, no cameras in the match; the verifier holds the service, the program (2 GiB address space), one replay and the video renderer; 4 CPUs pinned (the match runs on the wall clock)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
