# MuJoCo Playground · Go1JoystickRoughTerrain — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Make the Unitree Go1 follow the joystick command schedule on rough terrain (a 20 x 20 m heightfield, up to 5 cm high) for the whole 20 s episode without falling over.

You control the Unitree Go1 quadruped — **as if it were real hardware** — in MuJoCo Playground's
`Go1JoystickRoughTerrain` environment (plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you
cannot open. You get one client and up to 11 episodes.

## The episode
The robot starts at Playground's `home` pose, its base moved to (-0.096, 0.049) m and turned to a yaw of 118.2 deg, with a random base velocity (Playground's reset). The ground is Playground's rough terrain: a 20 x 20 m heightfield (`hfield.png`, up to 5 cm high) centred on the world origin, with nothing beyond its edge.
For 20 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after Exp(1) x 5 s; a draw may keep a component). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +1.137 | +0.168 | -0.703 |
| 0.34 | +1.137 | +0.000 | -0.703 |
| 2.76 | -1.078 | -0.702 | +0.000 |
| 10.96 | -1.078 | +0.000 | +0.787 |
| 11.88 | +0.000 | -0.359 | +0.787 |
| 12.22 | +0.000 | -0.359 | +0.000 |
| 13.48 | -0.036 | +0.000 | -0.087 |

The same schedule is `spec["command_schedule"]`; every response's `meta["command_now"]` is the current command.

## Rules (real-robot rules)
- **Episodes and resets.** You have **10 resets** (`spec["budget"]["reset"]`, which is authoritative: if it
  says 0, there is no reset and the one episode is the run). A reset (`POST /reset`, below) puts the robot back on the
  same frozen starting state and starts a new episode, either abandoning the running one or after one has ended; it
  takes no simulated time and returns the start's images and proprioception. Once an episode has ended, `submit`
  raises `EpisodeOver` until you reset. **Only the last episode is graded**: an episode you reset away is never graded,
  a success ends the run at once (no reset after it), and when your time is up the episode then running is the one
  graded. The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the
  episodes (`meta["control_steps"]` is the current episode's).
- **No privileged state.** You see the cameras that follow the robot (RGB, depth if you ask) and the robot's own
  sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts. No world positions, no success check.
- **The episode ends** after 1000 control steps, the whole schedule (`spec["max_control_steps"]`, counted by `meta["control_steps"]`), when the robot meets its termination rule (the trunk's up axis pointing below the horizon (the z component of the IMU frame's z axis negative): a failure), when you submit `done`, or when your time is up (before the end of the schedule, both are failures).
- **Success** is judged on the whole schedule: no termination, and in every command segment, after its first 25 control steps, a mean |v_xy - cmd_xy| of at most 0.2 m/s (`imu_linvel`) and a mean |w_z - cmd_wz| of at most 0.3 rad/s (`imu_gyro`).
- Your only budget is the time limit (`## Time limit`). Simulated time only advances with your commands (and
  `get_obs(seconds=...)`, which holds the current targets). `meta["time_left_s"]` is the service's count of the limit,
  from your first request to the service: it never runs out before your time does, so plan by it.
- Nothing to hand in: the service records the episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (a crash
  is never a reset and costs none) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- Nothing is put into your context automatically: images come back as arrays in Python objects.

## Client (`/opt/tools/rcb_client.py`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the current targets and watch for 1 s (max 30)
r.fk(q); r.ik({"FR": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```
Cameras: `track`, `side`, `back`, `top` (they follow the robot); `spec["cameras"]` gives each one's mounting and intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`, `joint_effort` (12 each, action
order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame: x forward, y left, z up),
`foot_contact` (FR, FL, RR, RL).

### `joint_position` (12)
FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee): absolute targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5 N m s/rad).
Rows are `dt` apart (a whole multiple of the 0.02 s control period, at most 0.5 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at most 10 s; values outside the limits
(`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`. Feedback control
means short chunks: each response tells you where the robot is now.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
