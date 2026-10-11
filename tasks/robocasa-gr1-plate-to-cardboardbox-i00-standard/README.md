# robocasa-gr1-plate-to-cardboardbox-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa-GR1 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa-gr1-plate-to-cardboardbox-i00-privileged` |
| Simulator / robot | `robosuite` / `fourier-gr1` |
| Family / instance | `robocasa-gr1/PosttrainPnPNovelFromPlateToCardboardboxSplitA` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robocasa-gr1:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa-gr1-plate-to-cardboardbox-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa-gr1/standard/server_casa.py`, tool module `casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the objects in the humanoid's camera images, coordinate two arms and two dexterous hands through the IK controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 256 actions submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator and writes the verdict, final at once; `tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`. The replay video is rendered after the verdict and never decides it.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 3 |
| Memory | 14 GB | 13 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: robosuite sim p90 9.7 GB, verifier p90 4.0 GB (RoboCasa and RoboCasa-GR1 together), mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only (OSMesa cameras); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 19 GiB memory. Limits measured: memory: agent container docker peak 2.5 GiB over 3 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 11 GiB (docker peak 6.7 GiB, 10 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Action type | `ee_pose` (24 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `egoview`, `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand` (robot-mounted; calibration in every response) |

### Change Log
- 2026-10-10: the sim service writes its verdict together with `finalized` in one atomic step and renders the replay video only afterwards (the video is optional and can no longer turn a verdict into `infra_error`; a restart never rewrites a written verdict); the collect hook (`environment/sim/finalize.sh`) waits for that verdict for up to 3450 s of a 3600 s timeout (before: 980 s of 1500 s, video included, which lost episodes longer than about 10,000 control steps); a malformed request field (`dt`, `seconds` or `video_fps` that is not a finite number, `cameras` or `note` of the wrong type, `dt` = 0, ...) is answered with 400 before any physics instead of 500 and the end of the episode; `time_left_s` counts from the start of the service's container, not from when its scene was built; the client's docstring describes this service. The scene, the instance, the success check and the pass rule are unchanged, so the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A `final.json` that cannot be read as a JSON object (truncated, not JSON, not an object) is graded `infra_error = 1` and `grader_error = 1`; before, the grader raised and the trial had no reward file. Nothing else changes: a readable `final.json` is graded as before.
- 2026-10-10 (review round 3, board 0067): the sim service's request handling (`environment/sim/server_casa.py`) and `tests/grade.py`. A negative or non-numeric `Content-Length` is answered 400 without reading the body (the service read until the client hung up, without a bound, which could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies of one name made it build N x N images within the frame budget); a port that is still held when the service restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a number is a 400 (`true` ran as 1 second). The grader: a `final.json` whose evidence fields (`control_steps`, `calls`, `elapsed_s`, `final_reward`) are not numbers no longer stops it before it writes a reward (they are reported as 0 and decide nothing). An episode's physics and the pass rule are unchanged.
