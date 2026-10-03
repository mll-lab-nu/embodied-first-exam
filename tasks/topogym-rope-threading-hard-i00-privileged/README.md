# topogym-rope-threading-hard-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-rope-threading-hard-i00-standard` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `rope_threading` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.10-cu128` |

## Task
TopoGym rope_threading (aloha, Genesis): produce one replayable trajectory. Thread the rope through the cyan ring (R1) then green ring (R2) then purple ring (R3), in that order along the rope from material start to material end. Frozen scene instance (variation rope_threading_hard, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: physical grasping only (no assisted grasping).

## Reference solution
None yet (`oracle = "none"`, no `solution/`). A reference solution must be written for this instance (assisted
grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the GPU, which is not bit-deterministic: the
final-state hashes (`deterministic`) are diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).

## Details
| | |
|---|---|
| Grasping | physical grasping only (no assisted grasping) |
| Success rule | his default success (goal_complete True; terminal revision terminal_v3_default_success) |

### Goal
Thread the rope through the cyan ring (R1) then green ring (R2) then purple ring (R3), in that order along the rope from material start to material end.

### Success requirements
- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross toward the side containing the purple ring (R3); purple ring (R3): cross away from the side containing the green ring (R2). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 1 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- Sizes: each ring's inner radius is 50 mm and its tube 12 mm thick (radius 6 mm); the rope's radius is 4 mm. So the rope's centreline must pass less than 45.9 mm from a ring's centre, and the passage is checked on the ring's middle plane and on the planes 6 mm to either side of it.
- The material start is the rope end that is farther from the rings at the start.
- A failure is reported in `s.status()["episode_end"]` as "rope_volume_invalid".
