# room — instance 00 — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo) **as if
it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. Like real hardware, it does not wait for you: once an episode is running, the robot moves in real time
while you think. **Task:** six loose objects — a chair, a trophy, a pair of headphones, two packages and a
snow globe — are scattered around the room (the table and the bookshelf are fixed). Tidy up: gather them
together, so they end up close to one another rather than spread out.

## Rules (real-robot rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, its servos holding their
  starting targets. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the
  robot runs at 50 Hz in real time, one control step every 0.02 s of wall-clock time, whether or not you send
  anything, until the episode ends. Between your commands it executes what you planned, then holds the last
  servo targets you sent; nothing pauses for you, not your thinking, not your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes
  seconds, and the robot falls within a few seconds of robot time without active balance. Drive it with a
  program: a controller of your own (Python in your container, with numpy and the client) that runs a loop at
  the control rate, reads the proprioception and sends targets, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) so that your session is free while it runs.
  Use your turns to start episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends when the task succeeds, when the robot falls (its pelvis drops near
  the ground), after 1000 control steps (20 s after its clock started), when your time is up, or on a
  simulator error. Nothing else ends it: a robot that has fallen without meeting one of these (lying on its
  side, sitting, face down) goes on until step 1000, so an episode that is still running does not mean the
  robot is still up. You have **50 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says
  0, there is no reset and the one episode is the run). `r.reset()` puts the robot and the scene back on the
  same frozen starting state and starts a new episode, paused until your next `submit`, with its own 1000
  control steps, either abandoning the running episode or after one has ended. Once an episode has ended,
  `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last episode is
  graded**: an episode you reset away is never graded, a success ends the run at once (no reset after it), and
  when your time is up the episode then running is the one graded. The wall clock is the run's and never
  restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256), its own
  joint angles and joint velocities, a pelvis IMU and `room_camera`, a camera fixed in the room. Not where the
  robot is in the room, not where the objects are, not the reward: the service judges the episode and only
  tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a simulator
  error, else `"failed"`). `spec()` gives the robot's own facts, as its URDF would: each actuator's range,
  each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the IMU's
  frame, each camera's field of view and pose.
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it
  ran. Keep the controller that drives the robot at `/app/output/gen.py` for the record: save it early and
  keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session
  earlier ends the run the same way (and stops your background programs), so do not stop early: while the
  episode runs, or a reset is left, the run can still pass.

## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the
  plan from control step `at` (an episode step number; by default the next step), replacing whatever was
  planned from `at` on and keeping what is planned before it. When the plan runs out, the last target is held.
  `res.meta["control_steps"]` is the number of steps run so far in this episode (so the next step has that
  number), `res.meta["proprio"]["now"]` the robot's proprioception now, `res.meta["plan_end_step"]` where the
  plan now ends.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, and compute
  the next one from the proprioception it returns. `cameras=[]` skips the images (the fastest call); sending
  faster than 50 Hz only replaces the same step's target again.
- Open loop: send up to 10 s of rows at once (a chunk, `dt` a multiple of 0.02) and the next chunk before the
  plan runs out, with `at` = the step where it should take over; `at` may be up to
  `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control
  step at the earliest. A row whose step has already run when the request arrives is dropped
  (`res.meta["late_steps"]` counts them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run
  and returns what the cameras saw meanwhile (the robot keeps executing its plan). `spec()["timing"]` states
  all this; `r.status()` shows `running` and `lag_s`.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**400**: a total of rewards, not a number of steps (an episode is at most 1000 steps). Unusually, this task
gives you no target positions at all. The dominant term measures how *spread out* the six objects are — the
variance of their horizontal coordinates — and rewards making that small; a smaller term pays for standing
steadily. Any arrangement that brings the objects close together scores, wherever in the room you do it. The
service ends the episode the moment the pass mark is reached (`reason = "success"`); that live episode is the
verdict.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the robot. Its docstring is the full reference
(`python -c "import rcb_client; help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the actuators' order and ranges, `control_dt` (0.02 s), `max_control_steps` (1000), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.02, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 61 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 50 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.proprio` (proprioception rows). Values outside [-1, 1] are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and changes nothing.
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
Measured cost here in standard mode: about 5.4 ms per one-row call asking for one head camera, physics
included; a call with `cameras=[]` skips the rendering. A control step is 20 ms.

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

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
