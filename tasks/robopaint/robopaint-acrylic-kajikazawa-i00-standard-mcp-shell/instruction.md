# RoboPaint · acrylic stroke copy · Kajikazawa in Kai Province (after Hokusai) (standard-mcp-shell)

## Task
A simulated Franka Panda arm holding a round acrylic brush. Task (笔触临摹, stroke copy): copy the painting shown in the
picture `/app/target.png` (a small acrylic painting after Katsushika Hokusai's woodblock print Kajikazawa in Kai
Province, c. 1830-32) onto the main sheet, in at most 377 strokes. The robot runs as a service you reach through the
`efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real hardware: one
live episode.

## Goal
Success: your painting on the main sheet matches the picture: the same colours in the same places, the same lights and
darks and the same edges, with paint where the picture has paint and only there, in at most 377 strokes; a small offset
of the whole painting (a few millimetres) is forgiven. The process rules below must hold as well. The episode runs until
your time is up (or a simulator error): there is no early end, and the main sheet is scored as your episode left it.

You get no score while you work: the grader scores the main sheet afterwards from the service's own record of your
episode. The score (`final_reward`, 0 to 1) is higher the closer your colours are to the picture's; it is scaled down
above the stroke cap and when a process rule fails.

Process rules: paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush, pressed
for the width you want. Colouring in or filling areas with a thin line, zigzag or serpentine fills, and contour-offset
fills (paths that circle round and round inside an area) are not allowed and fail the task, even when the sheet matches
the picture. The grader checks this on the episode with two numbers you can check yourself; only painted strokes on the
main sheet count (the practice sheet is free):
- Paint path budget: `path_mm` ≤ 44300 mm. `path_mm` is the total length of the brush tip's path while it presses on the
  main sheet with paint (all strokes together, sampled at every physics step).
- Strokes are sweeps: `scribble_share` ≤ 0.1. A stroke's scribble ratio is its length divided by the diagonal of its
  bounding box on the sheet (taken as at least 10 mm): about 1 for a straight or curved sweep, 2 for a sweep out and
  back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share` is the share
  of `path_mm` in strokes whose ratio is above 2.5.

Breaking a process rule fails the task.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: paint is permanent; every stroke you make stays on the paper.
- No privileged state: you see what the cameras see and feel the robot's own joint positions, velocities and efforts and
  its brush-tip pose; no sheet readout, no brush state, no score.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: the arm's base link panda_link0, +X away from the base over the table and the sheets, +Y to the
robot's left (where the paint or ink is), +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts:
arm (arm: 7 joints, end-effector pose). Cameras: `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: Paints: spec_file static.wells.wells (name, colour, radius 12 mm), in wells on a plate on the robot's left
(+Y): the tip inside a well's circle and below the paint surface loads that paint (the brush starts dry; a new paint
replaces the previous one). The main sheet (scored, under canvas_cam) and the practice sheet beside it (free for tests)
are described in spec_file static.sheets; positions in the world are not given: find the sheets and the paint wells on
the cameras (side_cam shows the brush's height above the paper). One continuous contact of the loaded tip with the main
sheet is one stroke, and pressing deeper gives a wider mark (the handle touches the paper 15 mm below its surface). A
stroke is best sent as one execute_trajectory space ee call: a few rows (above the start, press down, sweep along the
stroke, lift), dt 0.1 to 0.5 s apart; the service moves the tip on a straight line between consecutive rows. Hold the
brush vertical, tuft down (the start orientation). The arm is position-controlled at 20 Hz and lags a moving target. The
episode ends only when your time is up.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service builds the scene, under a minute)
spec = r.spec()                               # action types, dims, joint limits, cameras, budgets, static facts (sheets, paints, brush)

obs = r.get_obs()                             # current frames of spec["default_cameras"] (all but practice_cam): obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...28 names], "now": [...]}: 7 joints, tip x y z qw qx qy qz, joint velocities, efforts
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame (static cameras)
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

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
  pixel-aligned with `obs.last[cam]` (0 = no reading); `depth="frames"` in `r.submit(...)` or a watch → `res.depth[cam]`
  (N,H,W), one map per frame (1 mm steps). Depth is geometry only: paint on the paper never shows in it.
- `meta["time_left_s"]` is the service's count of the time left.

A service restart is not a reset. If the service crashes, it restarts and resumes the same episode in the state after
the last call it completed (the call that was running is lost as a whole: you get a connection error). `r.wait_ready()`
waits until it answers again (resuming replays the episode so far without rendering; the clock keeps running), then
`r.status()` tells `calls` and `control_steps`, so you know what was executed (`spec["on_service_error"]`).

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

## Others
- A practice sheet lies beside the main sheet: test the brush there as much as you like; it is never scored or counted.
- The exemplar is this robot's painting after Katsushika Hokusai, *Kajikazawa in Kai Province* (c. 1830-32), a
  public-domain work (Wikimedia Commons `File:Kajikazawa in Kai province.jpg`, Public domain); the exemplar picture is
  CC0.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; actions and simulated time are reported as cost; a runaway guard stops the robot after 72000
  control steps (1 h of simulated time; watching with `seconds > 0` also advances it).
