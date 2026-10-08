# Standard-mode protocol `eai-standard/2.1` (robot as a service)

> Formerly `rcb-limited/2.1` (limited mode). Protocol v1.0 ([PROTOCOL.md](PROTOCOL.md)) renamed it; the content is
> unchanged, and 2.1 includes the crash recovery described below (added 2026-09-29 without a version bump). Services
> and tasks report `eai-standard/2.1`; the shipped client also accepts the former `rcb-limited/2.x` spelling.
> Which parts of this document are required is listed in PROTOCOL §4.

The agent talks to a **sim service** it cannot open, over HTTP. **No reset**: one trial = one episode. **No step limit** (except a technical episode cap where a
task states one, e.g. DexToolBench's 360,000 control steps); the agent's wall-clock budget is the real limit; actions and simulated time are reported as cost. Nothing the agent can
call reveals object poses, scene files, seeds or the success predicate. Videos, frames, depth and proprioception come
back as **binary** in the response body (RCB1 frames, below), never base64; the agent's code decides what to keep.

Base URL: `http://sim:8000` (compose network) or `http://localhost:8000` (Harbor egress control puts the service in the
agent's network namespace); the client tries both. The socket opens only when the scene is ready (~1 min); until then
connections are refused and the client retries.

## Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: action types (dims, layouts, limits, semantics), cameras, proprio layout, budgets |
| GET | `/status` | — | JSON: `{step, calls, physics_steps, done, reason, elapsed_s}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, include_depth, video}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, include_depth, note}` + part `actions` float32 (T, dim) | RCB1 |
Anything else (`/state`, `/success`, …) returns **404**; so does `/reset` unless the run enables the optional reset
capability (below).

## RCB1 frame
```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```
Response parts: `video/<cam>` (mp4), `frames/<cam>` (uint8 [N,H,W,3]), `last/<cam>` (uint8 [H,W,3], always), `depth/<cam>`
(float16 [N,H,W], if requested), `proprio` (float32 [N, len(proprio layout)], one row per video frame: 82 columns on RoboTwin, 3 x actuators on MuJoCo). Requests over 64 MB → 413 (the client refuses
to send one); a
response over 256 MB drops `frames/`/`depth/` and says so in `meta.degraded`. `rcb1.py` (encode/decode, `python -m rcb1
unpack f dir`) is shipped with the client.

## `meta` (in every response)
`step` (rows executed so far), `calls`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio` = `{"layout": [82 names], "now": [82 floats]}` (groups below), `cameras`
(RoboTwin's per-camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the whole key omitted when the task sets
`RCB_OBS_CALIBRATION=0`), `done`, `reason`. `/submit` adds `chunk_id, type, executed_rows, physics_steps_chunk, clipped
[{row,index,reason}], n_clipped, plan [{row,left,right}] (ee_pose), ok`; `/observe` adds `obs_id, seconds, physics_steps_watch`.

## `/submit` semantics
- `joint_position` (14 = 6 joints + gripper per arm; rad; gripper 0 closed..1 open): rows are `dt` seconds apart
  (`1/250 ≤ dt ≤ 0.5`, a multiple of the 1/250 s physics step: 0.004, 0.008, 0.02, …; anything else is rejected, never rounded); the service streams drive targets at 250 Hz with `interpolate = "linear"` (default) or `"hold"`
  between rows, exactly as a real controller consumes a chunk. Out-of-limit values are clipped and reported (continuous
  joints have `null` limits and are never clipped). A chunk may cover at most `max_chunk_s` (10 s). Rows may carry 14
  extra columns (28 in all) = joint velocity feed-forward in rad/s, held over the row; without them the service uses the
  central difference of the streamed targets. (An expert record replayed at `dt = 1/250` with its velocities is exact.)
- `ee_pose` (16 = xyz + wxyz + gripper per arm, world frame): each row is planned by CuRobo against the table only and
  executed; `dt` is ignored (the planner sets the duration); a failed plan holds that arm for 50 physics steps and is
  reported in `plan`. The pose is RoboTwin's end-effector frame, **0.12 m behind the gripper centre** along the approach
  axis (same as the `proprio` end-effector poses). At most 50 rows per submit.
- Not yet: `joint_delta`, `joint_velocity`, `ee_delta`, `joint_torque` (listed under `spec.action_types.not_yet`).
- Video is captured every `250/video_fps` physics steps from the requested cameras, plus the first and last frame.
- After the chunk the task predicate is evaluated; the first success ends the episode (`done`, `reason = "success"`).
  The chunk is appended to the recorded `(T, 34)` trajectory and to `episode.jsonl`.

## `/observe` semantics
`seconds = 0` (default) returns the current frames, free (no physics). `seconds > 0` (≤ `max_watch_s`, 30) holds the last
command, advances physics and returns the video; the predicate is checked afterwards. Watching costs no budget beyond
the wall clock; the simulated time is recorded as cost.

## Errors (no physics executed)
| code | when |
|---|---|
| 400 | wrong type/dim, NaN/inf, `dt` or `seconds` out of range or `dt` not a multiple of the physics step, chunk too long, bad interpolate/video value, `video_fps` outside [1, 30], more than 3000 frames in one response (cameras × fps × seconds, depth counts double), malformed body |
| 409 | episode already finished (`done`); the trial is over |
| 413 | body over 64 MB (`rcb_client.py` raises before sending such a body) |
| 500 | simulator error; the episode ends with `reason = "error"` (the client raises `EpisodeOver`; the verifier reports `sim_error = 1`) |

## Episode semantics
The service starts the episode when it is ready (seed hidden inside). The first success ends it; otherwise it ends
when the agent phase ends (`timeout`) or on an error. The predicate is evaluated once more at episode end. No reset.

**Service crashes (no reset, no lost episode).** Every executed physics step is journaled (`trajectory_live.f64`) and every
completed call logs a checkpoint (step count + state hash) in `episode.jsonl`. If the service dies mid-episode, compose
restarts it (`restart: on-failure:6`) and it **resumes the same episode**: it replays the journal up to the last checkpoint,
checks the state hash, and continues. The call that was in flight is lost as a whole (its caller got a connection error or
5xx, not a result, so nothing is learned); `spec.on_service_error` tells the agent to check `GET /status` before continuing.
More than 2 crashes end the episode: `reason = sim_crashed_on_call` if every crash happened while serving a call (counted as
the agent's failure), else `sim_crashed` (`infra_error = 1`). A verdict already written is never overwritten. A crash before
the service is ready is a plain restart; a scene build that hangs is killed by a startup watchdog (`RCB_STARTUP_TIMEOUT_S`,
300 s) so compose retries it.

## Evidence and grading (agent never sees this)
`/data/episode.jsonl` (one record per call: type, rows, dt, cameras, note, clipped, plan, physics steps, success),
`/data/calls/NNNNNN/` (meta + last frames per call), and on end: `trajectory.npz` (T, 34), a fresh replay
(`replay_success`, `deterministic`), `replay.mp4` (six-view), `final.json`. The collect hook signals the service by PID
after the agent container is stopped; a separate verifier grades `final.json`: `success = live ∧ replay ∧ deterministic`,
reward fields as in PROTOCOL §2.6 and §4.8.

## Live recording (sidecar only; the agent sees none of it)
- `live.mp4`: the episode as six views (world / observer / head · front / left wrist / right wrist, 213×160 tiles), each
  frame stamped `wall mm:ss  sim s  #call what-the-agent-sent`. Frames are sampled every `250 / RCB_LIVE_FPS` physics
  steps (default 10 per simulated second) **only inside calls that ran physics** (a `/submit` chunk or an `/observe`
  watch window), so the agent's thinking time takes no frames; with `RCB_LIVE_FILTER=moving` (default) frames are also
  skipped while nothing moves (max change of all poses / joint states below `RCB_LIVE_MOVE_EPS`, 1e-3).
- Capture (`RCB_LIVE`): **`replay`** (default) logs only call boundaries during the episode (no cost to the agent) and
  renders `live.mp4` at episode end from the recorded trajectory; the simulation is bit-exact deterministic, so it is the
  same motion. `realtime` renders while the episode runs (the video survives a crash, but each frame costs ~150 ms of
  the agent's wall clock: a 10 s chunk took 20.6 s instead of 5.1 s). `off` disables it.
- `live_segments.jsonl` (per call: call, label, physics-step range, wall-clock start/end) and `live_timeline.jsonl`
  (per frame: frame, wall_s, sim_step, call, label) map every frame back to `episode.jsonl`.
- `calls/NNNNNN/actions.npy`: the exact action array of every `/submit` (float32, as sent).
- `trajectory_live.f64`: the recorded (T, 34) trajectory appended after every call (raw float64). With
  `live_segments.jsonl` it is enough to render the video offline if the container dies before the end.
- `startups.jsonl`: one line per service start; `resumed` / `restart_refused` events in `episode.jsonl` record crash
  recovery (see Episode semantics).
All are sidecar artifacts; the verifier copies `live.mp4` and `live_timeline.jsonl` next to `replay.mp4` (which stays the
authoritative video) and reports `live_video`, `live_frames`, `sim_startups`, `infra_error`.

## Proprioception (2.1)
82 columns, grouped in `spec.proprio_groups` (first column, count, meaning). 2.0's 30 columns are unchanged at 0–29;
2.1 appends what a real arm reports and 2.0 lacked:
| columns | group | source |
|---|---|---|
| 0–13 | `joint_cmd` | commanded drive targets + gripper command |
| 14–27 | `ee_pose` | measured end-effector link pose (RoboTwin ee frame, 0.12 m behind the TCP) |
| 28–29 | `gripper_cmd` | commanded gripper value |
| 30–43 | `joint_pos` | measured joint positions (articulation qpos) + measured gripper opening, from the finger joint mapped to the command's [0,1] units (clipped to [-0.2, 1.2]); the grasp signal a real gripper gives |
| 44–55 | `joint_vel` | measured arm joint velocities |
| 56–69 | `tcp_pose` | measured gripper-centre pose (RoboTwin `get_*_tcp_pose`) |
| 70–81 | `joint_effort` | stiffness·(target−q) + damping·(v_target−q̇) per arm joint: the PD drive's effort, a motor-current analogue |
Not exposed (simulator privilege): object poses, segmentation, contact forces on objects, the success predicate.

Depth (`include_depth`, head/front/wrist cameras) is exact by default. `RCB_DEPTH_NOISE=realsense` (task env) adds
stereo-camera-like noise, σ = 2 mm + 2.5 mm·z² (z in m), and 1 % dropouts (0 = no reading), seeded by
`RCB_DEPTH_NOISE_SEED`; it never affects physics.

## MuJoCo tasks (DexToolBench, MuJoCo Playground)
Same endpoints and RCB1 frames, served by `images/mujoco/limited/server_mj.py`. Differences: one action type,
`joint_position` with the task's own actuator layout (DexToolBench 29, ALOHA 14, Panda 8), rows `dt` apart where `dt`
is a multiple of `control_dt` (1/60 s DexToolBench, 1/50 s Playground), hold or linear interpolation per control step.
Actions are sent as **float64** (MuJoCo on CPU replays bit-exactly, and float32 rounding changes a chaotic tool swing).
`meta.task` carries the task definition (DexToolBench: current goal pose and index; Playground: the target) and
`meta.cameras` each camera's intrinsics and camera-to-world pose. DexToolBench's own eval gives each goal 10 s; here the
standard twins have **no per-goal limit** (one episode, no reset) and an episode cap of 360,000 control steps (100 min of
robot time, `spec.max_control_steps`; the 60 min agent budget ends first), while the privileged tasks give each goal 30 s
(replayed offline, free resets). DexToolBench episodes end when all goals are reached, at the cap, or when the agent's
time is up; Playground episodes run to the end of the agent phase and the final state is graded. The MuJoCo service
journals and resumes exactly as above (journal `record.f64`).
The service replays the recorded episode in a fresh simulator at the end (`deterministic`: same final state hash).

## KinDER and HumanoidBench tasks
Same endpoints, RCB1 frames and crash recovery, served by one shared service (`scripts/{kinder,humanoidbench}/shared/standard/rcb_service.py`,
identical in both) with a per-benchmark simulator adapter (`server.py`). Actions are delta or joint-position rows at the
task's control rate (KinDER 10 Hz, PyBullet tasks kinematic: a refused move comes back `blocked` and stops the chunk;
HumanoidBench 50 Hz); the step counters are `rows` and `control_steps`. No world coordinates are given (odometry and
camera poses are in the robot's starting frame); see [docs/benchmarks/](benchmarks/) for the per-benchmark observation
tables. A request body over 64 MB gets 413 before it is decoded.

## Optional reset capability
Off by default (`budget.reset = 0`): one trial is one episode. Exception, by owner decision (PROTOCOL §4.5): HumanoidBench's
standard tasks default to `budget.reset = 50` (2026-10-07). A run may set `RCB_RESET_BUDGET=N` on the service
(implemented by the KinDER and HumanoidBench services). Then `/spec.budget.reset = N`, `/spec.reset` describes it, and
`POST /reset` (RCB1 or JSON `{cameras, video}`, no physics) abandons the running episode and starts a new one from the
same frozen state, `N` times in all; `/status` and `meta` add `episode`, `resets_left` and `control_steps_total`. After a
success or once the agent's time is up, `/reset` returns 409, as it does when the budget is spent. Only the last
episode is graded. Results with `N > 0` are reported separately and never ranked with `N = 0` (PROTOCOL D1, §4.5).

## Standard-realtime mode: `eai-standard/2.3`
Time does not stop. The wire protocol of the standard-realtime mode (PROTOCOL §4b, v1.1; protocol-change issue #86), served by
standard-realtime tasks only (`<base>-standard-realtime`, `mode = "standard-realtime"`, `protocol = "eai-standard/2.3"`; implemented by HumanoidBench's,
`scripts/humanoidbench/shared/realtime/rcb_realtime.py`). 2.3 is 2.2 plus the realtime capability below; every 2.2
addition stays a MAY, so a 2.1 service with this capability is a 2.3 service. Same endpoints, RCB1 frames, crash
recovery and grading as 2.1. `/spec.timing` declares it: `realtime: true`, `slowdown` S (`RCB_SLOWDOWN`, default 1 = real
time; results with S ≠ 1 are reported separately from S = 1), `control_dt`, `wall_s_per_control_step`, `max_ahead_steps`.
Defaults of the mode (owner, 2026-10-08): `budget.reset = 50` (the reset capability above; `RCB_RESET_BUDGET` overrides
it), S = 1.
- **Clock.** An episode starts paused at its starting state. Its clock starts at its first `/submit` or `/observe`
  with `seconds > 0` (after a reset, and after a crash recovery, the episode is paused again) and runs one control step
  every `control_dt` × S seconds of wall time, whatever the agent does, until the episode ends.
- **`/submit`** answers at once. The chunk is expanded into control steps exactly as in 2.1 (`dt`, `linear` / `hold`) and
  becomes the plan from control step `at` (an integer of the episode; absent: the next step; at most `max_ahead_steps`
  ahead), replacing what was planned from `at` on and keeping what is planned before it; `linear` starts from the target
  in force just before `at`. Rows for steps that have run when the request arrives are dropped. When the plan runs out,
  the last target is held (zero-order hold). `meta` adds `start_step`, `late_steps`, `plan_end_step`; every `meta` and
  `/status` add `running`, `planned_steps`, `lag_s`. The answer carries the frames and proprioception of now, no video.
- **`/observe`** with `seconds = 0` answers at once; with `seconds > 0` it waits while that much robot time runs and
  returns what the cameras saw (2.1's video, frames, proprio rows); it never changes the plan. `cameras: []` asks for
  no images, only proprioception.
- **Grading** is 2.1's: the journal holds the sim row the simulator applied at every control step, and the graded
  episode's rows are replayed in a fresh simulator, so the replay equals the live run whatever the timing. Evidence
  added: `ticks.f64` (per journal row: wall time, the call whose chunk gave the row, -1 when held), `calls.jsonl` and
  `submitted.f64` (one line per call and every row as sent, instead of `calls/NNNNNN/`), and in `final.json`
  `realtime`, `slowdown`, `max_lag_s`, `stalls`, `held_steps`, `late_steps`.
- **Service.** The simulator's thread runs a due control step before any waiting request; behind the clock it runs the
  missed steps back to back, and more than 0.5 s behind it drops the debt (a stall, counted) instead of fast-forwarding
  the robot. Checkpoints every second of robot time while the clock runs; a crash resumes the same episode, paused.
- **Crashes are infrastructure.** No call spans a crash (`/submit` answers at once), so a crash is never put down to the
  agent: past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed`, a failed resume `resume_failed`, and a simulator
  error that ends the graded episode (`reason = "error"`) is one too; `final.json` carries `infra_error = 1` in all three.
- **Agent code** runs where it does in standard mode, in the agent's own container: a controller that streams targets
  through the client, not code uploaded next to the simulator.

The time model matches the one proposed for the Embodied Agent Olympiad's `eai-standard-realtime/1.0` (PR #41: the
world runs at 1/S of real speed, a command takes effect at the next control step and replaces the one under way, all
agent latency counts, the agent's own program may act) and uses its `slowdown` name. It stays inside 2.x: no `/start`,
`/act`, `/wait`, `/ready`, seats, reviews or metering proxy; native agents only (PROTOCOL D11).

## Versioning
`protocol` in `/spec`. 1.0 (`/step` with one action and base64 images) is retired; 2.0 = `/submit` + `/observe` + RCB1; 2.1 = 2.0 + measured proprioception (82 columns) + optional depth noise + crash recovery; `eai-standard/2.1` is the v1.0 name of 2.1. Minor versions only add; the 2.x client accepts every 2.x version under both spellings. Accepted, pending: `eai-standard/2.2` (PROTOCOL §6). `eai-standard/2.3` (2026-10-08) = 2.2 + the realtime capability, the standard-realtime mode's protocol (above). `eai-standard/2.4` (2026-10-08) = 2.3 + the operations capability (operation ids, request deadlines, `GET /operations/<id>`, call watchdog, tick ledger; [STANDARD_MODE_2_4.md](STANDARD_MODE_2_4.md)), for standard tasks.
