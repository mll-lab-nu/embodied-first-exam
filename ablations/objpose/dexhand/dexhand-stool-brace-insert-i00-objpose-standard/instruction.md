# DexHand · Assemble a wooden stool cross brace (standard)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a table (DexHand, MuJoCo). Assemble the cross brace of a pine
stool dry frame: the lower side frame lies flat on the table with its four bores facing up and three rails already
standing seated in three of them; the loose cross brace (a 0.26 m pine rail with an 8 mm dowel exposed 15 mm at each
end) lies on the table, and the opposite side frame lies upside down beside the lower frame. Pick up the brace, seat one
of its dowels in the empty bore of the lower frame, then lift the opposite side frame and lower it onto all four upper
dowels so that both brace dowels end up seated in their legs.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the brace is lifted off the table; one of its dowels is seated in the empty bore of the lower
frame; the opposite side frame is lifted; then each of the eight bores holds one seated dowel, every rail (the brace
included) joining the two side frames; finally the hand is off every part and all of them are still for a second. A
single seated brace dowel or any partial assembly never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the lower frame moves or tilts; a pre-seated rail is pulled partly out of its
bore or tilts; the brace touches the table again or sinks low after it was lifted, or tilts much after its first dowel
is seated; the opposite side frame touches the table after it was lifted, or tilts much from its upside-down carrying
orientation; any part falls freely (a drop); any part touches the floor, falls below the table top or leaves the work
area; or the physics becomes unstable. Later actions cannot undo a failure.

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
`wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin along the world axes) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians. `D` is 28 for `sharpa`
(22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger
joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator
targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between
0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts
from the previous target. The robot has no scalar gripper opening.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the table top is at z = 0.74
m. Cameras are overview, closeup and side, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and
start targets; the wrist x/y/z targets are offsets from the stage origin (stage origin (0.55, -0.1, 1.15) m) along the
world axes, and at zero wrist angles the palm faces down with the fingers along +x.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

At zero wrist angles the palm faces down, the fingers point along +x and the thumb is on the +y side.

### Scene
The lower side frame lies centred at (0.61, 0.0) m with its open bores facing up, the brace lies at (0.57, -0.33) m
along x and the opposite side frame lies upside down at (0.61, 0.5) m.

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

## Others
- All parts are free rigid pine bodies; the bores are hollow contact geometry with 0.1 mm of radial clearance for the
  dowels and no entry chamfer. Glue, screws, the seat and load capacity are not modelled.

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
