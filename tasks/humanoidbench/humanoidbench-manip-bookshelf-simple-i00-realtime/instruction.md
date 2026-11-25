# HumanoidBench · bookshelf_simple (realtime)

## Task
Put the five red objects on the bookshelf one at a time, palest first and darkest last, each on the see-through copy of
itself.

## Goal
Success: all five red objects are put on their places within the episode, one at a time, palest first, with the robot
standing steadily and a hand at the object it is moving. The episode ends as soon as the task is done.

Any of these ends the episode at once, and nothing after it counts:
- The robot falls.
- The object being moved drops below about knee height.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 50 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  a robot that has fallen stays down until you reset. Only the last episode is graded: a success ends the run at once
  (no reset after it), and when your time is up the episode then running is graded.
- You get only the robot's camera images (its two head cameras and `room_camera`, fixed in the room) and its own joint
  angles, joint velocities and pelvis IMU: not where the robot is in the room, not where the objects or their places
  are; no object poses, no scene layout, no score; the episode ends when the task is done, and the service tells you
  that it ended and why.

## Robot Interface
A simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench, MuJoCo). The robot runs as a service you
reach only through its client, as if it were real hardware, on a clock that does not stop while you think.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.3`, realtime mode); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 61 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 50 in all); returns the start's frames |

```python
from rcb_client import Robot
r = Robot()
a = ...                                         # (61,) servo targets in [-1, 1]
while True:                                     # the first submit starts the clock
    res = r.submit("joint_position", a[None], cameras=[])
    if res.done:
        break
    a = ...                                     # from res.meta["proprio"]["now"]
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch), `res.proprio`
(proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never refused; a malformed
request raises `ValueError` and changes nothing. One call returns at most 3000 images. A watch is refused with a 429
while the images in flight (pending watches and answers not read yet) would exceed it or 8 of them are outstanding; a
`submit` or a `get_obs()` without seconds is never refused for its images: its answer then comes without its frames and
`meta["frames_skipped"]` is set. Time per call (standard mode): about 7.7 ms per one-row call asking for one head
camera, physics included; a call with `cameras=[]` skips the rendering. A control step is 20 ms.
`r.reset()` puts the robot and the scene back on the same starting state and starts a new episode with its own 1000
control steps (either abandoning the running episode or after one has ended) and returns the start's images and
proprioception; the new episode stays paused until your next `submit`. Once an episode has ended, `submit` raises
`EpisodeOver` (its message gives `resets_left`) until you reset. `meta["episode"]` and `meta["resets_left"]` count the
episodes; the wall clock never restarts.

### Actions
One action type, `joint_position`: one row per control step (`control_dt` = 0.02 s, 50 Hz), rows `dt` apart (a multiple
of 0.02 s), a chunk at most 10 s. Every number is HumanoidBench's normalised servo target in [-1, 1]: -1 and +1 command
the two ends of that servo's range (`spec()["action_types"]["joint_position"]["range_rad"]`, radians), linearly, so 0 is
mid-range, not 0 rad. The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`,
`right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`.
The remaining 40 are the two Shadow hands, 20 each — `lh_A_*` then `rh_A_*`; each hand's first 2 are its wrist
(`*_A_WRJ2`, `*_A_WRJ1`) and the other 18 its fingers, where each of the 4 `*J0` ones (`*_A_FFJ0`, `*_A_MFJ0`,
`*_A_RFJ0`, `*_A_LFJ0`) drives a tendon that moves two finger joints together
(`spec()["action_types"]["joint_position"]["layout"]`). A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.

### Observations
- Cameras: the robot's two head cameras (`left_eye_camera`, `right_eye_camera`, RGB, 256 × 256) and `room_camera`, fixed
  in the room.
- The proprioception (`obs.meta["proprio"]`) has, per row, in `spec()["proprio_layout"]` order, the joints' angles
  (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`). The proprioception
  measures joints, not actuators: 69 of them, in `spec()["proprio"]["joints"]` order.
- The robot's own facts, as its URDF would give them, are in `r.spec()`: each actuator's range, each joint's axis and
  position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of
  view and pose.
- When an episode has ended, `meta["reason"]` says why: `"success"`, `"error"` after a simulator error, else `"failed"`.

### Time and streaming
- Time does not stop. An episode starts paused, on the frozen starting state, its servos holding their starting targets.
  Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs at 50 Hz
  in real time, one control step every 0.02 s of wall-clock time, whether or not you send anything, until the episode
  ends. Between your commands it executes what you planned, then holds the last servo targets you sent; nothing pauses
  for you, not your thinking, not your tool calls.
- You are far too slow to steer it turn by turn. One turn of yours (a model response, a tool call) takes seconds, and
  the robot falls within a few seconds of robot time without active balance. Drive it with a program: a controller of
  your own (Python in your container, with numpy and the client) that runs a loop at the control rate, reads the
  proprioception and sends targets, started in the background (`nohup python /app/ctrl.py > /app/ctrl.log 2>&1 &`). Use
  your turns to start episodes, read what happened, and improve the program.
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last target is held. `res.meta["control_steps"]` is the
  number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  robot's proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, and compute the next
  one from the proprioception it returns. `cameras=[]` skips the images (the fastest call); sending faster than 50 Hz
  only replaces the same step's target again.
- Open loop: send up to 10 s of rows at once (a chunk, `dt` a multiple of 0.02) and the next chunk before the plan runs
  out, with `at` = the step where it should take over; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps
  ahead.
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the robot keeps executing its plan). `spec()["timing"]` states all this; `r.status()`
  shows `running` and `lag_s`.

## Others
- A robot that has fallen in a way the Goal does not list (on its side, face down, sitting on the floor) is not stopped:
  the episode goes on, so an episode still running does not mean the robot is still up.
- Ending your session ends the run as the time limit does, and stops your background programs: while an episode runs, or
  a reset is left, the run can still pass.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 50 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 1000 control steps (20 s of robot time).
