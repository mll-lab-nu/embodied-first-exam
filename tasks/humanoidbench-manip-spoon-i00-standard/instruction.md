# spoon — instance 00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo) **as if
it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** take hold of the spoon, put it in the cup and stir: move its head around a small circle,
continuously, for the rest of the episode.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds,
  when the robot falls (its pelvis drops too low), after 1000 control steps (20 s of robot time), when your
  time is up, or on a simulator error. Nothing else ends it: a robot that has fallen without meeting one of
  these (lying on its side, sitting, face down) goes on until step 1000, so an episode that is still running
  does not mean the robot is still up. `spec()["budget"]["reset"]` is 0 in the standard configuration. (A run
  that grants N resets says so there; then `r.reset()` abandons the running episode and starts a new one from
  the same starting state, only the last episode is graded, and a success ends the run.)
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last
  ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while
  you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is in the room, not the spoon's pose, not the moving target point, not the reward: the service judges
  the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`,
  `"error"` after a simulator error, else `"failed"`). `spec()` gives the robot's own facts, as its URDF
  would: each actuator's range, each joint's axis and position, each link's mass and centre of mass, the
  feet's collision boxes, the IMU's frame, each camera's field of view and pose.
- There is nothing to hand in: the service records the episode, replays it and grades the replay. Keep the
  script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run the same way,
  so do not stop early: while the episode runs, it can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**650**: a total of rewards, not a number of steps (an episode is at most 1000 steps). A weighted sum of four
things: standing steadily, getting a hand to the spoon's handle, keeping the spoon's head inside the cup, and
— the largest single term — keeping that head close to a target point that **travels around a small circle at
a fixed rate, completing a revolution every 40 steps** (centred in the cup just above its floor,
counter-clockwise seen from above, starting on the side away from the robot). The spoon starts on the table
beside the cup, so the last two terms pay nothing until it is in the cup. The service ends the episode the
moment the pass mark is reached (`reason = "success"`), and a fresh replay of the recorded episode must reach
it as well and end in the same state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 61 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 61) servo targets in [-1, 1], one row per control step
```
Measured cost here: about 5.7 ms per control step in one-row calls asking for one head camera,
8.4 ms with both head cameras' images, 1.9 ms per step in chunks of 10 rows asking for one camera
(video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order,
the joints' angles (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`,
`imu_gravity_*`).

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`,
`right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are the two Shadow hands, 20 each —
`lh_A_*` then `rh_A_*`; each hand's first 2 are its wrist (`*_A_WRJ2`, `*_A_WRJ1`) and the other 18 its
fingers, where each of the 4 `*J0` ones (`*_A_FFJ0`, `*_A_MFJ0`, `*_A_RFJ0`, `*_A_LFJ0`) drives a tendon that
moves two finger joints together (`spec()["action_types"]["joint_position"]["layout"]`). The proprioception
measures joints, not actuators: 69 of them, in `spec()["proprio"]["joints"]` order. A target of −1 or +1
commands one end of that servo's range, `spec()["action_types"]["joint_position"]["range_rad"]` in radians,
and the scale is linear, so 0 is mid-range, not 0 rad. A constant action commands joint *targets*, not a pose:
whether the robot stays there depends on whether that pose is stable under gravity and contact.
