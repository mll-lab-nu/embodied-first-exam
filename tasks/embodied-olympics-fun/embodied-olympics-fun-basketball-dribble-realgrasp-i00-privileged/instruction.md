# embodied-olympics basketball-dribble-realgrasp — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Dribble the basketball, which starts pressed between your two palms, from the end line across the centre line, 14 m up the court, one palm at a time, without a dribbling or a travelling violation.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand in the backcourt just inside the end line, facing up the court (+x): the end line's inner edge is 0.5 m behind your pelvis and the centre line 14.0 m beyond that edge. The basket of this end is to your right: the court's long axis, with the backboard (its lower edge 2.9 m high, 1.2 m in from the end line) and the ring, is 2.5 m to your right; the side lines are 15.0 m apart, the nearer one 5 m to your left. Painted on the floor: the boundary lines, the restricted area, the free-throw line (5.8 m from the end line) and circle, the three-point line, the centre line and circle. The ball is pressed between your two palms in front of your chest, its centre about 1.3 m above the floor and 0.45 m ahead of your pelvis: your upper arms are a little forward, your forearms a little raised and turned in so that the palms squeeze it; the start command keeps that squeeze (the joint table's start angles are a little further in than the arms stand: the difference is the squeeze). Your hands have no grip: the grip columns of the action rows do nothing in this task.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds a live ball), Art. 23 (out of bounds), Art. 24 (dribbling), Art. 25 (travelling), Art. 28.1.3 (when a dribbled ball is in the frontcourt). Where this task departs from it:

- Art. 3 (equipment): the hands are flat rubber palm pads without fingers; the ball is held only by pressing it between the two palms (friction), and it slips or drops when the arms do not press hard enough. It is dribbled by pushing it with a palm; it has left your hands when no hand has been on it for 0.03 s.
- Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball thrown at a still palm keeps 0.12 of its speed) instead of bouncing it like the floor (0.85); with the ball's own floor rebound on the palms a squeezed ball rattles out of them within about a second. A dribbling hand therefore gives the ball its speed by its own motion. The floor keeps the ball's rule-book rebound.
- Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a hand's touch of the ball that lasts longer than 0.3 s. A dribble that has ended cannot legally be started again (Art. 24.2), so a ball that comes to rest in a hand, or is touched by both hands at once, ends the attempt.
- Art. 13: every touch of the ball by a part of you other than a hand is a violation, also while the ball is held at the start (no ball held against the chest or between the forearms); intent (an accidental touch of a leg is legal in the rule book) cannot be judged.
- Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within 2.0 m (horizontally) of your pelvis, so that a ball thrown ahead and walked after is not a dribble.
- Art. 28 (eight seconds to reach the frontcourt) is not applied: the attempt lasts at most 60 s of robot time.

A FIBA court, 28.0 m by 15.0 m inside its boundary lines (lines 0.05 m wide); the centre line's axis is 14.0 m from the end line. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands have no fingers and no grip: the ball starts pressed between your two flat palms, and only the force of your arms and friction hold it; it can slip out. A hand is the palm pad and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it, and it has left them once no hand has been on it for 0.03 s. You stand still. Starting the dribble: the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor, and the pivot foot may not leave the floor before the ball has left your hands (a foot has left the floor when it has not touched it for 0.03 s). While the ball is in your hands it may touch no part of you but your hands, and it may not touch the floor. The ball leaving your hands (pushed, dropped or slipped) is the first touch of your dribble. The dribble: after that you play the ball with one hand at a time, by touches that push it to the floor (thrown, tapped, rolled or bounced): between two touches by your hands the ball must have touched the floor; contacts of a hand less than 0.03 s apart are one touch. There is no limit to your steps while the ball is not in a hand. You succeed at the first moment the ball touches the floor in the frontcourt (beyond the centre line's far edge, 14.0 m plus half a line width from the end line) with both your feet in the frontcourt (every point where each foot last touched the floor is beyond that edge), after at least one touch of your dribble after the ball left your hands. You fail if you travel at the start; if the ball touches the floor or a part of you other than a hand while it is in your hands; if, after it has left your hands, a hand's touch lasts longer than 0.3 s (the ball has come to rest in the hand); if both hands touch the ball at the same time; if a hand touches the ball twice without the ball having touched the floor in between; if the ball touches any part of you other than a hand; if the ball's centre is ever more than 2.0 m (horizontally) from your pelvis after it left your hands; if the ball or any part of you touches the floor on or outside a boundary line (out of bounds); if you fall (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 60 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **dribble → past the free-throw line → in the frontcourt**. The attempt ends at the success (that moment is the success), at the first rule violation,
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

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The `stand` row that keeps the start as it is: `[0, -0.2, -0.05, -0.074, -0.3, -0, 0, -0, -0.2, 0.05, 0.074, -0.3, 0, 0, 0, 0, 0]` (`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

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
| 13 | `left_shoulder_pitch` | [-3.14, 1.57] | 9 | 40 | 300 | 6 | -0.2 |
| 14 | `left_shoulder_roll` | [-0.38, 3.4] | 9 | 40 | 300 | 6 | -0.05 |
| 15 | `left_shoulder_yaw` | [-2.66, 3.01] | 20 | 18 | 200 | 4 | -0.074 |
| 16 | `left_elbow_pitch` | [-0.95, 3.18] | 20 | 18 | 200 | 4 | -0.3 |
| 17 | `left_elbow_roll` | [-3.01, 2.75] | 31.4 | 19 | 80 | 1.5 | -0 |
| 18 | `left_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 19 | `left_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | -0 |
| 20 | `right_shoulder_pitch` | [-3.14, 1.57] | 9 | 40 | 300 | 6 | -0.2 |
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 40 | 300 | 6 | 0.05 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 18 | 200 | 4 | 0.074 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 18 | 200 | 4 | -0.3 |
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
