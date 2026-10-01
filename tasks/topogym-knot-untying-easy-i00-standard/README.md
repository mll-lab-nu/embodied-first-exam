# topogym-knot-untying-easy-i00-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `topogym-knot-untying-easy-i00-privileged` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `knot_untying` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` |

## Task
Standard-mode twin of `topogym-knot-untying-easy-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/rcb/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-knot-untying-easy-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it.

### Success requirements
- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope diameter plus 3 mm above it.
- Keep the rope volume intact; do not invert or collapse it to bypass the knot.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release clearance is measured between axis-aligned bounding boxes of the robot's collision geometries and the rope (refined per tetrahedron where they are close).

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.2`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; GPU physics: the state hashes are reported, not required; `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.2` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
