# Panda Dynamic Scenes · Reciprocal two-cup air relay (D01) (standard-mcp)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). A ball is thrown high
into the air when the episode starts and comes down near the left Panda. The left arm catches it in its cup and throws
it through the air to the right arm, whose cup must be moving when the ball enters it. The right arm carries the ball to
a second transfer region and throws it back from there. The left arm catches it again and delivers it into an open box
that slides back and forth along a rail, where the ball must settle while the box is moving. The robot runs as a service
you reach only through the `efe-robot` MCP tools, as if it were real hardware.

### Scene
Two Pandas. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw
pi (facing -x). Each hand carries a closed square cup: 0.12 m x 0.12 m inside, walls 28 mm high and 5 mm thick, floor 5
mm thick. The tool frame is the centre of the floor's top surface, z up out of the cup. A fixed adapter bar joins the
cup's -x wall (tool frame) to the hand; in the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the left
cup is level with identity orientation, centre at (0.02, -0.18, 0.22). The right cup is level and turned 180 deg about z
(orientation wxyz (0, 0, 0, 1), so its adapter side faces +x, towards its own base), centre at (0.19, 0.18, 0.22). On
both arms the tool's adapter runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes
its fingers touch the adapter, which ends the episode as a collision with its own tool (both grippers start fully open,
at 0.08 m).

A small orange ball (radius 18 mm) is thrown upwards and towards the left arm at t = 0. It rises high and falls back
down near the left cup within about the first second. A blue open box (the cart: 0.15 m x 0.15 m inside, 0.06 m deep) is
the moving link of a straight rail along the world's y axis, on the left arm's side. It is driven back and forth the
whole episode, slowly, and slowest where it turns around. There are no other objects. The table top is the world's z = 0
plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. The simulated clock advances only through your calls: every row you send and every second you
watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs
control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the
cameras saw. The episode lasts at most 25 s of robot time (the task's horizon, 2500 control steps): when it is reached
before the task is complete, the task has failed. The ball is already in the air at t = 0 and comes down within about
the first second, so watch it in short steps. The cart moves back and forth the whole time and is too slow for the
delivery near its turning points, so when the delivery can succeed depends on how long the earlier phases took.

## Goal
Success: the left cup catches the falling ball and throws it in a high arc (the ball well above the cups, over 0.30 m
up) to the right cup, which must be moving, away from where it started, as the ball drops into it; the right cup carries
the ball to the second transfer point, about (0.13, 0.15) at 0.24 m up, and throws it back from there in a high arc
(over 0.31 m up); the left cup catches it again and drops it into the moving cart, where it comes to rest out of the cup
and rides along for about 0.7 s while the cart moves. A catch means the ball drops into the cup from above after flying
free and stays there, not a bounce. The task fails at once if the right cup catches the ball while (nearly) standing
still, or if the throw back does not leave from the second transfer point.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Each cup may touch only the ball. Neither cup may touch the cart, its rail or
  base, or the table. The two arms must never touch each other: any contact between any parts of panda-0 and panda-1,
  cups included, is a failure. No other robot part (fingers, hands, links, bases) may touch anything, including the
  ball. In every task an arm never touches itself, no robot part touches the table or the floor, a robot part other than
  an allowed one touches nothing, a tool touches only what the task allows, and no contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes and resets: you have 3 resets (the spec's reset budget is authoritative). A reset puts the robot and the
  scene back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a
  new episode, abandoning the running one or after one has ended. Only the last episode is graded: an episode you reset
  away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode then
  running is the one graded. Do not stop early: while the episode runs, or a reset is left, the run can still pass.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the service tells you only that an episode has ended and why (a success, a failure or a
  simulator error).
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the scene's world frame, shared by both arms: origin on the table top (z = 0), +X
from the left arm (panda-0, at the -X end, facing +X) towards the right arm (panda-1, at the +X end, facing -X), +Y left
as seen from the left arm, +Z up; positions in the task text are already in this frame, and each arm's base pose is in
describe_robot's spec_file (robot_spec.arms); metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts:
left (arm: 7 joints, no end-effector pose); right (arm: 7 joints, no end-effector pose). Cameras: `overview`, `closeup`.

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

This robot: Each arm takes absolute joint-position targets (rad). Its servo turns every new target into a smooth,
jerk-limited motion (the joints arriving together, at most about 1.4 rad/s on joints 1-4 and 1.7 rad/s on joints 5-7)
and tracks it with torque control, so a far target is reached smoothly: move_robot with a short duration_s (e.g. 0.01)
sends the goal as one target and lets the servo set the pace, a longer duration_s ramps the target. There is no
end-effector pose command and no kinematics service: joints only. The scene moves by itself from the first control step,
and robot time passes only inside calls that move or wait (10 ms per control step; observe with seconds 0 is free), so
prepare a motion before sending it and use execute_trajectory (space joint, dt from 0.01 s) for timed sequences.
Positions in the task text are world coordinates (base_text says how they map to the base frame). describe_robot's
spec_file has robot_spec (base poses, joint, servo and safety limits) and proprio_groups for proprio_now (joint_pos,
tcp_pose, joint_vel, gripper_opening, joint_effort, tool_pose: world frame, quaternions wxyz; target: the targets in
force). Native rows (action type joint_position): per arm joint1..7 (rad) then the gripper aperture (m, 0 = closed ..
0.08 = open), panda-0 first.

### Observations
- World frame: metres, z up, the table top is the plane z = 0; quaternions are wxyz. Each arm's base pose is in the
  robot spec (`arms`).
- Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
  calibration in the spec's `["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
- The proprio columns are named in the spec's `["proprio_groups"]`: `joint_pos` (per arm joint1..7, finger_left,
  finger_right), `tcp_pose` (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort`
  (motor torques), `tool_pose` (the task tool's frame), `target` (the targets in force). The arms are listed panda-0
  first.

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
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 3 resets, each a new episode from the same frozen starting state; only the last episode is graded.
