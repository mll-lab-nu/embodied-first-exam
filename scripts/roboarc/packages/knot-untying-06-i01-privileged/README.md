# topogym-knot-untying-06-i01-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-knot-untying-06-i01-standard` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `knot_untying` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `labv18be/rcb-topogym:0.2.16-dev-cu128` |

## Task
TopoGym knot_untying (aloha, Genesis): produce one replayable trajectory. Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it. One end of every rope is clamped to the table under a staple and stays clamped. Frozen scene instance (variation knot_untying_rd_very_easy, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
None yet (`oracle = "none"`, no `solution/`). A reference solution must be written for this instance (assisted
grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the GPU, which is not bit-deterministic: the
final-state hashes (`deterministic`) are diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).
The replays are grading replays (tooling v18): if this GPU family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; at least one replay must
reach the goal with the instance's own thresholds within the trajectory's rows.

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision terminal_v5_fixed_contact_active_clearance_1mm) |

### Goal
Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it. One end of every rope is clamped to the table under a staple and stays clamped.

### Success requirements
- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope diameter plus 3 mm above it.
- Keep the rope volume intact; do not invert or collapse it to bypass the knot.
- Release all target parts and disengage any assisted grasp. Keep at least 1 mm of verified clearance between the rope and grippers or other robot links that can move. World-fixed bases may touch the rope normally. Interior overlap with any robot part is forbidden; ambiguous bounding-volume overlaps require a native-solid geometry check.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- The rope is a chain of 363 rigid capsule links (4.5 mm long, 8 mm thick) joined end to end; each joint bends and twists against a spring set by the rope's material (Young's modulus 50 kPa), with damping, and stops bending at 0.9 rad, where neighbouring links touch. The links do not deform: nothing about the rope's shape or volume ends the episode. A link moving faster than 2 m/s or spinning faster than 150 rad/s is slowed by extra damping (a speed clamp); this is not reported and does not end the episode. Pulled harder than about 14.9 N, the rope's links get extra rotational inertia (a tension guard), which only removes energy and is not reported.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release check bounds the rope's volume mesh (carried rigidly by its capsule links), element by element, against the robot's collision geometries and decides the close ones with the exact solids: every robot part that can move (grippers, arm links) needs at least 1 mm of clearance from the rope; a world-fixed base may touch it. An overlap with the interior of any robot part means the release is not certified: no success while it lasts, never a failure.
- Grasp regions (assisted grasping, see Grippers above; one or more spheres per graspable part): rope: 363 spheres of radius 8 mm. Both finger contacts must lie inside one of the part's spheres; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the GPU, which is not bit-deterministic, so a replay can differ slightly from your own run: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; during that hold it accepts rope speeds up to 1.25 mm/s instead of 1 mm/s. Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else is relaxed: every other condition, the failure conditions and the confirmation time are the same. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "rope_volume_invalid: <what>" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.
