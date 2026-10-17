# MuJoCo Playground · {{env}} — STANDARD-REALTIME MODE (robot as a service; time does not stop)

**Task:** {{task}}

You control the {{robot_name}} quadruped **as if it were real hardware**, in MuJoCo Playground's `{{env}}` environment
(plain MuJoCo 3.3.7 with Playground's scene, commit 4057c14). The simulator runs in a service you cannot open, you reach
it only through a client, and like real hardware it does not wait for you: once an episode is running, the robot moves
while you think.

**Slowdown: S = {{slowdown}}.** The world runs at 1/S of real speed: one control step ({{dt_ms}} ms of robot time) every
S x {{dt_ms}} ms of wall-clock time{{real_time_note}}. `spec()["timing"]["slowdown"]` states it.

{{episode_md_rt}}

## Rules (real-robot rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, the joints holding their starting
  targets. Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs at
  {{control_hz}} Hz of robot time, whether or not you send anything, until the episode ends. Between your commands it
  executes what you planned, then holds the last joint targets you sent; nothing pauses for you, not your thinking, not
  your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds,
  and a walking robot that is not balanced step by step falls within a second. Drive it with a program: a controller of your own
  (Python in your container, with numpy and the client) that runs a loop at the control rate, reads the proprioception
  and sends targets, started in the background (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) so
  that your session is free while it runs. Use your turns to start episodes, read what happened, and improve the
  program.
- **The episode ends** {{rt_end}}
- **Success** {{std_success}}
- **Resets.** You have **{{rt_resets}} resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there
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
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it ran.
  Keep the controller that drives the robot at `/app/output/gen.py` for the record:
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
  {{control_hz}} Hz only replaces the same step's target again.
- Open loop: send up to 10 s of rows at once (a chunk, `dt` a multiple of {{dt}} s), with `at` = the step where it should
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
| `r.spec()` | `GET /spec` | the robot's facts: the joints' order and limits, `control_dt` ({{dt}} s), `max_control_steps`, `timing`, the cameras, `proprio_layout`, `budget`, `robot_spec` (home pose, gains){{spec_cmd}} |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt={{dt}}, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of 12 targets `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most {{rt_resets}} in all); returns the start's frames |

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
Cameras: {{cameras}} (320 x 240), rendered on the service's GPU; `cameras=None` means every camera, so name the ones you
need. Each proprioception row (`spec()["proprio_layout"]`) has the 12 joint positions (action order), their velocities
(`*_vel`) and torques (`*_effort`), the IMU (`gyro_*`, `acc_*`, `gravity_*`, `linvel_*`; IMU frame: x forward, y left, z up),
the foot contacts (`*_contact`: {{feet}}) and the joystick command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`).

### `joint_position` (12)
{{joint_text}}: absolute targets of the joint position actuators (rad; {{gains}}). Rows are `dt` apart (a whole multiple
of the {{dt}} s control period), `interpolate="linear"` (default) or `"hold"` between rows; a chunk covers at most 10 s;
values outside the limits (`spec()["action_types"]["joint_position"]["lower"]` / `["upper"]`) are clipped.
