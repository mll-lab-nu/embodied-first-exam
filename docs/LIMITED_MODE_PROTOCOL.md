# Limited-mode protocol `rcb-limited/2.0` (robot as a service)

The agent talks to a **sim service** it cannot open, over HTTP. **No reset**: one trial = one episode. **No step limit**;
the agent's wall-clock budget is the only limit; actions and simulated time are reported as cost. Nothing the agent can
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
Anything else (including `/reset`, `/state`, `/success`) returns **404**.

## RCB1 frame
```
"RCB1" (4 B) | header_len uint32 LE (4 B) | header JSON (UTF-8) | blob_0 | blob_1 | …
header = {"v": 1, "meta": {...}, "parts": [{"name","kind","len", ...}, ...]}       # blobs in this order, no gaps
kinds: "mp4" (fps, n) · "array" (dtype, shape; C-order raw bytes) · "jpeg" · "json" · "bytes"
```
Response parts: `video/<cam>` (mp4), `frames/<cam>` (uint8 [N,H,W,3]), `last/<cam>` (uint8 [H,W,3], always), `depth/<cam>`
(float16 [N,H,W], if requested), `proprio` (float32 [N,30], one row per video frame). Requests over 64 MB → 413/400; a
response over 256 MB drops `frames/`/`depth/` and says so in `meta.degraded`. `rcb1.py` (encode/decode, `python -m rcb1
unpack f dir`) is shipped with the client.

## `meta` (in every response)
`step` (rows executed so far), `calls`, `physics_steps`, `sim_time_s`, `time_s`, `time_left_s`, `proprio` = `{"layout": [14
joint names incl. grippers, l_x..l_qz, r_x..r_qz, left_gripper_cmd, right_gripper_cmd], "now": [30 floats]}`, `cameras`
(RoboTwin's per-camera `intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the whole key omitted when the task sets
`RCB_OBS_CALIBRATION=0`), `done`, `reason`. `/submit` adds `chunk_id, type, executed_rows, physics_steps_chunk, clipped
[{row,index,reason}], n_clipped, plan [{row,left,right}] (ee_pose), ok`; `/observe` adds `obs_id, seconds, physics_steps_watch`.

## `/submit` semantics
- `joint_position` (14 = 6 joints + gripper per arm; rad; gripper 0 closed..1 open): rows are `dt` seconds apart
  (`1/250 ≤ dt ≤ 0.5`); the service streams drive targets at 250 Hz with `interpolate = "linear"` (default) or `"hold"`
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
| 400 | wrong type/dim, NaN/inf, `dt` or `seconds` out of range, chunk too long, bad interpolate/video value, malformed body |
| 409 | episode already finished (`done`); the trial is over |
| 413 | body over 64 MB |
| 500 | simulator error; the episode ends with `reason = "error"` |

## Episode semantics
The service starts the episode when it is ready (seed hidden inside). The first success ends it; otherwise it ends
when the agent phase ends (`timeout`) or on an error. The predicate is evaluated once more at episode end. No reset.

## Evidence and grading (agent never sees this)
`/data/episode.jsonl` (one record per call: type, rows, dt, cameras, note, clipped, plan, physics steps, success),
`/data/calls/NNNNNN/` (meta + last frames per call), and on end: `trajectory.npz` (T, 34), a fresh replay
(`replay_success`, `deterministic`), `replay.mp4` (six-view), `final.json`. The collect hook signals the service by PID
after the agent container is stopped; a separate verifier grades `final.json`: `success = live ∧ replay ∧ deterministic`,
reward fields as in PROTOCOL §3.

## Versioning
`protocol` in `/spec`. 1.0 (`/step` with one action and base64 images) is retired; 2.0 = `/submit` + `/observe` + RCB1.
