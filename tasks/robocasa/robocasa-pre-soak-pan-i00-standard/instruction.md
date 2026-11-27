# RoboCasa · PreSoakPan (standard)

## Task
Put the pan and the sponge in the sink, turn the sink faucet on, nearly all the way, and move your hand away.

## Goal
Success: the pan and the sponge are both all the way in the sink, the water is on with its handle turned nearly all the
way, and your hand has let go of the pan and moved away.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa, robosuite / MuJoCo). The
robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.hold(2.0, cameras=cams[:1])                            # hold still for 2 s of robot time
obs = r.get_obs(last_s=1.0)                                    # the frames recorded over the last 1 s (reading moves no time)
res = r.submit("ee_delta", A, cameras=cams[:1], video="mp4")   # A: (T, 12) rows, one per control step
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`hold(s)` holds the robot still while physics runs for `s` seconds: the delta channels are zero, and the targets, grip
and mode are kept. Those control steps are part of the episode. One call returns at most 3000 images.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`) and returns
  the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` (`.png`, `.npy`,
  `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- Action `ee_delta`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion per
  control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); `grip` (+1 closes,
  -1 opens); `base_x, base_y, base_yaw` -- the mobile base's target velocities in its own frame (1.0 = 1 m/s for
  `base_x` / `base_y` and 1.5 rad/s for `base_yaw`; force-limited velocity servos, so the base may lag the target);
  `torso` -- the torso lift, a joint-position controller with delta input (each step sets the lift's height target to
  its current height + 0.05 m × the value, so 1.0 = 5 cm per step; lift range 0–0.34 m); `hybrid_mode` (> 0: base mode,
  the arm's goal moves with the base; <= 0: arm mode, the default -1). Every channel is clipped to [-1, 1]. Rows are
  `dt` apart (default and minimum: `control_dt`). A chunk covers at most 10 s.
- World frame: metres, z up.

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

## Others
- The faucet handle moves two ways: one turns the water on and off, the other only sets the temperature.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Finish: if you never send `/finish`, the episode is graded when your session ends.
