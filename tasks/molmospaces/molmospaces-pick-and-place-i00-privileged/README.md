# molmospaces-pick-and-place-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-pick-and-place-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick-and-place` / seed 0 |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1: molmospaces-pick-and-place-i00-p__w3GRFg3 (run codex-gpt6_1_sol-high, batch molmo-v2-sol, 2026-10-16; its verifier's replays ran out of time on a loaded host (the earlier 500 s limit), so it was graded 1 offline with the verifier's replay tool: two fresh replays in the task's image, no time limit, both successes with equal final hashes); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Pick up the purple bottle with white cap and place it in or on the clear ashtray with notches. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-objaverse/FrankaPickandPlaceHardBench/FrankaPickandPlaceHardBench_20260206_json_benchmark`, episode 228:
an Objaverse object), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Pick a named object and set it into or onto a named receptacle in an unseen, cluttered house; at the end the gripper must have let go, the receptacle must carry the object, and the receptacle must not have been knocked away or tipped. The object starts with at least five other objects within 30 cm of it, and at least 25 cm from the receptacle, and shows small in the robot's fixed cameras (at most 630 pixels in the best of them at t = 0). 606 control steps (40 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs and the package
registries; the PyPI distribution `molmo-spaces` has those experts, PROTOCOL §5).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 40 s horizon = 606 control steps) or the last row, then upstream's `judge_success()`
on the final state: the robot does not touch the object; the receptacle supports the object (it carries at least 50% of the object's weight through contact, or the object lies on it by upstream's on-receptacle test, or the object is within 5 mm and 10 degrees, relative to the receptacle, of a pose in which it was supported at an earlier control step); and the receptacle has moved at most 15 cm and tilted at most 60 degrees from its start pose. Pass iff the replay succeeds; `replay.mp4` is rendered after
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
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickandPlaceHardBench/FrankaPickandPlaceHardBench_20260206_json_benchmark` (PnP-v2 (MolmoBot benchmarks)), episode 228, house procthor-objaverse val 2063 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Benchmark notes | tasks/molmospaces/README.md |
