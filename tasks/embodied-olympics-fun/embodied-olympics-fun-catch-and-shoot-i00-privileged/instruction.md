# embodied-olympics catch-and-shoot — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Catch and shoot: catch the chest pass that comes to you from the left wing with your two hands, then shoot from where you stand so that the ball enters the basket from above.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
A FIBA court. You stand at the top of the key facing the basket (+x), your arms at rest and your hands empty: the point under the ring's centre is 5.8 m ahead of your pelvis (inside the three-point line; the free-throw line is 1.575 m ahead of you). The passing machine stands on the left wing, where a passer would: its wheels' nip (where the ball leaves) 0.92 m ahead of you and 3.97 m to your left, 1.25 m above the floor, its head aimed at you; the ball waits in its throat behind the wheels. The pass is aimed at the point 0.4 m straight ahead of where your pelvis starts, 1.25 m above the floor: it leaves on a flat arc (13 degrees up, rising 0.2 m) and is there 0.44 s later, moving at about 8.4 m/s to your right and 16 degrees downwards. Your hands are open (grip values 0). A grip value is that hand's closure command (0 open, 1 every finger and thumb drive closing; a finger stops on what it touches). The ball is a free body: `held` in your state says which hand holds it (its fingers and its thumb or palm on it).

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played: with the hands), Art. 14 (control: a player holds a live ball), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 25 (travelling). Where this task departs from it:

- the player's hands: the H1-2's own Inspire hands (five fingers, six drives: four fingers, the thumb's flexion and rotation; the core's fingertip forces, 20 N, the thumb 30 N: twice the device's), closed by one command per hand; they hold the ball by contact and friction only (nothing is welded), a hand smaller than a player's (its span about 0.2 m against the ball's 0.24 m): one hand alone cannot hold the ball, two hold it pressed between the palms. Any shooting style is allowed; the ball is released when no hand touches it any more.
- Art. 14 (control) has no duration: here the ball is caught when both your hands have been on it together for 0.1 s without a break (a two-hand hold that lasts, not a tap that passes it on).
- Art. 13.1.2 (the ball is played with the hands only) is read strictly: from the pass until the shot is through, the ball may touch no part of you but your hands (fingers, thumb, palm and wrist); trapping it against the trunk, the arms or a leg is not a catch of this task, and a touch by a leg or a foot (always taken as deliberate: intent cannot be judged) is a violation.
- Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it.
- The pass is thrown by a two-wheel passing machine standing where the passer would stand (on the left wing), not by a team-mate: 0.40 m pneumatic wheels on speed-controlled 15 N m motors, the ball pushed into them from the machine's throat by a force-limited ram; always the same chest pass, at a fixed time, chest high on a flat arc at about 9.0 m/s (a chest pass: about 7-10 m/s), but without the backspin a player's thumbs give it (the wheels turn at the same speed: no spin).
- Art. 25.2.1: a ball caught with a foot off the floor is judged by the two-step rule without the pivoting it allows after a stop: after two steps no foot may touch the floor again while the ball is held.
- One attempt, no opponent, no rebound: a pass that is not caught on the fly, and touching the ball after the shot's release, end the attempt.

The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). It is passed to you about 2.0 s after the start by a passing machine 4.0 m away: a chest pass of about 9.0 m/s (the pass: the ball has left the machine's wheels). Your hands are five-finger hands that hold things only by contact and friction: one alone cannot hold the ball, two can (pressing it between the palms, open or with the fingers closed over it); it can slip out. A hand is its fingers, thumb, palm and wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it. In order: you catch the ball before it has touched the floor (the catch: both your hands have been on the ball together for 0.1 s without a break; touches before that, of one hand or both, are allowed); from the catch the ball stays in your hands until you let go of it (the shot's release: the moment no hand is on it; a ball that slips or drops out of your hands is released too); its centre goes down through the ring's plane inside the ring and on down to one ball diameter below it, which is the success. Travelling, from the catch to the shot's release: if both your feet are on the floor at the catch, the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor (in the steps case below: any foot that is on the floor, from where it stood or was put down), and once it has left the floor no foot may touch the floor again before the ball has left your hands. If a foot is off the floor at the catch, you may take at most 2 steps (a step: a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; not the same foot twice in a row), and after them no foot may touch the floor again before the release. You fail if anything of you touches the ball before it is passed; if, from the pass until the release, the ball touches any part of you other than your hands; if the passed ball touches the floor before you have caught it; if you travel; if any part of you touches the ball more than 0.05 s after the shot's release (it cannot be taken again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **catch → release → through the ring**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 15 s (1500 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 1500 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
                                       # ("real_hands": each hand's closure command, its drives' positions and torques, what it holds)
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
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

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
- **The left and right hands are the robot's own**: the H1-2's Inspire RH56DFX five-finger hand (6 self-locking linear drives for 12 joints: the thumb's rotation and flexion, one drive per finger with its two joints coupled; Unitree's H1-2 kinematics) with H2-class fingertip forces: 20 N per finger and 30 N the thumb, 2 x the RH56DFX's 10 / 15 N (Unitree's H2 Plus offers 20 N Sharpa Wave hands; Inspire's RH56E2 gives 28 / 30 N). 6 drives per hand; fingertip forces 20 N, 30 N (the thumb the largest); each drive is position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open). `grip_left` and `grip_right` are the closure commands: one value per hand from 0 (open) to 1 (closed), all of that hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip, turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's position and torque (`spec()` / `s.hold()` list the drives with their limits).
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
