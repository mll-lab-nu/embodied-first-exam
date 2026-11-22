# VLABench · select_poker_semantic (standard)

## Task
A Franka Panda arm at a table (VLABench on MuJoCo). Please pick up the poker 6 of spades and hold it up. The robot runs
as a service you reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: the 6 of spades is grasped and held up, lifted to a height of 0.9 m or more (world z). The episode ends as soon
as the task is done, and that episode, as it ran, is graded.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use VLABench's expert solutions, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`; its examples come from another benchmark: the numbers here and in
`spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.1 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.1, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 9 targets `dt` seconds apart (a multiple of 0.1; a chunk covers at most 10 s); stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.1, cameras=["forward"], video="none")   # A: (T, 9)
```

One call returns at most 3000 images. The answers come back decoded: `res.meta` (the counters, `done`, `reason`,
`proprio["now"]`, `clipped`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the cameras saw during
the call), `res.proprio` (rows). Measured cost here: about 40 ms of simulation per control step, plus about 15 ms per
camera image.

### Actions
- Action `joint_position` (9, float64): absolute position targets for VLABench's own actuators, the 7 arm joints (rad)
  and the 2 fingers (m, 0 closed … 0.04 open), each row held for its control steps (0.1 s, 100 physics steps each). The
  model sets no arm joint limits; stay inside the Panda's own,
  `spec()["action_types"]["joint_position"]["panda_joint_limits_rad"]`.

### Observations
- Four cameras: `forward`, `left`, `right` fixed, `wrist` on the hand; RGB 320×320, depth on request, each camera's
  intrinsics and pose in `spec()["cameras"]`.
- Proprioception (the spec's `proprio_layout`): `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `finger1_pos`,
  `finger2_pos` (m), `tcp_x/y/z` (m) and `tcp_qw/qx/qy/qz` (the hand's pose), `cmd_*` (the last command).
- World frame: metres; the robot's base is at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along its
  -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels.

### Episode
Time moves only inside calls: a submitted chunk runs its control steps, and holding still (`get_obs(seconds=s)`) runs
`s` seconds of them; between calls the robot waits, frozen, while you think, and reading the cameras without `seconds`
takes no time. Whether the episode has ended is in `meta["done"]`, and why in `meta["reason"]`: `"success"`, `"failed"`
at the step cap, `"error"` after a simulator error.

## Others
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
- Resources: 4 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 9,000 control steps (900 s of robot time); at the cap the episode ends and is graded as it stands.
