# DexHand · Put a folded letter into an envelope (standard)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a desk (DexHand, MuJoCo). Put the folded letter into the envelope: a tri-folded A4 letter lies flat on
the desk at (0.48, -0.14) m, and an empty DL wallet envelope (110 x 220 mm) lies flat at (0.48, 0.16) m with its open
mouth along its +X long edge and the open flap on the desk beyond the mouth. Move the letter to the mouth, feed it in
through the mouth, then let go.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the letter is inside the envelope, all but a sliver of it past the mouth and between the side seams, and the
hand has let go of the letter and the envelope, which lie still for a second. The episode ends as soon as the task is
done.

The episode ends at once as a failure if the letter or the envelope falls below the desk top, touches the floor, is
dropped or leaves the desk; if the letter is pressed through a wall, a seam or the mouth lip of the envelope; if the
envelope is pushed away or tilted; if the robot's arm, stand or parked left hand touches the letter or the envelope; or
if the physics becomes unstable. Later actions cannot undo a failure.

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
Forward kinematics uses only the robot's own links (the robot base is at (1.15, -0.25, 0.10) m, facing -x); no IK
primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (radians): the 7 left-arm joint targets
`SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target`, then the left-hand and the right-hand finger targets. `D` is 58
for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0` ... `r_wuji_r_LFJ3`). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
the hand root pose (`right_hand_C_MC`) and current targets. Quaternions in measured poses use WXYZ; world z is up and
the desk top is at z = 0.70 m. Cameras are overview, closeup and mouth (a low view of the envelope mouth), at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its
base plate stands on the floor at z = 0); the left arm is parked beside the torso and only the right arm and hand do the
task. Arm joints and fingers are position servos in the physics engine under native force bounds; pressing, sliding,
pushing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

Keep the left arm at its start targets; only the right arm and hand do the task.

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
- The envelope is a rigid pocket: back and front walls 4 mm apart, permanent side seams (narrowing to nothing over the
  last 10 mm before the mouth), a bottom seam, and a 30 mm elastic mouth lip that starts closed (flush with the front
  wall); a fingertip or the letter can lift it. The flap is a thin wedge on the desk and is never sealed.
- The letter is one stiff 99 x 210 x 2 mm card (5 g) with rounded fold edges: paper bending is not simulated. Both
  objects are free and move only through contact.

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
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them without success
  has failed.
