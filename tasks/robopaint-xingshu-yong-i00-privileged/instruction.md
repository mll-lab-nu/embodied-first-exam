# RoboPaint · 行书 臨帖 · 永 — frozen instance

You control a simulated **Franka Panda arm holding a large Chinese writing brush (毛笔)** via Python: ManiSkill 3.0.1 / SAPIEN 3.0.3
physics (PhysX on the CPU) for the robot; the brush's mark is a dynamic virtual brush model of a real brush (below).
**Task (臨帖):** copy the exemplar character **永** in running script (行书), shown in the picture `/app/target.png`, onto the main
sheet with brush and ink, **in at most 6 strokes**.

This is a *fixed scene instance*: you may reset and retry as many times as you want. Your deliverable is **one replayable
trajectory**, not a general policy.

## The brush, the ink and the sheets
- The brush is a rigid handle with a **30 mm soft tuft** (no collision); the robot's tool point (TCP) is the tip of the unbent
  tuft. Hold the brush vertical (as at the start); the model uses the tip's position and ignores tilt (the maximum tilt is reported).
- **Ink**: the brush starts **dry** (strokes leave no mark). The ink stone lies on a plate on the robot's left (+y): centre
  **(x, y) = (-0.100, 0.150)**, radius 20 mm, ink surface **z = 0.028 m** (plate top 0.026 m, rigid). **Dipping** = the tip inside the
  stone's circle and below the ink surface: the brush is then inked (it never runs dry) and **restored**: the hairs are gathered
  back to a point (no spread, no bend). `s.wells()` returns these facts.
- **Sheets** (surface z = **0.020 m**, lying on the board): the **main sheet**, a 227.18 mm square centred at world
  **(-0.100, 0.000)**, is the one that is scored; the **practice sheet**, 227.18 x 99.41 mm centred at **(-0.100, -0.1856)** (the
  robot's right of the main sheet), is for test strokes and is never scored or counted. `s.sheet_facts()`.
- **How the brush marks the paper** (the dynamic brush of Wang, Chen, Deng, Hutchinson, Dellaert, IROS 2020, arXiv 1911.08002,
  re-implemented; the code is `WangBrush` in `/opt/tools/rcb_brush.py`): wherever the tip is below a sheet's surface over the
  sheet with ink on the brush, the pressed hairs leave a mark. The mark is **not a disc under the tip**: its width and its length
  (a tapering "drag" tail) grow with the press depth (a light touch makes a hairline, about 15 mm press makes a mark about 17 mm
  wide; deeper presses do not spread it further, and the handle hits the paper at 30 mm); the part of the tuft on the paper **stays
  put until the handle has moved a press-dependent distance away (up to about 11 mm), then is dragged behind it**, so the mark
  trails the handle and cuts inside turns; lifting releases the bend (the mark's root snaps back under the handle). The state of
  the hairs carries over between strokes until the next dip. The tip is sampled at every physics step (100 Hz); one continuous
  contact with a sheet is one **stroke**; ink is permanent (only `s.reset()` clears it).
- The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag of about 0.1 s (2 mm at 2 cm/s).

## Target and score
- **The target is this picture**: `/app/target.png` (1024 x 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base), i.e. at world
  x = -0.100 + 0.1136 - Y/1000, y = 0.1136 - X/1000 (m) (`s.geo.mm_to_world(X, Y)`). Image top = the sheet's far edge (+x), image
  left = the robot's left (+y): the same orientation as `s.canvas()` and `canvas_cam`.
- Before scoring, the main sheet is **aligned with the picture**: your ink is moved by the single translation (no rotation or
  scaling, one shift for the whole sheet; whole pixels of 0.22 mm, at most 5 mm along each axis) that overlaps the exemplar's ink
  best, and every quantity below is taken after that shift (reported as `register_dx_mm`, `register_dy_mm`); if the best overlap
  lies at the 5 mm limit, no shift is applied.
- The main sheet is scored against the picture: its **inked area** (ink coverage ≥ 0.5) vs the exemplar's ink in the picture:
  **IoU**; **boundary F** (how well the edges of your ink match the edges of the exemplar's ink, precision / recall within 1 mm);
  **region coverage** (the exemplar's ink is divided into 9 regions; the fraction of each region covered by your ink; the
  worst one counts; `min_stroke_coverage` in the metrics); **stray ink**
  (ink more than 1 mm away from the exemplar's ink, as a fraction of the exemplar's inked area); the **number of strokes** on the
  main sheet (inked contacts). **Success iff IoU ≥ 0.80, boundary F ≥ 0.75, every region covered ≥ 0.80, stray ink ≤ 0.04
  and at most 6 strokes (continuous brush contacts) on the main sheet.** `final_reward` = the IoU (scaled by 6 / strokes if there are more than 6).
  Reported as well: ink precision / recall, missing ink, the mean region coverage. `s.score()` returns exactly these metrics for
  the current sheet: a scoring service (a separate container) replays the actions you have executed since your last `s.reset()` and
  scores the resulting sheet, so a call after a long episode takes as long as that replay.

## Process rules
Write the character with brush strokes, the way a person writes it: each stroke of the exemplar is written along its length,
with the brush pressed for the stroke's width (vary the press where the width changes); going over a stroke again is fine.
Colouring in or filling the shapes, zigzag or serpentine fills, and contour-offset fills (paths that go round and round inside a
shape) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the replayed
trajectory with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is free):
- `path_mm`: the total length of the brush tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > 1450 mm and `mark_width_mm` < 2.25 mm** (a long path of thin marks): it
fails the task. Our reference solution writes this exemplar with `path_mm` 483 mm and `mark_width_mm`
7.53 mm; the limits are 3 times its path (rounded up) and 0.3 times its mark width
(rounded down). A pressed brush, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**Success iff the picture rule above holds and the run is not colouring in.** `final_reward` = the continuous score above, ×
min(1, 1450 / `path_mm`) when it is colouring in. `s.score()` reports `path_mm`, `mark_width_mm`, `max_path_mm`,
`min_mark_width_mm`, `colour_in`, `image_success` (the picture rule alone), `strict_ok` (the process rule) and `success` (both);
`s.strokes()` holds each stroke's samples and its own mark.

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
q, ok, err = s.ik(pos, quat_wxyz=None); s.fk(q7); s.tip_down_quat(yaw)   # kinematics (default orientation: brush straight down)
s.tip_pose(); s.joint_positions(); s.press_depth(); s.pen_down()        # measured state
s.wells(); s.sheet_facts()         # the ink stone; the two sheets (centre, size, raster, mm per px)
s.canvas(); s.canvas("practice")   # the exact sheet images, uint8 RGB (row 0 = far edge, col 0 = left edge seen from the base)
s.ink(); s.ink("practice")         # the exact ink coverage, float32 [0, 1] (the score uses >= 0.5)
s.score()                          # the grader's metrics for the main sheet (+ success, final_reward)
s.strokes()                        # realized strokes: sheet, inked, 100 Hz samples (tip x, y, press, brush w, d, o, θ, root x, y), own ink
s.brush_state()                    # the brush model's state now: width, drag, offset, orientation, root, ink loaded
s.target_image(); s.geo            # the target picture (target.png as an array); the main sheet's frame (mm_to_world, world_to_px, ...)
s.render_frame("canvas_cam")       # RGB uint8 of one camera: canvas_cam, practice_cam, scene_cam, side_cam ("canvas" / "practice": exact)
s.render_grid()                    # cameras + the exact main sheet tiled
s.step(action)                     # one low-level action (7 joint targets, rad) = one control step (1/20 s)
s.record_start(); ...; actions = s.record_stop()    # (T, 7) actions, one row per control step
s.status()                         # score + {'sim_steps', 'n_contacts', 'loaded', 'state_sha', 'n_dips', 'max_press_m', ...}
s.replay(actions)                  # resets, replays open-loop, returns status (identical to a fresh process)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
s.camera_info(); s.render_depth("canvas_cam")      # per camera: K, extrinsics, image size, mount (all static); z-depth (m) on
                                                   #   render_frame's pixels, 0 = no reading (geometry only: the ink never shows)
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
  Quaternions are **WXYZ**. At the start the brush points straight down with the tip at about (0.000, 0.000, 0.093).
- Action (7): panda_joint1..7 absolute joint-position targets (rad), ManiSkill's `pd_joint_pos` controller. `s.hold_action()`
  is the no-op. Control runs at 20 Hz (physics 100 Hz).
- **Your wall-clock budget is 2 h (7200 s)**; there is no step budget. A runaway guard stops an episode at 72000 control steps (1 h
  of simulated time). Everything runs on the CPU except camera rendering.
- The exemplar picture is derived from a public-domain historical work of running-script calligraphy (Wikimedia Commons,
  PD-Art); rendered by robot-coding-bench (RoboPaint): `/app/NOTICE-exemplar.md`.
