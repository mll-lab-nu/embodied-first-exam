# BiGym 2.0 · saucepan-to-hob (standard)

## Task
Take the saucepan out of the cabinet under the counter, set it on the hob and let go.

## Goal
Success: the saucepan sits on the hob and neither gripper touches it, for a second. A fall (the pelvis tipping far over,
or dropping low) makes the episode a failure without ending it. After `/finish`, the robot stands still for one more
second, and the check runs at its end.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only what the robot's three cameras see (RGB, 84x84: `head`, `left_wrist`, `right_wrist`) and its own
  proprioception; not where any object is now, no success signal.

## Robot Interface
A simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo). NVIDIA's GR00T whole-body
controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the robot
balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its
grippers. The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one
live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`, its docstring the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the action type is `"whole_body"`:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (4650), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, last_s=0, video="frames")` | `POST /observe` | the current frames (free), or with `last_s=n` the frames recorded over the last n seconds; no time passes |
| `r.hold(seconds, cameras=None, video="mp4")` | `POST /submit` | stand still for `seconds` of robot time and return the video, like a submit |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 21 commands `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
```python
from rcb_client import Robot
r = Robot()
res = r.submit("whole_body", A, dt=0.02)   # A: (T, 21) commands, one row per control step
```

The episode starts when the service comes up, from a fixed starting state. Once it has ended, `submit` raises
`EpisodeOver`. Time moves only inside calls. `submit` runs your commands and `hold(s)` stands still for s seconds; both
use up the episode's control steps. Between calls the robot waits, frozen, while you think; `get_obs()` is free. One
call returns at most 3000 images. The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`,
`reason`, `proprio["now"]`, `clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the
cameras saw during the call), `res.proprio` (proprioception rows). Values outside the bounds are clipped, not refused,
and `meta["clipped"]` reports them. A malformed request raises `ValueError` and runs nothing. The response of the call
that ends the episode also carries `meta["outcome"]`, BiGym's own label of how it ended (`timeout` at the step cap,
`fell`, `terminated`, `physics_error`). Standing still is the row with the current height, lean, arm and gripper targets
and zero `vx`, `vy`, `wz`; `hold(s)` does that from your last row. Measured here: a control step costs about 14 ms of
service time inside a `submit` (a 1 s chunk returns in about 0.7 s); `get_obs()` about 10 ms. The client's docstring
explains the protocol with another benchmark's examples (`joint_position`, bounds [-1, 1], `imu`, `links`, `depth`): for
this task `spec()` is authoritative.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and returns
  the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`, `.npy`,
  `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
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
closed, in [0, 1]. Values outside the bounds are clipped. The row that stands still at the start: zeros but `height`
0.74, `left_gripper` 0.6, `right_gripper` 0.6. `right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the
joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

### Observations
Cameras: `head`, `left_wrist`, `right_wrist` (RGB, 84x84); `spec()["cameras"]` gives each camera's field of view and its
pose at the start. Each proprioception row has, in `spec()["proprio_layout"]` order: the positions (`*_pos`) of the 3
waist joints (they show the lean you command), each arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m),
and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the room's
frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): 25 values; then their velocities
(`*_vel`, per second) in the same order; then `left_gripper_state` and `right_gripper_state` (0 open .. 1 closed); then
the pelvis pose again as the base controller tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`).
`spec()["joints"]` gives each arm, waist and finger joint's axis, a point on it and its range (the pelvis frame with
every joint at 0: `spec()["joint_frame"]`; the sign convention: `spec()["joint_sign"]`), `spec()["grippers"]` the point
between each gripper's finger pads on its wrist link, and `spec()["cameras"][camera]["mount"]` each camera's pose on its
link.

### Notes
The episode also ends when the pelvis gets more than 10 m from the scene's origin, on a simulator error, and after 4650
control steps (93 s of robot time).

- The whole-body controller: it follows velocity commands with some lag and wobble, so read the pelvis pose and close
  the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least
  0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso
  leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8
  rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how
  the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It
  keeps the robot balanced but does not stop it from walking into things.
- Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below the
  targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
