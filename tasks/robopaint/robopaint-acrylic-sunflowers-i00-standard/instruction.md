# RoboPaint · acrylic stroke copy · Sunflowers (after van Gogh) (standard)

## Task
Copy the painting in `/app/target.png` (after Vincent van Gogh's Sunflowers) onto the main sheet in at most 380 strokes.

## Goal
Success: the main sheet looks like the picture (the same colours in the same places, the same lights and darks and
edges, and paint only where the picture has paint), you used at most 380 strokes, and the process rules below hold; a
small shift of the whole painting does not matter. The main sheet is scored as the episode leaves it. It ends when you
call finish (Limits) or when your session ends. The robot never tells you whether you have succeeded.

You are scored on how close your colours are to the picture's, afterwards, from the service's record of your episode.

Paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush. Colouring in or filling
areas with a thin line, zigzag or serpentine fills, and fills that circle round and round inside an area fail the task,
even when the sheet matches the picture. The exact checks are under Process rules in Robot Interface.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: paint is permanent; every stroke you make stays on the paper.
- You see only what the cameras see and feel the robot's own joint positions, velocities and efforts and its brush-tip
  pose: no sheet readout, no brush state, no score.

## Robot Interface
A simulated Franka Panda arm holding a round acrylic brush. The robot runs as a service you reach through its client or
its MCP tools, as if it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service builds the scene, under a minute)
spec = r.spec()                               # action types, dims, joint limits, cameras, budgets, static facts (sheets, paints, brush)

obs = r.get_obs()                             # current frames of spec["default_cameras"] (all but practice_cam): obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...28 names], "now": [...]}: 7 joints, tip x y z qw qx qy qz, joint velocities, efforts
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame (static cameras)
obs = r.hold(2.0)                             # hold the last command for 2 s of robot time: obs.video[cam] = mp4 bytes
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("ee_pose", P, dt=0.05)         # P: (T, 7) brush-tip targets, rows dt apart; IK per control step
res = r.submit("joint_position", A, dt=0.05)  # A: (T, 7) joint targets, rows dt apart; streamed at 20 Hz, linear interpolation
res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["canvas_cam"]                       # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["practice_cam"]                    # uint8 (N,H,W,3) at video_fps if requested
res.last["canvas_cam"]; res.proprio           # last frame per camera; float32 (N, 28) proprio at each video frame
r.status()                                    # calls, control_steps, done, reason, elapsed_s
r.wait_ready()                                # after a connection error: wait until the service has resumed
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy, frame_meta.npz, depth
```
- One call returns at most 640 images; a larger request is refused.
- Every frame: `res.frame_step` (control steps since the episode start), `res.frame_time_s` (simulated time) and
  `res.extrinsic_cv[cam]` (N,3,4), world → camera (constant: the cameras are static).
- `spec`: `spec["cameras"][cam]` → `intrinsic_cv` (3×3), `mount` (its static world pose), `depth_range_m`;
  `spec["world"]` (frame, units, `wxyz` quaternions); `spec["robot_spec"]`: joint limits, PD gains, 20 Hz control / 100
  Hz physics, the tool frame `tip` (no gripper); `spec["proprio_groups"]` names the proprio columns:
  `res.group("joint_vel")`, `res.group("joint_effort")` (a PD drive-effort estimate), `res.group("tcp_pose")` (the brush
  tip), `res.group(name, now=True)` for `meta["proprio"]["now"]`.
- Kinematics (stateless: no motion, no simulated time, free): `r.fk(q)["poses"]` → `{frame: [x,y,z,qw,qx,qy,qz]}` for
  the Panda's links and `tip`; `r.ik({"tip": pose}, seed=q)` → `{"ok", "q", "error"}`, the solver the `ee_pose` action
  uses.
- Depth: `r.get_obs(depth=True)` → `obs.last_depth[cam]`, float32 (H,W) z-depth in metres of the last frame,
  pixel-aligned with `obs.last[cam]` (0 = no reading); `depth="frames"` in `r.submit(...)` or `r.hold(...)` →
  `res.depth[cam]` (N,H,W), one map per frame (1 mm steps). Depth is geometry only: paint on the paper never shows in
  it.
- `meta["time_left_s"]` is the service's count of the time left.

A service restart is not a reset. If the service crashes, it restarts and resumes the same episode in the state after
the last call it completed (the call that was running is lost as a whole: you get a connection error). `r.wait_ready()`
waits until it answers again (resuming replays the episode so far without rendering; the clock keeps running), then
`r.status()` tells `calls` and `control_steps`, so you know what was executed (`spec["on_service_error"]`).

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
Two action types:
- `ee_pose` (7): `x y z qw qx qy qz` of the brush tip in the world frame (z up, the robot base at (-0.615, 0, 0), x away
  from the base, y to the robot's left); quaternion wxyz — the proprio quaternion at the start points the brush straight
  down. Rows are `dt` apart (`1/20 ≤ dt ≤ 0.5` s, a multiple of 1/20 s): the tip target moves on a straight line from
  the previous row's target at the 20 Hz control rate, one IK solve per control step (no collision checking), at most
  0.25 m/s (a faster row is slowed down; `meta["plan"]` reports it and any IK failure). At most 400 rows and 10 s per
  submit.
- `joint_position` (7): `panda_joint1..7` absolute joint targets in radians (PD-tracked), rows `dt` apart, `interpolate`
  = `"linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed in
  `meta["clipped"]` (limits in the spec).

### Observations
- Cameras (all static): `canvas_cam` (1024×1024, straight above the main sheet; image top = the sheet's far edge, image
  left = the robot's left; the arm hides the sheet when it is above it), `practice_cam` (512×1024 portrait, above the
  practice sheet, same orientation), `scene_cam` (640×480, across the table facing the robot) and `side_cam` (640×360,
  low on the robot's right, a grazing view along the sheets that shows the brush's height).
- Depth on request: float32 (H,W) z-depth in metres, pixel-aligned with the image (0 = no reading). Depth is geometry
  only: paint on the paper never shows in it.
- Proprioception: the robot's own joint positions, velocities and efforts and its brush-tip pose.

### The brush, the paints and the sheets
- The brush is a rigid handle with a 15 mm soft tuft (no collision; the handle hits the paper 15 mm below its surface);
  the proprio "tip" pose is the tuft's tip. Hold it vertical (as at the start).
- Paints (every colour the painting needs, premixed): 10 wells on a rigid plate on the robot's left (+y), in two rows,
  radius 12 mm; `spec["static"]["wells"]["wells"]` gives each well's name, colour and radius. Dipping = the tip inside a
  well's circle and below the paint surface: the brush is then loaded with that paint (the previous paint is gone; no
  mixing on the palette, it never runs dry). The brush starts dry. The robot does not report which paint it carries; the
  tuft shows the colour on the cameras.
- Sheets: the main sheet, a 227.18 mm square in front of the robot, is scored; the practice sheet, 227.18 × 99.41 mm, on
  the robot's right of the main sheet, is not.
- Wherever the loaded tip is below a sheet's surface the brush paints an opaque acrylic mark; what the mark looks like
  depends on how you press, move and turn the brush (the practice sheet is there to find out), and later strokes cover
  earlier ones. One continuous contact of the loaded brush with the main sheet is one stroke. The arm is
  position-controlled (PD, 20 Hz targets): a moving target is followed with a lag.

### The target picture
`/app/target.png` (1024 × 1024 px, RGB) shows the exemplar at its true size and place on the main sheet: the image
covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's top-left, has
its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's right, Y
towards the robot, origin = the sheet's far-left corner as seen from the robot's base). Image top = the sheet's far edge
(+x), image left = the robot's left (+y): the same orientation as `canvas_cam`.

### Process rules
The grader checks the process rules in Goal on the episode with two numbers you can check yourself; only painted strokes
on the main sheet count (the practice sheet is free):
- Paint path budget: `path_mm` ≤ 41700 mm. `path_mm` is the total length of the brush tip's path while it presses on the
  main sheet with paint (all strokes together, sampled at every physics step).
- Strokes are sweeps: `scribble_share` ≤ 0.1. A stroke's scribble ratio is its length divided by the diagonal of its
  bounding box on the sheet (taken as at least 10 mm): about 1 for a straight or curved sweep, 2 for a sweep out and
  back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share` is the share
  of `path_mm` in strokes whose ratio is above 2.5.

Breaking a process rule fails the task.

The score (`final_reward`, 0 to 1) is higher the closer your colours are to the picture's; it is scaled down above the
stroke cap and when a process rule fails.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; actions and simulated time are reported as cost; a runaway guard stops the robot after 72000
  control steps (1 h of simulated time; `hold(s)` also advances it).
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
