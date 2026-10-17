# robocasa365-pick-place-sink-to-counter-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa365-pick-place-sink-to-counter-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/PickPlaceSinkToCounter` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robocasa365:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa365-pick-place-sink-to-counter-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa365/standard/server_casa.py`, tool module `casa_tool`), which records the episode and judges it live (nothing is replayed); the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 404 actions submitted through the client, one row per control step.

## Verification
The sim service judges the live episode when the agent's time is up (the environment's success check on the state after the last executed control step; nothing is replayed) and writes the verdict, final at once; `tests/grade.py` (separate sandbox, no network) reads its `final.json` (`graded_by = live`): `success = live_success ∧ not solved at the start ∧ no simulator error`. The episode's start is checked against the frozen instance before the agent is served (`RCB_INSTANCE_SHA`, `RCB_START_SHA`; a mismatch is an infrastructure failure, `instance_mismatch`). The video is rendered from the trajectory after the verdict (one render pass) and never decides it.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 3 |
| Memory | 9 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim p90 5.6 GB, privileged container p90 7.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only (OSMesa cameras); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 19 GiB memory. Limits measured: memory: agent container docker peak 3.9 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 11 GiB (docker peak 6.4 GiB, 14 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Action type | `joint_position` (13 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand` (robot-mounted; calibration in every response) |

### Change Log
- 2026-10-10: the sim service writes its verdict together with `finalized` in one atomic step and renders the replay video only afterwards (the video is optional and can no longer turn a verdict into `infra_error`; a restart never rewrites a written verdict); the collect hook (`environment/sim/finalize.sh`) waits for that verdict for up to 3450 s of a 3600 s timeout (before: 980 s of 1500 s, video included, which lost episodes longer than about 10,000 control steps); a malformed request field (`dt`, `seconds` or `video_fps` that is not a finite number, `cameras` or `note` of the wrong type, `dt` = 0, ...) is answered with 400 before any physics instead of 500 and the end of the episode; `time_left_s` counts from the start of the service's container, not from when its scene was built; the client's docstring describes this service. The scene, the instance, the success check and the pass rule are unchanged, so the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A `final.json` that cannot be read as a JSON object (truncated, not JSON, not an object) is graded `infra_error = 1` and `grader_error = 1`; before, the grader raised and the trial had no reward file. Nothing else changes: a readable `final.json` is graded as before.
- 2026-10-10 (review round 3, board 0067): the sim service's request handling (`environment/sim/server_casa.py`) and `tests/grade.py`. A negative or non-numeric `Content-Length` is answered 400 without reading the body (the service read until the client hung up, without a bound, which could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies of one name made it build N x N images within the frame budget); a port that is still held when the service restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a number is a 400 (`true` ran as 1 second). The grader: a `final.json` whose evidence fields (`control_steps`, `calls`, `elapsed_s`, `final_reward`) are not numbers no longer stops it before it writes a reward (they are reported as 0 and decide nothing). An episode's physics and the pass rule are unchanged.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/server_casa.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the first start of the service's container (`time_left_s`) and from when its scene was ready (`time_s`). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-13 (board 0093; found in board 0086): the camera calibration (`environment/sim/server_casa.py`). `cam2world_gl` held the pose of MuJoCo's left-eye camera (`scene.camera[0]`), 3.4 cm (half the model's 0.068 m interpupillary distance) to the camera's left of the viewpoint the mono RGB and depth images are rendered from; it now is that viewpoint (`data.cam_xpos` / `data.cam_xmat`). Checked against MuJoCo's own renders of marker spheres at known world points, every served camera, before and after the robot moved: the reprojection error was 10.5-10.7 px median (up to 28 px for near points, always to the same side), now 0.15 px median and at most 0.4 px. The intrinsics were right (every camera here is given by its `fovy`, none by a sensor size) and are unchanged, as are the images, the scene, the frozen instance, the pass rule and the grader, so the task keeps its name. **Standard-mode results from before this date used the offset calibration**: a point located from the images and the reported calibration came out about 3.4 cm to the side (agents missed a microwave button by 3.5 cm), so they are not strictly comparable with later ones.
- 2026-10-17 (owner, boards 0150 and 0151): the verdict is the live episode's. The sim service judges the episode it ran (the environment's success check on the state after the last executed control step, the scene not solved at the start) and no longer replays it in a fresh simulator to grade it: `final.json` says `graded_by = live`, `replays = 0`, and `deterministic` / `replay_success` are gone from it and from `reward.json` (`graded_by_live = 1`). An episode that ended on a simulator error is no success (its last state is a partial step's; before, the replay of the executed steps and its hash comparison decided). The frozen start is checked when the episode begins, before the agent is served: the instance file's hash and the starting state's hash (`RCB_INSTANCE_SHA`, `RCB_START_SHA` in `environment/docker-compose.yaml`; the latter as logged by every archived standard episode of the instance); a mismatch is an infrastructure failure (`instance_mismatch`). The video is rendered from the trajectory after the verdict in one render pass (before: a second replay) and decides nothing; the collect hook waits for it for the rest of its time (before: twice the verdict's time + 120 s). The scene, the frozen instance, the success check, the agent's time and what the agent sees, except the instruction's scoring sentence, are unchanged, so the task keeps its name. Earlier results were graded live ∧ replay ∧ deterministic; their live part is `live_success` in their `final.json`.
