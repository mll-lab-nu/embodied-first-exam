# Standard-mode wire protocol `eai-standard/2.x` (robot as a service)

Part of the task protocol ([README](README.md)): the wire format of the standard modes.

**Version: `eai-standard/2.4`** is the current version. This document is the interoperability
specification of every 2.x version a task declares today: what a service answers and a client may send. Minor
versions only add, so each part holds for the versions after it unless a later part says otherwise, and the shipped
clients accept every 2.x service. What a task of the standard modes is, and which rules bind it, is in
the [README](README.md) (§3 Modes); the binding rules on the trust boundary (no simulator, state or success
predicate in the agent's reach; the verdict from a trusted record) are stated once, in
its [Appendix H](README.md#appendix-h-invariants-binding) (H.3, H.4), and are not repeated here. How a runner handles a trial that failed
for infrastructure reasons is in [running.md](running.md). What a benchmark's own service adds (its robot, action
types, cameras, proprioception columns, resume class, measured start-up times, known issues) is in its
`docs/benchmarks/<bench>.md`.

| Version | Content | Part | Implementation |
|---|---|---|---|
| `eai-standard/2.1` | the base: `/submit` and `/observe`, RCB1 responses, measured proprioception, optional depth noise; the optional reset capability | Part 1 | each benchmark's own service |
| `eai-standard/2.2` | 2.1 + optional capabilities: depth `last` / `frames`, per-frame steps, times and extrinsics, camera intrinsics and mounting, `robot_spec`, `world`, `POST /kinematics`, a per-call wall-clock bound; one shared service layer | Part 2 (§1–§18) | [`scripts/eai_standard/`](../../scripts/eai_standard/) |
| `eai-standard/2.3` | 2.2 + the realtime capability: a clock that does not stop | Part 3 | `scripts/humanoidbench/shared/realtime/rcb_realtime.py` |
| `eai-standard/2.4` | 2.3 + the operations capability: operation ids, request deadlines, `GET /operations/<id>`, a call watchdog, a physics-tick ledger | Part 4 (§19–§25) | [`scripts/eai_standard/v2_4/`](../../scripts/eai_standard/v2_4/) |

Which version a task serves is its `[metadata] protocol` (= `/spec.protocol`); which benchmarks serve which version is
in their docs, not listed here.

**Spelling.** Services and tasks report `eai-standard/2.x`; the shipped clients also accept `rcb-limited/2.x`. No task
declares a version before 2.1.

**Citing this document.** Numbered sections are unique in the document: §1–§18 are Part 2 (so "§13" is the shared
layer's crash recovery), §19–§25 are Part 4. The sections of Parts 1 and 3 are cited by their titles. A section whose
content is per benchmark points to the benchmarks' docs.

## Part 1 — `eai-standard/2.1`: the base

The agent talks to a **sim service** it cannot open, over HTTP. One trial is one episode unless the task declares a
reset budget (the optional reset capability, below). **No step limit** (except a technical episode cap where a task
states one in `spec.max_control_steps`); the agent's wall-clock budget is the real limit; actions and simulated time
are reported as cost. What the service never reveals (object poses, scene files, seeds, the success predicate) is
PROTOCOL Appendix H.3; contact or safety telemetry is published only where a benchmark's doc declares it field by
field. Videos, frames, depth and proprioception come back as **binary** in the response body (RCB1 frames, below),
never base64; the agent's code decides what to keep.

Base URL: `http://sim:8000` (compose network) or `http://localhost:8000` (Harbor egress control puts the service in the
agent's network namespace); the client tries both. The socket opens only when the scene is ready; until then
connections are refused and the client retries.

### Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: action types (dims, layouts, limits, semantics), cameras, proprio layout, budgets |
| GET | `/status` | — | JSON: `{step, calls, physics_steps, done, reason, elapsed_s}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, include_depth, video}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, include_depth, note}` + part `actions` float32 (T, dim) | RCB1 |

Anything else (`/state`, `/success`, …) returns **404**; so does `/reset` unless the task declares a reset budget
(below).

### RCB1 frame
```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```
Response parts: `video/<cam>` (mp4), `frames/<cam>` (uint8 [N,H,W,3]), `last/<cam>` (uint8 [H,W,3], always),
`depth/<cam>` (float16 [N,H,W], if requested), `cam2world_gl/<cam>` (float64 [N,4,4], for a camera that moves: its pose
at each returned frame), `proprio` (float32 [N, len(proprio layout)], one row per video frame; the columns are the
benchmark's). Requests over 64 MB → 413 (the client refuses to send one); a response over 256 MB drops
`frames/`/`depth/` and says so in `meta.degraded`. `rcb1.py` (encode/decode, `python -m rcb1 unpack f dir`) is shipped
with the client.

### `meta` (in every response)
`step` (rows executed so far), `calls`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio` =
`{"layout": [names], "now": [floats]}`, `cameras` (per camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the whole
key omitted when the task sets `RCB_OBS_CALIBRATION=0`), `done`, `reason`. `cameras` is the calibration of the state the
response ends in (the `last` frame, the final sample of `frames` / `depth`): static cameras never move, a camera on the
robot moves with it, and for each requested moving camera the response carries the part `cam2world_gl/<cam>` (one
pose per returned frame; `spec.camera_calibration`). `time_s` / `time_left_s` are the agent's clock (below; `/spec`
states it in `budget.clock` or `budget.wall_clock_note`). `/submit` adds `chunk_id, type, executed_rows,
physics_steps_chunk, clipped [{row,index,reason}], n_clipped, plan [...], ok`; `/observe` adds `obs_id, seconds,
physics_steps_watch`.

### `/submit` semantics
- `joint_position` rows are `dt` seconds apart, `dt` a multiple of the physics or control step and at most 0.5 s;
  anything else is rejected (400), never rounded. The service streams drive targets with `interpolate = "linear"`
  (default) or `"hold"` between rows, exactly as a real controller consumes a chunk. Out-of-limit values are clipped
  and reported (continuous joints have `null` limits and are never clipped). A chunk may cover at most `max_chunk_s`.
- Planner-executed types such as `ee_pose` state their frame, quaternion order and end-effector reference in `/spec`;
  a failed plan is reported in `meta.plan`, not as an error.
- Types a service does not offer yet are listed under `spec.action_types.not_yet`. The action layout, the action
  types and their dtype are the benchmark's (its doc).
- Video is captured every `physics_hz / video_fps` physics steps from the requested cameras, plus the first and last
  frame.
- After the chunk the task predicate is evaluated; the first success ends the episode (`done`, `reason = "success"`).
  The chunk is appended to the recorded trajectory and to `episode.jsonl`.

### `/observe` semantics
`seconds = 0` (default) returns the current frames, free (no physics). `seconds > 0` (≤ `max_watch_s`) holds the last
command, advances physics and returns the video; the predicate is checked afterwards. Watching costs no budget beyond
the wall clock; the simulated time is recorded as cost.

### Errors (no physics executed)
| code | when |
|---|---|
| 400 | wrong type/dim, a chunk with no rows, NaN/inf, a field of the wrong JSON type (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list), `dt` or `seconds` out of range or `dt` not a multiple of the physics step, chunk too long, bad interpolate/video value, `video_fps` outside [1, 30], more than 3000 frames in one response (cameras × fps × seconds, depth counts double), malformed body |
| 409 | episode already finished (`done`); the trial is over |
| 413 | body over 64 MB (`rcb_client.py` raises before sending such a body) |
| 500 | simulator error; the episode ends with `reason = "error"` (the client raises `EpisodeOver`; the verifier reports `sim_error = 1`) |

### Episode semantics
The service starts the episode when it is ready (seed hidden inside). The first success ends it; otherwise it ends
when the agent phase ends (`timeout`) or on an error. The predicate is evaluated once more at episode end.

**The agent's clock (every 2.x service).** `meta.time_s` is the wall time since the agent's **first
request** to the service, whatever the endpoint (`GET /spec`, which the shipped clients send first, counts), and
`meta.time_left_s` = `spec.budget.wall_clock_s` − `time_s`, never below 0. The clock does not start with the service,
when the scene is ready, or with a probe that only connects to the port; the first request is logged in
`episode.jsonl` (`first_request`) and a restarted service reads it back, so a restart never sets the clock back to
full. `GET /status` `elapsed_s` and the `elapsed_s` of `final.json` are the episode's own time, from the service's
start of the episode. Why: Harbor counts the agent's cutoff around the agent's run only, and the sidecar starts with
the environment, before the harness is installed, so a clock started with the service would run ahead of the agent's.
With this rule `time_left_s` never runs out before the agent is
stopped, and the agent's real time left is `time_left_s` minus what it spent before its first request. A service that
ends an episode on its own clock says so in its benchmark's doc. A readiness probe added to a compose file or a runner
must not send a request to the service before the agent runs: connecting to the port is enough.

**Service crashes (reference implementation).** The reference services journal every executed step and log a
checkpoint (step count + state hash) per completed call; when the service dies mid-episode, compose restarts it
(`restart: on-failure:N`) and it resumes the same episode from the journal, the call in flight lost as a whole
(`spec.on_service_error` tells the agent to check `GET /status` before continuing). This is how the shipped services
behave by default (details: §13), not a rule: what the protocol says about a trial that failed
for infrastructure reasons is the runner's single full retry (PROTOCOL Appendix H.5, [running.md](running.md)). A
verdict already written is never overwritten. A scene build that hangs is killed by a startup watchdog
(`RCB_STARTUP_TIMEOUT_S`; each service has its own default, and each task sets the value its build needs, §13.3). A host
on which the frozen instance does not rebuild to its stored initial state reports `reason = instance_mismatch` with
`infra_error = 1`.

### Evidence and grading (agent never sees this)
`/data/episode.jsonl` (one record per call: type, rows, dt, cameras, note, clipped, plan, physics steps, success),
`/data/calls/NNNNNN/` (meta + last frames per call), and on end: `trajectory.npz` (the graded episode, the deliverable),
`final.json`, then `replay.mp4`. The collect hook signals the service by PID after a collect hook has stopped
the agent's processes; from then on the service refuses every request, and it judges the episode it ran (the task's success rule, with any settle or hold window run on the live simulator)
and writes the verdict into `final.json` (`success`, the verdict; `live_success`, how the episode itself ended, before
any settle or hold check; `graded_by` = `live`, `replays` = 0); nothing is
replayed to grade it (PROTOCOL H.4). The video is recorded during the episode or rendered from `trajectory.npz` after
the verdict (`video_source`), and never decides anything. A separate verifier transcribes `final.json` into
`reward.json` (`graded_by_live` = 1). `infra_error = 1` means there is no verdict on the agent: `final.json` is
missing, unreadable or not finalized, or the service reported `sim_crashed`, `resume_failed`, `instance_mismatch` or
(2.4) `call_watchdog`.

### Live recording (optional, sidecar only; the agent sees none of it)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl`: rendered from the
recorded trajectory by default, frames stamped with the call, never affecting the verdict. The reference recording is RoboTwin's
(docs/benchmarks/robotwin.md).

### Proprioception (2.1)
A benchmark's 2.0 columns stay where they were; 2.1 appends what a real robot reports (measured joint positions and
velocities, the gripper opening, the tool-centre pose, a drive-effort estimate), grouped in `spec.proprio_groups` (first
column, count, meaning). The columns are the benchmark's (its doc). Not exposed: object poses, segmentation, contact
forces on objects, the success predicate (PROTOCOL Appendix H.3).

Depth (`include_depth`) is exact by default. `RCB_DEPTH_NOISE=realsense` (task env) adds stereo-camera-like noise,
σ = 2 mm + 2.5 mm·z² (z in m), and 1 % dropouts (0 = no reading), seeded by `RCB_DEPTH_NOISE_SEED`; it never affects
physics.

### Per-benchmark 2.1 services
The MuJoCo service (`images/mujoco/limited/server_mj.py`: DexToolBench, MuJoCo Playground manipulation),
the shared KinDER / HumanoidBench service (`rcb_service.py`), the MetaWorld+ and RoboCasa services serve the same
endpoints and frames with their own action layouts, control rates and cameras: docs/benchmarks/dextoolbench.md,
mujoco-playground.md, kinder.md, humanoidbench.md, metaworldplus.md, robocasa.md.

### Optional reset capability
Each task declares its own budget N (PROTOCOL §2): the `RCB_RESET_BUDGET` default of its `sim` service, served as
`/spec.budget.reset` and stated in its instruction (templates: 0 in standard mode, 10 in standard-realtime mode). Any
2.x service may implement the capability; which ones do is in their benchmarks' docs. With N > 0, `/spec.budget.reset =
N`, `/spec.reset` describes it, and `POST /reset` (RCB1 or JSON `{cameras, video}`, no physics) abandons the running
episode and starts a new one from the same frozen state, `N` times in all; `/status` and `meta` add `episode`,
`resets_left` and `control_steps_total`. After a success or once the agent's time is up, `/reset` returns 409, as it does
when the budget is spent. Only the last episode is graded. With N = 0 (or no declaration) `/reset` is 404. The reset
budget is part of a result's configuration: results with different budgets are not ranked together (running.md).

## Part 2 — `eai-standard/2.2`: capabilities added to 2.1

> 2.2 is a minor version of `eai-standard/2.1` (Part 1): everything there holds unless
> this part says otherwise, every 2.2 addition is an optional capability, and a request written for 2.0 or 2.1 gets
> the same answer as before (plus parts and keys an old client ignores).

**One implementation.** The source is [`scripts/eai_standard/`](../../scripts/eai_standard/): the service layer
`rcb_limited.py` (HTTP, RCB1 responses, the protocol helpers, the `/spec` self-check, crash recovery), the client
`rcb_client.py` + `rcb1.py`, the sidecar entrypoint `run.sh`, and the client image: `client.env` (the one client base,
pinned by digest) and `client-requirements.txt` (exact pins). The generators copy the code unchanged into every 2.2
task (`environment/rcb_client.py`, `environment/rcb1.py`, `environment/sim/{rcb_limited.py,rcb1.py,run.sh}`). Each
benchmark writes only its adapter, `environment/sim/server.py`: the robot, the cameras, the clock (`toy_server.py` is
the smallest complete one).

**Design principles.**
1. *A robot, not a simulator.* No state query, no success query, no step limit; resets only within the task's declared
   budget; the wall clock is the budget; actions and simulated time are reported as cost; the first success ends the
   episode.
2. *One information line.* The agent may know the robot and its sensors (spec sheet, kinematics, camera calibration,
   proprioception), never the world's ground truth (§10).
3. *Everything new is optional.* Depth, for example, costs a render and is off by default.
4. *Binary data, kept by the agent's code.* RCB1 frames, never base64; nothing is pushed into the model's context.
5. *Evidence the agent cannot touch.* The service records every call and judges the episode it ran, in a container the
   agent never saw; the recorded trajectory stays replayable (the video, audits).

### 1. Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: 2.1's keys + cameras' intrinsics and mounting, proprio groups, `robot_spec`, `world`, `kinematics`, `depth`, `on_service_error`, `max_call_wall_s` |
| GET | `/status` | — | JSON: `{step, calls, control_steps, done, reason, elapsed_s, resumes}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, video, depth}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, depth, note}` + part `actions` float32 (T, dim) | RCB1 |
| POST | `/kinematics` (2.2) | JSON `{op: "fk" \| "ik", ...}` (§8) | JSON |
| POST | `/reset` | as in Part 1 | only where the task declares a reset budget N > 0 (Part 1, "Optional reset capability") |

Anything else (`/state`, `/success`, `/reset` without a budget) returns **404**. `include_depth` (2.0/2.1) is still
accepted (§7). The shared 2.2 client has no `reset()`; an instruction whose task has a budget calls `POST /reset`
through `Robot._post`.

### 2. Response parts
Every recorded frame of a call (the first, one every `control_hz / video_fps` control steps, the last) has one entry on
one shared frame axis N: the rows of `frames/<cam>`, the frames of `video/<cam>`, `proprio`, `frame_step`,
`frame_time_s`, `extrinsic_cv/<cam>` and `depth_frames/<cam>`.

| part | kind | content |
|---|---|---|
| `video/<cam>` | mp4 | H.264 of the N frames (`video` = `mp4` \| `both`) |
| `frames/<cam>` | array uint8 (N,H,W,3) | the raw frames (`video` = `frames` \| `both`) |
| `last/<cam>` | array uint8 (H,W,3) | the last frame, always |
| `proprio` | array float32 (N,D) | one proprio row per frame, columns `spec.proprio_layout` |
| `frame_step` (2.2) | array int64 (N,) | control steps executed since the episode start when the frame was rendered |
| `frame_time_s` (2.2) | array float64 (N,) | its simulated time, `frame_step / control_hz` |
| `extrinsic_cv/<cam>` (2.2) | array float64 (N,3,4) | world → camera (OpenCV axes) at that frame (constant for a static camera) |
| `last_depth/<cam>` (2.2) | array float32 (H,W) | z-depth of the last frame in metres (`depth` = `last` \| `frames`) |
| `depth_frames/<cam>` (2.2) | bytes, `codec: "zlib"`, `dtype: "uint16"`, `shape: [N,H,W]`, `unit: "mm"` | z-depth of every frame (`depth` = `frames`); the client decodes it to float32 metres |
| `depth/<cam>` (2.1) | array float16 (N,H,W) | z-depth of every frame in metres, only for a 2.1 request (`include_depth: true` without `depth`) |

A response over 256 MB drops `depth_frames/` and `depth/` first, then `frames/` (mp4, last frames, last depth, proprio and
the per-frame arrays always stay) and says so in `meta.degraded`. Requests over 64 MB → 413.

### 3. Request fields (`/submit` header, `/observe` body)
| field | default | meaning |
|---|---|---|
| `cameras` | every camera | names from `spec.cameras`; the client sends `spec.default_cameras` when given none |
| `video_fps` | the service's | frames per simulated second |
| `video` | `mp4` (submit), `frames` (observe) | `mp4` \| `frames` \| `both` \| `none` |
| `depth` (2.2) | `none` | `none` \| `last` \| `frames`; JSON `true` = `last` |
| `include_depth` (2.0/2.1) | `false` | with no `depth` field: `true` answers as 2.1 did (`depth/<cam>` float16 per frame) |
| `seconds` (observe) | 0 | 0 = the current frames, no physics; > 0 (≤ `max_watch_s`) = hold the last command and watch |
| `type`, `dt`, `interpolate`, `note` (submit) | | as 2.1 |

### 4. `meta`
2.1's keys (`step`, `calls`, `control_steps`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio`, `done`,
`reason`), with `cameras` = per requested camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`, `image_size` at the last
frame (omitted when the task sets `RCB_OBS_CALIBRATION=0`). `/submit` adds `chunk_id, type, executed_rows,
control_steps_chunk, physics_steps_chunk, clipped [{row,index,reason}], n_clipped, plan [...], ok`; `/observe` adds
`obs_id, seconds, control_steps_watch, physics_steps_watch`. Both add **`stopped`** (2.2): `null`, or why the service
stopped the call early (§12).

### 5. `/spec`
2.0/2.1 keys, unchanged: `protocol` (`"eai-standard/2.2"`), `simulator`, `robot`, `task_text`, `control_hz`,
`physics_substeps`, `max_chunk_s`, `max_watch_s`, `cameras`, `action_types`, `proprio_layout`, `proprio_groups`, `static`
(scene facts: names, sizes, colours; never a position), `budget` (`{"reset": N, "steps": null, "wall_clock_s",
"clock"}`; `clock` says what `time_s` / `time_left_s` count from: the agent's first request, Part 1 "The agent's clock";
the shared layer fills it in and keeps the clock, `rcb_limited.agent_time`). 2.2 adds:

| key | content |
|---|---|
| `protocol_compat` | `["rcb-limited/2.0", "rcb-limited/2.1", "eai-standard/2.1"]`: requests written for these are served unchanged |
| `default_cameras` | the cameras the client asks for when a call names none |
| `cameras.<cam>` | + `depth: true`, `intrinsic_cv` (3×3), `mount`, `depth_range_m` |
| `robot_spec` | the robot's spec sheet (below) |
| `world` | `frame` (origin and axes in words), `up`, `units`, `quaternion_order` (`wxyz` \| `xyzw`, used by every pose of this service), `camera_axes` |
| `kinematics` | what `/kinematics` answers (§8) |
| `depth` | `{"modes": ["none", "last", "frames"], "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": 65.535, "frames_encoding": "uint16 mm, zlib", "noise": "off" \| "realsense"}` |
| `on_service_error` | what to do after a connection error or a 5xx (§13) |
| `max_call_wall_s` | the per-call wall-clock bound (§12) |

**Camera geometry.** `intrinsic_cv` K maps a point (X, Y, Z) in the camera's OpenCV frame (x right, y down, z forward) to
u = fx·X/Z + cx, v = fy·Y/Z + cy; the pixel that contains it is (column ⌊u⌋, row ⌊v⌋). `extrinsic_cv` (3×4) maps world to
that frame; `cam2world_gl` (4×4) is the camera pose with OpenGL axes = inverse(extrinsic_cv) · diag(1, −1, −1, 1).
`mount` is `{"type": "static", "extrinsic_cv", "cam2world_gl"}` or `{"type": "link", "parent_link": L, "link_T_cam_cv"}`
(world_T_cam = FK(L) · link_T_cam_cv for any joint configuration; L is in `kinematics.links`).

**`robot_spec`** (every value is the robot's own; nothing about the scene):
| key | content |
|---|---|
| `name`, `description` | the robot |
| `base` | `{"type": "fixed", "pose"}` or `{"type": "mobile", ...}` (root link, where its pose is in proprio, how it is commanded, its limits) |
| `joints` | every driven joint: `{name, type, unit, position_limits, velocity_limit, effort_limit, group}` = the limits the SIMULATOR enforces (`null` where it enforces none), plus, where known, `rated_velocity` / `rated_effort` and `rated_source` |
| `grippers` | per gripper: `joints`, `opening_m`, `command` (entries, range, open / close rule), `tcp_frame` |
| `controller` | `type`, `control_hz`, `physics_hz`, `gains` (`{joint: {"stiffness", "damping"}}`, the drives' own), `note` |
| `tcp` | per tool frame: `{"parent_link", "link_T_frame", "definition"}`: the fingertip centre and the `ee_pose` frame, with the offset between them |

### 6. Actions
As 2.1 (`joint_position` rows `dt` apart, a multiple of the control period, at most 0.5 s, `linear` or `hold`, clipped and
reported; a chunk covers at most `max_chunk_s`). `ee_pose` rows are end-effector targets solved by the benchmark's IK or
planner (its doc); a failed row is reported in `plan`. Not yet: `joint_delta`, `joint_velocity`, `ee_delta`,
`joint_torque` (`spec.action_types.not_yet`). After a chunk the task predicate is evaluated; the first success ends the
episode.

### 7. Depth
z-depth = the distance from the camera plane along the optical axis, in metres, for the same pixels as the RGB frame.
0 means no reading. `depth: "last"` returns `last_depth/<cam>` (float32, one depth render per camera per call);
`depth: "frames"` also returns `depth_frames/<cam>` (uint16 millimetres, zlib; decoded by the client to float32 metres,
1 mm steps). Exact by default; `RCB_DEPTH_NOISE=realsense` adds stereo-like noise (σ = 2 mm + 2.5 mm·z², 1 % dropouts,
seeded by `RCB_DEPTH_NOISE_SEED`), as 2.1. Depth never affects physics.

### 8. Kinematics
`POST /kinematics` is **stateless**: the answer depends only on the request, it never steps physics, never advances time,
never ends the episode and costs only wall clock. It uses the robot's kinematic model (the same as the `ee_pose` action and
the camera mounts), with no collision checking. `spec.kinematics`: `endpoint`, `joint_names` (the q layout; each a
`proprio_layout` column), `frame` (`world`, or `base` for a mobile robot unless the request gives `base_pose`),
`base_pose_proprio`, `quaternion_order`, `links`, `tcp_frames`, `ee_frames`, `ik_targets`, `ik` (solver, defaults).

| request | response |
|---|---|
| `{"op": "fk", "q", "links"?, "base_pose"?}` | `{"ok": true, "op": "fk", "frame", "poses": {link: [x,y,z, quaternion]}}` |
| `{"op": "ik", "targets": {frame: pose}, "seed"?, "base_pose"?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}` | `{"ok", "op": "ik", "frame", "q", "error": {frame: {"pos_m", "rot_rad"}}}` |

A malformed request → 400; no solution is `ok: false`, never an error.

### 9. Proprioception
2.1's rule, kept: a benchmark's 2.0 columns stay where they were; later groups are appended; every column has a name.
Every 2.2 service has at least the groups `joint_pos`, `joint_vel`, `gripper_opening` (metres between the fingertips),
`tcp_pose` (7 columns per `kinematics.tcp_frames` entry) and `joint_effort` (the PD drive-effort estimate, or the
simulator's measured effort).

### 10. Never provided
What no endpoint, part or `/spec` field gives is PROTOCOL Appendix H.3 (object poses, scene files, seeds, the success
predicate, segmentation; physical parameters of the scene other than the robot's own drive gains are not given
either). Provided: the robot and its tool, camera calibration, world conventions, the budget, and what the task's
texts give. Whether a task's texts state world coordinates of workspace items is its benchmark's decision (its doc,
"World-frame information"). `rcb_limited.check_spec` refuses to start a service whose `/spec` names a forbidden field or
puts a position into `static`; `ci_checks/check-standard-protocol.py` checks every response of a live service by hand.
Accepted consequence: a calibrated camera aimed at the workspace tells roughly where the workspace is.

### 11. Errors (no physics executed)
As 2.1: 400 malformed request (including a bad kinematics request), 409 episode over (`/observe` and `/kinematics` still
answer), 413 body over 64 MB, 500 simulator error: **on `/submit` and `/observe` the episode ends** with `reason = "error"`.
A negative `Content-Length` is a 400, answered without reading the body. The service listens on port 8000 of a network
namespace that, under Harbor's egress control, the agent's container shares: if a process of the agent holds the port
when the scene is built, the service waits for it (the agent's own time) instead of exiting.

### 12. Per-call bounds (2.2)
No step cap, and the wall clock stays the episode's only budget. Two bounds keep one call from holding the
single-threaded service:
- **`max_call_wall_s`** (`/spec`, default 900 s, below the client's 1800 s read timeout; task env `RCB_MAX_CALL_WALL_S`): a
  `/submit` or `/observe` that runs longer stops at the next control step and returns normally, with `meta.stopped =
  "max_call_wall_s"` and `executed_rows` below the rows sent.
- **Client hang-up**: when the client closes the connection (its read timeout, a killed process), the call stops at the
  next control step (`stopped: "client_disconnected"` in `episode.jsonl`); the response is not delivered.
In both cases the executed prefix stays: it is journaled and checkpointed like any call, and `/status` and the next
`meta.proprio.now` report the state after it, like a real controller that loses its link. An old client sees a normal
response with fewer rows executed; `rcb_client` exposes `Result.stopped` and prints a one-line warning.

A third bound keeps one call from exhausting the service's memory (every frame is held until the response is sent):
**`max_frames_per_call`** (`/spec`, where the adapter states one; the numbers are in the benchmarks' docs): the images a
call may return, cameras x frames with per-frame depth counted again. A request over it is a 400 before anything is
executed (`rcb_limited.check_frames`); a camera named twice is one camera. Where the length of a call is known only while
it runs (planner-executed rows), the call stops taking frames at the bound, runs to its end, always returns the last
frame, and `meta.frames_skipped` counts the frames left out. A service that states no bound is bounded by
`max_watch_s`, `max_chunk_s` and the frame rate.

### 13. Crash recovery (the shared layer's default behaviour)
The shared layer (`rcb_limited.Episode`; adapters call it as `toy_server.py` does) resumes a crashed service in the same
episode. This is an implementation of the reference services, not a rule (PROTOCOL Appendix H.5 is the
runner's single full retry of an infrastructure-failed trial; running.md).
- **Journal and checkpoints.** Every executed control step (the exact row given to the simulator's step) is appended to
  `journal.f64` (float64 rows). After every completed call the journal is flushed and a checkpoint is logged in
  `episode.jsonl`: call count, rows, control steps, the state hash, the robot's proprio row, and the adapter's `persist`
  keys (state that shapes later actions). `call_begin` / `call_end` bracket every call.
- **Restart.** `run.sh` is the sidecar's PID 1 and exits non-zero when the service crashes; compose restarts the container
  (`restart: on-failure:N`, same container and record). The new process finds the episode's `start` event and resumes:
  it replays the journal up to the last checkpoint (no rendering), truncates the journal there (the call in flight is lost
  as a whole: its caller got a connection error, not a result), checks the state (§13.1), restores the counters, the
  episode end if one was logged, and the `persist` keys, and continues the same episode. The agent's clock keeps running
  from its first request (the logged `first_request`), the episode's `elapsed_s` from the first start.
  `spec.on_service_error` tells the agent to wait for `GET /status` (client: `Robot.wait_ready()`) and check `calls` /
  `control_steps`.
- **Limits.** At most `RCB_MAX_RESUMES` (2) resumes; a third crash ends the episode: `sim_crashed_on_call` if every crash
  happened while a call was being served, else `sim_crashed` (`infra_error = 1`). A journal shorter than the log ends it as
  `resume_failed` (`infra_error = 1`). A verdict already on disk is never overwritten; the service then keeps its PID file
  for the collect hook and answers every request, `GET /spec` and `/status` included, with 409
  `{"gave_up": true, "reason", "infra_error"}`: the client's `Robot()` and `wait_ready()` raise `EpisodeOver` at once
  instead of waiting out their timeout. The same holds for a service that refuses the episode at its start.
- **Start-up.** A crash before the scene exists is a plain restart. The startup watchdog (faulthandler's C thread: it fires
  even while a native scene build holds the GIL) dumps every thread's traceback to `server.log` and exits after
  `RCB_STARTUP_TIMEOUT_S` (the shared 2.2 layer's default is 900 s; the 2.1 MuJoCo service's is 300 s; a task sets the
  value its build needs, §13.3); a start that follows failed starts waits min(120, 20·(n − 1)) s first. The watchdog stands
  down once the scene exists, so a long resume replay is not taken for a hang.

#### 13.1 Resume classes
The resume check depends on the simulator's determinism class, which the adapter declares (`Episode(..., resume=...)`;
each benchmark's class is in its doc):

| class | rule |
|---|---|
| `exact` | the replayed state hash must equal the checkpoint's; otherwise the episode ends `resume_failed` (`infra_error = 1`) |
| `approx` | the hash is compared and the result recorded; a mismatch does not end the episode: `resume_state_mismatch = 1`, and the robot's deviation from its checkpointed proprio is recorded (max \|Δ\| over `joint_pos`; the largest TCP position error from `tcp_pose`). Only a gross divergence, a TCP more than `RCB_RESUME_MAX_DEV_M` (0.05 m) from where it was, ends the episode as `resume_failed` (`infra_error = 1`) |

The standard modes are graded by the live episode the trusted service ran (PROTOCOL H.4): the verdict after a resume
is judged on the live state the resumed service continued from, so under `approx` a mismatch can perturb it as well as
what the agent saw; `reward.json` reports `resumes` and `resume_state_mismatch` for it (a trial with
`resume_state_mismatch = 1` can be audited by replaying its trajectory).

#### 13.2 Evidence fields
`final.json` and `episode.json` carry `sim_startups`, `resumes`, `resume_state_mismatch` (0/1), `resume_max_tcp_dev_m`,
`resume_max_joint_dev` (`Episode.final_fields()`), and a give-up adds `gave_up`, `reason` and `infra_error`. Graders copy the
numeric ones into `reward.json`, with `infra_error`.

#### 13.3 What generators emit
- `environment/docker-compose.yaml`, service `sim`: `command: sh /srv/run.sh` and `restart: on-failure:N` (N ≥ 3
  recommended); `RCB_DATA` = the record dir (`/data` unless the benchmark's image uses it otherwise).
- `RCB_STARTUP_TIMEOUT_S` per task, from the measured build time of its family on the evaluation hosts (at least twice the
  slowest measured build; the benchmarks' docs record the measurements). A family whose build exceeds the watchdog loops
  through every restart to a give-up.
- Optional: `RCB_MAX_RESUMES` (2), `RCB_MAX_CALL_WALL_S` (900), `RCB_RESUME_MAX_DEV_M` (0.05).
- `artifacts`: also `journal.f64`, `startups.jsonl`, `server.log` from `service = "sim"`.
- The agent container (`environment/Dockerfile`) and the verifier (`tests/Dockerfile`) `FROM` the `CLIENT_IMAGE` of
  `scripts/eai_standard/client.env`, and any `pip install` installs `client-requirements.txt`: the full pin list inline,
  or `-r client-requirements.txt` with a byte-identical copy in the build context. A new package or version is a change
  to the pins.
- The collect hook starts with `python3 /srv/rcb_limited.py end "$DATA"`: it waits through a resume (no PID file until the
  service is ready), signals only the process that wrote the newest `startups.jsonl` line, resends SIGUSR1 every 30 s, and
  exits 2 when `final.json` already holds the verdict (a give-up, or an in-process grade), 0 when the service dumped the
  episode and exited (the hook then merges the live verdict into `final.json` and renders the video; it replays
  nothing to grade).
- Adapters: `EP = L.Episode(DATA, dim, resume, persist)`; `EP.startup()` before the scene is built and `EP.scene_built()`
  after; `EP.journal(a)` in the control step (its True return stops the call: loops that test `E["done"]` test
  `EP.stopping` too); `S.record_start()` then `EP.begin(...)` instead of logging `start` and installing a SIGUSR1
  handler; `episode=EP, state_sha=..., proprio=...` in `L.Service`; `**EP.final_fields()` in `final.json` / `episode.json`.

#### 13.4 Measured scene builds
In the benchmarks' docs: each records its own build times next to its `RCB_STARTUP_TIMEOUT_S`.

#### 13.5 Cost and tests
One state hash per call (not per step). A resume replays the episode so far without rendering, on the agent's wall
clock (the benchmarks' docs give their replay rates). `python3 scripts/eai_standard/selftest.py` (CPU only, ~2 min) runs
`toy_server.py` under `run.sh` with a stand-in for compose's restart policy and checks: resume between and inside calls,
both classes, the third crash, the watchdog and back-off, client hang-up, the wall bound, both collect-hook outcomes,
SIGUSR1 during a resume, a simulator error, the client's protocol names, malformed requests, a port that is taken, a
negative `Content-Length` (CI job `unit-tests`).

### 14. Evidence and grading (the agent never sees this)
`episode.jsonl` (calls, checkpoints, resumes), `journal.f64`, `startups.jsonl`, `calls/NNNNNN/` (meta + last frames per call),
`server.log`, and at the end `trajectory.npz`, `final.json`, `replay.mp4`. The collect hook signals the service by PID
after a collect hook has stopped the agent's processes; the service judges the live episode in-process (or dumps it with its live verdict
and exits), and the hook writes `final.json`, then the video (recorded live or rendered from the trajectory: the
benchmark's doc). A separate, network-less verifier transcribes `final.json` (PROTOCOL H.4). A GPU lost to a host
systemd reload before the episode was judged is reported as `gpu_lost` (`infra_error`).

### 15. Privileged-mode parity
Recommended: a benchmark's privileged Session offers the same robot information from the same code: `s.camera_info()`,
`s.render_depth(cam)`, `s.robot_spec()`, `s.kinematics(req)` (`s.kinematics_spec()` = `/spec` `kinematics`). Privileged
mode stays privileged (object state through the tooling).

### 16. Per-simulator notes
In the benchmarks' docs: each describes its control rate, `joint_position` and `ee_pose` layouts,
cameras, depth source, `/kinematics` model, proprio columns, live success rule and video, and resume class.

### 17. Known issues
In the benchmarks' docs.

### 18. Versioning
`protocol` in `/spec` = `metadata.protocol` = `eai-standard/2.2`. The 2.x client accepts every 2.x service under both
spellings (`eai-standard/2.`, `rcb-limited/2.`); 2.1 clients work against a 2.2 service (they get float16 per-frame depth
for `include_depth` and ignore the new parts and keys).

## Part 3 — Standard-realtime mode: `eai-standard/2.3`

Time does not stop. The wire protocol of the standard-realtime mode, served by
standard-realtime tasks only (`mode = "standard-realtime"`, `protocol = "eai-standard/2.3"`); the shared implementation
is `scripts/humanoidbench/shared/realtime/rcb_realtime.py`, which other benchmarks' realtime services use unchanged. 2.3
is 2.2 plus the realtime capability below; every 2.2 addition stays optional, so a 2.1 service with this capability is a
2.3 service. Same endpoints, RCB1 frames and grading as 2.1. `/spec.timing` declares it: `realtime: true`, `slowdown` S
(`RCB_SLOWDOWN`; each task declares its default, `[metadata] slowdown`), `control_dt`, `wall_s_per_control_step`,
`max_ahead_steps`. Each task declares its reset budget (Part 1, "Optional reset capability"). S and the reset budget
are part of a result's configuration (running.md).
- **Clock.** An episode starts paused at its starting state. Its clock starts at its first `/submit` or `/observe`
  with `seconds > 0` (after a reset, and after a crash recovery, the episode is paused again) and runs one control step
  every `control_dt` × S seconds of wall time, whatever the agent does, until the episode ends.
- **`/submit`** answers at once. The chunk is expanded into control steps exactly as in 2.1 (`dt`, `linear` / `hold`) and
  becomes the plan from control step `at` (an integer of the episode; absent: the next step; at most `max_ahead_steps`
  ahead), replacing what was planned from `at` on and keeping what is planned before it; `linear` starts from the target
  in force just before `at`. Rows for steps that have run when the request arrives are dropped. When the plan runs out,
  the last target is held (zero-order hold). `meta` adds `start_step`, `late_steps`, `plan_end_step`; every `meta` and
  `/status` add `running`, `planned_steps`, `lag_s`. The answer carries the frames and proprioception of now, no video.
  A service with several action types never combines rows of different types: a chunk interpolates from the target of
  its own type (the simulator's current one when the plan holds another type just before `at`), a type that is not
  interpolable (a command: one row, one control step) is never interpolated, and a gap left before `at` is held steps
  (the simulator's hold row, as after the plan's end) unless the chunk's type is an interpolable target in force there,
  which is then held through the gap. A request the plan cannot take is a 400 and changes nothing.
- **`/observe`** with `seconds = 0` answers at once; with `seconds > 0` it waits while that much robot time runs and
  returns what the cameras saw (2.1's video, frames, proprio rows); it never changes the plan. `cameras: []` asks for
  no images, only proprioception.
- **Grading** is 2.1's: the live episode, judged by the service (PROTOCOL H.4). The journal holds the sim row the
  simulator applied at every control step, so the graded episode's trajectory reproduces the live run whatever the
  timing (the video is rendered from it). Evidence
  added: `ticks.f64` (per journal row: wall time, the call whose chunk gave the row, -1 when held), `calls.jsonl` and
  `submitted.f64` (one line per call and every row as sent, instead of `calls/NNNNNN/`), and in `final.json`
  `realtime`, `slowdown`, `held_steps`, `late_steps`, `max_queue_wait_s`, the clock's record -- `clock_s` (wall seconds
  the clock ran), `max_lag_s` (the furthest a control step ran behind its time; the true maximum), `stalls`,
  `stalled_s` (the wall time the stalls dropped: the robot stood still that long while its clock should have run),
  `stalled_share` = `stalled_s` / `clock_s` -- and what the requests cost: `requests_refused` (answered 4xx),
  `request_mb` (bodies read), `request_busy_s` (simulator-thread time spent on requests). All are checkpointed with the
  episode. The graders repeat the clock's record, `requests_refused` and `request_busy_s` in `reward.json` (numbers; a
  missing one is 0). None of it decides a verdict.
- **Service.** The simulator's thread runs a due control step before any waiting request; behind the clock it runs the
  missed steps back to back, and more than 0.5 s behind it drops the debt (a stall, counted, its seconds added to
  `stalled_s`) instead of fast-forwarding the robot. Checkpoints every second of robot time while the clock runs; the
  reference implementation resumes a crashed service in the same episode, paused.
- **What a request can cost the clock.** A request's body is read, decoded and checked on its HTTP thread:
  a request that is refused for what it says (404, 413, a malformed body, a wrong type / shape / `dt` / camera, a
  chunk longer than `max_chunk_s`) never reaches the simulator's thread, and neither does `GET /spec`. JSON text is
  parsed in the service's process only up to 1 MiB; a body with more of it is parsed by a child process, one at a time,
  and answered as any other -- the 64 MB limit stands, and such a body costs the clock nothing whether it is accepted or
  refused. A negative `Content-Length` is a 400, unread. Behind the clock, a waiting request is served once the clock has
  caught up (or, where the simulator cannot keep up by itself, after four times the time the last request of its kind
  took): requests queue behind each other, not into the clock, so `/observe` may take longer to answer under parallel
  load. A request that renders and alone takes more than 0.5 s makes the next rendering request wait four times that
  long, clock on time or not; requests without images (`cameras: []`, `/status`) are not held back by it. Requests can so
  take at most a fifth of the clock's time. The cameras are rendered (and the proprioception read) at most once per
  control step: parallel observes and watches share that step's frames. A watch (`seconds > 0`) renders inside the
  control steps it watches, so where one render of its cameras takes longer than its frame interval the clock runs late
  and stalls while it lasts -- counted in `stalls` and `stalled_s`. Refusals the episode's state decides (409; an `at`
  too far ahead; too many frames) are answered by the simulator's thread, and a 409 still comes before a 400 for a
  request's fields.
- **Crashes and simulator errors.** No call spans the clock (`/submit` answers at once), so what the agent's commands
  caused is told apart by time and by kind (PROTOCOL H.5: a normal task failure is no infrastructure failure). "After the first command" means after the first control step that ran a row the agent
  sent (held steps before it do not count).
  - A simulator error raised by a control step after the first command (`reason = "error"`) ends the episode as the
    agent's result: `sim_error = 1`, `infra_error = 0`. Before it: infrastructure.
  - A crash (the process dies) is resumed as in 2.1. It counts as the agent's when it happened inside a control step
    after the first command and the process died on SIGSEGV, SIGBUS, SIGFPE, SIGILL or SIGABRT (the service records
    the signal and the crashing stack with `faulthandler` in `crash.log`, a collected artifact, before it dies); a
    crash while the process builds the scene, replays its journal, renders or finalizes is not the agent's; past `RCB_MAX_RESUMES` restarts the trial then ends `sim_crashed_on_call` (the
    agent's 0) if every crash was the agent's, else `sim_crashed` (`infra_error = 1`). A process killed from outside
    (SIGKILL, SIGTERM, the out-of-memory killer: nothing recorded) and a crash before the first command are not the
    agent's; a failed resume is `resume_failed` (`infra_error = 1`). A reset whose new episode the simulator fails to
    build is infrastructure in both standard modes.
- **Agent code** runs where it does in standard mode, in the agent's own container: a controller that streams targets
  through the client, not code uploaded next to the simulator.

## Part 4 — `eai-standard/2.4`: the operations capability

Reference implementation:
[`scripts/eai_standard/v2_4/`](../../scripts/eai_standard/v2_4/), with `rcb_limited.py` and `rcb_client.py`. `rcb1.py`,
`run.sh`, the client image and the client pins are the 2.2 ones in `scripts/eai_standard/`. In the tables below, MUST
means "required of a service that reports 2.4" (what a 2.4 client may rely on).

### 19. Version

`eai-standard/2.4` = 2.3 + the **operations capability** below.
- Every earlier addition stays an optional capability. That covers 2.2's depth, `frame_time_s`, extrinsics,
  `POST /kinematics` and the per-call wall bound, and 2.3's realtime capability (Part 3). So a 2.2 service that adds the
  operations capability is a 2.4 service.
- Standard-mode tasks may declare `protocol = "eai-standard/2.4"`. Standard-realtime tasks stay on 2.3.
- Everything in Parts 1 and 2 holds unchanged: four endpoints (plus `/kinematics`, `/reset` within a declared budget and
  the one below), RCB1, and grading by the live episode.
- `/spec.protocol` is `eai-standard/2.4`.

Why: a native simulator call can run for minutes (IPC and PBD deformables). Under 2.2, a client whose HTTP read timed
out cannot tell whether the call ran, and a retry can execute the same actions twice. The capability makes every call
identifiable, bounded, and queryable after the fact.

### 20. Operation ids and request deadlines

| Item | Level |
|---|---|
| `/submit` and `/observe` accept `meta.operation_id` (string, `[A-Za-z0-9_-]{1,80}`) and `meta.request_deadline_unix_s` (finite number, Unix seconds); a malformed value is 400 | MUST |
| A request whose deadline has passed before execution starts gets **408**; no physics runs | MUST |
| An `operation_id` that the service has already admitted gets **409**, with `operation_id`, the operation record and a pointer to `/operations/<id>`; it is never executed again | MUST |
| The response `meta` echoes `operation_id` | MUST |
| A request without these fields is served as in 2.2 | MUST |
| The client sends a fresh id and a deadline (now + `max_call_wall_s`) on every call to a 2.4 service. It keeps the last id (`Robot.last_operation_id`), and its read timeout is at least the service budget + 120 s | SHOULD (reference client: always) |
| After a timeout the client queries the operation instead of re-sending the actions. A new id for the same actions is a new operation | SHOULD |

### 21. `GET /operations/<id>`

Returns the operation record as JSON: 200, or 404 for an unknown id, or 400 for a malformed id. Fields:
- `operation_id`;
- `status`: `admitted` | `completed` | `error` | `interrupted`;
- `rows_before`: control rows executed before the call;
- `committed_rows`: rows executed when the call ended;
- `stopped`: the call's stop reason, as in 2.2's `meta.stopped`.

After a crash recovery, an operation that was `admitted` becomes `interrupted`, with `execution_uncertain: true` and
`restored_committed_rows` (the rows the resumed episode replayed). `completed` means the call ended. Rows it executed are
in `committed_rows`. The service keeps no copy of the response video. The endpoint is read-only, never steps physics, and
is the only GET this capability adds.

### 22. Call watchdog

| Item | Level |
|---|---|
| A call's budget is `min(max_call_wall_s, request_deadline_unix_s − now)`. The service checks it, and a client disconnect, at control-step boundaries | MUST |
| A native step cannot be pre-empted safely, so the service also owns a hard watchdog. A call that has not finished 60 s past its budget ends the process. The restart then ends the episode as an infra error, `call_watchdog` (`infra_error = 1`), and does not replay into the call that hung | MUST |
| The restart ends the episode as `call_watchdog` only on evidence that the watchdog fired: the watchdog prints into its own file (`call-watchdog.trace`, emptied at every call), and its banner there is that evidence. `call-watchdog.json` alone, or its deadline having passed by the time the container is back, is not: any other crash during a call (a segfault, a CUDA error, an OOM kill) is handled like every crash (§13), and a resume removes both files | MUST |

### 23. Physics-tick ledger and durability

| Item | Level |
|---|---|
| The journal can record, for each executed row, the physics ticks it actually took (`journal.ticks.i64`, int64, one per row). A step that ends early inside its control period records fewer ticks, and `sim_time_s` and `frame_time_s` follow the actual physics clock | MAY (MUST for a service whose steps can end mid-period) |
| A resume replays each row with its recorded tick count. A missing or incomplete ledger ends the episode as an infra error, `resume_failed`. The ledger is cut to the last checkpoint together with the journal, also when that checkpoint has no rows | MUST if the ledger is kept |
| Journal rows, the tick ledger, checkpoints and operation records are fsynced, including their directory, before the call that counts them is reported complete | MUST |
| `dt` must be an integer multiple of the control period within float tolerance; otherwise 400 (2.1 rule, restated) | MUST |

### 24. Evidence

As in 2.2 (`/data/episode.jsonl`, `trajectory.npz`, `final.json`, `calls/`), plus:
- `/data/operations/<id>.json`;
- `journal.ticks.i64`, when kept;
- `call-watchdog.json`, while a call is running, and `call-watchdog.trace` (what the watchdog printed, if it fired).

The verifier still transcribes `final.json` only.

`python3 scripts/eai_standard/v2_4/selftest.py` tests the watchdog's evidence, the tick ledger and the 400 for malformed
bodies on the CPU (numpy only, about 15 s).

### 25. Compatibility

- 2.x clients connect to a 2.4 service unchanged. They send no operation ids and get 2.2 behaviour.
- The 2.4 client sends ids only when `/spec.protocol` is 2.4, so it also works against 2.1–2.3 services.
- A benchmark adopts 2.4 by copying `scripts/eai_standard/v2_4/` unchanged; `ci_checks/check-tooling-identity.sh`
  checks the copies.
