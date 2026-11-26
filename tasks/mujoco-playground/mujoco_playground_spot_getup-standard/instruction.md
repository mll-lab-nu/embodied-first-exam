# MuJoCo Playground · SpotGetup (standard)

## Task
The robot has fallen over. Get it back up, standing upright at its normal height.

## Goal
Success: the robot stands upright on its feet, at about its standing height, for half a second. Success is judged on how
things stand when the episode ends. The time standing must run up to that end. It ends when you call finish (Limits) or
when your session ends. The robot never tells you whether you have succeeded. The step limit (Robot Interface) ends it
too, judged the same way; the `done` action is the same as finish.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: after finish no reset is possible, and when your session ends the episode then running is graded.
- You get only the cameras and the robot's own sensors (joint positions, velocities and torques, the IMU, foot
  contacts): no world positions, no success signal.

## Robot Interface
Boston Dynamics Spot (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no walking
or balance controller. The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.hold(1.0)                              # hold the targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({"FL": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now (the same as finish)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `hold(s)`, which holds the current targets). A reset (`POST
/reset`, the `_post` line above) puts the robot back on the same frozen starting state and starts a new episode, either
abandoning the running one or after one has ended; it takes no simulated time and returns the start's images and
proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock is the run's
and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes (`meta["control_steps"]` is the
current episode's). If the service crashes, a call fails with a connection error: it restarts and resumes the same
episode (never a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check
`r.status()`. One call returns at most 3000 images.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
Action type `joint_position` (12): FL, FR, HL, HR legs, each hx (abduction), hy (hip pitch), kn (knee): absolute targets
of the joint position actuators (rad; kp = 400 N m/rad, joint damping 20 N m s/rad). Rows are `dt` apart (a whole
multiple of the 0.02 s control period, at most 0.5 s), `interpolate="linear"` (default) or `"hold"` between rows; a
chunk covers at most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped
and listed in `res.meta["clipped"]`. Feedback control means short chunks: each response tells you where the robot is
now.

### Observations
Cameras: `track`, `side`, `back`, `top` (they follow the robot); `spec["cameras"]` gives each one's mounting and
intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`,
`joint_effort` (12 each, action order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame:
x forward, y left, z up), `foot_contact` (FL, FR, HL, HR).

### Episode
The robot was dropped from 1 m in a random orientation with random joint angles (no base velocity) and settled for 0.5 s
with its joints held: at the start it lies with its trunk tilted 128.4 deg from upright. You have 300 control steps
(6 s) per episode.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
