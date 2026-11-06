# molmospaces-navigate-to-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-navigate-to-i00-standard` |
| Simulator / robot | `molmospaces` / `rainbow-rby1` |
| Family / instance | `navigate-to` / seed 0 |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-navigate-to-i00-priv__YWMd22o (run codex-gpt6_1_sol-high, batch molmo-v2-sol-rby1, 2026-10-16); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Navigate to any tablelamp (2 available). One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `holodeck-objaverse/NavToObjDataGenConfig/NavToObjHolodeckBench_20260115_json_benchmark`, episode 237:
several objects of the target type (the nearest counts)), with a Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera. Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Drive the mobile base through an unseen multi-room house to an object of a named type, ending close to it and facing it so the head camera sees it. The nearest target starts at least 8 m away and out of the head camera's view. 500 control steps (100 s at 5 Hz).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs and the package
registries; the PyPI distribution `molmo-spaces` has those experts, PROTOCOL §5).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 100 s horizon = 500 control steps) or the last row, then upstream's `judge_success()`
on the final state: for the one of the 2 target objects nearest to the robot base (horizontal distance), the horizontal distance from the base to its position (the origin of its body, not its nearest surface) is less than 1.5 m and at least one of its pixels shows in head_camera. Pass iff the replay succeeds; `replay.mp4` is rendered after
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
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `holodeck-objaverse/NavToObjDataGenConfig/NavToObjHolodeckBench_20260115_json_benchmark` (Navigation, Holodeck houses (MolmoSpaces benchmarks; the ProcTHOR-10k package was built on scene version 20251121, 0.2.9 loads 20251217 and its episodes miss objects)), episode 237, house holodeck-objaverse val 1769 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed and its text replaced by upstream NavToObjTask's own description (the package's is wrong), plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Benchmark notes | tasks/molmospaces/README.md |
