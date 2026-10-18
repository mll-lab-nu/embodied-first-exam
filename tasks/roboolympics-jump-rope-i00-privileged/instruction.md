# roboolympics jump-rope — instance i00

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 34 kg; the RoboOlympics simulator on MuJoCo)
via Python. **Task:** Skip rope: turn the rope forwards with both hands, over your head and under your feet, and jump it with both feet together, 17 times within one minute.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand facing +x on the level wooden floor of a sports hall. In each gripper you hold a handle (0.15 m long, 0.028 m thick) along the fingers, its far end about 0.08 m beyond the finger tips, where the rope is attached on a swivel. The rope is 2.13 m long and 0.1 kg, made of plastic beads 9.5 mm thick. It hangs from each handle straight down to the floor and lies on the floor behind your heels in a bow whose middle is about 0.25 m behind your pelvis or further. Nothing else is near you.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** The Chinese National Student Physical Fitness Standard (国家学生体质健康标准, 2014 revision, Ministry of Education 教体艺〔2014〕5号), one-minute rope skipping (1分钟跳绳): the rope turned forwards, a two-foot jump (正摇双脚跳); each turn of the rope round the body that passes under the feet counts one; a miss (the rope caught on the body) does not stop the clock, the skipper starts the rope again; the result is the count in one minute. The family's success line is the standard's pass mark (60 points) for first-grade boys: 17 jumps in one minute. Where this task departs from it:

- Equipment: the standard names no rope. The rope here is a 7 ft (2.13 m between the swivels) beaded school rope, the length that skipping-rope sizing charts give a skipper shorter than 1.45 m (4 ft 9 in): 28 rigid segments of two 38 mm low-density polyethylene beads each (9.5 mm across, Kanga's deluxe beaded rope), 0.1 kg in all (a 7 ft segmented rope weighs 0.2 lb). Neighbouring segments are tied by stiff pivots that stretch by a few millimetres under load (the cord), and the rope feels the air's drag. Its two plastic handles are 0.15 m long and 0.04 kg each, with the rope on a swivel at their far ends.
- Hands: the robot's hands are Unitree Dex1-1 two-finger grippers. Each handle is held between the jaws only by their friction, so it can slip out or be dropped.
- Judging: a judge's eye is replaced by geometry, checked at every 1 ms physics step. The rope passes under a foot when its point at that foot's sideways position crosses, from front to back, the upright plane across the robot's heading through the foot, lower than the foot's lowest point (plus the rope's thickness). It passes over the head when its point at the head's sideways position crosses the upright plane through the head from back to front, higher than the top of the head. Three numbers the standard leaves to the judge's eye: the rope must move backwards at 1.0 m/s or more as it passes (a turning rope, not a hop over a still one), under the second foot within 0.15 s of the first, and both feet must leave the floor within 0.1 s of each other (a two-foot jump).
- Timing: the minute runs from t = 0, with the robot standing, a handle in each gripper and the rope on the floor behind its heels. The attempt ends with success once the robot has landed on its feet after the 17th jump and stood still for 1.0 s (the families' land-and-stand rule), without waiting for the end of the minute.

You hold a skipping rope by its two handles, one in each of your two-finger grippers. Turn it forwards: over your head from back to front, then down in front of you and under your feet from front to back. A jump counts when the rope, after passing over your head, passes under both feet while nothing of you touches the floor, and your take-off was two-footed: both feet left the floor within 0.1 s of each other. The rope passes over your head when its point straight above your head crosses the upright plane through your head, from back to front, higher than the top of your head. It passes under a foot when its point at that foot's sideways position crosses the upright plane through that foot, across your heading, from front to back, lower than the bottom of the foot plus the rope's thickness, while it moves backwards over the floor at 1.0 m/s or more (the rope turning, not you hopping forwards over a still rope). It must pass under the second foot within 0.15 s of the first. Each turn of the rope counts at most once. Extra hops between turns are allowed but do not count. A miss does not end the attempt: if the rope stops on your body, passes under the feet while a foot or anything else of you touches the floor, passes under only one foot, turns backwards, or comes under your feet without first going over your head, that turn does not count, and the rope must go over your head again before the next jump. After your 17th counted jump you must land on your feet (the first thing of you to touch the floor) and then stand for 1.0 s without a break: only your feet on the floor, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s; then you succeed. You fail if you let go of a handle (a handle out of its gripper's jaws for more than 0.05 s, or a handle touching the floor), if the last landing is not on your feet, if you fall (your pelvis lower than 0.35 m, or any part of you other than your feet on the floor), or after 60 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **jump 1 → jump 2 → jump 3 → jump 4 → jump 5 → jump 6 → jump 7 → jump 8 → jump 9 → jump 10 → jump 11 → jump 12 → jump 13 → jump 14 → jump 15 → jump 16 → jump 17 → stand**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 60 s (6000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 151 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 6000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
                                       # (the grippers' "left_palm" and "right_palm" are their jaw centres; "real_hands": each gripper's
                                       # command, opening, opening speed, clamp force, what it holds, jaw centre and axes)
s.world                                # everything: s.world.m, s.world.d (MuJoCo model and data), s.world.robot
                                       # (addresses, limits), s.world.ref (the referee), s.world.task (the rules)
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `side`)
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
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each gripper's closure command, 0 (open) to 1 (closed). At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The left gripper is closed on `handle_left` at the start (closure command 1): opening it lets go. The right gripper is closed on `handle_right` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0.2, 0.2, 0, 1.28, 0, 0, 0, 0.2, -0.2, 0, 1.28, 0, 0, 0, 1, 1]` (`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains:

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
- **The left and right hands carry a gripper** instead of a fist pad: Unitree's Dex1-1 two-finger parallel gripper
  (modelled: 0.55 kg; a housing of 78 × 67 × 63 mm on the wrist and two jaws 80 mm long beyond it, with rubber pads;
  90 mm stroke; the jaws close along the palm's normal). It holds only by contact and friction (no weld, no help):
  what it holds can slip, turn in the jaws or drop. `grip_left` and `grip_right` are the closure commands from 0 (open, 90 mm between the pads) to 1 (closed),
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
