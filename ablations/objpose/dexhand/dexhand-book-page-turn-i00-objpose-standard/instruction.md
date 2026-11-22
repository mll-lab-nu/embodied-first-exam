# DexHand · Turn one page of a board book (standard)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms may be used), at a desk
(DexHand, MuJoCo). Turn one page of the board book lying open on the desk in front of the robot: it shows pages 4 (left)
and 5 (right). Turn the next right-hand board, leaf 2 (printed pages 5 and 6), over the spine onto the left stack so
that the book shows pages 6 and 7, and take the robot off the book. Every board starts flat on its stack, so the robot
has to separate the top board from the board under it itself.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the turned board lies flat on the left-hand stack, so that the book shows pages 6 and 7, every other board and
both covers lie as they started, no part of the robot touches the book, and the board stays still for a second. A partly
turned page never counts. The episode ends as soon as the task is done.

The episode ends at once as a failure if the book is shoved, lifted or turned on the desk, a second page turns, a cover
moves far (the book closing), a part of the book drops below the desk top, or the physics becomes unstable. Later
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
Forward kinematics uses only the robot's own links (both wrists); no IK primitive is supplied. If the service connection
fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled
episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order
(the row layouts below), radians. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10
s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. Actuator targets
are clipped to the published joint limits and clipping is reported. Row layout, `sharpa` (58): 0-6 left arm
`SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
(actuators `<joint>_target`); 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave
fingers
`left_thumb_CMC_FE, left_thumb_CMC_AA, left_thumb_MCP_FE, left_thumb_MCP_AA, left_thumb_IP, left_index_MCP_FE, left_index_MCP_AA, left_index_PIP, left_index_DIP`,
the same four for middle and ring, then
`left_pinky_CMC, left_pinky_MCP_FE, left_pinky_MCP_AA, left_pinky_PIP, left_pinky_DIP`; 36-57 the right Sharpa Wave
fingers in the same order (`right_...`). Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji fingers
`l_wuji_l_THJ0..THJ3` (thumb), `l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle), `l_wuji_l_RFJ0..RFJ3`
(ring), `l_wuji_l_LFJ0..LFJ3` (little); 34-53 the right Wuji fingers in the same order (`r_wuji_r_...`).

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the desk top is at z = 0.78 m.
Cameras are overview, closeup, front and top, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand (at the world origin, facing +x; shoulders at (0, +-0.2215, 1.121)) with two
7-joint arms and a dexterous hand on each wrist; both arms and both hands may be used. Every arm and finger joint is a
position servo in the physics engine under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad,
the arms' own torque limits and no gravity compensation, so a held target sags slightly under the arm's weight unless
your targets account for it). Lifting, carrying and laying the page down require physical contact. The controller runs
at 50 Hz, with ten 2 ms physics substeps. The book is not attached to anything: it rests on the desk under gravity and
friction, and a push on its pages moves it unless something holds it.

The robot stands at the world origin facing +x; at the start the left arm is parked and the right hand is palm up beside
the book; both arms may be used.

The frozen start row of each hand variant (arm targets and finger targets) is the robot's `joint_target` proprioception
right after a reset.

### Scene
World frame: z up, metres and radians, +x forward from the robot stand, +y to the robot's left. The desk top is the
plane z = 0.78 m (desk x in [0.22, 0.82] m, y in [-0.26, 0.26] m). The board book lies open on the desk as one free body
(`book_spine`, nothing anchors it): its spine runs along the world x axis through y = 0, from x = 0.434 to x = 0.586
(centre x = 0.51). Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm thick laminated board of 16 g; the right-hand
boards extend from the spine toward -y (the robot's right; fore-edge at y = -0.152), the left-hand boards toward +y
(fore-edge at y = +0.152). Boards hinge at the spine about the world x axis (`<board>_binding`, passive friction 0.002 N
m and damping 0.006 N m s/rad) on a small vertical binding compliance (`<board>_binding_compliance`, 200 N/m).
Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left stack, leaf 1 on top), leaf 2 9.0 mm, leaf 3
7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm (right stack, leaf 2 on top), both covers 0.6 mm.
Every board lies flat on its stack, 0.2 mm above the board below it: the top board's fore-edge face (1.2 mm tall, at y =
-0.152, top at z = 0.7884) sits directly above leaf 3's. Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf
hinge angles are measured from the flat right-hand position for right-hand boards (0 = flat right, pi = flat left) and
from the flat left-hand position for left-hand boards (negative = lifted toward the right). At the start the right hand
(frame `wrist_stage` / `right_hand_C_MC`, palm up, index straight) is at about (0.47, -0.44, 0.93) and the left arm
hangs parked beside the stand.

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
- The book is free on the desk: eight rigid laminated boards and two covers on passive binding hinges with friction and
  a little give. A push on its pages moves it unless something holds it.

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
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them without success
  has failed.
