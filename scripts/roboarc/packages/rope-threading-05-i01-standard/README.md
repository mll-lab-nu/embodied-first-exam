# topogym-rope-threading-05-i01-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.3`) |
| Twin | `topogym-rope-threading-05-i01-privileged` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `rope_threading` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `labv18b/rcb-topogym:0.2.16-dev-cu128` |

## Task
Standard-mode twin of `topogym-rope-threading-05-i01-privileged` (same frozen instance): the agent gets only the `eai-standard/2.3` client
(docs/rcb/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-rope-threading-05-i01-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Thread the rope through the cyan grommet in the wall (G1) then green ring (A) then purple grommet in the wall (G2) then amber ring (V), in that order along the rope from material start to material end.

### Success requirements
- Required directions along that material order: cyan grommet in the wall (G1): cross away from the side containing the amber ring (V); green ring (A): cross toward the side containing the purple grommet in the wall (G2); purple grommet in the wall (G2): cross toward the side containing the amber ring (V); amber ring (V): cross toward the side containing the cyan grommet in the wall (G1). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 10 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- The rope's Young's modulus is 5000 kPa. Gripper pressure can deform it. A crushed rope volume (an inverted volume element) ends the episode only once it has lasted at least 0.25 s (7 consecutive physics ticks; while it lasts, the goal cannot be confirmed); an invalid soft-body solver state is a simulator breakdown (below). Close to about half the rope's diameter and slow down in the last centimetre.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (reported in clipped[]).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (an invalid soft-body solver state): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Sizes (rope radius 4 mm): G1: inner radius 45 mm, tube radius 6 mm, centreline passage radius 41.9 mm on the middle plane and 44.2 mm on the two tube-offset planes; A: inner radius 45 mm, tube radius 6 mm, centreline passage radius 41.9 mm on the middle plane and 44.2 mm on the two tube-offset planes; G2: inner radius 45 mm, tube radius 6 mm, centreline passage radius 41.9 mm on the middle plane and 44.2 mm on the two tube-offset planes; V: inner radius 45 mm, tube radius 6 mm, centreline passage radius 41.9 mm on the middle plane and 44.2 mm on the two tube-offset planes.
- Aperture check: round_ring, compression allowance 1 mm. This allowance changes the geometric passage test; the collision geometry stays as declared.
- The material start is the rope end that is farther from the rings at the start.
- Only the grippers' fingers collide with the rope and the rings: every other robot part (palms, wrists, arm links, bases) passes through them without contact, so only the fingers can push, pinch or hold the rope.
- Grasp regions (assisted grasping, see Grippers above; one or more spheres per graspable part): rope: 456 spheres of radius 8 mm. Both finger contacts must lie inside one of the part's spheres; a part touched elsewhere is grasped physically.
- Grading: success needs the live episode to succeed (with the thresholds above) AND one fresh-process replay of its rows to succeed; a live failure is final whatever the replay shows. This family's physics runs on the GPU, which is not bit-deterministic, so that replay can differ slightly from the live episode: it runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (50 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in the live episode can still complete; the hold uses the thresholds above too (no tolerance for this family). Nothing else changes.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.3`: `submit` chunks of `joint_position` (14, streamed at the 25 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; the state hashes are reported, not required (GPU physics is not bit-deterministic; the CPU rigid families' is, on one host); `/logs/verifier/replay.mp4` is rendered during that replay; after a live success it is a grading replay (tooling v18): if this GPU family's episode has not ended after the last live row, the final targets are held for up to 2 s with the replay tolerances of the grader details; a live failure is final |
| crash recovery | `eai-standard/2.3` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
