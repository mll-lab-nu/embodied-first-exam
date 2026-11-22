# DexHand · Remove and reinstall a vacuum dust bin (standard-mcp)

## Task
Two dexterous hands, each on its own six-axis wrist stage (no arm), at a counter (DexHand, MuJoCo). Remove the dust bin
from the handheld vacuum on the counter and reinstall it: one hand steadies the vacuum (or works the button) while the
other handles the bin. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real
hardware.

## Goal
Success: in this order: the release button is pressed down (nearly its full travel) while the bin is still seated, and
the bin is taken clear of its seat; the bin is put back exactly in its seat, the button back up and the bin's catch
behind the latch tooth; then no hand touches the bin, the vacuum or the button, and both are still for a second. Partial
completion never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the vacuum body is moved or tilted; the bin falls (a free fall, or falling
while nothing touches it), touches the floor or a table leg, drops below the counter top or leaves the work area; bin
and vacuum are pressed into each other; or the physics becomes unstable. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame is the scene's world frame (+Z up; the wrist stage is fixed in it): the coordinates of
the task text; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand: 22 joints, no
end-effector pose); right (arm: 6 joints, no end-effector pose); left (arm: 6 joints, no end-effector pose); left_hand
(hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`.

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

This robot: Two hands on two wrist stages (parts right, left: stage joints; right_hand, left_hand: fingers), all joint
positions; the right stage's measured hand-mount pose comes back as ee. Every column is a position target (servo);
grasping and carrying work only through contact. The parts follow the Sharpa Wave layout (describe_robot spec_file: hand
"sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per hand) the columns differ: use execute_trajectory space
native with the order in spec action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call
covers at most 10 s. Measured poses are in the world frame of the task text, quaternions wxyz.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.65
m. Cameras are overview and closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for
`wuji`) and the exact order.

### Robot
You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin (0.45, 0.0, 0.8) m) and the left hand
(the right hand's mirror image) on `left_wrist_stage` (origin (0.55, 0.3, 0.95) m). Both are needed as in the real task:
one hand steadies the vacuum (or works the button) while the other handles the bin. The stages and the fingers are
position actuated in the physics engine under native force bounds; the vacuum body, the dust bin and the release button
move only through contact and their passive dynamics (the button is a spring-loaded slide). The controller runs at 50
Hz, with twenty 1 ms physics substeps.

Each stage's `x, y, z` targets are offsets (metres, along the world axes) from its origin; the rotations are serial XYZ
joints (radians).

Two hands, each on its own six-axis wrist stage. The left hand is the right Wave mirrored in y; one row is one 50 Hz
control (twenty 1 ms physics substeps).

### Scene
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m). The
tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button (nearly its full 6 mm)
lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction 0.55, so pushing the
catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's
bridge, so the seated bin cannot be lifted straight out: its top has to tilt out from under the lip, which the raised
tooth prevents. The vacuum-body frame is the body frame of `vacuum_body`; the seated bin pose in that frame is fixed by
the frozen start state (the bin starts seated). Cameras: `overview` (the counter from the front left) and `closeup` (the
latch and the bin).

## Others
- The bin is held by its two lower tabs on ledges at the bottom of the motor housing and by a spring latch at the top:
  the latch tooth on the red release button stops the bin's top catch from tilting out, and a fixed lip over the catch
  bridge stops it from being lifted straight out, so the top must tilt out from under the lip, which the tooth only
  allows while the button is pressed. The vacuum body, the bin and the button (a spring-loaded slide) move only through
  contact.

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
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`reset_episode()`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
