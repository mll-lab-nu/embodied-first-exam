# robolab-block-stacking-specified-order-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-block-stacking-specified-order-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `block_stacking_specified_order` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-block-stacking-specified__DGoPthS (robolab-block-stacking-specified-order-i00-privileged, run codex-gpt6_luna-xhigh, robolab-lunacx-0925-2038, ws3; https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/unlimited/); robolab-block-stacking-specified__Mvd28Jf (robolab-block-stacking-specified-order-i00-standard, run codex-gpt6_luna-xhigh, robolab-lunaxh-limited-0928, lab; https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/limited/). Human review per family (PROTOCOL §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robolab:0.1.1` |

## Task
Stack the blocks in the order from bottom to top: red, blue, green, yellow.

## Difficulty
RoboLab labels this task "complex" (3 subtasks; attributes: stacking, color); its success term (`stacked`) asks for stack 4 objects (order bottom_to_top). The tooling gives only thin primitives (move_ee on Isaac Lab's differential IK, joint moves, gripper, hold), so every grasp, transport and placement is the agent's to build. RoboLab ships no expert solution.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-block-stacking-specified__DGoPthS` (privileged mode, run `codex-gpt6_luna-xhigh`, batch `robolab-lunacx-0925-2038`, host ws3): [trial log](https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/unlimited/), [replay video](https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/unlimited/replay.mp4)
- `robolab-block-stacking-specified__Mvd28Jf` (standard mode, run `codex-gpt6_luna-xhigh`, batch `robolab-lunaxh-limited-0928`, host lab): [trial log](https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/limited/), [replay video](https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/robolab/codex-gpt6_luna-xhigh/block_stacking_specified_order/limited/replay.mp4)

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff RoboLab's
`success` term holds in every replay, the final-state hashes agree and the rebuilt frozen scene matches the recorded
one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The trajectory is the per-control-step (T, 8) action record;
with PhysX on the CPU a fresh process reproduces the live run bit for bit (the GPU pipeline does not, which is why
physics is pinned to the CPU); later replays inside one process can differ in the last bits, hence two fresh processes.
RoboLab's success term is instantaneous: it is checked after every control step and the first step where it holds ends
the episode (RoboLab's own termination; the replay stops there), so a goal state that holds at one control step counts.

No oracle; human review in PR #3 (PROTOCOL §2.7: per family, this task and its twin, a positive example and the `nop` result).

## Details
| | |
|---|---|
| Simulator | NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the CPU, RTX rendering), Franka Panda + Robotiq 2F-85 (DROID setup) |
| RoboLab task | `BlockStackingSpecifiedOrderTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | 5400 s in both modes: every Python process pays ~2 min of Isaac Sim launch + scene build (docs/benchmarks/robolab.md) |
| Generator | `scripts/robolab/mk_tasks.py` (`scripts/robolab/families.json`, `template/privileged/`, `shared/`); docs/benchmarks/robolab.md |
