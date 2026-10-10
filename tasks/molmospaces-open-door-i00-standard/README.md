# molmospaces-open-door-i00-standard

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `molmospaces-open-door-i00-privileged` |
| Simulator / robot | `molmospaces` / `rainbow-rby1` |
| Family / instance | `open-door` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-open-door-i00-privil__iroCZzB (run codex-gpt6_luna-medium, batch molmospaces-luna-1006; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/open_door/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Standard-mode twin of `molmospaces-open-door-i00-privileged` (the same frozen MolmoSpaces episode): Pull the door open. The agent gets only the
`eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`), which owns the episode, serves cameras, proprioception and upstream's kinematic
model, and records every executed row. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, replays the trajectory in two fresh processes and writes `final.json`; the verifier grades those artifacts
in a separate sandbox (`tests/Dockerfile`).

## Difficulty
That of `molmospaces-open-door-i00-privileged` (its README), without resets, object poses or a success check: every move is planned from camera
images, depth and the robot's own proprioception, within the benchmark's 40 s of simulated time.

## Reference solution
None is shipped (see `molmospaces-open-door-i00-privileged`).

## Verification
`success` = live success ∧ replay success ∧ deterministic. The episode follows upstream's evaluation: one upstream
`Task.step` per executed row; it ends at upstream's `is_done()` (400 control steps), at the agent's `done`,
or when the agent's time is up; then upstream's `judge_success()` on the final state: the door's hinge is open at least 67% of its 90-degree range. The two fresh-process
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
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 18 GiB memory. Limits measured: GPU: 2.7 GiB on a 48 GB card (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)); one trial on a 24 GB card peaked at 18.4 GiB and would exceed: calibrate -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 10 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `procthor-10k/rby1_benchmarks/door_opening_benchmark` (Door Open (MolmoSpaces benchmarks)), episode 0 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (docs/benchmarks/molmospaces.md) |
| Generator | `scripts/molmospaces/mk_tasks.py`; docs/benchmarks/molmospaces.md |
