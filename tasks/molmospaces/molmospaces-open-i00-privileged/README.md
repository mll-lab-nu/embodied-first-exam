# molmospaces-open-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-open-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `open` / seed 0 |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-open-i00-privileged__bVqNR4u (run codex-gpt6_1_sol-high, batch molmo-harder-sol, 2026-10-16, image 0.2.4, the same instance); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Open the dishwasher. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark`, episode 52:
a hinged door (revolute joint)), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Open an articulated fixture in a hand-built AI2-THOR kitchen: find a handle, grasp or push it and move it along its joint. Any fixture of the named kind counts (at most three joints in all), the fixture starts at least 0.75 m (horizontally) from the robot base, and its moving part has to travel at least 6 cm to count as open. Upstream's Hard configuration: the arm starts in a randomised posture and the robot up to 30° off facing the fixture. 455 control steps (30 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs and the package
registries; the PyPI distribution `molmo-spaces` has those experts, PROTOCOL §5).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 30 s horizon = 455 control steps) or the last row, then upstream's `judge_success()`
on the final state: some joint of any dishwasher in the room is open at least 15% of its range (all start closed). Pass iff the replay succeeds; `replay.mp4` is rendered after
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
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark` (FrankaOpenHardBench: upstream's Hard configuration of Open, not in its evaluation docs), episode 52, house ithor val 14 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Benchmark notes | tasks/molmospaces/README.md |
