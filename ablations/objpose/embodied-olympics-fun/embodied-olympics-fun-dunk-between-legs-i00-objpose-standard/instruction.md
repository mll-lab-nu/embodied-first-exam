# Embodied Olympics · dunk between the legs (standard)

## Task
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). From the top of the key, with the basketball held in your two hands, dribble it, make one of its bounces pass
between your legs, gather it in both hands, and with at most two steps dunk it: force it down through the ring from
above with your hands on it, then land on your feet.

A FIBA court. You stand at the top of the key facing the basket (+x): the point under the ring's centre is 4.425 m ahead
of your pelvis, the backboard's face 0.375 m beyond it, the end line's inner edge 1.575 m beyond that point. The
free-throw line (the top of the restricted area; its edge on your side 5.8 m from the end line) is 0.2 m ahead of your
pelvis, just in front of your toes; the side lines are 15.0 m apart, 7.5 m to each side of you. The ring's top edge is
2.39 m above the floor. Painted on the floor: the boundary lines, the restricted area, the free-throw line and circle,
the three-point line, the no-charge semi-circle, the centre line and circle. The ball is held between your two hands in
front of your chest, its centre 1.13 m above the floor and 0.39 m ahead of your pelvis: the hands open (grip values 0,
the fingers straight), the palms on its two sides (on these hands it bears on the two thumbs, which lie a little proud
of the palms), and the arms pressing the palms in (the start command's shoulder roll and yaw are a little further in
than the arms stand: the difference is the squeeze). A grip value is that hand's closure command (0 open, 1 every finger
and thumb joint closing towards its closed angle; a finger stops on what it touches).

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.

The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: from the top of the key you dribble, bounce the ball once between your legs, gather it in both hands and, with
at most two steps, dunk it down through the ring from above with your hands on it, then land on your feet.

The referee in the service judges these stages, in order: **dribble → between the legs → gather → dunk → stand**. An
attempt (an episode) ends at the success, at the first foul or after 40 s of robot time, and a success ends the trial at
once. Ending your session ends the run, so do not stop early: while you have attempts left, the run can still pass.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`. Keep your scripts and a `NOTES.md` of at most 20 lines in `/app/output/` (your approach, what
failed, what you downloaded or installed): save them early and keep them current.

Real-robot rules:
- Attempts: 5 resets, each a new attempt from the same start (the first attempt starts when the service comes up); only
  your last attempt is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; public tools, robot models and pretrained controllers are allowed, a ready-made solution to
  this task is not.
- Once an attempt is over, every reply carries the referee's call: the outcome (`"success"` or the rule that ended it)
  and how many of the stages it reached.

The attempt fails at once if:
- you travel, or you hang on the ring
- the ball touches the floor while in your hands before the dribble, or goes through the ring before it
- during the dribble a hand touches the ball twice without a bounce in between or holds it too long, the ball touches
  any part of you but a hand, or it gets too far away from you
- you gather the ball before a bounce between your legs
- after the gather the ball leaves your hands before it is in the ring, or touches the floor
- the ball goes through the ring without your hands on it from above (a shot, a tip or a drop), or comes up through it
  from below
- the ball or any part of you touches the floor on or outside the end line or a side line
- you fall: anything but your feet touches the floor, or your hips sink close to it

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`) is your whole interface to the robot. Its docstring is the full
reference (`python -c "import rcb_client; help(rcb_client)"`); its examples use another benchmark's names: for this task
`r.spec()` is authoritative.

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (4000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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
clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot is in
`stand` mode, but not with the arms at rest (the venue text says how it starts). The `stand` row that keeps the start as
it is:
`[0, -0.43, 0.2529, -1.1318, 0.4546, 0.2074, -0.44, 1.24, -0.4301, -0.2529, 1.1321, 0.4546, -0.2073, -0.44, -1.24, 0, 0]`
(`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other
angles or grips moves the arms or lets go.

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

### This run: privileged state queries
This run lets you query the simulator's state.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The kinds are
  `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`, `articulation` (a door,
  a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas region). The list is fixed for
  the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the current
  values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox` [[min x,
    y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the task
  is done.

## Others
Rule book: FIBA Official Basketball Rules. The rules here:
- A between-the-legs dunk at a lowered basket (the ring 2.39 m high): dribble, pass the ball between your legs, then
  dunk it.
- During the dribble only your hands may touch the ball, it may not come to rest in a hand, and you keep it within 2 m
  of you.
- Travelling: once the dribble ends you may take at most 2 steps before the dunk.
- The dunk: force the ball down through the ring with both hands on it, or one hand on top of it; the ball may not come
  up through the ring first.
- You may touch the basket for at most 0.3 s in all. After the dunk let go of the ball and stand on your feet for 1 s.

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
