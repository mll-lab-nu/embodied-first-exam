# RoboCasa-GR1 · PosttrainPnPNovelFromPlacematToBowlSplitA (standard)

## Task
Put the can from the placemat in the bowl, and move both hands away.

## Goal
Success: the can is in the bowl, not touching the counter, with the bowl still upright and both hands moved away from
the can and the bowl; the other item that started on the placemat with the can is not in the bowl. Success is judged on
how things stand when the episode ends. It ends when you call finish (Limits) or when your session ends. The robot never
tells you whether you have succeeded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Fourier GR1 humanoid (arms, waist and two dexterous six-command Fourier hands, on a fixed base), at a simulated
kitchen counter (RoboCasa GR1 tabletop, robosuite / MuJoCo). The robot runs as a service you reach through its client or
its MCP tools, as if it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, egoview, robot0_eye_in_right_hand, robot0_eye_in_left_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.hold(2.0, cameras=cams[:1])                            # hold still for 2 s of robot time
obs = r.get_obs(last_s=1.0)                                    # the frames recorded over the last 1 s (reading moves no time)
res = r.submit("ee_pose", A, cameras=cams[:1], video="mp4")   # A: (T, 24) rows, one per control step
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`hold(s)` keeps applying the last command (before the first one: both grip sites' current poses and the current hand
commands) while physics runs for `s` seconds; those control steps are part of the episode. Every channel is an absolute
target, so the grip sites stay within about a millimetre, but the IK's posture term can still move the waist and elbows
by a few hundredths of a radian while it holds. One call returns at most 3000 images.

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
- Action `ee_pose`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` --
  absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics
  controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order
  `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a
  binary grip. The GR1 has no mobile base. Values are clipped to the limits. Rows are `dt` apart (default and minimum:
  `control_dt`; a chunk covers at most 10 s).
- World frame: metres, z up. In the proprio, `eef_left_*` / `eef_right_*` are the grip sites' positions in the world
  frame; the action's pose targets and the `cmd_*` entries (the last command) are in the robot's base frame. The robot's
  base frame (body `robot0_base`, fixed in the world) has its origin at world (2.65064, -2.13092, 0.91581) m and is
  turned +90.0 deg about z (quaternion w x y z (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1,
  0], [1, 0, 0], [0, 0, 1]].

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

### Hands
Each hand command is the position target, in radians, of that finger's joints (`thumb_flexion` drives two thumb joints,
`thumb_rotation` one): 0 is the straight, open finger, larger values bend it toward the palm (the hand closes), and
every finger joint stops at the end of its range (1.22 to 1.74 rad), so values below 0 or above about 1.7 change nothing
more. The grip site that the pose targets place is the origin of the hand's mounting frame (`gripper0_right_grip_site`,
`gripper0_left_grip_site`), at the wrist end of the hand, not a point between the fingertips. The four small pink
spheres beside each hand are part of the robot model (visual markers `robot0_<side>_pinch_spheres_0..3`, about 13.5 cm
from its grip site, with no collision): they are not objects.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
