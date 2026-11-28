# MolmoSpaces · open-door (standard)

## Task
Pull the door open, at least 67% of the way.

## Goal
Success: the door is open at least 67% of the way. The `done` action is the same as `/finish`.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Rainbow Robotics RB-Y1 mobile manipulator (holonomic base, 6-joint torso, two 7-joint arms with parallel grippers,
head camera) in a simulated house (Ai2's MolmoSpaces, MuJoCo). The robot runs as a service you reach through its client
or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/3.0`):
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service builds the episode)
spec = r.spec()                                # action types, limits, cameras (+ calibration), robot_spec, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (H, W, 3); obs.meta["proprio"] {"layout", "now"}
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (H, W) z-depth in m (0 = no reading)
res = r.submit("joint_position", A, dt=0.1)   # A: (T, 25) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.hold(2.0)                              # hold the current targets for 2 s of robot time (whole control
                                               # steps: obs.meta["duration_s"] is what ran)
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({"left_gripper": pose7}, seed=q)        # the robot's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
- `meta["control_steps"]` counts the episode's control steps; `spec["max_control_steps"]` is the limit.
- One call returns at most 1812 images. Nothing is put into your context automatically: images come back as arrays in
  Python objects.
- If the service crashes, a call fails with a connection error: the service restarts and resumes the same episode (never
  a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- `joint_position` (25): `base_x`, `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`,
  `torso_5`, `left_arm_0`, `left_arm_1`, `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`,
  `right_arm_0`, `right_arm_1`, `right_arm_2`, `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`,
  `left_gripper`, `right_gripper`: the targets of the robot's joint-position controllers (base_x, base_y in m and
  base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive
  closes, negative opens, 0 exerts none)). Rows are `dt` apart (a whole multiple of the 0.1 s control period, at most
  0.5 s), `interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s; values outside the
  limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`.
  `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row order (`["layout"]` names
  every entry). In a row, the gripper entries are commands in the units above, not the measured openings.
- `done` (no rows): `r.submit("done", [])` ends the episode at once.
- `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's world
  frame (z up, metres).

### Observations
- Cameras: `head_camera`, `wrist_camera_l`, `wrist_camera_r`; RGB, and depth when you ask for it (z-depth in metres, 0 =
  no reading). Each camera's intrinsics and mount are in `spec["cameras"]`, and every response carries each camera's
  pose.
- Proprioception, what a real robot reports: joint positions, velocities and efforts, the gripper openings and the tool
  poses.

### Timing
One control step is 0.1 s of simulated time. Simulated time advances only with your commands and with `hold(s)`: while
you think, the robot waits. The service's `time_left_s` counts from your first request to the service, so it never
reaches 0 before your time is up. Plan by it.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 12 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 400 control steps (the benchmark's 40 s horizon), then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
