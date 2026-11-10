# embodied-olympics-match-tabletennis-matchlow-i01-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-tabletennis-matchlow-i01-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_matchlow` / seed 22 (allowed seeds: [22, 101, 111]; PROTOCOL §2) |
| Oracle | `partial` — full-state reference program (solution/): the twin's toolkit reference skill (SkillReference, each hit lowered in process by the twin's hit.py) with the true ball state in place of the cameras; a local Harbor oracle run lost 0:5 (valid, replay identical); the twin's toolkit-only reference loses 0:5 too; the nop (no program) scores 0 |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
The privileged twin of `embodied-olympics-match-tabletennis-matchlow-i01-realtime`: table tennis (ITTF, one game to 5) at the LOW level: a Franka Panda with a paddle on an x-y rail base, driven by your own joint-level commands (no hit skill), against the scripted opponent; level 1, seed 22, S = 10.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the table-tennis reference strategy with the ball's true state, each stroke lowered to joint-level rows by the twin's toolkit-only reference skill (solution/hit.py)).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = 10 (the verdict depends on the host's speed, as in the
realtime twin: the verifier runs on 4 pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player (H.2).
