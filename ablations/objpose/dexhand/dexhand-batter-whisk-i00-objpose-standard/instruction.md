# DexHand · Whisk batter in a bowl, drain and set the whisk down (standard)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a counter with a steel bowl of
batter (DexHand, MuJoCo). Pick up the balloon whisk, whisk the batter in the bowl, drain the whisk over the bowl and lay
it down on the counter. The whisk starts at rest, leaning on the bowl rim with its handle end on the counter; both hands
start open. The right hand uses the whisk; the left hand may steady the bowl.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the whisk is picked up and held clear of the bowl and the counter; its head goes into the batter
and circles the bowl at least five full times without leaving the batter (leaving it earlier starts the count again); it
hangs head-down over the bowl for half a second to drain; then it is laid down on the counter, roughly flat and away
from the bowl, and the hands have let go and it lies still for a second. Partial completion never counts. The episode
ends as soon as the task is done.

The episode ends at once as a failure if the bowl tips, slides or lifts; if, after the pickup, the whisk is dropped,
touches the counter or loses the hand's contact for more than a moment before it is placed; if it is tossed rather than
laid down once placed; if the bowl or the whisk touches the floor, falls below the counter top or leaves the work area;
or if the physics becomes unstable. Before the pickup the whisk may be nudged or slide off the rim. Later actions cannot
undo a failure.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, radians: columns 0-6 the left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, 7-13 the right arm `..._R_J1` ... `..._R_J7`, then the left hand's and the
right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ...
`left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per
hand, `l_wuji_*` then `r_wuji_*`). Actuator targets are clipped to the published joint limits and clipping is reported.
`dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each
row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.68
m; the bowl starts centred at (0.58, 0.0) m. Cameras are overview, closeup and side, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand on
each wrist. Every arm and finger joint is a position servo in the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags by about 1 cm at the
hand under load unless your targets account for it). The bowl and the whisk move only through contact with the hands,
the arms, each other and the counter. The controller runs at 50 Hz, with ten 2 ms physics substeps. World frame: metres
and radians, +z up, +x forward from the robot stand, +y to the robot's left.

The right arm/hand picks up and uses the whisk; the left arm/hand may steady the bowl.

### Scene
The episode starts with both hands open above the counter and the arms in a ready pose; holding the current targets
keeps it. The whisk rests against the bowl rim with its handle end on the counter; the left hand may steady the bowl.

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
- The batter is not simulated: it exerts no force on the whisk.

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
- Steps: at most 4,000 control steps (80 s of simulated time) per episode; an episode that reaches them without success
  has failed.
