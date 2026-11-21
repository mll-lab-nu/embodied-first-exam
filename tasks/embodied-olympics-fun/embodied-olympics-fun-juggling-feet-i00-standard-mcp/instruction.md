# embodied-olympics juggling-feet — instance i00 — STANDARD MODE, MCP TOOLS ONLY (robot as a service)

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through the `efe-robot` tools. **Task:** Juggle the football with your feet: drop it from between your palms and keep it in the air for ten foot touches in a row, each one sending the ball up above your knees, without it touching the ground or any other part of you.

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You may write and run code to compute; every robot command and observation must
go through the efe-robot MCP tools; code must not contact the simulator. Each robot command or observation is a tool
call you make yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is
checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and pass its path
as `rows_file` to `execute_trajectory`. The robot service and its rules are as described in this text; where it names
calls of the Python client `rcb_client.py`, which is not installed for your code here, use the tool that does the same:

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

**This robot** (Unitree G1 humanoid, 29 joints (legs 12, waist 3, arms 7 + 7), 1.32 m; Unitree's walking policy and a
running policy built in; fist pads on both wrists): torso (torso: 3 joints); left (arm: 7 joints, gripper); right (arm:
7 joints, gripper); legs (legs: 12 joints). Cameras: `head_left`, `head_right`, `venue`.

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
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** Joint targets are absolute angles (rad); a target moves at most the joint's speed limit per 10
ms step. The arms (left, right) and the waist (torso part) take joint targets through the `stand` action type: the
platform holds the legs in the standing stance with stiff gains and gravity support but no balance feedback, so a fast
or hard arm swing can tip the robot over; a move_robot call on these parts switches the legs back to `stand`. The legs
part uses the `joints` type (every joint at the default gains; nothing balances the robot in that mode). Legs and arm
goals use different action types: send them in separate move_robot calls, or send rows of any of the robot's action
types with execute_trajectory space native (stand, walk, run, run_arms, joints, lowcmd, walk_falcon, walk_agile; layouts
and bounds in describe_robot). move_robot and joint rows for the arms and the waist (torso part) start from the last
`stand` row sent through these tools (at the start of an attempt: the start command), grips included; locomote and the
legs part start from the joint targets in force and keep a grip closed while that hand holds something (holding_* in
proprio_now), open otherwise. On a fist pad a grip of 0.5 or more closes it (it holds a grippable object within 3.5 cm
of the palm). From walk_falcon or walk_agile, give `walk` a zero command for about 2 s before `stand` (straight to
`stand` usually ends in a fall); locomote ends each call with 1 s of zero command. Between calls the robot is frozen:
time passes only inside calls. There is no end-effector pose command: describe_robot's spec_file (robot_facts) has each
joint's range, speed and torque limits, default gains and the stance. The robot senses no position: the state shows its
heading (the pelvis IMU's yaw) only, and locomote's displacement reports the turn (dyaw), while dx and dy stay 0: judge
distances from the cameras. Once an attempt is over, results carry the referee's call (outcome, stages_reached of
stages_total).

## The venue
You stand on level grass in the middle of a 5.0 m x 5.0 m grid marked by white lines, facing along one side. Your upper arms hang, your forearms point forward and are turned so that the palms face each other; the ball is pressed between them, its centre about 0.85 m above the ground and 0.33 m ahead of your pelvis. The start command keeps that squeeze (the joint table's start angles are where the arms stand with the ball between the palms; the command is a little further in: the difference is the squeeze).

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** Ontario Soccer, OPDL Player Technical Benchmark Exercises (2015): Ball Mastery, juggled on the instep (the exercise list's 'one attempt on each instep', the warm-up's 'instep right juggling' and 'instep left juggling'): the ball starts in the hands, the player works in a 5 m x 5 m grid and has 60 seconds, the maximum number of consecutive juggles is recorded, and the ground, another surface or stepping out of the grid stops the count; the test sets no pass mark, so the family's standard is 10 consecutive foot juggles (the first milestone of youth juggling ladders and the standard of the existing juggling family). IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g) and for handling (Law 12: the hand or the arm). Where this task departs from it:

- The test's either-instep attempts are one attempt here in which either foot may play, in any order.
- The foot is the robot's ankle-roll link, the shoe-like part below the ankle joint: its sole, its top (the instep and laces), its sides, toe and heel; the robot has no separate toes and no laces, so the whole part counts. The G1's collision hull of the lower leg is wider and deeper than its shin and covers the instep: a ball lying on the top of the foot touches it. A contact with the lower leg's hull therefore counts as the foot where its point lies over the foot (between 0.08 m behind and 0.15 m ahead of the ankle joint along the foot) and at most 0.12 m above the ankle joint (measured along the foot's up direction: where the ball's equator is when it lies on the instep, plus 1 cm); a contact higher up the leg is the shin, the knee or the thigh: another surface, which the test's count does not allow.
- A counter's eye is replaced by numbers: contacts less than 0.05 s apart are one touch, a touch may last at most 0.05 s (a juggle is a strike, the ball may not rest, be cushioned or be balanced on the foot; a real instep kick's contact lasts about 0.01 s, Nunome et al. 2006, J. Sports Sci. 24: 11-22, and the robot's strikes last 0.011-0.013 s), and a touch counts when the ball's centre has then risen at least 0.22 m (one ball diameter) above where it was when the touch began and the whole ball has risen above the robot's knee height (0.36 m above the ground standing), before anything touches it again.
- A juggle is a strike: so that a ball that merely bounces off a still foot is not juggling, a touch must send the ball off with at least 0.95 of the speed it arrived with (a still foot returns at most the ball's own restitution, 0.85, and a raised leg held by its motors about 0.55); a touch that does not is not counted, and is not a fault.
- The ball's contact with the foot keeps the ball's own restitution (0.85, from the rule book's drop test): the robot's foot is rigid, like the metal pendulum with which Andersen, Kristensen and Sorensen (Football Science 5: 45-50, 2008) measured 0.82, and the compliance of a human foot and ankle (whose kicks they and earlier studies measured at 0.45-0.65) is here the compliance of the robot's own joints: a raised leg held by its motors returns about 0.55 of the ball's speed.
- The ball starts pressed between the robot's two open palms in front of its hips (the robot has flat palm pads, no fingers and no grip): only the arms' squeeze and friction hold it, and it slips out when they press too little. The drop is the hands' own movement (the palms parting); a referee's eye for 'the ball has left the hand' is replaced by a number: the ball touches no part of the robot for 0.03 s, and the drop is the end of its last contact. Before the drop only the hands may touch the ball (a ball held against the body, an arm or a leg is not in the hand). The palm pads' contact with the ball is that of a ball on a human hand (a ball thrown at a still palm keeps 0.10 of its speed, as a volleyball dropped onto a supported, relaxed hand does: Ivanova, ISBS 2000); every other contact keeps the ball's rule-book rebound. No wind.

A size-5 football (0.22 m across, 0.43 kg, in air) starts pressed between your two open palms; you stand in the middle of a square grid 5.0 m on each side, marked on the grass. Your hands have no fingers and no grip (the grip columns of the action rows do nothing in this task): only the squeeze of your arms and friction hold the ball, and it slips out when they press too little. Until the drop only your hands (the palm pads and the wrists) may touch the ball. The drop: the ball has touched no part of you for 0.03 s; it is the end of the ball's last contact with a hand. A hand or an arm may still be in contact with the ball for 0.15 s after the drop (the ball leaving the hand); after that a hand or an arm on the ball is a handball. From the drop on, only your feet may touch the ball: a foot is the part below the ankle joint (sole, instep, sides, toe and heel); a contact with your lower leg also counts as the foot where it lies over the foot (from 0.08 m behind to 0.15 m ahead of the ankle joint along the foot) and no more than 0.12 m above the ankle joint (along the foot's up direction), because your leg's collision shape covers the instep; the leg above that (shin, knee, thigh), the trunk, the head and the arms are other surfaces. A touch is a contact of the ball with a foot (contacts less than 0.05 s apart are one touch). It counts when, before anything touches the ball again, the ball's centre has risen at least 0.22 m above the height it had when the touch began and the whole ball (its lowest point) has risen above 0.36 m, your knee height; and when the ball left the touch with at least 0.95 of the speed it had when the touch began (both taken at the height where the touch began): a ball that only bounces off a still foot leaves slower, and such a touch is not counted, and is not a fault. You succeed at the moment the tenth touch counts. You fail if the ball touches the ground (before the drop too), if a part of you other than the hands touches it before the drop, if a hand or an arm touches it later than 0.15 s after the drop, or at all while a foot touches it or before a foot's touch has counted or been judged a bounce, if any part of you other than a foot touches it, if both feet touch it at once (the ball trapped), if one touch lasts longer than 0.05 s (the ball resting, rolling or balanced on a foot), if the ball is touched again before a touch has counted or been judged a bounce, if a foot (its ankle) leaves the grid, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground; standing on one foot is not a fall), or after 60 s.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**touch 1 → touch 2 → touch 3 → touch 4 → touch 5 → touch 6 → touch 7 → touch 8 → touch 9 → touch 10**. An attempt (an episode) ends at the success, at the first rule violation, or after 60 s
(6000 control steps) of robot time.

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
  call).
- Wall clock: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same
  way, so do not stop early: while you have attempts left, the run can still pass.

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
Its docstring is the full reference (the client is not installed for your code: the `efe-robot` tools stand for it; it explains the protocol with another benchmark's example names: for this task `spec()` is
authoritative).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (6000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 22) rows of the `walk` type
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The `stand` row that keeps the start as it is: `[0, 0, 0, -0.0309, -0.0352, -0.0438, 0.2274, -1.5483, -0.0591, -0.1964, -0.0309, 0.0351, 0.0438, 0.2273, 1.5483, -0.0591, 0.1964, 0, 0]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains
(also in `spec()["robot_facts"]`):

| # | joint | range (rad) | speed (rad/s) | torque (N m) | kp | kd | at the start (rad) |
|---|---|---|---|---|---|---|---|
| 0 | `left_hip_pitch` | [-2.5307, 2.8798] | 32 | 88 | 700 | 12 | -0.1 |
| 1 | `left_hip_roll` | [-0.5236, 2.9671] | 20 | 139 | 700 | 12 | 0 |
| 2 | `left_hip_yaw` | [-2.7576, 2.7576] | 32 | 88 | 500 | 8 | 0 |
| 3 | `left_knee` | [-0.0873, 2.8798] | 20 | 139 | 900 | 15 | 0.3 |
| 4 | `left_ankle_pitch` | [-0.8727, 0.5236] | 37 | 50 | 300 | 6 | -0.2 |
| 5 | `left_ankle_roll` | [-0.2618, 0.2618] | 37 | 50 | 300 | 6 | 0 |
| 6 | `right_hip_pitch` | [-2.5307, 2.8798] | 32 | 88 | 700 | 12 | -0.1 |
| 7 | `right_hip_roll` | [-2.9671, 0.5236] | 20 | 139 | 700 | 12 | 0 |
| 8 | `right_hip_yaw` | [-2.7576, 2.7576] | 32 | 88 | 500 | 8 | 0 |
| 9 | `right_knee` | [-0.0873, 2.8798] | 20 | 139 | 900 | 15 | 0.3 |
| 10 | `right_ankle_pitch` | [-0.8727, 0.5236] | 37 | 50 | 300 | 6 | -0.2 |
| 11 | `right_ankle_roll` | [-0.2618, 0.2618] | 37 | 50 | 300 | 6 | 0 |
| 12 | `waist_yaw` | [-2.618, 2.618] | 32 | 88 | 400 | 10 | 0 |
| 13 | `waist_roll` | [-0.52, 0.52] | 37 | 50 | 400 | 10 | 0 |
| 14 | `waist_pitch` | [-0.52, 0.52] | 37 | 50 | 400 | 10 | 0 |
| 15 | `left_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | -0.0309 |
| 16 | `left_shoulder_roll` | [-1.5882, 2.2515] | 37 | 25 | 300 | 6 | -0.0352 |
| 17 | `left_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | -0.0438 |
| 18 | `left_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 0.2274 |
| 19 | `left_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | -1.5483 |
| 20 | `left_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | -0.0591 |
| 21 | `left_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | -0.1964 |
| 22 | `right_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | -0.0309 |
| 23 | `right_shoulder_roll` | [-2.2515, 1.5882] | 37 | 25 | 300 | 6 | 0.0351 |
| 24 | `right_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0.0438 |
| 25 | `right_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 0.2273 |
| 26 | `right_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 1.5483 |
| 27 | `right_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | -0.0591 |
| 28 | `right_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0.1964 |

What the platform does and does not do for you:

- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a
  few seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own G1 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s; `vy` up to 0.5 and `wz` up to 1.57 rad/s; it follows with lag and barely moves in its first second.
  At a zero command it marks time on the spot (the pelvis sways and drifts a centimetre or two per second) and
  recovers from small disturbances, which `stand` does not. When the legs come to it from another mode it first blends
  them to the stance (0.3 s) and holds a zero command until the robot is steady (up to 2 s). It was trained with the
  arms at rest: moving the arms and the waist disturbs it.
- **`walk_falcon`** and **`walk_agile`** are two more walking policies for the G1's legs, with the same row as `walk`
  (you keep the waist and the arms): FALCON (LeCAR-Lab, MIT; trained with arm motions and forces on the hands) and
  AGILE's velocity-height policy (NVIDIA WBC-AGILE, Apache-2.0; trained while the arms and the waist moved), the
  released weights run in numpy at 50 Hz on their own leg gains (kp 100 / 100 / 100 / 200 / 20 / 20 per leg). Both
  hold still and follow the command better than `walk` while the arms move or carry something; FALCON also adds a small
  correction to the wrists. FALCON zeroes speeds below 0.2 m/s and turns below 0.2 rad/s and stands with the pelvis at
  about 0.74 m; AGILE zeroes commands of norm below 0.1, stands lower (about 0.68 m) and barely turns on the spot below
  about 0.7 rad/s (walking at 0.2 m/s or more it turns as asked). Their command ranges are in the action table. A
  walker takes the legs at once, from where they are (its memory starts afresh); `walk`, the other walker and `run`
  take them from it the same way. Going from a walker straight to `stand` usually ends in a fall (`stand` holds
  Unitree's stance and does not balance): give `walk` a zero command for about 2 s first.
- **`run`** runs Embodied Olympics' athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
  above that; the command changes at most 1.5 m/s per second), `|vy|` ≤ 0.12 m/s, `|wz|` ≤ 0.5 rad/s. `run_arms` gives
  you the arms while it keeps the legs and the waist; taking the arms away from its swing disturbs it. Switching to
  `stand`, `walk` or `joints` above about 0.6 m/s usually ends in a fall: slow down first (from 2.4 m/s that takes
  about 2 s and 2.3 m).
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`, evaluated
  at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit. `joints`
  uses the default gains of the table and zero `dq` and `tau`; `lowcmd` takes yours (kp up to 1000 / 500 / 400 and kd up to
  20 / 15 / 10 for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets;
  what bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to
  about 1.15 times that speed, where the motor's torque has fallen to zero).
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm). Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the 29 joint positions
(`*_pos`, rad), their velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in
force (`*_target`, rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from
sensor; angular velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
`holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms,
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. A
real G1 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
