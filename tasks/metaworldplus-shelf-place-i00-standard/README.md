# metaworldplus-shelf-place-i00-standard

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `metaworldplus-shelf-place-i00-privileged` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/shelf-place` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-metaworld:0.1.0` |

## Task
Standard-mode twin of `metaworldplus-shelf-place-i00-privileged`: the same instance and success check (Pick up the object and place it on the shelf at the target.), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's 78 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
