# embodied-olympics tennis-serve — instance i00 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Serve: from behind your baseline, release the tennis ball from your left hand, strike it with the racket held in your right hand before it reaches the ground, and send it over the net into the service box diagonally opposite.

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
in; the H1-2's own Inspire five-finger hands (6 drives) on both arms): torso (torso: 1 joints); left (arm: 7 joints,
gripper); right (arm: 7 joints, gripper); legs (legs: 12 joints). Cameras: `head_left`, `head_right`, `venue`.

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
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
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
You stand as the server: your pelvis 0.5 m behind your baseline and 1.0 m to the right of the centre mark, facing the net (+x), which is 12.385 m ahead of you. Painted on the court, all 0.05 m wide and inside the measurements: the two baselines, the two singles sidelines, the two service lines, the centre service line between them and a 0.10 m centre mark on each baseline; there are no doubles lines. Your target, the far service box on the left of the centre line, begins at the net and ends 6.4 m beyond it, and reaches from the centre service line 4.115 m to the left. The ball is held in your left hand; the spare ball rests in a cup on a thin stand, its centre 0.25 m ahead of your pelvis, 0.6 m to your left and 1.05 m above the ground. The racket's handle lies across your right palm near its butt, held by the closed fingers and thumb, the racket pointing along your forearm, its strings facing the way your palm faces.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and Appendix II (the racket), Rule 12 (a ball on a line), Rules 16-19 (the service, its order, the foot fault, the service fault), Rule 22 (the let), Rule 24 h and i (the ball touching the player; the ball touching the racket when the player does not hold it). Where this task departs from it:

- Rules 5-11, 20, 23-26 (the point): one first serve only, with no receiver; a fault ends the attempt as a failure (there is no second serve after a fault), a good serve ends it as the success
- Rule 22 (the let is replayed, as often as it happens): a let is replayed 1 time(s), with the spare ball that waits in a cup on a stand 0.6 m to your left; a further let ends the attempt as a failure
- Rule 16 ('stand at rest ... immediately before starting the service motion'): made measurable: both feet on the ground and neither moved more than 0.02 m during the 0.5 s before the ball leaves the hand; the service motion is the time from that release to the racket's strike
- Rule 18 a ('slight movements of the feet are permitted', no walking or running): made measurable: during the service motion no foot may touch the ground more than 0.3 m from where it stood at the release
- Rule 19 Case 1 (a toss that the server does not try to hit may be caught or let drop and tossed again): the intention cannot be judged: one toss per serve; a tossed ball that reaches the ground unstruck is a fault, and so is a tossed ball caught again (touching you for more than 0.05 s)
- Rule 16 (release 'by hand'): the ball is released when it has touched nothing at all for 0.1 s (a ball resting on a tee is not released), and the tossed ball may touch nothing but you and the racket; so that a ball struck out of the hand is not a serve, it must have touched nothing of you for 0.1 s when the racket strikes it
- Rule 16 ('hit the ball with the racket'): so that a ball thrown past the racket is not a serve, the hit must add speed: 0.05 s after its last contact with the racket the ball must be faster than it was when it reached the racket; and the ball may move at most 5.0 m/s when it reaches the racket (the speed of a ball that has fallen about 1.3 m: a toss, not a throw)
- the player's hands: the H1-2's own Inspire five-finger hands (six drives: four fingers, the thumb's flexion and rotation; fingertip forces 20 N, the thumb 30 N), closed by one command per hand; they hold the racket and the ball by contact and friction only
- Rule 24 i (the racket held): made measurable: the racket is held while its handle touches your right hand's fingers and its thumb or palm; it must not go unheld for more than 0.05 s at any time of the attempt
- Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at its first contact with the ground (a real ball's footprint is about 5 cm across)
- Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts less than 0.05 s apart are one hit, a later one is a second hit, and a contact longer than 0.05 s is a carry
- Rule 1 (the net): a net of cord hung from a steel cable, modelled as strips of mesh 0.5 m wide, each a chain of 3 rigid panels 2 cm thick hinged under the band, the band and cable a string of beads across the net under 1890 N of tension, held down at the centre by the strap; the strips are not joined to each other below the cable and the mesh does not stretch; a ball meets the twine with its own rule-book restitution (it cannot pass through the mesh)
- wind and weather: none; the air is still (sea level, 15 C)

The court is the ITF singles court: 23.77 m long and 8.23 m wide, measured to the outside of the lines, with a service line 6.4 m from the net on each side and a centre service line that divides the space between the net and each service line into two service boxes. The net stands across the middle, 0.914 m high at its centre and rising in a straight line to 1.07 m at the posts, which stand 0.914 m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift). Both your hands are five-finger hands that hold things only by contact and friction: the ball starts held in your left hand, the racket (0.685 m long, 0.30 kg, its balance 0.33 m from the butt, strung surface 0.33 m by 0.25 m, an octagonal handle 33.5 mm across) starts held by its handle in your right hand; either can slip or fall. The racket is held while its handle touches your right hand's fingers and its thumb or palm; it must never go unheld for more than 0.05 s, from the start to the end of the attempt. You serve from the right of the centre mark into the far service box on the left of the centre line. In order: (1) the toss: the ball is released when it has touched nothing at all for 0.1 s (a ball resting on something is not released; the racket touching the ball before the release is a fault); at the end of those 0.1 s you must stand at rest, both feet on the ground behind the baseline, between the extension of the centre mark and the extension of the right sideline, neither foot having left the ground or moved more than 0.02 m in the last 0.5 s (so not before 0.5 s after the start); (2) the strike: the racket hits the ball before it reaches the ground (any part of the racket counts: strings or frame), the ball having touched nothing of you for the last 0.1 s and moving at most 5.0 m/s when it reaches the racket (a toss, not a throw), and the hit speeds the ball up (0.05 s after its last contact with the racket it is faster than it was when it reached the racket); (3) the ball's centre passes the net's plane between the posts above the net's top edge; (4) its first contact with the ground is inside that service box, the lines included (the point under the ball's centre decides; ground contacts less than 0.02 s apart are one): that is the success. From the release to the strike your feet may not touch the baseline or the court, the ground beyond the sideline's extension or the centre mark's extension, nor the ground more than 0.3 m from where each stood at the release (a foot fault); after the strike you may step anywhere on your side. A serve that touches the net and still lands in the box is a let: it does not count, and you serve again, under the same rules, with the spare ball, which you take from its cup with your left hand (before a let you may not touch it); this happens at most 1 time(s), a further let fails. You fail on any fault: releasing the ball when not at rest in the server's position, a foot fault, the tossed ball touching you for more than 0.05 s (caught again: one toss per serve), touching anything but you and the racket (the spare ball, its cup or stand, the net), reaching the ground or passing the net unstruck, the racket striking the ball before it is clear of you, a ball that reaches the racket faster than 5.0 m/s, a hit that does not speed it up, the racket touching the struck ball again (contacts less than 0.05 s apart are one hit) or staying on it longer than 0.05 s, the served ball touching you (your hands included), a net post, the ground on your side or the ground outside the service box, or passing the net's plane anywhere but over the net. You also fail if the racket goes unheld (dropped, thrown, or slipped out of the hand), if any part of you or the racket touches the net or a post, if you touch the spare ball before a let, if you fall, or after 20 s. A fall is: your pelvis lower than 0.35 m above the ground, or any part of you other than your feet touching the ground; the racket may touch the ground.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**toss → strike → over the net → in**. An attempt (an episode) ends at the success, at the first rule violation, or after 20 s
(2000 control steps) of robot time.

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
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (2000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The left hand is closed on `ball` at the start (closure command 1): opening it lets go. The right hand is closed on `racket` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
