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
anything but the ground and the board. What counts is the score when the episode ends.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 50 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  a robot that has fallen stays down until you reset. Only the last episode is graded: when your time is up the episode
  then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

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
`r.reset()` puts the robot and the scene back on the same starting state and starts a new episode with its own 1000
control steps (either abandoning the running episode or after one has ended) and returns the start's images and
proprioception; it takes no robot time. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives
`resets_left`) until you reset. `meta["episode"]` and `meta["resets_left"]` count the episodes; the wall clock never
restarts.

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
- When an episode has ended, `meta["reason"]` says why: `"error"` after a simulator error, else `"failed"`.

### Time
Time moves only inside calls: running your servo targets and holding the last ones while you watch
(`get_obs(seconds=s)`, at most 30 s) use up the episode's control steps. Between calls the robot waits, frozen, while
you think; an observation without seconds is free.

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
- Resets: at most 50 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 1000 control steps (20 s of robot time).
