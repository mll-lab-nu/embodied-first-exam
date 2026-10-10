# molmospaces-close-i00-standard

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `molmospaces-close-i00-privileged` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `close` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-close-i00-privileged__HWWFXrw (run codex-gpt6_luna-medium, batch molmospaces-luna-1006; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/close/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Standard-mode twin of `molmospaces-close-i00-privileged` (the same frozen MolmoSpaces episode): Close the cabinet. The agent gets only the
`eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`), which owns the episode, serves cameras, proprioception and upstream's kinematic
model, and records every executed row. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, replays the trajectory in two fresh processes and writes `final.json`; the verifier grades those artifacts
in a separate sandbox (`tests/Dockerfile`).

## Difficulty
That of `molmospaces-close-i00-privileged` (its README), without resets, object poses or a success check: every move is planned from camera
images, depth and the robot's own proprioception, within the benchmark's 30 s of simulated time.

## Reference solution
None is shipped (see `molmospaces-close-i00-privileged`).

## Verification
`success` = live success ∧ replay success ∧ deterministic. The episode follows upstream's evaluation: one upstream
`Task.step` per executed row; it ends at upstream's `is_done()` (455 control steps), at the agent's `done`,
or when the agent's time is up; then upstream's `judge_success()` on the final state: the target's joint is open at most 15% of its range (it starts 50% open). The two fresh-process
replays of the recorded rows (`rcb_molmospaces.py replay`) must succeed and end in the same state; `replay.mp4` is
rendered after the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task
and its twin, a positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 6 GB | 5 GB |
| GPU memory | 3.5 GB | 3.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).
- Measured: GPU 2.7 GB on L40S, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory and CPU author estimate (MuJoCo, CPU physics, EGL rendering)

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `ithor/FrankaCloseHardBench/FrankaCloseHardBench_20260206_json_benchmark` (FrankaCloseHardBench: upstream's Hard configuration of Close, not in its evaluation docs), episode 51 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (docs/benchmarks/molmospaces.md) |
| Generator | `scripts/molmospaces/mk_tasks.py`; docs/benchmarks/molmospaces.md |
