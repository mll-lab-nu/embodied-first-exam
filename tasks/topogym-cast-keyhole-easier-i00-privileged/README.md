# topogym-cast-keyhole-easier-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-cast-keyhole-easier-i00-standard` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `cast_keyhole` / seed 0 |
| Oracle | `full` — oracle 1 / nop 0 on this frozen instance; independent replay verified. |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `topogym-local/cast-keyhole-oracle:20261002-02` |

## Task
TopoGym cast_keyhole (aloha, Genesis): produce one replayable trajectory. Separate and place the entire silver keyhole piece inside the green dashed goal region. Keep the gold piece on the puzzle/system side. Frozen scene instance (variation easier, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/oracle_cast_keyhole.py`, written for this instance with the tooling's primitives; `solution/solve.sh` records it into a
trajectory.

## Verification

Qualified on the benchmark host using the pinned local image shown above. The oracle and nop were run separately; oracle execution does not run during model evaluation. The runtime/scoring inputs and private actions below are identical to the tested candidate; only README and oracle metadata were updated for registration. See [qualification evidence](../../runs/test_results/cast_keyhole_oracle_20261002_01/harbor_qualification.json). This records one frozen instance, not arbitrary-seed robustness or pure-friction grasping.

Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the GPU, which is not bit-deterministic: the
final-state hashes (`deterministic`) are diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | his default success (goal_complete True; terminal revision cast_keyhole_placement_v4_grasp_contact_2mm) |

### Goal
Separate and place the entire silver keyhole piece inside the green dashed goal region. Keep the gold piece on the puzzle/system side.

### Success requirements
- Put every part of the entire silver keyhole piece inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 244.54 mm above the tabletop.
- Keep the gold piece, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 252.5 mm x 252.5 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The gold piece is free to move (its speed is not checked), but no point of it may cross that plane.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the 1 mm limit in the same tick.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): keyhole_gold: radius 26 mm; keyhole_silver: radius 22 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "Held finger contact penetration exceeded 2 mm", "Task contact penetration exceeded 1 mm" or "A task body fell below the table".
