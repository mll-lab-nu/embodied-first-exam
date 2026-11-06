# embodied-olympics-match-badminton-match-i04-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-badminton-match-i04-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_match` / seed 1034 |
| Oracle | `partial` — full-state reference program (solution/): the camera-only reference player (builtin_players.Reference) with the shuttle's true state in place of the cameras; the twin's opponent is the top tier (level 5), which the camera-only reference rarely beats; a local Harbor oracle run lost 2:11 (valid, replay identical); the nop (no program) scores 0 |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
The privileged twin of `embodied-olympics-match-badminton-match-i04-realtime`: singles badminton on a 0.4-scale court (BWF Laws, one game to 11): Franka Panda with a racket on a gantry base against the scripted opponent; level 5, seed 1034, S = 20.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 20 (the verdict depends on the host's speed, as in the
realtime twin: the verifier runs on 4 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 8 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
