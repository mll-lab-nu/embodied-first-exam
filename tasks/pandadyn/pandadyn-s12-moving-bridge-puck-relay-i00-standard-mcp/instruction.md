# Panda Dynamic Scenes · Spinning bridge puck relay and goal (S12) (standard-mcp)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). At the start a square puck slides fast along a raised source lane towards
the Panda, and the paddle hangs just above its path. Strike the puck while it is still sliding at 0.25 m/s or more so
that it slides onto a platform (the bridge) that turns continuously about a vertical axis, and from the bridge onto an
exit lane. Intercept it there with the paddle, let it separate, strike it again, and send it along the exit lane through
the doorway of a swinging gate that opens and closes by itself, without touching the gate, and on across a goal line,
without the paddle touching it as it crosses and with the gate still open. The robot runs as a service you reach only
through the `efe-robot` MCP tools, as if it were real hardware.

### Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a paddle: a flat rigid plate 12 mm thick, 0.10 m
wide and 50 mm tall, whose face normal is the tool frame's x axis. The tool frame is the paddle's centre. A rigid grey
adapter behind the paddle (tool -x side) joins it to the hand: a horizontal bar 0.035 m above the tool origin (tool x
from -0.132 to -0.038), a vertical post at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the
post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool
link. In the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the paddle is upright with identity
orientation (faces along world x, width along world y), centre at (-0.08, -0.15, 0.10): its lower edge, at z = 0.075, is
above the incoming puck's path. The tool's adapter runs between the gripper's fingertips: closing the gripper to less
than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision with its own
tool (the gripper starts fully open, at 0.08 m).

The puck is an orange square block 44 mm x 44 mm x 24 mm thick, quite bouncy. At t = 0 it is sliding fast towards the
robot on the source lane, a low, very slippery orange slab, and passes under the parked paddle. If nothing touches it,
it slows down and stops on the lane within about a second, beyond the paddle's start position. Next to the lane's end, a
blue rectangular platform (the bridge, 0.20 m x 0.10 m, 20 mm thick) turns continuously about a vertical axis through
its centre at a steady slow rate, clockwise seen from above. Its top is 2 mm lower than the source lane. Beyond it lies
the exit lane, a second slippery orange slab 2 mm lower again. Near the exit lane's far end a motor-driven gate swings
on a vertical hinge at one side edge of the lane: an amber blade 0.12 m long and 55 mm tall with a small knob on its
free end, its lower edge just clear of the lane. Closed, the blade spans the whole lane. The motor swings it open (its
free end moving downstream), holds it open briefly and swings it closed again, on a fixed cycle of a few seconds, open
for about a second each time. Past the end of the exit lane, on the table, is the goal line, with a static orange wall
(the backstop, 0.14 m wide, 8 cm tall) behind it. The table top is the world's z = 0 plane.

### Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they
do not wait for the robot. The simulated clock advances only through your calls: every row you send and every second you
watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that runs
control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and returns what the
cameras saw. The episode lasts at most 32 s of robot time (the task's horizon, 3200 control steps): when it is reached
before the task is complete, the task has failed. At t = 0 the puck is already sliding fast towards the robot; if
untouched it passes under the paddle and comes to rest on the source lane within about a second, and it is fast enough
for the first strike only during roughly its first 0.4 s. The bridge turns and the gate cycles open and closed the whole
time.

## Goal
Success: the paddle's first touch strikes the puck while it still slides fast, so that it slides onto the turning bridge
and from the bridge onto the exit lane; the paddle intercepts it there, lets it separate and strikes it again; the puck
slides along the exit lane through the doorway of the swinging gate while the gate is wide open, never touching the
gate, and on across the goal line (x = 0.48, around y = 0.12), not touching the paddle and with the gate still open. The
task fails at once if the first touch comes when the puck is already slow, if the puck touches the gate, if it passes
the doorway while the gate is not wide open, or if it crosses the goal line touching the paddle or with the gate closed.

The steps count only in this order, and a step once done stays done. The episode ends by itself as soon as the task is
done or has failed; the task also fails at once when:
- the task's horizon, 32 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the paddle may touch the puck, and the paddle may touch nothing but the
  puck: not the lanes, the bridge, the gate, the backstop or the table. No other part of the robot (fingers, hand,
  links, base) may touch anything. In every task the arm never touches itself, no robot part touches the table or the
  floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows, and no
  contact presses deep into anything;
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
`native`): the robot base frame is the Panda's base frame: origin at the foot of the arm on the table top, +X the way
the arm faces (world +x), +Y left, +Z up; the base's world position is in the task text and in describe_robot's
spec_file (robot_spec.arms), and a world point is that point minus the base position in this frame; metres, radians,
quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, no end-effector pose). Cameras: `overview`,
`closeup`.

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
