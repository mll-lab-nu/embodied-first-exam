# MuJoCo Playground · BarkourJoystick (standard)

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over, even when it gets pushed.

## Goal
Success: the robot never falls, and through every command of the schedule its speed and turning follow that command
closely on average. A fall (the trunk tipping over, or dropping low) or a leg joint leaving its allowed range (Robot
Interface) ends the episode at once, as a failure. Success is judged on the whole run, and only an episode that lasts to
the end of the schedule can succeed. The `done` action is the same as `/finish`.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded. No reset is possible after `/finish`.
- You get only the cameras and the robot's own sensors (joint positions, velocities and torques, the IMU, foot
  contacts): no world positions, no success signal.

## Robot Interface
Google's Barkour vB quadruped (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no
walking or balance controller. The robot runs as a service you reach through its client or its MCP tools, as if it were
real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.01)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.hold(1.0)                              # hold the targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({"foot_front_left": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now (the same as finish)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `hold(s)`, which holds the current targets). A reset
(`POST /reset`, the `_post` line above) puts the robot back on the same frozen starting state and starts a new episode.
You can reset during an episode (abandoning it) or after one has ended. A reset takes no simulated time and returns the
start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall
clock covers the whole run and never restarts. `meta["episode"]` and `meta["resets_left"]` count the episodes;
`meta["control_steps"]` counts only the current episode's steps. If the service crashes, a call fails with a connection
error. The service restarts and resumes the same episode (never a reset), in the state after the last call it completed.
`r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 3000 images.

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
Action type `joint_position` (12): front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee:
absolute targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the
actuators' own damping of 0.5 N m s/rad). Rows are `dt` apart (a whole multiple of the 0.01 s control period, at most
0.5 s), `interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s; values outside the
limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`. Feedback
control means short chunks: each response tells you where the robot is now.

The allowed joint ranges (leaving one ends the episode as a failure): abduction [-0.7, 0.52], hip [-1.0, 2.1], knee
[0.05, 2.1] rad.

### Observations
Cameras: `track` (follows the robot) and `realsense/rgb` (on its head); `spec["cameras"]` gives each one's mounting and
intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`,
`joint_effort` (12 each, action order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame:
x forward, y left, z up), `foot_contact` (foot_front_left, foot_hind_left, foot_front_right, foot_hind_right).

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. The schedule is `spec["command_schedule"]` (each segment's start and command); every response's
`meta["command_now"]` is the current command.

### Episode
The robot starts standing still at its `home` pose. The ground is flat. The episode lasts the whole schedule (10 s, 1000
control steps).

### Pushes
The torso is pushed 12 times at moments you are not told (half-sine pushes of up to 35 N lasting 0.05 s, in random
horizontal directions).

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: the episode ends at the end of the schedule, after 10 s of robot time.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
