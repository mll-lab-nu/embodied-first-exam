# robolab-rubiks-cube-left-of-bowl-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-rubiks-cube-left-of-bowl-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `rubiks_cube_left_of_bowl` / seed 0 |
| Oracle | `full` — The oracle scored 1 (deterministic, instance_exact) in Harbor runs robolab-rubiks-cube-left-of-bowl__onMcaQH (laptop, job tpl11-0927-1823-oracle-robolab-rubiks-cube-left-of-bowl-i00, at eaf2aff0) and robolab-rubiks-cube-left-of-bowl__tRHn5hq (ws3, job tpl19-0927-0430-oracle-robolab-rubiks-cube-left-of-bowl-i00, at fe045825), on a byte-identical tests/grade.py, frozen instance and oracle code (tests/test.sh differs only in the command that empties /logs/verifier before grading: rm -rf, the protocol v1.0 convention); the tooling (rcb_robolab.py) changed since only off the oracle and replay path: eaf2aff0 adds other families' registry entries; b3c7ca89 adds fail-safe 2.2 helpers and was re-checked through the same tooling path (the banana_in_bowl oracle trajectory ends in the same final state sha 61afa384566be3a5 with the old and the new CLI); cde31660 flips the depth default, which run-oracle and replay pass explicitly (depth=False); one docstring line now says standard mode. |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robolab:0.1.1` |

## Task
Put the rubiks cube to the left of the bowl.

## Difficulty
The second RoboLab task next to `robolab-banana-in-bowl-i00`, chosen to test something different: a **spatial relation** instead of containment. RoboLab's success term is `object_left_of(rubiks_cube, bowl, frame_of_reference="robot", require_gripper_detached=True)`: the horizontal vector from the bowl's pose to the cube's pose, in the robot's base frame, must lie within a 45 deg cone around the robot's +y axis, and the gripper must have let go. There is no distance limit and no support or level check. The scene (bowl, cube, banana on a different table from the banana task, top at z = 0.05 m) starts with the cube to the bowl's right, so the cube has to be carried across, past the bowl. The trap is the cube's reference point: the RoboLab asset puts the cube's origin on one of its faces, ~3 cm from its geometric centre (on the -y face at the reset pose), and both the success check and `s.objects()[...]["position"]` use that origin. A grasp aimed at `position` straddles the cube's edge: one finger lands on the cube's top, the descent stalls 2 cm high and the gripper cannot close (what the first oracle did, three times). The instructions of both modes state where the reference point is.

## Reference solution
`solution/oracle_rubiks_cube_left_of_bowl.py` (RoboLab ships no expert; written for this instance); `solution/solve.sh` records it into a
trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff RoboLab's
`success` term holds in every replay, the final-state hashes agree and the rebuilt frozen scene matches the recorded
one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The trajectory is the per-control-step (T, 8) action record;
with PhysX on the CPU a fresh process reproduces the live run bit for bit (the GPU pipeline does not, which is why
physics is pinned to the CPU); later replays inside one process can differ in the last bits, hence two fresh processes.
RoboLab's success term is instantaneous: it is checked after every control step and the first step where it holds ends
the episode (RoboLab's own termination; the replay stops there), so a goal state that holds at one control step counts.

## Details
| | |
|---|---|
| Simulator | NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the CPU, RTX rendering), Franka Panda + Robotiq 2F-85 (DROID setup) |
| RoboLab task | `RubiksCubeLeftOfBowlTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | 5400 s in both modes: every Python process pays ~2 min of Isaac Sim launch + scene build (docs/benchmarks/robolab.md) |
| Generator | `scripts/robolab/mk_tasks.py` (`scripts/robolab/families.json`, `template/privileged/`, `shared/`); docs/benchmarks/robolab.md |
