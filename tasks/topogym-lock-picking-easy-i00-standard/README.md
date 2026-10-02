# topogym-lock-picking-easy-i00-standard

| | |
|---|---|
| Benchmark | TopoGym |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `topogym-lock-picking-easy-i00-privileged` |
| Simulator / robot | `topogym` / `panda_robotiq` |
| Family / instance | `lock_picking` / seed 0 |
| Oracle | `none` — No reference solution (no solution/). The frozen instance was validated by the build: it builds in a fresh process (seed < 2^31) and holds still under hold checks in a fresh container, and a verifier replay grades without a grader error. No graded positive yet. Human review per family (protocol §2.7). |
| Agent time budget | 21600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/luigivamper/rcb-topogym:0.2.5-cu128` |

## Task
Standard-mode twin of `topogym-lock-picking-easy-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/rcb/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 8) trajectory; its collect hook
(`environment/sim/finalize.sh`) replays the trajectory once in a fresh process for success, rendering the video during
that replay. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `topogym-lock-picking-easy-i00-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
See `solution/`.

## Verification
See `tests/grade.py`.

## Details

### Goal
Insert the tabbed key through all three rotor plates and the final END plate, while respecting their slots and stops.

### Success requirements
- Keep the finite-length shaft passing through the full thickness of all four plates at once, facing the insertion direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all four bores. The radial numerical contact tolerance is 0.01 mm; do not push the shaft through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Sizes: bore radius 7.5 mm, shaft radius 6.5 mm. At each of the 8 plate faces (three 10 mm rotor plates and END, 150 mm apart), the shaft axis' distance from the bore axis plus 6.5 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm: about 1.01 mm of offset when the key is straight, which over the stack allows only about 0.25 degrees of tilt.
- The shaft reaches from 515 mm behind the leading tab to 15 mm in front of it; all 8 plate faces must lie within that length.
- Tabs: radius 36 mm, half-width 4 degrees; slots: half-width 8 degrees. A tab that overlaps a plate must sit inside one of that plate's slots with an angular margin of at least asin(axis offset / 36 mm) + the tilt.
- Rotor stops (from each rotor's start angle; "the other way" is the sense that turns rotor 2's slot toward the tabs' starting angle): rotor 1 15 degrees either way; rotor 2 10 degrees one way and 45 degrees the other; rotor 3 turns freely. Going more than 0.5 degrees beyond a stop ends the episode.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.2`: `submit` chunks of `joint_position` (8, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (8, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | none yet (`oracle = "none"`, no `solution/`) |
| verification | `success` = live success ∧ replay success: the live episode, then one fresh-process replay in the sidecar's collect hook, after the live service has exited; GPU physics: the state hashes are reported, not required; `/logs/verifier/replay.mp4` is rendered during that replay |
| crash recovery | `eai-standard/2.2` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |
