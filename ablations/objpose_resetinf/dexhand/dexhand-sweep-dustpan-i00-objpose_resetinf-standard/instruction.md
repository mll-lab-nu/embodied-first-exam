# DexHand · Sweep debris into a held dustpan (standard)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, over a floor (DexHand, MuJoCo).
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan: the robot starts with a broom held
in its right hand and a dustpan held in its left hand; the pan's entrance ramp rests on the floor next to six small
rigid pieces (packaging pieces, bottle caps, a wood chip and a crumpled-paper ball). Push the debris over the ramp with
the broom's bristles, then raise the dustpan.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: every one of the six pieces has been touched by the broom's bristles, all six lie in the pan on its floor, and
the pan is held up off the floor with everything still for a second. Five of six pieces, an unlifted pan or a shorter
hold is not a success. The episode ends as soon as the task is done.

The episode ends at once as a failure if a piece leaves the floor work area; any part of the robot touches a piece
(sweep with the broom only); from 1.2 s on (the first 1.2 s are a settling period), a tool slips in or drops from its
hand; a tool is pressed by any robot part other than its own hand; the arms, torso or the two hands collide with each
other; or the simulation becomes unstable. Later actions cannot undo a failure.

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
spec["hand"], spec["action_types"]["joint_position"]["layout"]
obs = r.get_obs(cameras=["work"], depth=True)
obs.last["work"]               # RGB uint8 (480, 640, 3)
obs.last_depth["work"]         # z-depth in metres
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.0005, interpolate="hold", video="none")
r.fk(q)                        # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
The client sends rows as float32. Requests return at most 1,000 camera images; ask for fewer cameras or a lower
`video_fps` for long chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps;
without seconds it only observes. Forward kinematics covers the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the
same journaled episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `dt` must be a multiple of
`1 / spec["control_hz"]` (0.0005 s), at most 0.5 s; a chunk covers at most `spec["max_chunk_s"]` seconds. `hold` keeps
each row for `dt`; `linear` interpolates from the previous target. Targets are clipped to the published joint limits and
clipping is reported.

Every row holds both arms' joint targets and both hands' finger targets (layout below). Sharpa rows (58 targets): the 7
left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand Sharpa
Wave finger targets (radians). Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20
right-hand Wuji Hand 2.2 finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC
flexion, CMC abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both palm poses (`l_hand_palm`, `r_hand_palm`) and current targets. Object poses, contacts are not published. Cameras
are overview, work (the floor area and the pan), pan and side, 640 x 480, fixed in the world. Measured poses use WXYZ
quaternions; world z is up, metres, the robot base at the origin, the floor the plane z = -0.10 m.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order. This task uses two hands of one model on the two arms of a fixed robot: Sharpa Wave (default) or
Wuji Hand 2.2. With Wuji the start differs only in the finger joints and their targets: both Wuji hands start closed on
the same broom and dustpan (the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa
start), and the targets at the start keep them.

### Robot
The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its handle;
the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force bounds; the
broom, the dustpan and the debris move only through contact and gravity. At the start the current targets keep both
tools in the hands; the first 1.2 s are a settling period in which the grip is not yet judged. The simulator integrates
at 0.5 ms and every action row is one physics step, so rows are a 2000 Hz control. The service simulates slower than
real time (several seconds of CPU per simulated second).

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
- The broom, the dustpan and the debris are free bodies that move only through contact and gravity.

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
- Steps: at most 160,000 rows (one per 0.5 ms physics step) (80 s of simulated time) per episode; an episode that
  reaches them without success has failed.
