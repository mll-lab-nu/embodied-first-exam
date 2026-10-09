# RoboPaint · oil painting from a reference · The Fighting Temeraire (after Turner) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **Franka Panda arm holding an oil-paint brush** (ManiSkill 3.0.1 physics; a painting-engine brush) **as if it were real
hardware**: the simulator runs in a service you cannot open. You get one client and one episode. **Task (paint from a reference):**
paint the picture shown in `/app/target.png` (a square crop of J. M. W. Turner's The Fighting Temeraire, 1839) onto the main sheet with brush and oil paints, **in at most 2360 strokes**.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends when your time is up (or on a simulator error). Paint is
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

## The brush, the paints and the sheets (`spec["static"]`)
- The brush is a rigid handle with a **15 mm soft tuft** (no collision; the handle hits the paper 15 mm below its surface); the
  proprio "tip" pose is the tuft's tip. Hold it vertical (as at the start).
- **Paints** (the picture's colours, premixed): 16 wells on a rigid plate on the robot's left (+y), in three rows, radius 9 mm;
  `spec["static"]["wells"]["wells"]` gives each well's name, colour and radius. **Dipping** = the tip inside a well's circle and
  below the paint surface: the brush is then loaded with that paint (the previous paint is gone; no mixing on the palette, it never
  runs dry). The brush starts **dry**. The robot does not report which paint it carries; the tuft shows the colour on the cameras.
- **Sheets**: the **main sheet**, a 227.18 mm square in front of the robot, is scored; the **practice sheet**, 227.18 × 99.41 mm, on
  the robot's right of the main sheet, is not.
- Wherever the loaded tip is below a sheet's surface the brush paints wet oil paint; what the mark looks like depends on how you
  press, move and turn the brush, and it blends with wet paint already on the sheet (the practice sheet is there to find out). One
  continuous contact of the loaded brush with the main sheet is one **stroke**. The arm is position-controlled (PD, 20 Hz targets):
  a moving target is followed with a lag.

## Target and score
- **The target is this picture**: `/app/target.png` (1024 × 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base). Image top = the sheet's far edge
  (+x), image left = the robot's left (+y): the same orientation as `canvas_cam`. `spec["static"]["target_image"]` repeats these
  facts.
- The grader compares the main sheet with the picture: the painting is compared with the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only; if the best shift reaches that limit, the sheet is scored unshifted); the metrics are then taken only inside the sheet's central area, 8 mm in from every edge (the border band is not scored); both blurred (σ = 1 mm); **ΔE** = the CIELAB colour difference (ΔE*ab) per pixel over the region where either has paint (dilated by 2 mm; the picture covers the whole sheet, so: the whole scored area): its mean and 90th percentile; **SSIM** of the lightness L* (σ 1.5 mm windows); **edge correlation** = the correlation of the lightness-gradient magnitudes of the two blurred pictures; **paint IoU** = the painted fraction of the scored area (paint coverage ≥ 0.5); the **number of strokes** on the main sheet (painted contacts). **Success iff mean ΔE ≤ 3.9, p90 ΔE ≤ 6.5, SSIM ≥ 0.85, edge correlation ≥ 0.59, paint IoU ≥ 0.96 and at most 2360 strokes** (the recorded episode is replayed twice and both replays must agree). The continuous score is max(0, 1 - mean ΔE / 20) (scaled by 2360 / strokes above 2360). Reported as well: the mean ΔE after a 4 mm blur, the SSIM at a 0.5 mm blur, and per colour region of the picture (the connected areas nearest to one paint, at least 30 mm²) the fraction within ΔE 10: the minimum and the area-weighted mean.

## Process rules
Paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush, pressed for the width you want.
Colouring in or filling areas with a thin line, zigzag or serpentine fills, and contour-offset fills (paths that circle round and
round inside an area) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the
replayed episode with two numbers you can check yourself; only painted strokes on the main sheet count (the practice sheet is
free):
- **Paint path budget: `path_mm` ≤ 51400 mm.** `path_mm` is the total length of the brush tip's path while it presses
  on the main sheet with paint (all strokes together, sampled at every physics step). The strokes of our reference solution add up
  to 17125 mm; the budget is 3 times that, rounded up.
- **Strokes are sweeps: `scribble_share` ≤ 0.1.** A stroke's scribble ratio is its length divided by the
  diagonal of its bounding box on the sheet (taken as at least 10 mm): about 1 for a straight or curved sweep,
  2 for a sweep out and back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share`
  is the share of `path_mm` in strokes whose ratio is above 2.5.

**Success iff the picture rule above holds and both process rules hold.** The continuous score is the one above ×
min(1, 51400 / `path_mm`) × (1 − `scribble_share` when the second rule fails).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
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
Cameras (all static): `canvas_cam` (1024×1024, straight above the main sheet; image top = the sheet's far edge, image left = the
robot's left; the arm hides the sheet when it is above it), `practice_cam` (512×1024 portrait, above the practice sheet, same
orientation), `scene_cam` (640×480, across the table facing the robot) and `side_cam` (640×360, low on the robot's right, a grazing
view along the sheets that shows the brush's height).

### Optional inputs (eai-standard/2.2; nothing changes unless you ask)
- **Depth**: `r.get_obs(depth=True)` → `obs.last_depth[cam]`, float32 (H,W) z-depth in metres of the last frame, pixel-aligned with
  `obs.last[cam]` (0 = no reading); `depth="frames"` in `r.submit(...)` or a watch → `res.depth[cam]` (N,H,W), one map per frame
  (1 mm steps). Depth is geometry only: paint on the paper never shows in it.
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

The picture is a public-domain painting, J. M. W. Turner, *The Fighting Temeraire* (1839; Wikimedia Commons `File:The Fighting Temeraire, JMW Turner, National Gallery.jpg`, Public domain), cropped to a square and downscaled to the sheet.
