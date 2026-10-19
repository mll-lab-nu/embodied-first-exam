# embodied-olympics discus-realgrasp — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 68 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Throw the discus that your right gripper holds by its rim from inside the circle so that it lands inside the sector at least 15.0 m from the circle, then leave the circle from its rear half and stand.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand in the rear half of the circle facing the sector (+x), your pelvis 0.55 m behind the circle's centre. Your right arm hangs straight down, a little away from the leg; the gripper's fingers point down and its jaws, closed at the full command, clamp the discus by its rim, the discus hanging below the hand with its faces towards and away from your leg. There is no cage. Still air.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle, 2.50 m for the discus), TR 32.12 (the 34.92 degree sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing events: the start, failures, the landing, leaving the circle, the measurement), TR 34 (the men's discus), TR 35 (the discus cage). Where this task departs from it:

- TR 34 (the discus; the thrower's hand): the right hand is Unitree's Dex1-1 two-jaw gripper (sold for the G1, the H2 and the R1, not for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, 80 mm jaws with rubber pads, at most 120 N of grip, opening at most 375 mm/s. It holds the discus by its rim, the discus' faces between the jaws (where a hand's palm and fingertips hold it), by friction only: nothing is welded or grippable, and the discus slips, turns in the jaws or flies out when the throw pulls harder than the clamp's friction (at the full clamp a steady pull at the discus' centre moves it in the jaws at about 200 N out of them and 100 N across them). The release is the gripper's last hold (both jaws on the discus) before it is clear of the robot.
- TR 34 (the discus' shape): an ellipsoid of the official diameter, thickness and mass (no separate metal rim: its moment of inertia is that of a uniform body; near the rim it is 13 to 19 mm thick, as the rule book's rim).
- TR 35 (the cage): there is no cage.
- TR 32.5-32.6: the ground outside the circle is level with the rim's top for 1 m and then falls to the field's level over 1 m (the circle's inside is the field's level, 0.02 m below the rim, instead of the field being level with the rim).
- TR 32.20: the mark is the point where the discus first touches the ground.
- TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, and the discus may not be gripped again.
- TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the circle correctly and stands.
- TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has 60 s.
- Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag, lift and the pitching moment of an ellipsoid, coefficients of the order of the published wind-tunnel data), still air, no wind.
- The qualifying mark of 15.0 m is this benchmark's (a school standard for the 2 kg discus); the rule book only measures.

The men's discus (2.0 kg, 0.22 m across, 0.045 m thick at its centre) starts clamped by its rim between the two jaws of your right hand's Dex1-1 gripper (the row's right grip value is the gripper's closure command, 0 open to 1 closed; nothing is welded or grippable: friction alone holds it, and it slips, turns or flies out when the throw pulls harder than the clamp). The circle is 2.5 m across inside its rim; the ground outside is 0.02 m higher than its inside. The sector opens from the circle's centre, 34.92 degrees wide, symmetric about the direction you face at the start. Holding: the discus touches both jaws of the right gripper. Before the release nothing of you but your right hand (the gripper and the wrist) may touch it, and it may not stay on the hand without the gripper's hold (touching the hand but not both jaws) for more than 0.2 s. The release is the gripper's last hold before the discus has touched nothing of you for 0.03 s; there is one release: after it the discus may not be held by the gripper again, nothing of you but the right hand may touch it, and the right hand only during the first 0.2 s (brushing it as it leaves). Its first touch of the ground must be inside the sector lines (on a line is out); the throw is measured from that point to the inside of the rim along the line through the circle's centre. You succeed when a valid throw measures at least 15.0 m and you have then left the circle correctly and stood for 1.0 s. Leaving correctly: after the discus has landed, your first touch of the rim's top or of the ground outside the circle is behind the line through the circle's centre across the throwing direction (the rear half). Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included) or the ground outside the circle before the discus has landed, or in the front half before you have left correctly; if the discus is touched by anything but the right hand before the release, stays on the hand without the gripper's hold, is gripped again or touched after the release (but for the right hand's brush); if it lands outside the sector or short of 15.0 m; if you fall (your pelvis lower than 0.5 m above the circle's floor, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact; a contact within 0.003 m of the rim's top counts as on it.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **release → landing → exit**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 60 s (6000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 6000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
                                       # (the gripper' "right_palm" is its jaw centre; "real_hands": each gripper's
                                       # command, opening, opening speed, clamp force, what it holds, jaw centre and axes)
s.world                                # everything: s.world.m, s.world.d (MuJoCo model and data), s.world.robot
                                       # (addresses, limits), s.world.ref (the referee), s.world.task (the rules)
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `sector`)
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
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_right`: the gripper's closure command, 0 (open) to 1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The right gripper is closed on `discus` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0, 0, 0, 0, 0, 0, -0.2, 0, 1.57, 0, 0, 0, 0, 1]` (`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

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
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 40 | 300 | 6 | -0.2 |
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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **13 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
