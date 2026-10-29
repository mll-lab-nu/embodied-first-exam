# humanclaw-sit-bed-i177-privileged

| | |
|---|---|
| Benchmark | HumanCLAW |
| Mode | privileged |
| Twin | `humanclaw-sit-bed-i177-standard` |
| Simulator / robot | `humanclaw` / `smplx-human` |
| Family / instance | `sit-bed` / seed 0 |
| Oracle | `none` — none: no reference solution searched for this episode yet (the navmesh oracle ran on 120 of the 1,218 canonical episodes); human review (PROTOCOL §4) |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:humanclaw-0.1.0` |

## Task
HumanCLAW find-navigate-interact (bed), privileged mode: one frozen episode,
delivered as one trajectory of at most 100 motion skills. Find the bed and move until your body is touching the target, with zero distance to the target object. Finally, sit on the bed. Modes, rules and what differs from
HumanCLAW's own evaluator: `tasks/humanclaw/README.md`.

## Difficulty
One of the other canonical episodes, not chosen by calibration (`tasks/humanclaw/README.md`, Selection).

## Reference solution
None: the navmesh oracle found no solution for this episode (`tasks/humanclaw/README.md`, Reference solution).

## Verification
`tests/grade.py`: two fresh-process replays of `/app/output/trajectory.npz` from `tests/instance.json`; success =
both meet HumanCLAW's InteractSR and end in the same state hash. `nop` (no file) scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 6 | 8 GiB | 1024 | 8 GiB | 10 GiB |
| verifier | 8 | 5 GiB | 1024 | 8 GiB | 10 GiB |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: an NVIDIA GPU of compute capability 8.0-9.0 with EGL (RTX 4090 / L40S / L4).
