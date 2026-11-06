# embodied-olympics-match-fencing-bout-i02-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-fencing-bout-i02-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `fencing_bout` / seed 35 |
| Oracle | `full` — full-state reference program (solution/): the twin's reference player (builtin_players.Reference, seed 0) as a program; a local Harbor oracle run won 15:13 (valid, replay identical); the nop (no program) scores 0 |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7` |

## Task
The privileged twin of `embodied-olympics-match-fencing-bout-i02-standard`: robot epee fencing (two Unitree G1 humanoids, one FIE direct-elimination bout fenced
phrase by phrase, nine tactical intentions) against the scripted fencer; level 2, seed 35, a turn sport with a chess
clock of 3600 s.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state (the bout, the scripted
fencer's own state) instead of the observation.

## Reference solution
`solution/solve.sh` submits the reference program: the sport's reference player (builtin_players.Reference, the
twin's oracle; it reads the opponent from the phrases so far).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the twin's own
turn service (`tools/fullsim/turn.py`: the chess clock of the twin, each exchange 5 s), one fresh journal replay, then
the replay video (replay.mp4) from the record.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 2 | 4 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole bout). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal bout is root-only. The public copies hold no reference player (H.2): the scripted fencer is
`sports/fencing/opponent.py`, part of the simulator.
