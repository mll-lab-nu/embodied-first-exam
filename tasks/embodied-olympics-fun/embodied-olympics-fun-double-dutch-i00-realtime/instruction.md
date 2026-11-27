# Embodied Olympics · double dutch (realtime)

## Task
Jump Double Dutch: get into the two turning ropes and jump them 10 times in a row, one rope per jump, without a rope
touching you, then land on your feet.

## Goal
Success: you get into the middle of the turning ropes, jump them ten times in a row, one rope per jump, without a rope
touching you, and land on your feet.

The referee in the service judges these stages, in order: **the entry, each of the 10 jumps, the landing**. Once the
referee calls success, it stays; the attempt continues until you finish. The first foul before a success ends the
attempt as a failure. A reset starts a new attempt, and only your last attempt is graded. Ending your session also stops
your background programs.

When you are done, send `/finish` to end the episode and get it graded.

Keep a `NOTES.md` of at most 20 lines in `/app/output/` (your approach, what failed, what you downloaded or installed):
save it early and keep it current.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, policies trained for it); trials are reviewed.
- Attempts: 5 resets, each a new attempt from the same start, paused until your next command; only your last attempt is
  graded.
- You get only what the robot's own sensors give (its head cameras, joint encoders, motor torques and IMUs) and the
  venue's fixed cameras: not where you or any object is, not the referee's state. If the referee ends an attempt on a
  foul, every reply after that names the rule broken (`meta["outcome"]`). The replies give no stage count and no success
  signal.

The attempt fails at once if:
- a rope touches any part of you, or passes under a foot that is on the ground or through you
- your hips leave the centre zone once they have entered it
- you touch a turning machine
- you fall: anything but your feet touches the floor, or your hips sink close to it, or the landing after the last jump
  is not on your feet

## Robot Interface
You control a simulated Unitree G1 humanoid robot (29 joints, 1.32 m tall, 33 kg; the Embodied Olympics simulator on
MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware, on a
clock that does not stop while you think.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.3`, realtime mode) is your whole interface to the robot. Its
docstring is the full reference (`python -c "import rcb_client; help(rcb_client)"`); its examples use another
benchmark's names: for this task `r.spec()` is authoritative.

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (2500), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
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
rendered on the service's GPU. With `interpolate="linear"` (the default), the command moves step by step in a straight
line from the command in force to the row. With `"hold"`, the row is applied as it is.

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
in the spec's `robot_facts`.

### Observations
- Cameras: the robot's two head cameras `head_left` and `head_right` (RGB 270 × 480, a stereo pair 5 cm apart, tilted
  20° down; depth on `head_left`) and the venue's fixed cameras (`venue`, `side`, `close`); the spec's `cameras` gives
  each one's field of view and pose at the start.
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
  about 0.6 m/s. `vy` goes up to 0.5 and `wz` up to 1.57 rad/s. It follows the command with lag and barely moves in its
  first second. At a zero command it marks time on the spot; the pelvis sways and drifts a centimetre or two per second.
  Unlike `stand`, it recovers from small disturbances. When you switch to `walk` from another mode, it first blends the
  legs to the stance (0.3 s), then holds a zero command until the robot is steady (up to 2 s). It was trained with the
  arms at rest: moving the arms and the waist disturbs it.
- **`walk_falcon`** and **`walk_agile`** are two more walking policies for the G1's legs. They use the same row as
  `walk`, so you keep the waist and the arms. `walk_falcon` is FALCON, trained with arm motions and forces on the hands;
  `walk_agile` is AGILE's velocity-height policy, trained while the arms and the waist moved. Both run their released
  weights in numpy at 50 Hz, with their own leg gains (kp 100 / 100 / 100 / 200 / 20 / 20 per leg). Both hold still and
  follow the command better than `walk` while the arms move or carry something; FALCON also adds a small correction to
  the wrists. FALCON treats speeds below 0.2 m/s and turns below 0.2 rad/s as zero, and stands with the pelvis at about
  0.74 m. AGILE treats commands with a norm below 0.1 as zero and stands lower (about 0.68 m). AGILE barely turns on the
  spot below about 0.7 rad/s; while walking at 0.2 m/s or more it turns as asked. Their command ranges are in the action
  table. When you switch to `walk_falcon` or `walk_agile`, that policy takes over the legs at once, from where they are,
  with its memory reset. `walk`, the other of the two and `run` take the legs over from it in the same way. Switching
  from `walk_falcon` or `walk_agile` straight to `stand` usually ends in a fall, because `stand` holds Unitree's stance
  and does not balance. First give `walk` a zero command for about 2 s.
- **`run`** runs the platform's athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
  above that; the command changes at most 1.5 m/s per second), `|vy|` ≤ 0.12 m/s, `|wz|` ≤ 0.5 rad/s. `run_arms` gives
  you the arms, while the running policy keeps the legs and the waist. Taking the arms away from the policy's swing
  disturbs it. Switching to `stand`, `walk` or `joints` above about 0.6 m/s usually ends in a fall: slow down first
  (from 2.4 m/s that takes about 2 s and 2.3 m).
- **`joints` / `lowcmd`** give you direct control. Each motor's torque is
  `kp (q − q_measured) + kd (dq − dq_measured) + tau`, computed at 1 kHz while your row is held for its 10 ms, then
  limited by the motor's torque-speed curve and torque limit. `joints` uses the default gains (the spec's `robot_facts`)
  with zero `dq` and `tau`. `lowcmd` uses the gains, `dq` and `tau` you send (kp up to 1000 / 500 / 400 and kd up to 20
  / 15 / 10 for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range. In each 10 ms step, a target moves at most the joint's speed
  limit × 10 ms away from the target in force. Joints that an action type does not include keep their current targets.
  The speed limit applies only to targets. The joint itself is bounded by the motor's torque-speed curve: with a
  `lowcmd` feed-forward torque, a joint can turn up to about 1.15 times that speed, where the motor's torque has fallen
  to zero.
- **The hands** have no working fingers here. Each carries a fist pad: a 4.4 × 8 × 10 cm box beyond the wrist, with its
  10 cm side along the forearm. Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

### Time and streaming
- The world runs at 1/S of real speed, with S = 1 (`spec()["timing"]["slowdown"]`): one control step (10 ms of robot
  time) every S x 10 ms of wall-clock time.
- Time does not stop: an attempt starts paused, on the frozen start, the robot holding its starting command. Its clock
  starts at your first `submit`. From then on the simulator runs at 100 Hz of robot time (S = 1) until the attempt ends,
  whether or not you send anything. The venue's timed events (the launch, the serve, the release) happen on that clock.
  Between your commands the robot executes what you planned, then holds the last command in force; nothing pauses for
  you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn: one turn of yours (a model response, a tool call) takes seconds; the
  decisive moment of an attempt takes a fraction of one. Drive the robot with a program: your own controller (Python in
  your container, with numpy and the client) that plans or streams the rows. Start it in the background
  (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`), or in the foreground if it ends when the attempt ends. Use your
  turns to start attempts, read what happened, and improve the program.
- Attempts: `r.reset()` abandons the running attempt (or follows one that has already ended) and starts a new one from
  the same start, paused until your next `submit`. Once an attempt has ended, `submit` raises `EpisodeOver` until you
  reset. The wall clock belongs to the whole run and never restarts.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (a step number within the attempt; by default the next step). They replace whatever was planned from
  `at` on and keep what is planned before it. When the plan runs out, the command in force is held.
  `res.meta["control_steps"]` is the number of steps run so far in this attempt (so the next step has that number).
  `res.meta["proprio"]["now"]` is the current proprioception, and `res.meta["plan_end_step"]` is where the plan now
  ends.
- Open loop: plan a whole movement at once (a chunk covers at most 10 s), with `at = 0` for the attempt's start.
  `r.submit(type, A, dt=0.01, interpolate="hold", at=0, cameras=[])` starts the clock and runs exactly those rows from
  the first step. `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit(type, a[None], cameras=[])`, computed from the proprioception
  the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped; `res.meta["late_steps"]` counts
  them. The rest of the chunk applies from the next step.
- `get_obs()` reads the robot now. `get_obs(last_s=n)` returns at once what the cameras recorded over the last n
  seconds. `r.status()` shows `running` and `lag_s`.

## Others
- The ropes are already turning at the start and never stop.

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: open. You may install packages and search for, download and use public tools, robot models and pretrained
  controllers (say in your notes what you used); you may read anything in your container, the benchmark's source
  included.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 5 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 25 s of robot time, then the episode ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
