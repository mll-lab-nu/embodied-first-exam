# DexHand · Hang a large picture on two wall hooks (standard)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms and both hands do the
task), facing a wall (DexHand, MuJoCo). Hang the framed picture on the two wall hooks: the free 2.0 kg frame (52 x 52 x
6 cm) stands upright on a console; two brass picture hooks are installed on the wall and two D-rings on passive hinges
are screwed to the back of the frame. Lift the frame off the console with both hands, engage both D-rings on their
matching hooks (left ring on the left hook, right ring on the right hook), then let go.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the frame is lifted off the console; both rings are threaded on their own hooks (behind the
hooks' lips, not resting on top of them); then the picture hangs from both hooks, each carrying part of its weight,
level and upright, off the console and the floor, with no hand touching it, and is still for a second. One engaged hook,
or rings left on the hook lips, never counts. What counts is how things stand at the end of the episode: a success
reached earlier and lost by the end does not count, so finish in the state you want graded and stop sending commands.

The episode ends at once as a failure if the frame touches the floor, leaves the work area, tilts far from upright,
sinks below its start height after the lift, or falls off a hook once both rings were engaged; if after the lift the
frame is held by nothing (no hand on it, not on the console, not hanging on both hooks): dropped, even if caught again,
released early, dangling from one hook or resting on the hook lips; if an arm, torso or stand link of the robot touches
anything (only the hands may make contact); or if the physics becomes unstable. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: when your time is up the
  episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
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
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

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

## Others
- The frame moves only through contact, gravity and its two passive ring hinges.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; there the episode ends and is graded as it
  stands.
