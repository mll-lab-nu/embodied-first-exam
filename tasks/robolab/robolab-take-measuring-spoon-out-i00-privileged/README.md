# robolab-take-measuring-spoon-out-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-take-measuring-spoon-out-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `take_measuring_spoon_out` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-take-measuring-spoon-out__vK2T2MY (robolab-take-measuring-spoon-out-i00-privileged, an earlier version of the task, run codex-gpt6_luna-xhigh, robolab-lunacx-0925-2038); robolab-take-measuring-spoon-out__3KikKcU (robolab-take-measuring-spoon-out-i00-standard, an earlier version of the task, run codex-gpt6_luna-xhigh, robolab-lunaxh-limited-0928). Re-graded with the current term (one fresh process per trajectory and tooling version): the cited robolab-take-measuring-spoon-out__vK2T2MY passes the current term too (success at control step 131 instead of 130: the spoon released by both fingers and supported by the table). Human review per family (PROTOCOL §4). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.2` |

## Task
Take the white colored measuring spoon out of the red bowl and put it on the table.

## Difficulty
RoboLab labels this task "simple" (1 subtasks; attributes: semantics); its success term (`object_outside_of`) asks for the measuring spoon taken out of the red bowl. The tooling gives only thin primitives (move_ee on Isaac Lab's differential IK, joint moves, gripper, hold), so every grasp, transport and placement is the agent's to build. RoboLab ships no expert solution.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-take-measuring-spoon-out__vK2T2MY` (privileged mode, on an earlier version of this task; run `codex-gpt6_luna-xhigh`, batch `robolab-lunacx-0925-2038`)
- `robolab-take-measuring-spoon-out__3KikKcU` (standard mode, on an earlier version of this task; run `codex-gpt6_luna-xhigh`, batch `robolab-lunaxh-limited-0928`)

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process; pass iff RoboLab's
`success` term holds in the replay and the rebuilt frozen scene matches the recorded
one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The trajectory is the per-control-step (T, 8) action record;
with PhysX on the CPU a fresh process reproduces the live run bit for bit (the GPU pipeline does not, which is why
physics is pinned to the CPU); later replays inside one process can differ in the last bits, hence a fresh process.
RoboLab's success term is instantaneous: it is checked after every control step and the first step where it holds ends
the episode (RoboLab's own termination; the replay stops there), so a goal state that holds at one control step counts.

No oracle; human review in PR #3 (PROTOCOL §4: per family, this task and its twin, a positive example and the `nop` result).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 4096 | 22 GiB | 10 GiB |
| verifier | 8 | 32 GiB | no cap | 22 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Simulator | NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the CPU, RTX rendering), Franka Panda + Robotiq 2F-85 (DROID setup) |
| RoboLab task | `TakeMeasuringSpoonOutTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); out of it, every Python process pays ~2 min of Isaac Sim launch + scene build (tasks/robolab/README.md) |
| Benchmark notes | tasks/robolab/README.md |
