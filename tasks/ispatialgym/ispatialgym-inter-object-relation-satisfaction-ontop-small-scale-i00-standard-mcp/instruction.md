# iSpatialGym · make the scene look like a picture (standard-mcp)

## Task
An R1Pro mobile robot with two arms, in a simulated house (iSpatialGym on BEHAVIOR-1K's OmniGibson). `/app/goal.png` is
what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the same camera,
resolution and intrinsics as the robot's own head camera. Change the scene so that it looks like the picture. No
sentence here names the objects that matter or what to do with them: the picture is the whole task. The robot runs as a
service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: the scene looks like the picture: the objects the task is about stand in the relations the picture shows (what
is on, in, under, next to or touching what, what is open, which objects the robot holds or has let go of), and two
objects each stand roughly where the picture shows them, turned roughly as there. The robot does not have to match the
picture (its arms, grippers and base may be anywhere), and nothing the picture does not show is judged.

Once the scene looks right, stop the robot and keep it and the objects still for at least 45 control steps (1.5 s of
simulated time): that is part of success, and the episode ends as soon as it holds.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no map, no world frame; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is under the robot's base_link at the height of its starting pose (about floor level):
+X the way the base faces, +Y to the robot's left, +Z up; it moves with the base; metres, radians, quaternions `wxyz`,
gripper 0 open .. 1 closed. Parts: left (arm: 7 joints, end-effector pose, gripper); right (arm: 7 joints, end-effector
pose, gripper); torso (torso: 4 joints, no end-effector pose); base (mobile: dx, dy, dyaw). Cameras:
`robot_r1:zed_link:Camera:0`, `robot_r1:left_realsense_link:Camera:0`, `robot_r1:right_realsense_link:Camera:0`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}` (the base: `{target: "base", dx, dy, dyaw}`); the
  parts move together and the call returns when the motion is done, with `reached` (the error per goal), a `failure`
  category if a goal was not reached, the state and a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The goal picture is /app/goal.png: the head camera's view (robot_r1:zed_link:Camera:0, same resolution and
intrinsics) once the task is done. Simulated time passes only while the robot moves or you wait, and the episode has a
fixed number of control steps (30 per simulated second; control_steps_left in every result): give short motions a short
duration_s. Success needs the scene and the robot still for 45 control steps: after the last motion, wait at least 1.5
s. End-effector poses (goals and state) are the fingertip centre (TCP), midway between the two fingertips, about 2 cm
further along the fingers than the end-effector frame between the finger pads, where a grasped object is held (the
proprio eef_pose group). An end-effector goal is solved by the robot's inverse kinematics from the current joints and
moves only that arm, in joint space, without collision checking. Grasping is assisted: closing on an object holds what
the finger pads touch, and the hand lets go only when fully open (gripper 0). The reported gripper value is 1 while the
measured opening is below 9 cm (closed, or holding an object) and 0 when fully open; gripper_opening_m is the measured
opening. The cameras give RGB only (no depth). The simulator runs at about 8 control steps per second of wall time.

### Observations
- Cameras: `robot_r1:zed_link:Camera:0` (head: the goal image's camera; it moves with the base and the trunk),
  `robot_r1:left_realsense_link:Camera:0` and `robot_r1:right_realsense_link:Camera:0` (wrists), 1080×1080 RGB each, no
  depth. They all move, so always use the calibration that arrived with the image. While the robot moves, a frame shows
  the scene 2 control steps (67 ms) before the step it is reported at; the camera pose that comes with it is the one it
  was rendered with.
- Proprioception: the robot's joints, base pose and velocity, end-effector and fingertip poses and gripper openings.
  Every pose is in the odometry frame: the robot's `base_link` at the start of the episode (x forward, y left, z up).
  Mind the joint order: the joint columns follow the robot spec's joint list (the trunk, then the two arms interleaved:
  left joint 1, right joint 1, left joint 2, ...), while the action's arm blocks (and the kinematics' `q`) are grouped
  (left arm joints 1-7, then right arm joints 1-7); map by name.

## Others
- Simulated time passes only while you submit rows or watch. To hold still, first send a row with the base command at 0
  (the base keeps its last command until the next row), then submit rows that hold still, or watch with
  `observe(seconds=...)`, which holds the last command.

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
- Resources: 8 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 1900 control steps (63.3 s of simulated time): they are the whole episode, which ends when they run out
  ("failed: the episode's control steps ran out") or on a simulator error; look and plan before you spend them.
