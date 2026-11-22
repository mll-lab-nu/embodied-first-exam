# MuJoCo Playground · SpotJoystickGaitTracking (standard)

## Task
Boston Dynamics Spot (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no walking
or balance controller. It starts standing still at its `home` pose. The ground is flat. Make it follow the joystick's
command schedule for the whole 20 s episode with the commanded gait (the feet's swing pattern, frequency and height),
without falling over. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: for the whole schedule the robot never falls; in every command's stretch, after a short settling time at its
start, its velocity over the ground (in its own frame) and its turning rate follow the command closely on average, and
its feet follow the gait's target heights closely. The episode lasts the whole schedule (20 s, 1000 control steps); a
fall (the trunk tilting well over) ends it at once, as a failure, and so does ending it yourself (`done`) or running out
of time before the schedule's end.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged state: you get the camera images (with their calibration) and the robot's own sensors (joint positions,
  velocities and torques, the IMU, foot contacts); no world positions; when the episode ends, the service tells you that
  it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule, gait
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the targets and watch for 1 s (max 30)
r.fk(q); r.ik({"FL": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the current targets). A reset
(`POST /reset`, the `_post` line above) puts the robot back on the same frozen starting state and starts a new episode,
either abandoning the running one or after one has ended; it takes no simulated time and returns the start's images and
proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock is the run's
and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes (`meta["control_steps"]` is the
current episode's). If the service crashes, a call fails with a connection error: it restarts and resumes the same
episode (never a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check
`r.status()`. One call returns at most 3000 images.

### Actions
Action type `joint_position` (12): FL, FR, HL, HR legs, each hx (abduction), hy (hip pitch), kn (knee): absolute targets
of the joint position actuators (rad; kp = 400 N m/rad, joint damping 10 N m s/rad, plus the actuators' own damping of
20 N m s/rad). Rows are `dt` apart (a whole multiple of the 0.02 s control period, at most 0.5 s),
`interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s; values outside the limits
(`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`. Feedback control
means short chunks: each response tells you where the robot is now.

### Observations
Cameras: `track`, `side`, `back`, `top` (they follow the robot); `spec["cameras"]` gives each one's mounting and
intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`,
`joint_effort` (12 each, action order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame:
x forward, y left, z up), `foot_contact` (FL, FR, HL, HR).

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. The schedule is `spec["command_schedule"]` (each segment's start and command); every response's
`meta["command_now"]` is the current command. The gait: a pace at 3.66 Hz, swing height h = 0.129 m. Foot i's target
height at control step t follows its phase phi = phase0[i] + t * phase_dt, wrapped to [-pi, pi), with phase0 = [0.0,
3.1416, 0.0, 3.1416] (feet FL, FR, HL, HR) and phase_dt = 0.4597 rad: with x = (phi + pi) / (2 pi), it rises as h (s^3 +
3 s^2 (1 - s)) with s = 2x over x in [0, 0.5] and falls as h minus that with s = 2x - 1 over [0.5, 1]. `spec["gait"]`
gives it.

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
