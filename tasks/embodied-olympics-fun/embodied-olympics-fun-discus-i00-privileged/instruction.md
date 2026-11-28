# Embodied Olympics · discus (privileged)

## Task
Throw the discus from the circle so that it lands inside the sector at least 15 m out, then leave the circle from its
back half and stand.

## Goal
Success: from the circle you throw the discus with your right hand so that it lands inside the sector at least 15 m from
the circle, then leave the circle from its back half and stand still.

The referee judges these stages, in order: **release → landing → exit**. An attempt ends at the success, at the first
foul or after 60 s (6000 control steps) of robot time.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`. It holds `actions`: one sim row of 141
floats per control step. It is replayed open-loop from the fixed start, one row per control step, until the referee ends
the attempt. It scores 1 if the replay succeeds, else 0. If the rows run out before the referee calls a success, it
scores 0. At most 6000 rows are used. Every row must be finite, including rows after the attempt's end; a NaN or an
infinite value scores 0.

Put two files beside it. `gen.py` is the script that produced it: it must run and reproduce `trajectory.npz`, reading
nothing but `/app/instance.json` and files under `/app/output/`. `NOTES.md` has at most 20 lines: your final approach
and why it works, the approaches that failed and what each told you, and what you downloaded or installed. The tooling
appends its own log, `rcb_session_log.jsonl`, to `/app/output/`: leave it there and do not set `RCB_SESSION_LOG`.

Save a trajectory as soon as you have one. Whenever you have a better one, overwrite it and update `gen.py` and
`NOTES.md` to match. A run that ends with no file scores zero. Do not stop early.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, policies trained for it); trials are reviewed.

The attempt fails at once if:
- before the discus lands, any part of you touches the top of the rim or the ground outside the circle; or, before you
  have left correctly, the front half
- before the release the discus is touched by anything but your right hand or rests on the hand without its hold; after
  the release you hold or touch it again
- it lands outside the sector or short of 15 m
- you fall

## Robot Interface
You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on
MuJoCo). You have the full simulator to develop with; you hand in a trajectory of robot actions. This is a *fixed
instance*: the same venue and start every time. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy. Units are metres. `s.state()` uses the venue's frame. At the start,
your pelvis is roughly above the point x = -0.6, y = 0, and you face +x, with +y to your left. +z is up. The floor is at
z = 0.

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
s.image("head_left")                   # a camera's RGB image (270 x 480; the cameras: `head_left`, `head_right`, `venue`, `sector`)
s.proprio()                            # the robot's own sensors as one row (s.ep.proprio_layout)
s.reset()                              # back to the frozen start (unlimited, instant); clears s.rows
s.replay()                             # replays s.rows from the fixed start, as the grading does
s.save_trajectory()                    # writes the SCORED file /app/output/trajectory.npz from s.rows
```

The simulator is deterministic on the CPU: the same rows from the frozen start give the same state, so a trajectory you
generate closed-loop (reading `s.state()`, `s.world`) replays exactly.
`python /opt/tools/rcb_rfo.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --out /tmp/r.json`
runs the same replay from the shell. The world's source is in `/opt/tools/rfo/` (the robot and action layer:
`world.py`). The robot library (model, meshes, limits, the walking and running policies' weights) is in
`/opt/roboolympics/`. You may build your own copies of the world to plan or learn in.

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
clipped. `grip_right`: the hand's closure command, 0 (open) to 1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, <
0.5 opens it. At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it
starts). The right hand is closed on `discus` at the start (closure command 1): opening it lets go. The `stand` row that
keeps the start as it is: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.57, 0, 0, 0, 1]` (`s.hold()` returns it); a `stand`
row with other angles or grips moves the arms or lets go.

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
  at about 0.6 m/s, and its heading drifts, so close the loop on the IMU. `vy` goes up to 0.5 and `wz` up to 1.57 rad/s.
  At a zero command it marks time on the spot. Unlike `stand`, it recovers from small disturbances. When you switch to
  `walk` from another mode, it first blends the legs to the stance (0.3 s), then holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The G1's
  two other walking policies (FALCON, AGILE) are not offered for this robot. Run on it (joints matched by name), they
  keep it upright but do not make it walk.
- **`joints` / `lowcmd`** give you direct control. Each motor's torque is
  `kp (q − q_measured) + kd (dq − dq_measured) + tau`, computed at 1 kHz while your row is held for its 10 ms, then
  limited by the motor's torque-speed curve and torque limit. `joints` uses the default gains from `/app/instance.json`
  (`t0.robot`), with zero `dq` and `tau`. `lowcmd` uses the gains, `dq` and `tau` you send (kp up to 1500 / 800 / 400
  and kd up to 30 / 20 / 10 for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range. In each 10 ms step, a target moves at most the joint's speed
  limit × 10 ms away from the target in force. Joints that an action type does not include keep their current targets.
  The speed limit applies only to targets. The joint itself is bounded by the motor's torque-speed curve: with a
  `lowcmd` feed-forward torque, a joint can turn up to about 1.15 times that speed, where the motor's torque has fallen
  to zero.
- **The right hand is the robot's own**: the H1-2's Inspire RH56DFX five-finger hand. It has 6 self-locking linear
  drives for 12 joints: one each for the thumb's rotation and flexion, and one per finger, which drives that finger's
  two coupled joints. Each hand has 6 drives, with fingertip forces of 20 N per finger and 30 N for the thumb (twice the
  stock hand's). Each drive is position-servoed and force-limited: closing stops when the drive reaches its force limit,
  and a larger load drags it open. `grip_right` is the closure command: one value per hand from 0 (open) to 1 (closed),
  all of that hand's drives following it together. The hand holds only by contact and friction (no weld), so what it
  holds can slip, turn or drop. It holds an object while the fingers and the thumb or palm touch it. The fingers, thumb
  and palm collide with the world and with the rest of your own body. The proprioception reports each hand's closure and
  every drive's position and torque (`spec()` / `s.hold()` list the drives with their limits).
- **The left hand** has no working fingers here. It carries a fist pad: a 4.4 × 8 × 10 cm box beyond the wrist, with its
  10 cm side along the forearm. Nothing in this task is grippable: `grip_left` has no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`, instant), all while you develop.
