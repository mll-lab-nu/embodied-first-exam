# embodied-olympics high-jump — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Do a high jump: approach the bar, take off from one foot, go over the bar between the uprights without knocking it off its supports, and come down on the landing mat.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand on the runway facing the bar (+x), your pelvis 8 m before it, opposite its middle. The bar is red with white ends, the uprights grey, the mat blue; the runway is level and goes on 15 m before the bar and to both sides.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** World Athletics Competition and Technical Rules, 2024 edition: TR 26 (26.3-26.7 the uprights 4.00 to 4.04 m apart, the 4.00 m bar of at most 2 kg and 30 mm diameter on flat supports 4 cm wide and 6 cm long, 1 cm clear of the uprights), TR 27.1 (the take-off from one foot), TR 27.2 (failures: the bar does not remain on the supports; touching the ground or the landing area beyond the plane of the bar's nearer edge without first clearing the bar), TR 27.3 (a runway of at least 15 m), TR 27.10 (a landing area of at least 6 m x 4 m x 0.7 m), TR 25.17 (one minute for a trial). Where this task departs from it:

- TR 27.1 ("The athlete shall take off from one foot") is judged on the ground's forces, after every 1 ms physics step: during the last 0.15 s before the lift-off of the jump's flight the other (free) foot's ground force stays below 0.05 of the robot's weight, or the free foot is off the ground for the whole of the take-off foot's last ground contact; nothing else of the robot touches the ground in that time (or in that contact); a break of at most 0.03 s in a foot's contact is not a new contact. A staggered two-foot push, with the free foot leaving just before the lift-off, is a take-off from both feet
- TR 27.2(b) is judged geometrically, in one flight: the robot's pelvis and feet (the ankle joints) must pass the plane between the uprights and above the height of the bar's upper side, and every part of the robot must get beyond the plane, all in the same flight (from the take-off to the first contact with anything but the bar); a crossing made while touching the ground or the mat, or after a landing, never counts; any contact with the ground or the mat beyond the plane before that clearance is the rule's failure; the rule's allowance for a foot that touches the landing area without advantage is not used
- TR 27.2(a) (the bar does not remain on the supports): judged 2.0 s after the clearance and the landing, the bar must lie on its supports: touching both, its centre within half a support's width (0.04/2 m) of its resting place along the runway and within 0.005 m of its resting height, and at rest (its centre slower than 0.05 m/s, turning slower than 0.5 rad/s); at any time before, it is off its supports when its centre is more than 0.05 m below its resting height
- TR 27.10 (the landing area): the mat is one box whose contact follows soft polyurethane foam (about 5 kPa at 25 % compression, then a plateau: a body landing at 4 m/s sinks about 0.4 m and does not bounce back); MuJoCo's contact fitted to it on this robot: a time constant of 0.8 s, damping ratio 1.0, an impedance falling from 0.4 to 0.05 over 0.08 m, friction 1.0; the foam does not spring back after the landing, and its shock absorption is not a certified one (the rule book sets only the size); it begins 0.1 m behind the bar's plane
- the bar is rigid (no sag); no wind; the athlete alone, one trial at one height, 1.0 m (FAMILIES.md: a school competition's opening height; the men's world record is 2.45 m)
- TR 27 does not define a jump; here its flight lasts at least 0.05 s and raises the pelvis at least 0.08 m above its height at lift-off (a fall from a stand raises it by nothing); the number is kept within this robot's reach: an open-loop two-foot squat jump leaves the ground at about 1.8 m/s (0.17 m of rise); a one-foot take-off of an agent's own on the declared H2-class legs (2.5 kW, 295 N m per joint) left the ground at 2.78 m/s (0.39 m of rise of the centre of mass)
- the bar is rigid and its supports are fixed, so unlike a real bar it would carry a body: touching it is allowed, as in the rules, but contact with it for more than 0.3 s in all is a failure, and so is a push from it: the normal impulse of the bar on the robot, summed over the attempt, may be at most 2.0 N s (a real bar sags and falls under any weight; a free 2 kg bar given that much momentum across its 4 cm supports slides off them, and here one already leaves them at about 0.7 N s; on the 67 kg robot it is 0.03 m/s); a pelvis or a foot that comes back over the plane has not passed it

World Athletics rules for the high jump. The bar (4.0 m long, 0.03 m thick, 2.0 kg) rests with its upper side 1.0 m above the ground on two flat supports (0.04 m wide, 0.06 m long) that face each other from two uprights 4.02 m apart; pushed more than half a support's width forwards or backwards, or lifted, it falls. The bar lies across y in the plane x = 0; the plane the rules mean is that of its nearer edge, x = -0.03/2. Behind it lies the landing mat: 6.0 m wide, 4.0 m deep, 0.7 m high, soft, beginning 0.1 m behind that plane. The approach is free (any direction, any distance on the 15.0 m of level runway). A flight is a time of at least 0.05 s in which nothing of you touches anything but the bar. Your jump is the flight in which your pelvis crosses the bar's plane. Its take-off must be from one foot: in the last 0.15 s before lift-off your other foot presses on the ground with less than 0.05 of your weight (or it is off the ground for the whole of the take-off foot's last ground contact), and nothing else of you touches the ground; and in it your pelvis must rise at least 0.08 m above its height at lift-off. The clearance is judged in that one flight, between the take-off and your first contact with anything but the bar: your pelvis and both feet (the ankle joints) must cross the plane between the uprights and higher than the bar's upper side (one that comes back over the plane has not passed it and must pass it again), and every part of you must get beyond the plane. A crossing made while you touch the ground or the mat, or after the flight has ended, never counts. You have cleared the bar when all of that has happened in the flight. You may touch the bar, for at most 0.3 s in all, and it may push you with a normal impulse of at most 2.0 N s in all (a real bar falls under any weight: it does not carry you or throw you up), and after the clearance you may land on any part of your body, on the mat or not. You succeed when you have cleared the bar and landed, and 2.0 s later the bar still lies on its supports: touching both, its centre within half a support's width of its resting place along x and within 0.005 m of its resting height, and at rest (its centre slower than 0.05 m/s, turning slower than 0.5 rad/s); a bar knocked up or off counts as off. A fall is not a failure by itself. You fail if the bar drops more than 0.05 m at any time, or is not lying on its supports at that judgement; if you are in contact with the bar for more than 0.3 s in all, or it pushes you with more than 2.0 N s; if you touch the ground or the mat beyond the plane before you have cleared the bar, with or without a jump; if your jump's flight ends (you touch anything but the bar) before you have cleared the bar; if the take-off is not from one foot; if the flight is not a jump; if your pelvis or a foot passes the plane outside the uprights or not higher than the bar; if your landing after the clearance touches the ground on the take-off side; or after 60 s (the time allowed for a trial).

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **take-off → clearance → bar stays**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 60 s (6000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in one fresh process, one row per control step until the referee ends the attempt; scored 1 if the replay succeeds, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 6000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `bar`)
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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
