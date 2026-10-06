# molmospaces-pick-and-place-color-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-pick-and-place-color-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick-and-place-color` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-pick-and-place-color__3KgL4cb (run codex-gpt6_luna-medium, batch molmospaces-luna-1006b; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/pick_and_place_color/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Pick up the metal stopwatch with buttons and place it in or on the red bowl. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-objaverse/FrankaPickandPlaceColorHardBench/FrankaPickandPlaceColorHardBench_20260304_json_benchmark`, episode 26:
an Objaverse object), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Pick-and-place where the receptacles look alike and only their colour tells them apart: the object has to end up in the one of the named colour. The object starts with at least five other objects within 30 cm of it. 606 control steps (40 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs only).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 40 s horizon = 606 control steps) or the last row, then upstream's `judge_success()`
on the final state: the rule of pick-and-place, for the receptacle of the named colour (the other, differently coloured receptacle does not count): the robot does not touch the object; that receptacle supports the object (at least 50% of its weight through contact, or upstream's on-receptacle test, or within 5 mm and 10 degrees, relative to the receptacle, of a pose in which it was supported at an earlier control step); and that receptacle has moved at most 15 cm and tilted at most 60 degrees. Pass iff both replays succeed and end in the same state; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task and its twin, a
positive example and the `nop` result).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickandPlaceColorHardBench/FrankaPickandPlaceColorHardBench_20260304_json_benchmark` (PnP-color-v2 (MolmoBot benchmarks)), episode 26, house procthor-objaverse val 1085 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Generator | `scripts/molmospaces/mk_tasks.py` (`families.json`, `instances/`, `template/`, `shared/`); docs/benchmarks/molmospaces.md |
