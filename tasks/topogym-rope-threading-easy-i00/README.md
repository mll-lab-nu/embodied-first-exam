# topogym-rope-threading-easy-i00

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / aloha (two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base) |
| Family / instance | `rope_threading` / variation `rope_threading_easy`, seed 0 (eval index None), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | physical grasping only (no assisted grasping) |
| Success rule | his default success (goal_complete True; terminal revision terminal_v3_default_success) |
| Agent budget | 21600 s |

## Goal
Thread the rope through the cyan ring (R1) then green ring (R2), in that order along the rope from material start to material end.

## Success requirements

- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross away from the side containing the cyan ring (R1). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 1 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Invalid rope volume ends the episode in failure.

## Grader details (in addition to the requirements above)

- Sizes: each ring's inner radius is 69 mm and its tube 12 mm thick (radius 6 mm); the rope's radius is 4 mm. So the rope's centreline must pass less than 64.9 mm from a ring's centre, and the passage is checked on the ring's middle plane and on the planes 6 mm to either side of it.
- The material start is the rope end that is farther from the rings at the start.
- A failure is reported in `s.status()["episode_end"]` as "rope_volume_invalid".

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
