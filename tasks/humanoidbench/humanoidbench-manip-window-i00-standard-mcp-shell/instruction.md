# HumanoidBench · window (standard-mcp-shell)

## Task
A simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench, MuJoCo). Grasp the wiping tool — it
starts in the air just in front of the hands and falls within the first second unless it is held — and wipe the window
with it, moving steadily up and down. The robot runs as a service you reach through the `efe-robot` MCP tools, their
Python client `efe_robot` or the service's own client, as if it were real hardware.

## Goal
Success: the episode's score reaches 650 (an episode has at most 1000 steps). A large share of every control step's
score is paid only while the tool touches the glass; the rest is for moving the tool up and down at around half a metre
per second, keeping both hands near the tool and standing upright. The episode ends early, with nothing more to score,
when the robot falls or the tool drops. The episode ends as soon as the score reaches the mark.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 50 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  a robot that has fallen stays down until you reset. Only the last episode is graded: a success ends the run at once
  (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (its two head cameras and `room_camera`, fixed in the room) and
  its own joint angles, joint velocities and pelvis IMU; not where the robot is in the room, not the tool's pose; no
  object poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it
  ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the pelvis frame: +X the way the pelvis faces, +Y left, +Z up (no part here takes an end-effector
pose, and the service reports no position of the robot in the room); metres, radians, quaternions `wxyz`, gripper 0 open
.. 1 closed. Parts: legs (legs: 10 joints, no end-effector pose); torso (torso: 1 joints, no end-effector pose); left
(arm: 5 joints, no end-effector pose); right (arm: 5 joints, no end-effector pose); left_hand (hand: 20 joints, no
end-effector pose); right_hand (hand: 20 joints, no end-effector pose). Cameras: `left_eye_camera`, `right_eye_camera`,
`room_camera`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: Every joint command here is HumanoidBench's own normalized servo target, not an angle: -1 and +1 command the
two ends of that actuator's range (range_rad of action type joint_position in describe_robot's spec_file), linearly, so
0 is mid-range, not 0 rad; values outside -1..1 are clipped. The state reports measured joint angles in radians
(proprio_now, layout proprio_layout: every joint's angle, then its velocity, then the pelvis IMU), so the two scales
differ; the hands' *J0 tendon servos command the sum of two joint angles. At the start of each episode every servo
targets 0 rad, which is (-(lo + hi) / (hi - lo)) on the normalized scale. move_robot and execute_trajectory space joint
keep the parts you do not name at the last command you sent: until you have sent one in an episode (also after a reset),
send a whole 61-number row with execute_trajectory space native (action_type joint_position). There is no walking or
balance controller: standing, stepping and keeping balance all come from the servo targets you send, 50 per second of
robot time (control period 0.02 s). Time passes only inside calls; the episode ends on success, a fall, a dropped object
where the task has one, or its last control step, and the service only says that it ended and why.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 61 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 50 in all); returns the start's frames |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 61) servo targets in [-1, 1], one row per control step
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.proprio`
(proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never refused; a malformed
request raises `ValueError` and runs nothing. One call returns at most 3000 images. Time per call: about 7.1 ms per
control step in one-row calls asking for one head camera, 9.3 ms with both head cameras' images, 2.2 ms per step in
chunks of 10 rows asking for one camera (video="none" each time).
`r.reset()` puts the robot and the scene back on the same starting state and starts a new episode with its own 1000
control steps (either abandoning the running episode or after one has ended) and returns the start's images and
proprioception; it takes no robot time. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives
`resets_left`) until you reset. `meta["episode"]` and `meta["resets_left"]` count the episodes; the wall clock never
restarts.

### Actions
One action type, `joint_position`: one row per control step (`control_dt` = 0.02 s, 50 Hz), rows `dt` apart (a multiple
of 0.02 s), a chunk at most 10 s. Every number is HumanoidBench's normalised servo target in [-1, 1]: -1 and +1 command
the two ends of that servo's range (`spec()["action_types"]["joint_position"]["range_rad"]`, radians), linearly, so 0 is
mid-range, not 0 rad. The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`,
`right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`.
The remaining 40 are the two Shadow hands, 20 each — `lh_A_*` then `rh_A_*`; each hand's first 2 are its wrist
(`*_A_WRJ2`, `*_A_WRJ1`) and the other 18 its fingers, where each of the 4 `*J0` ones (`*_A_FFJ0`, `*_A_MFJ0`,
`*_A_RFJ0`, `*_A_LFJ0`) drives a tendon that moves two finger joints together
(`spec()["action_types"]["joint_position"]["layout"]`). A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.

### Observations
- Cameras: the robot's two head cameras (`left_eye_camera`, `right_eye_camera`, RGB, 256 × 256) and `room_camera`, fixed
  in the room.
- The proprioception (`obs.meta["proprio"]`) has, per row, in `spec()["proprio_layout"]` order, the joints' angles
  (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`). The proprioception
  measures joints, not actuators: 69 of them, in `spec()["proprio"]["joints"]` order.
- The robot's own facts, as its URDF would give them, are in `r.spec()`: each actuator's range, each joint's axis and
  position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of
  view and pose.
- When an episode has ended, `meta["reason"]` says why: `"success"`, `"error"` after a simulator error, else `"failed"`.

### Time
Time moves only inside calls: running your servo targets and holding the last ones while you watch
(`get_obs(seconds=s)`, at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while
you think; an observation without seconds is free.

## Others
- Nothing but the task's own rules ends an episode early: a robot that has fallen without meeting one of them (lying on
  its side, sitting, face down) goes on until step 1000, so an episode that is still running does not mean the robot is
  still up.
- The tool starts in the air just in front of the hands and falls within the first second unless it is held.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 50 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 1000 control steps (20 s of robot time).
