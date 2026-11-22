# DexHand · Load two punched pages into a ring binder (standard)

## Task
One dexterous hand on a six-axis wrist stage (no arm), at a desk (DexHand, MuJoCo). Load both punched pages into the
open-front ring binder on the desk: the binder lies free with its back cover towards +x and three split rings on two
toggle plates, closed at the start; two rigid punched pages (139.7 x 215.9 mm, three holes along the binding edge) lie
loose and flat on the desk, printed face up, holes towards the binder (-x).
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the rings are opened; both pages are threaded onto the open rings through all their holes, each
hole on its own ring, and lie on the back cover with the hand off them; the rings are closed through every hole; then
the hand touches neither the pages nor the binder, and both pages rest still on the binder for a second. One page, an
unthreaded hole or open rings never count. The episode ends as soon as the task is done.

The episode ends at once as a failure if a page touches the floor, is dropped or leaves the desk area; if the binder is
pushed away or tipped; if a ring or a finger is pushed through a page (a ring can enter a page only through its hole);
or if the physics becomes unstable. Pages may slide on the desk and hang over its edge. Later actions cannot undo a
failure.

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
`wrist_x, wrist_y, wrist_z` (metres, offsets from the stage base at (0.62, 0.00, 0.70)) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians. `D` is 28 for `sharpa`
(22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger
joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator
targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between
0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts
from the previous target. The robot has no scalar gripper opening.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the desk top is at z = 0.70 m.
Cameras are overview, closeup, rings and pages, at 640 x 480.

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

The wrist targets `wrist_x, wrist_y, wrist_z` are offsets (metres, along the world axes) from the stage base at (0.62,
0.00, 0.70); `wrist_rx, wrist_ry, wrist_rz` are serial XYZ joint angles (radians); at zero wrist rotation the fingers
point down (-z) and the palm faces +x.

### Scene
The binder is free on the desk: back cover (with the ring mechanism near its spine edge) towards +x, spine and front
cover on passive hinges towards -x. Its two toggle plates carry the three ring halves on each side; an over-centre
housing spring (a passive spatial tendon) holds them either closed (0 rad) or open (0.60 rad), and the plates and the
two booster paddles are coupled by the binder's internal linkage (passive joint couplings, never attached to the hand).
Pressing a booster paddle down opens the rings; pushing the plates back past the over-centre point (for example by
pressing the raised inner edges of the open plates down) closes them.

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
- The pages are rigid 0.8 mm cardstock plates that do not bend (the holes are octagonal openings 6.35 mm across flats);
  a hand can drag a page so that its far edge overhangs the desk edge, then pinch it.

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
