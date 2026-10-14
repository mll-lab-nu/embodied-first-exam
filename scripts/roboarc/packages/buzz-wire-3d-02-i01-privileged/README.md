# topogym-buzz-wire-3d-02-i01-privileged

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | privileged |
| Twin | `topogym-buzz-wire-3d-02-i01-standard` |
| Simulator / robot | `topogym` / `panda_robotiq` |
| Family / instance | `buzz_wire_3d` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `labv18be/rcb-topogym:0.2.16-dev-cu128` |

## Task
TopoGym buzz_wire_3d (panda_robotiq, Genesis): produce one replayable trajectory. Guide the metal loop along the entire wire from start to finish without touching the wire, then release the tool on the finish support. Frozen scene instance (variation easier, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 1 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
None yet (`oracle = "none"`, no `solution/`). A reference solution must be written for this instance (assisted
grasping, if the family enables it, is the same for the oracle and the agent).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the final-state hashes
(`deterministic`) are still diagnostic, as for the GPU families; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision terminal_v4_traversal_then_deck_release) |

### Goal
Guide the metal loop along the entire wire from start to finish without touching the wire, then release the tool on the finish support.

### Success requirements
- Start within 10 mm along the wire from its starting end and traverse continuously until within 10 mm of its finishing end. Keep one unambiguous wire crossing inside the loop. Skipping branches or taking the loop off the route before completing traversal does not count; restart from the beginning if tracking is lost.
- After completing traversal, lower the tool onto the finish support. The completed traversal remains valid when the loop leaves the wire to rest on the support.
- Match the finish resting pose within 5 mm and 10 degrees. A half-turn about the handle axis is an equivalent orientation. The tool must actually contact the finish support.
- Keep all metal parts of the tool clear of the metal wire throughout the episode. Wooden-handle contact is not a metal-wire failure. Remove all robot contact before final confirmation.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and angular drift at most 0.02 rad.
- Keep all final conditions satisfied together for at least 1 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Any metal-tool touch of the metal wire ends the episode in failure, including brief or zero-force touches.
- The tool falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the whole robot (every link of both arms) and one around each collision geometry of the tool, so the true gap usually has to be larger than 5 mm.
- The loop's usable opening: the wire's centreline must cross the loop's disk less than 12.67 mm from the loop's centre (loop inner radius 14.14 mm minus the 1.47 mm wire radius).
- Continuous traversal: from one physics tick to the next, the crossing point may move along the wire by at most twice the loop's own motion in that tick (its displacement plus 12.67 mm times its rotation angle) plus 3 mm. A larger jump, no crossing, two crossings or a tangency cancels the traversal; it must then start again within 10 mm of the starting end, the end where the tool rests at the start.
- The finish support is the deck, and the finish resting pose is the start resting pose repeated at the wire's finishing end: the tool lies on the deck with its loop at that end of the wire and its handle pointing inward, the way it lies at the start.
- Metal contact is sampled at all 4 solver substeps of every tick. If any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): wand: radius 25 mm, on the wand's grip. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "wire_touched", "Wand fell below table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.
