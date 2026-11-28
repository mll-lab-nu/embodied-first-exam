# The `eai-standard/3.0` wire protocol

In the standard and realtime modes the robot is a service. It runs in a `sim` sidecar the agent cannot open, and the
agent reaches it over HTTP. Every such service answers `/spec.protocol = "eai-standard/3.0"`, and every standard and
realtime task declares `[metadata] protocol = "eai-standard/3.0"`. What a service serves beyond the base is said by
the capabilities in its `/spec`, never by a version string.

This document says what a service answers and what a client may send. The trust-boundary rules (no simulator, state
or success predicate in the agent's reach; the verdict from a trusted record) are invariants H.3 and H.4 in
[invariants.md](invariants.md). Each benchmark's own service details (its robot, action types, cameras,
proprioception columns, resume class, measured start-up times, known issues) are in `tasks/<benchmark>/README.md`.
How the service layers implement this document is in
[embodied_first_exam/standard/README.md](../../embodied_first_exam/standard/README.md). The HTTP interface is also
written out as OpenAPI 3.1 in [eai-standard.openapi.yaml](eai-standard.openapi.yaml).
`ci_checks/check-openapi-contract.py` runs the reference services and checks their answers against it.

## Capabilities

| Capability (`/spec`) | What it adds |
|---|---|
| base | `/spec`, `/status`, `/observe`, `/submit`, `/finish`; RCB1 responses; measured proprioception; optional depth noise |
| reset (`budget.reset > 0`) | `POST /reset`, within the task's reset budget |
| shared (`kinematics`, `robot_spec`, `world`, `max_call_wall_s`) | depth modes `last` / `frames`; per-frame steps, times and extrinsics; camera intrinsics and mounting; the robot's spec sheet; world conventions; `POST /kinematics`; a per-call wall-clock bound |
| realtime (`timing.realtime = true`) | a clock that does not stop |
| operations (`operations = true`) | operation ids, request deadlines, `GET /operations/{id}`, a call watchdog, a physics-tick ledger |
| match (`match`) | the match's own calls `/start`, `/ready`, `/say`, `/team`, and its score in `meta` |

Every capability is optional. A request written for the base gets the same answer from every service, plus parts and
keys a client may ignore. Which benchmarks serve which capabilities is in their READMEs.

## Connecting

- Base URL: `http://sim:8000` on the compose network, or `http://localhost:8000` when Harbor's egress control puts the
  service in the agent's network namespace. The shipped clients try both.
- The socket opens only when the scene is ready. Until then connections are refused and the client retries.
- A readiness probe added to a compose file or a runner must not send a request to the service before the agent runs.
  Connecting to the port is enough.
- Video, frames, depth and proprioception come back as **binary** in the response body (RCB1 frames), never base64.
  The agent's code decides what to keep.

## Rules on every service

- **Standard mode is Gym's `env.step`.** The world stands still between calls. `/submit` blocks until its chunk has
  run. It answers with the chunk's video (as asked), its proprioception and `meta.duration_s`, the robot seconds it
  ran. `planned_duration_s` is what it declared: rows × `dt`, or the planned duration of a planner type such as
  `ee_pose` where the service knows it.
- **A hold chunk lets time pass.** `/submit` with `{"type": <type>, "interpolate": "hold", "seconds": n}` and no rows
  holds the target in force (the last command) for n seconds of robot time. That is whole control steps, at least
  one, at most `max_chunk_s`. It answers as any `/submit`, with `meta.hold = true` and `executed_rows = 0`. Rows and
  `seconds` together (any value, 0 too), or no rows without a hold, are a 400.
- **`max_chunk_s`** is the one cap of a chunk and of a hold chunk.
- **`/observe` only reads.** It never lets time pass, never waits and never changes the plan. `seconds > 0` is a 400
  that names the hold chunk.
- **Realtime.** The clock starts at the episode's first `/submit` ([Realtime](#realtime)).
- **`/finish`** ends the episode ([Agent-ended episodes](#agent-ended-episodes)). The match extension is the one
  exception: a match ends by its rules, and its `/finish` is a 404.
- **Every agent-facing endpoint has an MCP tool** ([MCP tools](#mcp-tools)).
- **The shipped clients** have `get_obs(last_s=0)`, `hold(seconds)`, `submit(...)` and `finish()`.
  `get_obs(seconds=...)` raises and names `hold`.

## RCB1 frames

```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```

- Requests over 64 MB are a 413. The client refuses to send one.
- A response over 256 MB drops parts and says so in `meta.degraded`: per-frame depth first, then `frames/`. The mp4,
  the last frames, the last depth, the proprioception and the per-frame arrays always stay.
- `rcb1.py` (encode and decode; `python -m rcb1 unpack f dir`) ships with the client.

**Response parts.** Every recorded frame of a call has one entry on one shared frame axis N.

| Part | Kind | Content |
|---|---|---|
| `video/<cam>` | mp4 | H.264 of the N frames (`video` = `mp4` or `both`) |
| `frames/<cam>` | array uint8 (N,H,W,3) | the raw frames (`video` = `frames` or `both`) |
| `last/<cam>` | array uint8 (H,W,3) | the last frame, always |
| `proprio` | array float32 (N,D) | one proprioception row per frame, columns `spec.proprio_layout` |
| `frame_step` | array int64 (N,) | the control step of each frame |
| `depth/<cam>` | array float16 (N,H,W) | z-depth of every frame in metres; a request with `include_depth: true` and no `depth` field |
| `cam2world_gl/<cam>` | array float64 (N,4,4) | the pose of a moving camera at each returned frame (OpenGL axes) |
| `frame_time_s` (shared) | array float64 (N,) | simulated time of each frame, `frame_step / control_hz` |
| `extrinsic_cv/<cam>` (shared) | array float64 (N,3,4) | world → camera (OpenCV axes) at each frame |
| `last_depth/<cam>` (shared) | array float32 (H,W) | z-depth of the last frame in metres (`depth` = `last` or `frames`) |
| `depth_frames/<cam>` (shared) | bytes, `codec: "zlib"`, `dtype: "uint16"`, `shape: [N,H,W]`, `unit: "mm"` | z-depth of every frame (`depth` = `frames`); the client decodes it to float32 metres |

**Frame stride.** A call captures its first frame, one frame every round(step rate / `video_fps`) steps, and its last
frame. The step rate is the service's control rate, `control_hz`. A service that states only a physics rate and
steps physics once per command row (RoboTwin's, with `physics_hz`) counts physics steps instead. The frame count of a
call is of the frames really captured at that stride, not of the requested rate.

## Endpoints

| Method | Path | Body | Answer | Where |
|---|---|---|---|---|
| GET | `/spec` | — | JSON | every service |
| GET | `/status` | — | JSON | every service |
| POST | `/observe` | RCB1 or JSON | RCB1 | every service |
| POST | `/submit` | RCB1 (or JSON on a match) | RCB1 | every service |
| POST | `/finish` | optional, ignored | JSON | every service but a match |
| POST | `/reset` | RCB1 or JSON `{cameras, video}` | RCB1 | a reset budget N > 0 |
| POST | `/kinematics` | JSON | JSON | the shared capability, where the service has a kinematic model |
| GET | `/operations/{id}` | — | JSON | the operations capability |

Anything else (`/state`, `/success`, …) is a **404**. So is `/reset` without a reset budget, and `/kinematics` on a
service without it.

### `GET /spec`

The robot's facts. Fixed for the service's life. Base keys:

- `protocol` (`"eai-standard/3.0"`), `simulator`, `robot`, `task_text`;
- `control_hz` or `control_dt`, `physics_substeps` (or `physics_hz`), `max_chunk_s`, `max_video_fps`,
  `max_frames_per_call`, `max_control_steps`;
- `cameras`, `action_types` (dims, layouts, limits, semantics; `not_yet` lists types not offered yet),
  `proprio_layout`, `proprio_groups`;
- `static`: scene facts such as names, sizes and colours, never a position;
- `budget`: `{"reset": N, "steps", "wall_clock_s", "clock"}`. `clock` says what `time_s` and `time_left_s` count from;
- `success_signal`: says the success is hidden ([Agent-ended episodes](#agent-ended-episodes));
- `timing`: what `/submit` and `/observe` do, and the recorder (`timing.recorder`, [The recorder](#the-recorder));
- `on_service_error`: what to do after a connection error or a 5xx.

The shared capability adds `default_cameras`, camera intrinsics and mounting, `robot_spec`, `world`, `kinematics`,
`depth` and `max_call_wall_s` ([The shared capability](#the-shared-capability)). The realtime capability adds keys
under `timing` ([Realtime](#realtime)). The operations capability adds `operations: true`. A match adds `match`,
`endpoints` and `timing.deviations`.

### `GET /status`

Counters of the episode, no images:
`calls`, `control_steps` (or `step` and `physics_steps` on a benchmark's own service), `done`, `reason`, `elapsed_s`.
With a step limit it adds `step_limit` and `steps_left`. With a reset budget it adds `episode`, `control_steps_total`
and `resets_left`. The shared layer adds `resumes`. It is never refused after `/finish`. The shipped client's
`wait_ready()` polls it after a connection error. It has no MCP tool: its fields come back in every `meta`.

### `POST /observe`

Request (JSON or an RCB1 header): `{cameras, last_s, video_fps, video, depth, include_depth}`.

- `last_s = 0` (the default) returns the current frame and the proprioception of now.
- `last_s = n` returns the frames recorded in the last n robot seconds (at most `buffer_s`), `video_fps` apart, with
  the proprioception of their steps. `meta.last_s` says what they cover. With nothing recorded yet it returns the
  current frame.
- Per-frame depth with `last_s > 0` (`include_depth`, or `depth: "frames"`) is served only when every requested
  camera's depth is kept by the recorder (`/spec.timing.recorder.depth`). Otherwise it is a 400 that says to ask for
  depth with `last_s = 0`.
- `depth: "last"` with `last_s > 0` is not refused. It returns the current frame's depth, which is not the
  recorder's.
- Observing runs no physics and costs no budget beyond the wall clock.

### `POST /submit`

Request: an RCB1 header `{type, dt, interpolate, cameras, video_fps, video, depth, include_depth, note}` and a part
`actions`, float32 (T, dim). A hold chunk is the header `{type, interpolate: "hold", seconds, ...}` with no part.

- `joint_position` rows are `dt` seconds apart. `dt` is a positive whole multiple of the control step; anything else
  is a 400, never rounded. A service may cap `dt` further and says so in its README.
- The service streams drive targets with `interpolate = "linear"` (default) or `"hold"` between rows, as a real
  controller consumes a chunk.
- Out-of-limit values are clipped and reported in `meta.clipped`. Continuous joints have `null` limits and are never
  clipped.
- A chunk's rows × `dt` is at most `max_chunk_s`. A planner type such as `ee_pose`, whose duration the service plans,
  is not counted that way.
- Planner types such as `ee_pose` state their frame, quaternion order and end-effector reference in `/spec`. A failed
  plan is reported in `meta.plan`, not as an error.
- The action layout, the action types and their dtype are the benchmark's.
- The chunk is appended to the recorded trajectory and the call log. A success ends nothing and is not shown.

### `POST /finish`

Ends the episode (`reason = "finished"`) and answers `{"ok": true, ...}` with `/status`'s fields. Its body is optional
and ignored: no service parses it. Clients send `{}`, and an empty body is accepted too. Its `Content-Length` is
checked as every POST's (over 64 MB: 413; negative: 400). After it, every call but `GET /spec` and `GET /status` is a
409, and `resets_left` is 0.

### `POST /reset` (reset capability)

- A task declares its own reset budget N: the `RCB_RESET_BUDGET` default of its `sim` service, stated in its
  instruction. The default is 0.
- With N > 0, `/spec.budget.reset = N` and `/spec.reset` describes the capability. `POST /reset` (RCB1 or JSON
  `{cameras, video}`, no physics) abandons the running episode and starts a new one from the same frozen state, N
  times in all. `/status` and `meta` add `episode`, `resets_left` and `control_steps_total`.
- With N = 0, `/reset` is a 404.
- After `/finish`, or once the agent's time is up, `/reset` is a 409, as it is when the budget is spent. After the step
  cap or a failure end it is allowed while the budget lasts. A success changes nothing.
- Only the last episode is graded.
- The reset budget is part of a result's configuration: results with different budgets are not ranked together.
- Who serves it: the sidecar and realtime layers serve `/reset` with a budget. The shared and operations layers have
  no `/reset` of their own; an adapter that grants resets adds it. The sidecar and realtime clients have
  `r.reset()`. The shared client has none: an instruction whose task has a budget calls `POST /reset` through
  `Robot._post`.

### `POST /kinematics` (shared capability)

Stateless: the answer depends only on the request. It never steps physics, never advances time, never ends the
episode and costs only wall clock. It uses the robot's kinematic model (the same as the `ee_pose` action and the
camera mounts), with no collision checking.

| Request | Answer |
|---|---|
| `{"op": "fk", "q", "links"?, "base_pose"?}` | `{"ok": true, "op": "fk", "frame", "poses": {link: [x,y,z, quaternion]}}` |
| `{"op": "ik", "targets": {frame: pose}, "seed"?, "base_pose"?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}` | `{"ok", "op": "ik", "frame", "q", "error": {frame: {"pos_m", "rot_rad"}}}` |

`spec.kinematics` lists `endpoint`, `joint_names` (the q layout, each a `proprio_layout` column), `frame` (`world`, or
`base` for a mobile robot unless the request gives `base_pose`), `base_pose_proprio`, `quaternion_order`, `links`,
`tcp_frames`, `ee_frames`, `ik_targets` and `ik` (solver, defaults). A malformed request is a 400. No solution is
`ok: false`, never an error.

### `GET /operations/{id}` (operations capability)

See [Operations](#operations).

## `meta`

Every response carries `meta`:

- `step` (or `rows` on the sidecar layer), `calls`, `control_steps` (or `physics_steps`), `sim_time_s`;
- `time_s` and `time_left_s`, the agent's clock ([The agent's clock](#the-agents-clock));
- `proprio = {"layout": [names], "now": [floats]}`;
- `cameras`: per camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl` (and `image_size` on the shared layer). It is
  the calibration of the state the response ends in. An adapter that reads `RCB_OBS_CALIBRATION` leaves it out when
  the task sets it to 0. The sidecar layer sends none;
- `done`, `reason`.

| Answer | Adds |
|---|---|
| `/submit` | `chunk_id`, `type`, `executed_rows`, `control_steps_chunk` (or `physics_steps_chunk`), `duration_s`, `planned_duration_s`, `hold`, `clipped` `[{row,index,reason}]`, `n_clipped`, `plan`, `frame_step` (with images), `ok`; the shared layer adds `stopped` |
| `/observe` | `obs_id`, `last_s`, `frame_step` (with images), `seconds` (always 0), `control_steps_watch` (always 0), `ok`; the shared layer adds `stopped` |
| `/reset` | `frame_step` (with images: the new episode's first step), `ok` |

`frame_step` is the control step the newest image shows. No `meta` and no `/status` carries a success or progress
field.

## Errors

No physics runs on an error.

| Code | When |
|---|---|
| 400 | a malformed body; wrong type or dim; a chunk with no rows (other than a hold chunk); a hold chunk with rows; `/observe` with `seconds > 0`; NaN or inf; `dt`, `seconds`, `video_fps` or `last_s` not a finite JSON number (`true`, `false` or a string are refused; `null` is the default); `cameras` not a list; `dt` or `seconds` out of range, or `dt` not a multiple of the step; a chunk too long; an `interpolate` or `video` value the service does not know; `video_fps` outside [1, `max_video_fps`]; more images than `max_frames_per_call`; a negative `Content-Length` (answered without reading the body) |
| 404 | an endpoint the service does not serve |
| 409 | the episode is over: after `/finish` every call but `GET /spec` and `GET /status` (`GET /operations/{id}` included); after another end `/submit` and `/finish` are 409 while `/observe` still answers; a service that gave up answers every request with 409 `{"gave_up": true, "reason", "infra_error"}` |
| 413 | a body over 64 MB, `/finish`'s too |
| 500 | a simulator error; the episode ends with `reason = "error"`; the client raises `EpisodeOver`; the grader reports `sim_error = 1` |

Each 400 leaves the episode as it was. `video_fps` lies in [1, `max_video_fps`]: 30 on the sidecar and realtime
layers; on the shared and operations layers `/spec.max_video_fps` where the adapter declares it, else the larger of
30 and `control_hz`.

## Images per call

Every call that returns images has a per-call image budget, `max_frames_per_call`, stated in `/spec` and in the
instruction.

- **What counts.** Each camera frame is one image, and a depth frame one more. The count is of the frames the service
  really captures at its stride ([Frame stride](#rcb1-frames)). `video = "mp4"` or `"frames"` changes what is sent,
  not the budget.
- **Checked before the call.** A call over the budget is refused with a 400 that says so, and nothing runs.
- **Calls of unknown length.** A call whose length is known only while it runs (`ee_pose` rows, a chunk the service
  plans) stops filming at the budget instead. The motion goes on, its last frame is always taken, and
  `meta["frames_skipped"]` counts the frames left out. The trial's video still has them.
- **Memory.** Building a response holds the captured frames plus one response body. The service's memory cap covers
  the largest response the budget allows ([resources.md](resources.md#how-a-rules-caps-are-chosen)).
- **Realtime.** Answers not yet sent count against one budget together, and at most 8 answers with images are
  outstanding. A call is never refused for its images: past the budget, or with 8 answers outstanding, its answer
  comes without its frames and `meta["frames_skipped"]` is set.

## The recorder

`/spec.timing.recorder` declares `cameras` (every camera), `fps`, `buffer_s` (`RCB_LOOKBACK_S`, default 3), `records`
(when it records) and `depth` (the cameras whose depth it keeps).

- **Standard mode:** 10 fps (`RCB_CAMERA_FPS`, default 10). It records while a `/submit` runs, hold chunks too: every
  1 / `fps` of robot time, the RGB image of every camera and the proprioception, into a ring of the last `buffer_s`
  seconds (`records: "during /submit"`, `depth: []`). The ring is cleared at a reset. It has no process of its own.
- **Realtime mode:** 30 fps (`RCB_CAMERA_FPS`, default 30), recording while the clock runs, with the depth of the depth
  cameras ([Realtime](#realtime)).
- The recorder can be turned off (`Service(record_frames=False)` on the shared layers, `record_frames` on the
  sidecar). `/spec.timing.recorder` then says it records nothing (`cameras: []`), and `last_s` answers the current
  frame.
- With the sidecar's `record_frames = "delivered"`, a recorded frame holds the images the agent was sent at that step,
  and `last_s` returns only frames that hold every requested camera.

## Episodes

The service starts the episode when it is ready. The seed stays inside. One trial is one episode, unless the task
declares a reset budget.

### Agent-ended episodes

Every standard and realtime episode is agent-ended. `normalize` writes `RCB_AGENT_END: "1"` in the `sim` service's
environment, and `ci_checks/check-agent-end.py` checks it.

- **Hidden success.** `/spec.success_signal` says the success is hidden. No answer depends on the task's success: no
  `done` or `reason = "success"`, no 409, no early end of a chunk, no per-call work caused by it, no success or
  progress field of the service's own (stages reached, a settled-check counter). `resets_left` and `/reset` behave as
  before a success.
- **Who ends it.** The agent, with `POST /finish` (an MCP front end: its `finish` tool). A success does not end the
  episode.
- **Other ends.** The episode ends at whichever comes first:
  - `/finish`;
  - the step cap ([The step cap](#the-step-cap));
  - the end of the agent's session: its time limit, its token budget or its own exit. The collect hook's signal ends
    the episode with `reason = "timeout"`;
  - the task's failure rule, or a simulator error (`reason = "error"`).
- **The verdict.** The task's own success rule on the state the episode ended in. A settle or hold window the task
  declares runs from there on the live simulator, after the agent is gone. A hold window counts the steps already
  held. A success reached and then undone is 0.
- **Events.** A goal the task judges as events (a referee's call, moments in a sequence such as key strikes, a check
  at a trigger) is judged on them as they happened. The task says which kind it is.
- **Failure rules.** The task's failure rules keep running to the end. On a goal judged on its end state, a failure
  rule that ends the episode gives 0, after a success too. On a goal judged as events, an event that happened stands,
  and a failure rule ends the episode with the events reached so far.
- **Realtime.** `/finish` stops the clock with the episode. A settle or hold window runs after it, off the clock.
- **Resets.** As before a success. After `/finish` or the session's end `/reset` is a 409. After a failure end or the
  step cap it is allowed while the budget lasts. Only the last episode is graded.
- **The record.** `final.json` adds `success_signal = "hidden"`, `ended_by` (`finish`, `step_limit`, `session_end`,
  `failed` for the task's own failure rule, `error`), `hidden_success_seen`, `hidden_success_first_step`,
  `trial_hidden_success_seen`, `finish_time_s`, and with a step limit `step_limit` and `steps_used`. `reward.json`
  adds `ended_finish`, `ended_step_limit` and `ended_session_end`, as evidence only.
- **Which limit ended a session** is the runner's record: Harbor's `AgentTimeoutError` for the time limit, the
  gateway's `budget_stop` for the token budget. Over the token budget, an agent-ended task is graded on its end
  state, not failed on top (`scripts/write_task_results.py`).
- A client that never calls `/finish` has its episode ended by its session's end.

The match extension is exempt: a match ends by its own rules ([Match extension](#match-extension)).

### The step cap

- `/spec.max_control_steps` is the episode's step cap: the service's own episode length, lowered to `RCB_STEP_LIMIT`
  when the task sets one. Without either, the episode has no step cap.
- With `RCB_STEP_LIMIT`, `/spec.budget.steps` states the same number (the lower of `RCB_STEP_LIMIT` and the service's
  own cap), and every `meta` and `/status` add `step_limit` and `steps_left`. What one step is, the service's `/spec`
  and the instruction say.
- At the cap the layer ends the episode by itself (`reason = "step_limit"`, through the adapter's `end_step_limit`).
  The call that reaches it, a hold chunk too, stops at that step, and its answer says so (`done`, `reason`, a
  `duration_s` of the steps run). A service whose own cap ends the episode first is not ended again.
- After the cap `/submit` and `/finish` are 409, and `/observe` still answers.
- The episode is graded as it stands. The instruction's Limits states the cap in its Steps line ("at most N control
  steps, then the episode ends.").
- Otherwise the agent's wall-clock time is the real limit. Actions and simulated time are reported as cost.

### The agent's clock

- `meta.time_s` is the wall time since the agent's **first request** to the service, whatever the endpoint.
  `GET /spec`, which the shipped clients send first, counts.
- `meta.time_left_s` = `spec.budget.wall_clock_s` − `time_s`, never below 0. `wall_clock_s` is `RCB_WALL_CLOCK_S`,
  the task's cutoff.
- The clock does not start with the service, when the scene is ready, or with a probe that only connects to the port.
- The first request is logged (`first_request`). A restarted service reads it back, so a restart never sets the clock
  back to full.
- Why: Harbor counts the agent's cutoff around the agent's run only, and the sidecar starts with the environment,
  before the harness is installed. With this rule `time_left_s` never runs out before the agent is stopped. The
  agent's real time left is `time_left_s` minus what it spent before its first request.
- `/spec` says what the clock counts from: `budget.clock` (the sidecar layer in its top-level `clock`).
- `GET /status` `elapsed_s` and the `elapsed_s` of `final.json` count from the agent's first request on the sidecar
  and realtime layers. On the shared and operations layers they are the episode's own time, from the service's start
  of the episode.
- A service that ends an episode on its own clock says so in its benchmark's README.

### Service errors

- `spec.on_service_error` tells the agent what to do after a connection error or a 5xx: the service may have
  crashed and resumed the same episode (never a reset). Check `GET /status` (client: `Robot.wait_ready()`) and its
  `calls` and `control_steps` before continuing.
- A service that cannot go on (too many crashes, a failed resume, an episode refused at its start) answers every
  request, `GET /spec` and `/status` included, with 409 `{"gave_up": true, "reason", "infra_error"}`. The client's
  `Robot()` and `wait_ready()` then raise `EpisodeOver` at once.
- How the reference services journal, checkpoint and resume an episode is an implementation, not a rule
  ([embodied_first_exam/standard/README.md](../../embodied_first_exam/standard/README.md#crash-recovery)). What the
  protocol says about a trial that failed for infrastructure reasons is the runner's rerun (H.5).
- A host on which the frozen instance does not rebuild to its stored initial state reports
  `reason = "instance_mismatch"` with `infra_error = 1`.

### Evidence and grading

The agent never sees any of this.

- The service records every call: `/data/episode.jsonl` (one record per call: type, rows, dt, cameras, note, clipped,
  plan, steps) and `/data/calls/NNNNNN/` (meta and last frames per call).
- At the end it writes `trajectory.npz` (the graded episode, the deliverable), `final.json`, then the video.
- The collect hook signals the service by PID after a collect hook has stopped the agent's processes. From then on
  the service refuses every request that would run the simulator.
- The service judges the episode it ran, with the task's success rule and any settle or hold window run on the live
  simulator. It writes the verdict into `final.json`: `success` (the verdict), `live_success` (how the episode itself
  ended, before any settle or hold check), `graded_by = "live"`, `replays = 0`. Nothing is replayed to grade it.
- The video is a post-hoc replay of `trajectory.npz` after the verdict by default. Where the simulator is not verified
  bit-wise replayable it is a live recording (`video_source`). It never decides anything.
- With resets, the shared sidecar grader also keeps the first episode: `trajectory.first.npz` and `replay.first.mp4`.
  `final.json` says how it ended (`first_success`, `first_reason`). It decides nothing. A benchmark's own service
  keeps no first episode and reports `resets` only; `first_success` is then `success` without a reset, else 0.
- A separate verifier transcribes `final.json` into `reward.json` (`graded_by_live = 1`).
- `infra_error = 1` means there is no verdict on the agent: `final.json` is missing, unreadable or not finalized, or
  the service reported `sim_crashed`, `resume_failed`, `instance_mismatch`, `call_watchdog` or `gpu_lost`.

## Proprioception and depth

- A benchmark's own columns come first. Then come what a real robot reports: measured joint positions and velocities,
  the gripper opening, the tool-centre pose, a drive-effort estimate. They are grouped in `spec.proprio_groups`
  (first column, count, meaning).
- Every shared-layer service has at least the groups `joint_pos`, `joint_vel`, `gripper_opening` (metres between the
  fingertips), `tcp_pose` (7 columns per `kinematics.tcp_frames` entry) and `joint_effort` (the PD drive-effort
  estimate, or the simulator's measured effort).
- Never exposed: object poses, segmentation, contact forces on objects, the success predicate (H.3).
- Depth is z-depth: the distance from the camera plane along the optical axis, in metres, for the same pixels as the
  RGB frame. 0 means no reading.
- Depth is exact by default. `RCB_DEPTH_NOISE=realsense` (task environment) adds stereo-camera-like noise,
  σ = 2 mm + 2.5 mm·z² (z in m), and 1 % dropouts, seeded by `RCB_DEPTH_NOISE_SEED`. Depth never affects physics.

## The shared capability

A service with the shared capability adds the following to the base. Everything in the base holds.

**Request fields.**

| Field | Default | Meaning |
|---|---|---|
| `cameras` | every camera | names from `spec.cameras`; the client sends `spec.default_cameras` when given none |
| `video_fps` | the service's | frames per simulated second |
| `video` | `mp4` (submit), `frames` (observe) | `mp4`, `frames`, `both` or `none` |
| `depth` | `none` | `none`, `last` or `frames`; JSON `true` = `last` |
| `include_depth` | `false` | with no `depth` field: `true` answers `depth/<cam>`, float16 per frame |
| `last_s` (observe) | 0 | [`POST /observe`](#post-observe) |

On the sidecar layer in standard mode, `cameras: []` also means every camera. In realtime mode `cameras: []` means no
images.

**`/spec` keys.**

| Key | Content |
|---|---|
| `default_cameras` | the cameras the client asks for when a call names none |
| `cameras.<cam>` | adds `depth: true`, `intrinsic_cv` (3×3), `mount`, `depth_range_m` |
| `robot_spec` | the robot's spec sheet (below) |
| `world` | `frame` (origin and axes in words), `up`, `units`, `quaternion_order` (`wxyz` or `xyzw`, used by every pose of this service), `camera_axes` |
| `kinematics` | what `/kinematics` answers |
| `depth` | `{"modes": ["none", "last", "frames"], "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": 65.535, "frames_encoding": "uint16 mm, zlib", "noise": "off" or "realsense"}` |
| `max_call_wall_s` | the per-call wall-clock bound (below) |

**Camera geometry.** `intrinsic_cv` K maps a point (X, Y, Z) in the camera's OpenCV frame (x right, y down, z forward)
to u = fx·X/Z + cx, v = fy·Y/Z + cy. The pixel that contains it is (column ⌊u⌋, row ⌊v⌋). `extrinsic_cv` (3×4) maps
world to that frame. `cam2world_gl` (4×4) is the camera pose with OpenGL axes = inverse(extrinsic_cv) ·
diag(1, −1, −1, 1). `mount` is `{"type": "static", "extrinsic_cv", "cam2world_gl"}` or
`{"type": "link", "parent_link": L, "link_T_cam_cv"}`, where world_T_cam = FK(L) · link_T_cam_cv for any joint
configuration and L is in `kinematics.links`.

**`robot_spec`.** Every value is the robot's own, nothing about the scene.

| Key | Content |
|---|---|
| `name`, `description` | the robot |
| `base` | `{"type": "fixed", "pose"}` or `{"type": "mobile", ...}`: root link, where its pose is in proprio, how it is commanded, its limits |
| `joints` | every driven joint: `{name, type, unit, position_limits, velocity_limit, effort_limit, group}`, the limits the simulator enforces (`null` where it enforces none); where known, `rated_velocity`, `rated_effort` and `rated_source` |
| `grippers` | per gripper: `joints`, `opening_m`, `command` (entries, range, open / close rule), `tcp_frame` |
| `controller` | `type`, `control_hz`, `physics_hz`, `gains` (`{joint: {"stiffness", "damping"}}`, the drives' own), `note` |
| `tcp` | per tool frame: `{"parent_link", "link_T_frame", "definition"}`: the fingertip centre and the `ee_pose` frame, with the offset between them |

**Actions.** `ee_pose` rows are end-effector targets solved by the benchmark's IK or planner. A failed row is reported
in `plan`. Types not offered yet are listed under `spec.action_types.not_yet` (`joint_delta`, `joint_velocity`,
`ee_delta`, `joint_torque`).

**Never provided.** No endpoint, part or `/spec` field gives object poses, scene files, seeds, the success predicate,
segmentation, or physical parameters of the scene other than the robot's own drive gains. Provided: the robot and its
tool, camera calibration, world conventions, the budget, and what the task's texts give. Whether a task's texts state
world coordinates of workspace items is its benchmark's decision. `rcb_limited.check_spec` refuses to start a service
whose `/spec` names a forbidden field or puts a position into `static`. A calibrated camera aimed at the workspace
tells roughly where the workspace is: that is accepted.

**Per-call bounds.** The wall clock stays the episode's only time budget. Two bounds keep one call from holding the
single-threaded service:

- `max_call_wall_s` (`/spec`, default 900 s, task environment `RCB_MAX_CALL_WALL_S`). A `/submit` or `/observe` that
  runs longer stops at the next control step and returns normally, with `meta.stopped = "max_call_wall_s"` and
  `executed_rows` below the rows sent. The client's read timeout is at least `max_call_wall_s` + 120 s and at least
  1800 s.
- A client hang-up: when the client closes the connection (its read timeout, a killed process), the call stops at the
  next control step (`stopped: "client_disconnected"` in the call log). The response is not delivered.

In both cases the executed prefix stays. `/status` and the next `meta.proprio.now` report the state after it, as for
a real controller that loses its link. `rcb_client` exposes `Result.stopped` and prints a one-line warning.

**Other rules.** `/observe` and `/kinematics` still answer after any end but `/finish`. A 500 on `/submit` or
`/observe` ends the episode with `reason = "error"`. The service listens on port 8000 of a network namespace that,
under Harbor's egress control, the agent's container shares. If a process of the agent holds the port when the scene
is built, the service waits for it instead of exiting.

## Realtime

Time does not stop. Realtime tasks only: directories ending in `-realtime`, `/spec.timing.realtime = true`. The
realtime capability sits on the base. Endpoints, RCB1 frames and grading are the same.

**`/spec.timing`** declares `realtime: true`, `slowdown` S (`RCB_SLOWDOWN`; each task declares its default in its
`sim` service), `control_dt`, `wall_s_per_control_step` and `max_ahead_steps`. S and the reset budget are part of a
result's configuration.

**The clock.**
- An episode starts paused at its starting state. Its clock starts at its first `/submit`. After a reset, and after a
  crash recovery, the episode is paused again.
- Once started, it runs one control step every `control_dt` × S seconds of wall time, whatever the agent does, until
  the episode ends.
- The service publishes the first state before it answers any request, so the first `/observe` already has one.

**`/submit`** answers at once, with `duration_s` and `end_step` (= `plan_end_step`).
- The chunk is expanded into control steps as in standard mode (`dt`, `linear` or `hold`). It becomes the plan from
  control step `at`: an integer of the episode; absent means the next step; at most `max_ahead_steps` ahead.
- It replaces what was planned from `at` on and keeps what is planned before it. `linear` starts from the target in
  force just before `at`. Rows for steps that have already run when the request arrives are dropped.
- When the plan runs out, the last target is held (zero-order hold).
- A hold chunk plans the target in force for n seconds from `at`.
- `meta` adds `start_step`, `late_steps` and `plan_end_step`. Every `meta` and `/status` add `running`,
  `planned_steps` and `lag_s`. The answer carries the frames and proprioception of now, no video.
- A service with several action types never combines rows of different types. A chunk interpolates from the target
  of its own type (the simulator's current one when the plan holds another type just before `at`). A type that is not
  interpolable (a command: one row, one control step) is never interpolated. A gap left before `at` is held steps
  (the simulator's hold row), unless the chunk's type is an interpolable target in force there, which is then held
  through the gap.
- A request the plan cannot take is a 400 and changes nothing.

**`/observe`** answers at once and never changes the plan. It reads the recorder. `cameras: []` asks for no images,
only proprioception.

**The recorder.**
- Where the adapter can copy its state (`render_state()`) and draw such a copy (`render_from(state, cameras,
  depth)`), a recorder records the cameras while time runs. It is a process of its own, never the simulator's thread.
- `/spec.timing.recorder` declares it: `cameras`, `fps` (`RCB_CAMERA_FPS`, default 30), `resolution`, `buffer_s`,
  `records`, `depth`.
- The simulator thread hands it a copy of the state every 1 / `fps` of robot time. A recorder that is slower skips
  copies and never holds the clock back. It draws the copy with its own copy of the scene, so recording cannot change
  the journal, the trajectory or the verdict.
- Frames go into a ring of the last `buffer_s` robot seconds, each tagged with its control step. `/observe` reads only
  the ring, on its own thread: it never reaches the simulator.
- An answer with images adds `frame_step`, the control step the newest image shows. The recorder may be behind
  `control_steps`.
- At most 8 answers with images are built at a time. Past that, answers come without frames (`frames_skipped`).
- A recorder that dies is restarted. Meanwhile answers come without frames (`frames_pending`).
- An adapter without the two hooks renders on the simulator's thread into the same ring at 10 fps. Each render costs
  the clock its time, and `fps` says so.

**Grading** is the base's: the live episode, judged by the service. The journal holds the row the simulator applied
at every control step, so the graded trajectory reproduces the live run whatever the timing. Added evidence:
- `ticks.f64` (per journal row: wall time, and the call whose chunk gave the row, −1 when held), `calls.jsonl` and
  `submitted.f64` (one line per call and every row as sent);
- in `final.json`: `realtime`, `slowdown`, `held_steps`, `late_steps`, `max_queue_wait_s`, `camera_worker`; the
  clock's record (`clock_s`, `max_lag_s`, `stalls`, `stalled_s`, `stalled_share` = `stalled_s` / `clock_s`); and what
  requests cost (`requests_refused`, `request_mb`, `request_busy_s`);
- the graders repeat the clock's record, `requests_refused` and `request_busy_s` in `reward.json`. None of it decides
  a verdict.

**Keeping the clock.**
- The simulator's thread runs a due control step before any waiting request. Behind the clock it runs the missed
  steps back to back. More than 0.5 s behind, it drops the debt (a stall, counted, its seconds added to `stalled_s`)
  instead of fast-forwarding the robot.
- A request's body is read, decoded and checked on its HTTP thread. A request refused for what it says (404, 413, a
  malformed body, a wrong type, shape, `dt` or camera, a chunk longer than `max_chunk_s`) never reaches the
  simulator's thread, and neither does `GET /spec`.
- JSON text is parsed in the service's process only up to 1 MiB. A larger JSON body is parsed by a child process, one
  at a time, and costs the clock nothing.
- Behind the clock, a waiting request is served once the clock has caught up. Where the simulator cannot keep up by
  itself, it is served after four times the time the last request of its kind took. A request that renders and alone
  takes more than 0.5 s makes the next rendering request wait four times that long. Requests without images are not
  held back by it. Requests can so take at most a fifth of the clock's time.
- Without a recorder, the cameras are rendered at most once per control step, and parallel observes share that step's
  frames.
- Refusals the episode's state decides (409; an `at` too far ahead; too many frames) are answered by the simulator's
  thread. A 409 comes before a 400 for a request's fields.
- Checkpoints are written every second of robot time while the clock runs.

**Crashes and simulator errors.** No call spans the clock, so what the agent's commands caused is told apart by time
and by kind. "After the first command" means after the first control step that ran a row the agent sent.
- A simulator error raised by a control step after the first command (`reason = "error"`) ends the episode as the
  agent's result: `sim_error = 1`, `infra_error = 0`. Before it, it is infrastructure.
- A crash (the process dies) is resumed as on the sidecar layer, paused. It counts as the agent's when it happened
  inside a control step after the first command and the process died on SIGSEGV, SIGBUS, SIGFPE, SIGILL or SIGABRT.
  The service records the signal and the crashing stack in `crash.log` before it dies.
- A crash while the process builds the scene, replays its journal, renders or finalizes is not the agent's. Nor is a
  process killed from outside (SIGKILL, SIGTERM, the OOM killer), or a crash before the first command.
- Past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed_on_call` (the agent's 0) if every crash was the agent's,
  else `sim_crashed` (`infra_error = 1`). A failed resume is `resume_failed` (`infra_error = 1`).
- A reset whose new episode the simulator fails to build is infrastructure.

**Agent code** runs where it does in standard mode, in the agent's own container: a controller that streams targets
through the client, never code uploaded next to the simulator.

## Operations

The operations capability adds operation ids, deadlines and a watchdog to the shared capability. It is for
standard-mode services whose native calls can run for minutes (IPC and PBD deformables). Without it, a client whose
HTTP read timed out cannot tell whether the call ran, and a retry can run the same actions twice. A service with it
reports `/spec.operations = true`. "MUST" below is what a client of such a service may rely on.

**Operation ids and deadlines.**

| Rule | Level |
|---|---|
| `/submit` and `/observe` accept `meta.operation_id` (`[A-Za-z0-9_-]{1,80}`) and `meta.request_deadline_unix_s` (a finite number, Unix seconds). A malformed value is a 400. | MUST |
| A request whose deadline has passed before execution starts gets a **408**. No physics runs. | MUST |
| An `operation_id` the service has already admitted gets a **409**, with the operation record and a pointer to `/operations/<id>`. It never runs again. | MUST |
| The response `meta` echoes `operation_id`. | MUST |
| A request without these fields is served as on the shared layer. | MUST |
| The client sends a fresh id and a deadline (now + `max_call_wall_s`) on every call. It keeps the last id (`Robot.last_operation_id`), and its read timeout is at least the service budget + 120 s. | SHOULD |
| After a timeout the client queries the operation instead of re-sending the actions. A new id for the same actions is a new operation. | SHOULD |

**`GET /operations/{id}`** returns the operation record as JSON: 200, 404 for an unknown id, 400 for a malformed id.
Fields: `operation_id`; `status` (`admitted`, `completed`, `error` or `interrupted`); `rows_before` (rows run before
the call); `committed_rows` (rows run when the call ended); `stopped` (the call's stop reason). After a crash
recovery, an operation that was `admitted` becomes `interrupted`, with `execution_uncertain: true` and
`restored_committed_rows`. The service keeps no copy of the response video. The endpoint is read-only and never steps
physics.

**The call watchdog.**

| Rule | Level |
|---|---|
| A call's budget is `min(max_call_wall_s, request_deadline_unix_s − now)`. The service checks it, and a client disconnect, at control-step boundaries. | MUST |
| A native step cannot be pre-empted safely, so the service also owns a hard watchdog. A call that has not finished 60 s past `max_call_wall_s` ends the process. The watchdog counts from the service's own cap, never from the request deadline. The restart ends the episode as `call_watchdog` (`infra_error = 1`) and does not replay into the call that hung. | MUST |
| The restart ends the episode as `call_watchdog` only on evidence that the watchdog fired: its banner in `call-watchdog.trace`, emptied at every call. Any other crash during a call is handled like every crash, and a resume removes both watchdog files. | MUST |

**The physics-tick ledger and durability.**

| Rule | Level |
|---|---|
| The journal can record the physics ticks each row actually took (`journal.ticks.i64`, int64, one per row). A step that ends early inside its control period records fewer ticks, and `sim_time_s` and `frame_time_s` follow the actual physics clock. | MAY (MUST for a service whose steps can end mid-period) |
| A resume replays each row with its recorded tick count. A missing or incomplete ledger ends the episode as `resume_failed`. The ledger is cut to the last checkpoint together with the journal. | MUST if the ledger is kept |
| Journal rows, the tick ledger, checkpoints and operation records are fsynced, with their directory, before the call that counts them is reported complete. | MUST |
| `dt` is an integer multiple of the control period within float tolerance; otherwise 400. | MUST |

**Evidence** as on the shared layer, plus `/data/operations/<id>.json`, `journal.ticks.i64` when kept, and
`call-watchdog.json` (while a call runs) with `call-watchdog.trace`. The verifier still transcribes `final.json` only.

The operations client sends operation ids only to a service whose `/spec.operations` is `true`. With any other
service it behaves as the shared client.

## Match extension

Embodied Olympics - Match runs matches between seats, refereed by the match's own service. The match extension puts
the standard endpoints in front of that service and adds the match's own calls. A client that knows the base (or the
realtime capability) plays a match with it, and calls `/start` and `/ready` besides.

**`/spec`.** `protocol` is `eai-standard/3.0`. `/spec.match` is the match service's own spec. `/spec.timing.realtime`
says a real-time match. A turn-based match's seat API answers `turn_based: true` in its spec. `/spec` also carries
`control_hz`, `control_dt`, `cameras` (with `intrinsic_cv` and `pose_at_spec`), `action_types`, `timing`, `budget`,
`entities`, `extensions` and `endpoints`.

**Endpoints.**

| Endpoint | Request | Answer |
|---|---|---|
| `GET /status` | — | JSON `meta` |
| `POST /observe` | JSON or RCB1 header `{last_s, cameras, video, query, team_since}` | RCB1: `last/<camera>`, `frames/<camera>`, `frame_step/<camera>`, `view` (the match's own tiled PNG); `meta.observation` |
| `POST /submit` | RCB1 header `{type, dt, at, entity, cameras, note}` + part `actions` (float32 `(T, dim)` in `action_types.<type>.layout`, or JSON: a list of action objects), or JSON `{type, dt, at, entity, rows: [...]}`; a hold chunk `{type, interpolate: "hold", seconds}` without rows | RCB1, `meta` with `chunk_id`, `ok`, `effects` and the clock's fields |
| `POST /start` | `{}` | JSON `{accepted, ok, meta}`: you are ready; the match begins when every seat has started |
| `POST /ready` | `{why, plan}` (strings of at most 2000 characters, both required for a review) | JSON `{accepted, ok, meta}` once the world goes on |
| `POST /say` | `{text}` | a message to your team (team formats only; else 404) |
| `POST /team`, `GET /team?since=N` | `{since}` | your team's messages (team formats only; else 404) |

- An RCB1 request to `/start`, `/ready`, `/say` or `/team` is answered in RCB1, with the match's reply under `reply`.
- A row of `/submit` is an action object of the match. A numeric row in the type's layout is turned into one: an enum
  by the index of its value, a boolean as 0 or 1, all columns of a field with a default NaN = that default.
- One chunk is one type and, where actions name a robot or rod, one entity: `entity` in the header, in the rows, or as
  `type` = `<type>@<entity>`. The match checks each row when it is sent.
- **Not offered (404):** `/finish`, `/reset`, `/kinematics`. A match ends by its own rules: the final score, a forfeit,
  a review or start timeout, the session's end. There is one match per task and no reset.
- Besides the base codes, a match answers 403 (`seat not authorized`: a request from a host its seat is not bound
  to), 429 (too many requests of one seat in flight; empty body: retry more slowly) and 413 for a body over 8 MiB
  (`/spec.max_request_bytes`).
- The seat API `/<SEAT>/<call>` keeps working on the same port. Both reach the same match, and the per-seat request
  budget (20 per second, 4 open) counts them together.

**`meta`.** The base `meta` (`protocol`, `step`, `control_steps`, `sim_time_s`, `calls`, `time_s`, `time_left_s`,
`done`, `reason`, `proprio`) and the match: `score` (`{side: points}`), `side`, `review_due` (the world is frozen and
your review is due), `match_over` (= `done`), `phase` (`prepare`, `running` or `play`, `review`, `over`), `world` and
`state` (your seat's state; `proprio` is its numeric leaves). Realtime adds `running`, `planned_steps`, `lag_s` and
`effects`.

**Clocks.**
- **Realtime.** As [Realtime](#realtime): `/submit` answers at once, and its rows become the plan of their entity
  from control step `at`, row i at `at` + i × `dt` / `control_dt`. Rows whose step has run are dropped (`late_rows`,
  `late_steps`). `meta` adds `start_step`, `replaced_rows`, `plan_end_step`. Each planned row is handed to the match at
  its step. The answers report each row's `planned_step`, `effect_step` and `late_steps` in `meta.effects`, once.
  Rows are commands, never interpolated, and the last one stays in force. A hold chunk clears the entity's plan from
  `at` for n seconds.
- **Lockstep.** `/submit` runs its rows one after the other: each takes effect at the step the world is at, then the
  world advances `dt` (default one control step). It answers after the last row. A hold chunk lets n seconds of game
  time pass with the commands in force. Between calls the world stands still.
- **Turn-based.** `/submit` takes one row: the action of your turn, whose review follows with `/ready`. A hold chunk
  waits up to n real seconds for your turn.
- In every clock, `/observe` only reads (`seconds > 0` is a 400).
- **Freezes.** After every unit (a point, a phrase, a stoppage) the world freezes for the reviews until every due seat
  has sent `/ready`, at most `timing.review_timeout_s` of real time; else that side loses (`ready_timeout`). The match
  begins only after `/start`, within `timing.start.window_s` (else `no_show`). A realtime plan is cleared at a freeze.
  A `/submit` while the world is frozen or not started answers `ok: false` with `not_now` and runs nothing. After the
  match is over `/submit` is a 409, while `/observe` still answers 200 with the final state and no images.

**Declared deviations** (`/spec.timing.deviations`, each with its rule, what the match does and why):
- the clock starts at the start barrier (every seat's `/start`), not at the first `/submit`;
- the world freezes after every unit for the reviews, and the plan is cleared there;
- a row takes effect at the first control-step boundary after the match has prepared it; one row per entity is in
  flight;
- behind its clock the match runs the missed steps back to back and records how late (`final.json` `sim_lag`); it
  drops no debt;
- the match keeps no recorder: `/observe` with `last_s = n` answers with the sport's own frames of now, no video;
  `/submit` returns images only when it names `cameras`;
- no depth (`depth.modes` = `["none"]`), no `linear` or `hold` interpolation;
- a turn-based hold chunk's `seconds` counts real seconds.

**Grading** is the match's: its referee judges the live match (`final.json`, `tests/grade.py`). The seat API's record
(`episode.jsonl`) holds every action whichever endpoint sent it. The extension adds `eai_std_calls.jsonl`, one line
per standard call. None of it decides a verdict.

## MCP tools

Every standard and realtime task offers its robot service two ways in the same task: the shipped client (HTTP) and
the MCP server `efe-robot`. The agent chooses. Both reach the same service, so they drive the same robot in the same
episode and can be mixed call by call. The tools add nothing to the protocol: each sends its endpoint's request and
returns the reply.

**Every agent-facing endpoint has a tool.** A tool takes its endpoint's request fields; any other field of the
service goes in `fields`, sent unchanged. It returns the reply's `meta` unchanged, with each RCB1 part written as a
file under `/app/obs/` (arrays `.npy`, exact; uint8 images also `.png`; video `.mp4`).

| Endpoint | Tool | Where |
|---|---|---|
| `GET /spec` | `spec` | every task (the spec is also saved as a file, `spec_file`) |
| `POST /observe` | `observe` | every task |
| `POST /submit` | `submit` | every task; rows inline or as a file (`actions_file`), or a hold chunk; realtime adds `at`; the result's `step` repeats the reply's duration, end step, `steps_left` / `step_limit` and `done` |
| `POST /reset` | `reset` | a task with a reset budget |
| `POST /kinematics` | `kinematics` | a service that serves it |
| `POST /finish` | `finish` | every task; it sends the request only when `/spec.success_signal` starts with `"hidden"` |
| `GET /status` | none | its fields come back in every result's `meta` |
| `GET /operations/{id}` | none | the server re-queries it itself when a reply of an operations service is lost |

A match has the same `spec`, `observe` and `submit` tools, plus `start`, `ready` (and `say`, `team` in a team format).
It has no `finish`, `reset` or `kinematics`.

Three kinds of task keep only their own interface, and their READMEs say so: roboEngineer (the agent hands in a
policy, no live robot), the `matchlow` matches (the player delivers skill code the platform runs), and a match
exported without the extension (the G1 table-tennis tasks; its service serves only the seat API).
`ci_checks/check-mcp-tools.py` holds the routes the layers and adapters serve to this table, and every task to its
tool list.

**Time.**
- Standard mode: time passes only through `submit`. `observe` reads what is recorded and moves nothing.
- Realtime mode: no tool holds or slows the clock. `submit` answers at once as the endpoint does, and a call costs its
  own time. Each result carries `tool_s`, the tool's own wall time. On the toy realtime service an `observe` with
  `cameras = []` took 1.5-3 ms over HTTP and 1-3.5 ms more through the tool, plus whatever the agent's harness takes
  per tool call.
- Every call answers within 45 s of its arrival (`--max-block-s`, one deadline that includes any wait for an earlier
  call; Codex's MCP calls time out at 60 s). A call still running then returns `{"pending": true, "operation": id}`,
  and `observe(operation=id)` collects the reply. A call that arrives while an earlier one is still running at that
  deadline is not sent: its result is `{"sent": false, "operation": <the running one>}`. Nothing is retried.

**Shipping.**
- The server's files ship in the `standard-files` files-only image. `normalize` writes, from
  `embodied_first_exam/standard/mcp/inject.py`, into every standard and realtime task: `environment/efe_mcp/` with the
  task's `manifest.json` (its tools), the agent's Dockerfile lines that put the server at `/opt/tools/efe_mcp/`, one
  `[[environment.mcp_servers]]` entry in `task.toml` (`efe-robot`, stdio,
  `python3 /opt/tools/efe_mcp/server.py`), and `### MCP tools` after `### Client` in the instruction.
- Harbor registers the server with the agent's harness (Claude Code, Codex, Gemini CLI and the others that take MCP
  servers).
- The server needs Python 3 with numpy and requests (pillow for the `.png` copies): the standard client's pins. It
  answers `tools/list` from the manifest without contacting the service. A tool the running service shows later
  (`kinematics`, `reset`) is added with `notifications/tools/list_changed`. It logs one line per call to
  `/logs/agent/efe-mcp.jsonl`.
- Tests: `embodied_first_exam/standard/mcp/tests/`. An oracle run once over HTTP and once through the tools leaves the
  same episode.
