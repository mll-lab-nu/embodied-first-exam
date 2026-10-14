# MuJoCo Playground · Go1Handstand — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Make the Unitree Go1 do a handstand: balance on its front legs, nose down, hind legs in the air, for 2 s.

You control the Unitree Go1 quadruped — **as if it were real hardware** — in one episode of MuJoCo Playground's
`Go1Handstand` environment (plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you
cannot open. You get one client and one episode.

## The episode
The robot starts standing at Playground's `home` pose with a random base velocity (Playground's reset). You have 500 control steps (10 s).

## Rules (real-robot rules)
- **No reset.** One episode. You see four cameras that follow the robot (RGB, depth if you ask) and the robot's own
  sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts. No world positions, no success check.
- **The episode ends** the moment the pose has been held for 100 control steps in a row (success), when the robot meets the termination rule (the trunk's up axis below -0.25 (z component of the IMU frame's z axis), or any part of a front leg other than its foot (thigh, calf, hip) touching the floor: a failure), after 500 control steps (`spec["max_control_steps"]`), when you submit `done`, or when your time is up.
- **Success** is 100 control steps in a row (2 s) with the trunk's forward axis (the IMU frame's x axis) within 30 deg of straight down, the IMU at least 0.4 m above the floor, and the hind (RR, RL) feet off the ground, without a termination before; judged after every control step.
- Your only budget is the time limit (`## Time limit`). Simulated time only advances with your commands (and
  `get_obs(seconds=...)`, which holds the current targets). `meta["time_left_s"]` is the service's count of the limit,
  from your first request to the service: it never runs out before your time does, so plan by it.
- Nothing to hand in: the service records the episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- Nothing is put into your context automatically: images come back as arrays in Python objects.

## Client (`/opt/tools/rcb_client.py`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the current targets and watch for 1 s (max 30)
r.fk(q); r.ik({"FR": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
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
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
