# MuJoCo Playground · BarkourJoystick — STANDARD-REALTIME MODE (robot as a service; time does not stop)

**Task:** Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.

You control the Google Barkour vB quadruped **as if it were real hardware**, in MuJoCo Playground's `BarkourJoystick` environment
(plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you cannot open, you reach
it only through a client, and like real hardware it does not wait for you: once an episode is running, the robot moves
while you think.

**Slowdown: S = 1.** The world runs at 1/S of real speed: one control step (10 ms of robot time) every
S x 10 ms of wall-clock time (real time). `spec()["timing"]["slowdown"]` states it.

## The episode
The robot starts standing still at Playground's `home` pose (this environment's reset does not move it). The ground is flat. One control step is 10 ms of simulated time: Playground's Barkour environment keeps Menagerie's 2 ms timestep and takes 5 substeps.
For 10 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after 501 control steps). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +0.459 | +0.221 | +0.016 |
| 5.01 | +0.090 | -0.389 | +0.643 |

The torso is pushed 12 times at moments you are not told (Playground's kicks: half-sine pushes of up to 35 N lasting 0.05 s, in random horizontal directions).

The same schedule is `spec["command_schedule"]`; the proprioception's `cmd_vx`, `cmd_vy`, `cmd_wz` are the command in force.

## Rules (real-robot rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, the joints holding their starting
  targets. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs at
  100 Hz of robot time, whether or not you send anything, until the episode ends. Between your commands it
  executes what you planned, then holds the last joint targets you sent; nothing pauses for you, not your thinking, not
  your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds,
  and a walking robot that is not balanced step by step falls within a second. Drive it with a program: a controller of your own
  (Python in your container, with numpy and the client) that runs a loop at the control rate, reads the proprioception
  and sends targets, started in the background (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) so
  that your session is free while it runs. Use your turns to start episodes, read what happened, and improve the
  program.
- **The episode ends** after 1000 control steps, the whole schedule (`spec["max_control_steps"]`, counted by `meta["control_steps"]`), when the robot meets its termination rule (the trunk's up axis pointing below the horizon, a joint outside its box (abduction [-0.7, 0.52], hip [-1.0, 2.1], knee [0.05, 2.1] rad) or the torso lower than 0.18 m: a failure), or when your time is up (before the end of the schedule, a failure).
- **Success** is judged on the whole schedule: no termination, and in every command segment, after its first 25 control steps, a mean |v_xy - cmd_xy| of at most 0.2 m/s (`linvel_*`) and a mean |w_z - cmd_wz| of at most 0.3 rad/s (`gyro_*`).
- **Resets.** You have **10 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there
  is no reset and the one episode is the run). `r.reset()` puts the robot back on the same frozen starting state and
  starts a new episode, paused until your next `submit`, either abandoning the running episode or after one has ended.
  Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the
  last episode is graded**: an episode you reset away is never graded, a success ends the run at once (no reset after
  it), and when your time is up the episode then running is the one graded. The wall clock is the run's and never
  restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **No privileged state, no score.** You see the cameras that follow the robot (RGB, depth if you ask) and the robot's
  own sensors: joint positions, velocities and torques, the IMU (gyro, accelerometer, gravity's direction, the trunk's
  velocity), foot contacts, and the joystick command in force. No world positions, no success check: the service judges
  the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after
  a simulator error, else `"failed"`).
- There is nothing to hand in: the service records every control step it ran, replays the last episode in a fresh
  simulator and grades the replay. Keep the controller that drives the robot at `/app/output/gen.py` for the record:
  save it early and keep it current.
- Do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last targets are held. `res.meta["control_steps"]` is
  the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]` the
  proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Closed loop: send one row per control step, `r.submit("joint_position", a[None], cameras=[])`, and compute the next
  one from the proprioception it returns. `cameras=[]` skips the images (the fastest call); sending faster than
  100 Hz only replaces the same step's target again.
- Open loop: send up to 10 s of rows at once (a chunk, `dt` a multiple of 0.01 s), with `at` = the step where it should
  take over; `at` may be up to `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the robot keeps executing its plan). `r.status()` shows `running` and `lag_s`.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the joints' order and limits, `control_dt` (0.01 s), `max_control_steps`, `timing`, the cameras, `proprio_layout`, `budget`, `robot_spec` (home pose, gains), command_schedule |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 12 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most 10 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame, uint8 (240, 320, 3)), `res.frames` or `res.video` (what the cameras saw
during a watch), `res.proprio` (proprioception rows). Values outside the limits are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and changes nothing.
```python
from rcb_client import Robot
import numpy as np
r = Robot()
q = np.array(list(r.spec()["robot_spec"]["home_pose"].values()))   # 12 targets, the `home` pose
while True:                                     # the first submit starts the clock
    res = r.submit("joint_position", q[None], cameras=[])
    if res.done:
        break
    q = ...                                     # from res.meta["proprio"]["now"]
```
Cameras: `track` (follows the robot) and `realsense/rgb` (on its head) (320 x 240), rendered on the service's GPU; `cameras=None` means every camera, so name the ones you
need. Each proprioception row (`spec()["proprio_layout"]`) has the 12 joint positions (action order), their velocities
(`*_vel`) and torques (`*_effort`), the IMU (`gyro_*`, `acc_*`, `gravity_*`, `linvel_*`; IMU frame: x forward, y left, z up),
the foot contacts (`*_contact`: foot_front_left, foot_hind_left, foot_front_right, foot_hind_right) and the joystick command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`).

### `joint_position` (12)
front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee: absolute targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the actuators' own damping of 0.5 N m s/rad). Rows are `dt` apart (a whole multiple
of the 0.01 s control period), `interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s;
values outside the limits (`spec()["action_types"]["joint_position"]["lower"]` / `["upper"]`) are clipped.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
