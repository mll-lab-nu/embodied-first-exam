# Standard-mode protocol `eai-standard/2.2` (extension of 2.1)

> Formerly `rcb-limited/2.2`. Status: accepted, pending (PROTOCOL §6), merged with its crash recovery (§13 below).
> 2.2 is a minor version of [`eai-standard/2.1`](LIMITED_MODE_PROTOCOL.md): everything there holds unless this page
> says otherwise, every 2.2 addition is a MAY capability, and a request written for 2.0 or 2.1 gets the same answer as
> before (plus parts and keys an old client ignores). Which parts are required is listed in PROTOCOL §4.

**Who serves it.** The standard twins of seven benchmarks: BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces
and MyoSuite ([docs/benchmarks/](benchmarks/); MyoSuite: MuJoCo on the CPU, resume class `exact`), and MuJoCo Playground's
quadruped tasks. The RoboTwin and the other MuJoCo standard tasks (DexToolBench, MuJoCo Playground's manipulation tasks) serve 2.1.

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

## 1. Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: 2.1's keys + cameras' intrinsics and mounting, proprio groups, `robot_spec`, `world`, `kinematics`, `depth`, `on_service_error`, `max_call_wall_s` |
| GET | `/status` | — | JSON: `{step, calls, control_steps, done, reason, elapsed_s, resumes}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, video, depth}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, depth, note}` + part `actions` float32 (T, dim) | RCB1 |
| POST | `/kinematics` (2.2) | JSON `{op: "fk" \| "ik", ...}` (§8) | JSON |

Anything else (including `/reset`, `/state`, `/success`) returns **404**. `include_depth` (2.0/2.1) is still accepted (§7).

## 2. Response parts
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

## 3. Request fields (`/submit` header, `/observe` body)
| field | default | meaning |
|---|---|---|
| `cameras` | every camera | names from `spec.cameras`; the client sends `spec.default_cameras` when given none |
| `video_fps` | the service's | frames per simulated second |
| `video` | `mp4` (submit), `frames` (observe) | `mp4` \| `frames` \| `both` \| `none` |
| `depth` (2.2) | `none` | `none` \| `last` \| `frames`; JSON `true` = `last` |
| `include_depth` (2.0/2.1) | `false` | with no `depth` field: `true` answers as 2.1 did (`depth/<cam>` float16 per frame) |
| `seconds` (observe) | 0 | 0 = the current frames, no physics; > 0 (≤ `max_watch_s`) = hold the last command and watch |
| `type`, `dt`, `interpolate`, `note` (submit) | | as 2.1 |

## 4. `meta`
2.1's keys (`step`, `calls`, `control_steps`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio`, `done`,
`reason`), with `cameras` = per requested camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`, `image_size` at the last
frame (omitted when the task sets `RCB_OBS_CALIBRATION=0`). `/submit` adds `chunk_id, type, executed_rows,
control_steps_chunk, physics_steps_chunk, clipped [{row,index,reason}], n_clipped, plan [...], ok`; `/observe` adds
`obs_id, seconds, control_steps_watch, physics_steps_watch`. Both add **`stopped`** (2.2): `null`, or why the service
stopped the call early (§12).

## 5. `/spec`
2.0/2.1 keys, unchanged: `protocol` (`"eai-standard/2.2"`), `simulator`, `robot`, `task_text`, `control_hz`,
`physics_substeps`, `max_chunk_s`, `max_watch_s`, `cameras`, `action_types`, `proprio_layout`, `proprio_groups`, `static`
(scene facts: names, sizes, colours; never a position), `budget` (`{"reset": 0, "steps": null, "wall_clock_s"}`). 2.2 adds:

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

## 6. Actions
As 2.1 (`joint_position` rows `dt` apart, a multiple of the control period, at most 0.5 s, `linear` or `hold`, clipped and
reported; a chunk covers at most `max_chunk_s`). `ee_pose` rows are end-effector targets solved by the benchmark's IK or
planner (per benchmark, §16); a failed row is reported in `plan`. Not yet: `joint_delta`, `joint_velocity`, `ee_delta`,
`joint_torque` (`spec.action_types.not_yet`). After a chunk the task predicate is evaluated; the first success ends the
episode.

## 7. Depth
z-depth = the distance from the camera plane along the optical axis, in metres, for the same pixels as the RGB frame.
0 means no reading. `depth: "last"` returns `last_depth/<cam>` (float32, one depth render per camera per call);
`depth: "frames"` also returns `depth_frames/<cam>` (uint16 millimetres, zlib; decoded by the client to float32 metres,
1 mm steps). Exact by default; `RCB_DEPTH_NOISE=realsense` adds stereo-like noise (σ = 2 mm + 2.5 mm·z², 1 % dropouts,
seeded by `RCB_DEPTH_NOISE_SEED`), as 2.1. Depth never affects physics.

## 8. Kinematics
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

## 9. Proprioception
2.1's rule, kept: a benchmark's 2.0 columns stay where they were; later groups are appended; every column has a name.
Every 2.2 service has at least the groups `joint_pos`, `joint_vel`, `gripper_opening` (metres between the fingertips),
`tcp_pose` (7 columns per `kinematics.tcp_frames` entry) and `joint_effort` (the PD drive-effort estimate, or the
simulator's measured effort).

## 10. Never provided (the declaration of these six benchmarks, PROTOCOL D7)
Through any endpoint, part or `/spec` field, and in the task's texts (instruction, README, task.toml description): where
things are in the world (object poses and positions, world coordinates of workspace items: table or sheet heights, sheet,
well or bin centres, a pixel-to-world formula, a camera's distance to the scene); segmentation of any kind; physical
parameters of the scene (mass, friction, damping, inertia, restitution; the robot's own drive gains are the exception);
the success predicate. Provided: a detailed goal, object names and inventories, categories, sizes and colours where the
task needs them, qualitative relations, the robot and its tool, camera calibration, world conventions (BEHAVIOR's floor at
z = 0 defines its frame), the budget. `rcb_limited.check_spec` refuses to start a service whose `/spec` names a forbidden
field or puts a position into `static`; `ci_checks/check-limited-texts.sh` checks the texts of these six benchmarks (other
benchmarks decide for themselves, D7); `ci_checks/check-limited-protocol.py` checks every response of a live service.
Accepted consequence: a calibrated camera aimed at the workspace tells roughly where the workspace is.

## 11. Errors (no physics executed)
As 2.1: 400 malformed request (including a bad kinematics request), 409 episode over (`/observe` and `/kinematics` still
answer), 413 body over 64 MB, 500 simulator error: **on `/submit` and `/observe` the episode ends** with `reason = "error"`
(PROTOCOL §4.6).

## 12. Per-call bounds (2.2)
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

## 13. Crash recovery
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
  episode end if one was logged, and the `persist` keys, and continues the SAME episode, never a reset. The wall clock
  keeps running from the first start. `spec.on_service_error` tells the agent to wait for `GET /status` (client:
  `Robot.wait_ready()`) and check `calls` / `control_steps`.
- **Limits.** At most `RCB_MAX_RESUMES` (2) resumes; a third crash ends the episode: `sim_crashed_on_call` if every crash
  happened while a call was being served (the agent's failure), else `sim_crashed` (`infra_error = 1`). A journal shorter
  than the log ends it as `resume_failed` (`infra_error = 1`). A verdict already on disk is never overwritten; the service
  then idles with its PID file for the collect hook.
- **Start-up.** A crash before the scene exists is a plain restart. The startup watchdog (faulthandler's C thread: it fires
  even while a native scene build holds the GIL) dumps every thread's traceback to `server.log` and exits after
  `RCB_STARTUP_TIMEOUT_S` (default 900 s); a start that follows failed starts waits min(120, 20·(n − 1)) s first. The
  watchdog stands down once the scene exists, so a long resume replay is not taken for a hang.

### 13.1 Per-simulator resume rule (PROTOCOL §4.7)
The resume check depends on the simulator's determinism class, which the adapter declares (`Episode(..., resume=...)`):

| class | rule | benchmarks |
|---|---|---|
| `exact` | the replayed state hash must equal the checkpoint's; otherwise the episode ends `resume_failed` (`infra_error = 1`) | RoboWits on Genesis' CPU backend; RoboLab (Isaac, CPU PhysX: the resumed service is a fresh process, whose first replay is bit-exact); RoboPaint (ManiSkill/SAPIEN, CPU PhysX, CPU brush model); MolmoSpaces (MuJoCo, CPU physics) |
| `approx` | the hash is compared and the result recorded; a mismatch does not end the episode: `resume_state_mismatch = 1`, and the robot's deviation from its checkpointed proprio is recorded (max \|Δ\| over `joint_pos`; the largest TCP position error from `tcp_pose`). Only a gross divergence, a TCP more than `RCB_RESUME_MAX_DEV_M` (0.05 m) from where it was, ends the episode as `resume_failed` (`infra_error = 1`) | simulators declared nondeterministic: RoboWits on the GPU backend (the particle families separate_marbles_and_sand and stabilize_bottle, `RCB_ROBOWITS_BACKEND=gpu`); BEHAVIOR-1K (OmniGibson declares rollouts nondeterministic; measured so far: live = fresh replay on every 2.2 run, so it normally resumes exactly); ManiGuard (OmniGibson 3.7.2; not measured yet) |

This relaxes "the hash checked" of PROTOCOL §4.7 for declared-nondeterministic simulators only. It cannot raise a score:
the verdict never comes from the live state, it comes from fresh replays of the complete recorded trajectory (the
replayed prefix plus everything after the resume). A mismatch only perturbs what the agent saw, and the flags say so;
results can exclude or rerun such trials. Crashing the simulator on purpose gains nothing: there is no reset, and three
crashes inside calls count as the agent's failure.

### 13.2 Evidence fields
`final.json` and `episode.json` carry `sim_startups`, `resumes`, `resume_state_mismatch` (0/1), `resume_max_tcp_dev_m`,
`resume_max_joint_dev` (`Episode.final_fields()`), and a give-up adds `gave_up`, `reason` and `infra_error`. Graders copy the
numeric ones into `reward.json` (MAY fields, PROTOCOL §2.6), with `infra_error`.

### 13.3 What generators emit (3b–3e)
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

### 13.4 Measured scene builds (input for `RCB_STARTUP_TIMEOUT_S`)
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

### 13.5 Cost and tests
One state hash per call (not per step). A resume replays the episode so far without rendering: RoboWits ~700 steps/s
(CPU), RoboLab ~20/s, BEHAVIOR ~14–20/s (a 50k-step, 4 h episode: 45–60 min of downtime, on the agent's wall clock).
`python3 scripts/eai_standard/selftest.py` (CPU only, ~2 min) runs `toy_server.py` under `run.sh` with a stand-in for
compose's restart policy and checks: resume between and inside calls, both classes, the third crash, the watchdog and
back-off, client hang-up, the wall bound, both collect-hook outcomes, SIGUSR1 during a resume, a simulator error, the
client's protocol names. Per benchmark, the acceptance test (kill the service of one standard task, the episode goes on
and is graded correctly; check that `live_matches_replay` stays 1 where it was) belongs to its PR.

## 14. Evidence and grading (the agent never sees this)
`episode.jsonl` (calls, checkpoints, resumes), `journal.f64`, `startups.jsonl`, `calls/NNNNNN/` (meta + last frames per call),
`server.log`, and at the end `trajectory.npz`, the replays, `replay.mp4`, `final.json`. The collect hook signals the service
by PID after the agent container is stopped; RoboWits grades in-process (Genesis' CPU backend repeats exactly), RoboLab,
BEHAVIOR, RoboPaint and MolmoSpaces dump the episode, exit, and the hook replays it in two fresh processes. A separate, network-less
verifier grades `final.json`: `success = live ∧ replay ∧ deterministic` (RoboWits' GPU-backend families: determinism
reported, not required), reward fields as in PROTOCOL §2.6 and §4.8. A GPU lost to a host systemd reload is reported as
`gpu_lost` / `grader_error`. 2.1's live recording (`live.mp4`) is a RoboTwin service feature, not part of 2.2.

## 15. Privileged-mode parity
Every privileged Session of the six benchmarks offers the same information from the same code: `s.camera_info()`,
`s.render_depth(cam)`, `s.robot_spec()`, `s.kinematics(req)` (`s.kinematics_spec()` = `/spec` `kinematics`). Privileged mode
stays privileged (object state through the tooling).

## 16. Per-simulator notes (the protocol is the same; the robot and the clock differ)
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

## 17. Known issues
- RoboWits: during the in-process grading replay, `/status` and a late `/observe` report the replay's counter and scene;
  the episode is over by then and the grade is unaffected.
- BEHAVIOR-1K: while the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency);
  its `extrinsic_cv` is the pose it was rendered with, the proprio row the state at `frame_step`.
- Per-call state hashing on Isaac (RoboLab, BEHAVIOR) is new with crash recovery; their PRs re-check `live_matches_replay`.

## 18. Versioning
`protocol` in `/spec` = `metadata.protocol` = `eai-standard/2.2`. The 2.x client accepts every 2.x service under both
spellings (`eai-standard/2.`, `rcb-limited/2.`); 2.1 clients work against a 2.2 service (they get float16 per-frame depth
for `include_depth` and ignore the new parts and keys).
