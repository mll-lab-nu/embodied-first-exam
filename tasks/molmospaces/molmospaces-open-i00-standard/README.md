# molmospaces-open-i00-standard

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `molmospaces-open-i00-privileged` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `open` / seed 0 |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-open-i00-privileged__bVqNR4u (run codex-gpt6_1_sol-high, batch molmo-harder-sol, 2026-10-16, image 0.2.4, the same instance); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Standard-mode twin of `molmospaces-open-i00-privileged` (the same frozen MolmoSpaces episode): Open the dishwasher. The agent gets only the
`eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`), which owns the episode, serves cameras, proprioception and upstream's kinematic
model, and records every executed row. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit and writes `final.json` from the live episode's result (nothing is replayed to grade it), then renders
`replay.mp4`; the verifier grades those artifacts in a separate sandbox (`tests/Dockerfile`).

## Difficulty
That of `molmospaces-open-i00-privileged` (its README), without resets, object poses or a success check: every move is planned from camera
images, depth and the robot's own proprioception, within the benchmark's 30 s of simulated time.

## Reference solution
None is shipped (see `molmospaces-open-i00-privileged`).

## Verification
`success` = the live episode's success, judged by the sim service (graded live, no replay). The episode
follows upstream's evaluation: one upstream `Task.step` per executed row; it ends at upstream's `is_done()`
(455 control steps), at the agent's `done`, or when the agent's time is up; then upstream's
`judge_success()` on the final state: some joint of any dishwasher in the room is open at least 15% of its range (all start closed). The service checks the frozen start (the instance's t = 0 state hash)
when it builds the scene, before the agent is served. `replay.mp4` is rendered by one video-only pass from
`trajectory.npz` after the verdict, which it never changes. `infra_error = 1` (no verdict on the agent): no, an
unreadable or an unfinished `final.json`, a service that gave up after crashes between calls or never ended the
episode, a frozen start the image no longer builds (`instance_mismatch`). No oracle; human review in PR #276 (PROTOCOL §4: per family, this task
and its twin, a positive example and the `nop` result).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 12 GiB |
| `sim` | 2 | 10 GiB | 1024 | 5 GiB | — |
| verifier (as `main`) | 3 | 4 GiB | no cap | no GPU | 12 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark` (FrankaOpenHardBench: upstream's Hard configuration of Open, not in its evaluation docs), episode 52 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (tasks/molmospaces/README.md) |
| Benchmark notes | tasks/molmospaces/README.md |
