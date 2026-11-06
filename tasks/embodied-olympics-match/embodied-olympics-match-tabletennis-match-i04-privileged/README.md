# embodied-olympics-match-tabletennis-match-i04-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-tabletennis-match-i04-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_match` / seed 34 |
| Oracle | `partial` — full-state reference program (solution/): the camera-only reference player's serve and stroke planner fed the true ball state (the earlier table-tennis twins' smoke controller); a local Harbor oracle run lost 4:6 (valid, replay identical); the nop (no program) scores 0 |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
Win one complete match against the frozen sport's scripted L4 opponent, seed 34: the same frozen instance as `embodied-olympics-match-tabletennis-match-i04-realtime` (its realtime twin; there you see only camera images).

## Difficulty
Same frozen sport and instance as `embodied-olympics-match-tabletennis-match-i04-realtime`: scripted level 4, seed 34; full-simulator
development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's serve and stroke
planner fed the true ball state).

## Verification
Separate no-network verifier; root-owned trusted source (unreadable to the program), the program as `nobody` with a
public read-only copy of the full simulator (`/opt/dev`), the original core clock at S = 10, one fresh-process journal
replay (the original service's own) that must agree with the live match, then the replay video (`replay.mp4`, after
the verdict). The match ends as in the twin: over, or unfinished at 7200 s. The verdict of this live,
closed-loop match depends on the verifier host's speed, as for the realtime twin: the verifier's CPUs are
pinned (4, minimum = cap). If any process of the program's user survives the end of the match, the trial
is the program's 0 (never a win, never a retry).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.
