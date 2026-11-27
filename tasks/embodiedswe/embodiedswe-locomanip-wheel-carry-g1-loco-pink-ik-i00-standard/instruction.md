# EmbodiedSWE · carry the wheel to the basket, Unitree G1 (standard)

## Task
Carry the steering wheel from the table in front of you to the basket on the other table, off to your right, and leave
it in the basket.

## Goal
Success: the steering wheel was lifted off the near table and carried over, and it now rests inside the basket, let go
of and still (not held, not on the rim).

Lifting the wheel off the near table and carrying it over count as they happen.

When you are done, send `/finish` to end the episode and get it graded. Everything else is judged on the state at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Unitree G1 humanoid with three-finger hands, walking under EmbodiedSWE's frozen locomotion policy, its arms and waist
under its Pink IK. The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images; a larger request is refused (400)
before anything runs. The count is cameras × frames captured, where the frames are the first, one every round(60 /
`video_fps`) control steps, and the last. Each depth frame counts as one more image. `video="none"` captures only the
first and the last frame. A call that names no cameras gets `wide`, `head` at 3 frames per second, so every call up to
`max_chunk_s` fits.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
The action is `ee_pose` only, 32 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz`
each), 14 hand joint targets (rad), then the base command `vx vy wz hip_height` (`[0, 0, 0, 0.72]` stands still; the
wrist poses are in the world frame, so move them with the robot while it walks). Rows are streamed at the 60 Hz control
rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates
are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `wide`, `pick`, `place`, `overview` (static) and `head` (on the torso, where
the real G1 carries its depth camera).

## Limits
- Time: 14400 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 400,000 control steps (1.9 h of simulated time, reason `step_guard`), then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
