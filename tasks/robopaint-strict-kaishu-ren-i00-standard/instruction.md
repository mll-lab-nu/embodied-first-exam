# RoboPaint-strict · 楷书 臨帖 · 人 — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **Franka Panda arm holding a large Chinese writing brush (毛笔)** (ManiSkill 3.0.1 physics; the brush's mark comes from
a dynamic model of a real brush) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task (臨帖):** copy the exemplar character **人** in regular script (楷书), shown in the picture
`/app/target.png`, onto the main sheet with brush and ink, **in at most 2 strokes**.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends when your time is up (or on a simulator error). Ink is
  permanent: every stroke you make stays on the paper.
- **No privileged state.** You see what the cameras see (RGB; depth on request) plus the robot's own joint positions, velocities and
  efforts and its brush-tip pose. There is no sheet readout, no brush state and **no score**: the grader computes it afterwards from
  the service's own record of your episode.
- A **practice sheet** lies beside the main sheet: test the brush there as much as you like; it is never scored or counted.
- Steps are unlimited; your wall-clock budget of **2 h (7200 s)** is the limit (`meta["time_left_s"]`). Actions and simulated time
  are reported as cost (a runaway guard stops the robot after 72000 control steps = 1 h of simulated time; watching with
  `seconds > 0` also advances it).
- There is nothing to hand in: the service records your episode as the trajectory, which is replayed and scored. Leave your
  script at `/app/output/gen.py` for the record.
- **A service restart is not a reset.** If the service crashes, it restarts and resumes the SAME episode in the state after the
  last call it completed (the call that was running is lost as a whole: you get a connection error). `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far without rendering; the clock keeps running), then
  `r.status()` tells `calls` and `control_steps`, so you know what was executed (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object; what you
  look at and where you store it is your code's decision.

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
  **stroke coverage** (the fraction of each of the exemplar's strokes covered by your ink; the worst one counts); **stray ink**
  (ink more than 1 mm away from the exemplar's ink, as a fraction of the exemplar's inked area); the **number of strokes** on the
  main sheet. **Success iff IoU ≥ 0.80, boundary F ≥ 0.75, every stroke of the exemplar covered ≥ 0.80, stray ink ≤ 0.04 and at
  most 2 strokes on the main sheet** (the recorded episode is replayed twice and both replays must agree). The continuous score
  is the IoU (scaled by 2 / strokes above 2 strokes).

## Process rules (RoboPaint-strict)
Write the character with brush strokes, the way a person writes it: each stroke of the exemplar is written along its length,
with the brush pressed for the stroke's width (vary the press where the width changes); going over a stroke again is fine.
Colouring in or filling the shapes, zigzag or serpentine fills, and contour-offset fills (paths that go round and round inside a
shape) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the replayed
episode with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is free):
- `path_mm`: the total length of the brush tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > 720 mm and `mark_width_mm` < 2.43 mm** (a long path of thin marks): it
fails the task. Our reference solution writes this exemplar with `path_mm` 237 mm and `mark_width_mm`
8.13 mm; the limits are 3 times its path (rounded up) and 0.3 times its mark width
(rounded down). A pressed brush, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**Success iff the picture rule above holds and the run is not colouring in.** The continuous score is the one above, × min(1,
720 / `path_mm`) when it is colouring in.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
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

The exemplar derives from the fonts AR PL KaitiM GB / AR PL UKai (Arphic Public License): `/app/ARPHICPL.TXT`,
`/app/NOTICE-exemplar.md`.
