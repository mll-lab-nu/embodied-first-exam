# ABC Sim · in-hand transfer (standard)

## Task
Move the cream cheese stick to the left arm's side of the table, at least a hand's width past the middle, and set it
down there.

## Goal
Success: the cream cheese stick lies on the table on the left arm's side, at least a hand's width past the middle line
between the arms. It must hold for about a second after the episode ends, while the robot keeps your last command.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and efforts, gripper
  openings, tool-frame poses): no object poses, no scene layout; no success signal.

## Robot Interface
A bimanual robot in ABC Sim (MuJoCo): two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side
by side at the near edge of a table, facing +x (the left arm is the one at +y). The robot runs as a service you reach
through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, cameras (+ intrinsics, mounting), proprio layout, kinematics
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: top, left, right)
obs = r.get_obs(cameras=["top"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, gripper openings, tcp poses, efforts
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.034)   # rows: (T, 14) targets, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.hold(1.0)                              # hold the last targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q14); r.ik({"left_tcp": [x, y, z, qw, qx, qy, qz]})   # the robot's kinematic model (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last command), so the scene waits while
you think. Once the episode has ended, `submit` raises `EpisodeOver`. If the service crashes, a call fails with a
connection error. The service then restarts and resumes the same episode, in the state after the last call it completed.
`r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` gives the tool
frames `left_tcp`, `right_tcp`, `left_grasp`, `right_grasp` and the arm links for any joint positions, and `r.ik` solves
IK for the tool frames (both use `/kinematics`).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
Action type `joint_position` (14): 14 numbers per control step:
`[left_joint1..6, left_gripper, right_joint1..6, right_gripper]` -- each arm's six joint position targets (rad) and its
gripper opening (0 = closed, 1 = open, each finger 0.0475 m from closed; up to 1.042). The joints and grippers are
position servos that track the targets (MuJoCo position actuators with damping and force limits). A target outside a
joint's range is clamped to that range. The simulator rounds every command to float32. One control step = 17 physics
steps of 2 ms = 0.034 s (29.4 Hz). Columns in `spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt`
apart: a whole multiple of the 0.034 s control period, at most 0.5 s. A chunk covers at most 10 s. Between rows, use
`interpolate="linear"` (default, from the previous targets) or `"hold"`. The client sends the rows as float32. There is
no step budget.

### Observations
Cameras: `top` (above and behind the arms, looking down at the table), `left` and `right` (wrist cameras on the arms),
`overhead`, `left_side`, `right_side` (640x480; default `top`, `left`, `right`). `spec["cameras"]` gives each camera's
mounting and intrinsics. A camera is static or mounted on an arm link; the wrist cameras move with the arm, so use the
pose returned with each frame. Every response carries each frame's pose. Proprioception (`spec["proprio_groups"]`):
`joint_pos` (`q_<entry>`, the 14 action coordinates measured), `joint_vel` (`qd_<entry>`), `gripper_opening` (m),
`tcp_pose` (each arm's tool centre point, world frame, `wxyz`), `joint_effort` (`effort_<entry>`).

### World frame
The table's frame: x forward (away from the arms' bases), y to the left as the arms face the table, z up; metres,
radians, quaternions `wxyz`. Directions are as the arms face the table: left = +y, right = -y, behind = +x (farther from
the arms), in front = -x (nearer to them). No positions of the scene are given; the arms' base poses are in
`spec["robot_spec"]["base"]`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 10 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Finish: if you never send `/finish`, the episode is graded when your session ends.
