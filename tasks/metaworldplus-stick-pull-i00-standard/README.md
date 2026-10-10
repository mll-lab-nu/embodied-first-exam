# metaworldplus-stick-pull-i00-standard

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `metaworldplus-stick-pull-i00-privileged` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/stick-pull` / seed 1 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-metaworld:0.1.0` |

## Task
Standard-mode twin of `metaworldplus-stick-pull-i00-privileged`: the same instance and success check (Use the stick to pull the target object.), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's 119 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

In this environment the success state does not persist on its own: after the oracle's last action, holding still for 10 control steps loses it. Graded on the final state, a trajectory must end at that moment.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: privileged container p90 2.7 GB, sim 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: memory: agent container docker peak 2.9 GiB over 13 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 8 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.7 GiB, 7 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
| success | Meta-World's own check (`evaluate_state`). The thermos's handle (the loop the stick goes into) is within 12 cm of the target point AND the stick is still in the handle: the stick's far end is at or beyond the handle in x, within 4 cm of it in y and within 6 cm of it in z. A thermos that is at the target with the stick pulled out does not count. |

### Change Log
- 2026-10-10 (review 0067): the camera calibration in `meta["cameras"]` now gives the pose of the viewpoint the image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side of it, so points back-projected from depth were off by that much. This changes what the agent observes: standard-mode results from before this date are not strictly comparable.
- 2026-10-10 (review 0067): the instruction states this environment's success condition in full. Before, it said only that the object is compared with the target point "with a tolerance of a few centimetres" and left out that the stick must still be engaged in the final state, so an agent that finished the motion and then let the stick go scored 0 without having been told. Results from before this date were obtained under the incomplete text.
- 2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them (e.g. `dt = Infinity`) were a 500 that ended the episode. `meta["time_left_s"]` counts from the agent's first request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded `infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.
