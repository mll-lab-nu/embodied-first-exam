# topogym-orbits-medium-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-orbits-medium-i00-standard` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `orbits` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.7-cu128` |

## Task
TopoGym orbits (aloha, Genesis): produce one replayable trajectory. Separate and place the entire cord and wooden handle together inside the green dashed goal region. Keep the rings, posts and fixed assembly on the puzzle/system side. Frozen scene instance (variation orbits_medium, seed 0).

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
| Success rule | his default success (goal_complete True; terminal revision placement_region_v2_default_success) |

### Goal
Separate and place the entire cord and wooden handle together inside the green dashed goal region. Keep the rings, posts and fixed assembly on the puzzle/system side.

### Success requirements
- Put every part of the entire cord and wooden handle together inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 150 mm above the tabletop.
- Keep the rings, posts and fixed assembly, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Every point of the target cord must also move at most 1 mm/s. Holding the target with the gripper is allowed; release is not required.
- Keep the cord intact and attached to both handle attachment points; each attachment residual must be at most 2 mm. No inverted or collapsed cord volume is accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Broken attachments or invalid cord volume end the episode in failure.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 398.0 mm x 398.0 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes; for the cord every vertex of its simulated volume.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The remaining components here are fixed.
- A failure is reported in `s.status()["episode_end"]` as "connection_or_volume_invalid".
