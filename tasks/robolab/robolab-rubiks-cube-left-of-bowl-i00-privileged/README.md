# robolab-rubiks-cube-left-of-bowl-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-rubiks-cube-left-of-bowl-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `rubiks_cube_left_of_bowl` / seed 0 |
| Oracle | `full` — The oracle scored 1 under Harbor -a oracle on this version (2026-10-14: both-finger contact, settle hold): trial robolab-rubiks-cube-left-of-bowl__CbNtCUs (2026-10-14, on these files under a temporary -i01 name: they differ from it only in that name in the resource-limit files and in one comment line of rcb_robolab.py; deterministic 1, instance_exact 1, 183 rows; the success term fires at the same control step as on -i00). Earlier versions: The oracle scored 1 (deterministic, instance_exact) in Harbor runs robolab-rubiks-cube-left-of-bowl__onMcaQH (laptop, job tpl11-0927-1823-oracle-robolab-rubiks-cube-left-of-bowl-i00, at eaf2aff0) and robolab-rubiks-cube-left-of-bowl__tRHn5hq (job tpl19-0927-0430-oracle-robolab-rubiks-cube-left-of-bowl-i00, at fe045825), on a byte-identical tests/grade.py, frozen instance and oracle code (tests/test.sh differs only in the command that empties /logs/verifier before grading: rm -rf, the protocol v1.0 convention); the tooling (rcb_robolab.py) changed since only off the oracle and replay path: eaf2aff0 adds other families' registry entries; b3c7ca89 adds fail-safe 2.2 helpers and was re-checked through the same tooling path (the banana_in_bowl oracle trajectory ends in the same final state sha 61afa384566be3a5 with the old and the new CLI); cde31660 flips the depth default, which run-oracle and replay pass explicitly (depth=False); one docstring line now says standard mode. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.2` |

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
| RoboLab task | `RubiksCubeLeftOfBowlTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); out of it, every Python process pays ~2 min of Isaac Sim launch + scene build (tasks/robolab/README.md) |
| Benchmark notes | tasks/robolab/README.md |
