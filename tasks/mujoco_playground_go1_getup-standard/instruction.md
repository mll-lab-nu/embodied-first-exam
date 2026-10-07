# MuJoCo Playground · Go1Getup — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** The Unitree Go1 has fallen over. Make it get up and stand upright at its standing height.

You control the Unitree Go1 quadruped — **as if it were real hardware** — in one episode of MuJoCo Playground's
`Go1Getup` environment (plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you
cannot open. You get one client and one episode.

## The episode
The robot was dropped from 0.5 m in a random orientation with random joint angles and a random base velocity and settled for 0.5 s with its joints held: at the start it lies with its trunk tilted 110 deg from upright. You have 300 control steps (6 s).

## Rules (real-robot rules)
- **No reset.** One episode. You see four cameras that follow the robot (RGB, depth if you ask) and the robot's own
  sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts. No world positions, no success check.
- **The episode ends** the moment the robot has been upright for 25 control steps in a row (success), after 300 control steps (`spec["max_control_steps"]`, counted by `meta["control_steps"]`), when you submit `done`, or when your time is up.
- **Success** is 25 control steps in a row with the trunk within 10 deg of upright and the IMU at least 0.22 m above the floor (the Go1 stands at 0.255-0.26 m), judged after every control step; when the episode ends otherwise, it is judged on its last control steps.
- Your wall-clock budget is 3600 s from your start. Simulated time only advances with your commands (and
  `get_obs(seconds=...)`, which holds the current targets).
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
