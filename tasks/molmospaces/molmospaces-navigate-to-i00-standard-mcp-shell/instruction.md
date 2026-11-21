# MolmoSpaces · navigate-to — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service, eai-standard/2.2)

**Task:** Navigate to any tablelamp (2 available).

You control a Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera — **as if it were real hardware** — in one episode of Ai2's MolmoSpaces benchmark (several objects of the target type (the nearest counts)).
The simulator (upstream's own code: molmo-spaces 0.2.9, MuJoCo 3.5.0) runs in a service you cannot open. You get one
client and one episode.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: on the floor under the base's centre (base_x, base_y), +X the
way the base faces (base_theta), +Y to its left, +Z up; it moves with the base and is re-read at the start of every
call. Space `native` sends rows in the robot's own action types exactly as the sections below describe them (their
frame, units and gripper values).

**This robot** (Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with parallel
grippers, head camera): torso (torso: 9 joints); left (arm: 7 joints, end-effector pose, gripper); right (arm: 7 joints,
end-effector pose, gripper); base (mobile: dx, dy, dyaw). Cameras: `head_camera`, `wrist_camera_l`, `wrist_camera_r`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}` (the base: `{target: "base", dx, dy, dyaw}`); the
  parts move together and the call returns when the motion is done, with `reached` (errors per goal), a `failure`
  category if a goal was not reached, the state and the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** One control step is 0.2 s of simulated time; the episode ends after spec_file max_control_steps
steps (the task's horizon). The base is position-controlled in the house's world frame: base_odometry in every result is
its world pose. The arms take joint positions; end-effector goals are solved by the service's IK and sent as joint
positions. gripper_opening_m is the measured distance between the fingertips.

## Rules (real-robot rules)
- **No reset.** One episode. You see the robot's cameras (RGB, depth if you ask) and its proprioception (joints,
  grippers, tool poses, velocities, efforts). No object poses, no success check.
- **The episode ends** after **500 control steps** (the benchmark's 100 s horizon at
  5 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`), when you submit `done`
  (`r.submit("done", [])`), or when your time is up.
- **Success** is upstream's `judge_success()` on the state at that moment: for the one of the 2 target objects nearest to the robot base (horizontal distance), the horizontal distance from the base to its position (the origin of its body, not its nearest surface) is less than 1.5 m and at least one of its pixels shows in head_camera. The task has to hold at the
  end: met earlier and undone by then does not count, so end the episode with `done` once it holds. The service
  judges your episode itself, on the state it ends in; it scores 1 if that state succeeds.
- Your only budget is the time limit (`## Time limit`), from your start (the service's `time_s` and `time_left_s`
  count from your first request to it, so `time_left_s` never reaches 0 before your time is up: plan by it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`).
- Nothing to hand in: the service records the episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- Nothing is put into your context automatically: images come back as arrays in Python objects.

## Client (`/opt/tools/rcb_client.py`)
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
Cameras: `head_camera`, `wrist_camera_l`, `wrist_camera_r` (`spec["cameras"][cam]`: intrinsics and mount; every response carries each camera's pose).
One call returns at most 1812 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

### `joint_position` (25)
`base_x`, `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`, `torso_5`, `left_arm_0`, `left_arm_1`, `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`, `right_arm_0`, `right_arm_1`, `right_arm_2`, `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`, `left_gripper`, `right_gripper`: the targets of upstream's joint-position controllers (base_x, base_y in m and base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive closes, negative opens, 0 exerts none)). Rows are `dt` apart (a
whole multiple of the 0.2 s control period, at most 0.5 s: up to 0.4 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at
most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in
`res.meta["clipped"]`. `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row
order (`["layout"]` names every entry); the gripper entries of a row are commands in the units above, not the measured
openings. `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's
world frame (z up, metres).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **12 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
