# Embodied Olympics · paddle bounce (realtime)

## Task
Bounce the table-tennis ball on the paddle in your right hand 20 times in a row, each time back up to the height it was
dropped from, without letting go of the paddle.

## Goal
Success: you hit the dropped ball up 20 times in a row on the blade, each time to at least the height it was dropped
from, and never let go of the paddle.

The referee in the service judges these stages, in order: **each of the 20 bounces**. The referee's success call counts
the moment it is made: nothing after it undoes it, but the attempt does not end there. The first foul before a success
ends the attempt as a failure. A reset starts a new attempt, and only your last attempt is graded. Ending your session
also stops your background programs.

When you are done, send `/finish` to end the episode and get it graded.

Keep a `NOTES.md` of at most 20 lines in `/app/output/` (your approach, what failed, what you downloaded or installed):
save it early and keep it current.

Rules:
- **No cheating.** Do not search for, download or use an existing solution to this exact task (published or reference
  solutions, the benchmark's demonstrations, policies trained for it); trials are reviewed.
- Attempts: 5 resets, each a new attempt from the same start, paused until your next command; only your last attempt is
  graded.
- You get only what the robot's own sensors give (its head cameras, joint encoders, motor torques and IMUs) and the
  venue's fixed cameras: not where you or any object is, not the referee's state. If the referee ends an attempt on a
  foul, every reply then carries the rule broken (`meta["outcome"]`); no stage count, no success signal.

The attempt fails at once if:
- the paddle leaves your hand, or touches any part of you but your right hand
- the ball comes back to the blade without having risen high enough
- a touch lingers (the ball rests, rolls or is carried on the blade)
- the ball touches the floor or anything but the blade (the handle, your hand, arm or body, or the dropper)
- you or the paddle touch the ball before it is dropped
- you fall

## Robot Interface
You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 34 kg; the Embodied Olympics simulator on
MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware, on a
clock that does not stop while you think.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.3`, realtime mode) is your whole interface to the robot. Its
docstring is the full reference (`python -c "import rcb_client; help(rcb_client)"`); its examples use another
benchmark's names: for this task `r.spec()` is authoritative.

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (2000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left`, `running`, `planned_steps`, `lag_s` |
| `r.get_obs(cameras=None, last_s=0, video="frames", include_depth=False)` | `POST /observe` | the robot now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |
| `r.submit(type, A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the attempt's clock |
| `r.reset(cameras=None)` | `POST /reset` | a new attempt from the same start, paused (see above) |

One call returns at most 3000 images (`max_frames_per_call`). No call is refused for its images. While 8 answers with
images are still waiting to be read, a `submit` or a `get_obs()` answers without its frames and sets
`meta["frames_skipped"]`.

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped, not refused, and
`meta["clipped"]` reports them. A malformed request raises `ValueError` and runs nothing. `cameras=None` means every
camera: a controller's call should ask for none (`cameras=[]`) and read `res.meta["proprio"]["now"]`; the cameras are
rendered on the service's GPU. With `interpolate="linear"` (the default) each control step's command is a straight line
from the command in force to the row; `"hold"` applies the row as it is.

```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, at=0, cameras=[])   # A: (T, 22) rows of the `walk` type, from step 0
while not r.status()["done"]:
    ...                                              # or stream one row per control step from the proprioception
```

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`,
  `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. `submit`
  answers at once, as the endpoint does. The clock does not wait for a tool call, and a call also takes your harness's
  own time; each result's `tool_s` is the tool's part.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

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
are absolute angles (rad). Values outside the bounds are clipped. `grip_right`: the hand's closure command, 0 (open) to
1 (closed). `grip_left`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot is in `stand` mode, but
not with the arms at rest (the venue text says how it starts). The right hand is closed on `paddle` at the start
(closure command 1): opening it lets go. The `stand` row that keeps the start as it is: `[0, 0, 0, 0.2, 0.2, 0, 1.28, 0,
0, 0, 0.2, -0.2, 0, 1.28, 0, 0, 0, 0, 1]` (`spec()["start_command"]` has it, the robot keeps the command in force until
your next row); a `stand` row with other angles or grips moves the arms or lets go.

Joint order everywhere (Unitree's SDK order): `left_hip_pitch`, `left_hip_roll`, `left_hip_yaw`, `left_knee`,
`left_ankle_pitch`, `left_ankle_roll`, `right_hip_pitch`, `right_hip_roll`, `right_hip_yaw`, `right_knee`,
`right_ankle_pitch`, `right_ankle_roll`, `waist_yaw`, `waist_roll`, `waist_pitch`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_roll`, `left_wrist_pitch`, `left_wrist_yaw`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_roll`,
`right_wrist_pitch`, `right_wrist_yaw`. Each joint's range, speed and torque limits, default gains and start angle are
in the spec's `robot_facts`.

### Observations
- Cameras: the robot's two head cameras `head_left` and `head_right` (RGB 270 × 480, a stereo pair 5 cm apart, tilted
  20° down; depth on `head_left`) and the venue's fixed cameras (`venue`); the spec's `cameras` gives each one's field
  of view and pose at the start.
- Proprioception: each row has, in the spec's `proprio_layout` order: the 29 joint positions (`*_pos`, rad), their
  velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in force (`*_target`,
  rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from sensor; angular
  velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
  `holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms, 4
  joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`,
  `cmd_wz`) and `time_s`, the attempt's time. Then, at the end of the row, the gripper: `jaw_opening_right`,
  `jaw_speed_right`, `jaw_force_right` (the opening between the pads in m, its speed in m/s, + opening, and the clamp
  force in N, + closing); a gripper's `holding_*` is 1 while both its jaws touch the same object. A real G1 has no
  sensor for its position in the venue, and neither do you: that is what the cameras are for.

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
- **The right hand is the robot's own**: Unitree Dex3-1 three-finger hand (0.71 kg; thumb 3 + index 2 + middle 2 joints,
  each its own motor). 7 drives per hand; closing torques 0.49, 0.86 N m per joint; each drive is position-servoed and
  force-limited (closing stops where its force limit is reached, a larger load drags it open). `grip_right` is the
  closure command: one value per hand from 0 (open) to 1 (closed), all of that hand's drives following it together. The
  hand holds only by contact and friction (no weld): what it holds can slip, turn or drop; it holds an object while the
  fingers and the thumb or palm touch it. The fingers, thumb and palm collide with the world and with the rest of your
  own body. The proprioception reports each hand's closure and every drive's position and torque (`r.spec()` lists the
  drives with their limits).
- **The left hand** has no working fingers here; it carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm). Nothing in this task is grippable: `grip_left` has no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

### Time and streaming
- The world runs at 1/S of real speed, S = 1: one control step (10 ms of robot time) every S x 10 ms of wall-clock time;
  `spec()["timing"]["slowdown"]` states it.
- Time does not stop: an attempt starts paused, on the frozen start, the robot holding its starting command. Its clock
  starts at your first `submit` and from then on the simulator runs at 100 Hz of robot time (S = 1), whether or not you
  send anything, until the attempt ends: the venue's timed events (the launch, the serve, the release) happen on that
  clock. Between your commands the robot executes what you planned, then holds the last command in force; nothing pauses
  for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn: one turn of yours (a model response, a tool call) takes seconds; the
  decisive moment of an attempt takes a fraction of one. Drive the robot with a program: a controller of your own
  (Python in your container, with numpy and the client) that plans or streams the rows, started in the background
  (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`) or in the foreground if it ends with the attempt. Use your turns
  to start attempts, read what happened, and improve the program.
- Attempts: `r.reset()` abandons the running attempt (or follows one that has ended) and starts a new one from the same
  start, paused until your next `submit`; once an attempt has ended, `submit` raises `EpisodeOver` until you reset. The
  wall clock is the run's and never restarts.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an attempt step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the command in force is held. `res.meta["control_steps"]`
  is the number of steps run so far in this attempt (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (a chunk covers at most 10 s), with `at = 0` for the attempt's start:
  `r.submit(type, A, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly those rows from
  the first step; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit(type, a[None], cameras=[])`, computed from the proprioception
  the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped; `res.meta["late_steps"]` counts
  them. The rest of the chunk applies from the next step.
- `get_obs()` reads the robot now. `get_obs(last_s=n)` returns at once what the cameras recorded over the last n
  seconds. `r.status()` shows `running` and `lag_s`.

## Others
- The dropper lets the ball fall shortly after the start.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 5 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: an attempt ends by itself after 20 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
