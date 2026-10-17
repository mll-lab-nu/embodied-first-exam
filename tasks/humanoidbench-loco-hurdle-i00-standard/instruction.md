# hurdle — instance 00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task:** run the robot
forward down the walled track, past the hurdles, without touching the side or back walls and without falling.

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds, when
  the robot falls (its pelvis drops near the ground), after 1000 control steps (20 s of robot time), when your
  time is up, or on a simulator error. Nothing else ends it: a robot that has fallen without meeting one of
  these (lying on its side, sitting, face down) goes on until step 1000, so an episode that is still running
  does not mean the robot is still up. You have **50 resets** (`spec()["budget"]["reset"]`, which is
  authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot
  and the scene back on the same frozen starting state and starts a new episode with its own 1000 control
  steps, either abandoning the running episode or after one has ended; it takes no robot time and returns the
  start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` (its message
  gives `resets_left`) until you reset. **Only the last episode is graded**: an episode you reset away is
  never graded, a success ends the run at once (no reset after it), and when your time is up the episode then
  running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
  `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last
  ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while
  you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is on the track, not where the hurdles and walls are, not the reward: the service judges the episode
  and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a
  simulator error, else `"failed"`). `spec()` gives the robot's own facts, as its URDF would: each actuator's
  range, each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the
  IMU's frame, each camera's field of view and pose.
- There is nothing to hand in: the service records every episode and grades the last one as it ran. Keep the
  script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session
  earlier ends the run the same way, so do not stop early: while the episode runs, or a reset is left, the run
  can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**700**: a total of rewards, not a number of steps (an episode is at most 1000 steps). Forward speed, staying
upright (head at standing height, torso vertical) and low actuator force, multiplied together — but the speed
target is a sprint rather than a walk, on the order of 5 m/s. On top of that, touching any barrier's collision
geometry multiplies that entire step down to a small fraction of its value: contact is a gate to be respected,
not a penalty to be traded off. Only the walls that line the track on both sides and behind the start count as
barriers here; the hurdles carry no such penalty. They are solid all the same: each hurdle is one collision
box 37.5 cm high across the whole track (the bars drawn on it have no collision geometry of their own), so the
robot has to get over it. The service ends the episode the moment the pass mark is reached
(`reason = "success"`); that live episode is the verdict.

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
Measured cost here: about 4.4 ms per control step in one-row calls asking for one head camera,
5.3 ms with both head cameras' images, 1.0 ms per step in chunks of 10 rows asking for one camera
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

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
