# MolmoSpaces · navigate-to (standard-mcp-shell)

## Task
A Rainbow Robotics RB-Y1 mobile manipulator (holonomic base, 6-joint torso, two 7-joint arms with parallel grippers,
head camera) in a simulated house (Ai2's MolmoSpaces, MuJoCo). Navigate to any tablelamp (2 available). The robot runs
as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client,
as if it were real hardware: one live episode.

## Goal
Success: the robot stands within about 1.5 m of a table lamp, and that lamp shows in its head camera; of the two lamps,
the one nearest the robot counts. What counts is how things stand at the end of the episode: a success reached earlier
and lost by the end does not count, so finish in the state you want graded and stop sending commands. End the episode
with `done` once the task holds; otherwise it ends at the step limit (Limits) or when your time is up.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: on the floor under the base's centre (base_x, base_y), +X the way the base faces (base_theta), +Y to
its left, +Z up; it moves with the base and is re-read at the start of every call; metres, radians, quaternions `wxyz`,
gripper 0 open .. 1 closed. Parts: torso (torso: 9 joints, no end-effector pose); left (arm: 7 joints, end-effector
pose, gripper); right (arm: 7 joints, end-effector pose, gripper); base (mobile: dx, dy, dyaw). Cameras: `head_camera`,
`wrist_camera_l`, `wrist_camera_r`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}` (the base: `{target: "base", dx, dy, dyaw}`); the
  parts move together and the call returns when the motion is done, with `reached` (the error per goal), a `failure`
  category if a goal was not reached, the state and a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: end the episode (`done`).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: One control step is 0.2 s of simulated time; the episode ends after spec_file max_control_steps steps (the
task's horizon). The base is position-controlled in the house's world frame: base_odometry in every result is its world
pose. The arms take joint positions; end-effector goals are solved by the service's IK and sent as joint positions.
gripper_opening_m is the measured distance between the fingertips.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service builds the episode)
spec = r.spec()                                # action types, limits, cameras (+ calibration), robot_spec, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (H, W, 3); obs.meta["proprio"] {"layout", "now"}
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (H, W) z-depth in m (0 = no reading)
res = r.submit("joint_position", A, dt=0.2)   # A: (T, 25) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.get_obs(seconds=2.0, video="mp4")      # hold the current targets and watch for 2 s (max 30; whole control
                                               # steps: obs.meta["seconds"] is what ran)
r.fk(q); r.ik({"left_gripper": pose7}, seed=q)        # upstream's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
- `meta["control_steps"]` counts the episode's control steps; `spec["max_control_steps"]` is the limit.
- One call returns at most 1812 images; nothing is put into your context automatically: images come back as arrays in
  Python objects.
- If the service crashes, a call fails with a connection error: the service restarts and resumes the same episode (never
  a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.

### Actions
- `joint_position` (25): `base_x`, `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`,
  `torso_5`, `left_arm_0`, `left_arm_1`, `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`,
  `right_arm_0`, `right_arm_1`, `right_arm_2`, `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`,
  `left_gripper`, `right_gripper`: the targets of upstream's joint-position controllers (base_x, base_y in m and
  base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive
  closes, negative opens, 0 exerts none)). Rows are `dt` apart (a whole multiple of the 0.2 s control period, at most
  0.5 s: up to 0.4 s), `interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s; values
  outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in
  `res.meta["clipped"]`. `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row
  order (`["layout"]` names every entry); the gripper entries of a row are commands in the units above, not the measured
  openings.
- `done` (no rows): `r.submit("done", [])` ends the episode at once.
- `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's world
  frame (z up, metres).

### Observations
- Cameras: `head_camera`, `wrist_camera_l`, `wrist_camera_r`; RGB, and depth when you ask for it (z-depth in metres, 0 =
  no reading). Each camera's intrinsics and mount are in `spec["cameras"]`, and every response carries each camera's
  pose.
- Proprioception, what a real robot reports: joint positions, velocities and efforts, the gripper openings and the tool
  poses.

## Others
One control step is 0.2 s of simulated time. Simulated time advances only with your commands and with
`get_obs(seconds=...)`: while you think, the robot waits. The service's `time_left_s` counts from your first request to
it, so it never reaches 0 before your time is up: plan by it.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 12 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 500 control steps (the benchmark's 100 s horizon); then the episode ends by itself and is graded as it
  stands.
