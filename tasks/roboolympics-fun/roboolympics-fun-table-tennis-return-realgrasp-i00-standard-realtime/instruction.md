# roboolympics table-tennis-return-realgrasp — instance i00 — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 34 kg; the RoboOlympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, you reach it only through a
client, and like a real venue it does not wait for you: once an attempt is running, the robot, the ball and the venue
move while you think. **Task:** Return the service: after the table tennis ball has bounced once on your court, strike it with the paddle held in your right hand's gripper so that it touches the opponent's court, without letting go of the paddle.

**Slowdown: S = 1.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms of wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.

## The venue
You stand at your end of the table facing it (+x), on its centre line, your pelvis 0.5 m behind your end line; the net is 1.37 m beyond the end line and the server's end line 2.74 m. The ball waits at rest where the server strikes it: 3.288919 m ahead of your pelvis, -0.199863 m to your left (negative: to your right) and 0.899714 m above the floor, just behind the server's end line. The service is one of a library of legal robot services: they leave the server's racket at 2.2 to 4.5 m/s with up to 34 rad/s of spin and bounce on your court between 0.2 and 0.8 s after the strike; short services bounce a second time on your court if you do not strike them. The paddle's handle is closed in your right gripper along its two fingers, the butt just short of the gripper's body and the rest of the handle reaching beyond the fingertips; the blade's faces look the way the jaws close (your palm's side and the back of your hand), and the paddle points ahead along your forearm, the blade's centre about 0.24 m beyond your wrist.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** ITTF Handbook 2024, The Laws of Table Tennis: 2.1 (the table), 2.2 (the net assembly), 2.3 (the ball), 2.4 (the racket), 2.5 (definitions: struck, obstruction, racket hand, free hand), 2.6 (the service), 2.7 (the return), 2.10 (a point). Where this task departs from it:

- 2.6.1-2.6.3 (the service): there is no server and no toss: the ball waits at the server's strike point and is launched at 3.0 s with the position, velocity and spin it has at the strike of a legal service of RoboOlympics' serve library (a service a Franka arm made under its real limits; entry 221, the draw of this instance's seed, not chosen for being returnable), because the task is one return, not a match
- 2.1.3 (the table's bounce): the playing surface is Google DeepMind's system-identified table, on which a ball dropped from 30 cm rebounds 26 cm, not the Law's about 23 cm; it is the only identified model of the ball's bounce with spin there is
- 2.2 (the net): the net is a rigid wall 1 cm thick, 0.1525 m high, reaching 0.1525 m beyond each side line, without separate posts or a cord (DeepMind's model); a soft net is not simulated
- 2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick, 0.14 kg in all (legal: the Laws set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, hand-picked, not identified)
- 2.5.5 (the racket hand, the hand carrying the racket): the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws, at most 120 N); the handle lies along its jaws and the racket is held by their friction alone, as a hand holds it; "carrying" is defined by contact: the handle touches both of the gripper's jaws, and a break of up to 0.05 s is not a release; the racket may touch nothing of the player but the racket hand (the Laws do not forbid a second hand on the racket; here it would make the free hand a second racket hand)
- 2.10.1.7 (deliberately striking the ball twice): intent cannot be judged: every contact of the blade or the racket hand within 0.05 s of the first is the same strike, a later one is a second strike
- 2.10.1.8 (moving the playing surface): the table is fixed and this is not judged: a competition table weighs three times the robot and more, and the robot's push on it is limited by the grip of its own feet
- 2.5.8 and 2.10.1 (the ball touching the player): any touch of the ball by anything but the blade or the racket hand loses the point, also after the ball has bounced on the robot's court (stricter than the Laws, which then only require that the return be struck)

The table is the official one: 2.74 m long, 1.525 m wide, its playing surface 0.76 m above the floor, with a net 0.1525 m high across its middle that reaches 0.1525 m beyond each side line. Your court is the half of the playing surface on your side of the net, the opponent's court the other half; the top edges belong to the playing surface, the sides of the table top do not (a ball that touches the table with its centre below the level of the playing surface has hit the side). The ball is the official one (40 mm, 2.7 g) and flies in air: drag and the lift of its spin act on it. The racket is a separate body: a rigid square blade 0.15 m wide and 0.015 m thick on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick, 0.14 kg in all, the blade's centre 0.175 m from the butt. At the start its handle is closed in your right hand's two-finger gripper, which holds it by friction only: it can slip, turn in the gripper and fall. Your right hand (the gripper's jaws and body) is the racket hand, your left hand the free hand. The racket is in your hand while its handle touches both of the gripper's jaws; it has left your hand when for more than 0.05 s the handle has not touched both jaws. The service is struck 3.0 s after the start: a legal service, so the ball bounces first on the server's court, passes the net and bounces on your court. Then you must make a good return (Law 2.7): strike the ball, after that one bounce on your court, with the blade of the racket in your hand or with the racket hand below the wrist (the gripper), so that it touches the opponent's court, directly or after touching the net; it may pass over or around the net. You succeed at the moment the ball touches the opponent's court after your strike. All contacts of the blade or the racket hand with the ball within 0.05 s of the first are one strike. You fail if the racket leaves your hand at any time (dropped, thrown or slipped out of the gripper); if the racket touches any part of you other than the racket hand; if you or the racket touch the ball before the service, or before it has bounced on your court (obstruction); if the ball bounces a second time on your court before you strike it (ball contacts with the table less than 0.02 s apart are one bounce); if anything other than the blade or the racket hand touches the ball (the racket's handle, an arm, the body); if the blade or the racket hand touches the ball again later than 0.05 s after the first contact (struck twice, or carried); if after your strike the ball touches your own court, the side of the table or the floor before the opponent's court; if the ball touches the floor at any time; if any part of you or the racket touches the net; if the racket touches the floor; if your free hand touches the playing surface while the ball is in play (from the service on); if you fall; or after 8 s. Anything else of you, the racket included, may touch the table. A fall is your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**bounce → strike → opponent's court**. An attempt (an episode) ends at the success, at the first rule violation, or after 8 s
(800 control steps) of robot time.

## Real-robot rules
- **Time does not stop.** An attempt starts paused, on the frozen start, the robot holding its starting command. Its
  clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator runs at 100 Hz of robot
  time (S = 1), whether or not you send anything, until the attempt ends: the venue's timed events (the
  launch, the serve, the release) happen on that clock. Between your commands the robot executes what you planned,
  then holds the last command in force; nothing pauses for you, not your thinking, not your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds;
  the decisive moment of an attempt takes a fraction of one. Drive the robot with a program: a controller of your own
  (Python in your container, with numpy and the client) that plans or streams the rows, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the attempt.
  Use your turns to start attempts, read what happened, and improve the program.
- **Attempts.** `r.reset()` abandons the running attempt (or follows one that has ended) and starts a new one from the
  same start, paused until your next `submit`; `spec()["budget"]["reset"]` says how many resets you have
  (10 here; authoritative: if it says 0, the one attempt is the run). Once an attempt has ended,
  `submit` raises `EpisodeOver` until you reset. **Only your last attempt is graded**, and a success ends the trial at
  once. The wall clock is the run's and never restarts.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`; `spec()["cameras"]` says
  where each is mounted). Not where you or any object is, not the
  referee's state. Once an attempt is over, every response carries the referee's call: `meta["outcome"]`
  (`"success"` or the rule that ended it) and `meta["stages_reached"]` of `meta["stages_total"]`.
- There is nothing to hand in: the service records every control step it ran and grades your last attempt as it ran
  live (the referee's call). Keep the program that drives the robot at `/app/output/gen.py` and a `NOTES.md` of
  at most 20 lines (your approach, what failed, what you downloaded or installed) for the record: save them early and
  keep them current.
- Wall clock: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same
  way (and stops your background programs), so do not stop early: while you have attempts left, the run can still pass.

## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an attempt step number; by default the next step), replacing whatever was planned from `at` on
  and keeping what is planned before it. When the plan runs out, the command in force is held.
  `res.meta["control_steps"]` is the number of steps run so far in this attempt (so the next step has that number),
  `res.meta["proprio"]["now"]` the proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (a chunk covers at most 10 s), with `at = 0` for the attempt's start:
  `r.submit(type, A, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly those rows from
  the first step; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit(type, a[None], cameras=[])`, computed from the proprioception
  the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile. `r.status()` shows `running` and `lag_s`.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; it explains the protocol with another benchmark's example names: for this task `spec()` is
authoritative).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (800), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left`, `running`, `planned_steps`, `lag_s` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` (at most 30) of robot time |
| `r.submit(type, A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the attempt's clock |
| `r.reset(cameras=None)` | `POST /reset` | a new attempt from the same start, paused (see above) |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. `cameras=None` means every
camera: a controller's call should ask for none (`cameras=[]`) and read `res.meta["proprio"]["now"]`; the cameras are
rendered on the service's GPU. With `interpolate="linear"` (the default) each control step's command is a straight line from the
command in force to the row; `"hold"` applies the row as it is.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, at=0, cameras=[])   # A: (T, 22) rows of the `walk` type, from step 0
while not r.status()["done"]:
    ...                                              # or stream one row per control step from the proprioception
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_right`: the gripper's closure command, 0 (open) to 1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The right gripper is closed on `paddle` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0.2, 0.2, 0, 1.28, 0, 0, 0, 0.2, -0.2, 0, 1.28, 0, 0, 0, 0, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

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
| 15 | `left_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0.2 |
| 16 | `left_shoulder_roll` | [-1.5882, 2.2515] | 37 | 25 | 300 | 6 | 0.2 |
| 17 | `left_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0 |
| 18 | `left_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1.28 |
| 19 | `left_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0 |
| 20 | `left_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 21 | `left_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 22 | `right_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0.2 |
| 23 | `right_shoulder_roll` | [-2.2515, 1.5882] | 37 | 25 | 300 | 6 | -0.2 |
| 24 | `right_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0 |
| 25 | `right_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1.28 |
| 26 | `right_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0 |
| 27 | `right_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 28 | `right_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |

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
- **`run`** runs RoboOlympics' athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
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
- **The right hand carries a gripper** instead of a fist pad: Unitree's Dex1-1 two-finger parallel gripper
  (modelled: 0.55 kg; a housing of 78 × 67 × 63 mm on the wrist and two jaws 80 mm long beyond it, with rubber pads;
  90 mm stroke; the jaws close along the palm's normal). It holds only by contact and friction (no weld, no help):
  what it holds can slip, turn in the jaws or drop. `grip_right` is the closure command from 0 (open, 90 mm between the pads) to 1 (closed),
  any value between. The servo's setpoint follows it at about 375 mm/s of opening (the full stroke in 0.24 s; the
  jaws themselves can move briefly up to about 0.45 m/s when a clamp springs open), and a force-limited servo drives
  the jaws to it: on an object, the clamp force is about 10 N for every mm that the commanded opening
  (90 mm × (1 − command)) is below the object's width, at most 120 N, so a firm grip on a handle needs a command well
  past where the jaws touch it and a light one slips; a command that opens takes effect at once (the clamp eases or
  lets go within a millisecond, then the jaws open). The proprioception reports each gripper's opening, its speed and
  its clamp force; `holding_<side>` is 1 while both jaws touch the same object. The housing and the jaws collide with
  the world and with the rest of your own body. Where the model departs from the device: one command (the real one
  also sets a speed and a force; here the speed is the maximum and the force follows from the commanded opening), no
  5 N minimum force, and rubber pads (friction 1.0) that at 120 N hold about 240 N of shear, some five times the
  device's rated 5 kg friction-grasp load.
- **The left hand** has no working fingers here; it carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm) with a grip: while `grip_left` ≥ 0.5 the hand holds the nearest grippable
  object whose surface is within 3.5 cm of the palm point (the middle of the pad, 4.5 cm beyond the wrist flange along
  the forearm) and that moves at most 6 m/s relative to it; below 0.5 it lets go at once. Since the palm point is inside
  the pad, an object can be gripped where it touches one of the pad's two broad faces, not at its narrow sides or its
  far end. What is grippable is the task's own equipment, named in the rules.
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
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the gripper: `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A
real G1 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
