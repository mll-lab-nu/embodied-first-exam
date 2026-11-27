# MuJoCo Playground · ALOHA hand-over (standard)

## Task
Pick up the red box with the left arm, pass it to the right arm, and hold it at the see-through target box. Then take
the left arm off the box.

## Goal
Success: the right gripper holds the box at the target box, off the table, and no part of the left arm touches the box.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
An ALOHA 2 bimanual robot (two ViperX 300s arms facing each other across a table; MuJoCo Playground's scene, in MuJoCo).
The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one live
episode.

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
obs = r.hold(2.0, cameras=cams[:1])                            # hold the targets for 2 s of robot time
obs = r.get_obs(last_s=1.0)                                    # the frames recorded over the last 1 s (reading moves no time)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 14) rows dt apart
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
Action type `joint_position` (14): per arm `waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate, gripper`;
rows are `dt` apart (a multiple of `control_dt`), each held (`interpolate="hold"`) or ramped from the previous row
(`"linear"`, default) over its control steps; clipped to the limits in the spec. A chunk covers at most 10 s.

### Observations
`meta["proprio"]` (`layout`, `now`): the joint positions, velocities and current targets. `meta["task"]` is the task's
target (`target_pos`, and `target_quat_wxyz` where it has one). Calibration: `meta["cameras"][cam]` holds `intrinsic_cv`
(pinhole, pixels) and `cam2world_gl`, the 4x4 camera-to-world pose the image is rendered from (OpenGL axes: x right, y
up, the camera looks along -z). Both describe the state at the end of that call: the `last` image and the last frame of
every stack. Depth is the distance along the viewing axis, in metres. The overhead and teleoperator cameras are fixed.
The two wrist cameras move with the arms (`spec["cameras"][cam]["moving"]`): for them a response with several frames
also carries one pose per frame, `res.raw["cam2world_gl/<cam>"]["data"]`, float64 `(n_frames, 4, 4)`. `intrinsic_cv` is
`[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]` for the 320 x 240 image; fx and fy differ for the overhead and wrist cameras
(their sensor is wider than the image): use both.

## Limits
- Time: 1800 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Finish: if you never send `/finish`, the episode is graded when your session ends.
