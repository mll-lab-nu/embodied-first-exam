# embodied-olympics tennis-return — instance i00 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket held in your right hand back over the net so that it lands in the singles court on the far side, without letting go of the racket.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |
| `r.reset()` / `POST /reset` | `reset_episode()` |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: on the floor under the pelvis, +X the way the pelvis faces at
the start of the call, +Y left, +Z up (only the heading is sensed, from the pelvis IMU). Space `native` sends rows in
the robot's own action types exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Unitree H1-2 humanoid, 27 joints (legs 12, torso 1, arms 7 + 7), 1.78 m; Unitree's walking policy built
in; the H1-2's own Inspire five-finger hand (6 drives) on the right arm, a fist pad on the left): torso (torso: 1
joints); left (arm: 7 joints, gripper); right (arm: 7 joints, gripper); legs (legs: 12 joints). Cameras: `head_left`,
`head_right`, `venue`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `locomote(vx, vy, wz, duration_s, height?)`: walk with the robot's own controller (body-frame velocities), then stop;
  returns the displacement.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** Joint targets are absolute angles (rad); a target moves at most the joint's speed limit per 10
ms step. The arms (left, right) and the torso take joint targets through the `stand` action type: the platform holds the
legs in the standing stance with stiff gains and gravity support but no balance feedback, so a fast or hard arm swing
can tip the robot over; a move_robot call on these parts switches the legs back to `stand`. The legs part uses the
`joints` type (every joint at the default gains; nothing balances the robot in that mode). Legs and arm goals use
different action types: send them in separate move_robot calls, or send rows of any of the robot's action types with
execute_trajectory space native (stand, walk, joints, lowcmd; layouts and bounds in describe_robot). move_robot and
joint rows for the arms and the torso start from the last `stand` row sent through these tools (at the start of an
attempt: the start command), grips included; locomote and the legs part start from the joint targets in force and keep a
grip closed while that hand holds something (holding_* in proprio_now), open otherwise. On a fist pad a grip of 0.5 or
more closes it (it holds a grippable object within 3.5 cm of the palm). Between calls the robot is frozen: time passes
only inside calls. There is no end-effector pose command: describe_robot's spec_file (robot_facts) has each joint's
range, speed and torque limits, default gains and the stance. The robot senses no position: the state shows its heading
(the pelvis IMU's yaw) only, and locomote's displacement reports the turn (dyaw), while dx and dy stay 0: judge
distances from the cameras. Once an attempt is over, results carry the referee's call (outcome, stages_reached of
stages_total).

## The venue
You stand as the receiver: 2.75 m to the right of the court's centre line, your pelvis 0.5 m behind your baseline, facing the net (+x), which is 12.385 m ahead of you. Painted on the court, all 0.05 m wide and inside the measurements: the two baselines, the two singles sidelines, the two service lines, the centre service line between them and a 0.10 m centre mark on each baseline; there are no doubles lines. The far baseline is 23.77 m beyond yours. The server is a ball machine on a stand: the ball leaves its two wheels where a server strikes it, 2.7 m above the ground, 0.2 m behind the far baseline and 0.8 m to the server's right of the centre mark (your left of the centre line). The net gives a little when something meets it. The serve is flat, with a little topspin; it bounces in your right service box, the one between the centre line and the right sideline, and reaches your baseline about a second after it was struck. The racket's handle lies across your right palm near its butt, held by the closed fingers and thumb, the butt just beyond your little finger; the strings face the way your palm faces, and the racket points up, square to your forearm.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good return). Where this task departs from it:

- Rules 16-21 (the service): the server is a ball machine, not a player: a two-wheel machine on a stand behind the far baseline throws the serve from the server's strike point (2.7 m up) at about 3.0 s; there is no opponent, the attempt ends when your return lands
- Rule 4 (the racket held in the hand): the hand is the H1-2's own Inspire five-finger hand (six drives, fingertip forces 20 N, the thumb 30 N), closed by one command; the handle lies across the palm, and the racket is held by the fingers' contact and friction alone, as a hand holds it
- Rules 4 and 24 (the ball hit with the racket held in the hand; a thrown racket does not play the ball): "in the hand" is defined by contact: the racket's handle touches the hand's fingers and its thumb or palm; a break of up to 0.05 s (the jolt of an impact or a hard swing) is not a release
- Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at its first contact with the ground (a real ball's footprint is about 5 cm across)
- Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts less than 0.05 s apart are one hit, a later one is a second hit, and a contact longer than 0.05 s is a carry
- Rule 1 (the net): the net is 4 panels a side, each a 2 cm thick plate that gives way across the net on a spring and a damper (the stiffness of a cable at 2000.0 N between the posts, an estimate: the rule sets the heights, not the tension; the net 6.0 kg in all) instead of a mesh of cord; each moves as one plate (a real net's mesh gives locally), and a fast ball that meets it comes back at about a tenth of its speed
- wind and weather: none; the air is still (sea level, 15 C)

The court is the ITF singles court: 23.77 m long and 8.23 m wide, measured to the outside of the lines, with a service line 6.4 m from the net on each side. The net stands across the middle, 0.914 m high at its centre and rising in a straight line to 1.07 m at the posts, which stand 0.914 m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift). The racket is a separate body, 0.685 m long and 0.3 kg, balanced 0.33 m from the butt, with a strung surface 0.33 m by 0.25 m and an octagonal handle 0.0335 m across its flats and 0.19 m long; at the start its handle is closed in your right hand (a five-finger hand), which holds it by contact and friction only: it can slip, turn in the hand and fall. The racket is in your hand while its handle touches the hand's fingers and its thumb or palm; it has left your hand when for more than 0.05 s it has not. About 3.0 s after the start a ball machine behind the far baseline serves the ball at 30.0 m/s into your right service box; it is served when it has left the machine's wheels. In order: the ball bounces once on your side; the racket, in your hand, hits it (the strings, the frame or any other part of the racket counts); its centre passes the net's plane from your side to the far side, above the net's top edge or outside a post (it may touch the net or a post on the way); and its first contact with the ground after that is inside the far half of the singles court, the lines included (the point under the ball's centre decides; ground contacts less than 0.02 s apart are one bounce): that is the success. You fail if the racket leaves your hand at any time (dropped, thrown or slipped out of the hand), if the racket touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball touches any part of you (the hand included) at any time after the serve, if the racket touches the ball a second time (contacts less than 0.05 s apart are one hit) or stays on it longer than 0.05 s, if the ball passes the net's plane between the posts below the net's top edge, if any part of you or the racket touches the net or a post, or the ground beyond the net's plane, if you or the racket touch the ball before it is served, if you fall, or after 10 s. A fall is: your pelvis lower than 0.35 m above the ground, or any part of you other than your feet touching the ground; the racket may touch the ground on your side as long as it stays in your hand.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**bounce → racket → over the net → in**. An attempt (an episode) ends at the success, at the first rule violation, or after 10 s
(1000 control steps) of robot time.

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
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (1000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) (grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward (grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_right`: the hand's closure command, 0 (open) to 1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The right hand is closed on `racket` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

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
| 13 | `left_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | 0 |
| 14 | `left_shoulder_roll` | [-0.38, 3.4] | 9 | 60 | 300 | 6 | 0 |
| 15 | `left_shoulder_yaw` | [-2.66, 3.01] | 20 | 60 | 200 | 4 | 0 |
| 16 | `left_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0 |
| 17 | `left_elbow_roll` | [-3.01, 2.75] | 31.4 | 60 | 80 | 1.5 | 0 |
| 18 | `left_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 19 | `left_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 0 |
| 20 | `right_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | 0 |
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 60 | 300 | 6 | 0 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 60 | 200 | 4 | 0 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0 |
| 24 | `right_elbow_roll` | [-2.75, 3.01] | 31.4 | 60 | 80 | 1.5 | 0 |
| 25 | `right_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 26 | `right_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 0 |

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
- **The right hand is the robot's own**: the H1-2's Inspire RH56DFX five-finger hand (6 self-locking linear drives for 12 joints: the thumb's rotation and flexion, one drive per finger with its two joints coupled; Unitree's H1-2 kinematics) with H2-class fingertip forces: 20 N per finger and 30 N the thumb, 2 x the RH56DFX's 10 / 15 N (Unitree's H2 Plus offers 20 N Sharpa Wave hands; Inspire's RH56E2 gives 28 / 30 N). 6 drives per hand; fingertip forces 20 N, 30 N (the thumb the largest); each drive is position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open). `grip_right` is the closure command: one value per hand from 0 (open) to 1 (closed), all of that hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip, turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's position and torque (`spec()` / `s.hold()` list the drives with their limits).
- **The left hand** has no working fingers here; it carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm). Nothing in this task is grippable: `grip_left` has no effect.
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
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the gripper: `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A
real H1-2 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
