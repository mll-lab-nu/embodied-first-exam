# DexToolBench · short screwdriver · spin_vertical (standard-mcp)

## Task
A KUKA iiwa 14 arm with a 22-joint Sharpa HA4 dexterous hand stands next to a table with a short screwdriver on it
(DexToolBench, MuJoCo). Pick up the short screwdriver and move it through the demonstrated motion (spinning it about a
vertical axis): bring it to each of the 76 goal poses in order (the green ghost tool shows the current goal). The robot
runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: the short screwdriver has been brought to each of its 76 goal poses in turn, in order; a goal counts once the
whole tool matches the ghost's pose closely (position and orientation), and the next one then appears. The episode ends
as soon as the task is done. Goals have no time limit here. There is no partial credit (goals reached / 76 is only
reported, as `progress`).

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration), its own joint positions, velocities
  and targets, and the current goal pose with the count of goals reached; no object poses, no scene layout; the episode
  ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the scene's world frame (z up), not the arm's base: the table's centre is at x = y =
0 with its top at z = 0.53 m, and the iiwa's base stands at (0, 0.8, 0); no part here takes an end-effector pose;
metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, no end-effector pose);
left_hand (hand: 22 joints, no end-effector pose). Cameras: `front`, `side`, `top`, `oblique`.

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
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The arm and the hand take joint positions only: there is no end-effector pose command and no kinematics
service here, so placing the hand or the tool means choosing the iiwa's 7 joint angles (limits in describe_robot). Rows
are one control step apart (1/60 s) and each row's targets are held or ramped linearly between rows. The goals are shown
in the images as a green ghost copy of the tool, one goal at a time in order; the current goal counts as reached when
the tool closely matches the ghost's pose, and the next one then appears. Goals have no time limit; the episode ends
when every goal is reached, at its control-step limit, or when your time is up. Time passes only inside calls.

### Observations
- Cameras: `front`, `side`, `top`, `oblique`, all fixed; RGB 240 × 320, depth on request (metres).
- Each image comes with its camera's calibration (intrinsics and pose); depth is the distance along the viewing axis, in
  metres.
- Proprioception (`proprio_now`): the joint positions, velocities and current targets.
- The current goal (the tool result's `task`): its pose (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`,
  `goals_reached`, `steps_left_on_goal` (null: goals have no time limit here). The benchmark shows the controller the
  current goal, and the images show it as the green ghost tool.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 11 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`reset_episode()`), each a new episode from the same starting state.
- Steps: each episode ends after 360,000 control steps (100 min of robot time).
