# DexHand · Hang a large picture on two wall hooks (standard)

## Task
Hang the framed picture on the two wall hooks.

## Goal
Success: in this order, the frame is lifted off the console; the left ring on its back is threaded on the left hook and
the right ring on the right hook, behind the hooks' lips; then the picture hangs from both hooks, each carrying part of
its weight, level and upright, off the console and the floor, with no hand touching it, and is still for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The frame touches the floor, leaves the work area or tilts far from upright.
- After the lift, the frame sinks below its start height.
- Once both rings are on, a ring falls off its hook.
- After the lift, the frame is held by nothing: dropped (even if caught again), let go early, dangling from one hook or
  resting on the hook lips.
- An arm, torso or stand link of the robot touches anything (only the hands may make contact).
- The physics becomes unstable.

Each step of the Goal before the last one counts at the moment it happens.

When you are done, send `/finish` to end the episode and get it graded. Everything else is judged on the state at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded. No reset is possible after
  `/finish`.
- You get only the cameras and the robot's own sensor readings: no live object poses, no score, no success signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms and both hands do the
task), facing a wall (DexHand, MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if
it were real hardware.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview", "hook_closeup"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements (tcp_pose: both palms, 7 columns each)
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
# a new episode: POST /reset, or the MCP tool `reset` (this client has no reset() call)
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `hold(s)` holds the current targets
and records those steps. `get_obs()` only observes the current state. Forward kinematics uses only the robot's own
links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()`
before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps
running.

Resets: `POST /reset` (MCP tool `reset`) starts a new episode from the same starting state. You can call it during a
running episode, which it abandons, or after one has ended. It takes no simulated time and returns the start's images
and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and
`meta["resets_left"]` count the episodes. `meta["control_steps"]` counts the current episode's control steps,
`meta["control_steps_total"]` those of all episodes.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets in
radians (left arm `SHOULDER_PITCH_L_J1_target` ... `WRIST_ROLL_L_J7_target`, then the right arm `..._R_J1_target` ...
`..._R_J7_target`), then the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22
Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand,
`l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3, l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for
`r_wuji_r_`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be a
multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7, radians), followed by the
left hand's finger targets and then the right hand's (22 per hand for `sharpa`: the genuine right Sharpa Wave on the
right flange and its declared mirror image on the left flange; 20 per hand for `wuji`: the manufacturer's left and right
Wuji Hand 2.2).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both wrist poses and current targets; the frame's state is not published, measure it with the cameras. Quaternions in
measured poses use WXYZ. Cameras are overview, front, side and hook_closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

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

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode, then the episode ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
