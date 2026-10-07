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

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `procthor-10k/rby1_benchmarks/door_opening_benchmark` (Door Open (MolmoSpaces benchmarks)), episode 0 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (docs/benchmarks/molmospaces.md) |
| Generator | `scripts/molmospaces/mk_tasks.py`; docs/benchmarks/molmospaces.md |
