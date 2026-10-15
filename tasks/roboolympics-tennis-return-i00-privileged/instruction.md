# roboolympics tennis-return — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 68 kg; the RoboOlympics simulator on MuJoCo)
via Python. **Task:** Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket on your right hand back over the net so that it lands in the singles court on the far side.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand as the receiver: 2.75 m to the right of the court's centre line, your pelvis 0.5 m behind your baseline, facing the net (+x), which is 12.385 m ahead of you. Painted on the court, all 0.05 m wide and inside the measurements: the two baselines, the two singles sidelines, the two service lines, the centre service line between them and a 0.10 m centre mark on each baseline; there are no doubles lines. The far baseline is 23.77 m beyond yours. The ball waits where the server strikes it: 2.7 m above the ground, 0.2 m behind the far baseline and 0.8 m to the server's right of the centre mark (your left of the centre line). The serve is flat, with a little topspin; it bounces in your right service box, the one between the centre line and the right sideline, and reaches your baseline about a second after it was struck. The racket's handle lies along your right forearm; its strings face the way your palm faces.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good return). Where this task departs from it:

- Rules 16-21 (the service): the server is a machine: the ball appears at the server's strike point and leaves it with the serve's velocity and spin 3.0 s after the start; there is no opponent, the attempt ends when your return lands
- Rule 4 (the racket in the hand): the racket is clamped to the right hand with its handle along the forearm (the hand has no fingers to change the grip); it cannot be dropped or thrown
- Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at its first contact with the ground (a real ball's footprint is about 5 cm across)
- Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts less than 0.05 s apart are one hit, a later one is a second hit, and a contact longer than 0.05 s is a carry
- Rule 1 (the net): a 2 cm thick wall instead of a mesh of cord; a ball that meets it is stopped by a stiff, strongly damped contact
- wind and weather: none; the air is still (sea level, 15 C)

The court is the ITF singles court: 23.77 m long and 8.23 m wide, measured to the outside of the lines, with a service line 6.4 m from the net on each side. The net stands across the middle, 0.914 m high at its centre and rising in a straight line to 1.07 m at the posts, which stand 0.914 m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift); the racket (0.685 m long, 0.30 kg, strung surface 0.33 m by 0.25 m) is fixed to your right hand. 3.0 s after the start the ball is served from behind the far baseline at 30.0 m/s into your right service box. In order: the ball bounces once on your side; your racket hits it (any part of the racket counts); its centre passes the net's plane from your side to the far side, above the net's top edge or outside a post (it may touch the net or a post on the way); and its first contact with the ground after that is inside the far half of the singles court, the lines included (the point under the ball's centre decides; ground contacts less than 0.02 s apart are one bounce): that is the success. You fail if the racket touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball touches any part of you other than the racket at any time after the serve, if the racket touches the ball a second time (contacts less than 0.05 s apart are one hit) or stays on it longer than 0.05 s, if the ball passes the net's plane between the posts below the net's top edge, if any part of you or the racket touches the net or a post, or the ground beyond the net's plane, if anything of you touches the ball before it is served, if you fall, or after 10 s. A fall is: your pelvis lower than 0.35 m above the ground, or any part of you other than your feet touching the ground; the racket may touch the ground.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **bounce → racket → over the net → in**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 10 s (1000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 1000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
| `gen.py` | the script that produced it. It must **run and reproduce `trajectory.npz`**, reading nothing but `/app/instance.json` and files under `/app/output/` |
| `NOTES.md` | **at most 20 lines**: your final approach and why it works, the approaches that failed and what each told you, and what you downloaded or installed, if anything |

The tooling also appends its own log, `rcb_session_log.jsonl`, to `/app/output/`: leave it there and do not set
`RCB_SESSION_LOG`.

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it (with `gen.py` and `NOTES.md` to
match) whenever you have a better one.** The time limit (`## Time limit`) ends without warning; a run
that ends with no file scores zero. Do not stop early: keep improving until the time is up.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_rfo import Session
s = Session()                          # /app/instance.json; under a second
s.action_types                         # every action type: dim, layout, lower, upper, meaning (table below)
typ, row = s.hold()                    # the row that keeps the command in force with zero velocity (stand still)
done = s.step("walk", row)             # one control step (10 ms) of one row; True once the attempt is over
s.rows                                 # the sim rows of every step since the last reset: what save_trajectory() writes
s.status()                             # the referee: success, done, failed, stages, progress, metrics, events
s.state()                              # privileged state: pelvis (x, y, z, yaw), centre of mass, joints, the palms,
                                       # what each hand holds, and the task's objects under "task"
s.world                                # everything: s.world.m, s.world.d (MuJoCo model and data), s.world.robot
                                       # (addresses, limits), s.world.ref (the referee), s.world.task (the rules)
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`)
s.proprio()                            # the robot's own sensors as one row (s.ep.proprio_layout)
s.reset()                              # back to the frozen start (unlimited, instant); clears s.rows
s.replay()                             # what the verifier does with s.rows, here, in a fresh world
s.save_trajectory()                    # writes the SCORED file /app/output/trajectory.npz from s.rows
```
The simulator is deterministic on the CPU: the same rows from the frozen start give the same state, so a trajectory you
generate closed-loop (reading `s.state()`, `s.world`) replays exactly. `python /opt/tools/rcb_rfo.py replay --instance
/app/instance.json --traj /app/output/trajectory.npz --out /tmp/r.json` runs the verifier's replay from the shell. The
world's source is in `/opt/tools/rfo/` (the robot and action layer `world.py`, the referee's toolkit `referee.py`) and
this task's rules, as code, in `/opt/tools/rfo_task.py`; the robot library (model, meshes, limits, the walking and
running policies' weights) is in `/opt/roboolympics/`. You may build your own copies of the world to plan or learn in.

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz). Every row ends with `grip_left`, `grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains:

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
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 40 | 300 | 6 | 0 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 18 | 200 | 4 | 0 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 18 | 200 | 4 | 0 |
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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **13 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
