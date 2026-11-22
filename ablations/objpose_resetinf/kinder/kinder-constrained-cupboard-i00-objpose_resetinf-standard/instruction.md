# KinDER · constrained-cupboard (standard)

## Task
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). Put the six brown rods lying on the floor (30 cm long) into the row of eleven narrow cupboards
standing side by side ahead of the robot, one rod each, each into a cupboard's 40 cm-tall compartment: taking the rods
in order of their distance from where the centre of the robot's base starts, nearest first, they go into the 11th, 5th,
2nd, 8th, 4th and 1st cupboard of the row, counted from the robot's left as it faces the row at the start.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: every rod lies inside the tall compartment of the cupboard it is owed, one rod per cupboard. The episode ends
as soon as the task is done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.1`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action's layout and bounds, `control_dt` (0.1 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last command and watch for `seconds` (at most 30) |
| `r.submit("delta", A, cameras=None, video="mp4", include_depth=False)` | `POST /submit` | runs `A`, one row of 11 values per control step, at most 100 rows a call; stops early when the episode ends |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("delta", A)       # A: (T, 11), one 10 Hz control step per row
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.depth`
(metres), `res.proprio` (one row per frame). One call returns at most 3000 images. Values outside the bounds are clipped
and reported in `meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Once the
episode has ended, `submit` raises `EpisodeOver`. Time per call, on a lightly loaded host: about 14.2 ms per control
step in one-row calls asking for one camera, 19.4 ms with both cameras' images (and the wrist's depth), 10.0 ms per step
in chunks of 10 rows asking for one camera (`video="none"` each time).

### Actions
One action type, `delta`: 11 numbers per row, one 10 Hz control step, in the order of
`spec()["action_types"]["delta"]["layout"]`; at most 100 rows a call:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`:
  how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums
  are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).

### Observations
- Cameras: `robot_base` on the base and `robot_wrist` on the arm's last link (which also gives depth), RGB 480 × 640,
  each with its calibration.
- The proprioception (`obs.meta["proprio"]`) has, in `spec()["proprio_layout"]` order: `base_x`, `base_y`, `base_yaw`
  (the odometry frame: where the base started, x the way it faced, y left, z up), `base_vx`, `base_vy`, `base_yaw_rate`,
  `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the fingers' position: 0 open, 1 at their joint's closed
  limit, about 0.98 when they close on nothing) and `gripper_vel`; `spec()["proprio"]` gives the units.
- The robot's own facts, as its documentation would give them, are in `r.spec()`: each arm joint's axis, position and
  limits, the gripper's grasp point, each camera's field of view and pose; nothing about where anything else is.
- When the episode has ended, `meta["reason"]` says why: `"success"`, `"failed"` when its control steps ran out, or
  `"error"` after a simulator error.

### Time
Time moves only inside calls: running your actions and holding the last command while you watch (`get_obs(seconds=s)`,
at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while you think; an observation
without seconds is free.

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

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: the episode ends after 1000 control steps (100 s of robot time); the task has to be done by then.
