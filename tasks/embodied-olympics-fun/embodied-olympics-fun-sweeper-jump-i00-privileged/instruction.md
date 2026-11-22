# Embodied Olympics · sweeper jump (privileged)

## Task
You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on
MuJoCo). Jump the sweeper: standing on your podium, jump over the padded boom each time it sweeps round, 3 times in a
row without being hit, then stand still on the podium. This is a *fixed instance*: the same venue and start every time.
You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general
policy.

A Meltdown sweeper on a level bed: the motion base, a column 0.4 m in radius, stands 3.2 m in front of you (you face
it); you stand in the middle of your podium, its top 0.4 m above the bed. The boom sticks out from the base at shin
height and turns counter-clockwise seen from above: it comes at you from your left. At the start it points 200.0 degrees
of its turn before your podium (on the far side of the base), turning; it will be over your podium in about 4.17 s.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is to
your left, +z is up; the floor is z = 0.

You have the full simulator to develop with; you hand in a trajectory of robot actions.

## Goal
Success: you jump the sweeping boom three times in a row without being hit, then land on your feet on the podium and
stand still for a second before it comes round again.

The referee judges these stages, in order: **jump 1 → jump 2 → jump 3 → landing → stand**. An attempt ends at the
success, at the first foul or after 30 s (3000 control steps) of robot time.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `actions`, one sim row of 151 floats per
control step. It is replayed open-loop from the fixed start, one row per control step, until the referee ends the
attempt, and it scores 1 if the replay succeeds, else 0: when the rows run out, the attempt is judged as it stands. At
most 3000 rows are used, and every one must be finite, also those after the attempt's end (a NaN or an infinite value
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
- the boom touches any part of you (grabbing or holding it is a hit too), or passes through a foot that is not above it
- any part of you touches the bed round the podium or the motion base
- you fall: anything but your feet touches the floor, or your hips sink close to it, or the landing after the last jump
  is not on your feet

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
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `overview`)
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
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds:
`walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile`
-0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets
are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's
grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row
`[0, 0, 0, 0.2, 0.2, 0, 1.28, 0, 0, 0, 0.2, -0.2, 0, 1.28, 0, 0, 0, 0, 0]` (the waist and arms at their start angles,
both grips open) keeps it there.

Joint order everywhere (Unitree's SDK order): `left_hip_pitch`, `left_hip_roll`, `left_hip_yaw`, `left_knee`,
`left_ankle_pitch`, `left_ankle_roll`, `right_hip_pitch`, `right_hip_roll`, `right_hip_yaw`, `right_knee`,
`right_ankle_pitch`, `right_ankle_roll`, `waist_yaw`, `waist_roll`, `waist_pitch`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_roll`, `left_wrist_pitch`, `left_wrist_yaw`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_roll`,
`right_wrist_pitch`, `right_wrist_yaw`. Each joint's range, speed and torque limits, default gains and start angle are
in `/app/instance.json` (`t0.robot`).

### What the platform does
- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a few
  seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own G1 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s; `vy` up to 0.5 and `wz` up to 1.57 rad/s; it follows with lag and barely moves in its first second. At
  a zero command it marks time on the spot (the pelvis sways and drifts a centimetre or two per second) and recovers
  from small disturbances, which `stand` does not. When the legs come to it from another mode it first blends them to
  the stance (0.3 s) and holds a zero command until the robot is steady (up to 2 s). It was trained with the arms at
  rest: moving the arms and the waist disturbs it.
- **`walk_falcon`** and **`walk_agile`** are two more walking policies for the G1's legs, with the same row as `walk`
  (you keep the waist and the arms): FALCON (trained with arm motions and forces on the hands) and AGILE's
  velocity-height policy (trained while the arms and the waist moved), the released weights run in numpy at 50 Hz on
  their own leg gains (kp 100 / 100 / 100 / 200 / 20 / 20 per leg). Both hold still and follow the command better than
  `walk` while the arms move or carry something; FALCON also adds a small correction to the wrists. FALCON zeroes speeds
  below 0.2 m/s and turns below 0.2 rad/s and stands with the pelvis at about 0.74 m; AGILE zeroes commands of norm
  below 0.1, stands lower (about 0.68 m) and barely turns on the spot below about 0.7 rad/s (walking at 0.2 m/s or more
  it turns as asked). Their command ranges are in the action table. A walker takes the legs at once, from where they are
  (its memory starts afresh); `walk`, the other walker and `run` take them from it the same way. Going from a walker
  straight to `stand` usually ends in a fall (`stand` holds Unitree's stance and does not balance): give `walk` a zero
  command for about 2 s first.
- **`run`** runs the platform's athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
  above that; the command changes at most 1.5 m/s per second), `|vy|` ≤ 0.12 m/s, `|wz|` ≤ 0.5 rad/s. `run_arms` gives
  you the arms while it keeps the legs and the waist; taking the arms away from its swing disturbs it. Switching to
  `stand`, `walk` or `joints` above about 0.6 m/s usually ends in a fall: slow down first (from 2.4 m/s that takes about
  2 s and 2.3 m).
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`,
  evaluated at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit.
  `joints` uses the default gains (`/app/instance.json` (`t0.robot`)) and zero `dq` and `tau`; `lowcmd` takes yours (kp
  up to 1000 / 500 / 400 and kd up to 20 / 15 / 10 for legs / waist / arms). Nothing balances the robot in these modes
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
Rule book: none (it is a party and amusement game): players stand on podiums round a motion base whose padded booms
sweep round; jump the low boom each time it comes round; do not grab, hold or ride it; a player who is hit is out. This
task's rules:
- Players stand on podiums round a motion base whose padded booms sweep round: jump the low boom each time it comes
  round; it may not touch you (grabbing it counts as a hit).
- Land on your podium each time and touch nothing round it; after the last jump land on your feet and stand still for 1
  s.

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
