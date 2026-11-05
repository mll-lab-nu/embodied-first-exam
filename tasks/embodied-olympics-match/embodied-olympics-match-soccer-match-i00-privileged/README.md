# embodied-olympics-match-soccer-match-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-soccer-match-i00-realtime` |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_match` / seed 7 |
| Oracle | `partial` — full-state reference program (solution/): the screening's truth reference (the frozen scripted coach at the reference level: both robots go for the ball, in-walk kick) as a program reading the declared truth; in step timing it reproduces the in-world truth reference bit for bit; its results at levels 2 and 3 and on this instance are in the Embodied Olympics privileged report (soccer section); not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b` |

## Task
The privileged twin of `embodied-olympics-match-soccer-match-i00-realtime`: robot soccer 2 v 2 (RoboCup Humanoid Soccer League rules, soccer-2v2-10): two simulated Booster T1 humanoids of team A, commanded by one program, against the scripted team B on a boarded 10 x 7 m pitch, two halves of 5 minutes of game time; level 2, seed 7, S = 5.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 5 (the verdict depends on the host's speed, as in the
realtime twin: the verifier runs on 6 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 6 | 9 GiB | 1024 | no GPU | 10 GiB |
| verifier | 6 | 10 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
