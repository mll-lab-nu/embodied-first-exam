# humanclaw-nav-tv-i66-privileged

| | |
|---|---|
| Benchmark | HumanCLAW |
| Mode | privileged |
| Twin | `humanclaw-nav-tv-i66-standard` |
| Simulator / robot | `humanclaw` / `smplx-human` |
| Family / instance | `nav-tv` / seed 0 |
| Oracle | `full` — navmesh oracle (privileged tools, closed loop, on L40S): 21 actions; two fresh-process replays on L40S succeed with equal final hashes (ad082ae9e8aa0174) from the start hash 7547917900a860a3; not replayed on another GPU model; image humanclaw-0.1.0, 2026-10-29 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:humanclaw-0.1.0` |

## Task
HumanCLAW find-navigate (TV), privileged mode: one frozen episode,
delivered as one trajectory of at most 100 motion skills. Find the TV and move until your body is touching the target, with zero distance to the target object. Modes, rules and what differs from
HumanCLAW's own evaluator: `tasks/humanclaw/README.md`.

## Difficulty
One of the other canonical episodes, not chosen by calibration (`tasks/humanclaw/README.md`, Selection).

## Reference solution
`solution/actions.json`: the navmesh oracle's 21 actions, replayed by `solution/solve.sh`; where they do not succeed on the GPU at hand it runs the oracle again closed loop (`solution/oracle.py`).

## Verification
`tests/grade.py`: two fresh-process replays of `/app/output/trajectory.npz` from `tests/instance.json`; success =
both meet HumanCLAW's NavSR@20cm and end in the same state hash. `nop` (no file) scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 6 | 8 GiB | 1024 | 8 GiB | 10 GiB |
| verifier | 8 | 5 GiB | 1024 | 8 GiB | 10 GiB |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: an NVIDIA GPU of compute capability 8.0-9.0 with EGL (RTX 4090 / L40S / L4).
