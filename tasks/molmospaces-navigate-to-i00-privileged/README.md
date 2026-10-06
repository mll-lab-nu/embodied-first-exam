# molmospaces-navigate-to-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-navigate-to-i00-standard` |
| Simulator / robot | `molmospaces` / `rainbow-rby1` |
| Family / instance | `navigate-to` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-navigate-to-i00-priv__mENe7qn (run codex-gpt6_luna-medium, batch molmospaces-luna-1006b; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/navigate_to/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Navigate to any tablelamp (2 available). One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `holodeck-objaverse/NavToObjDataGenConfig/NavToObjHolodeckBench_20260115_json_benchmark`, episode 237:
several objects of the target type (the nearest counts)), with a Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera. Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Drive the mobile base through an unseen multi-room house to an object of a named type, ending close to it and facing it so the head camera sees it. The nearest target starts at least 8 m away and out of the head camera's view. 500 control steps (100 s at 5 Hz).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs only).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 100 s horizon = 500 control steps) or the last row, then upstream's `judge_success()`
on the final state: for the one of the 2 target objects nearest to the robot base (horizontal distance), the horizontal distance from the base to its position (the origin of its body, not its nearest surface) is less than 1.5 m and at least one of its pixels shows in head_camera. Pass iff both replays succeed and end in the same state; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task and its twin, a
positive example and the `nop` result).

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `holodeck-objaverse/NavToObjDataGenConfig/NavToObjHolodeckBench_20260115_json_benchmark` (Navigation, Holodeck houses (MolmoSpaces benchmarks; the ProcTHOR-10k package was built on scene version 20251121, 0.2.9 loads 20251217 and its episodes miss objects)), episode 237, house holodeck-objaverse val 1769 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed and its text replaced by upstream NavToObjTask's own description (the package's is wrong), plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Generator | `scripts/molmospaces/mk_tasks.py` (`families.json`, `instances/`, `template/`, `shared/`); docs/benchmarks/molmospaces.md |
