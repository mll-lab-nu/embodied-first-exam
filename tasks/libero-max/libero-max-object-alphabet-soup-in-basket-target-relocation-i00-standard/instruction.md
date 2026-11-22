# LIBERO-MAX · libero_object · target relocation (standard)

## Task
A Franka Panda arm at a table (LIBERO on robosuite / MuJoCo). Pick the alphabet soup and place it in the basket. The
scene changes once while you work (Others). The robot runs as a service you reach only through its client, as if it were
real hardware: one live episode.

## Goal
Success: the alphabet soup is in the basket. The episode ends as soon as the task is done, and that episode, as it ran,
is graded.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`; its examples come from another benchmark: the numbers here and in
`spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.05 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold still and watch for `seconds` (at most 30) |
| `r.submit("ee_delta", A, dt=0.05, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 7 numbers `dt` seconds apart (a multiple of 0.05; a chunk covers at most 10 s); stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("ee_delta", A, dt=0.05, cameras=["agentview"], video="none")   # A: (T, 7)
```

One call returns at most 3000 images. The answers come back decoded: `res.meta` (the counters, `done`, `reason`,
`proprio["now"]`, `clipped`, `cameras_now`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the
cameras saw during the call), `res.proprio` (rows). Measured cost here: about 20 ms of simulation per control step, plus
about 70 ms per camera image.

### Actions
- Action `ee_delta` (7, float64, each clipped to [-1, 1]): LIBERO's native operational-space control (OSC_POSE). Per
  control step the hand's target moves by `[dx, dy, dz]` × 0.05 m and turns by `[drx, dry, drz]` × 0.5 rad (axis-angle,
  world frame); `grip` +1 closes, -1 opens the gripper. With `dt = 0.05` each row is one control step;
  `get_obs(seconds=s)` holds still (zero motion, the gripper as last commanded).

### Observations
- Two cameras: `agentview` fixed in front of the robot, `wrist` on the hand; RGB 256×256, depth on request; their
  intrinsics and pose in the spec's `cameras` at the start; every action's reply carries the current ones in
  `meta["cameras_now"]`.
- Proprioception (the spec's `proprio_layout`): `eef_x/y/z` (m) and `eef_qw/qx/qy/qz` (the hand), `finger_left`,
  `finger_right` (m), `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `cmd_*` (the last action).
- World frame: metres; the robot's base is at (-0.6, 0, 0) facing +x: x forward (across the table), y to the robot's
  left, z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along its
  -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels (upright images).

### Episode
Time moves only inside calls: a submitted chunk runs its control steps, and holding still (`get_obs(seconds=s)`) runs
`s` seconds of them; between calls the robot waits, frozen, while you think, and reading the cameras without `seconds`
takes no time. Whether the episode has ended is in `meta["done"]`, and why in `meta["reason"]`: `"success"`, `"failed"`
at the step cap, `"error"` after a simulator error.

## Others
- The scene can change while you work: once during the episode, when your gripper first gets close to one of the task's
  objects, the scene changes: an object or a receptacle may be moved, an obstacle or a few other objects may appear, a
  camera may shift, or the lighting, the colours or the image noise may change. Nothing tells you when; the task and its
  success check stay the same, so keep checking what the cameras show. A moved object or receptacle jumps there alone:
  what already rests in or on it stays where it was.
- Ending your session early ends the run as the time limit does: do not stop early.

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
- Resources: 3 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 9,000 control steps (450 s of robot time); at the cap the episode ends and is graded as it stands.
