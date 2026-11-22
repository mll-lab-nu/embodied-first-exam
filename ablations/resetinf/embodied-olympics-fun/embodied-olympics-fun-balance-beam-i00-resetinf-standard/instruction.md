# Embodied Olympics · balance beam (standard)

## Task
You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on
MuJoCo). Walk along the balance beam from the end you stand on to the other end and stand there, without anything
touching the floor.

At t = 0 you stand on the beam's near end, facing along it (+x), in a tandem stance: the left foot in front of the
right, both on the beam's centre line, the feet's centres 0.15 m and 0.39 m from the near end (the soles reach from 0.09
m to 0.52 m); your pelvis is 0.25 m from the near end and 0.75 m above the beam's top, so your soles are 1.25 m above
the floor. The beam is narrower than your normal stance (your feet are normally 0.24 m apart; each sole is 0.07 m wide),
so here the robot does NOT start in `stand` mode: it starts with all its joints holding the tandem pose on the default
gains, as after a `joints` row, and the hold command at t = 0 is a `lowcmd` row that keeps those targets (left alone,
the robot stays standing like that). A `stand` row would move the legs to the normal stance and a `walk` row would start
the normal gait: both put the feet beside the beam. The beam and its two supports (0.9 m from each end) are fixed; the
far end is marked yellow.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.

The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: you walk along the beam to its far end and stand there, both feet on the beam inside its end, upright and
steady for two seconds.

The referee in the service judges these stages, in order: **half way → far end → stand**. An attempt (an episode) ends
at the success, at the first foul or after 90 s of robot time, and a success ends the trial at once. Ending your session
ends the run, so do not stop early: while you have attempts left, the run can still pass.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`. Keep your scripts and a `NOTES.md` of at most 20 lines in `/app/output/` (your approach, what
failed, what you downloaded or installed): save them early and keep them current.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only your last attempt is graded.
- No privileged state: you get what the robot's own sensors give (its head cameras, joint encoders, motor torques and
  IMUs) and the venue's fixed cameras; not where you or any object is, not the referee's state. Once an attempt is over,
  every reply carries the referee's call: the outcome (`"success"` or the rule that ended it) and how many of the stages
  it reached.
- Write your own controller; public tools, robot models and pretrained controllers are allowed, a ready-made solution to
  this task is not.

The attempt fails at once if:
- any part of you touches the floor or the beam's supports (you fall off the beam)
- anything but your feet touches the beam (no hands, knees or sitting)

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`) is your whole interface to the robot. Its docstring is the full
reference (`python -c "import rcb_client; help(rcb_client)"`); its examples use another benchmark's names: for this task
`r.spec()` is authoritative.

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (9000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

One call returns at most 3000 images (`max_frames_per_call`).

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Rendering is most of a
call's cost: a controller's call should ask for no video (`video="none"`, `cameras=["head_left"]` or fewer) and read
`res.proprio`. With `interpolate="linear"` (the default) each control step's command is a straight line from the command
in force to the row; `"hold"` applies the row as it is.

```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 22) rows of the `walk` type
```

### Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

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
grip, < 0.5 opens it. At the start the robot is not in the plain standing pose (the venue text says how it starts): it
is held in `lowcmd` mode. The row that keeps the command in force: `spec()["start_command"]` has it, and
`get_obs(seconds=...)` keeps the command in force.

Joint order everywhere (Unitree's SDK order): `left_hip_pitch`, `left_hip_roll`, `left_hip_yaw`, `left_knee`,
`left_ankle_pitch`, `left_ankle_roll`, `right_hip_pitch`, `right_hip_roll`, `right_hip_yaw`, `right_knee`,
`right_ankle_pitch`, `right_ankle_roll`, `waist_yaw`, `waist_roll`, `waist_pitch`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_roll`, `left_wrist_pitch`, `left_wrist_yaw`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_roll`,
`right_wrist_pitch`, `right_wrist_yaw`. Each joint's range, speed and torque limits, default gains and start angle are
in the spec's `robot_facts`.

### Observations
- Cameras: the robot's two head cameras `head_left` and `head_right` (RGB 270 × 480, a stereo pair 5 cm apart, tilted
  20° down; depth on `head_left`) and the venue's fixed cameras (`venue`, `beam_end`); the spec's `cameras` gives each
  one's field of view and pose at the start.
- Proprioception: each row has, in the spec's `proprio_layout` order: the 29 joint positions (`*_pos`, rad), their
  velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in force (`*_target`,
  rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from sensor; angular
  velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
  `holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms, 4
  joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`,
  `cmd_wz`) and `time_s`, the attempt's time. A real G1 has no sensor for its position in the venue, and neither do you:
  that is what the cameras are for.

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
  `joints` uses the default gains (the spec's `robot_facts`) and zero `dq` and `tau`; `lowcmd` takes yours (kp up to
  1000 / 500 / 400 and kd up to 20 / 15 / 10 for legs / waist / arms). Nothing balances the robot in these modes but
  your own targets.
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

### Time
- Time moves only inside calls: `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for s
  seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `r.get_obs()` with no
  seconds is free.

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

## Others
Rule book: FIG Apparatus Norms, women's artistic gymnastics, balance beam. The rules here:
- One pass along a 5 m competition beam (0.1 m wide, its top 1.25 m above the floor), judged pass or fail: from the end
  you start on to the last 0.5 m at the far end, on your feet.
- The beam is rigid, with no padding, and there are no mats round it.
- Only your feet may touch the beam; a hop is allowed if you come down on the beam on your feet.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included. Do not look up a ready-made solution to this exact task, such as the benchmark's reference solutions; trials
  are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
