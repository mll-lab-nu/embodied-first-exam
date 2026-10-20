# embodied-olympics-match-tabletennis-match-i01-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-tabletennis-match-i01-standard-realtime` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_match` / seed 22 |
| Oracle | `partial` — full-state reference program (solution/): the camera-only reference player's serve and stroke planner fed the true ball state; its wins on this instance and across levels 1-4 are in the Embodied Olympics privileged report (tools/tt_fullsim/calibrate.py); not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:olympiad-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
Win one complete match against the frozen sport's scripted L2 opponent, seed 22: the same frozen instance as `embodied-olympics-match-tabletennis-match-i01-standard-realtime` (its standard-realtime twin; there you see only camera images).

## Difficulty
Same frozen sport and instance as `embodied-olympics-match-tabletennis-match-i01-standard-realtime`: scripted level 2, seed 22; full-simulator
development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's serve and stroke
planner fed the true ball state).

## Verification
Separate no-network verifier; root-owned trusted source (unreadable to the program), the program as `nobody` with a
public read-only copy of the full simulator (`/opt/dev`), the original core clock at S = 10, one fresh-process journal
replay (the original service's own) that must agree with the live match, then the replay video (`replay.mp4`, after
the verdict). The match ends as in the twin: over, or unfinished at 7200 s. The verdict of this live,
closed-loop match depends on the verifier host's speed, as for the standard-realtime twin: the verifier's CPUs are
pinned (4, minimum = cap). If any process of the program's user survives the end of the match, the trial
is the program's 0 (never a win, never a retry).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 6 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (Embodied Olympics, an RTX 4090 workstation, 2026-10-15): CPU-only MuJoCo 3.3.7, no cameras; one world about 0.4 GB, 470 control steps/s on one core; the verifier holds the service, the policy (2 GiB address space) and two fresh replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 6 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 6 GiB memory. Limits measured: author estimate, not yet measured: 6 GiB under the 8 GiB container cap (2 GiB for the monitor's margin), enough for about ten worlds at once; processes 512 and disk 20 GiB: design defaults.
