# topogym-lock-picking-medium-i00-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-lock-picking-medium-i00-standard` |
| Simulator / robot | `topogym` / `panda_robotiq` |
| Family / instance | `lock_picking` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` |

## Task
TopoGym lock_picking (panda_robotiq, Genesis): produce one replayable trajectory. Insert the tabbed key through all three rotor plates and the final END plate, while respecting their slots and stops. Frozen scene instance (variation lock_picking_medium, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

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
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | his default success (goal_complete True; terminal revision terminal_v4_bore_contact_default_success) |

### Goal
Insert the tabbed key through all three rotor plates and the final END plate, while respecting their slots and stops.

### Success requirements
- Keep the finite-length shaft passing through the full thickness of all four plates at once, facing the insertion direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all four bores. The radial numerical contact tolerance is 0.01 mm; do not push the shaft through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Sizes: bore radius 7.5 mm, shaft radius 6.5 mm. At each of the 8 plate faces (three 10 mm rotor plates and END, 150 mm apart), the shaft axis' distance from the bore axis plus 6.5 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm: about 1.01 mm of offset when the key is straight, which over the stack allows only about 0.25 degrees of tilt.
- The shaft reaches from 515 mm behind the leading tab to 15 mm in front of it; all 8 plate faces must lie within that length.
- Tabs: radius 36 mm, half-width 4 degrees; slots: half-width 8 degrees. A tab that overlaps a plate must sit inside one of that plate's slots with an angular margin of at least asin(axis offset / 36 mm) + the tilt.
- Rotor stops (from each rotor's start angle; "the other way" is the sense that turns rotor 2's slot toward the tabs' starting angle): rotor 1 15 degrees either way; rotor 2 10 degrees one way and 75 degrees the other; rotor 3 turns freely. Going more than 0.5 degrees beyond a stop ends the episode.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "rotor_limit_exceeded" or "Key fell below table".
