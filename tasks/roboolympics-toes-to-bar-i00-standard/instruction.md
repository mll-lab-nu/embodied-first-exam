# roboolympics toes-to-bar — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the RoboOlympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Hanging from the high bar by both hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go.

## The venue
At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, both grips closed on the bar (hands 0.39 m apart: the palms at y = +0.195 and -0.195 m), legs in the standing posture, your pelvis 0.80 m below the bar, your feet 1.55 m below it and 0.04 m behind it, your soles about 1.25 m above the floor (1.05 m above the 0.20 m mats under the bar). Your feet are 0.24 m apart, each 0.08 m wide. A grip command below 0.5 opens that hand and lets go of the bar. Nothing holds the legs up here: the `stand` action keeps the legs in the stance with a feed-forward meant for standing on the ground; `joints` or `lowcmd` rows drive every joint. The uprights stand at the two ends of the bar, 1.2 m to either side of you.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the uprights, 28 mm in diameter) over 0.20 m mats. Where this task departs from it:

- the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, because the hands cannot wrap a bar; opening a grip lets go
- CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged by where the feet are (both feet's centres at least 1.4 m below the bar, nine tenths of the dead hang's 1.55 m, and behind the bar), because the referee has positions, not a judge's eye
- FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies only

The bar is 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it turns freely about its own axis. Both hands grip it from the start. A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each at a point between your two hands (shins, knees or anything else on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet are at least 1.4 m below the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment (in your dead hang they are 1.55 m below it). You succeed when the hang of repetition 5 is reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment either hand no longer grips the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**rep 1 → rep 2 → rep 3 → rep 4 → rep 5**. An attempt (an episode) ends at the success, at the first rule violation, or after 60 s
(6000 control steps) of robot time.

## Real-robot rules
- **Attempts.** The first episode starts when the service comes up. `r.reset()` abandons the running attempt (or
  follows one that has ended) and starts a new one from the same start; `spec()["budget"]["reset"]` says how many
  resets you have (50 here). **Only your last attempt is graded**, and a success ends the trial at once.
- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for
  s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `get_obs()` with
  no seconds is free.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`; `spec()["cameras"]` says
  where each is mounted). Not where you or any object is, not the
  referee's state. Once an attempt is over, every response carries the referee's call: `meta["outcome"]`
  (`"success"` or the rule that ended it) and `meta["stages_reached"]` of `meta["stages_total"]`.
- There is nothing to hand in: the service records your last attempt, replays it in a fresh simulator and grades the
  replay. Keep the script that drives the robot at `/app/output/gen.py` and a `NOTES.md` of at most 20 lines (your
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
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (6000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

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

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The left and the right grips are closed at the start. The `stand` row that keeps the start as it is: `[0, 0, 0, -3.06, 0.57, 1, 1.4, 0, 0, 0, -3.06, -0.57, -1, 1.4, -0, 0, -0, 1, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

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
| 15 | `left_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | -3.06 |
| 16 | `left_shoulder_roll` | [-1.5882, 2.2515] | 37 | 25 | 300 | 6 | 0.57 |
| 17 | `left_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 1 |
| 18 | `left_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1.4 |
| 19 | `left_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0 |
| 20 | `left_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 21 | `left_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 22 | `right_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | -3.06 |
| 23 | `right_shoulder_roll` | [-2.2515, 1.5882] | 37 | 25 | 300 | 6 | -0.57 |
| 24 | `right_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | -1 |
| 25 | `right_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1.4 |
| 26 | `right_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | -0 |
| 27 | `right_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 28 | `right_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | -0 |

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
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm) with a grip: while `grip_left` / `grip_right` ≥ 0.5 the hand holds the nearest grippable
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
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. A
real G1 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
