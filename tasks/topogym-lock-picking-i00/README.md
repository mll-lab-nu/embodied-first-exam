# topogym-lock-picking-i00

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / panda_robotiq (a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base) |
| Family / instance | `lock_picking` / variation `lock_picking_medium`, seed 0 (eval index 0), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.1.0` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | physical grasping only (no assisted grasping) |
| Agent budget | 5400 s |

## Goal
Insert the tabbed key through the lock plates. Rotate and translate the key to negotiate the rotor slots until its leading tab clears the final plate and the shaft reaches the insertion goal. Keep the key aligned with the bores; the rotor pins must remain constrained by their physical slots. Do not force the key or tabs through solid plates. Hold the completed configuration still.

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: physical grasping only (no assisted grasping).

## Reference solution
None yet: `solution/solve.sh` says so and exits 1 (the oracle agent scores 0). A reference solution must be
written for this instance (assisted grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The physics runs on the
GPU, which is not bit-deterministic: the final-state hashes (`deterministic`) and the rebuilt frozen scene
(`instance_ok`) are reported, not required (robot_coding_bench's GPU-backend rule).
