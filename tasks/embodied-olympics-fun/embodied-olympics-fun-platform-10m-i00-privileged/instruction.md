# embodied-olympics platform-10m — instance i00

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Do a forward dive straight (101A) from the 10 m platform: from your standing start at its front end, take off, turn half a somersault forwards in the straight position and enter the water head first, vertical, with your arms stretched beyond your head.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
The platform's top is 10.0 m above the water, 6.0 m long and 3.0 m wide; its front edge (a 0.2 m thick slab) is 0.119 m ahead of your pelvis, about 2 cm ahead of your toes, square across your path, and you stand on its centre line. It projects 1.5 m beyond the pool's edge; the water lies ahead and below. Handrails 1.0 m high run along both sides of the platform and across its back, the side rails ending 1.0 m before the front edge. The platform is rigid; nothing in the venue moves.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** World Aquatics (FINA) Diving Rules 2022-2025 (in force 3 December 2022): D 1.5 (dive numbers: 101 = front group, no flying action, one half somersault; A = straight), D 6.5.4 (a double jump on the platform is a failed dive), D 6.5.7 (a twist of 90 degrees or more at the entry: failed), D 6.5.8 / 6.5.8.1 (head first: arms below the head, maximum 4.5 points; the feet entering before the head or hands: failed), D 8.1.1 (awards 0 to 10), D 8.2.4 (standing dives: the starting position on the front end, the feet stay on the platform until the take-off), D 8.4.4 (the take-off bold, balanced and high, from the end of the platform), D 8.5.1-8.5.5 (the direct line of flight; touching the platform; unsafely close: at most 2 points; straight: not bent at the knees or hips, feet together, toes pointed), D 8.6.1-8.6.3 and 8.6.7 (the entry vertical, not twisted, the body straight, feet together, toes pointed; head first with the arms stretched beyond the head in line with the body, the hands close together; the dive is complete when the whole body is under the surface). World Aquatics Facilities Rules FR 5.2 (the 10 m platform at least 6.0 m long and 3.0 m wide, rigid and horizontal, a 0.2 m front edge, projecting at least 1.50 m beyond the pool edge, handrails at the back and the sides up to 1 m from the front edge). Where this task departs from it:

- D 8.1.1 (the judges' award): the panel's 0-10 award is replaced by pass/fail lines that stand for a dive with no failed-dive call and no capped award: the entry within 15.0 degrees of vertical, hips and knees bent less than 20.0 degrees, the ankles at most 0.12 m apart, the toes pointed (each ankle extended at least 0.3 rad of the robot's 0.52), both palms at least 0.15 m beyond the head along the body line, at most 0.2 m apart and within 0.15 m of the body line, a twist under 20.0 degrees; the rule book gives the qualities, not these numbers
- D 8.6 and D 8.1.2 (the entry): the water is not simulated. The pool's surface is a plane the robot passes through without resistance; the entry is judged from the first touch of the surface until the whole body is under it (D 8.6.7), and nothing after that is judged (D 8.1.2: no movement beneath the surface counts). With no water the body keeps turning through the entry (the water stops a diver's rotation), so the entry's angle is taken at one moment, when the hips (the pelvis) reach the surface; the shape is judged through the whole passage
- D 8.4.4 (a high take-off): a take-off counts once the robot's centre of mass rises at least 0.1 m above its height at the start, so that a fall forward is not a dive
- D 8.5.5 (the straight position): judged from the moment the body line passes the horizontal until the entry (the last quarter somersault; D 8.5.7's quarter somersault for flying dives), with the entry's limits
- D 8.5.3 / 8.5.4 / 8.4.4 (touching the platform; unsafely close; a take-off from the end): any touch of the platform or its railings after the take-off fails, and the distance is judged at the water surface: the entry point (the middle of the palms at the first touch of the water) between 0.5 m and 3.0 m in front of the platform's front edge (the rule book leaves 'unsafely close' and 'from the end' to the judges)
- D 8.5.1 (the direct line of flight): the entry point must be within 0.5 m to either side of the line the robot faces at the start
- D 8.2.4.2 / 6.5.4 (the feet stay on the platform; no double jump): a flight of 0.03 s or more that lands on the platform again fails, and neither foot may be off the platform for more than 0.1 s while the other is on it (a step, a crow-hop)
- D 8.2.1 (the starting position): the robot is placed at the front end at t = 0 instead of walking there; it stands as its rest pose stands (the arms in front), not straight with the head erect
- D 1.5 (the dive): the half somersault is checked as the body line's turn in the vertical plane from the start to the entry, 180.0 degrees within 45.0
- FR 5.3.1 (the pool): the pool's water is a drawn surface over a floor that nothing collides with; the pool's depth and the other boards are not built

You stand on the 10 m platform's front end facing the water (+x). The dive: take off from the platform (both feet stay on it until the take-off: a foot off it for more than 0.1 s while the other is on it, or any flight of 0.03 s or more that lands on the platform again, fails; the take-off counts when you are in the air and your centre of mass has risen at least 0.1 m above its height at the start), turn forwards through half a somersault (180.0 degrees, within 45.0, counted from your upright start) and enter the water head first. From the moment your body line (from the middle of your ankles to the middle of your shoulders) passes the horizontal until the dive is complete you must be in the straight position: hips and knees each bent less than 20.0 degrees from straight, the ankles at most 0.12 m apart, the toes pointed (each ankle pitched at least 0.3 rad towards the toes). The entry starts when the first part of you reaches the water surface (z = 0) and the dive is complete when the whole of you is under it; that first part must be a hand or the head (feet first fails); when your pelvis reaches the surface your body line must be within 15.0 degrees of vertical, head down; through the entry: not twisted (your shoulders' axis within 20.0 degrees of the platform's width direction); both palms at least 0.15 m beyond the centre of your head along the body line, at most 0.2 m apart and each within 0.15 m of the body line; and the straight position. The entry point (the middle of your palms when the first part of you touches the water) must be between 0.5 m and 3.0 m in front of the platform's front edge (closer is unsafely close) and within 0.5 m to either side of the line you face at the start. You fail if, after the take-off, any part of you touches the platform or its railings. Before the take-off any part other than the feet on the platform, or anything on the railings, fails. The water is not simulated: nothing after the dive is complete is judged. Success: a complete dive that keeps all of these. The attempt ends after 20 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **take-off → entry → under water**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 20 s (2000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 151 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 2000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `platform`)
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
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
