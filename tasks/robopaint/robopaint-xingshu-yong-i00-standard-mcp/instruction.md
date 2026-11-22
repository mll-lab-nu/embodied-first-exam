# RoboPaint · 行书 臨帖 · 永 — STANDARD MODE, MCP TOOLS ONLY (robot as a service, eai-standard/2.2)

You control a **Franka Panda arm holding a large Chinese writing brush (毛笔)** (ManiSkill 3.0.1 physics; the brush's mark comes from
a dynamic model of a real brush) **as if it were real hardware**: the simulator runs in a service you cannot open. You get the `efe-robot` tools and one episode. **Task (臨帖):** copy the exemplar character **永** in running script (行书), shown in the picture
`/app/target.png`, onto the main sheet with brush and ink, **in at most 6 strokes**.

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You may write and run code to compute; every robot command and observation must
go through the efe-robot MCP tools; code must not contact the simulator. Each robot command or observation is a tool
call you make yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is
checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and pass its path
as `rows_file` to `execute_trajectory`. The robot service and its rules are as described in this text; where it names
calls of the Python client `rcb_client.py`, which is not installed for your code here, use the tool that does the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: the arm's base link panda_link0, +X away from the base over the
table and the sheets, +Y to the robot's left (where the paint or ink is), +Z up. Space `native` sends rows in the
robot's own action types exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Franka Panda arm holding a brush fixed to its hand (no gripper)): arm (arm: 7 joints, end-effector
pose). Cameras: `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the robot base frame that a camera sees at pixel (u, v)
  of its full-size image (u the column, v the row), or one per pixel of `pixels` [[u, v], ...]: from a new depth image
  of that camera and its calibration (no time passes). For a camera with depth and a known pose; for any other the error
  says so.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** Ink: one ink stone (spec_file static.wells, radius 20 mm) on a plate on the robot's left (+Y):
the tip inside its circle and below the ink surface inks the brush and gathers its hairs to a point (the brush starts
dry). The main sheet (scored, under canvas_cam) and the practice sheet beside it (free for tests) are described in
spec_file static.sheets; positions in the world are not given: find the sheets and the ink stone on the cameras
(side_cam shows the brush's height above the paper). One continuous contact of the loaded tip with the main sheet is one
stroke, and pressing deeper gives a wider mark (the handle touches the paper 15 mm below its surface). A stroke is best
sent as one execute_trajectory space ee call: a few rows (above the start, press down, sweep along the stroke, lift), dt
0.1 to 0.5 s apart; the service moves the tip on a straight line between consecutive rows. Hold the brush vertical, tuft
down (the start orientation). The arm is position-controlled at 20 Hz and lags a moving target. The episode ends only
when your time is up.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends when your time is up (or on a simulator error). Ink is
  permanent: every stroke you make stays on the paper.
- **No privileged state.** You see what the cameras see (RGB; depth on request) plus the robot's own joint positions, velocities and
  efforts and its brush-tip pose. There is no sheet readout, no brush state and **no score**: the grader computes it afterwards from
  the service's own record of your episode.
- A **practice sheet** lies beside the main sheet: test the brush there as much as you like; it is never scored or counted.
- Steps are unlimited; **the time limit (`## Time limit`)** is your only budget (`meta["time_left_s"]` is the service's count of
  it). Actions and simulated time are reported as cost (a runaway guard stops the robot after 72000 control steps = 1 h of
  simulated time; watching with `seconds > 0` also advances it).
- There is nothing to hand in: the service records your episode as the trajectory and scores the main sheet as your episode left it.
- **A service restart is not a reset.** If the service crashes, it restarts and resumes the SAME episode in the state after the
  last call it completed (the call that was running is lost as a whole: you get a connection error). `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far without rendering; the clock keeps running), then
  `r.status()` tells `calls` and `control_steps`, so you know what was executed (`spec["on_service_error"]`).
- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their paths with small JSON; open an image with your file-reading tool, or ask for small images in the result with `inline_cameras`.

## The brush, the ink and the sheets (`spec["static"]`)
- The brush is a rigid handle with a **30 mm soft hair tuft** (no collision; the handle itself hits the paper when the tip is 30 mm
  below its surface); the proprio "tip" pose is the tip of the unbent tuft. Hold the brush vertical (as at the start).
- **Ink**: the brush starts **dry** (strokes leave no mark). The ink stone, radius 20 mm, lies on a rigid plate on the robot's left
  (+y). **Dipping** = the tip inside the stone's circle and below the ink surface: the brush is then inked (it never runs dry) and
  its hairs are gathered back to a point. The robot does not report whether the brush is inked; the tuft looks dark on the cameras
  when it is.
- **Sheets**: the **main sheet**, a 227.18 mm square in front of the robot, is scored; the **practice sheet**, 227.18 × 99.41 mm, on
  the robot's right of the main sheet, is not.
- The brush behaves like a soft brush: wherever the inked tip is below a sheet's surface, the pressed hairs leave a mark, and what
  the mark looks like depends on how you press and move. You have to find out how (the practice sheet is there for that).
- One continuous contact of the inked tip with the main sheet is one **stroke**. The arm is position-controlled (PD, 20 Hz
  targets): a moving target is followed with a lag.

## Target and score
- **The target is this picture**: `/app/target.png` (1024 × 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base). Image top = the sheet's far edge
  (+x), image left = the robot's left (+y): the same orientation as `canvas_cam`. `spec["static"]["target_image"]` repeats these
  facts.
- Before scoring, the main sheet is **aligned with the picture**: your ink is moved by the single translation (no rotation or
  scaling, one shift for the whole sheet; whole pixels of 0.22 mm, at most 5 mm along each axis) that overlaps the exemplar's ink
  best, and every quantity below is taken after that shift (reported as `register_dx_mm`, `register_dy_mm`); if the best overlap
  lies at the 5 mm limit, no shift is applied.
- The main sheet is scored against the picture: its **inked area** (ink coverage ≥ 0.5) vs the exemplar's ink in the picture:
  **IoU**; **boundary F** (how well the edges of your ink match the edges of the exemplar's ink, precision / recall within 1 mm);
  **region coverage** (the exemplar's ink is divided into 9 regions; the fraction of each region covered by your ink; the
  worst one counts); **stray ink**
  (ink more than 1 mm away from the exemplar's ink, as a fraction of the exemplar's inked area); the **number of strokes** on the
  main sheet. **Success iff IoU ≥ 0.80, boundary F ≥ 0.75, every region covered ≥ 0.80, stray ink ≤ 0.04 and at most
  6 strokes (continuous brush contacts) on the main sheet** (scored on the main sheet as your episode left it). The continuous score
  is the IoU (scaled by 6 / strokes above 6 strokes).

## Process rules
Write the character with brush strokes, the way a person writes it: each stroke of the exemplar is written along its length,
with the brush pressed for the stroke's width (vary the press where the width changes); going over a stroke again is fine.
Colouring in or filling the shapes, zigzag or serpentine fills, and contour-offset fills (paths that go round and round inside a
shape) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the live
episode with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is free):
- `path_mm`: the total length of the brush tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > 1450 mm and `mark_width_mm` < 2.25 mm** (a long path of thin marks): it
fails the task. Our reference solution writes this exemplar with `path_mm` 726 mm and `mark_width_mm`
5.14 mm; the limits are 3 times the path (rounded up) and 0.3 times the mark width (rounded down)
of an earlier reference solution, which wrote it with `path_mm` 483 mm and `mark_width_mm` 7.53 mm. A pressed brush, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**The stroke cap counts strokes as they are written, not contacts** (this refines "one continuous contact is one stroke"
above). A contact is cut into two strokes wherever the brush moves more than 5 mm along the main sheet without
marking it (its mark narrower than 0.1 mm: a press too light to ink), and a stroke longer than
1330 mm of path counts as one stroke per started 1330 mm (5 times our
reference solution's longest stroke, 265 mm, rounded up). Pieces joined by a touch too light to ink are
therefore separate strokes, and one contact held down to write and re-write for a long time counts as several; a stroke
written with the brush down and lifted at its end is one. **Strokes are sweeps:** at most 10 % of
`path_mm` may lie in strokes whose path is longer than 12 times the diagonal of their bounding box (taken as at
least 10 mm): back-and-forth, zigzag, spiral or looping fills inside one stroke fail (our reference solution's
strokes stay under 5 times).

**Success iff the picture rule above holds, the run is not colouring in, the counted strokes are within the cap and the strokes
are sweeps.** The continuous score is the one above, × min(1,
1450 / `path_mm`) when it is colouring in, × (1 − that share) when the strokes are not sweeps, and with the cap's
scaling taken on the counted strokes.

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service builds the scene, under a minute)
spec = r.spec()                               # action types, dims, joint limits, cameras, budgets, static facts (sheets, ink stone, brush)

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
Cameras (all static): `canvas_cam` (1024×1024, straight above the main sheet; image top = the sheet's far edge, image left = the
robot's left; the arm hides the sheet when it is above it), `practice_cam` (512×1024 portrait, above the practice sheet, same
orientation), `scene_cam` (640×480, across the table facing the robot) and `side_cam` (640×360, low on the robot's right, a grazing
view along the sheets that shows the brush height).

### Optional inputs (eai-standard/2.2; nothing changes unless you ask)
- **Depth**: `r.get_obs(depth=True)` → `obs.last_depth[cam]`, float32 (H,W) z-depth in metres of the last frame, pixel-aligned with
  `obs.last[cam]` (0 = no reading); `depth="frames"` in `r.submit(...)` or a watch → `res.depth[cam]` (N,H,W), one map per frame
  (1 mm steps). Depth is geometry only: ink on the paper never shows in it.
- **Every frame**: `res.frame_step` (control steps since the episode start), `res.frame_time_s` (simulated time) and
  `res.extrinsic_cv[cam]` (N,3,4), world → camera (constant: the cameras are static).
- **`spec`**: `spec["cameras"][cam]` → `intrinsic_cv` (3×3), `mount` (its static world pose), `depth_range_m`; `spec["world"]` (frame,
  units, `wxyz` quaternions); `spec["robot_spec"]`: joint limits, PD gains, 20 Hz control / 100 Hz physics, the tool frame `tip` (no
  gripper); `spec["proprio_groups"]` names the proprio columns: `res.group("joint_vel")`, `res.group("joint_effort")` (a PD
  drive-effort estimate), `res.group("tcp_pose")` (the brush tip), `res.group(name, now=True)` for `meta["proprio"]["now"]`.
- **Kinematics** (stateless: no motion, no simulated time, free): `r.fk(q)["poses"]` → `{frame: [x,y,z,qw,qx,qy,qz]}` for the
  Panda's links and `tip`; `r.ik({"tip": pose}, seed=q)` → `{"ok", "q", "error"}`, the solver the `ee_pose` action uses.

### Action types
- `ee_pose` (7): `x y z qw qx qy qz` of the **brush tip** in the world frame (z up, the robot base at (-0.615, 0, 0),
  x away from the base, y to the robot's left); quaternion wxyz — the proprio quaternion at the start points the brush straight
  down. Rows are `dt` apart (`1/20 ≤ dt ≤ 0.5` s, a multiple of 1/20 s): the tip target moves on a straight line from the
  previous row's target at the 20 Hz control rate, one IK solve per control step (no collision checking), at most 0.25 m/s (a
  faster row is slowed down; `meta["plan"]` reports it and any IK failure). At most 400 rows and 10 s per submit.
- `joint_position` (7): `panda_joint1..7` absolute joint targets in radians (PD-tracked), rows `dt` apart, `interpolate` =
  `"linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed in
  `meta["clipped"]` (limits in the spec).
- One call returns at most 640 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The exemplar picture is derived from a public-domain historical work of running-script calligraphy (Wikimedia Commons, PD-Art);
rendered by Embodied First Exam (RoboPaint): `/app/NOTICE-exemplar.md`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **5 GiB of memory**, **2048 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
