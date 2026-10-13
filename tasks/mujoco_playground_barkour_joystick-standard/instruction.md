# MuJoCo Playground · BarkourJoystick — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.

You control the Google Barkour vB quadruped — **as if it were real hardware** — in one episode of MuJoCo Playground's
`BarkourJoystick` environment (plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you
cannot open. You get one client and one episode.

## The episode
The robot starts standing still at Playground's `home` pose (this environment's reset does not move it). The ground is flat. One control step is 10 ms of simulated time: Playground's Barkour environment keeps Menagerie's 2 ms timestep and takes 5 substeps.
For 10 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after 501 control steps). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +0.459 | +0.221 | +0.016 |
| 5.01 | +0.090 | -0.389 | +0.643 |

The torso is pushed 12 times at moments you are not told (Playground's kicks: half-sine pushes of up to 35 N lasting 0.05 s, in random horizontal directions).

The same schedule is `spec["command_schedule"]`; every response's `meta["command_now"]` is the current command.

## Rules (real-robot rules)
- **No reset.** One episode. You see four cameras that follow the robot (RGB, depth if you ask) and the robot's own
  sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts. No world positions, no success check.
- **The episode ends** after 1000 control steps, the whole schedule (`spec["max_control_steps"]`, counted by `meta["control_steps"]`), when the robot meets its termination rule (the trunk's up axis pointing below the horizon, a joint outside its box (abduction [-0.7, 0.52], hip [-1.0, 2.1], knee [0.05, 2.1] rad) or the torso lower than 0.18 m: a failure), when you submit `done`, or when your time is up (before the end of the schedule, both are failures).
- **Success** is judged on the whole schedule: no termination, and in every command segment, after its first 25 control steps, a mean |v_xy - cmd_xy| of at most 0.2 m/s (`imu_linvel`) and a mean |w_z - cmd_wz| of at most 0.3 rad/s (`imu_gyro`).
- Your only budget is the time limit (`## Time limit`). Simulated time only advances with your commands (and
  `get_obs(seconds=...)`, which holds the current targets). `meta["time_left_s"]` is the service's count of the limit,
  from your first call to the service; approximate — the harness's own deadline is authoritative.
- Nothing to hand in: the service records the episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- Nothing is put into your context automatically: images come back as arrays in Python objects.

## Client (`/opt/tools/rcb_client.py`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.01)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the current targets and watch for 1 s (max 30)
r.fk(q); r.ik({"foot_front_left": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `track` (follows the robot) and `realsense/rgb` (on its head); `spec["cameras"]` gives each one's mounting and intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`, `joint_effort` (12 each, action
order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame: x forward, y left, z up),
`foot_contact` (foot_front_left, foot_hind_left, foot_front_right, foot_hind_right).

### `joint_position` (12)
front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee: absolute targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the actuators' own damping of 0.5 N m s/rad).
Rows are `dt` apart (a whole multiple of the 0.01 s control period, at most 0.5 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at most 10 s; values outside the limits
(`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`. Feedback control
means short chunks: each response tells you where the robot is now.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left. Installing packages is not cheating (`## External material` above).
