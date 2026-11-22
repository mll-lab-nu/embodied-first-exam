# AM-Bench · ambench-cabinet-pick-place-fahexa-i00 (standard-mcp)

## Task
A simulated aerial manipulator: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude while
hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in AM-Bench
(Isaac Lab). A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside
one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet. The robot runs as
a service you reach only through the `efe-robot` MCP tools, as if it were real hardware: one live episode.

### Scene
The ground is the world's z = 0 plane; there is no wall. Ahead of the robot stands an immovable cabinet with light-wood
panels and metal handles, about 1.2 m wide, 0.6 m deep and 1.68 m tall, its front facing the robot and its top a flat
board. From the bottom up: a solid base; a drawer with a horizontal bar handle; a compartment closed by two hinged doors
with vertical handles, which are locked; the can's compartment, about 27 cm tall, whose right half (as seen from the
robot) is closed by a fixed panel and whose left half is closed by a sliding door with a vertical bar handle; and a top
compartment closed by a front panel with a horizontal bar handle. The sliding door slides sideways to the robot's right,
in front of the fixed panel, over 0.6 m of travel; it has no spring (it stays where it is left) and its motion is
resisted by damping and friction. The bottom drawer and the top front panel are not jointed: they are loose parts held
in place only by gravity and contact. The can (4 cm in diameter, 6.4 cm tall, 5 g, with a soda label) stands upright on
the floor of the sliding-door compartment, a little in from the front and hidden behind the closed sliding door; its
exact spot varies by a few centimetres between instances, and nothing else varies. Nothing moves by itself. The robot
starts hovering level and motionless, facing the cabinet, with its arm at its zero joint configuration (end effector a
little ahead of and above the airframe) and the gripper closed.

## Goal
Success: the can stands at rest on the top of the cabinet; where on the top, which way up and whether the gripper still
holds it do not matter. The episode ends by itself as soon as the task is done (reason `success`), or as a failure when
its 60 s of simulated time run out (reason `episode_timeout`).

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Simulated time moves only while the robot runs your commands or you watch it hold still: between your calls the world
  is frozen.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: at the airframe's centre (measured at the start of each call), +X the airframe's
heading, +Y to its left, +Z straight up (level: the heading only, the airframe's tilt is ignored); it moves with the
airframe; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: end-effector pose, gripper).
Cameras: `ee_camera`, `base_camera`.

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

This robot: The robot flies: there is no separate base command, the airframe moves wherever the end-effector target
needs it (base_odometry in each result is the airframe's world position and heading). At the start the airframe hovers
level facing +X with the arm at its zero joints and the gripper closed. Move in small steps and watch the cameras: the
airframe, not only the arm, approaches nearby surfaces. The state's gripper value is the command in force;
gripper_opening_m is the measured finger opening (0.002 m = closed on nothing). The episode ends by itself at the first
control step where the task is done, or at the task's episode length of simulated time (spec_file max_control_steps at
120 Hz).

### Observations
- Cameras (384×384 each, both moving with the robot): `ee_camera` (on the end effector, looking along the gripper) and
  `base_camera` (on the airframe, looking forward); their intrinsics and mounts are in the spec's `cameras`, their pose
  at every frame comes with each reply.
- Depth (`depth=True`): z-depth in metres, 0 = no reading, pixel-aligned with the colour image, in 1 mm steps.
- Proprioception: 45 values a row (their `layout` comes with them): the arm's joint positions, velocities and efforts,
  the gripper's opening and command, the tool frame's pose (`tcp_pose`), the airframe's pose and velocity (`base_pose`,
  `base_vel`) and the end-effector target in force (`ee_cmd`); the groups are in the spec's `proprio_groups`.

## Others
- Neither the cabinet's pose, the sliding door's position nor the can's pose is given: the cabinet, the door and its
  handle have to be found with the forward-looking onboard cameras, the can is hidden behind the closed door at the
  start, and whether the can ended at the right height and at rest can only be judged from the images together with
  proprioception.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
