# kinder-dynamo-i00-privileged

| | |
|---|---|
| Benchmark | KinDER |
| Mode | privileged |
| Twin | `kinder-dynamo-i00-standard` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `dynamo` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
KinDER `kinder/Dynamo3D-o3-v0` (Dynamic3D, TidyBot++), seed 0, privileged mode: the agent has the simulator and its state and
hands in one trajectory, replayed open-loop in a fresh process. Its standard-mode twin is `kinder-dynamo-i00-standard`.

Task: drive the robot into the translucent green square marked on the floor; three chairs stand in the way and can be pushed. The task succeeds the moment the centre of the robot's base is inside the square. (The red, blue and yellow squares only mark where the chairs started.)

## Difficulty
Nonprehensile: three chairs stand between the robot and the floor square, and the base can push them. The benchmark's fixture: the pipeline check, with an oracle in both modes.

## Reference solution
`solution/oracle.py` steers the base from the state around the chairs' north side (three waypoints, every move inside a 0.1 m disc) into the square: success at step 101.

## Verification
One open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, in a container of
its own (`tests/Dockerfile`, no network): pass iff it reaches the goal within 1000 control steps. The oracle (`solution/solve.sh`) scores 1; `nop` scores 0.

Benchmark notes: `tasks/kinder/README.md`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 7 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.
