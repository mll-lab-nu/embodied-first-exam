# balance_hard — instance 00 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task:** stand on the
balance board and stay on it, upright and still, for the whole episode.

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
closed. Base frame of this robot: the pelvis frame: +X the way the pelvis faces, +Y left, +Z up (no part here takes an
end-effector pose, and the service reports no position of the robot in the room). Space `native` sends rows in the
robot's own action types exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Unitree H1 humanoid (HumanoidBench, MuJoCo): 19 position servos, no hands, no walking controller): legs
(legs: 10 joints, no end-effector pose); torso (torso: 1 joints, no end-effector pose); left (arm: 4 joints, no
end-effector pose); right (arm: 4 joints, no end-effector pose). Cameras: `left_eye_camera`, `right_eye_camera`,
`room_camera`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the robot base frame that a camera sees at pixel (u, v)
  of its full-size image (u the column, v the row), or one per pixel of `pixels` [[u, v], ...]: from a new depth image
  of that camera and its calibration (no time passes). For a camera with depth and a known pose; for any other the error
  says so.
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

**Notes on this robot.** Every joint command here is HumanoidBench's own normalized servo target, not an angle: -1 and
+1 command the two ends of that actuator's range (range_rad of action type joint_position in describe_robot's
spec_file), linearly, so 0 is mid-range, not 0 rad; values outside -1..1 are clipped. The state reports measured joint
angles in radians (proprio_now, layout proprio_layout: every joint's angle, then its velocity, then the pelvis IMU), so
the two scales differ. At the start of each episode every servo targets 0 rad, which is (-(lo + hi) / (hi - lo)) on the
normalized scale. move_robot and execute_trajectory space joint keep the parts you do not name at the last command you
sent: until you have sent one in an episode (also after a reset), send a whole 19-number row with execute_trajectory
space native (action_type joint_position). There is no walking or balance controller: standing, stepping and keeping
balance all come from the servo targets you send, 50 per second of robot time (control period 0.02 s). Time passes only
inside calls; the episode ends on success, a fall or its last control step, and the service only says that it ended and
why.

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds, when
  the robot falls, when anything but the roller under the board touches the ground or the roller touches
  anything but the ground and the board (see Scoring), after 1000 control steps (20 s of robot time), when
  your time is up, or on a simulator error. Nothing else ends it: a robot that has fallen without meeting one
  of these (lying on its side, sitting, face down) goes on until step 1000, so an episode that is still
  running does not mean the robot is still up. You have **50 resets** (`spec()["budget"]["reset"]`, which is
  authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot
  and the scene back on the same frozen starting state and starts a new episode with its own 1000 control
  steps, either abandoning the running episode or after one has ended; it takes no robot time and returns the
  start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` (its message
  gives `resets_left`) until you reset. **Only the last episode is graded**: an episode you reset away is
  never graded, a success ends the run at once (no reset after it), and when your time is up the episode then
  running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
  `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last
  ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while
  you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is in the room, not the board's or the roller's pose, not the reward: the service judges the episode
  and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a
  simulator error, else `"failed"`). `spec()` gives the robot's own facts, as its URDF would: each actuator's
  range, each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the
  IMU's frame, each camera's field of view and pose.
- There is nothing to hand in: the service records every episode and grades the last one as it ran. Keep the
  script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session
  earlier ends the run the same way, so do not stop early: while the episode runs, or a reset is left, the run
  can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**800**: a total of rewards, not a number of steps (an episode is at most 1000 steps). A good step asks for
only three things, multiplied together — low actuator force, staying upright (head at full standing height on
the board, torso vertical), and near-zero horizontal velocity — so scoring well for one step is not the
difficulty. The difficulty is that the episode ends the moment the pelvis drops too low, anything but the
rolling sphere touches the ground — the board included — or the sphere touches anything other than the ground
and the board, and every step after that is worth nothing. The service ends the episode the moment the pass
mark is reached (`reason = "success"`); that live episode is the verdict.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 19 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 50 in all); returns the start's frames |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 19) servo targets in [-1, 1], one row per control step
```
Measured cost here: about 5.0 ms per control step in one-row calls asking for one head camera,
7.3 ms with both head cameras' images, 1.1 ms per step in chunks of 10 rows asking for one camera
(video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order,
the joints' angles (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`,
`imu_gravity_*`).

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["action_types"]["joint_position"]["layout"]`; the proprioception measures the same joints in the same
order). A target of −1 or +1 commands one end of that servo's range,
`spec()["action_types"]["joint_position"]["range_rad"]` in radians, and the scale is linear, so 0 is
mid-range, not 0 rad. A constant action commands joint *targets*, not a pose: whether the robot stays there
depends on whether that pose is stable under gravity and contact.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
