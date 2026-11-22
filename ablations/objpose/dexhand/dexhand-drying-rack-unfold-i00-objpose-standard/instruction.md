# DexHand · Unfold a folding sweater dryer and stand it on its legs (standard)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a kitchen counter (DexHand, MuJoCo). Set up the folding
sweater dryer on the counter: it starts fully folded and stored underside up, its four legs folded between the two frame
halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and
stand it on its four feet, then let go.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the rack is open flat with all four legs open, stands upright on its four feet with no other part on the
counter, and the hand has let go of it and it stands still for a second. A partly open rack, a rack on fewer than four
feet or a rack that is still held never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the rack is dropped, pushed off the counter (or lifted far above it), touches
the floor or the counter cabinet, or, once it stands, falls over or collapses; or if the physics becomes unstable. Later
actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
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
`wrist_x, wrist_y, wrist_z` (metres, offsets of the hand mount from the stage origin (0.62, 0, 0.75) m along the world
axes; ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ
joints; rx and rz [-3.3, 3.3], ry [-1.6, 1.6]), then the finger targets in radians. `D` is 28 for `sharpa` (22 Sharpa
Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints
`r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets
are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets; the rack's joint angles and pose are not published, so you judge the rack from the
cameras. Quaternions in measured poses use WXYZ; world z is up, the counter top is at z = 0.75 m and spans x in [-0.13,
1.37] m, y in [-0.48, 0.48] m; the folded rack starts near (0.30, 0.0). Cameras are overview, side and closeup, at 640 x
480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands hang from the same six-axis wrist stage (origin above the counter), with the same wrist
joints, ranges, gains and start targets.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, turning and releasing the rack require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are offsets of the hand mount from the stage origin (0.62, 0, 0.75) m
along the world axes (ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]); `wrist_rx, wrist_ry, wrist_rz` are serial
XYZ joint angles (radians; rx and rz [-3.3, 3.3], ry [-1.6, 1.6]); at zero rotation the hand hangs palm down with the
fingers along +x and the thumb toward +y.

At zero rotation the hand hangs palm down with the fingers along +x and the thumb toward +y.

### Scene
The rack is a folding sweater dryer: two rectangular frame halves (each 0.33 m x 0.65 m, 0.205 kg) joined by a passive
pole hinge on the side rims (0 rad = open flat, pi rad = folded), each half with two offset 0.098 m legs on passive
hinges (0 rad = folded flat, 1.745 rad = 100 degrees = open stop, no latch: the stop lies 10 degrees past vertical, so
the standing rack's weight keeps an open leg open). The woven net is drawn only and has no collision. The rack is a free
body of 0.51 kg and starts fully folded and stored underside up, its legs sandwiched between the halves.

### This run: privileged state queries
This run lets you query the simulator's state.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The kinds are
  `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`, `articulation` (a door,
  a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas region). The list is fixed for
  the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the current
  values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox` [[min x,
    y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the task
  is done.

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
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
