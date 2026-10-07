# MuJoCo Playground · Go1JoystickFlatTerrain — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Make the Unitree Go1 follow the joystick command schedule on flat ground for the whole 20 s episode without falling over.

You control the Unitree Go1 quadruped — **as if it were real hardware** — in one episode of MuJoCo Playground's
`Go1JoystickFlatTerrain` environment (plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you
cannot open. You get one client and one episode.

## The episode
The robot starts at Playground's `home` pose, its base moved to (-0.493, -0.479) m and turned to a yaw of -142.4 deg, with a random base velocity (Playground's reset). The ground is flat.
For 20 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after Exp(1) x 5 s; a draw may keep a component). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +1.413 | -0.611 | +0.712 |
| 0.84 | -0.253 | -0.611 | +0.712 |
| 4.76 | -0.253 | -0.611 | +0.000 |
| 5.96 | -0.552 | -0.611 | +0.000 |

The same schedule is `spec["command_schedule"]`; every response's `meta["command_now"]` is the current command.

## Rules (real-robot rules)
- **No reset.** One episode. You see four cameras that follow the robot (RGB, depth if you ask) and the robot's own
  sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts. No world positions, no success check.
- **The episode ends** after 1000 control steps, the whole schedule (`spec["max_control_steps"]`, counted by `meta["control_steps"]`), when the robot meets its termination rule (the trunk's up axis pointing below the horizon (the z component of the IMU frame's z axis negative): a failure), when you submit `done`, or when your time is up (before the end of the schedule, both are failures).
- **Success** is judged on the whole schedule: no termination, and in every command segment, after its first 25 control steps, a mean |v_xy - cmd_xy| of at most 0.2 m/s (`imu_linvel`) and a mean |w_z - cmd_wz| of at most 0.3 rad/s (`imu_gyro`).
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
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
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
