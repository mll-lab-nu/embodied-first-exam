# sit_simple — instance 00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task:** sit the robot
down on the chair and keep it seated, upright and still.

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds, when
  the robot falls (its pelvis drops below about half its standing height, not far below its height when
  seated), after 1000 control steps (20 s of robot time), when your time is up, or on a simulator error.
  Nothing else ends it: a robot that has fallen without meeting one of these (lying on its side, sitting, face
  down) goes on until step 1000, so an episode that is still running does not mean the robot is still up. You
  have **50 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset and
  the one episode is the run). `r.reset()` puts the robot and the scene back on the same frozen starting state
  and starts a new episode with its own 1000 control steps, either abandoning the running episode or after one
  has ended; it takes no robot time and returns the start's images and proprioception. Once an episode has
  ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last
  episode is graded**: an episode you reset away is never graded, a success ends the run at once (no reset
  after it), and when your time is up the episode then running is the one graded. The wall clock is the run's
  and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last
  ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while
  you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is in the room, not the chair's pose, not the reward: the service judges the episode and only tells
  you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a simulator error,
  else `"failed"`). `spec()` gives the robot's own facts, as its URDF would: each actuator's range, each
  joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame,
  each camera's field of view and pose.
- There is nothing to hand in: the service records every episode, replays the last one in a fresh simulator
  and grades the replay. Keep the script that drives the robot at `/app/output/gen.py` for the record: save it
  early and keep it current.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run the same way,
  so do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**750**: a total of rewards, not a number of steps (an episode is at most 1000 steps). A product: the average
of two seat terms — how close the pelvis is to the height it has when seated, and whether the robot is over
the seat rather than beside it — multiplied by staying upright, a seated posture (the head's height above the
torso), not moving, and low actuator force. Every step spent not yet sitting forfeits the reward that step
could have paid, so both *how fast* and *how steadily* the robot sits matter. The service ends the episode the
moment the pass mark is reached (`reason = "success"`), and a fresh replay of the recorded episode must reach
it as well and end in the same state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 19 targets `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 50 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 19) servo targets in [-1, 1], one row per control step
```
Measured cost here: about 5.2 ms per control step in one-row calls asking for one head camera,
7.5 ms with both head cameras' images, 0.9 ms per step in chunks of 10 rows asking for one camera
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
