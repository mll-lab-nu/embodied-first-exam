# roboolympics hurdles — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the RoboOlympics simulator on MuJoCo)
via Python. **Task:** Run the 50 m hurdles: go over all four hurdles in your lane, never beside one or under its top, and bring your torso to the finish line.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand in your lane facing the finish (+x), the front ends of your feet 0.02 m behind the start line, your pelvis 0.23 m behind it. The lane lines are white on a red track; the hurdles' top bars are white with black stripes; two white posts stand beside the finish line. In your rest pose your forearms point forward at about the height of a hurdle's top.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** World Athletics Competition and Technical Rules, 2024 edition: TR 22 (22.1-22.3 distances and heights: the men's hurdle 1.067 m high, 13.72 m to the first, 9.14 m between; at the indoor distance of 50 m that is four hurdles and 8.86 m from the last to the finish; 22.4-22.5 the hurdle: 1.18 to 1.20 m wide, a top bar 70 mm high, a base at most 0.70 m long, at least 10 kg, a toppling force of 3.6 to 4.0 kg at the centre of the top bar's top edge; 22.6 each hurdle is gone over in the athlete's own lane; 22.6.1 a foot or leg beside the hurdle below the plane of its top; 22.6.2 knocking a hurdle down by hand or body; 22.7 knocking hurdles down otherwise is no offence), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish). Where this task departs from it:

- TR 16 (the start): no starter's commands, no blocks and no reaction time: the robot stands with the front ends of its feet 0.02 m behind the start line and the clock runs from t = 0
- TR 22.6 ('goes over each hurdle') is judged geometrically at the plane of the hurdle's top bar: the pelvis must pass above the height of the hurdle's top, each foot (its ankle joint) above the lower edge of the top bar (a foot that strikes the bar knocks the hurdle down, which is allowed; a foot below the bar goes under), all three between the bar's ends
- TR 22.6.2 (knocking down or displacing a hurdle by hand, body or the upper side of the lead leg): intent and the side of the leg cannot be judged: a hurdle tipped more than 10.0 degrees within 0.5 s of a touch by a hand, an arm, the trunk or the pelvis is a failure; the legs may knock it down
- TR 17.3 (lanes): the lane is judged by the pelvis (its centre more than half a lane width from the lane's centre line); TR 22.6.1 is judged on the centres of the legs' collision bodies within 0.1 m of the hurdle's plane
- TR 17 (a fallen athlete): a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the race (did not finish)
- TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches the finish line's plane, interpolated between 1 ms physics steps (the H1-2's trunk and head are one link, so its torso includes the head); no wind; the robot alone on a straight of three lanes
- the hurdle touches only the robot (its hinge's stop is the ground), and tips forwards only, like RoboOlympics'; the distance is the indoor 50 m with its four hurdles, on an outdoor straight, not the 110 m; the time limit, 140 s, is this benchmark's (FAMILIES.md)

World Athletics rules for the hurdles, at the indoor distance of 50 m. The lane runs along +x, 1.22 m wide, centred on y = 0; the start line (0.05 m wide) has its far edge at x = 0, the finish line is x = 50.0 m. 4 hurdles stand across the lane, the first 13.72 m from the start line and one every 9.14 m after it (the last 8.86 m before the finish). A hurdle is 1.067 m high and 1.19 m wide with a top bar 0.07 m high; its two base feet, 0.7 m long, lie on the track on your side of it. It is hinged at the foot of its uprights and tips over forwards when a horizontal force of more than 3.8 kg pushes the middle of its top bar; let go before it has gone too far, it swings back. The clock starts at t = 0. You go over a hurdle when your pelvis and both your feet (the ankle joints) have crossed the plane of its top bar towards +x, each between the bar's two ends, the pelvis higher than the hurdle's top (1.067 m above the track) and each foot higher than the lower edge of its top bar (1.067 m less 0.07 m), whether the hurdle still stands or not; a pelvis or a foot that comes back over the plane has not crossed it and must cross it again. The hurdles are gone over in order. Knocking a hurdle down with your legs is allowed (a hurdle tipped more than 45.0 degrees is counted as down, without a fault). You finish at the moment the leading point of your torso (the trunk and head hull; not the arms, legs or feet) reaches the finish line, with all hurdles gone over. You succeed with a finish within 140 s of robot time. A fall does not end the race: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail if your pelvis or a foot crosses the next hurdle's plane beside the hurdle, or lower than said above (going under its top); if a part of one of your legs is beside the next hurdle (beyond the bar's ends, within 0.1 m of its plane) lower than the hurdle's top; if a hurdle is tipped more than 10.0 degrees within 0.5 s of being touched, while it was not yet tipped that far, by a hand, an arm, your trunk or your pelvis (knocked by hand or body; only hurdles within 3 m of your pelvis are judged); if your pelvis is more than half the lane's width from y = 0; if your torso reaches the finish line before every hurdle is gone over; when down for 10.0 s; or after 140 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **hurdle 1 → hurdle 2 → hurdle 3 → hurdle 4 → finish**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 140 s (14000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 14000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `first_hurdle`)
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
