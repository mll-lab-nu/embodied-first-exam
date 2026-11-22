# DexHand · Fixed-wrist multi-axis marked sphere reorientation (standard)

## Task
One dexterous hand on a six-axis wrist stage, the wrist locked (no arm), holding a free marked sphere (DexHand, MuJoCo).
With the wrist fixed, rotate the marked sphere +90 degrees about palm-local Y, then +90 degrees about palm-local X from
that pose, then back to its exact initial orientation, keeping hand contact throughout.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order, each held briefly: the sphere turned a positive quarter turn about palm-local Y; from there a
positive quarter turn about palm-local X; back in its exact initial orientation, held still at the end. At least two
fingertips hold the sphere at each of these poses. What counts is how things stand at the end of the episode: a success
reached earlier and lost by the end does not count, so finish in the state you want graded and stop sending commands.

The episode ends at once as a failure if the sphere loses all contact with the hand, rests on anything else, moves far
from its place in the hand or drops low, the fingers squeeze it hard, the palm moves, or the physics becomes unstable.
Later actions cannot undo a failure.

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
obs = r.get_obs(cameras=["overview", "inhand_top"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
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
`rows` is `(T, 28)` (Sharpa) or `(T, 26)` (Wuji) in `spec["action_types"]["joint_position"]["layout"]` order: wrist XYZ
translations (metres), three serial XYZ rotational joints (radians), then the 22 or 20 finger joints (radians). Actuator
targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between
0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts
from the previous target. The robot has no scalar gripper opening.

Sharpa rows: the six wrist targets, then
`right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`,
`right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows:
the same six wrist targets, then `r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`,
`MFJ0..3`, `RFJ0..3`, `LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview, side, palm
(behind the hand), and two close-ups of the held object, `inhand_top` (from above the palm) and `inhand_side` (from the
thumb side), at 640 x 480; the default is overview and inhand_top. No object state is published: the close-ups (with
depth and their calibration) are how you see the object in the hand.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands are mounted in the same wrist frame. Each hand starts from its own finger pose (Wuji:
`wuji_reset.json`), with the object held as at the Sharpa start.

### Robot
Palm-local axes belong to a frame fixed to the palm; with the wrist locked it is aligned with the world axes: +X points
from the wrist toward the fingertips (world +x), +Y points across the palm from the thumb side toward the little-finger
side (world +y), and +Z points out of the palm, which faces up (world +z). In the simulator it has the orientation of
the `wrist_stage` body (the identity quaternion while the wrist is locked), not that of the palm link `right_hand_C_MC`,
whose own axes are rotated relative to it. A turn about a palm-local axis is about that palm-fixed axis (it does not
turn with the object), and a positive angle follows the right-hand rule: counterclockwise when seen from the positive
end of the axis looking back toward the palm. So +90 degrees about Y carries the side of the sphere that faces up toward
the fingertips, and +90 degrees about X carries the side that faces up toward the thumb side.

You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently actuated
finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands). The wrist stage is position actuated in the physics
engine; grasping and manipulating require physical contact. The five fingers are thumb, index, middle, ring and pinky.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints. The first six
entries of every action must remain [-0.08, 0, 0.29, 0, 0, 0]. Float32 wire-format rounding is accepted and normalized
to those exact fixed targets before physics runs. Use the declared target values rather than copying measured wrist
joint positions. Only the finger targets may change. Objects have no actuators, scripted motion or grasp attachments;
they move through contact and normal gravity.

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
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
