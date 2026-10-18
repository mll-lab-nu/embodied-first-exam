# RoboTwin 2.0

RoboTwin 2.0's standard tasks serve `eai-standard/2.1` (docs/protocol/standard_mode.md Part 1), the service the base protocol
was written from. Generators: `scripts/robotwin_mk_task.py` (privileged), `scripts/robotwin_mk_limited.py` (standard,
inside the eai-robotwin image); shared files checked by `scripts/robotwin_sync_shared.py --check`.


## Standard-mode service details

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
with the arms (`cam2world_gl/<cam>` per returned frame). `/spec` states the agent's clock in
`budget.wall_clock_note`.

**Proprioception (82 columns)**, grouped in `spec.proprio_groups`:

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

**Grading** (the live episode, PROTOCOL H.4; no grading replay). `success` is RoboTwin's `check_success` on the
episode the sidecar ran: it is checked after every call that ran physics, the first success ends the episode, and when
the agent's time is up (the collect hook's SIGUSR1, after the monitor is sealed and the agent's container is stopped
with `kill -9 -1`) the final state is checked once more. `final.json` gets the verdict at once (`graded_by = "live"`, `replays = 0`, `finalized`,
the end state's hash `live_sha`, `video_pending: true`); `trajectory.npz` is saved as the deliverable. The frozen
instance is checked when the scene is built, before the agent is served: `rcb_traj.Session` compares the initial-state
hash with `instance.json`'s `state_sha` (a mismatch: one retry, then `instance_mismatch`, `infra_error = 1`). The
grader (`tests/grade.py`) transcribes it; `infra_error = 1` only for a missing / unreadable final.json, no live verdict
(`graded_by` absent: the hook gave up first, or `finalize_error`), `sim_crashed`, `resume_failed`, `instance_mismatch`;
`sim_crashed_on_call`, a simulator error from the agent's call (`reason = "error"`), a timeout are the agent's 0.

**Video.** After the verdict one pass over the trajectory (`rcb_live.LiveRecorder.render_videos`) rebuilds the frozen
instance, steps the rows once and writes both `replay.mp4` (six views, 320×240 tiles, a frame every
max(10, rows/600) steps) and `live.mp4` (below); `video_pending` is false when it is done or failed (`video_error`). The
collect hook waits for it until 2200 s (an episode whose physics filled the whole 1800 s cutoff, plus at most ~2100
rendered frames); a video not ready by then is lost, the verdict is not.

**Live recording** (sidecar only; the agent sees none of it):
- `live.mp4`: the episode as six views (world / observer / head · front / left wrist / right wrist, 213×160 tiles), each
  frame stamped `wall mm:ss  sim s  #call what-the-agent-sent`. Frames are sampled every `250 / RCB_LIVE_FPS` physics
  steps (default 10 per simulated second) only inside calls that ran physics, so the agent's thinking time takes no
  frames; with `RCB_LIVE_FILTER=moving` (default) frames are also skipped while nothing moves (max change of all poses /
  joint states below `RCB_LIVE_MOVE_EPS`, 1e-3).
- Capture (`RCB_LIVE`): **`replay`** (default) logs only call boundaries during the episode (no cost to the agent) and
  renders `live.mp4` after the verdict from the recorded trajectory, in the same pass as `replay.mp4`; `realtime` renders while the episode runs (the video
  survives a crash, but each frame costs ~150 ms of the agent's wall clock: a 10 s chunk took 20.6 s instead of 5.1 s);
  `off` disables it.
- `live_segments.jsonl` (per call) and `live_timeline.jsonl` (per frame) map every frame back to `episode.jsonl`;
  `calls/NNNNNN/actions.npy` is the exact action array of every `/submit`; `trajectory_live.f64` with
  `live_segments.jsonl` is enough to render the video offline; `startups.jsonl` has one line per service start.
- The verifier copies `live.mp4` and `live_timeline.jsonl` next to `replay.mp4` (which stays the authoritative video)
  and reports `live_video`, `live_frames`, `sim_startups`, `infra_error`.
