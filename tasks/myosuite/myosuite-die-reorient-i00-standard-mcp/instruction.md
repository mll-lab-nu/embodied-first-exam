# MyoSuite · die_reorient (standard-mcp)

## Task
The MyoHand, a musculoskeletal model of a human forearm and hand (MyoSuite, MuJoCo), driven only through its actuators
(39 muscles): there is no joint-level controller. A die rests in the palm of the upturned hand; a translucent target die
shows the goal orientation. Turn the die in the hand until it matches the target die. The robot runs as a service you
reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: the die matches the target die's position and orientation closely and holds it for a second. The episode ends
as soon as the task is done; it ends as a failure when the die is dropped (it gets far from the target).

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- No privileged state: you get the camera images (with their calibration) and the body's own proprioception (joint
  positions, velocities and actuator torques, muscle activations and lengths); no object, ball, opponent or goal poses;
  the episode ends when the task is done, and the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the simulator's world frame (z up): camera poses are given in it; no part here takes
an end-effector pose; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: the robot's own action
types only (`execute_trajectory` space `native`). Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`,
`hand_side_inter`, `hand_side_exter`, `plam_lookat`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: A muscle's command a sets its excitation u = 1 / (1 + exp(-5 (a - 0.5))), not clipped (a = -1: about 0.0006,
a = 0.5: 0.5, a = 1: 0.92); activation follows excitation with a short delay (about 10 ms up, 40 ms down); muscles only
pull, one muscle can cross several joints, and its force depends on its length and speed. Before your first command of
an episode every column holds -1 (all muscles relaxed). Every command goes through execute_trajectory space native
(action_type muscle, 39 numbers per row). The robot's own action type takes one row per control step (the control period
is in describe_robot), columns in its layout (describe_robot: action_types_native; spec_file has each actuator, muscle
and joint). The state is proprio_now (layout in spec_file: proprio_layout, proprio_groups): joint positions and
velocities, muscle activations and lengths, joint efforts. There is no joint-level controller: joints move only through
muscle forces. Time passes only inside calls; the service says when the episode ended and why, never the object or goal
state.

### Observations
Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat`
(640x480; default `hand_top`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on the forearm (the
radius): they move with it (pronation turns them), so use the pose returned with each frame; the spec's `["cameras"]`
gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and
every response carries each frame's pose. Proprioception (the spec's `["proprio_groups"]`): `joint_pos` (`q_<joint>`),
`joint_vel` (`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort`
(`effort_<joint>`, the actuators' generalized force on each joint).

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
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`reset_episode()`), each a new episode from the same starting state.
