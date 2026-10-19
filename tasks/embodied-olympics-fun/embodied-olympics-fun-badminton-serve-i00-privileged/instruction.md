# embodied-olympics badminton-serve — instance i00

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 34 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Serve: standing in your right service court, let the shuttle go from your left hand and hit it with the racket in your right hand, base first and below 1.15 m, over the net into the receiver's service court diagonally opposite.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand in your right service court facing the net (+x), whose plane is 2.45 m ahead of your pelvis; the middle of the centre line is 0.45 m to your left, so your service court reaches from the near edge of the centre line to the outer edge of the singles side line 2.59 m to the right of the centre line's middle, and from the short service line (its edge nearest the net 1.98 m from the net) back to the back boundary line 6.70 m from the net. The receiver's right service court, your target, is beyond the net on the other side of the centre line: from 1.98 m to 6.70 m beyond the net, from the centre line to the singles side line 2.59 m to the left of the centre line's middle. Your forearms point forward; your left gripper's jaws pinch the shuttle's feathers, the shuttle hanging cork down; your right gripper's jaws clamp the racket's handle at its butt end, the handle along the fingers, the racket pointing forward and down from the hand, its strings facing the way the jaws close.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** BWF Laws of Badminton (BWF Statutes, Section 4.1, the edition in force in 2025): Law 1 (the court and the court equipment: 13.40 m x 6.10 m, 40 mm lines that are part of the area they bound, the singles side lines 5.18 m apart, the short service lines 1.98 m from the net; the net 1.524 m high at the centre and 1.55 m over the doubles side lines, 760 mm deep; the posts on the doubles side lines), Law 2 (the shuttle: 16 feathers, a cork base 25-28 mm across, 4.74-5.50 g), Law 3 (testing a shuttle for speed), Law 4 (the racket: at most 680 mm long and 230 mm wide), Law 9 (the service: 9.1 a correct service, 9.2 its start), Law 10 (singles: the service courts), Law 13 (faults). Where this task departs from it:

- Laws 7, 8, 10.2-10.3, 11 (the toss, the scoring, the rally, the receiver): one service only, with no receiver; a fault ends the attempt as a failure, a correct service that lands in the receiver's service court is the success; singles at the score 0 (so from the right service court, into the diagonally opposite one)
- Law 9.1 (no undue delay; the receiver ready): there is no receiver; the service may come at any time within the episode
- Law 9.2 (the start of the service is the first forward movement of the server's racket head once the players have taken their positions): taking position cannot be told from the robot's other arm movements; made measurable: a forward movement of the racket head starts when its speed towards the net rises above 0.5 m/s and lasts until that speed falls below 0.1 m/s; the service starts at the earlier of the release of the shuttle and the start of the head's forward movement that brings it to the hit; a forward movement of the head that starts after the release and stops before the hit is a fault (Law 9.1: the racket's movement continues forwards until the service is delivered)
- Law 9.1 (some part of both feet in contact with the court in a stationary position): made measurable: from the start of the service to the hit each foot touches the floor (a gap of at most 0.02 s, the chatter of a contact, still counts as touching) and moves at most 0.03 m
- Law 9.1 (the server lets go of the shuttle and hits it): the shuttle starts pinched by its feathers in the left hand's two-finger gripper and is let go by opening it; it counts as let go once it has touched nothing of yours for 0.03 s (the release is the moment it came free), so that the jaws' last brush as they open is part of the holding; so that the hand does not throw the service, the shuttle may move at most 4.0 m/s when it reaches the racket and must leave it faster than it came; one release per service (a shuttle that has been let go may be touched by nothing of yours but the racket)
- Law 9.1 (the server's racket initially hits the base of the shuttle): judged at the physics step (1 ms) of the racket's first contact: the cork base must be touching the racket then (the feathers may touch it in the same step)
- Law 9.1 (the server's racket): the racket must be held in the right hand throughout the attempt: it counts as held while it touches both jaws of the right gripper, and a break of at most 0.05 s (the contact chatter of a fast swing) is still held
- Law 13 ('caught and held on the racket and then slung', 'hit twice'): made measurable: racket contacts less than 0.03 s apart are one hit, a later one is a second hit, and a contact longer than 0.02 s is a carry
- Law 9.1 (the flight upwards from the racket): judged when the hit is over (0.03 s after its last contact): the shuttle is then rising
- Law 13 (the shuttle landing outside the boundary lines; lines are in): the landing point is where the shuttle first touches the floor
- Law 4 (the racket): a rigid racket (no string-bed deflection, no frame flex); its strings meet the shuttle with a restitution of 0.5
- Law 1 (the net): a 2 cm thick wall instead of a mesh of cord; a shuttle that meets it is stopped by a stiff, strongly damped contact
- the hall's air: still (no draught), at sea level and 15 C; the shuttle's spin about its axis is not driven by its feathers

The court is the BWF court: 13.4 m long and 6.1 m wide (between the doubles side lines), with the singles side lines 5.18 m apart, a short service line 1.98 m from the net on each side, a centre line from each short service line to the back boundary line, and a doubles long service line 0.76 m inside each back boundary line; every line is 0.04 m wide and is part of the area it bounds (the centre line is shared by the two service courts). This is singles: a service court reaches from the short service line to the back boundary line and from the centre line to the singles side line. The net stands across the middle, its top 1.524 m high at the centre and rising in a straight line to 1.55 m at the posts on the doubles side lines; it is 0.76 m deep, with open space under it. The shuttle is a feathered shuttle (5.1 g, a cork base 26 mm across, 16 feathers whose tips form a circle 64 mm across) with a shuttle's heavy air drag (it falls at 6.8 m/s at most) that turns it to fly cork first; it starts pinched by its feathers in your left hand's gripper, cork down. The racket (0.67 m, 85 g, strung area 0.27 m by 0.21 m) is held in your right hand's gripper by friction alone: it can slip, turn and fall. You serve from your right service court into the receiver's right service court, the one diagonally opposite. The racket must stay in your right hand all the time: it touches both of the gripper's jaws, and a break of more than 0.05 s is a fault. In order: (1) the release: your left hand lets the shuttle go; it is let go once it has touched nothing of yours for 0.03 s (the release is the moment it came free; until then it is still held), and from then on nothing of yours but the racket may touch it. (2) the hit: the racket hits the shuttle before it reaches the floor. At the first instant of contact the cork base is touching the racket (the feathers touching it first, alone, is a fault), the whole shuttle is lower than 1.15 m above the floor, the shuttle moves at most 4.0 m/s, and the racket head is moving towards the net. A forward movement of the racket head starts when its speed towards the net rises above 0.5 m/s and lasts until that speed falls below 0.1 m/s. The service starts at the earlier of the release and the start of the racket head's forward movement that brings it to the hit; a forward movement that starts after the release and stops before the hit is a fault. From the start of the service to the hit both feet stand in your service court, touching neither its lines nor anything outside it, each foot touching the floor all the time (a gap of at most 0.02 s still counts as touching) and moving at most 0.03 m. The hit is one contact: racket contacts less than 0.03 s apart are one hit, it lasts at most 0.02 s, and when it is over (0.03 s after its last contact) the shuttle is faster than it was when it reached the racket and is rising. (3) the shuttle passes the net's plane over the net's top edge, between the posts (it may touch the net). (4) its first contact with the floor (contacts less than 0.02 s apart are one) is inside the receiver's right service court, the lines included: that is the success. You fail on any fault: the shuttle reaching the floor, touching the net or passing the net's plane without a hit; the racket touching the shuttle before you let it go; the shuttle touching you, or touched by anything of yours but the racket, after the release; a hit that breaks a rule of (2); a second hit; a carry; the shuttle passing through or under the net or outside the posts, touching a post, landing on your side or outside that service court; the racket leaving your right hand, or touching the floor, the net or a post, at any time; any part of you touching the net or a post; a fall; or 15 s passing. A fall is: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **release → hit → over the net → in**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 15 s (1500 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 151 floats per control step. Replayed open-loop from the frozen start in two fresh processes, one row per control step until the referee ends the attempt; scored 1 if both replays succeed and end in the same state, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 1500 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
                                       # (the grippers' "left_palm" and "right_palm" are their jaw centres; "real_hands": each gripper's
                                       # command, opening, opening speed, clamp force, what it holds, jaw centre and axes)
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
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left gripper's closure command, 0 (open, 90 mm) to 1 (closed); grip_right: the right gripper's closure command, 0 (open, 90 mm) to 1 (closed)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each gripper's closure command, 0 (open) to 1 (closed). At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The left gripper is closed on `shuttle` at the start (closure command 0.365): opening it lets go. The right gripper is closed on `racket` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0, 0.1, 0, 0, 1.5708, 0, 0, 0, -0.1, 0, 0, 0, 1, 0, 0.365, 1]` (`s.hold()` returns it); a `stand` row with other angles or grips moves the arms or lets go.

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
| 15 | `left_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0 |
| 16 | `left_shoulder_roll` | [-1.5882, 2.2515] | 37 | 25 | 300 | 6 | 0.1 |
| 17 | `left_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0 |
| 18 | `left_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 0 |
| 19 | `left_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 1.5708 |
| 20 | `left_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 21 | `left_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 22 | `right_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0 |
| 23 | `right_shoulder_roll` | [-2.2515, 1.5882] | 37 | 25 | 300 | 6 | -0.1 |
| 24 | `right_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0 |
| 25 | `right_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 0 |
| 26 | `right_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0 |
| 27 | `right_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 1 |
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
- **The left and right hands carry a gripper** instead of a fist pad: Unitree's Dex1-1 two-finger parallel gripper
  (modelled: 0.55 kg; a housing of 78 × 67 × 63 mm on the wrist and two jaws 80 mm long beyond it, with rubber pads;
  90 mm stroke; the jaws close along the palm's normal). It holds only by contact and friction (no weld, no help):
  what it holds can slip, turn in the jaws or drop. `grip_left` and `grip_right` are the closure commands from 0 (open, 90 mm between the pads) to 1 (closed),
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
  device's rated 5 kg friction-grasp load.
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
