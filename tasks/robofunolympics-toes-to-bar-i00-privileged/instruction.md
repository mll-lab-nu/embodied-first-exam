# robofunolympics toes-to-bar — instance i00

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the RoboOlympics simulator on MuJoCo)
via Python. **Task:** Hanging from the high bar by both hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, both grips closed on the bar (hands 0.39 m apart: the palms at y = +0.195 and -0.195 m), legs in the standing posture, your pelvis 0.80 m below the bar, your feet 1.55 m below it and 0.04 m behind it, your soles about 1.25 m above the floor (1.05 m above the 0.20 m mats under the bar). Your feet are 0.24 m apart, each 0.08 m wide. A grip command below 0.5 opens that hand and lets go of the bar. Nothing holds the legs up here: the `stand` action keeps the legs in the stance with a feed-forward meant for standing on the ground; `joints` or `lowcmd` rows drive every joint. The uprights stand at the two ends of the bar, 1.2 m to either side of you.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the uprights, 28 mm in diameter) over 0.20 m mats. Where this task departs from it:

- the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, because the hands cannot wrap a bar; opening a grip lets go
- CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged by where the feet are (both feet's centres at least 1.4 m below the bar, nine tenths of the dead hang's 1.55 m, and behind the bar), because the referee has positions, not a judge's eye
- FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies only

The bar is 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it turns freely about its own axis. Both hands grip it from the start. A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each at a point between your two hands (shins, knees or anything else on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet are at least 1.4 m below the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment (in your dead hang they are 1.55 m below it). You succeed when the hang of repetition 5 is reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment either hand no longer grips the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **rep 1 → rep 2 → rep 3 → rep 4 → rep 5**. The attempt ends at the success (that moment is the success), at the first rule violation,
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
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The left and the right grips are closed at the start. The `stand` row that keeps the start as it is: `[0, 0, 0, -3.06, 0.57, 1, 1.4, 0, 0, 0, -3.06, -0.57, -1, 1.4, -0, 0, -0, 1, 1]` (`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

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

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. The one thing not to look up is a solution to this exact task: this benchmark's own source code and reference solutions. This is an honour rule; trials are reviewed.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **13 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
