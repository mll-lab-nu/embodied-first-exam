# molmospaces-open-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-open-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `open` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-open-i01-privileged__hkZsZtE (run codex-gpt6_luna-medium, batch molmospaces-luna-v3 of 2026-10-03: an earlier round on the same episode, kept with the run's records, not on the results site); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Open the cabinet. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark`, episode 49:
a hinged door (revolute joint)), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Open an articulated fixture in a hand-built AI2-THOR kitchen: find a handle, grasp or push it and move it along its joint. Any fixture of the named kind counts. Upstream's Hard configuration: the arm starts in a randomised posture and the robot up to 30° off facing the fixture. 455 control steps (30 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs only).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 30 s horizon = 455 control steps) or the last row, then upstream's `judge_success()`
on the final state: some joint of any cabinet in the room is open at least 15% of its range (all start closed). Pass iff both replays succeed and end in the same state; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task and its twin, a
positive example and the `nop` result).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark` (FrankaOpenHardBench: upstream's Hard configuration of Open, not in its evaluation docs), episode 49, house ithor val 14 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Generator | `scripts/molmospaces/mk_tasks.py` (`families.json`, `instances/`, `template/`, `shared/`); docs/benchmarks/molmospaces.md |
