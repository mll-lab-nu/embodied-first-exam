# DexHand · Hang a large picture on two wall hooks (standard-mcp)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms and both hands do the
task), facing a wall (DexHand, MuJoCo). Hang the framed picture on the two wall hooks: the free 2.0 kg frame (52 x 52 x
6 cm) stands upright on a console; two brass picture hooks are installed on the wall and two D-rings on passive hinges
are screwed to the back of the frame. Lift the frame off the console with both hands, engage both D-rings on their
matching hooks (left ring on the left hook, right ring on the right hook), then let go. The robot runs as a service you
reach only through the `efe-robot` MCP tools, as if it were real hardware.

## Goal
Success: in this order: the frame is lifted off the console; both rings are threaded on their own hooks (behind the
hooks' lips, not resting on top of them); then the picture hangs from both hooks, each carrying part of its weight,
level and upright, off the console and the floor, with no hand touching it, and is still for a second. One engaged hook,
or rings left on the hook lips, never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the frame touches the floor, leaves the work area, tilts far from upright,
sinks below its start height after the lift, or falls off a hook once both rings were engaged; if after the lift the
frame is held by nothing (no hand on it, not on the console, not hanging on both hooks): dropped, even if caught again,
released early, dangling from one hook or resting on the hook lips; if an arm, torso or stand link of the robot touches
anything (only the hands may make contact); or if the physics becomes unstable. Later actions cannot undo a failure.

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
`native`): the robot base frame is the Marvin stand origin (the floor point under its torso): +X the way the robot
faces, +Y to its left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand:
22 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose); right (arm: 7 joints, no end-effector
pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `front`, `side`, `hook_closeup`.

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

This robot: Two 7-joint arms (parts left, right) and two hands (left_hand, right_hand), all joint positions: no
end-effector pose command and no inverse kinematics; the measured hand-mount pose comes back as ee. The arm servos have
no gravity compensation (a held target sags about 1 cm at the hand under load). A one-hand task keeps the other arm
parked at its start targets. Every column is a position target (servo); grasping and carrying work only through contact.
The parts follow the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20
finger joints per hand) the columns differ: use execute_trajectory space native with the order in spec
action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured
poses are in the world frame of the task text, quaternions wxyz.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both wrist poses and current targets; the frame's state is not published, measure it with the cameras. Quaternions in
measured poses use WXYZ. Cameras are overview, front, side and hook_closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
the spec's `["hand"]`; the spec's `["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for
`wuji`) and the exact order.

### Robot
You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand on each wrist. The
arm joints and the fingers are position actuated in the physics engine under native force bounds; the frame moves only
through contact, gravity and its two passive ring hinges, so lifting, carrying, hooking and releasing all require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

Both arms and both hands perform the task.

Arm servos: kp 700 N m/rad, kv 48, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity
compensation; each hand sits rigidly on its arm's flange.

### Scene
World frame: metres, z up, x pointing into the wall.

- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19; the console stands on its two rear legs (x =
  0.615) so that the robot stand's base plate fits under its front half.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre of
  its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The robot stand faces the wall (+x) in front of the console, its base origin at (0.18, 0.00, 0.20): it stands on a
  0.10 m plinth exactly under its base plate; the shoulders are 1.121 m above the base origin, at y = +-0.2215. Only the
  hands may touch anything: any contact of an arm, torso or stand link with the frame, the hooks, the wall, the console,
  the floor or the other hand ends the episode (`robot_collision`).
- At the start both hands hang palm-inward above the frame's side rails, fingers pointing down, thumbs toward the wall.
  With `sharpa` the right hand is the genuine Sharpa Wave right hand and the left hand is a declared mirror image of it
  (the right model reflected, same joints, ranges and force limits); with `wuji` both are the manufacturer's left and
  right Wuji Hand 2.2 models.

The start targets hold the hands above the frame with open fingers.

## Others
- The frame moves only through contact, gravity and its two passive ring hinges.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`reset_episode()`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
