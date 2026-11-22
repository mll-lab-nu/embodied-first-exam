# DexToolBench · claw hammer · swing_down (standard-mcp-shell)

## Task
A KUKA iiwa 14 arm with a 22-joint Sharpa HA4 dexterous hand stands next to a table with a claw hammer on it
(DexToolBench, MuJoCo). Pick up the hammer and move it through the demonstrated *swing-down* motion: bring it to each of
the 37 goal poses in order (the green ghost hammer shows the current goal). The robot runs as a service you reach
through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real
hardware.

## Goal
Success: the claw hammer has been brought to each of its 37 goal poses in turn, in order; a goal counts once the whole
tool matches the ghost's pose closely (position and orientation), and the next one then appears. The episode ends as
soon as the task is done. Goals have no time limit here. There is no partial credit (goals reached / 37 is only
reported, as `progress`).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration), its own joint positions, velocities
  and targets, and the current goal pose with the count of goals reached; no object poses, no scene layout; the episode
  ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the scene's world frame (z up), not the arm's base: the table's centre is at x = y = 0 with its top
at z = 0.53 m, and the iiwa's base stands at (0, 0.8, 0); no part here takes an end-effector pose; metres, radians,
quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, no end-effector pose); left_hand (hand: 22
joints, no end-effector pose). Cameras: `front`, `side`, `top`, `oblique`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: The arm and the hand take joint positions only: there is no end-effector pose command and no kinematics
service here, so placing the hand or the tool means choosing the iiwa's 7 joint angles (limits in describe_robot). Rows
are one control step apart (1/60 s) and each row's targets are held or ramped linearly between rows. The goals are shown
in the images as a green ghost copy of the tool, one goal at a time in order; the current goal counts as reached when
the tool closely matches the ghost's pose, and the next one then appears. Goals have no time limit; the episode ends
when every goal is reached, at its control-step limit, or when your time is up. Time passes only inside calls.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # camera names
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> float16 metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joint positions, velocities, current targets
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]                              # see below
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold the targets and watch for 2 s (max 30)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 29) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
obs = r.reset(cameras=cams)                   # a new episode from the starting state; obs.meta["resets_left"]
```
The episode ends when every goal is reached or at the step limit (`spec()["max_control_steps"]`); after that `submit`
raises `EpisodeOver` (409) until you reset. `r.reset(cameras=None, include_depth=False)` (`POST /reset`): a new episode
from the same starting state; it returns the start's frames, and `meta` (also `r.status()`) carries `episode`,
`resets_left` and `control_steps_total`. Resetting does not stop or restore the clock. Calibration:
`meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x
right, y up, the camera looks along -z; the viewpoint the image is rendered from), for the state at the end of that call
(the `last` image and the last frame of every stack). One call returns at most 3000 images.

### Actions
`joint_position`, 29 numbers per row: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in
`spec()["action_types"]["joint_position"]["layout"]`); rows are `dt` apart (a multiple of `control_dt`), each held
(`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
limits in the spec. A chunk covers at most 10 s.

### Observations
- Cameras: `front`, `side`, `top`, `oblique`, all fixed; RGB 240 × 320, depth on request (metres).
- Each image comes with its camera's calibration (intrinsics and pose); depth is the distance along the viewing axis, in
  metres.
- Proprioception (`obs.meta["proprio"]`): the joint positions, velocities and current targets.
- The current goal (`meta["task"]`): its pose (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`,
  `steps_left_on_goal` (null: goals have no time limit here). The benchmark shows the controller the current goal, and
  the images show it as the green ghost tool.

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
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 11 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 360,000 control steps (100 min of robot time).
