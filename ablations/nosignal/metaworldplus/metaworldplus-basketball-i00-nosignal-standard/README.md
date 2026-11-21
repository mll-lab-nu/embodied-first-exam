# metaworldplus-basketball-i00-standard

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `metaworldplus-basketball-i00-privileged` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/basketball` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:metaworld-0.1.0` |

## Task
Standard-mode twin of `metaworldplus-basketball-i00-privileged`: the same instance and success check (Pick up the ball and place it through the basketball hoop.), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's 90 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

## Verification
Graded by the live episode, nothing replayed (owner 2026-10-17): when the episode ends, the sim
service applies Meta-World's success check to the live state after the last executed control step and writes the
verdict to its `final.json` (`graded_by = "live"`, `replays = 0`); `tests/grade.py` (separate sandbox, no network)
reads it: `success = live_success`, `infra_error = 1` when there is no verdict on the agent. The frozen start is
checked when the episode begins (instance hash, starting-state hash). The video is rendered from the recorded
trajectory in one pass after the verdict and decides nothing. After the agent's time the collect hooks stop the
agent's processes; the service writes the verdict at once (no grading replay), then renders the video (a scene build,
the episode's physics and at most about 600 frames of one camera, on the CPU; typically under a minute), all inside the
sim hook's 840 s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
| success | Meta-World's own check (`evaluate_state`). The ball's centre is within 8 cm of the point that has the target point's x and y and the height z = 0.30 m, with the height difference counted double. |
