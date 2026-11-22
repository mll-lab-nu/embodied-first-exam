# RoboARC · cast_coil (standard-mcp)

## Task
Two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base, at a table (RoboARC, MuJoCo). Assemble the
gold and silver Cast Coil pieces into their matching interlocking configuration, then release both. The robot runs as a
service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

## Goal
Success: the gold and silver pieces are fitted together exactly in their interlocking configuration, the assembly
resting on the table (at least one piece standing on it, neither hanging off it), and the robot has let go of both and
moved clear, with both pieces at rest; merely touching or holding them together does not count. Do not jam pieces into
one another: a success with pieces pushed into each other is held for review instead of being credited. Dropping a piece
off the table ends the episode as a failure. The episode ends, as a success, as soon as all of this has held for half a
second.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration), its own sensor readings and the
  safety readings (Robot Interface); no object poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: origin at the robot's root link (the origin of the service's frame), +Z up; +X is the
service frame's +y axis (across the table, between the two arms) and +Y its -x axis (towards the left arm); metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, end-effector pose, gripper); right
(arm: 6 joints, end-effector pose, gripper). Cameras: `cam_high`, `cam_low`, `cam_left_wrist`, `cam_right_wrist`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The episode ends by itself at the first success (all of the task's final conditions holding for its
confirmation time: after the last move let simulated time pass with wait or observe seconds), when the task's own
failure predicate fires (reason task_failed) or when your time is up; there is no step budget and nothing to signal.
End-effector goals are solved by the service's inverse kinematics (no collision checking) and driven to in joint space;
a solution more than 0.5 rad from the current joints on any joint is refused for that arm (it holds), so long
end-effector moves go in steps of a few cm and degrees. Arm joint targets move at most 0.04 rad per control step; a
faster request takes the steps it needs. No gripper target goes lower than 15 mm below the tabletop. Grasping is
assisted (spec robot_spec.grippers states the rule): closing on a graspable part inside its grasp region takes hold of
it, and any command that opens the gripper by more than 0.2 % of its travel lets it go. The gripper value in the state
is the command in force; gripper_opening_m is the measured gap between the finger pads. Joint efforts (proprio_now,
*_effort) rise when an arm pushes on something.

### Observations
- Cameras: `cam_high` (static); `cam_low` (static); `cam_left_wrist` (on the robot link `left/gripper_base`; it moves,
  so use the pose that comes with each frame); `cam_right_wrist` (on the robot link `right/gripper_base`; it moves, so
  use the pose that comes with each frame). Resolution 848×480. The spec's `["cameras"][cam]` gives the intrinsics and
  the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`). A
  point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy;
  depth is that Z. The spec's `["robot_spec"]` lists the joints with their position, velocity and effort limits, the
  grippers, the PD gains and the tool frames; the spec's `["world"]` the frame conventions (the world frame: origin at
  the robot's root link on its mounting, +z up; no positions of the scene are given).
- The safety readings (the tool result's `safety`, in every response) report, since the previous call, forcing (the
  arms' pressing loads and forcing events), the deepest task contact, the longest time above its sustained limit and the
  review events (rigid families), the lowest rope / cord volume ratio (soft families) and the table-guard stops, each
  next to its limit.

### Grasping
- Assisted grasping: a gripper whose command moves towards closed takes hold of a graspable part (coil_gold,
  coil_silver) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the
  penetration at most 2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper
  (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, the part drifts 1
  cm / 0.15 rad from its held pose, or the hold has to push or pull its part with more than 60 N averaged over 20 ms) is
  lost, and the gripper must open before it can take hold again; that force is reached when, for example, two held parts
  that hook into each other are pulled apart, or a held part is pressed into another object. Two grippers never hold the
  same part; other objects are grasped physically (friction).
- Grasp regions (one sphere per graspable part): coil_gold: radius 25 mm; coil_silver: radius 25 mm. Both finger
  contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

## Others
- Objects here (the names the safety readings use): `coil_gold`, `coil_silver`.
- The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive
  torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An
  arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint
  targets become its measured joints for that control step, so it stops pushing (the response does not report these
  stops).
- Forcing (an arm drive near its torque cap while its gripper, or a part it holds, presses hard on something) is
  recorded as evidence (the tool result's `safety`) and shown to the reviewer when a success is reviewed; it does not
  end the episode or change the grade by itself. A simulator breakdown ends the episode: as an infrastructure error, or
  as your failure if an arm was forcing just before it.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 4 CPUs, 16 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps, watches included, graded as it
  stands.
