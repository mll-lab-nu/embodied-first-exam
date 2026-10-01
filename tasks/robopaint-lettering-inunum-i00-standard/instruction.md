# RoboPaint · lettering · in unum — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **Franka Panda arm holding a broad-edge (chisel) dip pen** (ManiSkill 3.0.1 physics; the pen's mark comes from a model of a real
pen) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one client and one episode.
**Task:** copy the lettering shown in the picture `/app/target.png` onto the main sheet with pen and ink, **in at most 9
strokes**.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends when your time is up (or on a simulator error). Ink is
  permanent: every stroke you make stays on the paper.
- **No privileged state.** You see what the cameras see (RGB; depth on request) plus the robot's own joint positions, velocities and
  efforts and its pen-tip pose. There is no sheet readout, no pen state and **no score**: the grader computes it afterwards from the
  service's own record of your episode.
- A **practice sheet** lies beside the main sheet: test the pen there as much as you like; it is never scored or counted.
- Steps are unlimited; your wall-clock budget of **2 h (7200 s)** is the limit (`meta["time_left_s"]`). Actions and simulated
  time are reported as cost (a runaway guard stops the robot after 72000 control steps = 1 h of simulated time; watching with
  `seconds > 0` also advances it).
- There is nothing to hand in: the service records your episode as the trajectory, which is replayed and scored. Leave your
  script at `/app/output/gen.py` for the record.
- **A service restart is not a reset.** If the service crashes, it restarts and resumes the SAME episode in the state after the
  last call it completed (the call that was running is lost as a whole: you get a connection error). `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far without rendering; the clock keeps running), then
  `r.status()` tells `calls` and `control_steps`, so you know what was executed (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object; what you
  look at and where you store it is your code's decision.

## The pen, the ink and the sheets (`spec["static"]`)
- The pen is a rigid holder with a **broad-edge (chisel) steel nib 4 mm wide** at its end (no collision; the holder hits the
  paper 6 mm below its surface); the proprio "tip" pose is the middle of the nib's writing edge. **The edge lies along the tool's y axis**
  (the second column of the tip pose's rotation matrix); at the start pose that is along the writing line (world -y).
  Turning the pen about the vertical turns it (the camera images show the nib). The part of the edge that is below a sheet's surface writes (a tilted pen writes with one corner); a steel nib does
  not widen when pressed harder. Moved along its edge the nib draws a 0.4 mm line; moved across it, a line as wide as the nib.
- **Ink**: the pen starts **dry** (strokes leave no mark). The ink well, radius 20 mm, lies on a rigid plate on the robot's left
  (+y). **Dipping** = the tip inside the well's circle and below the ink surface: the pen is then inked (it never runs dry). The
  robot does not report whether the pen is inked; the nib looks dark on the cameras when it is.
- **Sheets**: the **main sheet**, a 227.18 mm square in front of the robot, is scored; the **practice sheet**, 227.18 × 99.41 mm, on
  the robot's right of the main sheet, is not.
- Wherever the inked pen touches a sheet below its surface it writes; what the mark looks like depends on how you hold, press and
  move the pen (the practice sheet is there to find out). One continuous contact of the inked pen with the main sheet is one
  **stroke**. The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag.

## Target and score
- **The target is this picture**: `/app/target.png` (1024 × 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base). Image top = the sheet's far edge
  (+x), image left = the robot's left (+y): the same orientation as `canvas_cam`. `spec["static"]["target_image"]` repeats these
  facts.
- The main sheet is scored against the picture: its **inked area** (ink coverage ≥ 0.5) vs the exemplar's ink in the picture.
  Before scoring, the main sheet is aligned with the picture: your ink is moved by the single translation (no rotation or
  scaling, one shift for the whole sheet, whole pixels, at most 5 mm along each axis) that best matches the picture; every quantity
  below is taken after that shift, which is reported (`register_dx_mm`, `register_dy_mm`; the unshifted IoU as `iou_unregistered`).
  If the best match lies at the 5 mm limit, no shift is applied. **IoU** of the inked areas; **boundary F**: how well
  the edges of your ink match the edges of the exemplar's ink (precision / recall within 1 mm); **stroke coverage**: the fraction
  of each of the exemplar's strokes covered by your ink (the worst one counts); **stray ink**: ink more than 1 mm
  away from the exemplar's ink, as a fraction of the exemplar's inked area; the **number of strokes** on the main sheet (inked
  contacts).
  **Success iff IoU ≥ 0.86, boundary F ≥ 0.80, every stroke of the exemplar covered ≥ 0.75, stray ink
  ≤ 0.04 and at most 9 strokes on the main sheet.** (The recorded episode is replayed twice and both replays must agree.) The continuous score is the IoU
  (scaled by 9 / strokes above 9 strokes).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service builds the scene, under a minute)
spec = r.spec()                               # action types, dims, joint limits, cameras, budgets, static facts (sheets, ink well, pen)

obs = r.get_obs()                             # current frames of spec["default_cameras"] (all but practice_cam): obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...28 names], "now": [...]}: 7 joints, tip x y z qw qx qy qz, joint velocities, efforts
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame (static cameras)
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", P, dt=0.05)         # P: (T, 7) pen-tip targets, rows dt apart; IK per control step
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
view along the sheets that shows the pen height).

### Optional inputs (eai-standard/2.2; nothing changes unless you ask)
- **Depth**: `r.get_obs(depth=True)` → `obs.last_depth[cam]`, float32 (H,W) z-depth in metres of the last frame, pixel-aligned with
  `obs.last[cam]` (0 = no reading); `depth="frames"` in `r.submit(...)` or a watch → `res.depth[cam]` (N,H,W), one map per frame
  (1 mm steps). Depth is geometry only: ink on the paper never shows in it.
- **Every frame**: `res.frame_step` (control steps since the episode start), `res.frame_time_s` (simulated time) and
  `res.extrinsic_cv[cam]` (N,3,4), world → camera (constant: the cameras are static).
- **`spec`**: `spec["cameras"][cam]` → `intrinsic_cv` (3×3), `mount` (its static world pose), `depth_range_m`; `spec["world"]` (frame,
  units, `wxyz` quaternions); `spec["robot_spec"]`: joint limits, PD gains, 20 Hz control / 100 Hz physics, the tool frame `tip` (no
  gripper); `spec["proprio_groups"]` names the proprio columns: `res.group("joint_vel")`, `res.group("joint_effort")` (a PD
  drive-effort estimate), `res.group("tcp_pose")` (the pen tip), `res.group(name, now=True)` for `meta["proprio"]["now"]`.
- **Kinematics** (stateless: no motion, no simulated time, free): `r.fk(q)["poses"]` → `{frame: [x,y,z,qw,qx,qy,qz]}` for the
  Panda's links and `tip`; `r.ik({"tip": pose}, seed=q)` → `{"ok", "q", "error"}`, the solver the `ee_pose` action uses.

### Action types
- `ee_pose` (7): `x y z qw qx qy qz` of the **pen tip** in the world frame (z up, the robot base at (-0.615, 0, 0),
  x away from the base, y to the robot's left); quaternion wxyz — the proprio quaternion at the start points the pen straight
  down. Rows are `dt` apart (`1/20 ≤ dt ≤ 0.5` s, a multiple of 1/20 s): the tip target moves on a straight line from the
  previous row's target at the 20 Hz control rate, one IK solve per control step (no collision checking), at most 0.25 m/s (a
  faster row is slowed down; `meta["plan"]` reports it and any IK failure). At most 400 rows and 10 s per submit.
- `joint_position` (7): `panda_joint1..7` absolute joint targets in radians (PD-tracked), rows `dt` apart, `interpolate` =
  `"linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed in
  `meta["clipped"]` (limits in the spec).
Wrist note: turning the pen far about the vertical can run joint 7 into its limit on one side; the other way round reaches the
same orientation of the nib (the mark is the same for a pen turned by 180°).

The exemplar's letterforms were authored for this benchmark and are in the public domain (CC0-1.0): `/app/NOTICE-exemplar.md`.
