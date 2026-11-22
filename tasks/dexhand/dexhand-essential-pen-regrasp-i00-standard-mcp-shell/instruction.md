# DexHand: Paper Mate palm-to-tripod pen regrasp — MCP tools and shell

With the wrist fixed, move the unsupported pen 30 mm along its initial longitudinal axis relative to the palm, then turn its axis by 45 degrees and hold its marked grip band with thumb, index and middle fingertips. The initial pen rests against the central palm surfaces; the final pen must clear those central palm surfaces. All three named fingertips must contact the marked band. Other finger links may also contribute contact; an exclusive fingertip-only grasp is not required. No table support, other hand or whole-object release is allowed.

You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently
actuated finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands).
The wrist stage is position actuated in the physics engine; grasping and manipulating require physical contact.
The five fingers are thumb, index, middle, ring and pinky. The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints.
The first six entries of every action MUST remain [-0.08, 0, 0.29, 0, 0, 0].
Float32 wire-format rounding is accepted and normalized to those exact fixed targets before physics runs.
Use the declared target values rather than copying measured wrist joint positions. Only the finger targets may
change. Objects have no actuators, scripted motion or grasp attachments; they move through contact and normal gravity.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |
| `r.reset()` / `POST /reset` | `reset_episode()` |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the scene's world frame (+Z up; the wrist stage is fixed in it): the coordinates of
the task text. Space `native` sends rows in the robot's own action types exactly as the sections below describe them
(their frame, units and gripper values).

**This robot** (Sharpa Wave dexterous hand (22 finger joints) on a locked six-axis wrist stage: fingers only):
right_hand (hand: 22 joints). Cameras: `overview`, `side`, `palm`, `inhand_top`, `inhand_side`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** Fixed-wrist task: the six wrist-stage targets (the first six action columns) must stay at
[-0.08, 0, 0.29, 0, 0, 0]; move_robot and execute_trajectory joint rows keep them, and native rows must carry them
unchanged. Only the fingers (part right_hand) move. inhand_top and inhand_side are close-ups of the held object (no
object state is published). Every column is a position target (servo); grasping and carrying work only through contact.
The parts follow the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20
finger joints per hand) the columns differ: use execute_trajectory space native with the order in spec
action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured
poses are in the world frame of the task text, quaternions wxyz.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Sharpa rows: the six wrist targets, then `right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`, `right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows: the same six wrist targets, then `r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`, `MFJ0..3`, `RFJ0..3`, `LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP). Both hands are mounted in the same wrist frame; Sharpa fingers use the dissipative velocity coefficient declared in the frozen instance, Wuji fingers the manufacturer's position servos. Sharpa starts from the instance's declared finger pose; Wuji starts from the pose in `wuji_reset.json` (neutral fingers when the file is absent), an authoring choice that keeps the object held at reset, not a policy. The wrist, fixtures and predicate are identical for both hands; where a Wuji grasp cannot hold an object at the Sharpa start pose, `wuji_reset.json` also declares the held objects' start poses in the Wuji grasp, and every reset-relative quantity is measured from the post-reset pose.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

## Success predicate
The verifier evaluates these conditions on features it computes from simulator state (values rounded to six significant digits here; the verifier uses the frozen task's unrounded values, which differ from these only beyond the sixth significant digit). A stage or the terminal condition counts a control sample only if its bounds held at every 2 ms physics substep of that control interval; stages are completed in order and each starts after the previous one.

1. Stage `advance_pen`: `0.024 <= pen_axial <= 0.036`, `0 <= pen_angle <= 0.2`, `2 <= contacts <= 5`, for 5 consecutive control samples.
2. Stage `turn_and_tripod_grip`: `0.024 <= pen_axial <= 0.036`, `0.65 <= pen_angle <= 0.92`, `3 <= pen_grip_contacts <= 5`, `contact_thumb == 1`, `contact_index == 1`, `contact_middle == 1`, `pen_palm_contacts == 0`, `pen_grip_thumb == 1`, `pen_grip_index == 1`, `pen_grip_middle == 1`, for 5 consecutive control samples.
3. Terminal hold after the last stage: `0.024 <= pen_axial <= 0.036`, `0.65 <= pen_angle <= 0.92`, `3 <= pen_grip_contacts <= 5`, `contact_thumb == 1`, `contact_index == 1`, `contact_middle == 1`, `pen_palm_contacts == 0`, `0 <= speed <= 0.06`, `pen_grip_thumb == 1`, `pen_grip_index == 1`, `pen_grip_middle == 1`, for 25 consecutive control samples.

Invariants, checked at every physics substep for the whole episode (fail-fast): `0 <= force <= 80`, `0 <= speed <= 12`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `support == 0`, `0 <= object_displacement <= 0.07`, `0.18 <= object_height <= 0.6`, `object_hand_contacts >= 1`, `pen_initial_palm_contacts >= 1`, `0 <= pen_initial_horizontal_error <= 0.174533`.

The first violated invariant or guard, a non-finite feature or unstable physics fails the episode immediately and permanently: the episode ends there and later rows are not executed, so a dropped, slipped or knocked-away object can never be recovered in that episode (a reset starts a new one: `## Episodes and resets`). Success is reached when the terminal hold completes; the episode ends there too. Completing only some stages is a failure.

Feature definitions:
- `pen_axial`: pen displacement along its reset axis in the palm frame, m
- `pen_angle`: angle between the pen axis and its reset axis in the palm frame, rad
- `contacts`: fingers whose fingertip pad touches a task object (> 0.01 N)
- `pen_grip_contacts`: fingers whose fingertip pad touches the pen inside the painted grip band (> 0.01 N)
- `contact_thumb`: see scene.py
- `contact_index`: see scene.py
- `contact_middle`: see scene.py
- `pen_palm_contacts`: palm contacts with the pen (> 0.01 N)
- `pen_grip_thumb`: see scene.py
- `pen_grip_index`: see scene.py
- `pen_grip_middle`: see scene.py
- `speed`: largest absolute velocity of any task-object degree of freedom, m/s or rad/s (peak over the substeps)
- `force`: largest contact force on any task object, N (peak over the 2 ms substeps)
- `palm_drift`: palm displacement from its reset position, m
- `wrist_rotation`: palm rotation from its reset orientation, rad
- `support`: contacts (> 0.01 N) between a task object and the environment (table, fixtures)
- `object_displacement`: object displacement from its reset position in the palm frame, m
- `object_height`: height of the object's centre above the world origin, m (the table top is at 0.10 m)
- `object_hand_contacts`: contacts (> 0.005 N) between the object and any hand link
- `pen_initial_palm_contacts`: palm contacts with the pen in the frozen reset (constant)
- `pen_initial_horizontal_error`: inclination of the pen in the frozen reset, rad (constant)

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. A failure ends an episode at once; a
reset starts a new one (see `## Episodes and resets`). The service records every action and watch step, then judges
the graded episode as it ran (that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`;
no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
obs = r.get_obs(cameras=["overview", "inhand_top"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, 28)` (Sharpa) or `(T, 26)` (Wuji) in `spec["action_types"]["joint_position"]["layout"]` order: wrist XYZ translations (metres),
three serial XYZ rotational joints (radians), then the 22 or 20 finger joints (radians). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview,
side, palm (behind the hand), and two close-ups of the held object, `inhand_top` (from above the palm)
and `inhand_side` (from the thumb side), at 640 x 480; the default is overview and inhand_top. No object state is
published: the close-ups (with depth and their calibration) are how you see the object in the hand. Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call
returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for larger chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it without seconds
only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied.
If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery
resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **10 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
