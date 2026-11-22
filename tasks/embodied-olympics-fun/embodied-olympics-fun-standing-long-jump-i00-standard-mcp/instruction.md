# Embodied Olympics · standing long jump (standard-mcp)

## Task
You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on
MuJoCo). Do a standing long jump: from a standstill behind the take-off line, take off from both feet without a step,
land on your feet at least your own height beyond the line, and stand.

You stand facing +x with your feet side by side, their front ends 0.05 m behind the take-off line (white); your pelvis
is 0.164 m behind the line. The floor is level and firm; a yellow line is painted across it at the qualifying mark.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.

The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: from a standstill behind the take-off line you jump from both feet without a step, land on your feet at least
your own height (1.32 m) beyond the line, and then stand steady for a second (you may step after the landing).

The referee in the service judges these stages, in order: **take-off → landing → stand**. An attempt (an episode) ends
at the success, at the first foul or after 20 s of robot time, and a success ends the trial at once. Ending your session
ends the run, so do not stop early: while you have attempts left, the run can still pass.

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
- a foot is on or over the line, you step or shuffle before the take-off, or one foot leaves the ground before the other
- the flight is not a jump, or the landing is not on your feet
- the jump is short of 1.32 m
- you fall: anything but your feet touches the floor, or your hips sink close to it

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: on the floor under the pelvis, +X the way the pelvis faces at the start of the call, +Y
left, +Z up (only the heading is sensed, from the pelvis IMU); metres, radians, quaternions `wxyz`, gripper 0 open .. 1
closed. Parts: torso (torso: 3 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose, gripper); right
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
arms (left, right) and the waist (torso part) take joint targets through the `stand` action type: the platform holds the
legs in the standing stance with stiff gains and gravity support but no balance feedback, so a fast or hard arm swing
can tip the robot over; a move_robot call on these parts switches the legs back to `stand`. The legs part uses the
`joints` type (every joint at the default gains; nothing balances the robot in that mode). Legs and arm goals use
different action types: send them in separate move_robot calls, or send rows of any of the robot's action types with
execute_trajectory space native (stand, walk, run, run_arms, joints, lowcmd, walk_falcon, walk_agile; layouts and bounds
in describe_robot). move_robot and joint rows for the arms and the waist (torso part) start from the last `stand` row
sent through these tools (at the start of an attempt: the start command), grips included; locomote and the legs part
start from the joint targets in force and keep a grip closed while that hand holds something (holding_* in proprio_now),
open otherwise. On a fist pad a grip of 0.5 or more closes it (it holds a grippable object within 3.5 cm of the palm).
From walk_falcon or walk_agile, give `walk` a zero command for about 2 s before `stand` (straight to `stand` usually
ends in a fall); locomote ends each call with 1 s of zero command. Between calls the robot is frozen: time passes only
inside calls. There is no end-effector pose command: describe_robot's spec_file (robot_facts) has each joint's range,
speed and torque limits, default gains and the stance. The robot senses no position: the state shows its heading (the
pelvis IMU's yaw) only, and locomote's displacement reports the turn (dyaw), while dx and dy stay 0: judge distances
from the cameras. Once an attempt is over, results carry the referee's call (outcome, stages_reached of stages_total).

### Observations
- Cameras: the robot's two head cameras `head_left` and `head_right` (RGB 270 × 480, a stereo pair 5 cm apart, tilted
  20° down; depth on `head_left`) and the venue's fixed cameras (`venue`); the spec's `cameras` gives each one's field
  of view and pose at the start.
- Proprioception: each row has, in the spec's `proprio_layout` order: the 29 joint positions (`*_pos`, rad), their
  velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in force (`*_target`,
  rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from sensor; angular
  velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
  `holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms, 4
  joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`,
  `cmd_wz`) and `time_s`, the attempt's time. A real G1 has no sensor for its position in the venue, and neither do you:
  that is what the cameras are for.

### What the platform does
- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a few
  seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own G1 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s; `vy` up to 0.5 and `wz` up to 1.57 rad/s; it follows with lag and barely moves in its first second. At
  a zero command it marks time on the spot (the pelvis sways and drifts a centimetre or two per second) and recovers
  from small disturbances, which `stand` does not. When the legs come to it from another mode it first blends them to
  the stance (0.3 s) and holds a zero command until the robot is steady (up to 2 s). It was trained with the arms at
  rest: moving the arms and the waist disturbs it.
- **`walk_falcon`** and **`walk_agile`** are two more walking policies for the G1's legs, with the same row as `walk`
  (you keep the waist and the arms): FALCON (trained with arm motions and forces on the hands) and AGILE's
  velocity-height policy (trained while the arms and the waist moved), the released weights run in numpy at 50 Hz on
  their own leg gains (kp 100 / 100 / 100 / 200 / 20 / 20 per leg). Both hold still and follow the command better than
  `walk` while the arms move or carry something; FALCON also adds a small correction to the wrists. FALCON zeroes speeds
  below 0.2 m/s and turns below 0.2 rad/s and stands with the pelvis at about 0.74 m; AGILE zeroes commands of norm
  below 0.1, stands lower (about 0.68 m) and barely turns on the spot below about 0.7 rad/s (walking at 0.2 m/s or more
  it turns as asked). Their command ranges are in the action table. A walker takes the legs at once, from where they are
  (its memory starts afresh); `walk`, the other walker and `run` take them from it the same way. Going from a walker
  straight to `stand` usually ends in a fall (`stand` holds Unitree's stance and does not balance): give `walk` a zero
  command for about 2 s first.
- **`run`** runs the platform's athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
  above that; the command changes at most 1.5 m/s per second), `|vy|` ≤ 0.12 m/s, `|wz|` ≤ 0.5 rad/s. `run_arms` gives
  you the arms while it keeps the legs and the waist; taking the arms away from its swing disturbs it. Switching to
  `stand`, `walk` or `joints` above about 0.6 m/s usually ends in a fall: slow down first (from 2.4 m/s that takes about
  2 s and 2.3 m).
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`,
  evaluated at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit.
  `joints` uses the default gains (the spec's `robot_facts`) and zero `dq` and `tau`; `lowcmd` takes yours (kp up to
  1000 / 500 / 400 and kd up to 20 / 15 / 10 for legs / waist / arms). Nothing balances the robot in these modes but
  your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets; what
  bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to about
  1.15 times that speed, where the motor's torque has fallen to zero).
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the 10
  cm along the forearm). Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
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
Rule book: the standing long jump of school and club fitness tests: the feet side by side behind the take-off line, a
two-foot take-off with no step or preliminary hop, a landing on the feet; the jump is measured from the take-off line to
the nearest point of contact at the landing. The rules here:
- The standing long jump: feet side by side behind the take-off line, a two-foot take-off with no step or preliminary
  hop; rising on your toes is allowed.
- No part of a foot may be on or over the line before the jump.
- The jump is measured from the line to your landing mark nearest to it; the mark to reach is 1.32 m.

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
