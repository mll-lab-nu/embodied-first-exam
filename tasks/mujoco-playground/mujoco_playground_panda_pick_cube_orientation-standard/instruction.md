# MuJoCo Playground · Panda pick cube with orientation (standard)

## Task
Pick up the green box and hold it at the see-through red box, tilted the same way.

## Goal
Success: the green box is at the see-through red box, tilted the same way as it. Success is judged on how things stand
when the episode ends. It ends when you call finish (Limits) or when your session ends. The robot never tells you
whether you have succeeded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka Panda arm (MuJoCo Playground's scene, in MuJoCo). The robot runs as a service you reach through its client or
its MCP tools, as if it were real hardware: one live episode.

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
obs = r.hold(2.0, cameras=cams[:1])                            # hold the targets for 2 s of robot time
obs = r.get_obs(last_s=1.0)                                    # the frames recorded over the last 1 s (reading moves no time)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 8) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```

One call returns at most 3000 images.

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
Action type `joint_position` (8): `actuator1..7` joint targets (rad), `actuator8` finger opening (0..0.04 m); rows are
`dt` apart (a multiple of `control_dt`), each held (`interpolate="hold"`) or ramped from the previous row (`"linear"`,
default) over its control steps; clipped to the limits in the spec. A chunk covers at most 10 s.

### Observations
`meta["proprio"]` (`layout`, `now`): the joint positions, velocities and current targets. `meta["task"]` is the task's
target (`target_pos`, and `target_quat_wxyz` where it has one). Calibration: `meta["cameras"][cam]` holds `intrinsic_cv`
(pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x right, y up, the camera looks along -z; the
viewpoint the image is rendered from), for the state at the end of that call (the `last` image and the last frame of
every stack). Depth is the distance along the viewing axis, in metres. The four cameras are fixed.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
