# topogym-rope-threading-easy-i00-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.3`) |
| Twin | `topogym-rope-threading-easy-i00-privileged` |
| Simulator / robot | `topogym` / `aloha` |
| Family / instance | `rope_threading` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.8-cu128` |

## Task
Standard-mode twin of `topogym-rope-threading-easy-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.3` client
(docs/rcb/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-rope-threading-easy-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Thread the rope through the cyan ring (R1) then green ring (R2), in that order along the rope from material start to material end.

### Success requirements
- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross away from the side containing the cyan ring (R1). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 1 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Invalid rope volume ends the episode in failure.

### Grader details (in addition to the requirements above)
- Sizes: each ring's inner radius is 69 mm and its tube 12 mm thick (radius 6 mm); the rope's radius is 4 mm. So the rope's centreline must pass less than 64.9 mm from a ring's centre, and the passage is checked on the ring's middle plane and on the planes 6 mm to either side of it.
- The material start is the rope end that is farther from the rings at the start.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.3`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; GPU physics: the state hashes are reported, not required; `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.3` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
