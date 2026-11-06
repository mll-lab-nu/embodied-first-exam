# embodied-olympics pole-vault — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 35 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Vault over the bar with the pole you carry: plant its tip in the box, leave the ground hanging on it, go over the bar between the uprights and come down on the mat, with the bar still on its pegs.

## The venue
You stand on the runway facing the box (+x), your pelvis 20 m before the zero line, in the middle of the runway; the runway goes on 20 m behind you. The pole lies level along +x in your right hand, held at its middle across the palm (grip value 1), the right arm hanging, the forearm pointing forwards and down; the left hand is open (grip value 0). A grip value is that hand's closure command (0 open, 1 every finger and thumb joint closing towards its closed angle; a finger stops on what it touches). The pole is a free body: `held` in your state says which hand holds it. The bar is red with white ends, the uprights grey, the mats blue; the box is the dark patch at the runway's end, the zero line white.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** World Athletics Competition and Technical Rules, 2024 edition: TR 28 (28.1 the bar may be moved up to 0.80 m from the zero line towards the landing area; 28.2 failures: (a) the bar does not remain on both pegs, (b) touching the ground or the landing area beyond the zero line with the body or the pole without first clearing the bar, (c) moving a hand up the pole after leaving the ground, (d) steadying the bar with a hand; 28.6 a runway of at least 40 m; 28.8 the box; 28.9-28.10 the uprights and pegs 4.28 to 4.37 m apart, the 4.50 m bar of at most 2.25 kg; 28.12 a landing area of at least 5 m x 5 m x 0.8 m with front pieces 2 m long), TR 25.17 (one minute for a trial). Where this task departs from it:

- TR 28.11 (vaulting poles: any material, length and diameter, a smooth surface): the pole is a 2.35 m (7 ft 8 in) pole rated 40.8 kg (90 lb), UCS's Junior Spirit, the lightest rating at or above the robot's 34.8 kg with its hands (the makers' rule: a pole rated at or above the athlete's weight); its mass (1.1 kg) and thickness (0.032 m) are estimates, the makers give none; it is rigid: it does not bend and stores no energy (the simulator has no validated model of a bending pole)
- the grip: each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index and middle 2 each, one motor per joint, at the device's torques); it holds the pole by its fingers' contact and friction alone (nothing is welded), so the pole can slide in the hand, turn in it and drop; a hand holds the pole while the pole touches its fingers and its thumb or palm. The pole collides with the robot's body as with everything else
- TR 28.8 (the box): it is sunk below the runway as the rule draws it, but only the pole (and the bar) can enter it; for the robot's feet it is covered at runway level; its side walls are planes
- TR 28.2(b), (c), (d) are judged geometrically: any contact of the robot or the pole with the ground or the mats beyond the zero line before the bar is cleared; a hand that holds the pole more than 0.05 m farther from its tip than the upper hand's grip was at lift-off; a hand on the bar for more than 0.1 s in all
- a vault is told from a jump by numbers (TR 28 does not define one): the take-off (the robot's last ground contact before the flight that clears the bar) must end a run-up, the pelvis' forward speed averaged over the last 0.5 s before it at least 2.5 m/s (a novice's short run-up is some 4 to 6 m/s), with the pole at least 20.0 degrees from vertical then (a planted pole leans some 25 to 35 degrees at a vault's take-off); in that flight the robot must hang on the pole for at least 0.15 s: a hand gripping it higher than the pelvis, its tip in the box pressed into it with at least 0.5 of the robot's weight, nothing of the robot on the ground; pushing down on the top of a pole (the pelvis above the hands) is not a hang; the pelvis and the feet (the ankle joints) must pass the bar's plane between the pegs and above the bar; the bar is cleared when every part of the robot is beyond its plane
- TR 28.2(a): the bar is judged 2.0 s after the landing; it is off its pegs when its centre is more than 0.05 m below its resting height; the pegs are square in section, the bar rigid
- TR 28.12 (the landing area): the mats are rigid boxes with a soft contact set from a pit's urethane foam (23 lb ILD: about 12.7 kPa; under a 0.5 m^2 back landing on the 0.8 m mat, 7.9 kN/m: MuJoCo's contact time constant 0.069 s for the robot's mass, critically damped), not a deforming foam; the mat's face behind the box slopes away at 45 degrees as the rule asks, the front pieces' faces beside the box are vertical, and the uprights stand in the mat without a recess; no wind
- TR 28 (the heights are the competition's: no rule sets a lowest one): one trial at one height, 1.0 m, set for this robot: its run-up (the running policy's 4 m/s) carries about 0.8 m of height above a centre of mass about 0.65 m up, and a rigid pole returns none of what the plant takes; a lower bar would lie on the landing area, which TR 28.12 makes 0.8 m high
- TR 28.1 (the athlete chooses where the bar stands, 0 to 0.80 m beyond the zero line): it stands 0.2 m beyond it, set for the short pole (there is no choice: the task is one trial)

World Athletics rules for the pole vault. You carry the pole (2.35 m long, 0.032 m thick, 1.1 kg; rigid: it does not bend) held at its middle in your right hand. Your hands are three-finger hands (a thumb, an index and a middle finger) that hold by contact and friction only, so the pole can slide in a hand, turn in it and drop; a hand holds the pole while the pole touches that hand's index or middle finger and its thumb or palm, anywhere along its length, and it can be let go and taken again. The pole touches the box, the mats, the uprights, the bar and your body (not the runway's surface around the box: it rests on the ground beside it as on a level floor). The runway (40.0 m, 1.22 m wide) leads along +x to the box, which is sunk into the ground: its bottom is 1.00 m long and slopes down from the runway's level at x = -1.08 m to 0.20 m below it at the foot of the stop board (x = -0.10 m); the stop board leans back to the zero line x = 0 at runway level; the box is 0.60 m wide at its front and 0.15 m at the foot of the stop board (your feet do not sink into it: for them it is covered). The bar (4.5 m long, 0.03 m thick, 2.25 kg) rests with its upper side 1.0 m above the ground on two pegs (0.055 m long, 0.013 m thick, 4.3 m apart) that point towards the landing area, 0.2 m beyond the zero line; pushed towards the landing area by half a peg's length, or lifted, it falls. The landing mat (5.0 m x 5.0 m, 0.8 m high, soft) begins 0.15 m beyond the zero line (behind the box its face slopes away at 45 degrees, so the pole can lean on over it); two front pieces of the same height flank the box for 2.0 m before it. The vault: (1) plant: the pole's tip is in the box while a hand grips the pole. (2) take-off: you leave the ground from a run-up, your pelvis' forward (+x) speed averaged over the last 0.5 s before the lift-off at least 2.5 m/s, with the pole at least 20.0 degrees from vertical at the lift-off; then you hang on the planted pole: for at least 0.15 s in that flight nothing of you touches anything but the pole and the bar while a hand grips the pole higher than your pelvis and the pole's tip rests in the box, pressed into it with at least 0.5 of your weight (the pole carries you: pushing down on its top with your pelvis above your hands is not a hang). (3) clearance: in that same flight your pelvis and both feet (the ankle joints) cross the plane of the bar's nearer edge between the pegs and higher than the bar's upper side (one that comes back over the plane has not passed it), and every part of you gets beyond that plane; you may touch the bar. (4) You come down, on any part of your body, with or without the pole. You succeed when 2.0 s after your landing the bar is still on its pegs. A fall is not a failure by itself. You fail if the bar drops more than 0.05 m at any time, whether you or the pole knocked it; if, before you have cleared the bar, anything of you or the pole touches the ground or the mats beyond the zero line; if your pelvis or a foot passes the bar's plane outside the pegs or not higher than the bar; if you clear the bar without such a take-off and hang (a jump without the pole, a standing jump on it, or a push on its top); if, in the flight of the vault, a hand holds the pole more than 0.05 m farther from its tip than your upper hand did at lift-off (climbing); if your hands touch the bar for more than 0.1 s in all (steadying it); or after 60 s (the time allowed for a trial).

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**plant → take-off → clearance → bar stays**. An attempt (an episode) ends at the success, at the first rule violation, or after 60 s
(6000 control steps) of robot time.

## Real-robot rules
- **Attempts.** The first episode starts when the service comes up. `r.reset()` abandons the running attempt (or
  follows one that has ended) and starts a new one from the same start; `spec()["budget"]["reset"]` says how many
  resets you have (5 here). **Only your last attempt is graded**, and a success ends the trial at once.
- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for
  s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `get_obs()` with
  no seconds is free.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`, `box`; `spec()["cameras"]` says
  where each is mounted). Not where you or any object is, not the
  referee's state. Once an attempt is over, every response carries the referee's call: `meta["outcome"]`
  (`"success"` or the rule that ended it) and `meta["stages_reached"]` of `meta["stages_total"]`.
- There is nothing to hand in: the service records your last attempt and grades it as it ran live (the referee's
  call). Keep the script that drives the robot at `/app/output/gen.py` and a `NOTES.md` of at most 20 lines (your
  approach, what failed, what you downloaded or installed) for the record: save them early and keep them current.
- Wall clock: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same
  way, so do not stop early: while you have attempts left, the run can still pass.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; it explains the protocol with another benchmark's example names: for this task `spec()` is
authoritative).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (6000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Rendering is most of a
call's cost: a controller's call should ask for no video (`video="none"`, `cameras=["head_left"]` or fewer) and read
`res.proprio`. With `interpolate="linear"` (the default) each control step's command is a straight line from the
command in force to the row; `"hold"` applies the row as it is.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 22) rows of the `walk` type
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 3 + arms 14 joint targets | 19 | the platform holds the legs in the stance; you give the waist's 3 and the arms' 14 joint targets (rad) (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets | 22 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `run` | `vx`, `vy`, `wz` | 5 | the running policy drives all 29 joints from the velocity command (it swings the arms) (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `run_arms` | `vx`, `vy`, `wz` + arms 14 joint targets | 19 | the running policy drives the legs and the waist; you give the 14 arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `joints` | all 29 joint targets | 31 | you give all 29 joint targets (rad); the default PD gains, no feed-forward (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `lowcmd` | all 29 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 29 targets, then 29 velocities, 29 torques, 29 kp, 29 kd | 147 | Unitree's LowCmd for all 29 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk_falcon` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | FALCON's walking policy (LeCAR-Lab, trained with arm motions and forces on the hands; it also nudges the wrists) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |
| `walk_agile` | `vx`, `vy`, `wz` + waist 3 + arms 14 joint targets (as `walk`) | 22 | AGILE's velocity-height walking policy (NVIDIA WBC-AGILE, trained while the arms and the waist moved) drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets (grip_left: the left hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch); grip_right: the right hand's closure command, 0 (open, the fingers straight) to 1 (every drive closing towards its closed position; fingers stop on what they touch)) |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57; `walk_falcon` -0.8 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `walk_agile` -0.5 ≤ vx ≤ 0.8, -0.5 ≤ vy ≤ 0.5, -1 ≤ wz ≤ 1; `run` and `run_arms` 0 ≤ vx ≤ 5, |vy| ≤ 0.12, |wz| ≤ 0.5. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left` and `grip_right`: each hand's closure command, 0 (open) to 1 (closed). At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it starts): the joint table's last column has the angles in force. The right hand is closed on `pole` at the start (closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0.2, 0.4, 0, 1.28, 0, 0, 0, 0, -0.5, 0.5, 1, 0.633, 0.5, 0, 0, 1]` (`spec()["start_command"]` has it, and `get_obs(seconds=...)` keeps the command in force); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains
(also in `spec()["robot_facts"]`):

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
| 15 | `left_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0.2 |
| 16 | `left_shoulder_roll` | [-1.5882, 2.2515] | 37 | 25 | 300 | 6 | 0.4 |
| 17 | `left_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0 |
| 18 | `left_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1.28 |
| 19 | `left_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0 |
| 20 | `left_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 21 | `left_wrist_yaw` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0 |
| 22 | `right_shoulder_pitch` | [-3.0892, 2.6704] | 37 | 25 | 300 | 6 | 0 |
| 23 | `right_shoulder_roll` | [-2.2515, 1.5882] | 37 | 25 | 300 | 6 | -0.5 |
| 24 | `right_shoulder_yaw` | [-2.618, 2.618] | 37 | 25 | 300 | 6 | 0.5 |
| 25 | `right_elbow` | [-1.0472, 2.0944] | 37 | 25 | 300 | 6 | 1 |
| 26 | `right_wrist_roll` | [-1.9722, 1.9722] | 37 | 25 | 100 | 2 | 0.633 |
| 27 | `right_wrist_pitch` | [-1.6144, 1.6144] | 22 | 5 | 60 | 1 | 0.5 |
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
- **The left and right hands are the robot's own**: Unitree Dex3-1 three-finger hand (0.71 kg; thumb 3 + index 2 + middle 2 joints, each its own motor; MuJoCo Menagerie g1_with_hands kinematics). 7 drives per hand; closing torques 0.49, 0.86 N m per joint; each drive is position-servoed and force-limited (closing stops where its force limit is reached, a larger load drags it open). `grip_left` and `grip_right` are the closure commands: one value per hand from 0 (open) to 1 (closed), all of that hand's drives following it together. The hand holds only by contact and friction (no weld): what it holds can slip, turn or drop; it holds an object while the fingers and the thumb or palm touch it. The fingers, thumb and palm collide with the world and with the rest of your own body. The proprioception reports each hand's closure and every drive's position and torque (`spec()` / `s.hold()` list the drives with their limits).
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the 29 joint positions
(`*_pos`, rad), their velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in
force (`*_target`, rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from
sensor; angular velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
`holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms,
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the grippers: `jaw_opening_left`, `jaw_speed_left`, `jaw_force_left`, `jaw_opening_right`, `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A
real G1 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
