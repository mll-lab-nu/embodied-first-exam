# Standard-mode wire protocol `eai-standard/2.x` (robot as a service)

Part of the task protocol ([README](README.md)): the wire format of the standard modes.

**Version: `eai-standard/3.0`** is the current version. Its rules ("Version 3.0" below) hold on every layer: 2.1–2.4
and the match extension. Each layer keeps its own version string. This document is the interoperability
specification of every 2.x version a task declares today: what a service answers and a client may send. Minor
versions only add, so each part holds for the versions after it unless a later part says otherwise, and the shipped
clients accept every 2.x service. What a task of the standard modes is, and which rules bind it, is in
the [README](README.md) (§3 Modes); the binding rules on the trust boundary (no simulator, state or success
predicate in the agent's reach; the verdict from a trusted record) are stated once, in
its [Appendix H](README.md#appendix-h-invariants-binding) (H.3, H.4), and are not repeated here. How a runner handles a trial that failed
for infrastructure reasons is in [running.md](running.md). What a benchmark's own service adds (its robot, action
types, cameras, proprioception columns, resume class, measured start-up times, known issues) is in its
`tasks/<benchmark>/README.md`.

| Version | Content | Part | Implementation |
|---|---|---|---|
| `eai-standard/2.1` | the base: `/submit` and `/observe`, RCB1 responses, measured proprioception, optional depth noise; the optional reset capability | Part 1 | each benchmark's own service |
| `eai-standard/2.2` | 2.1 + optional capabilities: depth `last` / `frames`, per-frame steps, times and extrinsics, camera intrinsics and mounting, `robot_spec`, `world`, `POST /kinematics`, a per-call wall-clock bound; one shared service layer | Part 2 (§1–§18) | [`embodied_first_exam/standard/`](../../embodied_first_exam/standard/) |
| `eai-standard/2.3` | 2.2 + the realtime capability: a clock that does not stop | Part 3 | `embodied_first_exam/standard/realtime/rcb_realtime.py` |
| `eai-standard/2.4` | 2.3 + the operations capability: operation ids, request deadlines, `GET /operations/<id>`, a call watchdog, a physics-tick ledger | Part 4 (§19–§25) | [`embodied_first_exam/standard/v2_4/`](../../embodied_first_exam/standard/v2_4/) |
| `eai-standard/2.x+match/1.0` | an extension, not a version: 2.1 (lockstep, turn-based) or 2.3 (realtime) in front of a match service, plus the match's own calls `/start`, `/ready`, `/say`, `/team` and its score in `meta` | Part 5 (§26–§31) | [`embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/`](../../embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/) |

Which version a task serves is its `[metadata] protocol` (= `/spec.protocol`); which benchmarks serve which version is
in their docs, not listed here. Every version is also offered as MCP tools, one per endpoint, in the same task ("MCP
tools", the last section).

**Spelling.** Services and tasks report `eai-standard/2.x`; the shipped clients also accept `rcb-limited/2.x`. No task
declares a version before 2.1.

### Version 3.0

`eai-standard/3.0` is a set of rules every layer follows (`/spec.standard = "eai-standard/3.0"`); a layer's own
version string (`/spec.protocol`, `[metadata] protocol`) says which capabilities it has. Where a part below says
otherwise about `/observe`, `/submit` or the clock, this section wins; the older text stays as the history of 2.1–2.4.
The HTTP interface of every layer is written out as OpenAPI 3.1 in
[`eai-standard-3.0.openapi.yaml`](eai-standard-3.0.openapi.yaml); `ci_checks/check-openapi-contract.py` runs the
reference services of 2.1–2.4 and checks their answers against it.

- **Standard mode is Gym's `env.step`.** The world stands still between calls. `/submit` blocks until its chunk has run
  and answers with the chunk's video (as asked), its proprioception and `meta.duration_s`, the robot seconds it ran
  (`planned_duration_s`: what it declared, rows × `dt`; a planner type such as `ee_pose`: the planned duration where the
  service knows it).
- **A hold chunk lets time pass.** `/submit` with `{"type": <type>, "interpolate": "hold", "seconds": n}` and no rows
  holds the target in force (the last command, as 2.1's watch held it) for n seconds of robot time (whole control steps,
  at least one; at most `max_chunk_s`) and answers as any `/submit` (`meta.hold = true`, `executed_rows = 0`,
  `duration_s`). `max_chunk_s` is the one cap of a chunk and of a hold chunk in every layer (2.1–2.4 and the match
  extension; `max_watch_s` is gone). Rows and `seconds` together (any value, 0 too), or no rows without a hold, are a
  400 in every layer. In realtime mode it answers at once and plans the target in force for n seconds from `at`.
- **`/observe` only reads.** It never lets time pass, never waits and never changes the plan. `last_s = 0` (the default)
  returns the current frame and the proprioception of now; `last_s = n` the frames recorded in the last n robot seconds
  (at most `buffer_s`), `video_fps` apart, with the proprioception of their steps (`meta.last_s`: what they cover; none
  recorded yet: the current frame). Every answer with images (`/observe`, `/submit` and `/reset`, every layer; in 2.3
  also a service without a recorder) adds `meta.frame_step`, the control step its newest image shows. `seconds > 0` is
  a 400 that names the hold chunk. Per-frame depth with `last_s > 0` (`include_depth`; 2.2/2.4 `depth: "frames"`) is
  served only when every requested camera is one whose depth the recorder keeps (`/spec.timing.recorder.depth`);
  otherwise it is a 400 that says to ask for depth with `last_s = 0` (the current frame's depth), in every layer. 2.2/2.4
  `depth: "last"` with `last_s > 0` is not refused: it returns the current frame's depth (`last_depth/<cam>`), which is
  not the recorder's.
- **The recorder.** `/spec.timing.recorder` declares `cameras` (every camera), `fps`, `buffer_s` (`RCB_LOOKBACK_S`,
  default 3), `records` (when it records) and `depth` (the cameras whose depth it keeps). Standard mode: 10 fps
  (`RCB_CAMERA_FPS`, default 10), recorded while a `/submit` runs (hold chunks too): every 1 / `fps` of robot time, the
  RGB image of every camera and the proprioception, into a ring of the last `buffer_s` seconds (`records: "during
  /submit"`, `depth: []`), cleared at a reset; no process of its own. Realtime mode: 30 fps (`RCB_CAMERA_FPS`, default
  30), Part 3's recorder ("Cameras"), recording continuously while the clock runs, with the depth of the depth cameras;
  an adapter without its two hooks records on the simulator's thread into the same ring at 10 fps (each render there
  costs the clock its time), which its `fps` says.
- **The field checks are the same in every layer** (2.2/2.4 answer them in `rcb_limited.py`, before the adapter sees
  the call): `dt`, `seconds`, `video_fps` and `last_s` are JSON numbers (not `true`/`false`, not a string) and finite,
  `null` is the default; `video_fps` lies in [1, `max_video_fps`] (2.1/2.3: 30; 2.2/2.4: `/spec.max_video_fps` where
  the adapter declares it, else the larger of 30 and `control_hz`); `interpolate` is one the service knows (2.2/2.4:
  `linear` or `hold`); a chunk's rows × `dt` is at most `max_chunk_s` (a planner type such as `ee_pose`, whose duration
  the service plans, is not counted so). Each is a 400 that leaves the episode as it was. A `/finish` body is read
  only up to the 64 MB limit (more: 413, a negative `Content-Length`: 400) though it is ignored. After `/finish`
  `GET /operations/{id}` (2.4) is a 409 like every other call but `GET /spec` and `GET /status`, and `resets_left` is
  0. A hold chunk's `planned_duration_s` is the `seconds` it sent (what it declared); `duration_s` what ran (a hold the
  adapter stops early, blocked, is shorter). 2.3's hold answer carries `hold = true` and `executed_rows = 0` like the
  other layers'. The standard recorder of 2.2/2.4 can be turned off (`Service(record_frames=False)`, as 2.1's
  `record_frames`): `/spec.timing.recorder` then says it records nothing and `last_s` answers the current frame; 2.3
  without a recorder declares the same (`cameras: []`). With 2.1's `record_frames = "delivered"` a recorded frame
  holds the images the agent was sent at that step, and `last_s` returns only frames that hold every requested camera.
- **The realtime clock** starts at the episode's first `/submit` (again after a reset and a crash recovery), never at an
  `/observe`; `/submit` answers at once with `duration_s` and `end_step` (= `plan_end_step`). An `/observe` before the
  simulator thread has published its first state is a 503 `{"error": "warming up"}` (retry).
- **`/finish`** is required in the standard and realtime modes ("Agent-ended episodes"; RoboEngineer and Embodied
  Olympics - Match are exempt: a match ends by its rules, its `/finish` is a 404, and its clock starts at its `/start`
  barrier, a deviation it declares in `/spec.timing.deviations`).
- **Every agent-facing endpoint has an MCP tool** ("MCP tools", the last section): `spec`, `observe`, `submit` (a hold
  chunk too), `finish`, and `reset` where the task has a reset budget, `kinematics` where the service serves it.
- **The shipped clients**: `get_obs(last_s=0)` (`get_obs(seconds=…)` raises and names `hold`), `hold(seconds)` (the
  hold chunk), `submit(...)`, `finish()`.

**Citing this document.** Numbered sections are unique in the document: §1–§18 are Part 2 (so "§13" is the shared
layer's crash recovery), §19–§25 are Part 4, §26–§31 are Part 5. The sections of Parts 1 and 3 are cited by their titles. A section whose
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
| GET | `/status` | — | JSON: the shared sidecar (`rcb_service.py`): `{calls, rows, control_steps, done, reason, elapsed_s}`, plus `step_limit`, `steps_left` with a step limit and `episode`, `control_steps_total`, `resets_left` with a reset budget; a benchmark's own service: `{step, calls, physics_steps, done, reason, elapsed_s}` |
| POST | `/observe` | RCB1 or JSON `{cameras, last_s, video_fps, include_depth, video}` (3.0; before: `seconds`) | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, include_depth, note}` + part `actions` float32 (T, dim); a hold chunk (3.0): header `{type, interpolate: "hold", seconds, ...}`, no part | RCB1 |

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
benchmark's), `frame_step` (int64 [N]: the control step of each returned frame, on an `/observe` with `last_s > 0`). Requests over 64 MB → 413 (the client refuses to send one); a response over 256 MB drops
`frames/`/`depth/` and says so in `meta.degraded`. `rcb1.py` (encode/decode, `python -m rcb1 unpack f dir`) is shipped
with the client.

### `meta` (in every response)
`step` (rows executed so far), `calls`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio` =
`{"layout": [names], "now": [floats]}`, `cameras` (per camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the whole
key omitted when the task sets `RCB_OBS_CALIBRATION=0`), `done`, `reason`. The shared sidecar (`rcb_service.py`) says
`rows` and `control_steps` instead of `step` and `physics_steps`, and sends no `cameras` calibration (a benchmark's own
service does). `cameras` is the calibration of the state the
response ends in (the `last` frame, the final sample of `frames` / `depth`): static cameras never move, a camera on the
robot moves with it, and for each requested moving camera the response carries the part `cam2world_gl/<cam>` (one
pose per returned frame; `spec.camera_calibration`). `time_s` / `time_left_s` are the agent's clock (below; `/spec`
states it: the shared 2.1 sidecar in the top-level `clock`, the 2.2 layer in `budget.clock`, a benchmark's own service
in `budget.clock` or `budget.wall_clock_note`).

| answer | adds |
|---|---|
| `/submit` | `chunk_id`, `type`, `executed_rows`, `control_steps_chunk` (a benchmark's own service: `physics_steps_chunk`), `duration_s`, `planned_duration_s`, `hold` (a hold chunk), `clipped` `[{row,index,reason}]`, `n_clipped`, `plan` (where the service plans), `frame_step` (with images), `ok`; the shared sidecar also the adapter's step fields (never a success or progress field) |
| `/observe` | `obs_id`, `last_s`, `frame_step` (with images), `seconds` (always 0), `control_steps_watch` (always 0; a benchmark's own service: `physics_steps_watch`), `ok` |
| `/reset` | `frame_step` (with images: the new episode's first step), `ok` |

### `/submit` semantics
- `joint_position` rows are `dt` seconds apart, `dt` a positive whole multiple of the control step (`control_dt`);
  anything else is rejected (400), never rounded. A service may cap `dt` further and says so in its doc (Embodied
  Olympics - Match: at most 0.5 s). The service streams drive targets with `interpolate = "linear"`
  (default) or `"hold"` between rows, exactly as a real controller consumes a chunk. Out-of-limit values are clipped
  and reported (continuous joints have `null` limits and are never clipped). A chunk may cover at most `max_chunk_s`.
- Planner-executed types such as `ee_pose` state their frame, quaternion order and end-effector reference in `/spec`;
  a failed plan is reported in `meta.plan`, not as an error.
- Types a service does not offer yet are listed under `spec.action_types.not_yet`. The action layout, the action
  types and their dtype are the benchmark's (its doc).
- Video is captured every `physics_hz / video_fps` physics steps from the requested cameras, plus the first and last
  frame.
- The chunk is appended to the recorded trajectory and to `episode.jsonl`. From 3.0 a success ends nothing and is not
  shown; the agent ends the episode ("Agent-ended episodes"). Before 3.0: the task predicate was evaluated after the
  chunk, and the first success ended the episode (`done`, `reason = "success"`).

### `/observe` semantics
From 3.0: `last_s` ("Version 3.0"); `seconds > 0` is a 400 and a hold chunk takes its place. Before 3.0:
`seconds = 0` (default) returned the current frames, free (no physics); `seconds > 0` (≤ 30 s) held the last
command, advanced physics and returned the video; the predicate was checked afterwards. Watching costs no budget beyond
the wall clock; the simulated time is recorded as cost.

### Errors (no physics executed)
| code | when |
|---|---|
| 400 | wrong type/dim, a chunk with no rows (other than a hold chunk), a hold chunk with rows, `/observe` with `seconds > 0` (3.0), NaN/inf, a field of the wrong JSON type (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list), `dt` or `seconds` out of range or `dt` not a multiple of the physics step, chunk too long, bad interpolate/video value, `video_fps` outside [1, `max_video_fps`] ("Version 3.0"), a JSON `true`/`false` or string where a number goes, more images than `max_frames_per_call` in one response (PROTOCOL §3), malformed body |
| 409 | episode already finished (`done`); the trial is over; after `/finish` every call but `GET /spec` and `GET /status` (2.4's `GET /operations/{id}` too) |
| 413 | body over 64 MB, `/finish`'s too (`rcb_client.py` raises before sending such a body) |
| 503 | realtime (2.3): an `/observe` before the simulator thread has published its first state (`{"error": "warming up"}`; retry) |
| 500 | simulator error; the episode ends with `reason = "error"` (the client raises `EpisodeOver`; the verifier reports `sim_error = 1`) |

### Episode semantics
The service starts the episode when it is ready (seed hidden inside). From protocol v3.0 the agent ends it (POST
`/finish`, "Agent-ended episodes" below; required in the standard and realtime modes), or the step cap, the end of the
agent's session (`timeout`), the task's failure rule or an error does; the state it ends in is judged. Before v3.0 (and
in a service without the feature) the first success ended it; otherwise it ended when the agent phase ended
(`timeout`) or on an error, and the predicate was evaluated once more at episode end.

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
for infrastructure reasons is the runner's rerun (PROTOCOL Appendix H.5, [running.md](running.md)). A
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
replayed to grade it (PROTOCOL H.4). The video is a post-hoc replay of `trajectory.npz` after the verdict by default, and a live
recording where the simulator is not verified bit-wise replayable (`video_source`, PROTOCOL §4); it never decides
anything. With resets, the shared 2.1 sidecar service (`rcb_service.py`, one file copied into each benchmark that runs it,
also under the 2.3 realtime layer; the copies behave the same on the wire, and a few differ only in comments) keeps the first episode as evidence too: `trajectory.first.npz` (its
rows from the journal) and `replay.first.mp4`, rendered after the graded video; `final.json` says how it ended
(`first_success`, `first_reason`; a success ends the trial, so after a reset `first_success` is 0) and decides nothing
with it. A separate verifier transcribes `final.json` into `reward.json` (`graded_by_live` = 1); the shared grader
(`embodied_first_exam/standard/v2_1/grade.py`) also writes `first_success`, the first-attempt, no-reset result reported
beside the graded one, and copies the first episode's files. A service of a benchmark's own keeps no first episode and
reports `resets` only; `first_success` is then `success` when no reset was made, else 0 (running.md "Results").
`infra_error = 1` means there is no verdict on the agent: `final.json` is
missing, unreadable or not finalized, or the service reported `sim_crashed`, `resume_failed`, `instance_mismatch` or
(2.4) `call_watchdog`.

### Live recording (sidecar only; the agent sees none of it)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl`: captured during the
episode, or rendered from the recorded trajectory where a post-hoc replay is allowed (PROTOCOL §4), frames stamped with
the call, never affecting the verdict. The reference recording is RoboTwin's
(tasks/robotwin-2/README.md).

### Proprioception (2.1)
A benchmark's 2.0 columns stay where they were; 2.1 appends what a real robot reports (measured joint positions and
velocities, the gripper opening, the tool-centre pose, a drive-effort estimate), grouped in `spec.proprio_groups` (first
column, count, meaning). The columns are the benchmark's (its doc). Not exposed: object poses, segmentation, contact
forces on objects, the success predicate (PROTOCOL Appendix H.3).

Depth (`include_depth`) is exact by default. `RCB_DEPTH_NOISE=realsense` (task env) adds stereo-camera-like noise,
σ = 2 mm + 2.5 mm·z² (z in m), and 1 % dropouts (0 = no reading), seeded by `RCB_DEPTH_NOISE_SEED`; it never affects
physics.

### Per-benchmark 2.1 services
These services serve the same endpoints and frames with their own action layouts, control rates and cameras; each is
described in its benchmark's `tasks/<benchmark>/README.md`:
- the MuJoCo service, `embodied_first_exam/benchmarks/dextoolbench/sim/server_mj.py` (DexToolBench; the same file serves
  the MuJoCo Playground ALOHA and Panda tasks as `embodied_first_exam/benchmarks/mujoco-playground/sim/server_mj.py`);
- the MetaWorld+ service, `embodied_first_exam/benchmarks/metaworldplus/sim/server_mw.py`;
- the RoboCasa service, `embodied_first_exam/benchmarks/robocasa/sim/server_casa.py` (RoboCasa and RoboCasa-GR1);
- the RoboTwin service, `embodied_first_exam/benchmarks/robotwin-2/sim/server.py`;
- the shared sidecar `rcb_service.py`, one copy per benchmark (`embodied_first_exam/benchmarks/<benchmark>/sim/` or
  `standard/`, HumanCLAW's at the folder's top), with that benchmark's adapter: KinDER, HumanoidBench, Panda Dynamic
  Scenes, LIBERO-Max, VLABench, BiGym 2.0, Embodied Olympics - Fun, Embodied Safety Exam, HumanCLAW, the realtime tasks
  of RoboCasa365, MyoSuite and MuJoCo Playground, and ABC-Sim's realtime tasks (in its image,
  `images/abc-sim/tools/realtime/`); the 2.3 realtime layer (`rcb_realtime.py`) runs over it.

### Optional reset capability
Each task declares its own budget N (PROTOCOL §2): the `RCB_RESET_BUDGET` default of its `sim` service, served as
`/spec.budget.reset` and stated in its instruction (templates: 0 in both standard and realtime mode). Any
2.x service may implement the capability; which ones do is in their benchmarks' docs. With N > 0, `/spec.budget.reset =
N`, `/spec.reset` describes it, and `POST /reset` (RCB1 or JSON `{cameras, video}`, no physics) abandons the running
episode and starts a new one from the same frozen state, `N` times in all; `/status` and `meta` add `episode`,
`resets_left` and `control_steps_total`. After `/finish` or once the agent's time is up, `/reset` returns 409, as it does
when the budget is spent; a success changes nothing (from 3.0; before 3.0 a success ended the trial and `/reset` was a
409 after it). Only the last episode is graded. With N = 0 (or no declaration) `/reset` is 404. The reset
budget is part of a result's configuration: results with different budgets are not ranked together (running.md).

### Agent-ended episodes
PROTOCOL §3 "Agent-ended episodes": required from protocol v3.0 for every standard and realtime task served by an
`eai-standard/2.x` service of its mode (`normalize` writes `RCB_AGENT_END: "1"` in its `sim` service's environment;
`ci_checks/check-agent-end.py` checks it), an optional capability before. `RCB_STEP_LIMIT: "<N>"` adds a step limit
(what one step is: the service's `/spec` and the task's instruction); without one, the service's own step cap
(`/spec.max_control_steps`, the task's episode length) ends the episode the same way (`reason = "step_limit"`). Every
2.x service implements it (2.1: the sidecar `rcb_service.py`; 2.2 and 2.4: `rcb_agent_end.py` with the adapter; 2.3:
`rcb_realtime.py` over `rcb_service.py`; a benchmark's own 2.1 server: the same wire). The wire, additive (a 2.0 or 2.1
client that never calls `/finish` is served as before, its session's end ending the episode):
- `/spec.success_signal` says the success is hidden; with a step limit `/spec.budget.steps = /spec.max_control_steps = N`,
  and every `meta` and `/status` add `step_limit` and `steps_left`.
- No answer depends on the task's success: no `done` / `reason = "success"`, no 409, no early end of a chunk and no
  per-call work caused by it, `resets_left` and `/reset` as before a success, no success or progress field of the
  service's own (stages reached, a settled-check counter) in `meta` or `/status`.
- `POST /finish` (its body is optional and ignored: the shared layers 2.1-2.4 never parse it; clients send `{}`,
  which every service accepts, as it does an empty body) ends the episode (`reason = "finished"`) and answers `{"ok": true, ...}` with `/status`'s
  fields; after it every call but `GET /spec` and `GET /status` is a 409. Without the feature it is a 404.
- At the step limit the episode ends by itself (`reason = "step_limit"`; the chunk stops at that step); then `/submit`
  and `/finish` are 409, `/observe` still answers.
- The collect hook's signal at the end of the agent's session ends the episode with `reason = "timeout"`.
- Realtime (2.3): `/finish` is answered by the simulator thread between control steps; the clock stops with the episode
  (no step runs after it) and a settle or hold window runs after the agent is gone, off the clock. (Before 3.0 the
  pending watches were answered here; from 3.0 `/observe` never waits, so none is pending.)
- Resets: as before a success (`resets_left` counts as without one); after `/finish` or the session's end `/reset` is a
  409; after a failure end or the step cap it is allowed while the budget lasts. Only the last episode is graded.
- The verdict: the task's own rule on the state the episode ended in, with its settle or hold window run from there on
  the live simulator (a hold window counts the steps already held). A success reached and then undone is 0. A goal the
  task judges as events (a referee's call, moments in a sequence such as key strikes, a check at a trigger) is judged on
  them as they happened; the task says which (RoboDojo: `rcb_robodojo.END_JUDGEMENT`, where an ordered stage sequence
  is judged from the episode except its last stage, which must still hold at the end). The task's failure rules keep
  running to the end, with one rule by judgement type: on a goal judged on the end state, a failure rule that ends the
  episode gives 0, after a success too; on a goal judged as events, an event that happened stands (a referee's call or
  a scored point is not taken back by a later foul or fall), and a failure rule ends the episode with the events
  reached so far. A simulator error is judged as without the feature.
- `final.json` adds `success_signal = "hidden"`, `ended_by` (`finish`, `step_limit`, `session_end`, `failed`: the
  task's own failure rule, `error`), `hidden_success_seen`, `hidden_success_first_step`, `trial_hidden_success_seen`,
  `finish_time_s` and, with a step limit, `step_limit` and `steps_used`; `reward.json` adds `ended_finish`,
  `ended_step_limit`, `ended_session_end` (evidence only; the shared 2.1 grader `v2_1/grade.py` and RoboDojo's copy
  them, final.json is the record). Which limit ended a session (`session_end`) is the runner's record: Harbor's
  `AgentTimeoutError` for the time limit, the gateway's `budget_stop` for the token budget; over the token budget an
  agent-ended task is graded on its end state, not failed on top (`scripts/write_task_results.py`, by the task's mode).
- Implementation for the 2.2 and 2.4 layers: `embodied_first_exam/standard/agent_end/rcb_agent_end.py` (`Service`,
  `serve`, `hidden_success`, `final_fields`, `steps_left`; files-only image `agent-end-files`); an adapter without
  `finish()` refuses to start with the feature on; tests `agent_end_selftest.py`.
- Implementation for the 2.1 sidecar and the 2.3 realtime layer: `rcb_service.py` (`AGENT_END`; the adapter's
  `end_judgement` = `"state"` or `"events"`, `end_window_steps` for a settle or hold window, `hidden_keys` for progress
  fields of `step()`'s info, `info["step_cap"]` for a done that is the episode's length) and `rcb_realtime.py` (the
  `/finish` route); tests `agent_end_v21_selftest.py`.
- `/spec.success_signal` is the key a front end reads: where it says `hidden`, an MCP front end offers a `finish` tool
  that sends `POST /finish`.

## Part 2 — `eai-standard/2.2`: capabilities added to 2.1

> 2.2 is a minor version of `eai-standard/2.1` (Part 1): everything there holds unless
> this part says otherwise, every 2.2 addition is an optional capability, and a request written for 2.0 or 2.1 gets
> the same answer as before (plus parts and keys an old client ignores).

**One implementation.** The source is [`embodied_first_exam/standard/`](../../embodied_first_exam/standard/): the service layer
`rcb_limited.py` (HTTP, RCB1 responses, the protocol helpers, the `/spec` self-check, crash recovery), the client
`rcb_client.py` + `rcb1.py`, the sidecar entrypoint `run.sh`, and the client image: `client.env` (the one client base,
pinned by digest) and `client-requirements.txt` (exact pins). Tasks carry no copies of it: every 2.2 task's Dockerfiles take the files unchanged from the files-only image
`standard-files` (`COPY --from=<image@digest>`, `images/standard-files/FILES.json`): the client's `rcb_client.py` and
`rcb1.py` to `/opt/tools/`, the sidecar's `rcb_limited.py`, `rcb1.py` and `run.sh` to `/srv/`. Each benchmark writes
only its adapter `server.py` (the robot, the cameras, the clock), in `embodied_first_exam/benchmarks/<benchmark>/sim/`
or in the task's `environment/sim/` (`toy_server.py` is the smallest complete one).

**Design principles.**
1. *A robot, not a simulator.* No state query, no success query, no step limit; resets only within the task's declared
   budget; the wall clock is the budget; actions and simulated time are reported as cost; the agent ends the episode
   (`/finish`) and the state it ends in is judged (before 3.0 the first success ended it).
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
| POST | `/observe` | RCB1 or JSON `{cameras, last_s, video_fps, video, depth}` (3.0; before: `seconds`) | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, depth, note}` + part `actions` float32 (T, dim); a hold chunk (3.0): header `{type, interpolate: "hold", seconds, ...}`, no part | RCB1 |
| POST | `/finish` (3.0) | optional, ignored | JSON: ends the episode ("Agent-ended episodes", Part 1) |
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
| `cameras` | every camera | names from `spec.cameras`; the client sends `spec.default_cameras` when given none; in 2.1 standard mode `[]` also means every camera (in realtime mode `[]` means no images) |
| `video_fps` | the service's | frames per simulated second |
| `video` | `mp4` (submit), `frames` (observe) | `mp4` \| `frames` \| `both` \| `none` |
| `depth` (2.2) | `none` | `none` \| `last` \| `frames`; JSON `true` = `last` |
| `include_depth` (2.0/2.1) | `false` | with no `depth` field: `true` answers as 2.1 did (`depth/<cam>` float16 per frame) |
| `last_s` (observe, 3.0) | 0 | 0 = the current frames; n = the frames recorded in the last n seconds; never physics (`seconds > 0`: 400, "Version 3.0") |
| `type`, `dt`, `interpolate`, `note` (submit) | | as 2.1 |

### 4. `meta`
2.1's keys (`step`, `calls`, `control_steps`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio`, `done`,
`reason`), with `cameras` = per requested camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`, `image_size` at the last
frame (omitted when the task sets `RCB_OBS_CALIBRATION=0`). `/submit` adds `chunk_id, type, executed_rows,
control_steps_chunk, physics_steps_chunk, duration_s, planned_duration_s, clipped [{row,index,reason}], n_clipped,
plan [...], frame_step, ok`; `/observe` adds `obs_id, last_s, frame_step, seconds, control_steps_watch,
physics_steps_watch`. Both add **`stopped`** (2.2): `null`, or why the service
stopped the call early (§12).

### 5. `/spec`
2.0/2.1 keys, unchanged: `protocol` (`"eai-standard/2.2"`), `simulator`, `robot`, `task_text`, `control_hz`,
`physics_substeps`, `max_chunk_s`, `cameras`, `action_types`, `proprio_layout`, `proprio_groups`, `static`
(scene facts: names, sizes, colours; never a position), `budget` (`{"reset": N, "steps": null, "wall_clock_s",
"clock"}`; `clock` says what `time_s` / `time_left_s` count from: the agent's first request, Part 1 "The agent's clock";
the shared layer fills it in and keeps the clock, `rcb_limited.agent_time`; the 2.4 layer has no clock of its own:
its adapter keeps it and states it, as RoboArc's IKEA service does). 2.2 adds:

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
As 2.1 (`joint_position` rows `dt` apart, a whole multiple of the control period, `linear` or `hold`, clipped and
reported; a chunk covers at most `max_chunk_s`). `ee_pose` rows are end-effector targets solved by the benchmark's IK or
planner (its doc); a failed row is reported in `plan`. Not yet: `joint_delta`, `joint_velocity`, `ee_delta`,
`joint_torque` (`spec.action_types.not_yet`). From 3.0 a success ends nothing ("Agent-ended episodes", Part 1); before
3.0 the task predicate was evaluated after a chunk and the first success ended the episode.

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
answer after any end but `/finish`; after `/finish` every call but `/spec` and `/status` is a 409), 413 body over 64 MB, 500 simulator error: **on `/submit` and `/observe` the episode ends** with `reason = "error"`.
A negative `Content-Length` is a 400, answered without reading the body. The service listens on port 8000 of a network
namespace that, under Harbor's egress control, the agent's container shares: if a process of the agent holds the port
when the scene is built, the service waits for it (the agent's own time) instead of exiting.

### 12. Per-call bounds (2.2)
No step cap, and the wall clock stays the episode's only budget. Two bounds keep one call from holding the
single-threaded service:
- **`max_call_wall_s`** (`/spec`, default 900 s, below the client's read timeout, which is at least `max_call_wall_s` + 120 s and at least 1800 s; task env `RCB_MAX_CALL_WALL_S`): a
  `/submit` or `/observe` that runs longer stops at the next control step and returns normally, with `meta.stopped =
  "max_call_wall_s"` and `executed_rows` below the rows sent.
- **Client hang-up**: when the client closes the connection (its read timeout, a killed process), the call stops at the
  next control step (`stopped: "client_disconnected"` in `episode.jsonl`); the response is not delivered.
In both cases the executed prefix stays: it is journaled and checkpointed like any call, and `/status` and the next
`meta.proprio.now` report the state after it, like a real controller that loses its link. An old client sees a normal
response with fewer rows executed; `rcb_client` exposes `Result.stopped` and prints a one-line warning.

A third bound keeps one call from exhausting the service's memory (every frame is held until the response is sent):
**`max_frames_per_call`** (`/spec`): the images a call may return; the rule is PROTOCOL §3 "Images per call" (shared
helpers: `rcb_limited.frames_per_call`, `check_frames`, `Recorder(max_images=...)`).

### 13. Crash recovery (the shared layer's default behaviour)
The shared layer (`rcb_limited.Episode`; adapters call it as `toy_server.py` does) resumes a crashed service in the same
episode. This is an implementation of the reference services, not a rule (PROTOCOL Appendix H.5 is the
runner's rerun of an infrastructure-failed trial; running.md).
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

#### 13.3 What a 2.2 task declares
- `environment/docker-compose.yaml`, service `sim`: `command: sh /srv/run.sh` and `restart: on-failure:N` (N ≥ 3
  recommended); `RCB_DATA` = the record dir (`/data` unless the benchmark's image uses it otherwise).
- `RCB_STARTUP_TIMEOUT_S` per task, from the measured build time of its family on the evaluation hosts (at least twice the
  slowest measured build; the benchmarks' docs record the measurements). A family whose build exceeds the watchdog loops
  through every restart to a give-up.
- Optional: `RCB_MAX_RESUMES` (2), `RCB_MAX_CALL_WALL_S` (900), `RCB_RESUME_MAX_DEV_M` (0.05).
- `artifacts`: also `journal.f64`, `startups.jsonl`, `server.log` from `service = "sim"`.
- The agent container (`environment/Dockerfile`) and the verifier (`tests/Dockerfile`) `FROM` the `CLIENT_IMAGE` of
  `embodied_first_exam/standard/client.env`, and any `pip install` installs `client-requirements.txt`: the full pin list inline,
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
clock (the benchmarks' docs give their replay rates). `python3 embodied_first_exam/standard/selftest.py` (CPU only, ~2 min) runs
`toy_server.py` under `run.sh` with a stand-in for compose's restart policy and checks: resume between and inside calls,
both classes, the third crash, the watchdog and back-off, client hang-up, the wall bound, both collect-hook outcomes,
SIGUSR1 during a resume, a simulator error, the client's protocol names, malformed requests, a port that is taken, a
negative `Content-Length` (CI job `unit-tests`).

### 14. Evidence and grading (the agent never sees this)
`episode.jsonl` (calls, checkpoints, resumes), `journal.f64`, `startups.jsonl`, `calls/NNNNNN/` (meta + last frames per call),
`server.log`, and at the end `trajectory.npz`, `final.json`, `replay.mp4`. The collect hook signals the service by PID
after a collect hook has stopped the agent's processes; the service judges the live episode in-process (or dumps it with its live verdict
and exits), and the hook writes `final.json`, then the video (a post-hoc replay, or a live recording where PROTOCOL §4
requires one). A separate, network-less verifier transcribes `final.json` (PROTOCOL H.4). A GPU lost to a host
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

## Part 3 — Realtime mode: `eai-standard/2.3`

Time does not stop. The wire protocol of the realtime mode, served by
realtime tasks only (directories ending in `-realtime`, `protocol = "eai-standard/2.3"`); the shared implementation
is `embodied_first_exam/standard/realtime/rcb_realtime.py`, which other benchmarks' realtime services use unchanged. 2.3
is 2.2 plus the realtime capability below; every 2.2 addition stays optional, so a 2.1 service with this capability is a
2.3 service. Same endpoints, RCB1 frames and grading as 2.1. `/spec.timing` declares it: `realtime: true`, `slowdown` S
(`RCB_SLOWDOWN`; each task declares its default in its `sim` service), `control_dt`, `wall_s_per_control_step`,
`max_ahead_steps`. Each task declares its reset budget (Part 1, "Optional reset capability"). S and the reset budget
are part of a result's configuration (running.md).
- **Clock.** An episode starts paused at its starting state. Its clock starts at its first `/submit` (3.0; before:
  also an `/observe` with `seconds > 0`; after a reset, and after a crash recovery, the episode is paused again) and runs one control step
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
- **`/observe`** answers at once and never changes the plan (3.0: it reads the recorder, `last_s`; `seconds > 0` is a
  400; before 3.0 `seconds > 0` waited while that much robot time ran). `cameras: []` asks for
  no images, only proprioception.
- **Cameras (the recorder).** Where the adapter can copy its state (`render_state()`) and draw such a copy
  (`render_from(state, cameras, depth)`), a recorder -- a process of its own, never the simulator's thread -- records
  the cameras while time runs, and `/spec.timing.recorder` declares it: `cameras`, `fps` (`RCB_CAMERA_FPS`, default 30),
  `resolution`, `buffer_s`, `records`, `depth` (the depth cameras: their depth is recorded too).
  The simulator thread hands it a copy of the state every 1 / `fps` of robot time (a recorder that is slower skips
  copies; it never holds the clock back); it draws the copy with its own copy of the scene, so recording cannot change
  the journal, the trajectory or the verdict. The frames go into a ring of the last `buffer_s` robot seconds, each
  tagged with its control step. `/observe` reads only the recorder, on its own thread: it answers at once, never
  waits, never moves time and never reaches the simulator. `last_s = 0` (the default) returns the current frame (the
  newest recorded) with the proprioception of now; `last_s = n` the frames recorded in the last n robot seconds
  (capped at `buffer_s`; none recorded in it: the newest frame), `video_fps` apart, with the proprioception of their
  steps (`meta.last_s`: what they cover). `seconds > 0` is refused (400). The clock starts at the first `/submit`
  (after a reset too); a `/submit` answers at once with the newest recorded frames. An answer with images adds one
  field, `frame_step`: the control step the newest image shows (the recorder may be behind `control_steps`); at most 8
  answers with images are built at a time (past that: without frames, `frames_skipped`). A recorder that dies is
  restarted; meanwhile answers come without frames (`frames_pending`). final.json adds `camera_worker` (frames
  rendered, copies skipped, render time). Adapters without the two hooks render on the simulator's thread into the same
  ring (3.0) at 10 fps (each render costs the clock its time; `fps` says so), as below. Before the simulator thread has
  published its first state, an `/observe` is a 503 `{"error": "warming up"}`.
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
  take at most a fifth of the clock's time. Without a recorder, the cameras are rendered (and the proprioception
  read) at most once per control step: parallel observes share that step's frames. (Before 3.0 a watch, `/observe`
  with `seconds > 0`, rendered inside the control steps it watched, so where one render of its cameras took longer than
  its frame interval the clock ran late and stalled while it lasted; from 3.0 that request is a 400.) The clock's
  stalls are counted in `stalls` and `stalled_s`. Refusals the episode's state decides (409; an `at`
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
[`embodied_first_exam/standard/v2_4/`](../../embodied_first_exam/standard/v2_4/), with `rcb_limited.py` and `rcb_client.py`. `rcb1.py`,
`run.sh`, the client image and the client pins are the 2.2 ones in `embodied_first_exam/standard/`. In the tables below, MUST
means "required of a service that reports 2.4" (what a 2.4 client may rely on).

### 19. Version

`eai-standard/2.4` = 2.3 + the **operations capability** below.
- Every earlier addition stays an optional capability. That covers 2.2's depth, `frame_time_s`, extrinsics,
  `POST /kinematics` and the per-call wall bound, and 2.3's realtime capability (Part 3). So a 2.2 service that adds the
  operations capability is a 2.4 service.
- Standard-mode tasks may declare `protocol = "eai-standard/2.4"`. Realtime tasks stay on 2.3.
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
| A native step cannot be pre-empted safely, so the service also owns a hard watchdog. A call that has not finished 60 s past `max_call_wall_s` ends the process; the watchdog counts from the service's own cap, never from the request deadline, so a short deadline cannot get a slow step killed. The restart then ends the episode as an infra error, `call_watchdog` (`infra_error = 1`), and does not replay into the call that hung | MUST |
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

`python3 embodied_first_exam/standard/v2_4/selftest.py` tests the watchdog's evidence, the tick ledger and the 400 for malformed
bodies on the CPU (numpy only, about 15 s).

### 25. Compatibility

- 2.x clients connect to a 2.4 service unchanged. They send no operation ids and get 2.2 behaviour.
- The 2.4 client sends ids only when `/spec.protocol` is 2.4, so it also works against 2.1–2.3 services.
- A benchmark adopts 2.4 by copying `embodied_first_exam/standard/v2_4/` unchanged; `ci_checks/check-tooling-identity.sh`
  checks the copies.

## Part 5 — The match extension: `eai-standard/2.x+match/1.0`

Embodied Olympics - Match ([its README](../../tasks/embodied-olympics-match/README.md)) runs matches between seats,
refereed by the match's own service (its `core/`, unchanged). The match extension puts the standard endpoints in front of
that service and adds the match's own calls, so an agent uses the same endpoint names as in every other standard task.
It is an extension of a 2.x version, not a new version: a client that knows 2.1 (or 2.3) plays a match with it, and
calls `/start` and `/ready` besides.

### 26. Version and implementation

- `/spec.protocol` is `eai-standard/2.3+match/1.0` for a real-time match (Part 3's clock, §29) and
  `eai-standard/2.1+match/1.0` for a standard twin in lockstep and for a turn-based match. `/spec.extensions` is
  `{"match": "1.0"}`; `/spec.match_protocol` names the match service's own protocol (`eai-standard-realtime/1.0`,
  `eai-standard-lockstep/1.0`, `eai-standard-turn/1.0`). The shipped clients accept these ids (any `eai-standard/2.`).
- The implementation is `embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/`, copied unchanged into each
  task's `environment/sim/eai_std/` by `apply_eai_std.py` next to it (which also sets the task's protocol, client and
  text). The sim sidecar runs `python3 -m eai_std.serve` (`EAI_STD_CLOCK` = `realtime`, `lockstep` or `turn`): the core's
  own entry point (`core/serve.py`, or `core/lockstep.py` for a standard twin) builds and runs the match as before, and
  the extension only wraps its HTTP server. One port serves both APIs: the standard endpoints below and the core's seat
  API `/<SEAT>/<call>` (the `game` command), which keeps working unchanged; both reach the same match, and the per-seat
  request budget (20 per second, 4 open) counts them together.
- `core/` and `sport/` are untouched, so the match's `source_sha` is unchanged.

### 27. Endpoints

| Endpoint | Request | Answer |
|---|---|---|
| `GET /spec` | — | JSON: 2.1's spec (`protocol`, `control_hz`, `control_dt`, `cameras` with `intrinsic_cv` and `pose_at_spec`, `action_types`, `timing`, `budget`, `entities`), plus `extensions`, `endpoints` and `match`: the match service's own spec (`game spec`) in full |
| `GET /status` | — | JSON `meta` (§28) |
| `POST /observe` | JSON or RCB1 header `{last_s, cameras, video, query, team_since}` | RCB1: `last/<camera>`, `frames/<camera>`, `frame_step/<camera>`, `view` (the match's own tiled PNG); `meta.observation` (the match's observation fields) |
| `POST /submit` | RCB1 header `{type, dt, at, entity, cameras, note}` + part `actions` (float32 `(T, dim)` in `action_types.<type>.layout`, or json: a list of action objects), or JSON `{type, dt, at, entity, rows: [...]}`; a hold chunk `{type, interpolate: "hold", seconds}` without rows (3.0) | RCB1, `meta` + `chunk_id`, `ok`, `effects` and the clock's fields (§29) |
| `POST /start` | `{}` | JSON `{accepted, ok, meta}`: you are ready; the match begins when every seat has started |
| `POST /ready` | `{why, plan}` (strings, at most 2000 characters each; both required for a review) | JSON `{accepted, ok, meta}` once the world goes on (every due seat has reviewed) |
| `POST /say` | `{text}` | JSON `{…, ok, meta}`: a message to your team (team formats only; else 404) |
| `POST /team`, `GET /team?since=N` | `{since}` | JSON `{messages, …, ok, meta}`: your team's messages (team formats only; else 404) |

An RCB1 request to `/start`, `/ready`, `/say` or `/team` is answered in RCB1 (header: `meta` with the match's reply under
`reply`). A row of `/submit` is an action object of the match (the body `game act` sends); a numeric row in the type's
layout is turned into one (an enum by the index of its value, a boolean as 0 / 1, all columns of a field with a default
NaN = that default). One chunk is one type and, where actions name a robot or rod (`entity`), one entity: `entity` in
the header, in the rows, or as `type` = `<type>@<entity>` (the shipped clients have no entity argument). The match checks
each row when it is sent, as the seat API does.

**Not offered (404):** `/finish`, `/reset`, `/kinematics`. A match ends by its own rules (the final score, a forfeit, a
review or start timeout, the session's end), never by the agent, so these tasks are exempt from agent-ended episodes
(Part 1, "Agent-ended episodes"); there is one match per task and no reset. Besides 2.1's codes, a match answers 403
(`seat not authorized`: a request from a host its seat is not bound to) and 429 (too many requests of one seat in
flight; empty body: retry more slowly), and refuses a request body over 8 MiB (413; `/spec.max_request_bytes`), all
declared deviations (`/spec.timing.deviations`).

### 28. `meta`

Every answer carries 2.1's `meta` (`protocol`, `step`, `control_steps`, `sim_time_s`, `calls`, `time_s`, `time_left_s`
from the first request and `RCB_WALL_CLOCK_S`, `done`, `reason`, `proprio`) and the match:
- `score`: the match's score (`{side: points}`), `side`: your side;
- `review_due`: true while the world is frozen and your review is due (send `/ready`);
- `match_over`: true once the match is decided (= `done`);
- `phase` (the match's: `prepare`, `running` (turn-based: `play`), `review`, `over`), `world`, and `state`: your seat's state as the match gives it
  (`game status`); `proprio` is its numeric leaves, each answer with its own `layout`;
- realtime: `running`, `planned_steps`, `lag_s` (Part 3) and `effects` (§29).

### 29. Clocks

- **Realtime (2.3).** As Part 3: `/submit` answers at once; its rows become the plan of their entity from control step
  `at` (absent: the current step; at most `max_ahead_steps` ahead), row i at `at` + i × `dt` / `control_dt`, replacing
  what was planned from `at` on and keeping what is planned before it; rows whose step has run are dropped (`late_rows`,
  `late_steps`); `meta` adds `start_step`, `replaced_rows`, `plan_end_step`. Each planned row is handed to the match at its
  step and takes effect as the seat API's act does (`took_effect`); the answers report each row's `planned_step`,
  `effect_step` and `late_steps` in `meta.effects` (once, in the next answer). Rows are commands, never interpolated, and
  the last one stays in force (zero-order hold, as the sport defines a command's duration). `/observe` answers at once
  (3.0: `seconds > 0` is a 400); a hold chunk clears the entity's plan from `at` for n seconds, the command in force
  staying.
- **Lockstep (2.1, a standard twin).** `/submit` runs its rows one after the other: each takes effect at the step the
  world is at, then the world advances `dt` (default: one control step); it answers after the last row. A hold chunk
  (3.0) lets n seconds of game time pass with the commands in force (`game wait`); `/observe` only reads (`seconds > 0`:
  a 400). Between calls the world stands still.
- **Turn-based (2.1).** `/submit` takes one row: the action of your turn (its review follows with `/ready`). A hold
  chunk (3.0) waits up to n real seconds for your turn (`game wait`; n at most `max_chunk_s`, which here counts real
  seconds; a declared deviation);
  `/observe` only reads (`seconds > 0`: a 400).
- **Freezes.** After every unit (a point, a phrase, a stoppage) the world freezes for the reviews until every due seat
  has sent `/ready`, at most `timing.review_timeout_s` of real time, else that side loses (`ready_timeout`); the match
  begins only after `/start`, within `timing.start.window_s` (else `no_show`). A realtime plan is cleared at a freeze. A
  `/submit` while the world is frozen or not started answers `ok: false` with `not_now` and executes nothing; a
  `/submit` after the match is over is a 409 (`done`, `reason`, `match_over`), while `/observe` still answers 200 with
  the final state and no images, and `/spec`, `/status` answer as before.

### 30. Deviations from Part 3

What the realtime clock cannot take from Part 3, `/spec.timing.deviations` lists, each with its rule, what the match does
and why:
- the clock starts at the start barrier (every seat's `/start`), not at the first `/submit`: a match is a contest of
  several seats;
- it freezes after every unit for the reviews (Embodied Olympics' rules), and the plan is cleared there;
- a row takes effect at the first control-step boundary after the match has prepared it (a high-level action is planned
  by the platform): normally its step, later when the preparation takes longer than one control period (reported per
  row); one row per entity is in flight, the next waits for the previous one's effect;
- behind its clock the match runs the missed steps back to back and records how late (`final.json` `sim_lag`); it drops
  no debt (no stalls);
- the match keeps no recorder: `/observe` with `last_s = n` answers with the sport's own frames of now (`meta.last_s`
  says what they span), no video; `/submit` returns images only when it names `cameras` (a render costs the clock);
- no depth (`depth.modes` = `["none"]`), no `linear` / `hold` interpolation.

The lockstep and turn-based clocks list theirs the same way.

### 31. Grading and evidence

Unchanged: the match's referee judges the live match (`final.json`, `tests/grade.py`), and the seat API's record
(`episode.jsonl`) holds every action whichever endpoint sent it. The extension adds `eai_std_calls.jsonl` (one line per
standard call; realtime: each planned row's dispatch and effect, with wall times). None of it decides a verdict.

## MCP tools (every version)
Every standard and realtime task offers its robot service two ways, in the same task: the service's client (HTTP, as
in the parts above) and the MCP server `efe-robot`. The agent chooses; both reach the same service, so they drive the
same robot in the same episode and can be mixed call by call. The tools add nothing to the protocol: each sends its
endpoint's request and returns the reply.

**Rule: every agent-facing endpoint has a tool.** A tool takes its endpoint's request fields (any other field of the
service in `fields`, sent unchanged) and returns the reply's `meta` unchanged, with each RCB1 part written as a file
under `/app/obs/` (arrays `.npy`, exact; uint8 images also `.png`; video `.mp4`). A convenience tool may exist on top of
these, but no endpoint is without its tool unless the table says why.

| Endpoint | Tool | Where |
|---|---|---|
| `GET /spec` | `spec` | every task (the spec also saved as a file, `spec_file`) |
| `POST /observe` | `observe` | every task: what is already recorded, at once (`last_s`) |
| `POST /submit` | `submit` | every task; rows inline or as a file (`actions_file`), or a hold chunk (`interpolate` "hold" + `seconds`, no rows); realtime adds `at`; the result's `step` repeats the reply's duration, end step, `steps_left` / `step_limit` and `done` |
| `POST /reset` | `reset` | a task with a reset budget ("Optional reset capability") |
| `POST /kinematics` | `kinematics` | a 2.2 / 2.4 task whose service serves it (§8) |
| `POST /finish` | `finish` | every task; it sends the request only when `/spec.success_signal` starts with `"hidden"` ("Agent-ended episodes"), else it says so and sends nothing |
| `GET /status` | none | its fields come back in every result's `meta` |
| `GET /operations/<id>` | none | the tool server re-queries it itself when a 2.4 reply is lost (Part 4) |

A match (Embodied Olympics - Match, `eai-standard/2.x+match/1.0`, Part 5) has the same `spec`, `observe` and `submit`
(its rows are the match's JSON action objects; a hold chunk too) and the extension's calls as extra tools: `start`,
`ready` (and `say`, `team` in a team format). It has no `finish` (its `/finish` is a 404: the match's rules end it), no
`reset` and no `kinematics`; its declared deviations (`/spec.timing.deviations`: the clock from `/start`, `last_s` the
frames of now) are the service's. `GET /status` likewise has no tool.
`ci_checks/check-mcp-tools.py` holds the routes the layers and adapters serve to this table, and every task to its
tool list. Three kinds of task keep only their own interface, and their docs say so: RoboEngineer (`eai-policy`: the
agent hands in a policy, no live robot), the matchlow matches (the player delivers skill code the platform runs) and a
match exported without the extension (`eai-standard-lockstep/1.0`, `eai-standard-realtime/1.0`: no
`environment/sim/eai_std/`, the G1 table-tennis tasks; its service serves only the seat API `/<SEAT>/<call>` of the
`game` command).

**Time.** Standard mode: time passes only through `submit`; `observe` reads what is recorded and moves nothing.
Realtime mode: no tool holds or slows the clock; `submit` answers at once as the endpoint does, and a call costs its
own time. Each result carries `tool_s`, the tool's own wall time: on the toy 2.3 service an `observe` with `cameras = []` took 1.5-3 ms over HTTP and 1-3.5 ms more through the tool (`embodied_first_exam/standard/mcp/tests/test_realtime.py`), plus whatever the agent's harness takes per tool call, which is outside the task's control. Every call answers within 45 s of its arrival (`--max-block-s`, one deadline that includes any wait for an
earlier call; Codex's MCP calls time out at 60 s): one still running then returns `{"pending": true, "operation": id}`
and `observe(operation=id)` collects the reply; a call that arrives while an earlier one is still running at that
deadline is not sent (an error result, `{"sent": false, "operation": <the running one>}`). Nothing is retried: a call is
sent once.

**Shipping.** `scripts/task_conventions.py` `normalize` writes, from `embodied_first_exam/standard/mcp/inject.py`, into
every standard and realtime task: `environment/efe_mcp/` (the server, copied unchanged, and the task's `manifest.json`:
its tools), `COPY efe_mcp /opt/tools/efe_mcp` in the agent's Dockerfile, one `[[environment.mcp_servers]]` entry
(`efe-robot`, stdio, `python3 /opt/tools/efe_mcp/server.py`) in task.toml, through which Harbor registers the server
with the agent's harness (Claude Code, Codex, Gemini CLI and the others that take MCP servers), and `### MCP tools`
after `### Client` in the instruction's Robot Interface. The server needs Python 3 with numpy and requests (pillow for
the `.png` copies): the standard client's pins (`client-requirements.txt`). It answers `tools/list` from the manifest
without contacting the service; a tool the running service shows later (`kinematics`, `reset`) is added with
`notifications/tools/list_changed`. It logs one line per call to `/logs/agent/efe-mcp.jsonl`. Tests:
`embodied_first_exam/standard/mcp/tests/` (toy 2.2, 2.3 and 2.4 services and a match seat; an oracle run once over HTTP
and once through the tools leaves the same episode).
