# Embodied Olympics · clean and jerk (standard-mcp-shell)

## Task
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). Clean and jerk the barbell: lift it from its blocks to your shoulders, then to locked arms overhead, and hold
it there motionless until the down signal.

You stand upright in the middle of the platform, facing +x, your soles 0.1 m above the floor, in the rest pose (upper
arms down, forearms forward). The barbell lies across your front, parallel to your shoulders and centred on you, its
sleeves on two blocks (0.30 m along x, 0.20 m along y, 0.35 m high, centred 0.8 m to either side of you): its axis is
0.2 m ahead of your pelvis and 0.375 m above the platform, just beyond your toes (they reach 0.164 m ahead of your
pelvis). Your shoulder joints are 1.46 m above the platform when you stand, 0.30 m apart; the centre of your head is at
1.70 m, its top at 1.79 m; your knee joints are at 0.48 m. In the `stand` action's stance your knees are bent by about
21 degrees, and your elbows are at a right angle in the rest pose: neither is extended. Your elbow joints have no stop
at the straight arm (they bend both ways from it). Both hands are open (grip values 0): a grip value is that hand's
closure command (0 open, the fingers straight; 1 every finger and the thumb closing; a finger stops on what it touches).
The barbell is a free body: `held` in your state says which hand grasps it with its fingers and its thumb or palm. The
platform's edges are 2 m away in every direction.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.

The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the
service's own client, as if it were real hardware.

## Goal
Success: you lift the barbell from its blocks in both hands to your shoulders, then to locked arms overhead, and hold it
there motionless until the down signal, which comes after two seconds of holding.

The referee in the service judges these stages, in order: **lift-off → clean → overhead → down signal**. An attempt (an
episode) ends at the success, at the first foul or after 60 s of robot time, and a success ends the trial at once.
Ending your session ends the run, so do not stop early: while you have attempts left, the run can still pass.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`. Keep your scripts and a `NOTES.md` of at most 20 lines in `/app/output/` (your approach, what
failed, what you downloaded or installed): save them early and keep them current.

Real-robot rules:
- Attempts: 5 resets, each a new attempt from the same start (the first attempt starts when the service comes up); only
  your last attempt is graded.
- No privileged state: you get what the robot's own sensors give (its head cameras, joint encoders, motor torques and
  IMUs) and the venue's fixed cameras; not where you or any object is, not the referee's state. Once an attempt is over,
  every reply carries the referee's call: the outcome (`"success"` or the rule that ended it) and how many of the stages
  it reached.
- Write your own controller; public tools, robot models and pretrained controllers are allowed, a ready-made solution to
  this task is not.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

The attempt fails at once if:
- the bar leaves its blocks while fewer than two hands hold it
- once the bar has passed knee height, a hand lets go, or the barbell touches the platform or a block before the down
  signal
- you take the bar overhead in one movement (a snatch) instead of stopping at your shoulders
- anything but your feet touches the platform, any part of you touches a block, or you or the barbell touch the floor
  beside the platform

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: on the floor under the pelvis, +X the way the pelvis faces at the start of the call, +Y left, +Z up
(only the heading is sensed, from the pelvis IMU); metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed.
Parts: torso (torso: 1 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose, gripper); right (arm: 7
joints, no end-effector pose, gripper); legs (legs: 12 joints, no end-effector pose). Cameras: `head_left`,
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
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

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

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`) is your whole interface to the robot. Its docstring is the full
reference (`python -c "import rcb_client; help(rcb_client)"`); its examples use another benchmark's names: for this task
`r.spec()` is authoritative.

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (6000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

One call returns at most 3000 images (`max_frames_per_call`).

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Rendering is most of a
call's cost: a controller's call should ask for no video (`video="none"`, `cameras=["head_left"]` or fewer) and read
`res.proprio`. With `interpolate="linear"` (the default) each control step's command is a straight line from the command
in force to the row; `"hold"` applies the row as it is.

```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 20) rows of the `walk` type
```

### Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds:
`walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are
clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot
stands in `stand` mode with the arms at rest: the `stand` row `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` (the
waist and arms at their start angles, both grips open) keeps it there.

Joint order everywhere (Unitree's SDK order): `left_hip_yaw`, `left_hip_pitch`, `left_hip_roll`, `left_knee`,
`left_ankle_pitch`, `left_ankle_roll`, `right_hip_yaw`, `right_hip_pitch`, `right_hip_roll`, `right_knee`,
`right_ankle_pitch`, `right_ankle_roll`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`,
`left_elbow_pitch`, `left_elbow_roll`, `left_wrist_pitch`, `left_wrist_yaw`, `right_shoulder_pitch`,
`right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow_pitch`, `right_elbow_roll`, `right_wrist_pitch`,
`right_wrist_yaw`. Each joint's range, speed and torque limits, default gains and start angle are in the spec's
`robot_facts`.

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
  position and torque (`r.spec()` lists the drives with their limits).
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

### Time
- Time moves only inside calls: `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for s
  seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `r.get_obs()` with no
  seconds is free.

## Others
Rule book: IWF Technical and Competition Rules & Regulations. The rules here:
- One clean and jerk from blocks: a 5 kg technique bar rests on two lifting blocks; your hands start open.
- The clean: bring the bar to your shoulders, standing under it, and hold it there.
- The jerk: then drive it overhead and finish with arms and legs straight, both feet on the platform and in line, the
  bar overhead and you still under it.
- Only your feet may touch the platform, and you may not leave it. The whole attempt has 60 s.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included. Do not look up a ready-made solution to this exact task, such as the benchmark's reference solutions; trials
  are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 5 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
