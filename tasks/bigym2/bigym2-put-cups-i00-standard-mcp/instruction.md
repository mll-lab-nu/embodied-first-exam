# BiGym 2.0 · put-cups (standard-mcp)

## Task
A simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo). NVIDIA's GR00T whole-body
controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the robot
balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its
grippers. At the start the two cups stand on the counter in front of you (about 0.7 m away, 14° to your left, 0.86 m
above the floor; about 0.6 m away, straight ahead, 0.86 m above the floor); the wall cabinet above the counter has two
closed glass doors, their handles about 0.5 m away, straight ahead, 1.24 m above the floor and about 0.5 m away,
straight ahead, 1.24 m above the floor, and its bottom shelf is about 0.8 m away, straight ahead, 1.15 m above the
floor. (Distances are from your pelvis along the floor, directions from the way you face, heights above the floor;
measured on this scene.) Take the cups from the counter and gently put them away in the wall cabinet. The robot runs as
a service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: both cups stand on the bottom shelf of the wall cabinet (its glass doors start closed), let go, for a second.
An object counts as held while a finger of a gripper touches it: an open gripper still resting against it holds it. The
episode ends as soon as the success has held for a second; it also ends when the pelvis gets more than 10 m from the
scene's origin, on a simulator error, and after 3000 control steps (60 s of robot time). A fall (the pelvis tipping far
over, or dropping low) makes the episode a failure without ending it.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get what the robot's three cameras see (RGB, 84x84: `head`, `left_wrist`, `right_wrist`) and
  its own proprioception; not where any object is now (only the start positions under Task), not the success check: when
  the episode ends, the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is on the floor under the pelvis: +X the way the pelvis faces, +Y left, +Z up; it moves
with the robot; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 7 joints, no
end-effector pose, gripper); right (arm: 7 joints, no end-effector pose, gripper); torso (torso: 1 joints, no
end-effector pose); lift (lift: 1 joints, no end-effector pose). Cameras: `head`, `left_wrist`, `right_wrist`.

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
- `locomote(vx, vy, wz, duration_s, height?)`: walk with the robot's own controller (body-frame velocities), then stop;
  returns the displacement.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The arms take joint positions only (no end-effector pose command); each joint's axis and range and each
gripper's point between its finger pads are in describe_robot's spec_file (joints, joint_frame, grippers). The servos
track with a small error: the measured arm joints sit a little below their targets, by up to a few hundredths of a
radian. The torso lean (target torso) and the pelvis height (target lift) are commands to the whole-body controller,
which also moves the waist. Time passes only inside calls; the episode has a fixed number of control steps (50 per
simulated second; control_steps in every result counts those used, spec_file max_control_steps is the total). A fall
(the pelvis tipping far over, or dropping low) makes the episode a failure without ending it.

### Observations
Cameras: `head`, `left_wrist`, `right_wrist` (RGB, 84x84); the spec's `["cameras"]` gives each camera's field of view
and its pose at the start. Each proprioception row has, in the spec's `["proprio_layout"]` order: the positions
(`*_pos`) of the 3 waist joints (they show the lean you command), each arm's 7 joints (rad) and its gripper's 2 finger
joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its
heading, in rad: the room's frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): 25 values;
then their velocities (`*_vel`, per second) in the same order; then `left_gripper_state` and `right_gripper_state` (0
open .. 1 closed); then the pelvis pose again as the base controller tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`,
`pelvis_yaw`). The spec's `["joints"]` gives each arm, waist and finger joint's axis, a point on it and its range (the
pelvis frame with every joint at 0: the spec's `["joint_frame"]`; the sign convention: the spec's `["joint_sign"]`), the
spec's `["grippers"]` the point between each gripper's finger pads on its wrist link, and the spec's
`["cameras"][camera]["mount"]` each camera's pose on its link.

## Others
- The whole-body controller: it follows velocity commands with some lag and wobble, so read the pelvis pose and close
  the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least
  0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso
  leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8
  rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how
  the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It
  keeps the robot balanced but does not stop it from walking into things.
- Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below the
  targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag.
- Ending your session early ends the run as the time limit does: do not stop while the episode runs; it can still pass.

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
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
