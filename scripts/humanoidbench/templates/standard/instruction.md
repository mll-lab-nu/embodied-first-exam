# {{family}} — instance {{instance_tag}} — STANDARD MODE (robot as a service)

You control a simulated {{robot_label}} (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task:** {{standard_task_statement}}

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up. It ends when the task succeeds{{standard_ends}}, after {{max_steps}} control steps ({{robot_seconds}} s of robot time), when your time is up, or on a simulator error. Nothing else ends it: a robot that has fallen without meeting one of these (lying on its side, sitting, face down) goes on until step {{max_steps}}, so an episode that is still running does not mean the robot is still up. You have **{{reset_budget}} resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot and the scene back on the same frozen starting state and starts a new episode with its own {{max_steps}} control steps, either abandoning the running episode or after one has ended; it takes no robot time and returns the start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last episode is graded**: an episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your servo targets and `get_obs(seconds=s)` holds the last ones for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, {{image_hw}}), its own joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not {{standard_hidden}}, not the reward: the service judges the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a simulator error, else `"failed"`). `spec()` gives the robot's own facts, as its URDF would: each actuator's range, each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of view and pose.
- There is nothing to hand in: the service records every episode and grades the last one as it ran. Keep the script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**{{success_bar}}**: a total of rewards, not a number of steps (an episode is at most {{max_steps}} steps).
{{standard_scoring_note}} The service ends the episode the moment the pass mark is reached (`reason = "success"`); that
live episode is the verdict.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` ({{control_dt}} s), `max_control_steps` ({{max_steps}}), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt={{control_dt}}, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of {{nu}} targets `dt` seconds apart (a multiple of {{control_dt}}; a chunk covers at most 10 s); stops early when the episode ends |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most {{reset_budget}} in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt={{control_dt}})   # A: (T, {{nu}}) servo targets in [-1, 1], one row per control step
```
Measured cost here: about {{ms_single}} ms per control step in one-row calls asking for one head camera,
{{ms_images}} ms with both head cameras' images, {{ms_batch}} ms per step in chunks of 10 rows asking for one camera
(video="none" each time).

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order, the joints'
angles (`*_pos`, rad), their velocities (`*_vel`, rad/s), then the IMU (`imu_gyro_*`, `imu_gravity_*`).

{{standard_actuator_layout}}
