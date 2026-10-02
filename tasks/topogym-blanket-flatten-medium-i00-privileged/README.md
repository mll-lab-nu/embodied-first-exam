# topogym-blanket-flatten-medium-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-blanket-flatten-medium-i00-standard` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `blanket_flatten` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.7-cu128` |

## Task
TopoGym blanket_flatten (aloha, Genesis): produce one replayable trajectory. Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw. Frozen scene instance (variation blanket_flatten_medium, seed 0).

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
| Success rule | his default success (goal_complete True; terminal revision release_settling_v1) |

### Goal
Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw.

### Success requirements
- Cover at least 90% of the blanket's unfolded material area in top-down projection. Overlapping layers count only once, holes do not count, and a large outer bounding box is insufficient.
- Keep every cloth point at most 30 mm above the tabletop and no more than 8 mm below it.
- No material edge may stretch beyond 1.15 times its original length. Raised corners or pulling the blanket taut in the air do not count.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement from the start of confirmation at most 3 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- The blanket is 0.6 m x 0.48 m (0.288 m^2), so the coverage needs at least 0.2592 m^2 of its area in the top view. Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- A failure is reported in `s.status()["episode_end"]` as "Cloth fell below the table".
