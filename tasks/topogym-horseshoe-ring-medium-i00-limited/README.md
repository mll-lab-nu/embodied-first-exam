# topogym-horseshoe-ring-medium-i00-limited

Limited-mode twin of `topogym-horseshoe-ring-medium-i00` (same frozen instance): the agent gets only the `rcb-limited/2.2` client
(docs/rcb/LIMITED_MODE_PROTOCOL.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene, records the episode as a (T, 14) trajectory, replays it for success, and renders the
video. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the
unlimited task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Goal

Separate and place the entire removable ring inside the green dashed goal region. Keep the horseshoes and chains on the puzzle/system side.

## Success requirements

- Put every part of the entire removable ring inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 222.299 mm above the tabletop.
- Keep the horseshoes and chains, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep every permanent chain/eye interlock intact; free only the removable target ring.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Losing any permanent chain/eye connection ends the episode in failure.
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Finger contact with a held movable piece may penetrate at most 2 mm; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand. All other task contacts, including piece-piece, table, arm and gripper-housing contacts, may penetrate at most 1 mm. Exceeding either limit ends the episode in failure.

## Grader details (in addition to the requirements above)

- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 230.3 mm x 230.3 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The horseshoes and chain links are free to move (their speed is not checked), but no point of them may cross that plane.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the 1 mm limit in the same tick.
- The four permanent connections (the upper and lower eye of each horseshoe with its chain link) are checked at every tick by the linking number of the two loops.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): horseshoe_left: radius 90.6 mm, enclosing the whole part; horseshoe_right: radius 90.6 mm, enclosing the whole part; target_ring: radius 77.7 mm, enclosing the whole part. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

| | |
|---|---|
| tier / mode | perception / limited (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `rcb-limited/2.2`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet: `solution/solve.sh` says so and exits 1 |
| verification | `success` = live success ∧ replay success, computed inside the sidecar (GPU physics: the state hashes are reported, not required); `/logs/verifier/replay.mp4` |
