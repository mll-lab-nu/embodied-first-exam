# embodied-olympics clean-and-jerk — instance i00

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
via Python. **Task:** Clean and jerk the barbell: lift it from its blocks to your shoulders, then to locked arms overhead, and hold it there motionless until the down signal.

This is a *fixed instance*: the same venue and start every time. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## The venue
You stand upright in the middle of the platform, facing +x, your soles 0.1 m above the floor, in the rest pose (upper arms down, forearms forward). The barbell lies across your front, parallel to your shoulders and centred on you, its sleeves on two blocks (0.30 m along x, 0.20 m along y, 0.35 m high, centred 0.8 m to either side of you): its axis is 0.2 m ahead of your pelvis and 0.375 m above the platform, just beyond your toes (they reach 0.164 m ahead of your pelvis). Your shoulder joints are 1.46 m above the platform when you stand, 0.30 m apart; the centre of your head is at 1.70 m, its top at 1.79 m; your knee joints are at 0.48 m. In the `stand` action's stance your knees are bent by about 21 degrees, and your elbows are at a right angle in the rest pose: neither is extended. Your elbow joints have no stop at the straight arm (they bend both ways from it). Both hands are open (grip values 0): a grip value is that hand's closure command (0 open, the fingers straight; 1 every finger and the thumb closing; a finger stops on what it touches). The barbell is a free body: `held` in your state says which hand grasps it with its fingers and its thumb or palm. The platform's edges are 2 m away in every direction.

Frame: metres; the origin is on the floor under your pelvis at the start, +x is the way you face at the start, +y is
to your left, +z is up; the floor is z = 0. 

## The rules
**Rule book:** IWF Technical and Competition Rules & Regulations (International Weightlifting Federation; 2020 edition, article numbers quoted from memory of the 2020s editions): 2.3 the clean and jerk, 2.5 incorrect movements, 3.1 the platform, 3.3 the barbell (the women's bar: 15 kg, 2.01 m, a 25 mm grip section 1.31 m long, sleeves 50 mm thick; collars 2.5 kg; the lightest barbell in competition, women: 21 kg = the bar, two collars and two 0.5 kg discs). Where this task departs from it:

- 3.3 (the barbell): the barbell is an aluminium technique bar, American Barbell's ATB-5-E (5 kg, 1.835 m, a 25 mm grip section 1.31 m long as the women's bar's, sleeves 50 mm thick), training equipment, not a competition barbell (the women's bar is 15 kg, the lightest competition barbell 21.0 kg), without collars or discs. The reason is the robot's arms: with the women's 15 kg bar the turnover from the hang to the shoulders asks 1.08 to 1.17 times what the elbow and shoulder motors give, and with 10 kg the robot topples at the turnover, so neither a heavier bar nor a faster turnover is open. There is no choice of weight and no progression of attempts, because the task is one attempt
- 3.1 and 3.3 (the bar on the platform, on its discs): the bar rests by its sleeves on two lifting blocks 0.35 m high (a block clean & jerk, a standard training form), so that its axis is 0.375 m above the platform; a competition bar on its 0.45 m discs lies at 0.225 m, but the squat to that height is out of the robot's reach: its hips would have to flex past where the hip links meet the pelvis (the robot's own body collides with itself), and every squat tried fell back onto a thigh. Without discs or blocks the bar would lie on its inner collars 0.04 m above the platform, where the hands' curled fingers cannot close round it without touching the platform
- 3.3 (what the maker does not give): the bar's 5.0 kg are split 1.74 kg for the shaft and the rest between the two revolving sleeves with their inner collars (0.08 m across, 0.03 m wide); these are estimates
- 3.3 (the grip): each hand is the H1-2's own Inspire five-finger hand (six self-locking drives; 20 N at each fingertip, 30 N at the thumb), open at the start; it holds the bar by its fingers' and palm's contact and friction alone (nothing is welded; no chalk, no hook grip with the thumb under the fingers), and the bar can slip, turn in the hand and drop. A hand holds the bar while the grip section touches that hand's fingers (closed round it; a break of up to 0.05 s, the contact flickering under a load, is not letting go)
- 2.3.1 (the clean): the referee judges the end of the clean, not the movement: the bar at the shoulders (its axis within 0.15 m of both shoulder joints; the robot's rigid chest stands 0.07 m ahead of them, so the bar cannot lie on the collarbones) with the legs extended, the feet on one line and everything motionless for 0.5 s (the rule says "motionless" and gives no time); that the bar came there in a single movement is not judged, because that needs a human reading of the pull
- the rules' "at the shoulders" and "overhead" assume a lifter who stands under the bar; so that neither position can be reached bent over or with the bar behind the back, in both the trunk must be upright (the cosine of its tilt at least 0.94), the bar's centre no more than 0.25 m (horizontally) from the point midway between the shoulder joints, and the bar within 20.0 degrees of the line through the shoulder joints (seen from above)
- 2.5 (incorrect movements): judged here are the unfinished attempt above knee height, a part other than the feet on the platform, leaving the platform, the incomplete extension of the arms and legs at the finish and the feet not on one line; not judged, because they need a human judge's reading of the movement: the press-out and a pause while the arms extend, pulling from the hang, the bar touching the thighs, the elbows or upper arms touching the knees or thighs, an uneven extension of the arms, the oscillation of the bar before the jerk
- 2.3.2 (the finish): "fully extended" is read from the robot's joints: each elbow within 10.0 degrees and each knee within 10.0 degrees of straight; "motionless" is the bar and the pelvis slower than 0.1 m/s; the three referees' "down" signal is given by the simulator when the final position has been held for 2.0 s, and the attempt ends there: lowering the bar after the signal is not part of the task
- 6.6 (the clock): the athlete's one minute runs here from the start of the episode to the down signal (60 s for the whole attempt); the rule's minute runs from the call to the platform to the start of the lift, and there is no call here

The barbell is an aluminium technique bar (5.0 kg, 1.835 m long; the grip section between the inner collars is 1.31 m long and 0.025 m thick; the sleeves are 0.2325 m long and 0.05 m thick and revolve on the bar), without discs or collars: 5.0 kg. It rests by its sleeves on two lifting blocks (0.35 m high) standing on the competition platform (4.0 m by 4.0 m, 0.1 m high), on which you stand. Your hands are five-finger hands, open at the start; a hand holds the bar while the bar's grip section touches that hand's fingers (a break of up to 0.05 s is not letting go); they hold it by contact and friction only, so it can slip, turn in the hands and drop. Lift-off: the bar may leave its blocks only in both hands: you fail the moment the bar's axis is more than 0.03 m above where it lies at rest while fewer than two hands hold it. The attempt: once the bar's centre has been 0.48 m above the platform (knee height) the lift must be finished: from then on you fail if either hand lets go or if any part of the barbell touches the platform or a block before the down signal. The clean: the bar must first rest at your shoulders: its axis within 0.15 m of both shoulder joints, both hands on it, both knees within 10.0 degrees of straight, both feet on the platform and on one line, the bar and your pelvis slower than 0.1 m/s, and you under the bar (your trunk upright: the cosine of its tilt at least 0.94; the bar's centre no more than 0.25 m, horizontally, from the point midway between your shoulder joints; the bar, seen from above, within 20.0 degrees of the line through them), with the attempt begun (the bar has been above knee height and touches nothing but you), all of it without a break for 0.5 s. You fail if the bar's axis is more than 0.25 m above the centre of your head before that (a lift from the platform to overhead in one movement is a snatch). The jerk and the finish: after the clean, bring the bar overhead. The final position is: the bar's axis at least 0.25 m above the centre of your head, both hands on it, both elbows within 10.0 degrees of straight (the angle between the upper arm's and the forearm's long axes), both knees within 10.0 degrees of straight (the angle hip, knee, ankle), both feet on the platform and on one line (their centres no more than 0.05 m apart along the horizontal direction square to the bar; under a bar tilted more than 60.0 degrees from level the feet never count as on one line), the bar and your pelvis slower than 0.1 m/s, and you under the bar as in the clean (trunk upright, the bar's centre over the middle of your shoulders, the bar along your shoulder line). Once it is held for 2.0 s without a break the down signal is given: that is success, and the attempt ends. At any time you fail if a part of you other than your feet touches the platform, if any part of you touches a block, if any part of you or of the barbell touches the floor beside the platform, or after 60 s. There is no other fall rule: you may squat as low as you like, and the bar may touch your body.

A referee decides this from the simulator's state after every physics step (1 ms): the events that must happen, in
order, are **lift-off → clean → overhead → down signal**. The attempt ends at the success (that moment is the success), at the first rule violation,
or after 60 s (6000 control steps). `s.status()` shows the referee's record at any time:
`stages`, `failed` (the rule that ended the attempt), `metrics`, `events`.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): `actions`, one sim row of 141 floats per control step. Replayed open-loop from the frozen start in one fresh process, one row per control step until the referee ends the attempt; scored 1 if the replay succeeds, else 0. The rows must reach the success: when they run out the attempt is judged as it stands. At most 6000 rows are used; every one of them must be finite, also those after the attempt's end (a file with a NaN or an infinite value scores 0) |
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
