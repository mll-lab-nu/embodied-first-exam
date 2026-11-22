# KinDER · dynamo (standard)

## Task
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). Drive the robot into the translucent green square marked on the floor; three chairs stand in the
way and can be pushed. (The red, blue and yellow squares only mark where the chairs started.) Measured at the start, in
the odometry frame (Robot Interface): the green square's centre is at x = 5.12 m, y = -2.48 m, 5.7 m from the centre of
the base and 26° to the right of the way it faces; it is 0.85 m along x by 0.85 m along y, its sides turned about 7°
counter-clockwise (seen from above) from the frame's axes.
The robot runs as a service you reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: the middle of the robot's base is inside the green square. The episode ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's own sensors: its two cameras (with their calibration), its joint encoders and
  the base's odometry; no object poses, no scene layout, no score; the episode ends when the task is done, and the
  service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.depth`
(metres), `res.proprio` (one row per frame). One call returns at most 3000 images. Values outside the bounds are clipped
and reported in `meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Once the
episode has ended, `submit` raises `EpisodeOver`. Time per call, on a lightly loaded host: about 13.2 ms per control
step in one-row calls asking for one camera, 18.1 ms with both cameras' images (and the wrist's depth), 7.6 ms per step
in chunks of 10 rows asking for one camera (`video="none"` each time).

### Actions
One action type, `delta`: 11 numbers per row, one 10 Hz control step, in the order of
`spec()["action_types"]["delta"]["layout"]`; at most 100 rows a call:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`:
  how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums
  are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).

### Observations
- Cameras: `robot_base` on the base and `robot_wrist` on the arm's last link (which also gives depth), RGB 480 × 640,
  each with its calibration.
- The proprioception (`obs.meta["proprio"]`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw`
  (the odometry frame: where the base started, x the way it faced, y left, z up), `base_vx`, `base_vy`, `base_yaw_rate`,
  `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed
  limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.
- The robot's own facts, as its documentation would give them, are in `r.spec()`: each arm joint's axis, position and
  limits, the gripper's grasp point, each camera's field of view and pose; nothing about where anything else is.
- When the episode has ended, `meta["reason"]` says why: `"success"`, `"failed"` when its control steps ran out, or
  `"error"` after a simulator error.

### Time
Time moves only inside calls: running your actions and holding the last command while you watch (`get_obs(seconds=s)`,
at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while you think; an observation
without seconds is free.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: the episode ends after 1000 control steps (100 s of robot time); the task has to be done by then.
