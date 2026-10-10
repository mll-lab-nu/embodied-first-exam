# robocasa365-microwave-defrost-meat-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa365-microwave-defrost-meat-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/MicrowaveDefrostMeat` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robocasa365:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa365-microwave-defrost-meat-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa365/standard/server_casa.py`, tool module `casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 1056 actions submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator and writes the verdict, final at once; `tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`. The replay video is rendered after the verdict and never decides it.

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
