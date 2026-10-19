# metaworldplus-button-press-topdown-wall-i00-standard

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `metaworldplus-button-press-topdown-wall-i00-privileged` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/button-press-topdown-wall` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:metaworld-0.1.0` |

## Task
Standard-mode twin of `metaworldplus-button-press-topdown-wall-i00-privileged`: the same instance and success check (Reach past the wall and press the button downward.), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's 61 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

## Verification
Graded by the live episode, nothing replayed (owner 2026-10-17, board 0150/0151): when the episode ends, the sim
service applies Meta-World's success check to the live state after the last executed control step and writes the
verdict to its `final.json` (`graded_by = "live"`, `replays = 0`); `tests/grade.py` (separate sandbox, no network)
reads it: `success = live_success`, `infra_error = 1` when there is no verdict on the agent. The frozen start is
checked when the episode begins (instance hash, starting-state hash). The video is rendered from the recorded
trajectory in one pass after the verdict and decides nothing. After the agent's time the collect hooks stop the
agent's processes; the service writes the verdict at once (no grading replay), then renders the video (a scene build,
the episode's physics and at most about 600 frames of one camera, on the CPU; typically under a minute), all inside the
sim hook's 840 s.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: privileged container p90 2.7 GB, sim 0.7 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: memory: agent container docker peak 2.9 GiB over 13 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, 4090-ws1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 8 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.7 GiB, 7 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
| success | Meta-World's own check (`evaluate_state`). The button's top is within 2.4 cm of the target point in height; only z is compared (the button is pushed down). |

### Change Log
- 2026-10-10 (review 0067): the camera calibration in `meta["cameras"]` now gives the pose of the viewpoint the image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side of it, so points back-projected from depth were off by that much. This changes what the agent observes: standard-mode results from before this date are not strictly comparable.
- 2026-10-10 (review 0067): the instruction states this environment's success condition (what is compared with the target point, in which axes, with which tolerance) instead of "a tolerance of a few centimetres".
- 2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them (e.g. `dt = Infinity`) were a 500 that ended the episode. `meta["time_left_s"]` counts from the agent's first request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded `infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.
- 2026-10-10 (review round 3, board 0067): the sim service's request handling only (`environment/sim/server_mw.py`). A negative or non-numeric `Content-Length` is answered 400 without reading the body (the service read until the client hung up, without a bound, which could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies of one name made it build N x N images within the frame budget); a port that is still held when the service restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a number is a 400 (`true` ran as 1 second). An episode's physics, the grader and the pass rule are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode is graded by the live episode; no grading replay. `success` is Meta-World's check on the live simulator's state after the last executed control step (`live_success`, the same rule as before; the fresh replay that also had to succeed and end in the same state no longer runs). The video is rendered from the recorded trajectory in one pass after the verdict. The frozen start is checked when the episode begins (the instance's hash and the starting state's hash; a mismatch is an infrastructure failure), and the agent's leftover processes are stopped before the episode ends. What the agent sees and does is unchanged; only the instruction's scoring sentence is new.
