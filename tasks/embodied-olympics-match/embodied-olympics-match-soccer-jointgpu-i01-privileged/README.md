# embodied-olympics-match-soccer-jointgpu-i01-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-soccer-jointgpu-i01-standard` |
| Simulator / robot | `mujoco` / `booster-t1` |
| Family / instance | `soccer_jointmatch` / seed 101 (allowed seeds: [101, 1, 2]; PROTOCOL §2) |
| Oracle | `partial` — full-state reference program (solution/): the twin's joint-level oracle controller (joint_oracle.py with its team, walker and DCM modules) fed the true state; oracle runs were waived for the Embodied Olympics - Match twins: untested |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b` |

## Task
The privileged twin of `embodied-olympics-match-soccer-jointgpu-i01-realtime`: humanoid robot soccer 2 v 2 at the JOINT LEVEL (12 leg joint targets per Booster T1 every 20 ms, no walking policy, no kick skill), coach format, against the learned joint-level team (level 5), CPU + GPU resource tier; level 5, seed 101, S = 10.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the twin's joint-level reference team (DCM walker + team strategy) on the formal views).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 10 (the verdict depends on the host's speed, as in the
realtime twin: the verifier runs on 6 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | 12 GiB | 10 GiB |
| verifier | 6 | 12 GiB | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player (H.2).
