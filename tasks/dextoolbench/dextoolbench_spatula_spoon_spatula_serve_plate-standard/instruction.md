# DexToolBench · spoon spatula · serve_plate (standard)

## Task
Pick up the spatula and make a serving motion onto the plate, following the green ghost spatula through its poses in
order.

## Goal
Success: the spatula has lined up closely with the ghost spatula, in both position and orientation, at each of its 48
poses in order. Each pose counts when it is reached: success is judged on whether every pose was reached, in order, by
the time the episode ends.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded. No reset is possible after
  `/finish`.
- You get only the cameras, the robot's own joint positions, velocities and targets, and the current goal pose with the
  count of goals reached before it: no object poses, no scene layout, no success signal.

## Robot Interface
A KUKA iiwa 14 arm with a 22-joint Sharpa HA4 dexterous hand stands next to a table with a spoon spatula on it
(DexToolBench, MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # camera names
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> float16 metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joint positions, velocities, current targets
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]                              # see below
obs = r.hold(2.0, cameras=cams[:1])           # hold the targets for 2 s of robot time
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 29) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
obs = r.reset(cameras=cams)                   # a new episode from the starting state; obs.meta["resets_left"]
```
After the step limit (`spec()["max_control_steps"]`) `submit` raises `EpisodeOver` (409) until you reset, and after
`/finish` every call but `spec` and `status` is refused. `r.reset(cameras=None, include_depth=False)` (`POST /reset`): a
new episode from the same starting state; it returns the start's frames, and `meta` (also `r.status()`) carries
`episode`, `resets_left` and `control_steps_total`. Resetting does not stop or restore the clock. Calibration:
`meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x
right, y up, the camera looks along -z; the viewpoint the image is rendered from), for the state at the end of that call
(the `last` image and the last frame of every stack). One call returns at most 3000 images.

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
`joint_position`, 29 numbers per row: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in
`spec()["action_types"]["joint_position"]["layout"]`); rows are `dt` apart (a multiple of `control_dt`), each held
(`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
limits in the spec. A chunk covers at most 10 s.

### Observations
- Cameras: `front`, `side`, `top`, `oblique`, all fixed; RGB 240 × 320, depth on request (metres).
- Each image comes with its camera's calibration (intrinsics and pose); depth is the distance along the viewing axis, in
  metres.
- Proprioception (`obs.meta["proprio"]`): the joint positions, velocities and current targets.
- The current goal (`meta["task"]`): its pose (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`,
  `steps_left_on_goal` (null: goals have no time limit here). Once the last goal is reached it stays the current goal
  (`goals_reached` stops one short): the service never says whether every pose has been reached. The benchmark shows the
  controller the current goal, and the images show it as the green ghost tool.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 11 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 360,000 control steps (100 min of robot time).
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
