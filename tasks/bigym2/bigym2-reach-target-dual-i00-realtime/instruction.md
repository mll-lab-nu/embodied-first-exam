# BiGym 2.0 · reach-target-dual (realtime)

## Task
Put your left gripper in the red sphere and your right gripper in the green sphere at the same time, with the gap
between each gripper's fingers inside its sphere.

## Goal
Success: the point between the left gripper's finger pads is inside the red sphere and the right gripper's is inside the
green sphere, at the same time, for a second. The episode ends as soon as it succeeds. A fall (the pelvis tipping far
over, or dropping low) makes the episode a failure without ending it.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only what the robot's three cameras see (RGB, 84x84: `head`, `left_wrist`, `right_wrist`) and its own
  proprioception; not where any object is now, not the success check: when the episode ends, the service tells you that
  it ended and why.

## Robot Interface
A simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo). Like real hardware, it does not wait
for you: once the episode is running, the robot moves in real time while you think. NVIDIA's GR00T whole-body
controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the robot
balanced: you command where it walks, how high its pelvis is, its arm joints and its grippers. The robot runs as a
service you reach only through its client, as if it were real hardware, on a clock that does not stop while you think:
one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the action type is `"whole_body"`:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (700), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s` |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 20 commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, seconds=0, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |

One call returns at most 3000 images. A watch is refused with a 429 while the images in flight (pending watches and
answers not read yet) would exceed it or 8 of them are outstanding; a `submit` or a `get_obs()` without seconds is never
refused for its images: its answer then comes without its frames and `meta["frames_skipped"]` is set. Measured here on
an otherwise idle host: the simulator spends about 14 ms of each 20 ms control step, so it keeps up with the clock
(largest lag seen 0.07 s); `get_obs()` without seconds answers in about 10 ms. Values outside the bounds are clipped and
reported in `meta["clipped"]`, never refused; a malformed request raises `ValueError` and changes nothing. The client's
docstring explains the protocol with another benchmark's examples (`joint_position`, bounds [-1, 1], `imu`, `links`,
`depth`): for this task `spec()` is authoritative.

### Actions
Action type `whole_body`: rows of 20 floats in physical units, one per control step (0.02 s), in this order: `vx` (0):
walking velocity command, forward (m/s, the robot's frame), in [-1, 1]; `vy` (1): walking velocity command, to the left
(m/s), in [-1, 1]; `height` (2): pelvis height command (m), in [0.4, 1]; `wz` (3): turning rate command, + turns left
(rad/s), in [-1, 1]; 4-10: the left arm's 7 joints, 11-17: the right arm's, each in the order shoulder pitch, shoulder
roll, shoulder yaw, elbow, wrist roll, wrist pitch, wrist yaw: absolute joint targets (rad), bounds shoulder pitch
[-3.0892, 2.6704], shoulder roll [-1.5882, 2.2515], shoulder yaw [-2.618, 2.618], elbow [-1.0472, 2.0944], wrist roll
[-1.9722, 1.9722], wrist pitch [-1.6144, 1.6144], wrist yaw [-1.6144, 1.6144] (the same for both arms); `left_gripper`
(18) and `right_gripper` (19): 0 open .. 1 closed, in [0, 1]. Values outside the bounds are clipped. The row that stands
still at the start: zeros but `height` 0.74, `left_gripper` 0.6, `right_gripper` 0.6. `right_shoulder_roll_joint`'s
bounds are BiGym's action bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

### Observations
Cameras: `head`, `left_wrist`, `right_wrist` (RGB, 84x84); `spec()["cameras"]` gives each camera's field of view and its
pose at the start. Each proprioception row has, in `spec()["proprio_layout"]` order: the positions (`*_pos`) of each
arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`,
`pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the room's frame, z up, heading 0 along the room's +x axis
and counter-clockwise positive): 22 values; then their velocities (`*_vel`, per second) in the same order; then
`left_gripper_state` and `right_gripper_state` (0 open .. 1 closed); then the pelvis pose again as the base controller
tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`). `spec()["joints"]` gives each arm, waist and finger
joint's axis, a point on it and its range (the pelvis frame with every joint at 0: `spec()["joint_frame"]`; the sign
convention: `spec()["joint_sign"]`), `spec()["grippers"]` the point between each gripper's finger pads on its wrist
link, and `spec()["cameras"][camera]["mount"]` each camera's pose on its link.

### Time and streaming
- Slowdown: S = 1. The robot runs in real time: one control step (20 ms of robot time) every 20 ms of wall-clock time.
  `spec()["timing"]["slowdown"]` states it.
- Time does not stop. The episode starts paused, on a fixed starting state, the robot standing still. Its clock starts
  at your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs at 50 Hz in real time, one control
  step every 0.02 s of wall-clock time, whether or not you send anything, until the episode ends. Between your commands
  it executes what you planned, then holds your last command with zero walking and turning velocity (it stands still
  where it is); nothing pauses for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours takes seconds. Drive it with a program: a controller
  of your own (Python in your container, with numpy and the client) that runs a loop, reads the robot and sends
  commands, started in the background (`setsid nohup python -u /app/ctrl.py > /app/ctrl.log 2>&1 < /dev/null &`:
  `setsid` matters, a plain `nohup ... &` is killed when your shell command returns) so that your session is free while
  it runs.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  When the plan runs out, the robot stands still on your last command; a gap you leave with a later `at` is filled with
  the plan's last row instead, its walking and turning velocity included. `res.meta["control_steps"]` is the number of
  steps run so far, `res.meta["proprio"]["now"]` the robot's proprioception now, `res.meta["plan_end_step"]` where the
  plan now ends.
- Closed loop: every 0.1-0.2 s send the next 0.1-0.2 s of rows (`r.submit("whole_body", A, dt=0.02, cameras=[])`),
  computed from the proprioception the previous call returned, so the plan never runs out between your calls (when it
  does, the robot stands still). `cameras=[]` skips the images (the fastest call).
- Open loop: send up to 10 s of rows at once (`dt` a multiple of 0.02) and the next chunk before the plan runs out, with
  `at` = the step where it should take over; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- A `linear` chunk starts its interpolation from the command in force just before `at`: the row planned for that step,
  or, once the plan has run out, the standing row the robot holds.
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts them).
  `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw. `spec()["timing"]` states all this; `r.status()` shows `running` and `lag_s`.

### Notes
The episode also ends when the pelvis gets more than 10 m from the scene's origin, on a simulator error, and after 700
control steps (14 s of robot time).

- The whole-body controller: it follows velocity commands with some lag and wobble, so read the pelvis pose and close
  the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least
  0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso
  leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8
  rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how
  the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It
  keeps the robot balanced but does not stop it from walking into things.
- Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below the
  targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag.

## Others
- Ending your session early ends the run as the time limit does (and stops your background programs): do not stop while
  the episode runs; it can still pass.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
