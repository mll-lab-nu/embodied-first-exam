# push — instance 00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task:** push the box on
the table to the target position, marked in the scene by a small red cube.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds,
  when the box reaches the target, after 500 control steps (10 s of robot time), when your time is up, or on a
  simulator error. Nothing else ends it: a robot that has fallen without meeting one of these (lying on its
  side, sitting, face down) goes on until step 500, so an episode that is still running does not mean the
  robot is still up. `spec()["budget"]["reset"]` is 0 in the standard configuration. (A run that grants N
  resets says so there; then `r.reset()` abandons the running episode and starts a new one from the same
  starting state, only the last episode is graded, and a success ends the run.)
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last
  ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while
  you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is in the room, not where the hand or the box is, not the target's coordinates, not the reward: the
  service judges the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`:
  `"success"`, `"error"` after a simulator error, else `"failed"`). `spec()` gives the robot's own facts, as
  its URDF would: each actuator's range, each joint's axis and position, each link's mass and centre of mass,
  the feet's collision boxes, the IMU's frame, each camera's field of view and pose.
- There is nothing to hand in: the service records the episode, replays it and grades the replay. Keep the
  script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run the same way,
  so do not stop early: while the episode runs, it can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**700**: a total of rewards, not a number of steps (an episode is at most 500 steps). Every step here is
*negative*: it costs the box's distance to the target, plus a smaller charge for the left hand's distance to
the box. The only positive term is a one-off bonus, paid when the box lands within a few centimetres of the
target — and that also ends the episode. So the bar is not reached by scoring well for a long time; it is
reached by finishing, and finishing *early*, because every extra step subtracts. The service ends the episode
the moment the pass mark is reached (`reason = "success"`), and a fresh replay of the recorded episode must
reach it as well and end in the same state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (500), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 19 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 19) servo targets in [-1, 1], one row per control step
```
Measured cost here: about 4.0 ms per control step in one-row calls asking for one head camera,
6.1 ms with both head cameras' images, 0.7 ms per step in chunks of 10 rows asking for one camera
(video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order,
the joints' angles (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`,
`imu_gravity_*`).

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["action_types"]["joint_position"]["layout"]`; the proprioception measures the same joints in the same
order). A target of −1 or +1 commands one end of that servo's range,
`spec()["action_types"]["joint_position"]["range_rad"]` in radians, and the scale is linear, so 0 is
mid-range, not 0 rad. A constant action commands joint *targets*, not a pose: whether the robot stays there
depends on whether that pose is stable under gravity and contact.
