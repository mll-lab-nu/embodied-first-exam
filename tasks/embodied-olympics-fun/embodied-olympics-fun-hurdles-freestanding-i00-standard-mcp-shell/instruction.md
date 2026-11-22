# embodied-olympics hurdles-freestanding — instance i00 — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Run the 50 m hurdles over four free-standing hurdles: go over each one in your lane, never beside it, under its top, or after pushing it away, leave at least one of them standing, and bring your torso to the finish line.

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
in; fist pads on both wrists): torso (torso: 1 joints); left (arm: 7 joints, gripper); right (arm: 7 joints, gripper);
legs (legs: 12 joints). Cameras: `head_left`, `head_right`, `venue`, `first_hurdle`.

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
You stand in your lane facing the finish (+x), the front ends of your feet 0.02 m behind the start line, your pelvis 0.23 m behind it. The lane lines are white on a red track; the hurdles' top bars are white with black stripes, their bases and counterweights grey on the track, reaching 0.7 m towards you along the lane's edges; two white posts stand beside the finish line. In your rest pose your forearms point forward at about the height of a hurdle's top.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** World Athletics Competition and Technical Rules, 2024 edition: TR 22 (22.1-22.3 distances and heights: the men's hurdle 1.067 m high, 13.72 m to the first, 9.14 m between; at the indoor distance of 50 m that is four hurdles and 8.86 m from the last to the finish; 22.4-22.5 the hurdle: metal with a non-metallic top bar, two bases and two uprights at the extreme end of each base supporting a rectangular frame reinforced by a cross bar, 1.18 to 1.20 m wide, a top bar 70 mm high and 10 to 25 mm thick, a base at most 0.70 m long, at least 10 kg, counterweights set so that a horizontal force of 3.6 to 4.0 kg at the centre of the top bar's top edge topples it; placed with the feet towards the approaching athlete; 22.6 each hurdle is gone over in the athlete's own lane; 22.6.1 a foot or leg beside the hurdle below the plane of its top; 22.6.2 knocking down or displacing a hurdle by hand or body; 22.7 knocking hurdles down otherwise is no offence), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish). Where this task departs from it:

- TR 16 (the start): no starter's commands, no blocks and no reaction time: the robot stands with the front ends of its feet 0.02 m behind the start line and the clock runs from t = 0
- TR 22.6 ('goes over each hurdle') is judged geometrically at the hurdle's standing pose on its mark, wherever the hurdle is now: the pelvis must pass above the height of the hurdle's top, each foot (its ankle joint) above the lower edge of the top bar, all three between the bar's ends, through the plane where the top bar stood, all three in one flight (from the first crossing to the last the robot touches nothing but that hurdle's top bar: the rule book's clearance is a stride in the air, and a leg swung over from the ground or a step over a hurdle that lies on the track is not one); a hurdle that has fallen, or has been pushed on or out of the lane, does not lower or move what is to be gone over; going over it on the hurdle (climbing) is judged by contact: a hurdle not yet gone over that still stands may not push the robot upwards by more than 100.0 N for longer than 0.15 s, and at the instant the pelvis or a foot crosses its plane only the legs may touch it, on its top bar
- TR 22.6.2 (knocking down or displacing a hurdle by hand, body or the upper side of the lead leg) and TR 22.7: intent and the side of the leg cannot be judged, so the cause of a hurdle's displacement is judged from contacts: a hurdle that leaves its standing pose (a point of its top bar more than 0.1 m from where it stood) within 0.5 s of a touch by a hand, an arm, the trunk or the pelvis is a failure if that touch was the robot's latest on it or came within 0.1 s; the legs may knock it down, on its top bar, during the clearance (while the robot touches nothing but that hurdle's top bar, or its pelvis is over the hurdle's plane); any other displacement before the hurdle is gone over (pushed, kicked or shoved along the track first, from the ground) is a failure: the athlete did not go over that hurdle as it stood
- TR 22.6 / 22.7 (knocking hurdles down with the legs is no offence): stricter here in one way only: an attempt in which every hurdle is knocked down (each leaves its standing pose, a point of its top bar more than 0.1 m from where it stood) fails at the moment the last one does, so at least one hurdle is cleared cleanly (gone over and still standing on its mark at the finish); a race that only knocks the hurdles over is not judged a hurdle clearance for a robot that cannot be watched for intent
- TR 17.3 (lanes): the lane is judged by the pelvis (its centre more than half a lane width from the lane's centre line); TR 22.6.1 is judged on the centres of the legs' collision bodies within 0.1 m of the hurdle's plane
- TR 17 (a fallen athlete): a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the race (did not finish)
- TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches the finish line's plane, interpolated between 1 ms physics steps (the H1-2's trunk and head are one link, so its torso includes the head); no wind; the robot alone on a straight of three lanes
- TR 22.4-22.5 (the hurdle): a rigid body (no deflection of the top bar); the rule book does not give the friction of a hurdle on the track: 0.6 (rubber feet on a polyurethane track); the counterweights are set once for the toppling force 3.8 kg; the distance is the indoor 50 m with its four hurdles, on an outdoor straight, not the 110 m; the time limit, 140 s, is this benchmark's (FAMILIES.md)

World Athletics rules for the hurdles, at the indoor distance of 50 m. The lane runs along +x, 1.22 m wide, centred on y = 0; the start line (0.05 m wide) has its far edge at x = 0, the finish line is x = 50.0 m. 4 hurdles stand across the lane, the face of the first one's top bar 13.72 m from the start line and one every 9.14 m after it (the last 8.86 m before the finish). A hurdle is a loose object standing on the track: 1.19 m wide and 1.067 m high, a top bar 0.07 m high, two uprights and a cross bar 0.35 m below its top; its two bases, 0.7 m long, lie on the track on your side of it, with counterweights on them; it weighs 10.9 kg and tips over forwards when a horizontal force of more than 3.8 kg pushes the middle of its top bar (tipped further than about 55 degrees it falls on by itself); it can slide on the track (friction 0.6), fall, bounce and lie where it comes to rest, and you can trip on it, but not climb on it. Each hurdle is judged where it stands at the start (its standing pose on its mark), wherever it is later. The clock starts at t = 0. You go over a hurdle when your pelvis and both your feet (the ankle joints) have crossed the plane of its top bar in its standing pose towards +x, each between the bar's two ends, the pelvis higher than the hurdle's top (1.067 m above the track) and each foot higher than the lower edge of its top bar (1.067 m less 0.07 m), whether the hurdle still stands there or not, and in one flight: from the first of these three crossings to the last, no part of you touches anything but that hurdle's top bar; a pelvis or a foot that comes back over the plane has not crossed it and must cross it again. The hurdles are gone over in order. A hurdle leaves its standing pose when a point of its top bar is more than 0.1 m from where it stood. Knocking a hurdle down with your legs is allowed when a leg strikes its top bar during the clearance: while you touch nothing else but that hurdle's top bar (in the air) or once your pelvis is over the hurdle's plane; a hurdle tipped more than 60.0 degrees is counted as down, without a fault. Where a hurdle comes to rest after that does not matter. But at least one hurdle must be cleared cleanly: if every hurdle has left its standing pose (knocked, also legally), you fail at the moment the last one does. You finish at the moment the leading point of your torso (the trunk and head hull; not the arms, legs or feet) reaches the finish line, with all hurdles gone over. You succeed with a finish within 140 s of robot time. A fall does not end the race: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail if your pelvis or a foot crosses the next hurdle's plane beside the hurdle, or lower than said above (going under its top); if between the first and the last of these crossings you touch the track or anything else but its top bar (stepping over it); if a part of one of your legs is beside the next hurdle (beyond the bar's ends, within 0.1 m of its plane) lower than the hurdle's top; if a hurdle leaves its standing pose within 0.5 s of being touched by a hand, an arm, your trunk or your pelvis, that touch being your latest on it or within 0.1 s before (knocked by hand or body; also one you have gone over); if you climb on a hurdle you have not yet gone over while it stands (tipped less than 60.0 degrees): it pushes you upwards by more than 100.0 N for longer than 0.15 s, or anything of you but a leg on its top bar touches it at the instant your pelvis or a foot crosses its plane; if a hurdle you have not yet gone over leaves its standing pose in any other way than the legal knock above (pushed, kicked or shoved along the track before you went over it); if your pelvis is more than half the lane's width from y = 0; if your torso reaches the finish line before every hurdle is gone over; if you knock down every hurdle; when down for 10.0 s; or after 140 s.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**hurdle 1 → hurdle 2 → hurdle 3 → hurdle 4 → finish**. An attempt (an episode) ends at the success, at the first rule violation, or after 140 s
(14000 control steps) of robot time.

## Real-robot rules
- **Attempts.** The first episode starts when the service comes up. `r.reset()` abandons the running attempt (or
  follows one that has ended) and starts a new one from the same start; `spec()["budget"]["reset"]` says how many
  resets you have (5 here). **Only your last attempt is graded**, and a success ends the trial at once.
- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for
  s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `get_obs()` with
  no seconds is free.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`, `first_hurdle`; `spec()["cameras"]` says
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
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (14000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

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
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm). Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
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
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. A
real H1-2 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
