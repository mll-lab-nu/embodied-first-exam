# embodied-olympics-match-tabletennisg1-matchgpu-i01-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | privileged |
| Twin | `embodied-olympics-match-tabletennisg1-matchgpu-i01-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `tabletennisg1_match` / seed 4 |
| Oracle | `partial` — the sport's camera-only reference player (solution/program.py: builtin_players:OpenReference in its in-process form, the learned striker of the release on CPU; it ignores the truth) won 5:3 on a Xeon Platinum 8488C (the CPU tier) and lost 6:7 on the GPU tier's EPYC host (the in-process match is replay-identical on one host, not across CPU architectures) (Embodied First Exam's local Harbor runs: see the benchmark README; replay identical); nop 0 |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0@sha256:8bc6d02f91aa5730bbf93bc5c1c4a477feee6f5846ff8c609aaa3a25e0eb36af` |

## Task
Win one complete match against the platform's G1 at level 4 (the BOSS), seed 4: the same frozen instance as
`embodied-olympics-match-tabletennisg1-matchgpu-i01-standard-realtime` and its standard twin, with the full simulator in development and the full state (the ball's true state, both
robots) in every view. The benchmark README (G1 table tennis) has the port and the oracle runs.

## Difficulty
Level 4, seed 4, the release's frozen instance; the opponent reads the ball's true state, and so does the program.

## Reference solution
`solution/solve.sh` submits `solution/program.py`: the sport's camera-only reference player in its in-process form
(it ignores the truth); it won 5:3 on a Xeon Platinum 8488C (the CPU tier) and lost 6:7 on the GPU tier's EPYC host (the in-process match is replay-identical on one host, not across CPU architectures) (the world waits for it at every step, which its twins' world does not).

## Verification
Separate no-network verifier (`tests/formal.py`): the program as `nobody` in its own process against a fresh,
unmodified match on the trusted simulator (root only) with the sport's in-process runner (`core/local.py`: the world
waits for each answer, 0.5 s per call, 1800 s of program time in all); the core's fresh-process replay of the episode
must agree; then the replay video (after the verdict). A process of the program's user left after the match: its 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 2048 | 20 GiB | 10 GiB |
| verifier | 12 | 16 GiB | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB.
