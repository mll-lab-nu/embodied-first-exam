# Standard-mode wire protocol `eai-standard/2.x` (robot as a service)

**Version: `eai-standard/2.4`** (2026-10-08) is the current version. This one document specifies every 2.x version a
task declares today. Minor versions only add, so each part holds for the versions after it unless a later part says
otherwise, and the shipped clients accept every 2.x service. Which parts are required is listed in
[PROTOCOL.md](PROTOCOL.md) §4 (standard mode) and §4b (standard-realtime mode).

| Version | Content | Part | Declared by (`metadata.protocol`, `/spec.protocol`) | Implementation |
|---|---|---|---|---|
| `eai-standard/2.1` | the base: `/submit` and `/observe`, RCB1 responses, measured proprioception, optional depth noise, crash recovery; the optional reset capability | Part 1 | the standard tasks of RoboTwin, DexToolBench, MuJoCo Playground (manipulation), KinDER, HumanoidBench, MetaWorld+, VLABench, RoboCasa, RoboCasa365, RoboCasa-GR1, LIBERO-MAX, BiGym 2.0 and RoboFunOlympics | each benchmark's own service (Part 1 names them) |
| `eai-standard/2.2` | 2.1 + MAY capabilities: depth `last` / `frames`, per-frame steps, times and extrinsics, camera intrinsics and mounting, `robot_spec`, `world`, `POST /kinematics`, a per-call wall-clock bound; one shared service layer with crash recovery | Part 2 (§1–§18) | the standard tasks of BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, YAMLab, LabUtopia, AutoBio and MuJoCo Playground (quadrupeds) | [`scripts/eai_standard/`](../scripts/eai_standard/) |
| `eai-standard/2.3` | 2.2 + the realtime capability: a clock that does not stop | Part 3 | every standard-realtime task (HumanoidBench, BiGym 2.0, RoboOlympics) | `scripts/humanoidbench/shared/realtime/rcb_realtime.py` |
| `eai-standard/2.4` | 2.3 + the operations capability: operation ids, request deadlines, `GET /operations/<id>`, a call watchdog, a physics-tick ledger | Part 4 (§19–§25) | the standard tasks of RoboARC | [`scripts/eai_standard/v2_4/`](../scripts/eai_standard/v2_4/) |

**Names and earlier versions.** `eai-standard/2.x` was called `rcb-limited/2.x` (limited mode) until PROTOCOL v1.0; the
content is unchanged, services and tasks report the `eai-standard` spelling, and the shipped clients also accept the
former one. No task declares a version before 2.1: 1.0 (`/step` with one action and base64 images) is retired, 2.0 =
`/submit` + `/observe` + RCB1, and 2.1 = 2.0 + measured proprioception (82 columns) + optional depth noise + crash
recovery (added 2026-09-29 without a version bump).

**Citing this document.** Numbered sections are unique in the document: §1–§18 are Part 2 (so "§13" is 2.2's crash
recovery), §19–§25 are Part 4. The sections of Parts 1 and 3 are cited by their titles.

## Part 1 — `eai-standard/2.1`: the base

The agent talks to a **sim service** it cannot open, over HTTP. **No reset**: one trial = one episode. **No step limit** (except a technical episode cap where a
task states one, e.g. DexToolBench's 360,000 control steps); the agent's wall-clock budget is the real limit; actions and simulated time are reported as cost. Nothing the agent can
call reveals object poses, scene files, seeds or the success predicate (contact or safety telemetry only where a
benchmark declares it, PROTOCOL §4.5: RoboARC's `meta["safety"]`). Videos, frames, depth and proprioception come
back as **binary** in the response body (RCB1 frames, below), never base64; the agent's code decides what to keep.

Base URL: `http://sim:8000` (compose network) or `http://localhost:8000` (Harbor egress control puts the service in the
agent's network namespace); the client tries both. The socket opens only when the scene is ready (~1 min); until then
connections are refused and the client retries.

### Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: action types (dims, layouts, limits, semantics), cameras, proprio layout, budgets |
| GET | `/status` | — | JSON: `{step, calls, physics_steps, done, reason, elapsed_s}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, include_depth, video}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, include_depth, note}` + part `actions` float32 (T, dim) | RCB1 |
Anything else (`/state`, `/success`, …) returns **404**; so does `/reset` unless the run enables the optional reset
capability (below).

### RCB1 frame
```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```
Response parts: `video/<cam>` (mp4), `frames/<cam>` (uint8 [N,H,W,3]), `last/<cam>` (uint8 [H,W,3], always), `depth/<cam>`
(float16 [N,H,W], if requested), `cam2world_gl/<cam>` (float64 [N,4,4], for a camera that moves: its pose at each returned frame), `proprio` (float32 [N, len(proprio layout)], one row per video frame: 82 columns on RoboTwin, 3 x actuators on MuJoCo). Requests over 64 MB → 413 (the client refuses
to send one); a
response over 256 MB drops `frames/`/`depth/` and says so in `meta.degraded`. `rcb1.py` (encode/decode, `python -m rcb1
unpack f dir`) is shipped with the client.

### `meta` (in every response)
`step` (rows executed so far), `calls`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio` = `{"layout": [82 names], "now": [82 floats]}` (groups below), `cameras`
(RoboTwin's per-camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the whole key omitted when the task sets
`RCB_OBS_CALIBRATION=0`), `done`, `reason`. `cameras` is computed for every response and is the calibration of the state
the response ends in (the `last` frame, the final sample of `frames` / `depth`): static cameras never move, the wrist
cameras move with the arms, and for each requested wrist camera the response carries the part `cam2world_gl/<cam>`
(float64 [N,4,4], one pose per returned frame; `spec.camera_calibration`). Until 2026-10-10 the service sent the
calibration of its start, which was wrong for the wrist cameras once an arm had moved. `time_s` / `time_left_s` are the agent's clock
(below; RoboTwin's `/spec` states it in `budget.wall_clock_note`, the other services in `budget.clock`). `/submit` adds `chunk_id, type, executed_rows, physics_steps_chunk, clipped
[{row,index,reason}], n_clipped, plan [{row,left,right}] (ee_pose), ok`; `/observe` adds `obs_id, seconds, physics_steps_watch`.

### `/submit` semantics
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

### `/observe` semantics
`seconds = 0` (default) returns the current frames, free (no physics). `seconds > 0` (≤ `max_watch_s`, 30) holds the last
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
when the agent phase ends (`timeout`) or on an error. The predicate is evaluated once more at episode end. No reset.

**The agent's clock (every 2.x service, since 2026-10-13).** `meta.time_s` is the wall time since the agent's **first
request** to the service, whatever the endpoint (`GET /spec`, which the shipped clients send first, counts), and
`meta.time_left_s` = `spec.budget.wall_clock_s` − `time_s`, never below 0. The clock does not start with the service,
when the scene is ready, or with a probe that only connects to the port; the first request is logged in
`episode.jsonl` (`first_request`) and a resumed service reads it back, so a restart never sets the clock back to
full. `GET /status` `elapsed_s` and the `elapsed_s` of `final.json` are the episode's own time, from the service's
start of the episode. Why: Harbor counts the agent's cutoff around the agent's run only (PROTOCOL §2.12), and the
sidecar starts with the environment, before the harness is installed; a clock started with the service, or at the
end of a scene build that finished before the agent began, ran ahead of the agent's (a median of 79 s over 2,322
recorded trials, board 0085) and `time_left_s` reached 0 that much too early. With this rule the service's clock is
never ahead of the harness's: `time_left_s` never runs out before the agent is stopped, and the agent's real time left
is `time_left_s` minus what it spent before its first request (seconds, where the service is up before the agent; the
part of a slow start-up that falls inside the agent's phase otherwise). No service ends an episode on this clock, with
one exception: RoboARC's (Part 4) still ends the episode at 0 until its next task update
(`docs/benchmarks/roboarc.md`); since its MuJoCo release (2026-10-13) it counts from the first request like the others. A readiness probe added to a compose file or a runner must not send a
request to the service before the agent runs: connecting to the port is enough.

**Service crashes (no reset, no lost episode).** Every executed physics step is journaled (`trajectory_live.f64`) and every
completed call logs a checkpoint (step count + state hash) in `episode.jsonl`. If the service dies mid-episode, compose
restarts it (`restart: on-failure:6`) and it **resumes the same episode**: it replays the journal up to the last checkpoint,
checks the state hash, and continues. The call that was in flight is lost as a whole (its caller got a connection error or
5xx, not a result, so nothing is learned); `spec.on_service_error` tells the agent to check `GET /status` before continuing.
More than 2 crashes end the episode: `reason = sim_crashed_on_call` if every crash happened while serving a call (counted as
the agent's failure), else `sim_crashed` (`infra_error = 1`). A verdict already written is never overwritten: the replay's
verdict (`replay_success`, `deterministic`) is in `final.json` before any video is rendered, and it stands from then on,
also when the service is restarted while rendering. A crash before
the service is ready is a plain restart; a scene build that hangs is killed by a startup watchdog (`RCB_STARTUP_TIMEOUT_S`,
300 s) so compose retries it. A host on which the frozen instance does not rebuild to its stored initial state (PROTOCOL §3)
gets one retry and then `reason = instance_mismatch` with `infra_error = 1`.

### Evidence and grading (agent never sees this)
`/data/episode.jsonl` (one record per call: type, rows, dt, cameras, note, clipped, plan, physics steps, success),
`/data/calls/NNNNNN/` (meta + last frames per call), and on end: `trajectory.npz` (T, 34), a fresh replay
(`replay_success`, `deterministic`), `replay.mp4` (six-view), `final.json`. The collect hook signals the service by PID
after the agent container is stopped; a separate verifier grades `final.json`: `success = live ∧ replay ∧ deterministic`,
reward fields as in PROTOCOL §2.6 and §4.8. `infra_error = 1` means there is no verdict on the agent: `final.json` is
missing or unreadable, the replay's verdict is not in it (the service was still replaying when the collect hook gave up,
or the replay itself failed: `finalize_error`), or the service reported `sim_crashed`, `resume_failed` or
`instance_mismatch`. A verdict that is on disk is graded whether or not `finalized` (the videos) was reached.
`sim_crashed_on_call` stays the agent's failure (`infra_error = 0`).

### Live recording (sidecar only; the agent sees none of it)
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

### Proprioception (2.1)
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

### MuJoCo tasks (DexToolBench, MuJoCo Playground)
Same endpoints and RCB1 frames, served by `images/mujoco/limited/server_mj.py`. Differences: one action type,
`joint_position` with the task's own actuator layout (DexToolBench 29, ALOHA 14, Panda 8), rows `dt` apart where `dt`
is a multiple of `control_dt` (1/60 s DexToolBench, 1/50 s Playground), hold or linear interpolation per control step.
Actions are sent as **float64** (MuJoCo on CPU replays bit-exactly, and float32 rounding changes a chaotic tool swing).
`meta.task` carries the task definition (DexToolBench: current goal pose and index; Playground: the target) and
`meta.cameras` each camera's intrinsics (`intrinsic_cv` = `[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]` for the returned image; fx = fy for a camera defined by its field of view, fx ≠ fy for one defined by its sensor size, which MuJoCo renders with the sensor's extent in each direction: ALOHA's overhead and wrist cameras, 158.52 and 216.45 px; until 2026-10-13 the service reported fx = fy = 216.45 for them) and camera-to-world pose: the viewpoint the image is rendered from, in the state
the response ends in (`spec.camera_calibration`; until 2026-10-10 the position was MuJoCo's left-eye camera, 3.4 cm to
the side, and the pose was the one at service start). Cameras carry `moving` (true for ALOHA's wrist cameras); for a
requested moving camera the response also has the part `cam2world_gl/<cam>` (float64 [N,4,4], one pose per returned
frame). `time_s` / `time_left_s` are the agent's clock (above; `spec.budget.clock`). `final.json` is `finalized`
as soon as the replay's verdict is in it; the video is rendered afterwards and sets `video_done`, which is what the
collect hook waits for, so the video never decides or delays a verdict (the MetaWorld+ service,
`images/metaworld/standard/server_mw.py`, follows the same rules; docs/benchmarks/metaworldplus.md). DexToolBench's own eval gives each goal 10 s; here the
standard twins have **no per-goal limit** and **20 resets** (owner, 2026-10-13: the optional reset capability below;
until then one episode, no reset) and an episode cap of 360,000 control steps (100 min of
robot time, `spec.max_control_steps`; the 60 min agent budget ends first), while the privileged tasks give each goal 30 s
(replayed offline, free resets). DexToolBench episodes end when all goals are reached, at the cap, or when the agent's
time is up; Playground episodes run to the end of the agent phase and the final state is graded. The MuJoCo service
journals and resumes exactly as above (journal `record.f64`).
The service replays the recorded episode in a fresh simulator at the end (`deterministic`: same final state hash).

### KinDER and HumanoidBench tasks
Same endpoints, RCB1 frames and crash recovery, served by one shared service (`scripts/{kinder,humanoidbench}/shared/standard/rcb_service.py`,
identical in both) with a per-benchmark simulator adapter (`server.py`). Actions are delta or joint-position rows at the
task's control rate (KinDER 10 Hz, PyBullet tasks kinematic: a refused move comes back `blocked` and stops the chunk;
HumanoidBench 50 Hz); the step counters are `rows` and `control_steps`. No world coordinates are given (odometry and
camera poses are in the robot's starting frame); see [docs/benchmarks/](benchmarks/) for the per-benchmark observation
tables. A request body over 64 MB gets 413 before it is decoded.

### Optional reset capability
Off by default (`budget.reset = 0`): one trial is one episode, in standard and standard-realtime mode alike. Exception, by
owner decision (PROTOCOL §4.5): HumanoidBench's standard tasks (2026-10-07) and standard-realtime tasks (2026-10-08) default
to `budget.reset = 50`, MyoSuite's standard tasks (2026-10-09) to `budget.reset = 10`; BiGym2's and KinDER's standard
tasks (2026-10-11) to `budget.reset = 10`; DexToolBench's standard tasks (2026-10-13) to `budget.reset = 20`. A run may set `RCB_RESET_BUDGET=N`
on the service (implemented by the KinDER, HumanoidBench, BiGym2, MyoSuite and MuJoCo (`server_mj.py`: DexToolBench, Playground ALOHA / Panda) services; MyoSuite's 2.2 client has no `reset()`,
so its instruction calls `POST /reset` through `Robot._post`). Then `/spec.budget.reset = N`, `/spec.reset` describes it, and
`POST /reset` (RCB1 or JSON `{cameras, video}`, no physics) abandons the running episode and starts a new one from the
same frozen state, `N` times in all; `/status` and `meta` add `episode`, `resets_left` and `control_steps_total`. After a
success or once the agent's time is up, `/reset` returns 409, as it does when the budget is spent. Only the last
episode is graded. Results with `N > 0` are reported separately and never ranked with `N = 0` (PROTOCOL D1, §4.5).

## Part 2 — `eai-standard/2.2`: capabilities added to 2.1

> Formerly `rcb-limited/2.2`. Status: accepted (PROTOCOL §6), with its crash recovery (§13).
> 2.2 is a minor version of `eai-standard/2.1` (Part 1): everything there holds unless this part
> says otherwise, every 2.2 addition is a MAY capability, and a request written for 2.0 or 2.1 gets the same answer as
> before (plus parts and keys an old client ignores). Which parts are required is listed in PROTOCOL §4.

**Who serves it.** The standard twins of thirteen benchmarks: BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces,
MyoSuite, DexJoCo, YAMLab, RoboDojo, LabUtopia, AutoBio and Panda Dynamic Scenes ([docs/benchmarks/](benchmarks/); MyoSuite and AutoBio: MuJoCo on the CPU, resume class `exact`; YAMLab: Isaac
Lab with CPU PhysX, resume class `exact`; RoboDojo: Isaac Lab with GPU PhysX, resume class `exact`, `approx` for its six
standard-only tasks graded by the live episode; LabUtopia: Isaac Sim, PhysX on the CPU, resume class `exact`; Panda Dynamic Scenes:
ManiSkill / SAPIEN with CPU PhysX, resume class `exact`), and MuJoCo Playground's quadruped tasks. The RoboTwin and the other MuJoCo standard tasks (DexToolBench, MuJoCo Playground's manipulation tasks) serve 2.1.

**One implementation.** The source is [`scripts/eai_standard/`](../scripts/eai_standard/), the D9 shared source of these six
benchmarks: the service layer `rcb_limited.py` (HTTP, RCB1 responses, the protocol helpers, the `/spec` self-check, crash
recovery), the client `rcb_client.py` + `rcb1.py`, the sidecar entrypoint `run.sh`, and the client image: `client.env`
(the one client base, pinned by digest) and `client-requirements.txt` (exact pins). The generators copy the code unchanged
into every 2.2 task (`environment/rcb_client.py`, `environment/rcb1.py`, `environment/sim/{rcb_limited.py,rcb1.py,run.sh}`);
`ci_checks/check-tooling-identity.sh` checks the copies, `ci_checks/check-standard-client.sh` the images. Each benchmark writes only its adapter,
`environment/sim/server.py`: the robot, the cameras, the clock (`toy_server.py` is the smallest complete one).

**Design principles.**
1. *A robot, not a simulator.* No reset, no state query, no success query, no step limit; the wall clock is the budget;
   actions and simulated time are reported as cost; the first success ends the episode.
2. *One information line.* The agent may know the robot and its sensors (spec sheet, kinematics, camera calibration,
   proprioception), never the world's ground truth (§10).
3. *Everything new is optional.* Depth, for example, costs a render and is off by default.
4. *Binary data, kept by the agent's code.* RCB1 frames, never base64; nothing is pushed into the model's context.
5. *Evidence the agent cannot touch.* The service records every call; grading replays the record in fresh processes,
   in a container the agent never saw.

### 1. Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: 2.1's keys + cameras' intrinsics and mounting, proprio groups, `robot_spec`, `world`, `kinematics`, `depth`, `on_service_error`, `max_call_wall_s` |
| GET | `/status` | — | JSON: `{step, calls, control_steps, done, reason, elapsed_s, resumes}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, video, depth}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, depth, note}` + part `actions` float32 (T, dim) | RCB1 |
| POST | `/kinematics` (2.2) | JSON `{op: "fk" \| "ik", ...}` (§8) | JSON |

Anything else (including `/reset`, `/state`, `/success`) returns **404**. `include_depth` (2.0/2.1) is still accepted (§7).

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
(scene facts: names, sizes, colours; never a position), `budget` (`{"reset": 0, "steps": null, "wall_clock_s",
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
planner (per benchmark, §16); a failed row is reported in `plan`. Not yet: `joint_delta`, `joint_velocity`, `ee_delta`,
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

### 10. Never provided (the declaration of these six benchmarks, PROTOCOL D7)
Through any endpoint, part or `/spec` field, and in the task's texts (instruction, README, task.toml description): where
things are in the world (object poses and positions, world coordinates of workspace items: table or sheet heights, sheet,
well or bin centres, a pixel-to-world formula, a camera's distance to the scene); segmentation of any kind; physical
parameters of the scene (mass, friction, damping, inertia, restitution; the robot's own drive gains are the exception);
the success predicate. Provided: a detailed goal, object names and inventories, categories, sizes and colours where the
task needs them, qualitative relations, the robot and its tool, camera calibration, world conventions (BEHAVIOR's floor at
z = 0 defines its frame), the budget. `rcb_limited.check_spec` refuses to start a service whose `/spec` names a forbidden
field or puts a position into `static`; `ci_checks/check-standard-texts.sh` checks the texts of these six benchmarks and of LabUtopia and AutoBio (other
benchmarks decide for themselves, D7); `ci_checks/check-standard-protocol.py` checks every response of a live service.
Accepted consequence: a calibrated camera aimed at the workspace tells roughly where the workspace is.

### 11. Errors (no physics executed)
As 2.1: 400 malformed request (including a bad kinematics request), 409 episode over (`/observe` and `/kinematics` still
answer), 413 body over 64 MB, 500 simulator error: **on `/submit` and `/observe` the episode ends** with `reason = "error"`
(PROTOCOL §4.6). A negative `Content-Length` is a 400, answered without reading the body. The service listens on port
8000 of a network namespace that, under Harbor's egress control, the agent's container shares: if a process of the agent
holds the port when the scene is built, the service waits for it (the agent's own time) instead of exiting, which would
count as one of its crashes.

### 12. Per-call bounds (2.2)
No step cap, and the wall clock stays the episode's only budget (PROTOCOL §4.4, §4.5). Two bounds keep one call from
holding the single-threaded service:
- **`max_call_wall_s`** (`/spec`, default 900 s, below the client's 1800 s read timeout; task env `RCB_MAX_CALL_WALL_S`): a
  `/submit` or `/observe` that runs longer stops at the next control step and returns normally, with `meta.stopped =
  "max_call_wall_s"` and `executed_rows` below the rows sent.
- **Client hang-up**: when the client closes the connection (its read timeout, a killed process), the call stops at the
  next control step (`stopped: "client_disconnected"` in `episode.jsonl`); the response is not delivered.
In both cases the executed prefix stays: it is journaled and checkpointed like any call, and `/status` and the next
`meta.proprio.now` report the state after it, like a real controller that loses its link. An old client sees a normal
response with fewer rows executed; `rcb_client` exposes `Result.stopped` and prints a one-line warning.

A third bound keeps one call from exhausting the service's memory (every frame is held until the response is sent):
- **`max_frames_per_call`** (`/spec`, where the adapter states one: DexJoCo and MyoSuite 1000, RoboARC 2000, RoboWits
  1500, RoboPaint 640, RoboDojo 3000; LabUtopia and AutoBio state a bound per camera): the images a call may return, cameras x frames
  with per-frame depth counted again (as four images in RoboARC, RoboWits and RoboPaint, what a depth frame costs).
  A request over it is a 400 before anything is executed (`rcb_limited.check_frames`); a camera named twice is one
  camera. Where the length of a call is known only while it runs (RoboARC's and RoboWits' `ee_pose` rows), the
  call stops taking frames at the bound, runs to its end, always returns the last frame, and `meta.frames_skipped`
  counts the frames left out. RoboLab, YAMLab, ManiGuard, MolmoSpaces, BEHAVIOR and MuJoCo Playground's quadruped
  services state no such bound yet (their calls are bounded by `max_watch_s`, `max_chunk_s` and the frame rate).

### 13. Crash recovery
The 2.2 implementation of PROTOCOL §4.7, with the semantics of the RoboTwin and MuJoCo services
(`rcb_limited.Episode`; adapters call it as `toy_server.py` does):
- **Journal and checkpoints.** Every executed control step (the exact row given to the simulator's step) is appended to
  `journal.f64` (float64 rows). After every completed call the journal is flushed and a checkpoint is logged in
  `episode.jsonl`: call count, rows, control steps, the state hash, the robot's proprio row, and the adapter's `persist`
  keys (state that shapes later actions, e.g. RoboPaint's last tip target). `call_begin` / `call_end` bracket every call.
- **Restart.** `run.sh` is the sidecar's PID 1 and exits non-zero when the service crashes; compose restarts the container
  (`restart: on-failure:6`, same container and record). The new process finds the episode's `start` event and resumes:
  it replays the journal up to the last checkpoint (no rendering), truncates the journal there (the call in flight is lost
  as a whole: its caller got a connection error, not a result), checks the state (below), restores the counters, the
  episode end if one was logged, and the `persist` keys, and continues the SAME episode, never a reset. The agent's
  clock keeps running from its first request (the logged `first_request`), the episode's `elapsed_s` from the first start. `spec.on_service_error` tells the agent to wait for `GET /status` (client:
  `Robot.wait_ready()`) and check `calls` / `control_steps`.
- **Limits.** At most `RCB_MAX_RESUMES` (2) resumes; a third crash ends the episode: `sim_crashed_on_call` if every crash
  happened while a call was being served (the agent's failure), else `sim_crashed` (`infra_error = 1`). A journal shorter
  than the log ends it as `resume_failed` (`infra_error = 1`). A verdict already on disk is never overwritten; the service
  then keeps its PID file for the collect hook and answers every request, `GET /spec` and `/status` included, with 409
  `{"gave_up": true, "reason", "infra_error"}`: the client's `Robot()` and `wait_ready()` raise `EpisodeOver` at once
  instead of waiting out their timeout. The same holds for a service that refuses the episode at its start (DexJoCo with
  fewer than 4 CPUs, RoboWits when the frozen instance does not rebuild).
- **Start-up.** A crash before the scene exists is a plain restart. The startup watchdog (faulthandler's C thread: it fires
  even while a native scene build holds the GIL) dumps every thread's traceback to `server.log` and exits after
  `RCB_STARTUP_TIMEOUT_S` (default 900 s); a start that follows failed starts waits min(120, 20·(n − 1)) s first. The
  watchdog stands down once the scene exists, so a long resume replay is not taken for a hang.

#### 13.1 Per-simulator resume rule (PROTOCOL §4.7)
The resume check depends on the simulator's determinism class, which the adapter declares (`Episode(..., resume=...)`):

| class | rule | benchmarks |
|---|---|---|
| `exact` | the replayed state hash must equal the checkpoint's; otherwise the episode ends `resume_failed` (`infra_error = 1`) | RoboWits on Genesis' CPU backend; RoboLab (Isaac, CPU PhysX: the resumed service is a fresh process, whose first replay is bit-exact); RoboPaint (ManiSkill/SAPIEN, CPU PhysX, CPU brush model); MolmoSpaces (MuJoCo, CPU physics); YAMLab (Isaac, CPU PhysX, a fixed env seed: the resumed service is a fresh process, whose first run is bit-exact); LabUtopia (Isaac Sim, CPU PhysX, a fresh process as RoboLab; one control step is one physics step); AutoBio (MuJoCo 3.3, CPU physics; one control step is one physics step); RoboDojo (Isaac, GPU PhysX: the resumed service is a fresh process, whose first run is bit-exact, measured on 48 of its 54 tasks; `make_toast` with PhysX enhanced determinism); Panda Dynamic Scenes (ManiSkill / SAPIEN, CPU PhysX with enhanced determinism, one thread; every reset rebuilds the scene; ten physics steps per control step) |
| `approx` | the hash is compared and the result recorded; a mismatch does not end the episode: `resume_state_mismatch = 1`, and the robot's deviation from its checkpointed proprio is recorded (max \|Δ\| over `joint_pos`; the largest TCP position error from `tcp_pose`). Only a gross divergence, a TCP more than `RCB_RESUME_MAX_DEV_M` (0.05 m) from where it was, ends the episode as `resume_failed` (`infra_error = 1`) | simulators declared nondeterministic: RoboWits on the GPU backend (the particle families separate_marbles_and_sand and stabilize_bottle, `RCB_ROBOWITS_BACKEND=gpu`); BEHAVIOR-1K (OmniGibson declares rollouts nondeterministic; measured so far: live = fresh replay on every 2.2 run, so it normally resumes exactly); ManiGuard (OmniGibson 3.7.2; not measured yet); RoboDojo's six standard-only tasks graded by the live episode (`make_toast_random`, the three liquid tasks and the two cloth tasks: GPU PhysX particles and cloth do not replay bit for bit; PROTOCOL §4.8) |

This relaxes "the hash checked" of PROTOCOL §4.7 for declared-nondeterministic simulators only. It cannot raise a score:
the verdict never comes from the live state, it comes from fresh replays of the complete recorded trajectory (the
replayed prefix plus everything after the resume). A mismatch only perturbs what the agent saw, and the flags say so;
results can exclude or rerun such trials. Crashing the simulator on purpose gains nothing: there is no reset, and three
crashes inside calls count as the agent's failure.
The one exception is a task graded by the live episode (PROTOCOL §4.8: physics that does not replay bit for bit;
RoboDojo's six standard-only tasks): there the verdict is the live episode's, so after a resume it is the live state the
resumed service continued from. `reward.json` reports `resumes` and `resume_state_mismatch` for it, at most two resumes are
allowed as everywhere, and a success with `resumes > 0` is reported with those fields (results can exclude or rerun it).

#### 13.2 Evidence fields
`final.json` and `episode.json` carry `sim_startups`, `resumes`, `resume_state_mismatch` (0/1), `resume_max_tcp_dev_m`,
`resume_max_joint_dev` (`Episode.final_fields()`), and a give-up adds `gave_up`, `reason` and `infra_error`. Graders copy the
numeric ones into `reward.json` (MAY fields, PROTOCOL §2.6), with `infra_error`.

#### 13.3 What generators emit (3b–3e)
- `environment/docker-compose.yaml`, service `sim`: `command: sh /srv/run.sh` and `restart: on-failure:6` (N ≥ 3 is the
  MUST, PROTOCOL §4.1); `RCB_DATA` = the record dir (`/data`; BEHAVIOR `/out`, since `/data` is its dataset).
- `RCB_STARTUP_TIMEOUT_S` **per task, from the measured build time** of its family on the evaluation hosts (MUST; the 900 s
  default is too short for some families, below): at least twice the slowest measured build. A family whose build exceeds
  the watchdog loops through every restart to a give-up.
- Optional: `RCB_MAX_RESUMES` (2), `RCB_MAX_CALL_WALL_S` (900), `RCB_RESUME_MAX_DEV_M` (0.05).
- `artifacts`: also `journal.f64`, `startups.jsonl`, `server.log` from `service = "sim"`.
- The agent container (`environment/Dockerfile`) and the verifier (`tests/Dockerfile`) `FROM` the `CLIENT_IMAGE` of
  `scripts/eai_standard/client.env` (PROTOCOL §2.4), and any `pip install` installs `client-requirements.txt`: the full pin
  list inline (`RUN pip install --no-cache-dir certifi==… … urllib3==…`), or `-r client-requirements.txt` with a
  byte-identical copy in the build context. The agent containers of today need the whole list (numpy, pillow, scipy,
  requests and its dependencies); the verifiers install nothing. A new package or version is a change to the pins.
- The collect hook starts with `python3 /srv/rcb_limited.py end "$DATA"`: it waits through a resume (no PID file until the
  service is ready), signals only the process that wrote the newest `startups.jsonl` line, resends SIGUSR1 every 30 s, and
  exits 2 when `final.json` already holds the verdict (a give-up, or an in-process grade; `--wait-key video_done` for
  RoboWits), 0 when the service dumped the episode and exited (RoboLab, BEHAVIOR, RoboPaint, MolmoSpaces: the hook replays next).
- Adapters: `EP = L.Episode(DATA, dim, resume, persist)`; `EP.startup()` before the scene is built and `EP.scene_built()`
  after; `EP.journal(a)` in the control step (its True return stops the call: loops that test `E["done"]` test
  `EP.stopping` too); `S.record_start()` then `EP.begin(...)` instead of logging `start` and installing a SIGUSR1
  handler; `episode=EP, state_sha=..., proprio=...` in `L.Service`; `**EP.final_fields()` in `final.json` / `episode.json`.

#### 13.4 Measured scene builds (input for `RCB_STARTUP_TIMEOUT_S`)
Episode `start` minus the end of Harbor's environment setup, from our standard-mode trials on the laptop (RTX 4090
laptop GPU, 32 GB): a lower bound of the build, since the sidecar starts during environment setup. 3b–3e re-measure on
their evaluation hosts.

| benchmark | families measured (trials) | build | note |
|---|---|---|---|
| RoboWits, CPU backend | 29 (94) | 47–234 s (median ~60 s) | default 900 s is enough |
| RoboWits, particle families | separate_marbles_and_sand, stabilize_bottle | 39–56 min on the CPU backend; ~140 s on the GPU backend | they run on the GPU backend; a CPU-backend build needs `RCB_STARTUP_TIMEOUT_S` ≥ 7200 |
| RoboLab | 13 (20) | 98–217 s | default enough |
| BEHAVIOR-1K | 6 (12) | 130–404 s (scene load); cold builds on a loaded lab host 433–519 s | `RCB_STARTUP_TIMEOUT_S` = 1800: each trial starts with a cold Kit cache (its own `*_trusted` volume), about 250 s more |
| RoboPaint | brush families, 285 standard trials on ws, ws3 and lab (up to 50 at once) | episode start at most 126 s after Harbor's environment setup began (median ~30 s); the Session build alone at most 106 s | `RCB_STARTUP_TIMEOUT_S` = 600 (≥ 4× the slowest start) |
| MolmoSpaces | 8 (213), on a lab host (RTX 4090, 32 cores) | episode start 8–52 s after Harbor's environment setup began (median 11 s; navigate-to 33–52 s) | `RCB_STARTUP_TIMEOUT_S` = 300 |

#### 13.5 Cost and tests
One state hash per call (not per step). A resume replays the episode so far without rendering: RoboWits ~700 steps/s
(CPU), RoboLab ~20/s, BEHAVIOR ~14–20/s (a 50k-step, 4 h episode: 45–60 min of downtime, on the agent's wall clock).
`python3 scripts/eai_standard/selftest.py` (CPU only, ~2 min) runs `toy_server.py` under `run.sh` with a stand-in for
compose's restart policy and checks: resume between and inside calls, both classes, the third crash, the watchdog and
back-off, client hang-up, the wall bound, both collect-hook outcomes, SIGUSR1 during a resume, a simulator error, the
client's protocol names, malformed requests, a port that is taken, a negative `Content-Length` (CI job `unit-tests`). Per benchmark, the acceptance test (kill the service of one standard task, the episode goes on
and is graded correctly; check that `live_matches_replay` stays 1 where it was) belongs to its PR.

### 14. Evidence and grading (the agent never sees this)
`episode.jsonl` (calls, checkpoints, resumes), `journal.f64`, `startups.jsonl`, `calls/NNNNNN/` (meta + last frames per call),
`server.log`, and at the end `trajectory.npz`, the replays, `replay.mp4`, `final.json`. The collect hook signals the service
by PID after the agent container is stopped; RoboWits grades in-process (Genesis' CPU backend repeats exactly), RoboLab,
BEHAVIOR, RoboPaint and MolmoSpaces dump the episode, exit, and the hook replays it in two fresh processes. A separate, network-less
verifier grades `final.json`: `success = live ∧ replay ∧ deterministic` (RoboWits' GPU-backend families: determinism
reported, not required), reward fields as in PROTOCOL §2.6 and §4.8. A GPU lost to a host systemd reload is reported as
`gpu_lost` / `grader_error`. 2.1's live recording (`live.mp4`) is a RoboTwin service feature, not part of 2.2.

### 15. Privileged-mode parity
Every privileged Session of the six benchmarks offers the same information from the same code: `s.camera_info()`,
`s.render_depth(cam)`, `s.robot_spec()`, `s.kinematics(req)` (`s.kinematics_spec()` = `/spec` `kinematics`). Privileged mode
stays privileged (object state through the tooling).

### 16. Per-simulator notes (the protocol is the same; the robot and the clock differ)
| | RoboWits (Genesis 0.4.7) | RoboLab (Isaac Lab 2.3) | BEHAVIOR-1K (OmniGibson 3.9.2, R1Pro) | RoboPaint (ManiSkill 3.0.1 / SAPIEN 3.0.3) | ManiGuard (OmniGibson 3.7.2, Franka long-finger) | MolmoSpaces (molmo-spaces 0.2.9, MuJoCo 3.5.0) |
|---|---|---|---|---|---|---|
| rows streamed at | 30 Hz control (4 substeps) | 15 Hz control (8 substeps) | 30 Hz control (4 substeps) | 20 Hz control (5 substeps) | 20 Hz control (6 substeps) | Franka 15.15 Hz (33 substeps); RB-Y1 5 Hz (navigation, 100) or 10 Hz (door, 50) |
| `joint_position` | 16: per arm 7 joints + gripper width (m) | 8: 7 joints + binary gripper (switched) | 25: base (per-step targets, robot frame) + trunk + arms + grippers | 7 joints | 8: 7 joints + binary gripper (+1 / -1, switched) | Franka 8: 7 joints + Robotiq command (0–255); RB-Y1 25: base x, y, θ (world) + torso 6 + arms 14 + two gripper forces |
| `ee_pose` | 16 (right first), IK per row, gripper-tip frame | 8, closed-loop differential IK, fingertip-centre frame | 16 (left first, xyzw), cuRobo IK for both end effectors per row | 7, brush-tip targets `dt` apart, IK per control step | 8 (xyzw), numpy IK per row, fingertip-centre frame | not offered (`not_yet`) |
| cameras | `ego` (static), `wrist_right`, `wrist_left` | `egocentric_mirrored_camera`, `over_shoulder_left_camera` (static), `wrist_cam` | head + two wrist cameras (224×224, moving) | `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam` (static) | `cam_opposite`, `cam_left`, `cam_right`, `cam_left_shoulder` (static), `wrist` | Franka: wrist and shoulder (moving), three randomised static; RB-Y1: head + two wrist cameras (moving) |
| depth | Genesis rasterizer | Isaac `distance_to_image_plane` | OmniGibson `depth_linear` | SAPIEN depth buffer (geometry only: ink and paint never show) | OmniGibson `depth_linear` | MuJoCo depth buffer |
| `/kinematics` | pinocchio on the URDF (14 arm joints) | numpy model of the USD joints (7) | numpy model of the articulation (trunk + arms), cuRobo fallback | SAPIEN's pinocchio (7) | numpy model of the articulation (7 arm joints), world frame | upstream's `MlSpacesKinematics` on the robot's MuJoCo model (Franka 7, RB-Y1 23 with the base) |
| proprio columns (2.0 → 2.2) | 30 → 80 | 16 → 32 | 49 → 121 | 14 → 28 | — → 43 (no 2.0 version) | 2.2 only: 29 (Franka), 85 (RB-Y1) |
| grading replays | in-process (exact) | two fresh processes | two fresh processes | two fresh processes | two fresh processes | two fresh processes |
| resume class (§13.1) | `exact` (CPU backend), `approx` (GPU backend) | `exact` | `approx` | `exact` | `approx` (until measured) | `exact` |

### 17. Known issues
- RoboWits: during the in-process grading replay, `/status` and a late `/observe` report the replay's counter and scene;
  the episode is over by then and the grade is unaffected.
- BEHAVIOR-1K: while the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency);
  its `extrinsic_cv` is the pose it was rendered with, the proprio row the state at `frame_step`.
- Per-call state hashing on Isaac (RoboLab, BEHAVIOR) is new with crash recovery; their PRs re-check `live_matches_replay`.

### 18. Versioning
`protocol` in `/spec` = `metadata.protocol` = `eai-standard/2.2`. The 2.x client accepts every 2.x service under both
spellings (`eai-standard/2.`, `rcb-limited/2.`); 2.1 clients work against a 2.2 service (they get float16 per-frame depth
for `include_depth` and ignore the new parts and keys).

## Part 3 — Standard-realtime mode: `eai-standard/2.3`

Time does not stop. The wire protocol of the standard-realtime mode (PROTOCOL §4b, v1.1; protocol-change issue #86), served by
standard-realtime tasks only (`<base>-standard-realtime`, `mode = "standard-realtime"`, `protocol = "eai-standard/2.3"`; implemented by HumanoidBench's,
`scripts/humanoidbench/shared/realtime/rcb_realtime.py`, which RoboOlympics' tasks use unchanged). 2.3 is 2.2 plus the realtime capability below; every 2.2
addition stays a MAY, so a 2.1 service with this capability is a 2.3 service. Same endpoints, RCB1 frames, crash
recovery and grading as 2.1. `/spec.timing` declares it: `realtime: true`, `slowdown` S (`RCB_SLOWDOWN`, default 1 = real
time; results with S ≠ 1 are reported separately from S = 1), `control_dt`, `wall_s_per_control_step`, `max_ahead_steps`.
Defaults of the mode: `budget.reset = 0`, as in standard mode (the optional reset capability of Part 1; `RCB_RESET_BUDGET` overrides it;
HumanoidBench's per-benchmark exception is 50, PROTOCOL §4.5), and S = 1 (RoboOlympics' per-benchmark exception is 10,
PROTOCOL §4b).
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
- **Grading** is 2.1's: the journal holds the sim row the simulator applied at every control step, and the graded
  episode's rows are replayed in a fresh simulator, so the replay equals the live run whatever the timing. Evidence
  added: `ticks.f64` (per journal row: wall time, the call whose chunk gave the row, -1 when held), `calls.jsonl` and
  `submitted.f64` (one line per call and every row as sent, instead of `calls/NNNNNN/`), and in `final.json`
  `realtime`, `slowdown`, `held_steps`, `late_steps`, `max_queue_wait_s`, the clock's record -- `clock_s` (wall seconds
  the clock ran), `max_lag_s` (the furthest a control step ran behind its time; the true maximum), `stalls`,
  `stalled_s` (the wall time the stalls dropped: the robot stood still that long while its clock should have run),
  `stalled_share` = `stalled_s` / `clock_s` -- and what the requests cost: `requests_refused` (answered 4xx),
  `request_mb` (bodies read), `request_busy_s` (simulator-thread time spent on requests). All are checkpointed with the
  episode: after a crash-resume they still cover the whole trial. The graders repeat the clock's record,
  `requests_refused` and `request_busy_s` in `reward.json` (numbers; a missing one is 0). None of it decides a verdict.
- **Service.** The simulator's thread runs a due control step before any waiting request; behind the clock it runs the
  missed steps back to back, and more than 0.5 s behind it drops the debt (a stall, counted, its seconds added to
  `stalled_s`) instead of fast-forwarding the robot. Checkpoints every second of robot time while the clock runs; a
  crash resumes the same episode, paused.
- **What a request can cost the clock** (2026-10-10). A request's body is read, decoded and checked on its HTTP thread:
  a request that is refused for what it says (404, 413, a malformed body, a wrong type / shape / `dt` / camera, a
  chunk longer than `max_chunk_s`) never reaches the simulator's thread, and neither does `GET /spec`. JSON text is
  parsed in the service's process only up to 1 MiB; a body with more of it (the client sends the rows as an RCB1 array
  part, a few kB of JSON at most) is parsed by a child process, one at a time, and answered as any other -- the 64 MB
  limit stands, and such a body costs the clock nothing whether it is accepted or refused. A negative `Content-Length`
  is a 400, unread. Behind the clock, a waiting request is served once the clock has caught up (or, where the
  simulator cannot keep up by itself, after four times the time the last request of its kind took): requests queue
  behind each other, not into the clock, so `/observe` may take longer to answer under parallel load. A request that
  renders and alone takes more than 0.5 s (a stall by itself: CPU rendering) makes the next rendering request wait
  four times that long, clock on time or not; requests without images (`cameras: []`, `/status`) are not held back by
  it. Requests can so take at most a fifth of the clock's time. The cameras are rendered (and the proprioception
  read) at most once per control step: parallel observes and watches share that step's frames. What remains: a watch
  (`seconds > 0`) renders inside the control steps it watches, so where one render of its cameras takes longer than
  its frame interval the clock runs late and stalls while it lasts (GPU rendering takes about 0.5 ms a frame; CPU
  rendering does not keep up) -- counted in `stalls` and `stalled_s`.
  Refusals the episode's state decides (409; an `at` too far ahead; too many frames) are answered by the simulator's
  thread, as before, and a 409 still comes before a 400 for a request's fields.
- **Crashes are infrastructure.** No call spans a crash (`/submit` answers at once), so a crash is never put down to the
  agent: past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed`, a failed resume `resume_failed`, and a simulator
  error that ends the graded episode (`reason = "error"`) is one too; `final.json` carries `infra_error = 1` in all three.
- **Agent code** runs where it does in standard mode, in the agent's own container: a controller that streams targets
  through the client, not code uploaded next to the simulator.

The time model matches the one proposed for the Embodied Agent Olympiad's `eai-standard-realtime/1.0` (PR #41: the
world runs at 1/S of real speed, a command takes effect at the next control step and replaces the one under way, all
agent latency counts, the agent's own program may act) and uses its `slowdown` name. It stays inside 2.x: no `/start`,
`/act`, `/wait`, `/ready`, seats, reviews or metering proxy; native agents only (PROTOCOL D11).

## Part 4 — `eai-standard/2.4`: the operations capability

Status: accepted 2026-10-08 (owner), protocol-change issue #89. It was first served by RoboTangle's standard tasks; the
benchmark's own release called it "2.3", but that number had already gone to the realtime capability (#86). Reference
implementation: [`scripts/eai_standard/v2_4/`](../scripts/eai_standard/v2_4/), with `rcb_limited.py` and
`rcb_client.py`. `rcb1.py`, `run.sh`, the client image and the client pins are the 2.2 ones in `scripts/eai_standard/`.

### 19. Version

`eai-standard/2.4` = 2.3 + the **operations capability** below.
- Every earlier addition stays a MAY capability. That covers 2.2's depth, `frame_time_s`, extrinsics, `POST /kinematics`
  and the per-call wall bound, and 2.3's realtime capability (Part 3,
  "Standard-realtime mode"). So a 2.2 service that adds the operations capability is a 2.4 service.
- Standard-mode tasks may declare `protocol = "eai-standard/2.4"` (PROTOCOL §2.3). Standard-realtime tasks stay on 2.3
  (PROTOCOL §4b).
- Everything in PROTOCOL §4 holds unchanged: four endpoints (plus `/kinematics` and the one below), RCB1, no reset,
  crash recovery that resumes the same episode, and grading by a fresh replay.
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
| The restart ends the episode as `call_watchdog` only on evidence that the watchdog fired: the watchdog prints into its own file (`call-watchdog.trace`, emptied at every call), and its banner there is that evidence. `call-watchdog.json` alone, or its deadline having passed by the time the container is back, is not: any other crash during a call (a segfault, a CUDA error, an OOM kill) is resumed like every crash (PROTOCOL §4.7), and a resume removes both files | MUST |

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

The verifier still grades `final.json` only (PROTOCOL §4.8).

`python3 scripts/eai_standard/v2_4/selftest.py` tests the watchdog's evidence, the tick ledger and the 400 for malformed
bodies on the CPU (numpy only, about 15 s).

### 25. Compatibility

- 2.x clients connect to a 2.4 service unchanged. They send no operation ids and get 2.2 behaviour.
- The 2.4 client sends ids only when `/spec.protocol` is 2.4, so it also works against 2.1–2.3 services.
- A benchmark adopts 2.4 by copying `scripts/eai_standard/v2_4/` unchanged; `ci_checks/check-tooling-identity.sh`
  checks the copies.
