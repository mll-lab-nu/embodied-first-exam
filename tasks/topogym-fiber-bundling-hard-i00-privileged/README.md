# topogym-fiber-bundling-hard-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-fiber-bundling-hard-i00-standard` |
| Simulator / robot | `topogym` / `panda_robotiq` |
| Family / instance | `fiber_bundling` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` |

## Task
TopoGym fiber_bundling (panda_robotiq, Genesis): produce one replayable trajectory. Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored. Frozen scene instance (variation fiber_bundling_hard, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: physical grasping only (no assisted grasping).

## Reference solution
None yet (`oracle = "none"`, no `solution/`). A reference solution must be written for this instance (assisted
grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the GPU, which is not bit-deterministic: the
final-state hashes (`deterministic`) and the rebuilt frozen scene (`instance_ok`) are reported, not required
(robot_coding_bench's GPU-backend rule).

## Details
| | |
|---|---|
| Grasping | physical grasping only (no assisted grasping) |
| Success rule | his default success (goal_complete True; terminal revision terminal_v4_fiber_ring_plane) |

### Goal
Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored.

### Success requirements
- Pass every fiber tip first, then successive material points through to its root. The actual crossing history must be observed; placing fibers on the far side or passing only the tips is not completion.
- All fiber points must finish beyond the exit side of the ring tube, allowing for fiber thickness. The branching face of the front sheath must also pass through and clear the tube with its full thickness. The fixed rear terminal must remain anchored and does not pass through.
- Keep the angle between every pair of adjacent fiber segments at most 60 degrees in the final configuration.
- Touch and grasp only the thick sheath with the gripper. Keep the completed passage valid through confirmation; holding is allowed, with no separate release or speed threshold.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Any gripper touch of a fine fiber at any time ends the episode in failure, including a brief or zero-force touch.
- A fiber link falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Sizes: ring inner radius 13.5 mm, ring tube radius 4 mm; 16 fibers of radius 1.2 mm; sheath radius 12 mm.
- Each fiber is tracked at 11 points from tip to root. A point counts when it crosses the ring's plane less than 17.48 mm from the ring's axis, in tip-to-root order; a crossing out of order or outside that radius resets that point and every point behind it, and crossing back loses the credit.
- At the end every fiber point must be more than 5.2 mm past the ring's plane (tube + fiber radius) and the centre of the sheath's front face more than 16 mm past it (tube + sheath radius). The exit side is the side opposite to where the fibers start.
- The failure counts contact between a fine fiber and the gripper (fingers and hand, housing included); arm links touching a fiber do not count. Contact is sampled at all 4 solver substeps of every tick; if any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- A failure is reported in `s.status()["episode_end"]` as "fiber_gripper_contact" or "Fiber below table".
