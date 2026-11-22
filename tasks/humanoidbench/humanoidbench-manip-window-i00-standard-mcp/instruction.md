# HumanoidBench · window (standard-mcp)

## Task
A simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench, MuJoCo). Grasp the wiping tool — it
starts in the air just in front of the hands and falls within the first second unless it is held — and wipe the window
with it, moving steadily up and down. The robot runs as a service you reach only through the `efe-robot` MCP tools, as
if it were real hardware.

## Goal
Success: the episode's score reaches 650 (an episode has at most 1000 steps). A large share of every control step's
score is paid only while the tool touches the glass; the rest is for moving the tool up and down at around half a metre
per second, keeping both hands near the tool and standing upright. The episode ends early, with nothing more to score,
when the robot falls or the tool drops. The episode ends as soon as the score reaches the mark.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes: 50 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  a robot that has fallen stays down until you reset. Only the last episode is graded: a success ends the run at once
  (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (its two head cameras and `room_camera`, fixed in the room) and
  its own joint angles, joint velocities and pelvis IMU; not where the robot is in the room, not the tool's pose; no
  object poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it
  ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the pelvis frame: +X the way the pelvis faces, +Y left, +Z up (no part here takes an
end-effector pose, and the service reports no position of the robot in the room); metres, radians, quaternions `wxyz`,
gripper 0 open .. 1 closed. Parts: legs (legs: 10 joints, no end-effector pose); torso (torso: 1 joints, no end-effector
pose); left (arm: 5 joints, no end-effector pose); right (arm: 5 joints, no end-effector pose); left_hand (hand: 20
joints, no end-effector pose); right_hand (hand: 20 joints, no end-effector pose). Cameras: `left_eye_camera`,
`right_eye_camera`, `room_camera`.

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
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

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

### Observations
- Cameras: the robot's two head cameras (`left_eye_camera`, `right_eye_camera`, RGB, 256 × 256) and `room_camera`, fixed
  in the room.
- The proprioception (`proprio_now`) has, per row, in the spec's `["proprio_layout"]` order, the joints' angles
  (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`). The proprioception
  measures joints, not actuators: 69 of them, in the spec's `["proprio"]["joints"]` order.
- The robot's own facts, as its URDF would give them, are in the spec file (`describe_robot`): each actuator's range,
  each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each
  camera's field of view and pose.
- When an episode has ended, the tool result's `reason` says why: `"success"`, `"error"` after a simulator error, else
  `"failed"`.

### Time
Time moves only inside calls: running your servo targets and holding the last ones while you watch
(`observe(seconds=s)`, at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while
you think; an observation without seconds is free.

## Others
- Nothing but the task's own rules ends an episode early: a robot that has fallen without meeting one of them (lying on
  its side, sitting, face down) goes on until step 1000, so an episode that is still running does not mean the robot is
  still up.
- The tool starts in the air just in front of the hands and falls within the first second unless it is held.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 50 (`reset_episode()`), each a new episode from the same starting state.
- Steps: each episode ends after 1000 control steps (20 s of robot time).
