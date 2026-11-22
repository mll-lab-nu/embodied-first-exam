# DexHand · Install a desk fan front guard (standard)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a worktop (DexHand, MuJoCo). Install the front guard on the
unpowered desk fan: the fan stands on the worktop facing the operator (its axis along world -x), the four U clips of its
rear wire guard (at 45, 135, 225 and 315 degrees around the rim) start swung open, and the detached front guard (a 0.369
m wire cage with a raised hub cap) lies flat on the worktop, dome up. Lift the guard, turn it upright with its dome
facing the operator, seat its rim on the rear rim, close all four clips over the two rims, and take the hand away.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the guard is seated centred on the rear rim and square to the fan, with all four clips closed and locked over
both rims (each upper clip locked over the seated guard; the lower clips may be closed before or after it is seated);
then the hand touches neither the guard, the clips nor the fan, and the guard is still for a second. A guard that is
only placed, or clips that are only partly closed, never count. The episode ends as soon as the task is done.

The episode ends at once as a failure if the fan is moved or tilted; the guard, once lifted, touches the worktop, a
table leg or the floor again, or is dropped, even if caught again; the guard touches the fan's base, stem, neck, motor
housing, feet or buttons; the guard falls below the worktop or leaves the work area; or the physics becomes unstable.
Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview"], depth=True)
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then
the finger targets in radians. `D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`,
`r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits
and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the worktop is at z = 0.65 m.
Cameras are overview and closeup, at 640 x 480 (poses under Scene). The service serves no object pose, contact or clip
angle: measure the guard, the fan and the clips through the cameras and depth.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and
start targets.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are world positions of the hand mount (metres) and
`wrist_rx, wrist_ry, wrist_rz` serial XYZ joint angles (radians, not a quaternion).

### Scene
World frame, metres and radians, z up.

- Worktop: top at z = 0.65, spanning x in [0.28, 1.08], y in [-0.50, 0.50].
- Fan (free body on four rubber feet, 2.15 kg with its clips): body frame starts at (0.73, 0.18, 0.952) with the cage
  axis along world -x. The rear rim (radius 0.1845, wire radius 0.0018) lies in the plane x = 0.73.
- Clip hinges (fixed to the fan; hinge axis tangential to the rim; angle 0 closed over both rims, 1.40 open, the elastic
  detent's over-centre point at 0.70): 45 deg (0.734, 0.3128, 1.0848), 135 deg (0.734, 0.0472, 1.0848), 225 deg (0.734,
  0.0472, 0.8192), 315 deg (0.734, 0.3128, 0.8192). All four clips start open at 1.40. A closed lower clip (225 or 315
  deg) forms an open-topped U channel that can carry the guard's rim.
- Front guard (rigid, 0.185 kg): rim radius 0.1845 (wire radius 0.0018), dish 0.047 deep toward the operator, a hub cap
  of radius 0.043 and height 0.022 at its centre (front face 0.057 in front of the rim plane), centre of mass 0.018 in
  front of the rim plane on the axis. It starts flat on the worktop, dome up, rim centre at (0.48, -0.275, 0.6518).
- Seat: the guard is seated with its centre at (0.72635, 0.18, 0.952), i.e. 3.65 mm in front of the rear-rim plane, axis
  along world -x.
- Wrist stage: targets are world positions x in [-0.2, 1.0], y in [-0.6, 0.6], z in [0.35, 1.55] and serial XYZ angles
  in [-3.14, 3.14]; it starts at (0.40, 0.00, 0.95, 3.0, 0, 0) (palm down, fingers along +x).
- Cameras (640 x 480): `overview` at (-0.06, -0.84, 1.40) looking at (0.60, -0.07, 0.84), fovy 45; `closeup` at (0.20,
  -0.27, 1.22) looking at (0.72, 0.17, 1.00), fovy 55.

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

## Others
- The upper clips can only lock over a seated guard. The clips are rigid U channels on passive hinges held by an elastic
  over-centre spring (a snap detent); the guard is a rigid wire cage.

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
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
