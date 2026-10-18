# topogym-buzz-wire-3d-07-i01-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.3`) |
| Twin | `topogym-buzz-wire-3d-07-i01-privileged` |
| Simulator / robot | `topogym` / `panda_robotiq` |
| Family / instance | `buzz_wire_3d` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `labv18be/rcb-topogym:0.2.16-dev-cu128` |

## Task
Standard-mode twin of `topogym-buzz-wire-3d-07-i01-privileged` (same frozen instance): the agent gets only the `eai-standard/2.3` client
(docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 8) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-buzz-wire-3d-07-i01-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Guide the metal loop along the entire wire from start to finish without touching the wire, then release the tool on the finish support. Black rubber sleeves on the wire are insulated: the ring may rest on them. The final bend and the post at the finish are insulated as well.

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
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (reported in clipped[]).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the whole robot (every link of both arms) and one around each collision geometry of the tool, so the true gap usually has to be larger than 5 mm.
- The loop's usable opening: the wire's centreline must cross the loop's disk less than 12.67 mm from the loop's centre (loop inner radius 14.14 mm minus the 1.47 mm wire radius).
- Continuous traversal: from one physics tick to the next, the crossing point may move along the wire by at most twice the loop's own motion in that tick (its displacement plus 12.67 mm times its rotation angle) plus 3 mm. A larger jump, no crossing, two crossings or a tangency cancels the traversal; it must then start again within 10 mm of the starting end, the end where the tool rests at the start.
- The finish support is the deck, and the finish resting pose is the start resting pose repeated at the wire's finishing end: the tool lies on the deck with its loop at that end of the wire and its handle pointing inward, the way it lies at the start.
- Metal contact is sampled at all 4 solver substeps of every tick. If any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): wand: radius 25 mm, on the wand's grip. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.3`: `submit` chunks of `joint_position` (8, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (8, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; the state hashes are reported, not required (GPU physics is not bit-deterministic; the CPU rigid families' is, on one host); `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.3` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
