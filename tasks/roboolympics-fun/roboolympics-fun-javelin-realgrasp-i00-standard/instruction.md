# roboolympics javelin-realgrasp — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 68 kg; the RoboOlympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Throw the javelin held by its cord in your right gripper over the shoulder from behind the arc so that its head strikes the ground first, inside the sector, at least 20.0 m from the arc, then leave the runway behind the arc and stand.

## The venue
You stand on the runway's centre line facing the sector (+x), your pelvis 2.0 m behind the middle of the arc; the arc's centre is 6.0 m behind you, its ends are 0.25 m behind its middle and 2.0 m to either side, and the runway reaches 28 m behind you. Your right arm hangs down, its gripper's fingers pointing down; the javelin lies level across the gripper's closed jaws, its cord between them, pointing forwards (the tip 0.98 m ahead of the jaws). Still air. The jaws open when your right grip command goes to 0 (at most 375 mm/s).

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** World Athletics Competition and Technical Rules 2024: TR 32.9 (the javelin runway and its arc), TR 32.12 (the sector), TR 32.14, 32.16, 32.17 and 32.20 (throwing events: failures, the landing, leaving the runway, the measurement), TR 38.1 (the throw), TR 38.3-38.6 (the men's javelin, its grip). Where this task departs from it:

- TR 38.1(a) ("the javelin shall be held at the grip with one hand"): the hand is a two-jaw gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws, at most 120 N of clamp, opening at most 375 mm/s; Unitree sells it for the G1, the H2 and the R1, not the H1-2: here it sits on the H1-2's right wrist where the palm ends); the cord lies across its jaws and is held by their friction only. Held means both jaws touching the cord; the hold may break for at most 0.02 s (contacts flicker); the release is the end of the hold, the last moment both jaws touched the cord. "Over the shoulder or upper part of the throwing arm" is judged at the release: the javelin's centre of gravity must then be at least 0.0 m higher than the throwing shoulder's joint.
- TR 38.1(a) (one hand): before the release the javelin may not touch your left arm or hand (it may rest against the rest of you: the rule book forbids only the second hand).
- TR 38.1(c): "turned completely around" is judged as the chest's heading more than 135.0 degrees away from the throwing direction at any time before the release.
- TR 38.3-38.6: the javelin is one rigid body (no bending or vibration) whose head does not stick in the ground; the mark is the point where the head first touches the ground; the cord grip is a smooth band 0.16 m long and 0.029 m across (no pattern: the pads' rubber gives the friction).
- Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model with coefficients of the order of the published wind-tunnel data, the centre of pressure 0.25 m behind the centre of gravity), still air, no wind. The model's drag does not grow with the angle of attack as a real javelin's does: a javelin released nose-high flies up to a fifth farther here than it would.
- TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, and the javelin may not be gripped again.
- TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the runway correctly and stands.
- TR 25.17 (one minute for a trial): the whole trial, leaving the runway included, has 60 s.
- The qualifying mark of 20.0 m is this benchmark's (a boys' school standard for the 800 g javelin); the rule book only measures.

The men's javelin (0.8 kg, 2.65 m long, its centre of gravity 0.98 m from the tip, a metal head of 0.29 m; its cord grip, 0.16 m long and 0.029 m across, covers the centre of gravity) starts held at its cord between the two jaws of your right hand, a two-jaw gripper that holds only by friction: the javelin can slip along or turn in the jaws, and drop. It is held while both jaws touch the cord (breaks of at most 0.02 s are ignored); the release is the end of the hold: the last moment both jaws touched the cord, however it ends (opened, slipped or dropped). Until the release the javelin may not touch your left arm or hand (the javelin is held with one hand). The runway is 4.0 m wide between the inner edges of its side lines and 30.0 m long; it ends at the arc, a white strip whose inner edge is a circle of 8.0 m radius round a point on the runway's centre line; short white lines run outwards from the arc's two ends at right angles to the side lines. The sector is bounded by the two lines from the arc's centre through the arc's ends (28.96 degrees between them). The throw: at the release the javelin's centre of gravity must be at least 0.0 m higher than your right shoulder joint. There is one release: after it the javelin may not be held again (both jaws on the cord once more) and no part of you may touch it, except that your right arm and its gripper may still touch it during the first 0.2 s (the shaft sliding out through the jaws). The throw is valid only if the head touches the ground before any other part of the javelin, at a point inside the sector lines (on a line is out). It is measured from that point to the inner edge of the arc along the line through the arc's centre. You succeed when a valid throw measures at least 20.0 m and you have then left the runway correctly and stood for 1.0 s. Leaving correctly: after the javelin has landed, your first touch of a side line or of the ground outside the runway is behind the arc's end lines, or you touch the ground 4.0 m or more behind the arc's ends. Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if, at any time before that, any part of you touches the arc, its end lines or the ground beyond them; if you touch a side line or the ground outside the runway (also behind its rear end) before the javelin has landed; if your chest is turned more than 135.0 degrees away from the throwing direction before the release (your back to the arc); if the javelin touches your left arm or hand before the release; if it is released lower than the shoulder; if it is held again, or touched, after the release (but for the grace above); if it does not land head first, lands outside the sector or short of 20.0 m; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**release → landing → exit**. An attempt (an episode) ends at the success, at the first rule violation, or after 60 s
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
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`, `sector`, `hand`; `spec()["cameras"]` says
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
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 20) rows of the `walk` type
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_right`: the gripper's closure command, 0 (open) to 1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The right gripper is closed on `javelin` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0, 0, 0, 0, 0, 0, -0.15, 0, 1.57, 0, 0, 0, 0, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains
(also in `spec()["robot_facts"]`):

| # | joint | range (rad) | speed (rad/s) | torque (N m) | kp | kd | at the start (rad) |
|---|---|---|---|---|---|---|---|
| 0 | `left_hip_yaw` | [-0.43, 0.43] | 23 | 200 | 800 | 10 | 0 |
| 1 | `left_hip_pitch` | [-3.14, 2.5] | 23 | 200 | 800 | 10 | -0.16 |
| 2 | `left_hip_roll` | [-0.43, 3.14] | 23 | 200 | 800 | 10 | 0 |
| 3 | `left_knee` | [-0.26, 2.05] | 14 | 300 | 1200 | 16 | 0.36 |
| 4 | `left_ankle_pitch` | [-0.8973, 0.5236] | 9 | 60 | 160 | 8 | -0.2 |
| 5 | `left_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 6 | `right_hip_yaw` | [-0.43, 0.43] | 23 | 200 | 800 | 10 | 0 |
| 7 | `right_hip_pitch` | [-3.14, 2.5] | 23 | 200 | 800 | 10 | -0.16 |
| 8 | `right_hip_roll` | [-3.14, 0.43] | 23 | 200 | 800 | 10 | 0 |
| 9 | `right_knee` | [-0.26, 2.05] | 14 | 300 | 1200 | 16 | 0.36 |
| 10 | `right_ankle_pitch` | [-0.8973, 0.5236] | 9 | 60 | 160 | 8 | -0.2 |
| 11 | `right_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 12 | `torso` | [-2.35, 2.35] | 23 | 200 | 600 | 15 | 0 |
| 13 | `left_shoulder_pitch` | [-3.14, 1.57] | 9 | 40 | 300 | 6 | 0 |
| 14 | `left_shoulder_roll` | [-0.38, 3.4] | 9 | 40 | 300 | 6 | 0 |
| 15 | `left_shoulder_yaw` | [-2.66, 3.01] | 20 | 18 | 200 | 4 | 0 |
| 16 | `left_elbow_pitch` | [-0.95, 3.18] | 20 | 18 | 200 | 4 | 0 |
| 17 | `left_elbow_roll` | [-3.01, 2.75] | 31.4 | 19 | 80 | 1.5 | 0 |
| 18 | `left_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 19 | `left_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 0 |
| 20 | `right_shoulder_pitch` | [-3.14, 1.57] | 9 | 40 | 300 | 6 | 0 |
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 40 | 300 | 6 | -0.15 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 18 | 200 | 4 | 0 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 18 | 200 | 4 | 1.57 |
| 24 | `right_elbow_roll` | [-2.75, 3.01] | 31.4 | 19 | 80 | 1.5 | 0 |
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
  device's rated 5 kg friction-grasp load. Unitree sells the Dex1-1 for the G1, not the H1-2: here it sits on the wrist where the Inspire hand's palm ends (its fingers removed, the palm's shell kept), which makes that forearm longer than a real installation would.
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
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the 27 joint positions
(`*_pos`, rad), their velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in
force (`*_target`, rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from
sensor; angular velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
`holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms,
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the gripper: `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A
real H1-2 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
