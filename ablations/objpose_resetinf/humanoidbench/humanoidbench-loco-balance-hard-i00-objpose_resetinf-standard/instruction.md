# HumanoidBench · balance_hard (standard)

## Task
A simulated Unitree H1 humanoid (HumanoidBench, MuJoCo). Stand on the balance board and stay on it, upright and still,
for the whole episode.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the episode's score reaches 800 (an episode has at most 1000 steps). Every control step scores for standing
tall on the board (head at standing height, torso upright), keeping still and using little force, so the robot has to
stay balanced on the board for most of the episode. The episode ends early, with nothing more to score, when the robot
falls, when anything but the roller under the board touches the ground (the board included), or when the roller touches
anything but the ground and the board. The episode ends as soon as the score reaches the mark.

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
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 19 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 50 in all); returns the start's frames |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 19) servo targets in [-1, 1], one row per control step
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.proprio`
(proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never refused; a malformed
request raises `ValueError` and runs nothing. One call returns at most 3000 images. Time per call: about 5.0 ms per
control step in one-row calls asking for one head camera, 7.3 ms with both head cameras' images, 1.1 ms per step in
chunks of 10 rows asking for one camera (video="none" each time).

### Actions
One action type, `joint_position`: one row per control step (`control_dt` = 0.02 s, 50 Hz), rows `dt` apart (a multiple
of 0.02 s), a chunk at most 10 s. Every number is HumanoidBench's normalised servo target in [-1, 1]: -1 and +1 command
the two ends of that servo's range (`spec()["action_types"]["joint_position"]["range_rad"]`, radians), linearly, so 0 is
mid-range, not 0 rad. The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`,
`left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`,
`right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["action_types"]["joint_position"]["layout"]`; the proprioception measures the same joints in the same order). A
constant action commands joint *targets*, not a pose: whether the robot stays there depends on whether that pose is
stable under gravity and contact.

### Observations
- Cameras: the robot's two head cameras (`left_eye_camera`, `right_eye_camera`, RGB, 256 × 256) and `room_camera`, fixed
  in the room.
- The proprioception (`obs.meta["proprio"]`) has, per row, in `spec()["proprio_layout"]` order, the joints' angles
  (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`).
- The robot's own facts, as its URDF would give them, are in `r.spec()`: each actuator's range, each joint's axis and
  position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of
  view and pose.
- When an episode has ended, `meta["reason"]` says why: `"success"`, `"error"` after a simulator error, else `"failed"`.

### Time
Time moves only inside calls: running your servo targets and holding the last ones while you watch
(`get_obs(seconds=s)`, at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while
you think; an observation without seconds is free.

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
- Nothing but the task's own rules ends an episode early: a robot that has fallen without meeting one of them (lying on
  its side, sitting, face down) goes on until step 1000, so an episode that is still running does not mean the robot is
  still up.

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
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 1000 control steps (20 s of robot time).
