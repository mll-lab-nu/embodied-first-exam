# Embodied Olympics · volleyball bump (privileged)

## Task
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one contact,
above net height and into the setter's target at the net. This is a *fixed instance*: the same venue and start every
time. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

You face the net (+x), which is 6 m ahead of you; your end line is 3 m behind you. A volleyball machine stands on the
floor behind the far end line, its wheels 2.6 m above the floor, 15.6 m ahead of you and 1.5 m to your left, aimed at
your court. About 3.0 s after the start it serves the ball at about 14 m/s; it climbs to a little over 4 m, clears the
net by more than a metre and comes down at about 40 degrees below the horizontal and 11.4 m/s. About 1.4 s after the
serve it is 1 m above the floor about 0.9 m in front of you and 0.8 m to your left; untouched it lands level with you,
about 0.75 m to your left. The setter's target is painted on the floor at the net, ahead of you and to your right.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is to
your left, +z is up; the floor is z = 0.

You have the full simulator to develop with; you hand in a trajectory of robot actions.

## Goal
Success: with one forearm pass you send the served ball up above net height and down into the setter's target at the
net.

The referee judges these stages, in order: **pass → above the net height → in the target**. An attempt ends at the
success, at the first foul or after 10 s (1000 control steps) of robot time.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `actions`, one sim row of 141 floats per
control step. It is replayed open-loop from the fixed start, one row per control step, until the referee ends the
attempt, and it scores 1 if the replay succeeds, else 0: when the rows run out, the attempt is judged as it stands. At
most 1000 rows are used, and every one must be finite, also those after the attempt's end (a NaN or an infinite value
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
- you touch the ball machine or the waiting ball, or the ball before it has crossed the net
- the ball touches the floor before your pass
- anything but a forearm or a hand touches the ball, you hold it, or you touch it again after the pass
- the ball does not rise above net height, or comes down outside the target
- you touch the net, an antenna or a post, or a foot is on the floor wholly beyond the centre line
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
clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in
`stand` mode with the arms at rest: the `stand` row `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` (the waist and
arms at their start angles, both grips open) keeps it there.

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
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the 10
  cm along the forearm). Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Others
Rule book: FIVB Official Volleyball Rules. The rules here:
- A ball machine across the net sends the ball to you; pass it (a bump) after it has crossed the net, before it touches
  the floor.
- Play it with your forearms or hands in one clean contact; no holding, no second touch.
- The pass must rise above net height and come down on the target. Do not touch the net, an antenna or a post, or step
  wholly over the centre line.

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
