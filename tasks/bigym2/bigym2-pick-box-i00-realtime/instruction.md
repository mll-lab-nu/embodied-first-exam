# BiGym 2.0 · pick-box (realtime)

## Task
Move the cardboard box from the side table onto the kitchen counter and let go.

## Goal
Success: the box rests on top of the kitchen counter and neither gripper touches it, for a second. A fall (the pelvis
tipping far over, or dropping low) makes the episode a failure without ending it.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only what the robot's three cameras see (RGB, 84x84: `head`, `left_wrist`, `right_wrist`) and its own
  proprioception; not where any object is now, no success signal.

## Robot Interface
A simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo). Like real hardware, it does not wait
for you: once the episode is running, the robot moves in real time while you think. NVIDIA's GR00T whole-body controller
drives the legs and waist and keeps the robot balanced. It is a learned policy that runs inside every control step. You
command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its grippers. The
robot runs as a service you reach through its client or its MCP tools, as if it were real hardware, on a clock that does
not stop while you think: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, realtime mode, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the action type is `"whole_body"`:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (4400), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s` |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 21 commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, last_s=0, video="frames")` | `POST /observe` | the robot now, or with `last_s=n` what the cameras recorded over the last n seconds; it never waits |

One call returns at most 3000 images. No call is refused for its images. While 8 answers with images are still waiting
to be read, a `submit` or a `get_obs()` answers without its frames and sets `meta["frames_skipped"]`. Measured here on
an otherwise idle host: the simulator spends about 14 ms of each 20 ms control step, so it keeps up with the clock
(largest lag seen 0.07 s); `get_obs()` answers in about 10 ms. Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and changes nothing. The client's docstring
explains the protocol with examples from another benchmark (`joint_position`, bounds [-1, 1], `imu`, `links`, `depth`).
For this task, `spec()` is what counts.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and returns
  the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`, `.npy`,
  `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. `submit`
  answers at once, as the endpoint does. The clock does not wait for a tool call, and a call also takes your harness's
  own time; each result's `tool_s` is the tool's part.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
Action type `whole_body`: rows of 21 floats in physical units, one per control step (0.02 s), in this order: `vx` (0):
walking velocity command, forward (m/s, the robot's frame), in [-1, 1]; `vy` (1): walking velocity command, to the left
(m/s), in [-1, 1]; `height` (2): pelvis height command (m), in [0.4, 1]; `wz` (3): turning rate command, + turns left
(rad/s), in [-1, 1]; `pitch` (4): torso lean command, + leans forward (rad), in [-0.2, 0.8]; 5-11: the left arm's 7
joints, 12-18: the right arm's, each in the order shoulder pitch, shoulder roll, shoulder yaw, elbow, wrist roll, wrist
pitch, wrist yaw: absolute joint targets (rad), bounds shoulder pitch [-3.0892, 2.6704], shoulder roll [-1.5882,
2.2515], shoulder yaw [-2.618, 2.618], elbow [-1.0472, 2.0944], wrist roll [-1.9722, 1.9722], wrist pitch [-1.6144,
1.6144], wrist yaw [-1.6144, 1.6144] (the same for both arms); `left_gripper` (19) and `right_gripper` (20): 0 open .. 1
closed, in [0, 1]. Values outside the bounds are clipped. The row that stands still at the start is all zeros except
`height` 0.74, `left_gripper` 0.6 and `right_gripper` 0.6. `right_shoulder_roll_joint`'s bounds are BiGym's action
bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

### Observations
Cameras: `head`, `left_wrist`, `right_wrist` (RGB, 84x84); `spec()["cameras"]` gives each camera's field of view and its
pose at the start. Each proprioception row has these values, in `spec()["proprio_layout"]` order. First 25 positions
(`*_pos`): the 3 waist joints (they show the lean you command), each arm's 7 joints (rad) and its gripper's 2 finger
joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its
heading, in rad). The pelvis values are in the room's frame: z up, heading 0 along the room's +x axis and
counter-clockwise positive. Then their velocities (`*_vel`, per second) in the same order. Then `left_gripper_state` and
`right_gripper_state` (0 open .. 1 closed). Then the pelvis pose again as the base controller tracks it (`pelvis_x`,
`pelvis_y`, `pelvis_z`, `pelvis_yaw`). `spec()["joints"]` gives each arm, waist and finger joint's axis, a point on that
axis and the joint's range. These are in the pelvis frame with every joint at 0 (`spec()["joint_frame"]`); the sign
convention is in `spec()["joint_sign"]`. `spec()["grippers"]` gives the point between each gripper's finger pads, on its
wrist link. `spec()["cameras"][camera]["mount"]` gives each camera's pose on its link.

### Time and streaming
- Slowdown: S = 1. The robot runs in real time: one control step (20 ms of robot time) every 20 ms of wall-clock time.
  `spec()["timing"]["slowdown"]` states it.
- Time does not stop. The episode starts paused, on a fixed starting state, the robot standing still. Its clock starts
  at your first `submit` and from then on the robot runs at 50 Hz in real time, one control step every 0.02 s of
  wall-clock time, whether or not you send anything, until the episode ends. Between your commands it executes what you
  planned, then holds your last command with zero walking and turning velocity (it stands still where it is); nothing
  pauses for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours takes seconds. Drive it with a program: a controller
  of your own (Python in your container, with numpy and the client) that runs a loop, reads the robot and sends
  commands. Start it in the background so that your session is free while it runs:
  `setsid nohup python -u /app/ctrl.py > /app/ctrl.log 2>&1 < /dev/null &`. `setsid` matters: a plain `nohup ... &` is
  killed when your shell command returns.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  When the plan runs out, the robot stands still on your last command. A gap is different: if you leave one by starting
  a chunk at a later `at`, the gap is filled with the plan's last row, its walking and turning velocity included.
  `res.meta["control_steps"]` is the number of steps run so far, `res.meta["proprio"]["now"]` the robot's proprioception
  now, `res.meta["plan_end_step"]` where the plan now ends.
- Closed loop: every 0.1-0.2 s, send the next 0.1-0.2 s of rows (`r.submit("whole_body", A, dt=0.02, cameras=[])`),
  computed from the proprioception the previous call returned. That way the plan never runs out between your calls (when
  it does, the robot stands still). `cameras=[]` skips the images (the fastest call).
- Open loop: send up to 10 s of rows at once (`dt` a multiple of 0.02). Send the next chunk before the plan runs out,
  with `at` set to the step where it should take over; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps
  ahead.
- A `linear` chunk starts its interpolation from the command in force just before `at`: the row planned for that step,
  or, once the plan has run out, the standing row the robot holds.
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts them).
  `get_obs()` reads the robot now. `get_obs(last_s=n)` returns at once what the cameras recorded over the last n
  seconds. `spec()["timing"]` states all this; `r.status()` shows `running` and `lag_s`.

### Notes
The episode also ends when the pelvis gets more than 10 m from the scene's origin and on a simulator error.

- The whole-body controller follows velocity commands with some lag and wobble, so read the pelvis pose and close the
  loop rather than dead-reckon. A planar speed command below 0.055 m/s means standing still (use 0 or at least 0.06).
  When it stands still, the base drifts a few centimetres, and further while the hands push on furniture or the torso
  leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8
  rad lean). Heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m). Squatting (a lower height) is how
  the hands reach low objects. While squatting the controller does not step: walk first, then squat in place. It keeps
  the robot balanced but does not stop it from walking into things.
- Keep your own copy of the last row you sent. A row rebuilt from the measured joint angles sits a little below the
  targets the arms were holding, because the servos track with a small error. Holding with such a row lets the arms sag.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 4,400 control steps (88 s of robot time), then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
