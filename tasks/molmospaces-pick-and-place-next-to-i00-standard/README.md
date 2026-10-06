# molmospaces-pick-and-place-next-to-i00-standard

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `molmospaces-pick-and-place-next-to-i00-privileged` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick-and-place-next-to` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-pick-and-place-next__g7CLYbk (run codex-gpt6_luna-medium, batch molmospaces-luna-1006c; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/pick_and_place_next_to/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Standard-mode twin of `molmospaces-pick-and-place-next-to-i00-privileged` (the same frozen MolmoSpaces episode): Pick up the red tdk vhs tape and place it next to the soap bottle. The agent gets only the
`eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`), which owns the episode, serves cameras, proprioception and upstream's kinematic
model, and records every executed row. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, replays the trajectory in two fresh processes and writes `final.json`; the verifier grades those artifacts
in a separate sandbox (`tests/Dockerfile`).

## Difficulty
That of `molmospaces-pick-and-place-next-to-i00-privileged` (its README), without resets, object poses or a success check: every move is planned from camera
images, depth and the robot's own proprioception, within the benchmark's 30 s of simulated time.

## Reference solution
None is shipped (see `molmospaces-pick-and-place-next-to-i00-privileged`).

## Verification
`success` = live success ∧ replay success ∧ deterministic. The episode follows upstream's evaluation: one upstream
`Task.step` per executed row; it ends at upstream's `is_done()` (455 control steps), at the agent's `done`,
or when the agent's time is up; then upstream's `judge_success()` on the final state: the horizontal gap between the two objects' axis-aligned bounding boxes is between 0 and 6 cm; both rest on the same supporting body; and the reference object has moved at most 15 cm and rotated at most 60 degrees from its start pose. The two fresh-process
replays of the recorded rows (`rcb_molmospaces.py replay`) must succeed and end in the same state; `replay.mp4` is
rendered after the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task
and its twin, a positive example and the `nop` result).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickandPlaceNextToHardBench/FrankaPickandPlaceNextToHardBench_20260305_json_benchmark` (PnP-next-to-v2 (MolmoBot benchmarks)), episode 89 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (docs/benchmarks/molmospaces.md) |
| Generator | `scripts/molmospaces/mk_tasks.py`; docs/benchmarks/molmospaces.md |
