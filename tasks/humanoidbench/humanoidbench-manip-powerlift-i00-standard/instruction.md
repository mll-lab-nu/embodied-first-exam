# HumanoidBench · powerlift (standard)

## Task
Lift the dumbbell off the floor to overhead and hold it there.

## Goal
Success: the dumbbell is held up overhead for most of the episode, with the robot standing steadily. Success counts as
it happens: every moment the robot does this well adds to its score over the episode (its full length is in Limits).
Once you have done this well for long enough, the task is passed, even if you fall afterwards.

When you are done, send `/finish` to end the episode and get it graded.

The episode ends at once as a failure if the robot falls (its pelvis drops close to the floor).

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 50 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  a robot that has fallen stays down until you reset. Only the last episode is graded.
- You get only the robot's camera images (its two head cameras and `room_camera`, fixed in the room) and its own joint
  angles, joint velocities and pelvis IMU: not where the robot is in the room, not the dumbbell's pose; no object poses,
  no scene layout, no score, no success signal.

## Robot Interface
A simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench, MuJoCo). The robot runs as a service you
reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/3.0`); its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`). The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, last_s=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or with `last_s=n` the frames recorded over the last n seconds; no time passes |
| `r.hold(seconds, cameras=None, video="mp4")` | `POST /submit` | hold the last targets for `seconds` of robot time and return the video, like a submit |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 61 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 50 in all); returns the start's frames |

```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 61) servo targets in [-1, 1], one row per control step
```
The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.proprio`
(proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never refused; a malformed
request raises `ValueError` and runs nothing. One call returns at most 3000 images. Time per call: about 6.7 ms per
control step in one-row calls asking for one head camera, 8.7 ms with both head cameras' images, 1.8 ms per step in
chunks of 10 rows asking for one camera (video="none" each time). `r.reset()` puts the robot and the scene back on the
same starting state and starts a new episode with its own 1000 control steps. You can call it during a running episode,
which it abandons, or after one has ended. It returns the start's images and proprioception; it takes no robot time.
Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset.
`meta["episode"]` and `meta["resets_left"]` count the episodes; the wall clock never restarts.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`,
  `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
One action type, `joint_position`, with one row per control step (`control_dt` = 0.02 s, 50 Hz). Rows are `dt` apart (a
multiple of 0.02 s), and a chunk covers at most 10 s. Every number is HumanoidBench's normalised servo target in [-1,
1]. The mapping is linear: -1 and +1 command the two ends of that servo's range
(`spec()["action_types"]["joint_position"]["range_rad"]`, radians), so 0 is mid-range, not 0 rad. The 61 actuators are
position servos. The first 21 are the body, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`, `torso`,
`left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40
are the two Shadow hands, 20 each: `lh_A_*`, then `rh_A_*`. In each hand the first 2 are the wrist (`*_A_WRJ2`,
`*_A_WRJ1`) and the other 18 are the fingers. Each of the 4 `*J0` actuators (`*_A_FFJ0`, `*_A_MFJ0`, `*_A_RFJ0`,
`*_A_LFJ0`) drives a tendon that moves two finger joints together
(`spec()["action_types"]["joint_position"]["layout"]`). A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.

### Observations
- Cameras: the robot's two head cameras (`left_eye_camera`, `right_eye_camera`, RGB, 256 × 256) and `room_camera`, fixed
  in the room.
- Each row of the proprioception (`obs.meta["proprio"]`) holds, in `spec()["proprio_layout"]` order, the joints' angles
  (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`). The proprioception
  measures joints, not actuators: 69 of them, in `spec()["proprio"]["joints"]` order.
- The robot's own facts, as its URDF would give them, are in `r.spec()`: each actuator's range, each joint's axis and
  position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of
  view and pose.
- When an episode has ended, `meta["reason"]` says why: `"finished"` after your finish, `"step_limit"` at the end of its
  control steps, `"error"` after a simulator error, else `"failed"`.

### Time
Time moves only inside calls: running your servo targets and holding the last ones (`hold(s)`) use up the episode's
control steps. Between calls the robot waits, frozen, while you think; an observation is free.

## Others
- A fall that leaves the pelvis above that height (kneeling, or slumped against something) does not end the episode. It
  goes on, so an episode that is still running does not mean the robot is still up.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 50 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 1,000 control steps (20 s of robot time), then the episode ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
