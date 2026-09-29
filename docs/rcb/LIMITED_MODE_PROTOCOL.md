# Limited-mode protocol `rcb-limited/2.2` (robot as a service)

The agent talks to a **sim service** it cannot open, over HTTP. **No reset**: one trial = one episode. **No step limit**;
the agent's wall-clock budget is the only limit; actions and simulated time are reported as cost. **Nothing says where
things are**: no object poses or positions and no world coordinates of the workspace, and no physical parameters,
segmentation, scene files, seeds or success predicate (§ Never provided). The agent gets a detailed task (objects named,
sizes and colours where the task needs them), the robot, calibrated cameras, depth, proprioception and kinematics.
Videos, frames, depth and proprioception come back as **binary** in the response body (RCB1 frames, below), never
base64; the agent's code decides what to keep.

Versions: 2.0 = `/submit` + `/observe` + RCB1; 2.1 = 2.0 + measured proprioception + optional depth noise (Kangrui,
RoboTwin); **2.2 = 2.1 + depth (last frame or every frame) + per-frame step, time and camera poses + camera intrinsics
and mounting, a robot spec sheet and world conventions in `/spec` + a stateless `/kinematics` endpoint**. Every 2.2
addition is optional for the agent: a request written for 2.0 or 2.1 gets the same answer as before (plus parts and
keys an old client ignores). Services: BEHAVIOR-1K, RoboLab, RoboWits and RoboPaint serve 2.2; the RoboTwin tasks on this
branch serve 2.0.

Base URL: `http://sim:8000` (compose network) or `http://localhost:8000` (Harbor egress control puts the service in the
agent's network namespace); the client tries both. The socket opens only when the scene is ready (~1-5 min); until then
connections are refused and the client retries.

## Endpoints
| method | path | body | response |
|---|---|---|---|
| GET | `/spec` | — | JSON: action types, cameras (intrinsics, mounting), proprio layout + groups, robot spec, world, budget, kinematics, depth |
| GET | `/status` | — | JSON: `{step, calls, control_steps, done, reason, elapsed_s}` |
| POST | `/observe` | RCB1 or JSON `{cameras, seconds, video_fps, video, depth}` | RCB1 |
| POST | `/submit` | RCB1: header `{type, dt, interpolate, cameras, video_fps, video, depth, note}` + part `actions` float32 (T, dim) | RCB1 |
| POST | `/kinematics` | JSON `{op: "fk"\|"ik", ...}` (§ Kinematics) | JSON |

Anything else (including `/reset`, `/state`, `/success`) returns **404**. `include_depth` (2.0/2.1) is still accepted
(§ Depth).

## RCB1 frame
```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```
`rcb1.py` (encode/decode, `python -m rcb1 unpack f dir`) is shipped with the client, unchanged since 2.0.

### Response parts
Every recorded frame of a call (the first, one every `control_hz / video_fps` control steps, the last) has one entry on
one shared frame axis N: the rows of `frames/<cam>`, the frames of `video/<cam>`, `proprio`, `frame_step`,
`frame_time_s`, `extrinsic_cv/<cam>` and `depth_frames/<cam>`.

| part | kind | content |
|---|---|---|
| `video/<cam>` | mp4 | H.264 of the N frames (`video` = `mp4` \| `both`) |
| `frames/<cam>` | array uint8 (N,H,W,3) | the raw frames (`video` = `frames` \| `both`) |
| `last/<cam>` | array uint8 (H,W,3) | the last frame, always |
| `proprio` | array float32 (N,D) | one proprio row per frame, columns `spec.proprio_layout` |
| `frame_step` (2.2) | array int64 (N,) | the frame's step index: control steps executed since the episode start when it was rendered |
| `frame_time_s` (2.2) | array float64 (N,) | its simulated time, `frame_step / control_hz` |
| `extrinsic_cv/<cam>` (2.2) | array float64 (N,3,4) | world → camera (OpenCV axes) at that frame, every requested camera (constant for a static one) |
| `last_depth/<cam>` (2.2) | array float32 (H,W) | z-depth of the last frame in metres (`depth` = `last` \| `frames`) |
| `depth_frames/<cam>` (2.2) | bytes, `codec: "zlib"`, `dtype: "uint16"`, `shape: [N,H,W]`, `unit: "mm"` | z-depth of every frame: zlib of C-order uint16 millimetres (`depth` = `frames`); the client decodes it to float32 metres |
| `depth/<cam>` (2.1) | array float16 (N,H,W) | z-depth of every frame in metres, only for a 2.1 request (`include_depth: true` without `depth`) |

A response over 256 MB drops `depth_frames/` and `depth/` first, then `frames/` (mp4, last frames, last depth, proprio
and the per-frame arrays always stay) and says so in `meta.degraded`. Requests over 64 MB → 413.

## Request fields (`/submit` header, `/observe` body)
| field | default | meaning |
|---|---|---|
| `cameras` | every camera | names from `spec.cameras` (unknown names are skipped); the client sends `spec.default_cameras` when given none |
| `video_fps` | the service's (see `/spec`) | frames per simulated second |
| `video` | `mp4` (submit), `frames` (observe) | `mp4` \| `frames` \| `both` \| `none` |
| `depth` (2.2) | `none` | `none` \| `last` (depth of the last frame per camera) \| `frames` (plus one depth map per frame). JSON `true` = `last` |
| `include_depth` (2.0/2.1) | `false` | with no `depth` field: `true` answers as 2.1 did (`depth/<cam>` float16 per frame) |
| `seconds` (observe) | 0 | 0 = the current frames, no physics; > 0 (≤ `max_watch_s`) = hold the last command and watch |
| `type`, `dt`, `interpolate`, `note` (submit) | | § Submit |

## `meta` (in every response)
`step` (rows executed so far), `calls`, `control_steps`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`,
`proprio` = `{"layout": [names], "now": [floats]}` (the current row, columns as `spec.proprio_layout`), `cameras` (per
requested camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`, `image_size`, **at the last frame**; the per-frame poses are
the `extrinsic_cv/<cam>` part; the whole key is omitted when the task sets `RCB_OBS_CALIBRATION=0`), `done`, `reason`.
`/submit` adds `chunk_id, type, executed_rows, control_steps_chunk, physics_steps_chunk, clipped [{row,index,reason}],
n_clipped, plan [...], ok`; `/observe` adds `obs_id, seconds, control_steps_watch, physics_steps_watch`.

## `/spec`
2.0 keys, unchanged: `protocol` (`"rcb-limited/2.2"`), `simulator`, `robot` (a name), `task_text`, `control_hz`,
`physics_substeps`, `max_chunk_s`, `max_watch_s`, `cameras`, `action_types` (dims, layouts, limits, units, semantics,
`not_yet`), `proprio_layout`, `static` (the benchmark's scene facts: names, sizes, colours; never a position, height,
centre or world coordinate), `budget` (`{"reset": 0, "steps": null,
"wall_clock_s": the task's agent timeout}`). 2.1: `proprio_groups`. 2.2 adds:

| key | content |
|---|---|
| `protocol_compat` | `["rcb-limited/2.0", "rcb-limited/2.1"]`: requests written for these are served unchanged |
| `default_cameras` | the cameras the client asks for when a call names none |
| `cameras.<cam>` | + `depth: true`, `intrinsic_cv` (3×3), `mount` (below), `depth_range_m` ([near, far] the renderer resolves) |
| `robot_spec` | the robot's spec sheet (below) |
| `world` | `frame` (origin and axes in words; a convention such as BEHAVIOR's floor at z = 0 may define it), `up` (`+z`), `units` (`{"length": "m", "angle": "rad", "time": "s"}`), `quaternion_order` (`wxyz` \| `xyzw`, used by every pose in this service), `camera_axes` |
| `kinematics` | what `/kinematics` answers (§ Kinematics) |
| `depth` | `{"modes": ["none", "last", "frames"], "default": "none", "kind": "z-depth", "unit": "m", "invalid": 0, "max_m": 65.535, "frames_encoding": "uint16 mm, zlib", "noise": "off" \| "realsense"}` |

**Camera geometry.** `intrinsic_cv` K maps a point (X, Y, Z) in the camera's OpenCV frame (x right, y down, z forward) to
the image position u = fx·X/Z + cx, v = fy·Y/Z + cy; the pixel that contains it is (column ⌊u⌋, row ⌊v⌋).
`extrinsic_cv` (3×4) maps world to that camera frame; `cam2world_gl` (4×4) is the camera pose with OpenGL axes (x right,
y up, z backward) = inverse(extrinsic_cv) · diag(1, −1, −1, 1). `mount` says how a camera is fixed:
- `{"type": "static", "extrinsic_cv": 3×4, "cam2world_gl": 4×4}`: it never moves;
- `{"type": "link", "parent_link": L, "link_T_cam_cv": 4×4}`: it rides on robot link L; its OpenCV frame in L's frame is
  `link_T_cam_cv`, so world_T_cam = FK(L) · link_T_cam_cv for any joint configuration (L is in `kinematics.links`).

**`robot_spec`** (every value is the robot's own; nothing about the scene):
| key | content |
|---|---|
| `name`, `description` | the robot |
| `base` | `{"type": "fixed", "pose": [x,y,z, quaternion]}` (world pose of the kinematic root) or `{"type": "mobile", ...}`: root link, where its pose is in proprio, how the base is commanded, its per-step and speed limits |
| `joints` | ordered list of every joint the robot drives: `{name, type (revolute \| prismatic \| continuous), unit (rad \| m), position_limits [lo, hi] \| null, velocity_limit, effort_limit, group}` = the limits the SIMULATOR enforces (they govern what happens; a limit it does not enforce is `null`, never a placeholder), plus, where known, the manufacturer's `rated_velocity` / `rated_effort` and their `rated_source` (left out when unknown) |
| `grippers` | per gripper: `joints`, `opening_m` ([closed, fully open] distance between the fingertips), `command` (the action entries, their range, the open / close rule, when a command switches), `tcp_frame` |
| `controller` | `type` (e.g. joint-position PD), `control_hz`, `physics_hz`, `gains` (`{joint: {"stiffness", "damping"}}`, the drives' own), `note` |
| `tcp` | per tool frame: `{"parent_link", "link_T_frame" (4×4), "definition"}`: the fingertip centre (TCP) and the frame the `ee_pose` action uses, with the offset between them |

## Depth (2.2)
z-depth = the distance from the camera plane along the optical axis (the Z of the OpenCV camera frame), in metres, for
the same pixels as the RGB frame (same H×W, same pixel grid). 0 means no reading: nothing rendered there, a surface
beyond `max_m`, or a simulated dropout. `depth: "last"` returns `last_depth/<cam>` (float32) and costs one depth render
per camera per call; `depth: "frames"` also renders depth for every frame and returns them as `depth_frames/<cam>` (uint16
millimetres, zlib; decoded by the client to float32 metres, 1 mm steps). Exact by default; with the task env
`RCB_DEPTH_NOISE=realsense` stereo-camera-like noise is added (σ = 2 mm + 2.5 mm·z², z in m, and 1 % dropouts = 0, seeded by
`RCB_DEPTH_NOISE_SEED`, as 2.1). Depth never affects physics: rendering reads the state, it does not step it.

## Kinematics (2.2)
`POST /kinematics` is **stateless**: the answer depends only on the request (never on the robot's current state), it
never steps physics, never advances time, never ends the episode and costs nothing but the wall clock. It uses the
robot's kinematic model (the same model the service's `ee_pose` action and camera mounts use).

`spec.kinematics`: `endpoint`, `joint_names` (the q layout; every name is a `proprio_layout` column holding the measured
joint position), `frame` (`world`; `base` for a mobile robot: poses in the base frame unless the request gives
`base_pose`), `base_pose_proprio` (mobile: the 7 proprio columns of the base pose), `quaternion_order`, `links` (the frames
FK returns: robot links and named tool frames), `tcp_frames` (the fingertip centre per gripper, the order of the
`tcp_pose` proprio group), `ee_frames` (the `ee_pose` action's frames), `ik_targets` (frames IK accepts), `ik` (solver,
which joints move, `tol_pos_m`, `tol_rot_rad`, `max_iters` defaults, collision checking: none).

| request | response |
|---|---|
| `{"op": "fk", "q": [...], "links": [optional], "base_pose": [optional]}` | `{"ok": true, "op": "fk", "frame", "poses": {link: [x,y,z, q0,q1,q2,q3]}}` |
| `{"op": "ik", "targets": {frame: [x,y,z, quaternion]}, "seed": [optional q], "base_pose", "tol_pos_m", "tol_rot_rad", "max_iters"}` | `{"ok": bool, "op": "ik", "frame", "q": [...] \| null, "error": {frame: {"pos_m", "rot_rad"}}}` |

`ok` is true when every target is met within the tolerances; `q` is the best solution found (clamped to the joint
limits), `error` its residual per target. A malformed request (wrong length, unknown frame, non-unit quaternion) → 400;
no solution is `ok: false`, never an error.

## Proprioception
2.1's rule, kept: the benchmark's 2.0 columns stay where they were; the 2.1/2.2 groups are appended after them, and
every column has a name (`spec.proprio_layout`). `spec.proprio_groups` = `{name: [first column, count, meaning]}`; groups
may point at 2.0 columns. Every 2.2 service has at least these groups:
| group | content |
|---|---|
| `joint_pos` | measured joint positions (encoders) |
| `joint_vel` | measured joint velocities |
| `gripper_opening` | measured opening of each gripper in metres (distance between the fingertips; a gripper closed on an object stops above its closed value); empty for a robot without one |
| `tcp_pose` | measured TCP pose per `kinematics.tcp_frames` entry (7 columns each, `world.quaternion_order`) |
| `joint_effort` | drive-effort estimate per arm joint, stiffness·(target − q) + damping·(v_target − q̇) (a motor-current analogue; rises when the arm pushes against something), or the simulator's measured drive effort (the meaning says which) |

## `/submit` semantics
- `joint_position` rows are `dt` seconds apart (at least one control period, at most 0.5 s, a multiple of the control
  period); the service streams drive targets at the benchmark's control rate with `interpolate = "linear"` (default) or
  `"hold"` between rows, exactly as a real controller consumes a chunk. Out-of-limit values are clipped and reported. A
  chunk may cover at most `max_chunk_s` (10 s). (RoboTwin: 14 = 6 joints + gripper per arm, streamed at 250 Hz, optional
  velocity feed-forward columns.)
- `ee_pose` rows are end-effector targets (per benchmark: planner or IK per row, below); a failed row is reported in `plan`.
- Not yet: `joint_delta`, `joint_velocity`, `ee_delta`, `joint_torque` (listed under `spec.action_types.not_yet`).
- After the chunk the task predicate is evaluated; the first success ends the episode (`done`, `reason = "success"`).

## `/observe` semantics
`seconds = 0` (default) returns the current frames, free (no physics). `seconds > 0` (≤ `max_watch_s`, 30) holds the last
command, advances physics and returns the video; the predicate is checked afterwards. Watching costs no budget beyond
the wall clock; the simulated time is recorded as cost.

## Never provided
Through any endpoint, part or `/spec` field, and in the task's texts (instruction, README, task.toml description):
where things are in the world — object poses and positions, and world coordinates of workspace items (table or sheet
heights, sheet / well / bin centres, a pixel-to-world formula, a camera's distance to the scene); segmentation of any
kind (masks, labels, instance ids); physical parameters of the scene (mass, friction, damping, inertia, restitution; the
robot's own drive gains in `robot_spec.controller` are the one exception); the success predicate. Provided: a detailed
goal, object names and inventories, categories, sizes and colours where the task needs them, qualitative relations,
the robot and its tool (TCP geometry, gripper strokes, base pose), camera calibration, world conventions (BEHAVIOR's
floor at z = 0 defines its frame), the budget. `rcb_limited.check_spec` refuses to start a service whose `/spec` names a
forbidden field or puts a position into `static`; `ci_checks/check-limited-texts.sh` checks the texts (run_all.sh) and
`ci_checks/check-limited-protocol.py` every response of a live service. A known consequence, accepted: a calibrated
camera aimed at the workspace (e.g. RoboPaint's `canvas_cam` above the main sheet) tells roughly where that workspace is.

## Errors (no physics executed)
| code | when |
|---|---|
| 400 | wrong type/dim, NaN/inf, `dt` or `seconds` out of range, chunk too long, bad interpolate/video/depth value, malformed body or kinematics request |
| 409 | episode already finished (`done`); the trial is over (`/observe` and `/kinematics` still answer) |
| 413 | body over 64 MB |
| 500 | simulator error; on `/submit` the episode ends with `reason = "error"` |

## Episode semantics
The service starts the episode when it is ready (seed hidden inside). The first success ends it; otherwise it ends
when the agent phase ends (`timeout`) or on an error. The predicate is evaluated once more at episode end. No reset.

## Evidence and grading (agent never sees this)
`episode.jsonl` (one record per call), `calls/NNNNNN/` (meta + last frames per call), and on end: `trajectory.npz`, the
replays (`replay_success`, `deterministic`), `replay.mp4`, `final.json`. The collect hook signals the service by PID after
the agent container is stopped; a separate verifier grades `final.json`: `success = live ∧ replay ∧ deterministic`,
reward fields as in PROTOCOL §3. 2.1's live recording (`live.mp4`, per-call action dumps) is a sidecar feature of the
RoboTwin tasks on Kangrui's branch, not part of the wire protocol; the 2.2 services here do not record it.

## Unlimited mode parity (task tooling, same data)
Every unlimited Session of the four 2.2 benchmarks offers the same information from the same code:
`s.camera_info(cameras=None)` → `{cam: {intrinsic_cv, extrinsic_cv, cam2world_gl, image_size, mount, moves}}` for the current
state; `s.render_depth(cam)` → float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned with `s.render_frame(cam)`;
`s.robot_spec()` → the `/spec` `robot_spec` dict; `s.kinematics(req)` → the `/kinematics` answer for the same request
(`s.kinematics_spec()` = `/spec` `kinematics`). The limited service serves exactly these. Unlimited mode stays the
privileged tier (object state through the tooling, as before); nothing of § Never provided's other kinds is added there.

## Known issues
- RoboWits: after the episode ends, the service replays the recorded trajectory in the same process (Genesis' CPU
  backend repeats it exactly) to grade it; while that replay runs, `/status` and a late `/observe` report the replay's
  step counter and scene, not the final state of the episode. The episode is over by then (`done`), and the grade is
  unaffected.
- BEHAVIOR-1K: while the robot moves, a frame shows the scene 2 control steps before its `frame_step` (the renderer's
  latency); its `extrinsic_cv` is the pose it was rendered with, the proprio row is the state at `frame_step`. Rendering
  twice per capture would remove the lag at ~50 ms per frame.
- The 2.0 clients shipped with our tasks compared the protocol string exactly, so they refuse any other version; every
  task ships the 2.x client, which accepts all 2.x services (Kangrui's 2.1 client works against a 2.2 service as well:
  it gets its float16 per-frame depth for `include_depth` and ignores the new parts).

## Versioning
`protocol` in `/spec`. 1.0 (`/step` with one action and base64 images) is retired; 2.0 = `/submit` + `/observe` + RCB1;
2.1 = 2.0 + measured proprioception + optional depth noise; 2.2 = 2.1 + depth + per-frame metadata + camera intrinsics and
mounting + robot spec + world conventions + `/kinematics`. The 2.x client accepts every 2.x service.

## Per-simulator notes (the protocol is the same; the robot and the clock differ)
| | RoboTwin 2.0 | RoboWits (Genesis) | RoboLab (Isaac Lab) | BEHAVIOR-1K (Isaac, R1Pro) | RoboPaint (ManiSkill/SAPIEN) |
|---|---|---|---|---|---|
| protocol here | 2.0 | 2.2 | 2.2 | 2.2 | 2.2 |
| rows streamed at | 250 Hz physics | 30 Hz control (4 substeps) | 15 Hz control (8 substeps) | 30 Hz control (4 substeps) | 20 Hz control (5 substeps) |
| `joint_position` | 14 (+14 velocity ff) | 16: per arm 7 joints + gripper width (m) | 8: 7 joints + binary gripper (switched, not interpolated) | 25: base (per-step targets in the robot frame) + trunk + arms + grippers; base and grippers switch at the row | 7 joints |
| `ee_pose` | 16, CuRobo per row | 16 (right first), IK per row, gripper-tip frame | 8, closed-loop differential IK, fingertip-centre frame | 16 (left first, xyzw), cuRobo IK for both end effectors per row (trunk may bend), base still | 7, brush-tip targets `dt` apart, IK per control step |
| cameras | 4 (+2 free views) | `ego` (static), `wrist_right`, `wrist_left` (848×480) | `egocentric_mirrored_camera`, `over_shoulder_left_camera` (static), `wrist_cam` | the robot's head + two wrist cameras (224×224) | `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam` (all static) |
| episode end → evidence | in-process replay vs live | in-process replay vs live | service dumps and exits; the collect hook replays in two fresh processes | same as RoboLab; artifacts under `/out` (`/data` is the dataset) | same as RoboLab |
| depth (2.2) | 2.1 `include_depth` only | Genesis rasterizer depth | Isaac Lab `distance_to_image_plane` (the service always renders it; unlimited: `Session(..., depth=True)`) | OmniGibson `depth_linear` | SAPIEN depth buffer (geometry only: ink and paint never show) |
| moving cameras (link mounts) | — | `wrist_right` / `wrist_left` on `Pika_Gripper_Base_R` / `_L` | `wrist_cam` on the Robotiq `base_link` | the head camera on its ZED link (moves with the base and trunk), the wrist cameras on their RealSense links | none (all static) |
| `/kinematics` model | — | pinocchio on RoboWits' URDF; q = the 14 arm joints | numpy model from the USD joint frames; q = the 7 arm joints | numpy model of the live articulation's USD joint frames (read at start); q = trunk + both arms; base frame (world with `base_pose`); DLS IK, cuRobo as the fallback | SAPIEN's pinocchio model; q = the 7 joints; tool frame `tip` |
| proprio columns (2.0 → 2.2) | 30 (2.0) | 30 → 80 | 16 → 32 | 49 → 121 (the q_i columns named) | 14 → 28 |
| `robot_spec` effective / rated limits | — | effort = the drive clamp (2000), no velocity limit enforced / URDF | 10 rad/s (USD), 87 / 12 N m / Panda datasheet | PhysX's = the manufacturer URDF's (`r1pro_source.urdf`, read from the mounted dataset) / the same URDF; the base: the service's per-step bounds (4.5 m/s, 9 rad/s) | 100 rad/s (PhysX cap), 100 N m (drive clip) / Panda (ManiSkill URDF) |
`dt` must be a multiple of the benchmark's row period (`1/control_hz` in the spec); `meta` reports `control_steps` and
`physics_steps` where the two differ. `final.json` on the Isaac benchmarks adds `live_matches_replay` (informational) and
`gpu_lost` (the host's GPU became unusable for new processes: an infrastructure failure, graded as `grader_error`).
