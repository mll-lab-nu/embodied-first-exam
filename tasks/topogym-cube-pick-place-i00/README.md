# topogym-cube-pick-place-i00

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / panda_robotiq (a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base) |
| Family / instance | `cube_pick_place` / variation `base`, seed 0 (eval index 0), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.1.0` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | assisted grasping (contact_weld_v1) |
| Agent budget | 5400 s |

## Goal
Pick up the cube, hold it at least 5 cm above the table for at least 0.2 s, place it back at its original position, open the gripper, withdraw at least 5 cm and let it settle. Merely reaching or closing the gripper is not completion.

## Difficulty
The infrastructure example task (not one of the 13 TopoGym families): one Panda arm with a Robotiq 2F-85 gripper must lift a 4 cm cube at least 5 cm, hold it 0.2 s, put it back within 2 cm of where it started, open, withdraw and let it settle. Assisted grasping holds the cube once both fingers touch it; the Robotiq drive needs about 1.5 s to close and as long to open.

## Reference solution
`solution/oracle_cube_pick_place.py`, written for this instance with the tooling's primitives; `solution/solve.sh` records it into a
trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The physics runs on the
GPU, which is not bit-deterministic: the final-state hashes (`deterministic`) and the rebuilt frozen scene
(`instance_ok`) are reported, not required (robot_coding_bench's GPU-backend rule).
