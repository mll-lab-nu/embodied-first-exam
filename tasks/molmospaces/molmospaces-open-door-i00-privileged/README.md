# molmospaces-open-door-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-open-door-i00-standard` |
| Simulator / robot | `molmospaces` / `rainbow-rby1` |
| Family / instance | `open-door` / seed 0 |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-open-door-i00-privil__EJchtFe (run codex-gpt6_1_sol-high, batch molmo-v2-sol-rby1, 2026-10-16); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Pull the door open. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-10k/rby1_benchmarks/door_opening_benchmark`, episode 0:
a door to pull), with a Rainbow Robotics RB-Y1 mobile manipulator (upstream's RBY1M configuration): holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera. Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Open a closed room door with the mobile manipulator: base and arms have to move together to swing it past two thirds of its range, pushing or pulling as the door opens. 400 control steps (40 s at 10 Hz).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs and the package
registries; the PyPI distribution `molmo-spaces` has those experts, PROTOCOL §5).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 40 s horizon = 400 control steps) or the last row, then upstream's `judge_success()`
on the final state: the door's hinge is open at least 67% of its 90-degree range. Pass iff the replay succeeds; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #276 (PROTOCOL §4: per family, this task and its twin, a
positive example and the `nop` result).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 7 | 20 GiB | 2048 | 7 GiB | 10 GiB |
| verifier | 4 | 16 GiB | no cap | 7 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `procthor-10k/rby1_benchmarks/door_opening_benchmark` (Door Open (MolmoSpaces benchmarks)), episode 0, house procthor-10k val 0 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Benchmark notes | tasks/molmospaces/README.md |
