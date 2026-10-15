# RoboTwin 2.0

RoboTwin 2.0's standard tasks serve `eai-standard/2.1` (docs/STANDARD_MODE.md Part 1), the service the base protocol
was written from. Generators: `scripts/robotwin_mk_task.py` (privileged), `scripts/robotwin_mk_limited.py` (standard,
inside the eai-robotwin image); shared files checked by `scripts/robotwin_sync_shared.py --check`.


## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

**Actions.**
- `joint_position` (14 = 6 joints + gripper per arm; rad; gripper 0 closed..1 open): rows are `dt` seconds apart
  (`1/250 ≤ dt ≤ 0.5`, a multiple of the 1/250 s physics step: 0.004, 0.008, 0.02, …); the service streams drive
  targets at 250 Hz. A chunk may cover at most `max_chunk_s` (10 s). Rows may carry 14 extra columns (28 in all) = joint
  velocity feed-forward in rad/s, held over the row; without them the service uses the central difference of the
  streamed targets. (An expert record replayed at `dt = 1/250` with its velocities is exact.)
- `ee_pose` (16 = xyz + wxyz + gripper per arm, world frame): each row is planned by CuRobo against the table only and
  executed; `dt` is ignored (the planner sets the duration); a failed plan holds that arm for 50 physics steps and is
  reported in `plan`. The pose is RoboTwin's end-effector frame, **0.12 m behind the gripper centre** along the approach
  axis (same as the `proprio` end-effector poses). At most 50 rows per submit.
- Video is captured every `250/video_fps` physics steps; the chunk is appended to the recorded `(T, 34)` trajectory.
- `/observe` watches at most `max_watch_s` = 30 s.

**`meta.cameras`** carries RoboTwin's per-camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the wrist cameras move
with the arms (`cam2world_gl/<cam>` per returned frame). Until 2026-10-10 the service sent the calibration of its start,
which was wrong for the wrist cameras once an arm had moved. `/spec` states the agent's clock in
`budget.wall_clock_note`.

**Proprioception (82 columns)**, grouped in `spec.proprio_groups`. 2.0's 30 columns are unchanged at 0–29:

| columns | group | source |
|---|---|---|
| 0–13 | `joint_cmd` | commanded drive targets + gripper command |
| 14–27 | `ee_pose` | measured end-effector link pose (RoboTwin ee frame, 0.12 m behind the TCP) |
| 28–29 | `gripper_cmd` | commanded gripper value |
| 30–43 | `joint_pos` | measured joint positions (articulation qpos) + measured gripper opening, from the finger joint mapped to the command's [0,1] units (clipped to [-0.2, 1.2]) |
| 44–55 | `joint_vel` | measured arm joint velocities |
| 56–69 | `tcp_pose` | measured gripper-centre pose (RoboTwin `get_*_tcp_pose`) |
| 70–81 | `joint_effort` | stiffness·(target−q) + damping·(v_target−q̇) per arm joint: the PD drive's effort |

Depth (`include_depth`) is available on the head, front and wrist cameras.

**Crash recovery.** Every executed physics step is journaled (`trajectory_live.f64`) and every completed call logs a
checkpoint in `episode.jsonl`; compose restarts the service (`restart: on-failure:6`) and it resumes the same episode.
More than 2 crashes end the episode: `sim_crashed_on_call` if every crash happened while serving a call, else
`sim_crashed` (`infra_error = 1`). A scene build that hangs is killed by the service's startup watchdog
(`RCB_STARTUP_TIMEOUT_S`, 300 s). A host on which the frozen instance does not rebuild gets one retry and then
`reason = instance_mismatch` with `infra_error = 1`.

**Grading.** `success = live ∧ replay ∧ deterministic`; `replay.mp4` is six-view.

**Live recording** (sidecar only; the agent sees none of it):
- `live.mp4`: the episode as six views (world / observer / head · front / left wrist / right wrist, 213×160 tiles), each
  frame stamped `wall mm:ss  sim s  #call what-the-agent-sent`. Frames are sampled every `250 / RCB_LIVE_FPS` physics
  steps (default 10 per simulated second) only inside calls that ran physics, so the agent's thinking time takes no
  frames; with `RCB_LIVE_FILTER=moving` (default) frames are also skipped while nothing moves (max change of all poses /
  joint states below `RCB_LIVE_MOVE_EPS`, 1e-3).
- Capture (`RCB_LIVE`): **`replay`** (default) logs only call boundaries during the episode (no cost to the agent) and
  renders `live.mp4` at episode end from the recorded trajectory; `realtime` renders while the episode runs (the video
  survives a crash, but each frame costs ~150 ms of the agent's wall clock: a 10 s chunk took 20.6 s instead of 5.1 s);
  `off` disables it.
- `live_segments.jsonl` (per call) and `live_timeline.jsonl` (per frame) map every frame back to `episode.jsonl`;
  `calls/NNNNNN/actions.npy` is the exact action array of every `/submit`; `trajectory_live.f64` with
  `live_segments.jsonl` is enough to render the video offline; `startups.jsonl` has one line per service start.
- The verifier copies `live.mp4` and `live_timeline.jsonl` next to `replay.mp4` (which stays the authoritative video)
  and reports `live_video`, `live_frames`, `sim_startups`, `infra_error`.
