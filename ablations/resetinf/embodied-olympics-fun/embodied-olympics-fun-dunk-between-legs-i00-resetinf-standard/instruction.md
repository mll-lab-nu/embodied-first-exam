# embodied-olympics dunk-between-legs — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** From the top of the key, with the basketball held in your two hands, dribble it, make one of its bounces pass between your legs, gather it in both hands, and with at most two steps dunk it: force it down through the ring from above with your hands on it, then land on your feet.

## The venue
A FIBA court. You stand at the top of the key facing the basket (+x): the point under the ring's centre is 4.425 m ahead of your pelvis, the backboard's face 0.375 m beyond it, the end line's inner edge 1.575 m beyond that point. The free-throw line (the top of the restricted area; its edge on your side 5.8 m from the end line) is 0.2 m ahead of your pelvis, just in front of your toes; the side lines are 15.0 m apart, 7.5 m to each side of you. The ring's top edge is 2.39 m above the floor. Painted on the floor: the boundary lines, the restricted area, the free-throw line and circle, the three-point line, the no-charge semi-circle, the centre line and circle. The ball is held between your two hands in front of your chest, its centre 1.13 m above the floor and 0.39 m ahead of your pelvis: the hands open (grip values 0, the fingers straight), the palms on its two sides (on these hands it bears on the two thumbs, which lie a little proud of the palms), and the arms pressing the palms in (the start command's shoulder roll and yaw are a little further in than the arms stand: the difference is the squeeze). A grip value is that hand's closure command (0 open, 1 every finger and thumb joint closing towards its closed angle; a finger stops on what it touches).

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds a live ball), Art. 15 (a dunk: the ball forced downwards into the basket with one or both hands), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 23 (out of bounds), Art. 24 (dribbling: its start, its end, no second dribble), Art. 25 (travelling, 25.2.1.2: two steps upon completion of a dribble), Art. 26 (three seconds), Art. 36 (technical foul: hanging on the ring); FIBA Mini-Basketball Rules (the ring at 2.60 m). Where this task departs from it:

- Basketball Equipment (basket): the basket is lowered: the ring's top edge is 2.39 m above the floor, below FIBA Mini-Basketball's 2.60 m (FIBA's own ring: 3.05 m), set at the robot's measured own-motor reach (H1-2 with H2-class leg actuators), at the edge of the robot's reach, and the pass between the legs is the harder part; the full-size backboard keeps its size and its height relative to the ring (lower edge 2.24 m). The ball stays the size-7 ball.
- Art. 3 (equipment, the hands): the hands are the H1-2's own Inspire five-finger hands (six drives: four fingers, the thumb's flexion and rotation), closed by one command per hand; the ball is held by the hands' contact and friction alone (the open palms pressed on its sides by the arms) and slips or drops when they do not hold it. It is dribbled by pushing it with a hand (the palm and the fingers).
- Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a touch of one hand that lasts longer than 0.3 s. The dribble ends when both hands touch the ball at the same time (the gather); a dribble ended by a ball at rest in one hand ends the attempt (no dribble can be started again, Art. 24.2).
- Art. 13: during the dribble every touch of the ball by a part of you other than a hand is a violation; intent (an accidental touch of a leg is legal in the rule book) cannot be judged.
- The rule book has no 'between the legs': this task's definition (the leg gate: the triangle of your two feet and your crotch below your knees, crossed by the ball's centre during a bounce, no hand on it, the ball moving through it at 1.0 m/s or more, and the ball on the other side at the next touch) is this task's own requirement.
- Art. 15 defines a dunk only as forcing the ball downwards into the basket with one or both hands: here, at the moment its centre enters the ring, both hands are on the ball, or a hand is on it whose latest contact is at least 0.06 m above its centre (a hand pressing it from above).
- Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within 2.0 m (horizontally) of your pelvis while it is dribbled.
- Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside the ring and on to one ball diameter below it.
- Art. 26 (three seconds) is not applied: the attempt is a single action without opponents (as in the other basketball families, which start in or next to the restricted area).
- Art. 36: hanging on the ring is judged by time: the robot may touch the basket (ring, its plate, the backboard) for at most 0.3 s in all.
- The landing (on the feet, standing 1.0 s) is this task's own requirement; the rule book asks nothing of a player after a goal.

A FIBA court (15.0 m wide inside its side lines, lines 0.05 m wide); the official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 2.39 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.24 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands are five-finger hands: the ball starts held between them, the palms pressed on its sides and the hands open, and only the hands' contact and friction hold it; it can slip out. A hand is the palm, the fingers and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it. Starting the dribble: you stand still with the ball in your hands; the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor, and the pivot foot may not leave the floor before the ball has left your hands (a foot has left the floor when it has not touched it for 0.03 s). The ball may not touch the floor while it is in your hands. The dribble starts when the ball has left your hands and touched the floor. The dribble: you play the ball by touches of one hand at a time that push it to the floor: between two touches by your hands the ball must have touched the floor (the ball leaving your hands at the start counts as a touch); contacts of your hands less than 0.03 s apart are one touch; a touch of one hand may last at most 0.3 s (longer: the ball has come to rest in the hand); the ball may touch no part of you but your hands; its centre must stay within 2.0 m (horizontally) of your pelvis; there is no limit to your steps. Between the legs: the leg gate is the triangle whose corners are the soles of your two feet (each foot's sole point) and your crotch (the point midway between your two hip joints), wherever your legs are, up to the height of your lower knee joint, while the triangle's area is at least 0.02 m2 (a thinner one, with a sole on the line from the other sole to the crotch, is no gate). A bounce goes between your legs when, between two touches of your hands, the ball touches the floor, its centre passes through the leg gate from one side of the gate's plane to the other while no hand touches it, the ball itself (not you) moving through that plane in the direction of the pass at 1.0 m/s or more, this is the last time its centre passes the gate's plane before the next touch, and at that next touch the ball is on the other side of the plane from where it was at the touch before. At least one bounce of your dribble must go between your legs. The gather: the dribble ends when both your hands are on the ball at the same moment; it must end so, and only after a bounce between your legs. From then on the ball must stay in your hands until its centre has gone down into the ring, and it may not touch the floor (a second dribble). Travelling: after the gather you may take at most 2 steps with the ball in your hands. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row; a foot on the floor may not slide more than 0.2 m from where it stood or was put down; after that no foot may touch the floor again until the ball is through the ring. The dunk: the ball's centre goes down through the ring's plane inside the ring while both your hands are on the ball, or while a hand is on it whose latest contact with it is at least 0.06 m above the ball's centre (pressing it down from above), and on down to one ball diameter below the ring (in the hands, or let go once its centre is inside the ring). A ball whose centre comes up through the ring from below is a violation. Hanging on the ring: you may touch the basket (the ring, its plate, the backboard) with any part of you for at most 0.3 s in all. After the dunk let go of the ball (no hand on it) and stand: for 1.0 s without a break only your feet touch the ground, your torso is upright (the cosine of its tilt at least 0.94) and your pelvis moves slower than 0.35 m/s. Then you have succeeded. You fail if you travel; if the ball touches the floor while in your hands before the dribble, or goes through the ring before it; if during the dribble a hand touches the ball twice without the ball touching the floor in between, a touch of one hand lasts too long, the ball touches a part of you other than a hand, or the ball gets further from you than the control distance; if you gather the ball before a bounce between your legs; if after the gather the ball leaves your hands before its centre has entered the ring or touches the floor; if the ball goes through the ring after an entry at which neither both hands nor a hand from above were on it (a shot, a tip from below or the side, a drop); if, let go inside the ring, it touches the floor without having gone through; if the ball comes up through the ring from below; if the ball or any part of you touches the floor on or outside a boundary line (the end line or a side line); if you hang on the ring; if you fall at any time (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 40 s.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**dribble → between the legs → gather → dunk → stand**. An attempt (an episode) ends at the success, at the first rule violation, or after 40 s
(4000 control steps) of robot time.

## Real-robot rules
- **Attempts.** The first episode starts when the service comes up. `r.reset()` abandons the running attempt (or
  follows one that has ended) and starts a new one from the same start; `spec()["budget"]["reset"]` says how many
  resets you have (5 here). **Only your last attempt is graded**, and a success ends the trial at once.
- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for
  s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `get_obs()` with
  no seconds is free.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`; `spec()["cameras"]` says
  where each is mounted). Not where you or any object is, not the
  referee's state. Once an attempt is over, every response carries the referee's call: `meta["outcome"]`
  (`"success"` or the rule that ended it) and `meta["stages_reached"]` of `meta["stages_total"]`.
- There is nothing to hand in: the service records your last attempt and grades it as it ran live (the referee's
  call). Keep the script that drives the robot at `/app/output/gen.py` and a `NOTES.md` of at most 20 lines (your
  approach, what failed, what you downloaded or installed) for the record: save them early and keep them current.
- Wall clock: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same
  way, so do not stop early: while you have attempts left, the run can still pass.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; it explains the protocol with another benchmark's example names: for this task `spec()` is
authoritative).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (4000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Rendering is most of a
call's cost: a controller's call should ask for no video (`video="none"`, `cameras=["head_left"]` or fewer) and read
`res.proprio`. With `interpolate="linear"` (the default) each control step's command is a straight line from the
command in force to the row; `"hold"` applies the row as it is.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 20) rows of the `walk` type
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The `stand` row that keeps the start as it is: `[0, -0.43, 0.2529, -1.1318, 0.4546, 0.2074, -0.44, 1.24, -0.4301, -0.2529, 1.1321, 0.4546, -0.2073, -0.44, -1.24, 0, 0]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains
(also in `spec()["robot_facts"]`):

| # | joint | range (rad) | speed (rad/s) | torque (N m) | kp | kd | at the start (rad) |
|---|---|---|---|---|---|---|---|
| 0 | `left_hip_yaw` | [-0.43, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 1 | `left_hip_pitch` | [-3.14, 2.5] | 23 | 360 | 800 | 10 | -0.16 |
| 2 | `left_hip_roll` | [-0.43, 3.14] | 23 | 360 | 800 | 10 | 0 |
| 3 | `left_knee` | [-0.26, 2.05] | 14 | 360 | 1200 | 16 | 0.36 |
| 4 | `left_ankle_pitch` | [-0.8973, 0.5236] | 9 | 66.88 | 160 | 8 | -0.2 |
| 5 | `left_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 6 | `right_hip_yaw` | [-0.43, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 7 | `right_hip_pitch` | [-3.14, 2.5] | 23 | 360 | 800 | 10 | -0.16 |
| 8 | `right_hip_roll` | [-3.14, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 9 | `right_knee` | [-0.26, 2.05] | 14 | 360 | 1200 | 16 | 0.36 |
| 10 | `right_ankle_pitch` | [-0.8973, 0.5236] | 9 | 66.88 | 160 | 8 | -0.2 |
| 11 | `right_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 12 | `torso` | [-2.35, 2.35] | 23 | 200 | 600 | 15 | 0 |
| 13 | `left_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | -0.43 |
| 14 | `left_shoulder_roll` | [-0.38, 3.4] | 9 | 60 | 300 | 6 | 0.2529 |
| 15 | `left_shoulder_yaw` | [-2.66, 3.01] | 20 | 60 | 200 | 4 | -1.1318 |
| 16 | `left_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0.4546 |
| 17 | `left_elbow_roll` | [-3.01, 2.75] | 31.4 | 60 | 80 | 1.5 | 0.2074 |
| 18 | `left_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | -0.44 |
| 19 | `left_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 1.24 |
| 20 | `right_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | -0.4301 |
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 60 | 300 | 6 | -0.2529 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 60 | 200 | 4 | 1.1321 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0.4546 |
| 24 | `right_elbow_roll` | [-2.75, 3.01] | 31.4 | 60 | 80 | 1.5 | -0.2073 |
| 25 | `right_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | -0.44 |
| 26 | `right_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | -1.24 |

What the platform does and does not do for you:

- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a
  few seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own H1-2 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s and its heading drifts (close the loop on the IMU); `vy` up to 0.5 and `wz` up to 1.57 rad/s. At a
  zero command it marks time on the spot and recovers from small disturbances, which `stand` does not. When the legs
  come to it from another mode it first blends them to the stance (0.3 s) and holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The
  G1's two other walking policies (FALCON, AGILE) are not offered for it: driven on this robot (joints matched by name)
  they keep it upright but do not walk it.
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`, evaluated
  at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit. `joints`
  uses the default gains of the table and zero `dq` and `tau`; `lowcmd` takes yours (kp up to 1500 / 800 / 400 and kd up to
  30 / 20 / 10 for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets;
  what bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to
  about 1.15 times that speed, where the motor's torque has fallen to zero).
- **The left and right hands are the robot's own**: the H1-2's Inspire RH56DFX five-finger hand (6 self-locking linear drives for 12 joints: the thumb's rotation and flexion, one drive per finger with its two joints coupled; Unitree's H1-2 kinematics) with H2-class fingertip forces: 20 N per finger and 30 N the thumb, 2 x the RH56DFX's 10 / 15 N (Unitree's H2 Plus offers 20 N Sharpa Wave hands; Inspire's RH56E2 gives 28 / 30 N). 6 drives per hand; fingertip forces 20 N, 30 N (the thumb the largest); each drive is position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open). `grip_left` and `grip_right` are the closure commands: one value per hand from 0 (open) to 1 (closed), all of that hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip, turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's position and torque (`spec()` / `s.hold()` list the drives with their limits).
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the 27 joint positions
(`*_pos`, rad), their velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in
force (`*_target`, rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from
sensor; angular velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
`holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms,
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the grippers: `jaw_opening_left`, `jaw_speed_left`, `jaw_force_left`, `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A
real H1-2 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## This run: unlimited resets, save and load

This run changes the reset budget and adds two calls. This section overrides anything above, and anything in `/spec`,
that says there is no reset, one episode only, or fewer resets.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON body
  such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state.
  The answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`,
  `loads` and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets.
  Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a
  load until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved
  state followed by what you did after the load. The success rule is checked again from your next command on. A
  success still ends the run: no reset, save or load after it.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
