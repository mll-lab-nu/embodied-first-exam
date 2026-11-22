# Embodied Olympics · catch and shoot (standard-mcp)

## Task
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). Catch and shoot: catch the chest pass that comes to you from the left wing with your two hands, then shoot from
where you stand so that the ball enters the basket from above.

A FIBA court. You stand at the top of the key facing the basket (+x), your arms at rest and your hands empty: the point
under the ring's centre is 5.8 m ahead of your pelvis (inside the three-point line; the free-throw line is 1.575 m ahead
of you). The passing machine stands on the left wing, where a passer would: its wheels' nip (where the ball leaves) 0.92
m ahead of you and 3.97 m to your left, 1.25 m above the floor, its head aimed at you; the ball waits in its throat
behind the wheels. The pass is aimed at the point 0.4 m straight ahead of where your pelvis starts, 1.25 m above the
floor: it leaves on a flat arc (13 degrees up, rising 0.2 m) and is there 0.44 s later, moving at about 8.4 m/s to your
right and 16 degrees downwards. Your hands are open (grip values 0). A grip value is that hand's closure command (0
open, 1 every finger and thumb drive closing; a finger stops on what it touches). The ball is a free body: `held` in
your state says which hand holds it (its fingers and its thumb or palm on it).

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.

The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: you catch the pass with both hands before it touches the floor and, from where you stand, shoot it into the
basket from above.

The referee in the service judges these stages, in order: **catch → release → through the ring**. An attempt (an
episode) ends at the success, at the first foul or after 15 s of robot time, and a success ends the trial at once.
Ending your session ends the run, so do not stop early: while you have attempts left, the run can still pass.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Attempts: 5 resets, each a new attempt from the same start (the first attempt starts when the service comes up); only
  your last attempt is graded.
- No privileged state: you get what the robot's own sensors give (its head cameras, joint encoders, motor torques and
  IMUs) and the venue's fixed cameras; not where you or any object is, not the referee's state. Once an attempt is over,
  every reply carries the referee's call: the outcome (`"success"` or the rule that ended it) and how many of the stages
  it reached.
- Write your own controller; public tools, robot models and pretrained controllers are allowed, a ready-made solution to
  this task is not.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

The attempt fails at once if:
- you touch the ball before it is passed, or the pass touches the floor before you catch it
- between the pass and your release the ball touches any part of you but your hands
- you travel
- you touch the ball again after the shot
- the ball touches the floor before it goes through the ring, or comes up through the ring from below
- you fall before the ball is through

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: on the floor under the pelvis, +X the way the pelvis faces at the start of the call, +Y
left, +Z up (only the heading is sensed, from the pelvis IMU); metres, radians, quaternions `wxyz`, gripper 0 open .. 1
closed. Parts: torso (torso: 1 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose, gripper); right
(arm: 7 joints, no end-effector pose, gripper); legs (legs: 12 joints, no end-effector pose). Cameras: `head_left`,
`head_right`, `venue`.

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
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: Joint targets are absolute angles (rad); a target moves at most the joint's speed limit per 10 ms step. The
arms (left, right) and the torso take joint targets through the `stand` action type: the platform holds the legs in the
standing stance with stiff gains and gravity support but no balance feedback, so a fast or hard arm swing can tip the
robot over; a move_robot call on these parts switches the legs back to `stand`. The legs part uses the `joints` type
(every joint at the default gains; nothing balances the robot in that mode). Legs and arm goals use different action
types: send them in separate move_robot calls, or send rows of any of the robot's action types with execute_trajectory
space native (stand, walk, joints, lowcmd; layouts and bounds in describe_robot). move_robot and joint rows for the arms
and the torso start from the last `stand` row sent through these tools (at the start of an attempt: the start command),
grips included; locomote and the legs part start from the joint targets in force and keep a grip closed while that hand
holds something (holding_* in proprio_now), open otherwise. On a fist pad a grip of 0.5 or more closes it (it holds a
grippable object within 3.5 cm of the palm). Between calls the robot is frozen: time passes only inside calls. There is
no end-effector pose command: describe_robot's spec_file (robot_facts) has each joint's range, speed and torque limits,
default gains and the stance. The robot senses no position: the state shows its heading (the pelvis IMU's yaw) only, and
locomote's displacement reports the turn (dyaw), while dx and dy stay 0: judge distances from the cameras. Once an
attempt is over, results carry the referee's call (outcome, stages_reached of stages_total).

### Observations
- Cameras: the robot's two head cameras `head_left` and `head_right` (RGB 270 × 480, a stereo pair 5 cm apart, tilted
  20° down; depth on `head_left`) and the venue's fixed cameras (`venue`); the spec's `cameras` gives each one's field
  of view and pose at the start.
- Proprioception: each row has, in the spec's `proprio_layout` order: the 27 joint positions (`*_pos`, rad), their
  velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in force (`*_target`,
  rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from sensor; angular
  velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
  `holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms, 4
  joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`,
  `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the grippers: `jaw_opening_left`,
  `jaw_speed_left`, `jaw_force_left`, `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the
  pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both
  its jaws touch the same object. A real H1-2 has no sensor for its position in the venue, and neither do you: that is
  what the cameras are for.

### What the platform does
- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a few
  seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own H1-2 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks
  at about 0.6 m/s and its heading drifts (close the loop on the IMU); `vy` up to 0.5 and `wz` up to 1.57 rad/s. At a
  zero command it marks time on the spot and recovers from small disturbances, which `stand` does not. When the legs
  come to it from another mode it first blends them to the stance (0.3 s) and holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The G1's
  two other walking policies (FALCON, AGILE) are not offered for it: driven on this robot (joints matched by name) they
  keep it upright but do not walk it.
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`,
  evaluated at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit.
  `joints` uses the default gains (the spec's `robot_facts`) and zero `dq` and `tau`; `lowcmd` takes yours (kp up to
  1500 / 800 / 400 and kd up to 30 / 20 / 10 for legs / waist / arms). Nothing balances the robot in these modes but
  your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets; what
  bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to about
  1.15 times that speed, where the motor's torque has fallen to zero).
- **The left and right hands are the robot's own**: the H1-2's Inspire RH56DFX five-finger hand (6 self-locking linear
  drives for 12 joints: the thumb's rotation and flexion, one drive per finger with its two joints coupled). 6 drives
  per hand, with fingertip forces of 20 N per finger and 30 N for the thumb (twice the stock hand's); each drive is
  position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open).
  `grip_left` and `grip_right` are the closure commands: one value per hand from 0 (open) to 1 (closed), all of that
  hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip,
  turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide
  with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's
  position and torque (the spec file (`describe_robot`) lists the drives with their limits).
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

### Time
- Time moves only inside calls: `execute_trajectory` runs your rows and `observe(seconds=s)` holds the command in force
  for s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `observe()`
  with no seconds is free.

## Others
Rule book: FIBA Official Basketball Rules. The rules here:
- A machine on the left wing passes the ball to you; catch it on the fly with both hands and shoot. One attempt: no
  opponent, no rebound.
- From the pass until the shot is through, the ball may touch only your hands; after the release you may not touch it
  again.
- Travelling: caught with both feet on the floor, the first foot you lift makes the other your pivot foot, and no foot
  may come down again before the release; caught in the air, you may take at most 2 steps before it.
- The ring is rigid and the net does not slow the ball; a goal is the ball going down through the ring.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers; you may read anything in your container, the benchmark's source included. Do not look up a ready-made
  solution to this exact task, such as the benchmark's reference solutions; trials are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 5 (`reset_episode()`), each a new episode from the same starting state.
