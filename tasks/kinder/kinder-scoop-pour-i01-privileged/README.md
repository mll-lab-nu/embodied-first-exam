# kinder-scoop-pour-i01-privileged

| | |
|---|---|
| Benchmark | KinDER |
| Mode | privileged |
| Twin | `kinder-scoop-pour-i01-standard` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `scoop-pour` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `none` — none yet: no positive example is known for this instance (human review pending) |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
KinDER `kinder/ScoopPour3D-o50-v0` (Dynamic3D, TidyBot++), seed 0, privileged mode: the agent has the simulator and its state and
hands in one trajectory, replayed open-loop in a fresh process. Its standard-mode twin is `kinder-scoop-pour-i01-standard`.

Task: move all 50 small dark-red cubes from the yellow bin into the green bin; a scoop is in the scene. The task succeeds the moment every cube's centre is inside the green bin, at least 1 cm from each of its inner walls and at least 0.5 cm below its rim.

## Difficulty
Nonprehensile, tool use, dynamics: move 50 small cubes from one bin to another with a scoop, each ending well inside the target bin. The variant is upstream's o50 (both cube families use theirs, tasks/kinder/README.md).

## Reference solution
None, and no positive example yet: the task is unvalidated (`validated = false`, docs/protocol/README.md §2, §4) until a human review records one.

## Verification
One open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, in a container of
its own (`tests/Dockerfile`, no network): pass iff it reaches the goal within 1000 control steps. No oracle; no positive example yet (human review pending). `nop` scores 0.

Benchmark notes: `tasks/kinder/README.md`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 7 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.
