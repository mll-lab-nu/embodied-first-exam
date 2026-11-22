# Embodied Olympics · dunk (privileged)

## Task
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). Dunk the basketball with both hands: holding it in your two hands, jump, force it down through the ring from
above with both hands on it, and land on your feet. This is a *fixed instance*: the same venue and start every time. You
may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

A FIBA court. You stand under the basket's front, facing it (+x), inside the no-charge semi-circle: the point under the
ring's centre is 0.75 m ahead of your pelvis, the backboard's face 0.375 m beyond it. The ring's top edge is 2.39 m
above the floor. The ball is held between your two hands in front of your chest, its centre 1.13 m above the floor and
0.39 m ahead of your pelvis: the hands open (grip values 0, the fingers straight), the palms on its two sides (on these
hands it bears on the two thumbs, which lie a little proud of the palms), and the arms pressing the palms in (the start
command's shoulder roll and yaw are a little further in than the arms stand: the difference is the squeeze). A grip
value is that hand's closure command (0 open, 1 every finger and thumb joint closing towards its closed angle; a finger
stops on what it touches).

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is to
your left, +z is up; the floor is z = 0.

You have the full simulator to develop with; you hand in a trajectory of robot actions.

## Goal
Success: holding the ball in both hands, you jump, force it down through the ring from above with both hands on it, and
land on your feet.

The referee judges these stages, in order: **dunk → stand**. An attempt ends at the success, at the first foul or after
15 s (1500 control steps) of robot time.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `actions`, one sim row of 141 floats per
control step. It is replayed open-loop from the fixed start, one row per control step, until the referee ends the
attempt, and it scores 1 if the replay succeeds, else 0: when the rows run out, the attempt is judged as it stands. At
most 1500 rows are used, and every one must be finite, also those after the attempt's end (a NaN or an infinite value
scores 0).

Beside it: `gen.py`, the script that produced it, which must run and reproduce `trajectory.npz` reading nothing but
`/app/instance.json` and files under `/app/output/`; and `NOTES.md`, at most 20 lines: your final approach and why it
works, the approaches that failed and what each told you, what you downloaded or installed. The tooling appends its own
log, `rcb_session_log.jsonl`, to `/app/output/`: leave it there and do not set `RCB_SESSION_LOG`.

Save a trajectory as soon as you have one and overwrite it (with `gen.py` and `NOTES.md` to match) whenever you have a
better one; a run that ends with no file scores zero. Do not stop early.

Rules: write your own controller; public tools, robot models and pretrained controllers are allowed, a ready-made
solution to this task is not. Only `trajectory.npz` counts: changing the simulator's state while you develop changes
nothing in the grading.

The attempt fails at once if:
- the ball leaves your hands before it is in the ring, or touches the floor before the dunk
- the ball goes through the ring without both hands on it (a one-hand dunk, a tip, a shot or a drop), or comes up
  through it from below
- you travel, or you hang on the ring
- you fall: anything but your feet touches the floor, or your hips sink close to it

## Robot Interface
### Session
Already installed; run `python` from any directory:
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
s.replay()                             # replays s.rows from the fixed start, as the grading does
s.save_trajectory()                    # writes the SCORED file /app/output/trajectory.npz from s.rows
```

The simulator is deterministic on the CPU: the same rows from the frozen start give the same state, so a trajectory you
generate closed-loop (reading `s.state()`, `s.world`) replays exactly.
`python /opt/tools/rcb_rfo.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --out /tmp/r.json`
runs the same replay from the shell. The world's source is in `/opt/tools/rfo/` (the robot and action layer `world.py`,
the referee's toolkit `referee.py`) and this task's rules, as code, in `/opt/tools/rfo_task.py`; the robot library
(model, meshes, limits, the walking and running policies' weights) is in `/opt/roboolympics/`. You may build your own
copies of the world to plan or learn in.

### Actions
One row is one control step (10 ms; the physics runs at 1 kHz). Every row ends with `grip_left`, `grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds:
`walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are
clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot is in
`stand` mode, but not with the arms at rest (the venue text says how it starts). The `stand` row that keeps the start as
it is:
`[0, -0.43, 0.2529, -1.1318, 0.4546, 0.2074, -0.44, 1.24, -0.4301, -0.2529, 1.1321, 0.4546, -0.2073, -0.44, -1.24, 0, 0]`
(`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order): `left_hip_yaw`, `left_hip_pitch`, `left_hip_roll`, `left_knee`,
`left_ankle_pitch`, `left_ankle_roll`, `right_hip_yaw`, `right_hip_pitch`, `right_hip_roll`, `right_knee`,
`right_ankle_pitch`, `right_ankle_roll`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`,
`left_elbow_pitch`, `left_elbow_roll`, `left_wrist_pitch`, `left_wrist_yaw`, `right_shoulder_pitch`,
`right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow_pitch`, `right_elbow_roll`, `right_wrist_pitch`,
`right_wrist_yaw`. Each joint's range, speed and torque limits, default gains and start angle are in
`/app/instance.json` (`t0.robot`).

### What the platform does
- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a few
  seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own H1-2 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks
  at about 0.6 m/s and its heading drifts (close the loop on the IMU); `vy` up to 0.5 and `wz` up to 1.57 rad/s. At a
  zero command it marks time on the spot and recovers from small disturbances, which `stand` does not. When the legs
  come to it from another mode it first blends them to the stance (0.3 s) and holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The G1's
  two other walking policies (FALCON, AGILE) are not offered for it: driven on this robot (joints matched by name) they
  keep it upright but do not walk it.
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`,
  evaluated at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit.
  `joints` uses the default gains (`/app/instance.json` (`t0.robot`)) and zero `dq` and `tau`; `lowcmd` takes yours (kp
  up to 1500 / 800 / 400 and kd up to 30 / 20 / 10 for legs / waist / arms). Nothing balances the robot in these modes
  but your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets; what
  bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to about
  1.15 times that speed, where the motor's torque has fallen to zero).
- **The left and right hands are the robot's own**: the H1-2's Inspire RH56DFX five-finger hand (6 self-locking linear
  drives for 12 joints: the thumb's rotation and flexion, one drive per finger with its two joints coupled). 6 drives
  per hand, with fingertip forces of 20 N per finger and 30 N for the thumb (twice the stock hand's); each drive is
  position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open).
  `grip_left` and `grip_right` are the closure commands: one value per hand from 0 (open) to 1 (closed), all of that
  hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip,
  turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide
  with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's
  position and torque (`spec()` / `s.hold()` list the drives with their limits).
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Others
Rule book: FIBA Official Basketball Rules. The rules here:
- A dunk at a lowered basket (the ring 2.39 m high). You start standing with the ball in your hands, as a player who has
  just ended a dribble: no dribble, and the ball may not touch the floor before the dunk.
- Travelling: at most 2 steps with the ball in your hands.
- The dunk: force the ball down through the ring with both hands on it; it may not come up through the ring first.
- You may touch the basket for at most 0.3 s in all. After the dunk let go of the ball and stand on your feet for 1 s.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included. Do not look up a ready-made solution to this exact task, such as the benchmark's reference solutions; trials
  are reviewed.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`, instant), all while you develop.
