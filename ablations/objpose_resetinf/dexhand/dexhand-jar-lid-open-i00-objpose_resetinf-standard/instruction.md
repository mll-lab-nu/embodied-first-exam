# DexHand · Open a jam jar and set the lid aside (standard)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a worktop (DexHand, MuJoCo). Open the jam jar with the right hand and set its lid aside on the
worktop: a filled glass jam jar stands upright on the worktop with its red twist-off steel lid closed.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the lid is unscrewed (turned counter-clockwise, seen from above, until its lugs clear the
thread) while it still sits on the jar; it is lifted clear of the jar; then it stands upright on the worktop away from
the jar, the hand off the lid and the jar, the jar upright on the worktop, and both are still for a second. A partial
sequence never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the jar tips, slides or is lifted; the lid touches the worktop before it has
been lifted clear; the lid is dropped from the air (there is no time to catch it; a lid that tips over or falls flat on
the worktop has not dropped); the jar or the lid touches the floor, falls below the worktop top or leaves the worktop or
the work area; the lid is forced up through the thread; the parked left arm or the left hand touches the jar or the lid;
or the physics becomes unstable. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all position targets in radians: the 14
Marvin arm joints (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values; then the
right arm `..._R_J1` ... `..._R_J7`), then the left hand's and the right hand's finger joints. `D` is 58 for `sharpa`
(22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s.
Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no
scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. The service serves no jar or lid pose, contact, lid turn or stage; it reports only
whether the episode has ended and whether in success or failure. Quaternions in measured poses use WXYZ; world z is up,
+x points forward from the robot, the jar stands at (-0.22, -0.08) and the worktop top is at z = 0.75 m. Cameras are
overview, closeup, side and wide, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist (the robot stands behind the worktop, its base centre at x = -0.56, y = 0.08 on the floor, facing +x;
shoulders at z = 1.121 m (1.221 m above the floor)). The left arm stays parked beside the torso with its hand open; the
task is done by the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine
under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a
held target sags under the arm's weight unless your targets account for it). Turning, lifting, carrying and releasing
the lid require physical contact, and the jar is held by nothing but its own weight and friction on the worktop. The
controller runs at 50 Hz, with ten 2 ms physics substeps. At reset the right hand hangs open, palm down, about 0.1 m
above the lid with its fingers along +x; the left arm is at its parked pose.

### Scene
The worktop top is at z = 0.75 and spans |x| <= 0.45, |y| <= 0.58 (world frame, metres, z up, +x forward from the
robot). The filled 297 ml glass jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.86) stands upright centred at
x = -0.22, y = -0.08; its red 64.8 mm twist-off steel lid weighs 32 g. Jar and lid are free rigid bodies.

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
- Nothing holds the jar: it stands on its own weight, and its glass-on-worktop friction resists only about 0.13 N m of
  twisting torque, so turn the lid without turning, sliding or tipping the jar. Any robot part touching the jar or the
  lid counts as the hand touching it.
- The closure is a lug thread made of contact geometry: four inclined ramps on the jar neck hold four lugs inside the
  lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive about +z,
  relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the
  gaps between the ramps (a turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without
  lifting, the lugs run into the next ramps, and turning clockwise from closed tightens and jams. The lid is lightly
  closed: no vacuum, seal adhesion or tightening torque.

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
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
