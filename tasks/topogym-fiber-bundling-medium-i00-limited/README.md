# topogym-fiber-bundling-medium-i00-limited

Limited-mode twin of `topogym-fiber-bundling-medium-i00` (same frozen instance): the agent gets only the `rcb-limited/2.2` client
(docs/rcb/LIMITED_MODE_PROTOCOL.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene, records the episode as a (T, 8) trajectory, replays it for success, and renders the
video. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the
unlimited task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Goal

Manipulate the thick sheath to pass every fine fiber and the front sheath through the fixed copper ring; keep the rear terminal anchored.

## Success requirements

- Pass every fiber tip first, then successive material points through to its root. The actual crossing history must be observed; placing fibers on the far side or passing only the tips is not completion.
- All fiber points must finish beyond the exit side of the ring tube, allowing for fiber thickness. The branching face of the front sheath must also pass through and clear the tube with its full thickness. The fixed rear terminal must remain anchored and does not pass through.
- Keep the angle between every pair of adjacent fiber segments at most 60 degrees in the final configuration.
- Touch and grasp only the thick sheath with the gripper. Keep the completed passage valid through confirmation; holding is allowed, with no separate release or speed threshold.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Any gripper touch of a fine fiber at any time ends the episode in failure, including a brief or zero-force touch.
- A fiber link falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Sizes: ring inner radius 13.5 mm, ring tube radius 4 mm; 8 fibers of radius 1.2 mm; sheath radius 12 mm.
- Each fiber is tracked at 11 points from tip to root. A point counts when it crosses the ring's plane less than 17.48 mm from the ring's axis, in tip-to-root order; a crossing out of order or outside that radius resets that point and every point behind it, and crossing back loses the credit.
- At the end every fiber point must be more than 5.2 mm past the ring's plane (tube + fiber radius) and the centre of the sheath's front face more than 16 mm past it (tube + sheath radius). The exit side is the side opposite to where the fibers start.
- The failure counts contact between a fine fiber and the gripper (fingers and hand, housing included); arm links touching a fiber do not count. Contact is sampled at all 4 solver substeps of every tick; if any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.

| | |
|---|---|
| tier / mode | perception / limited (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `rcb-limited/2.2`: `submit` chunks of `joint_position` (8, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (8, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet: `solution/solve.sh` says so and exits 1 |
| verification | `success` = live success ∧ replay success, computed inside the sidecar (GPU physics: the state hashes are reported, not required); `/logs/verifier/replay.mp4` |
