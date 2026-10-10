# RoboPaint · oil painting from a reference · Irises (after van Gogh) — frozen instance

You control a simulated **Franka Panda arm holding an oil-paint brush** via Python: ManiSkill 3.0.1 / SAPIEN 3.0.3 physics (PhysX on
the CPU) for the robot; the paint is libmypaint's brush engine (MyPaint). **Task (paint from a reference):** paint the picture shown in `/app/target.png` (a square crop of Vincent van Gogh's Irises, 1889) onto the main sheet with brush and oil paints, **in at most 2486 strokes**.

This is a *fixed scene instance*: you may reset and retry as many times as you want. Your deliverable is **one replayable
trajectory**, not a general policy.

## The brush, the paints and the sheets
- The brush is a rigid handle with a **15 mm soft tuft** (no collision; the handle hits the paper 15 mm below its surface); the
  robot's tool point (TCP) is the tuft's tip. Hold it vertical (as at the start).
- **Paints** (the picture's colours, premixed): 16 wells on a plate on the robot's left (+y), in three rows, radius 9 mm,
  paint surface **z = 0.028 m** (plate top 0.026 m, rigid); `s.wells()` gives each well's name, colour and centre. **Dipping** = the tip
  inside a well's circle and below the paint surface: the brush is then loaded with that paint on a fresh brush (the previous
  paint is gone; no mixing on the palette, it never runs dry). The brush starts **dry**.
- **Sheets** (surface z = **0.020 m**): the **main sheet**, a 227.18 mm square centred at world **(-0.100, 0.000)**, is scored; the
  **practice sheet**, 227.18 x 99.41 mm centred at **(-0.100, -0.1856)**, is for test strokes and is never scored or counted.
- **How the paint goes on**: at every physics step (100 Hz) the tip over a sheet is one motion event for libmypaint 1.6.1 with the
  mypaint-brushes preset `tanda/oil-03-paint` made pointed (dab size scaled to the paper; the preset's random dab offset and
  tracking noise follow the pressure like the dab size, so a light press draws a thin line; the frozen preset is the instance's
  `brush.preset_json`): a wet oil paint whose mark depends on the **pressure** (press depth / 15 mm: straight strokes are about
  2 mm wide at a 1.25 mm press, 2.5 mm at 1.5 mm, 3 mm at 2 mm, 4.2 mm at 3 mm, 6 mm at 4 mm, 8 mm at 5 mm and 11 mm from 6 mm on;
  a lighter press thins and fades the line), the **speed**, the **direction** (the elliptical dabs follow it) and the engine's own
  smudging and jitter (deterministic): strokes pick up and blend the wet paint already on the sheet, and later strokes lie over
  earlier ones. The engine is `MyPaintPainter` in `/opt/tools/rcb_brush.py` (+ `/opt/mypaint`). One continuous contact is one
  **stroke**; paint is permanent (only `s.reset()` clears it).
- The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag of about 0.1 s.

## Target and score
- **The target is this picture**: `/app/target.png` (1024 x 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base), i.e. at world
  x = -0.100 + 0.1136 - Y/1000, y = 0.1136 - X/1000 (m) (`s.geo.mm_to_world(X, Y)`). Image top = the sheet's far edge (+x), image
  left = the robot's left (+y): the same orientation as `s.canvas()` and `canvas_cam`.
- The grader compares the main sheet with the picture: the painting is compared with the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only; if the best shift reaches that limit, the sheet is scored unshifted); the metrics are then taken only inside the sheet's central area, 8 mm in from every edge (the border band is not scored); both blurred (σ = 1 mm); **ΔE** = the CIELAB colour difference (ΔE*ab) per pixel over the region where either has paint (dilated by 2 mm; the picture covers the whole sheet, so: the whole scored area): its mean and 90th percentile; **SSIM** of the lightness L* (σ 1.5 mm windows); **edge correlation** = the correlation of the lightness-gradient magnitudes of the two blurred pictures; **paint IoU** = the painted fraction of the scored area (paint coverage ≥ 0.5); the **number of strokes** on the main sheet (painted contacts). **Success iff mean ΔE ≤ 10.6, p90 ΔE ≤ 17.5, SSIM ≥ 0.52, edge correlation ≥ 0.35, paint IoU ≥ 0.96 and at most 2486 strokes.** `final_reward` = max(0, 1 - mean ΔE / 20) (scaled by 2486 / strokes above 2486). Reported as well: the mean ΔE after a 4 mm blur, the SSIM at a 0.5 mm blur, and per colour region of the picture (the connected areas nearest to one paint, at least 30 mm²) the fraction within ΔE 10: the minimum and the area-weighted mean. The shift found is reported too (`register_dx_mm`, `register_dy_mm`: mm along the picture's columns and rows). `s.score()` returns exactly these metrics for the current sheet: a scoring service (a separate container) replays the actions you have executed since your last `s.reset()` and scores the resulting sheet.

## Process rules
Paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush, pressed for the width you want.
Colouring in or filling areas with a thin line, zigzag or serpentine fills, and contour-offset fills (paths that circle round and
round inside an area) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the
replayed trajectory with two numbers you can check yourself; only painted strokes on the main sheet count (the practice sheet is
free):
- **Paint path budget: `path_mm` ≤ 55600 mm.** `path_mm` is the total length of the brush tip's path while it presses
  on the main sheet with paint (all strokes together, sampled at every physics step). The strokes of our reference solution add up
  to 18503 mm; the budget is 3 times that, rounded up.
- **Strokes are sweeps: `scribble_share` ≤ 0.1.** A stroke's scribble ratio is its length divided by the
  diagonal of its bounding box on the sheet (taken as at least 10 mm): about 1 for a straight or curved sweep,
  2 for a sweep out and back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share`
  is the share of `path_mm` in strokes whose ratio is above 2.5.

**Success iff the picture rule above holds and both process rules hold.** `final_reward` = the continuous score above ×
min(1, 55600 / `path_mm`) × (1 − `scribble_share` when the second rule fails). `s.score()` reports `path_mm`,
`max_path_mm`, `scribble_share`, `scribble_max` (the largest ratio of a stroke), `longest_stroke_mm`, `image_success` (the picture
rule alone), `strict_ok` (the process rules) and `success` (all).

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes; it succeeds if both replays meet the success rule above and end in
exactly the same state. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_brush import Session
s = Session(instance="/app/instance.json")    # a few seconds; builds the scene in the frozen state
s.reset()                          # back to the initial state: blank sheets, dry brush, robot at its start pose (exact)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_tip"])
p["move_tip"](pos, quat_wxyz=None, speed=0.05, settle=0)   # straight-line tip move, one IK solve per control step
p["move_joints"](q7, max_dq=0.03, settle=0); p["hold"](10); p["set_joint_targets"](q7, steps=1)
q, ok, err = s.ik(pos, quat_wxyz=None); s.fk(q7); s.tip_down_quat(yaw)   # kinematics (default orientation: the start pose)
s.tip_pose(); s.joint_positions(); s.press_depth(); s.pen_down()        # measured state
s.wells(); s.sheet_facts()         # the paint wells; the two sheets (centre, size, raster, mm per px)
s.canvas(); s.canvas("practice")   # the exact sheet images, uint8 RGB (row 0 = far edge, col 0 = left edge seen from the base)
s.ink(); s.ink("practice")         # the exact paint coverage, float32 [0, 1] (the score uses >= 0.5)
s.score()                          # the grader's metrics for the main sheet (+ success, final_reward)
s.strokes()                        # realized strokes: sheet, inked, colour, 100 Hz samples (tip x, y, press, ...)
s.brush_state()                    # the paint on the brush now (None = dry)
s.target_image(); s.geo            # the target picture (target.png as an array); the main sheet's frame (mm_to_world, world_to_px, ...)
s.render_frame("canvas_cam")       # RGB uint8 of one camera: canvas_cam, practice_cam, scene_cam, side_cam ("canvas" / "practice": exact)
s.render_grid()                    # cameras + the exact main sheet tiled
s.step(action)                     # one low-level action (7 joint targets, rad) = one control step (1/20 s)
s.record_start(); ...; actions = s.record_stop()    # (T, 7) actions, one row per control step
s.status()                         # score + {'sim_steps', 'n_contacts', 'loaded', 'state_sha', 'n_dips', 'max_tilt_deg_in_contact', ...}
s.replay(actions)                  # resets, replays open-loop, returns status (identical to a fresh process)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
s.camera_info(); s.render_depth("canvas_cam")      # per camera: K, extrinsics, image size, mount (all static); z-depth (m) on
                                                   #   render_frame's pixels, 0 = no reading (geometry only: the paint never shows)
s.robot_spec(); s.kinematics_spec()                # the robot's spec sheet (joint limits, PD gains, rates, tool frame "tip");
                                                   #   what s.kinematics() answers (frames, IK defaults)
s.kinematics({"op": "fk", "q": q7}); s.kinematics({"op": "ik", "targets": {"tip": pose7}, "seed": q7})   # stateless FK / IK (world)
s.joint_velocities(); s.joint_efforts()            # measured joint velocities (rad/s); a PD drive-effort estimate (N m)
s.state_sha(); s.n_steps                           # the state hash the replays compare; control steps since the last reset
s.camera_params("canvas_cam"); p["get_tip_pose"](); p["get_joint_targets"]()   # one camera's calibration; = s.tip_pose(), s.hold_action()
from rcb_brush import quat_mul, quat_slerp, quat_to_mat   # WXYZ quaternion helpers
```
The primitives are deliberately thin (IK moves without collision checking, joint moves, hold); everything else is yours to build.

The grader replays in two fresh processes, each exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_brush.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: z up, table top z = 0, the robot's base at (-0.615, 0, 0), x forward (away from the base), y to the robot's left.
  Quaternions are **WXYZ**. At the start the brush points straight down with the tip at about (0.000, 0.000, 0.108).
- Action (7): panda_joint1..7 absolute joint-position targets (rad), ManiSkill's `pd_joint_pos` controller. `s.hold_action()`
  is the no-op. Control runs at 20 Hz (physics 100 Hz).
- **Your wall-clock budget is 2 h (7200 s)**; there is no step budget. A runaway guard stops an episode at 72000 control steps (1 h
  of simulated time). Everything runs on the CPU except camera rendering.
- The picture is a public-domain painting, Vincent van Gogh, *Irises* (1889; Wikimedia Commons `File:Irises-Vincent van Gogh.jpg`, Public domain), cropped to a square and downscaled to the sheet; libmypaint is ISC, the mypaint-brushes presets CC0 (`/opt/mypaint`).

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included; the `scorer` service is the benchmark's and does not count): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.
