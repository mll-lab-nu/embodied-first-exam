# topogym-knot-untying-easy-i00-limited

Limited-mode twin of `topogym-knot-untying-easy-i00` (same frozen instance): the agent gets only the `rcb-limited/2.2` client
(docs/rcb/LIMITED_MODE_PROTOCOL.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene, records the episode as a (T, 14) trajectory, replays it for success, and renders the
video. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the
unlimited task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Goal

Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it.

## Success requirements

- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope diameter plus 3 mm above it.
- Keep the rope volume intact; do not invert or collapse it to bypass the knot.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Invalid rope volume ends the episode in failure.

## Grader details (in addition to the requirements above)

- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release clearance is measured between axis-aligned bounding boxes of the robot's collision geometries and the rope (refined per tetrahedron where they are close).

| | |
|---|---|
| tier / mode | perception / limited (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `rcb-limited/2.2`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet: `solution/solve.sh` says so and exits 1 |
| verification | `success` = live success ∧ replay success, computed inside the sidecar (GPU physics: the state hashes are reported, not required); `/logs/verifier/replay.mp4` |
