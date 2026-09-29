# topogym-blanket-flatten-i00

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / aloha (two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base) |
| Family / instance | `blanket_flatten` / variation `blanket_flatten_easy`, seed 0 (eval index 0), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.1.0` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | physical grasping only (no assisted grasping) |
| Agent budget | 5400 s |

## Goal
Unfold and spread the blanket flat on the table. Remove folds, rolls and self-overlaps so the fabric covers its unfolded footprint without excessive stretching. Release the blanket, withdraw the grippers and let it settle flat and still on the tabletop.

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: physical grasping only (no assisted grasping).

## Reference solution
None yet: `solution/solve.sh` says so and exits 1 (the oracle agent scores 0). A reference solution must be
written for this instance (assisted grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The physics runs on the
GPU, which is not bit-deterministic: the final-state hashes (`deterministic`) and the rebuilt frozen scene
(`instance_ok`) are reported, not required (robot_coding_bench's GPU-backend rule).
