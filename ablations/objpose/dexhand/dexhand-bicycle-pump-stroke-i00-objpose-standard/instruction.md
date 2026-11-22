# DexHand · Inflate a tire with a portable bicycle pump (standard)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a bench (DexHand, MuJoCo). Inflate the bicycle tire with the portable bicycle pump: a mini floor pump
(barrel 0.25 m tall) stands free on its folding foot on the bench next to a 20-inch wheel lying on the bench; the pump's
hose head starts disconnected from the wheel's Schrader valve, its thumb lock open (lever pointing up), and the tire is
at 200.0 kPa.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the hose head is pushed onto the valve and its thumb lock closed; with the head connected, the
pump handle goes through at least 28 full strokes (pushed nearly all the way down and let back up nearly to the top;
shallower strokes do not count), which brings the tire to 210.6 kPa; the thumb lock is opened and the head pulled back
off the valve; then the handle rests at the top, the pump stands upright and still, and no part of the robot touches the
pump or the head for a second. The episode ends as soon as the task is done.

The episode ends at once as a failure if the pump tips over, slides or lifts off its spot, falls below the bench top or
touches the floor; if the connected head is pulled back or its lock opened before the tire is pumped up; if the head is
pulled back while its lock is still closed (open the lock first); or if the physics becomes unstable. Later actions
cannot undo a failure.

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
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the bench top is at z = 0.70
m. Cameras are overview, closeup, wide and front, at 640 x 480. Camera RGB and calibrated depth from `overview`
(default) and `closeup` (aimed at the pump), the robot's own joint positions, velocities, actuator efforts, hand pose
and current targets, and robot-link forward kinematics. The service does not report the pump pose, the head or lever
position, the piston depth, the stroke count, the tire pressure or contacts: judge the handle and the pump from the
images and depth. At the end of an episode the meta reports `done`, `success` and a failure category.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds;
arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags under the
arm's weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

### Scene
The pump stands near world (0.42, 0.08) with its T handle about 0.45 m above the bench at rest; the disconnected hose
head sits at the wheel rim near world (0.546, -0.12, 0.747) with its thumb-lock lever pointing up, and seats by sliding
17.5 mm toward the rim along (-0.981, 0, -0.196).

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
- The head sits on the valve stem's axis 17.5 mm out from its seat and moves only along that axis (a passive slide with
  a little friction): pushing it 17.5 mm toward the rim seats it on the stem. The thumb lock is a passive hinge on the
  head that turns from pointing up (open) to lying flat toward the wheel hub (closed).
- The T handle starts at the top of its 0.20 m travel; the piston's air spring pushes it back up (about 6 N at the top,
  46 N at the bottom of the stroke). A stroke counts only while the head is connected and locked; every counted stroke
  raises the tire pressure by the same amount.
- The wheel, valve and hose are fixed props (the hose end moves with the head); the head and its lock move only through
  contact.

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
- Steps: at most 5,000 control steps (100 s of simulated time) per episode; an episode that reaches them without success
  has failed.
