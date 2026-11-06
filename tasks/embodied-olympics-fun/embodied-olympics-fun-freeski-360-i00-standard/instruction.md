# embodied-olympics freeski-360 — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Drop in from the start platform, ride the in-run, take off from the kicker, do a 360 in the air, land on your skis and ride away past the finish line.

## The venue
x runs down the course from the start platform's back edge; you stand facing +x near the platform's front edge (the start line, 6.0 m from its back) with your boots 0.3 m behind it; the platform is level, 8 m wide. Past the edge the in-run falls at 35.0 degrees for 38.0 m, bends (radius 30.0 m) into a 5.0 m flat, and the kicker (6.0 m wide) rises from it (radius 18.0 m) to a 1.0 m lip at 25.0 degrees; the lip is about 59 m down the course and about 23 m below the platform. Behind the lip the table runs 15.0 m from the lip at the flat's level to the knoll (blue line), the landing falls at 36.0 degrees for 30.0 m (24.0 m wide), bends (radius 30.0 m) into the flat outrun (45.0 m, 30.0 m wide); the finish line (green) is 15.0 m into the outrun. Red lines mark the start line and the lip.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** FIS International Competition Rules (ICR) Book VI (Joint Regulations for Snowboard, Freestyle, Freeski and Ski Cross), edition June 2026: 3101.3 (the start platform: a completely flat, level area), 3102.4.1 (the big air site, level A: start area at least 5 m, in-run at least 30 m at 20 degrees or more, a 5-10 m flat before the kicker, a kicker at least 2.0 m high with a take-off angle of 25 degrees or more, at least 15 m from the take-off to the landing, a landing of 28 degrees or more, at least 20 m long and wide, an outrun of at least 25 m), 3402 (big air judging: difficulty, execution, amplitude, the landing), 3610 (the start: the competitor drops in on the start referee's signal); FIS Snowboard & Freeski Park & Pipe Judges Handbook, edition 2025, 8-11 (tricks by their rotation: spins in 180 degree units, flips; a trick counts when it is landed on the skis and ridden away); FIS Specifications for Competition Equipment 2026/27 B.2.2 (freestyle skis: no limits). Where this task departs from it:

- ICR 3402 / Park & Pipe Judges Handbook 8-11 (judges score each jump 0-100 by impression): one task is one trick, pass or fail: the trick is measured, not judged (the method of the Embodied Olympics freeski sport, MIT, with the spin taken from the skis), over the flight only (from the last contact with the snow to the next), so a rotation on the snow never counts and a wobble back and forth cancels; the spin is the skis' heading change (each ski's long axis, tail to tip, followed in the horizontal plane every 1 ms and unwrapped, so whole turns add up; held while a ski points within 10 degrees of the vertical; the mean of the two skis), counted in 180 degree units (not the pelvis's yaw: the pelvis turns against the skis on the hips and against the trunk at the waist, so its yaw can count turns the skis never made); the flip is the pelvis's angular velocity integrated about the horizontal axis across the take-off direction less the straight air's own forward turn (61.0 degrees: the lip's plus the landing's angle), counted in 360 degree units and only if the body went upside down; each to the nearest unit, so up to half a unit short or over still counts as that unit (a judge would deduct; a rotation half a unit or more off is the next or the previous trick). A flip with half a turn of spin is still that flip (freeski's rule: its own twist). A twist made while inverted is measured about the vertical like any spin (a cork and a twisting flip are not told apart). Grabs, amplitude, style and execution are not judged.
- Park & Pipe Judges Handbook (a landed trick: on the skis, riding away in control): the landing must be clean: the first contact after the flight is the skis', with both skis pointing the way the trick lands (forwards after whole turns, backwards after an odd number of half turns) within 45.0 degrees (a judge sees a 360 landed sideways or switch as another trick or a crash); from 0.5 s after that contact (the landing's impact and its first correction) to the finish line each ski's heading stays within 90.0 degrees of its heading then (no spin on the snow: a judge does not credit rotation made on the landing, and a skier riding away straight needs at most the landing's 45.0 degrees plus the finish line's 30.0 degrees of correction; a quarter turn is above that and half the smallest spin, the 180 of a revert); no other part of the robot (hands included; the boots on their skis are allowed) touches the snow from then until the finish line 15.0 m past the outrun's start, the robot is not down (on the snow with the pelvis less than 0.4 m above it or the trunk more than 70.0 degrees from its normal) for 1.0 s in all (freeski's fall rule; a judge would deduct for sitting back), the landing is past the table (a landing on the table or the knuckle before the knoll fails), and the skis cross the finish line pointing the way the trick landed (within 30.0 degrees).
- ICR 3102.4.1 (the big air site): the course is the Embodied Olympics freeski big air (MIT): a level start platform 6.0 m long, its edge rounded (radius 8.0 m, an estimate) onto a 38.0 m in-run at 35.0 degrees, a 30.0 m transition, a 5.0 m flat, a kicker of transition radius 18.0 m with a 1.0 m straight lip at 25.0 degrees (2.1 m above the flat, 6.0 m wide), a table 15.0 m long at the flat's level, an 8.0 m knoll rounding, a 36.0 degree landing 30.0 m long and 24.0 m wide, a 30.0 m transition and a 45.0 m outrun (30.0 m wide); every length within level A's limits, the transitions' radii estimates (FIS gives none); the snow is a profile of boxes (pieces of 25 cm along the arcs).
- ICR 3610 (the start): there is no start gate and nothing holds or pushes the robot: it stands on its skis on the level start platform, its boots 0.3 m behind the platform's edge (the start line), and the start referee's signal is given at t = 0; the robot leaves by its own action (it must work itself over the edge); not started within 20.0 s is a DNS.
- Equipment (EQ B.2.2): no limits for freestyle skis; the skis are the Faction Prodigy 1 Grom 135 cm (115/84/111 mm, radius 10 m, 1.19 kg), each three bodies (the middle rigid under the binding, the forebody and the afterbody on hinges with the ski's bending stiffness, EI 60 and 80 N m^2: estimates); binding 0.65 kg (stand height 35 mm) and boot 1.2 kg as mass on the ski (estimates); the binding holds the foot rigidly and never releases; the boot's forward flex is not modelled (the ankle joint moves inside it); no poles (big air athletes ski without them). The skis are solid against the robot's body and each other.
- Snow and air: the ski-snow model of the Embodied Olympics freeski sport (MIT, ported): kinetic friction after Wolfsperger et al. 2021, the edge's hold after Mossner et al. 2013 with Federolf's race-piste snow, hard well-damped snow; still air at a mountain venue (1.052 kg/m^3), the air's drag and lift on every link (a normal-force model); no wind, no snow is moved.
- Competition format (ICR 3501-3504: qualification and final runs, the best scores added): one jump, one attempt.

FIS big air, one jump, judged on one trick: the 360: one full turn of spin (your skis turn 270 to 450 degrees about the vertical in the air, either way) and no flip. Your feet are bound to freestyle skis (1.35 m twin tips). You stand on the level start platform with your boots 0.3 m behind its edge (the start line); the start signal is given at t = 0 and you must leave the platform by your own action (nothing holds or pushes you) within 20.0 s. The course: the platform's edge rounds onto the in-run (38.0 m at 35.0 degrees), a transition and a 5.0 m flat, then the kicker (it rises to its lip at 25.0 degrees, 2.1 m above the flat), a table 15.0 m long at the flat's level, the knoll, the landing (36.0 degrees, 30.0 m long), a transition and the flat outrun. The jump is your flight off the kicker: it starts within 4.0 m of the lip, rising at 10.0 degrees or more. The trick is measured in the air only (from the moment your last contact with the snow ends until the next contact). The spin is your skis' heading change: each ski's long axis (tail to tip) is followed in the horizontal plane (unwrapped, so whole turns add up; held while the ski points within 10 degrees of the vertical) and the spin is the mean of the two skis' changes, counted in half turns of 180 degrees (your pelvis's or trunk's own yaw does not count). The flip is your pelvis's rotation about the horizontal axis across your take-off direction, after removing the 61.0 degrees a straight air turns forward anyway, counted in full turns of 360 degrees and only if your body went upside down; each to the nearest unit (up to half a unit short or over still counts as that unit). A flip with half a turn of spin is still that flip. You succeed when the jump's rotation is the 360 and the landing is clean: the first contact after the flight is your skis', on the knoll or the landing hill (past the table), with both skis pointing forwards (down the course, +x) within 45.0 degrees at that first contact; from 0.5 s after it until both boots cross the finish line each ski's heading stays within 90.0 degrees of its heading at that moment (no spinning on the snow); from the first contact until both boots cross the finish line (15.0 m past the start of the outrun) no part of you but the boots touches the snow and you are not down for 1.0 s in all (down: on the snow with your pelvis less than 0.4 m above it, measured along its normal, or your trunk more than 70.0 degrees from its normal; the time down shrinks again at a quarter of the rate while you are up); and at the finish line your pelvis is at least 0.4 m above the snow and both skis point forwards (within 30.0 degrees). You fail: on any other trick (more or less rotation, a flip where none is asked, a different direction of flip, a take-off riding backwards), a landing with a ski pointing more than 45.0 degrees from forwards, a spin on the snow (a ski's heading more than 90.0 degrees from where it was 0.5 s after the landing), on a fall at any time (a part of you other than your boots on the snow, or down for 1.0 s in all), a landing on the table, the body first, a run with no jump, a stop (slower than 0.3 m/s for 3.0 s after the start), no start within 20.0 s, or at 40 s.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**start → take-off → landing → ride-away**. An attempt (an episode) ends at the success, at the first rule violation, or after 40 s
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
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`, `start`, `kicker`; `spec()["cameras"]` says
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

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

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
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
