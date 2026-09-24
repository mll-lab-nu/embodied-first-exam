# Limited-mode protocol `rcb-limited/1.0` (robot as a service)

The agent talks to a **sim service** it cannot open, through JSON over HTTP. There is **no reset**: one trial =
one episode, exactly like one attempt on a real robot. There is **no step limit**; the agent's wall-clock budget
(`[agent].timeout_sec`) is the only limit, and the step count is reported as cost. Nothing the agent can call
reveals object poses, scene files, seeds or the success predicate.

Base URL: `http://sim:8000` (compose network) or `http://localhost:8000` (Harbor egress control puts the service
in the agent's network namespace). The client library tries both. All bodies are JSON; images are base64 PNG.

## Endpoints
| method | path | purpose |
|---|---|---|
| GET | `/spec` | static description: robot, action types, joint names/limits, cameras, budgets |
| GET | `/observe` | current observation without acting (allowed at any time, does not count as a step) |
| POST | `/step` | execute one action, return the next observation |
| GET | `/status` | `{step, physics_steps, done, reason, elapsed_s}` |

Anything else (including `/reset`, `/state`, `/success`) returns **404**.

## `GET /spec` response
```json
{
 "protocol": "rcb-limited/1.0",
 "simulator": "robotwin-2.0", "robot": "aloha-agilex",
 "task_text": "Stack the green block on top of the red block ...",
 "action_types": ["qpos", "ee"],
 "qpos": {"dim": 14,
          "layout": ["fl_joint1","fl_joint2","fl_joint3","fl_joint4","fl_joint5","fl_joint6","left_gripper",
                     "fr_joint1","fr_joint2","fr_joint3","fr_joint4","fr_joint5","fr_joint6","right_gripper"],
          "units": "rad for joints; gripper in [0,1], 0 = closed, 1 = open",
          "limits": {"fl_joint1": [-3.1416, 3.1416], "...": "..."}},
 "ee": {"dim": 16,
        "layout": ["l_x","l_y","l_z","l_qw","l_qx","l_qy","l_qz","left_gripper",
                   "r_x","r_y","r_z","r_qw","r_qx","r_qy","r_qz","right_gripper"],
        "frame": "world: origin at the table centre on the floor plane, +z up, robot base at y = -0.65 facing +y, table top at z ~= 0.74",
        "quaternion": "wxyz, unit norm",
        "note": "same convention as observation.endpose.left/right, so an observed pose is a valid target. NOT the fingertip: this is RoboTwin's end-effector frame, 0.12 m behind the gripper centre along the approach axis on ALOHA-AgileX (gripper_bias 0.12); to put the fingers at p command p - 0.12*approach_axis"},
 "cameras": {"head_camera": {"mounted": "static", "rgb": true, "depth": false, "calibration_in_obs": true},
             "front_camera": {...}, "left_camera": {"mounted": "left wrist", ...}, "right_camera": {...}},
 "physics_hz": 250,
 "budget": {"reset": 0, "steps": null, "wall_clock_s": 3600}
}
```
`limits` are the ranges the service will accept. (The ALOHA URDF only carries placeholder ±10 rad limits; the
service reports ±π for those joints, matching RoboTwin's own joint-legality rule.)

## Observation (returned by `/observe` and `/step`)
```json
{
 "step": 12, "physics_steps": 3480, "time_s": 13.92,
 "images": {"head_camera": "<base64 PNG RGB>", "front_camera": "...", "left_camera": "...", "right_camera": "..."},
 "cameras": {"head_camera": {"intrinsic_cv": [[3x3]], "extrinsic_cv": [[3x4]], "cam2world_gl": [[4x4]]}, "...": "..."},   // RoboTwin's per-camera
                                                                                      // calibration, exactly as in its get_obs(); the whole key is omitted when the task sets RCB_OBS_CALIBRATION=0
 "depth":  {"head_camera": "<base64 float16 little-endian HxW metres>"},            // only if the task enables depth
 "joint":  {"left_arm": [6 floats], "left_gripper": 0.98, "right_arm": [6 floats], "right_gripper": 1.0,
            "vector": [14 floats]},                                                   // measured positions, qpos layout
 "endpose": {"left": [x,y,z,qw,qx,qy,qz], "right": [x,y,z,qw,qx,qy,qz]},              // ee layout, world frame
 "done": false, "reason": null,                                                       // see episode semantics
 "time_left_s": 3412.6                                                                // wall-clock budget left
}
```
Everything the model learns comes from observations (strict gym contract); `/spec` only describes the action space and
static robot facts. Images are what RoboTwin's cameras render (`get_obs()`), nothing more. The per-camera calibration
(`cameras`) is part of RoboTwin's native observation — a real robot ships calibrated cameras too — and a task may
switch it off (`RCB_OBS_CALIBRATION=0`) for a pixels-only variant. No object poses, no segmentation unless a
`perception`-tier task variant explicitly enables it in `/spec`.

## `POST /step`
Request:
```json
{"type": "qpos", "action": [14 floats]}          or          {"type": "ee", "action": [16 floats]}
```
Semantics (identical to RoboTwin's policy evaluator `take_action(action, action_type)`):
- `qpos`: the service plans a time-optimal interpolation (TOPP) from the current joints to the target and steps the
  physics until it is reached (typically 50–300 physics steps); the grippers interpolate linearly alongside. If TOPP
  fails or the target equals the current joints, RoboTwin holds the arm for 50 physics steps; the response reports it
  as `"plan": {"left": "TOPP ... -> arm held 50 steps", ...}` instead of `"Success"`.
- `ee`: the service runs CuRobo to a collision-free path **against the table only** (objects are not in its
  world model) for each arm and executes it; grippers as above. If a plan fails for an arm, that arm holds
  position for 50 physics steps and the response carries `"plan": {"left": "Success", "right": "failed"}`.
- One request = one step, whatever the number of physics steps consumed (`physics_steps` is also reported).

Response: the observation (above) plus
```json
{"ok": true, "plan": {"left": "Success", "right": "Success"}, "done": false, "reason": null}
```

Errors (no physics executed):
| code | when |
|---|---|
| 400 | wrong `type`, wrong dimension, NaN/inf, joint or gripper value outside `spec.limits`, non-unit quaternion |
| 409 | episode already finished (`done` = true); the trial is over, nothing else can be done |
| (connection refused) | service still loading (CuRobo warm-up on start, ~1 min): the socket opens only when the scene is ready; the client retries |
| 413 | request body over 1 MB |

## Episode semantics
- The service starts the episode when the container starts (seed hidden inside the service); the agent's first
  `/observe` is the initial scene.
- After every step the service evaluates the task's own `check_success()` (never exposed). The first success ends
  the episode: `done = true, reason = "success"`. Otherwise the episode ends when Harbor's agent phase ends
  (`reason = "timeout"`), or on an unrecoverable simulator error (`reason = "error"`). At episode end the predicate
  is evaluated once more, so a success that materialised after the last step (an object settling) still counts.
- `elapsed_s` in `final.json` is the episode's wall clock from service-ready to episode end (not including finalize).
- No reset. A dropped object, a collision, a crashed agent script: all count, as on hardware.

## Evidence and grading (agent never sees this)
The service appends one line per event to `/data/episode.jsonl`:
```json
{"ts": ..., "ev": "start", "task": "stack_blocks_two", "seed": 60417, "state_sha": "..."}
{"ts": ..., "ev": "observe", "step": 0}
{"ts": ..., "ev": "step", "step": 1, "type": "qpos", "action": [...], "physics_steps": 212, "plan": {...}, "success": false}
{"ts": ..., "ev": "end", "reason": "success", "step": 37, "physics_steps": 9120, "elapsed_s": 412.3}
```
A `[[verifier.collect]]` hook asks the service to write `/data/final.json` (`success`, `steps`, `physics_steps`,
`elapsed_s`, `reason`) and to render `/data/replay.mp4` from its own frame buffer (six-view grid). Both are
collected as sidecar artifacts and graded in a **separate verifier sandbox**: `reward.txt` = 1 iff
`final.json.success`; `reward.json` carries `success`, `n_actions` (= steps), `sim_steps` (= physics steps),
`elapsed_s`, `video_rendered` — the same field names as unlimited mode (PROTOCOL §3), so results are comparable.

## Versioning
`protocol` in `/spec` is the contract version. Adding fields is backward compatible; changing a layout, a frame,
or the episode semantics bumps the major version. Tasks record the version in `task.toml` `[metadata].protocol`.
