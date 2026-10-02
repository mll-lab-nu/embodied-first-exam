# topogym-orbits-easy-i00-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.3`) |
| Twin | `topogym-orbits-easy-i00-privileged` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `orbits` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.8-cu128` |

## Task
Standard-mode twin of `topogym-orbits-easy-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.3` client
(docs/rcb/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-orbits-easy-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Separate and place the entire cord and wooden handle together inside the green dashed goal region. Keep the rings, posts and fixed assembly on the puzzle/system side.

### Success requirements
- Put every part of the entire cord and wooden handle together inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 150 mm above the tabletop.
- Keep the rings, posts and fixed assembly, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Every point of the target cord must also move at most 1 mm/s. Holding the target with the gripper is allowed; release is not required.
- Keep the cord intact and attached to both handle attachment points; each attachment residual must be at most 2 mm. No inverted or collapsed cord volume is accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Broken attachments or invalid cord volume end the episode in failure.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 398.0 mm x 398.0 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes; for the cord every vertex of its simulated volume.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The remaining components here are fixed.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.3`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; GPU physics: the state hashes are reported, not required; `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.3` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
