# RoboPaint · lettering · Commendation animates the mind. — frozen instance

You control a simulated **Franka Panda arm holding a pointed flexible dip pen** via Python: ManiSkill 3.0.1 / SAPIEN 3.0.3 physics (PhysX
on the CPU) for the robot; the pen's mark is the ink laid between the two tines, whose spread follows the press depth. **Task (臨摹, copying an
exemplar):** copy the line **Commendation animates the mind.** (engraved English round hand, 1741), shown in the picture `/app/target.png`, onto the main sheet with pen and ink, **in at most 9
strokes**.

This is a *fixed scene instance*: you may reset and retry as many times as you want. Your deliverable is **one replayable
trajectory**, not a general policy.

## The pen, the ink and the sheets
- The pen is a rigid holder with a **pointed flexible steel nib** (two tines split by a slit; no collision; the holder hits
  the paper 6 mm below its surface); the robot's tool point (TCP) is the point. A light touch (a press of up to 1.0 mm below a sheet's surface)
  writes a **hairline 0.4 mm wide**; pressed deeper, the tines spread apart and the line widens **linearly with the press depth,
  up to 2.0 mm at a 3.5 mm press** (fully open; no wider beyond that). The tines spread along the **tool's y axis** (the second
  column of the tip pose's rotation matrix; at the start pose along the writing line, world -y): a pressed stroke is wide
  where the point moves across that axis and stays thin where it moves along it. `s.tip_down_quat(yaw)` turns the pen about the vertical by `yaw` (counter-clockwise as seen by the writer, looking at the sheet with its far edge up).
- **Ink**: the pen starts **dry** (strokes leave no mark). The ink well lies on a plate on the robot's left (+y): centre
  **(x, y) = (-0.100, 0.150)**, radius 20 mm, ink surface **z = 0.028 m** (plate top 0.026 m, rigid). **Dipping** = the tip inside the
  well's circle and below the ink surface: the pen is then inked (it never runs dry). `s.wells()` returns these facts.
- **Sheets** (surface z = **0.020 m**, lying on the board): the **main sheet**, a 227.18 mm square centred at world
  **(-0.100, 0.000)**, is the one that is scored; the **practice sheet**, 227.18 x 99.41 mm centred at **(-0.100, -0.1856)** (the
  robot's right of the main sheet), is for test strokes and is never scored or counted. `s.sheet_facts()`.
- The tip is sampled at every physics step (100 Hz); one continuous contact with a sheet is one **stroke**; ink is permanent (only
  `s.reset()` clears it). The mark model is `PointedPenPainter` in `/opt/tools/rcb_brush.py`.
- The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag of about 0.1 s (2 mm at 2 cm/s).

## Target and score
- **The target is this picture**: `/app/target.png` (1024 x 1024 px, RGB) shows the exemplar at its true size and place on the main
  sheet: the image covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's
  top-left, has its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's
  right, Y towards the robot, origin = the sheet's far-left corner as seen from the robot's base), i.e. at world
  x = -0.100 + 0.1136 - Y/1000, y = 0.1136 - X/1000 (m)
  (`s.geo.mm_to_world(X, Y)`). Image top = the sheet's far edge (+x), image left = the robot's left (+y): the same orientation as
  `s.canvas()` and `canvas_cam`.
- The main sheet is scored against the picture: its **inked area** (ink coverage ≥ 0.5) vs the exemplar's ink in the picture.
  Before scoring, the main sheet is aligned with the picture: your ink is moved by the single translation (no rotation or
  scaling, one shift for the whole sheet, whole pixels, at most 5 mm along each axis) that best matches the picture; every quantity
  below is taken after that shift, which is reported (`register_dx_mm`, `register_dy_mm`; the unshifted IoU as `iou_unregistered`).
  If the best match lies at the 5 mm limit, no shift is applied. **IoU** of the inked areas; **boundary F**: how well
  the edges of your ink match the edges of the exemplar's ink (precision / recall within 1 mm); **region coverage**: the exemplar's ink is
  divided into 52 regions, at most 30 mm each along its strokes; the fraction of each region covered by your ink (the worst
  one counts); **stray ink**: ink more than 1 mm
  away from the exemplar's ink, as a fraction of the exemplar's inked area; the **number of strokes** on the main sheet (inked
  contacts).
  **Success iff IoU ≥ 0.85, boundary F ≥ 0.80, every region covered ≥ 0.75, stray ink
  ≤ 0.04 and at most 9 strokes on the main sheet.** `final_reward` = the IoU (scaled by 9 / strokes if there are more than 9).
  Reported as well: ink precision / recall, missing ink, the mean region coverage. `s.score()` returns exactly these metrics for
  the current sheet: a scoring service (a separate container) replays the actions you have executed since your last `s.reset()` and
  scores the resulting sheet, so a call after a long episode takes as long as that replay.

## Process rules
Letter the exemplar with pen strokes, the way a scribe writes it: each stroke of a letter is a pass of the pen along it, its width
coming from the pen (the pressure on the pointed pen and the direction of travel); going over a stroke again
is fine. Colouring in or filling the letters' shapes, zigzag or serpentine fills (back-and-forth passes across a stroke), and
contour-offset fills are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the
replayed trajectory with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is
free):
- `path_mm`: the total length of the pen tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > 3240 mm and `mark_width_mm` < 0.12 mm** (a long path of thin marks): it
fails the task. Our reference solution writes this exemplar with `path_mm` 1079 mm and `mark_width_mm`
0.41 mm; the limits are 3 times its path (rounded up) and 0.3 times its mark width
(rounded down). A pressed pen, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**Success iff the picture rule above holds and the run is not colouring in.** `final_reward` = the continuous score above, ×
min(1, 3240 / `path_mm`) when it is colouring in. `s.score()` reports `path_mm`, `mark_width_mm`, `max_path_mm`,
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
s.reset()                          # back to the initial state: blank sheets, dry pen, robot at its start pose (exact)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_tip"])
p["move_tip"](pos, quat_wxyz=None, speed=0.05, settle=0)   # straight-line tip move, one IK solve per control step
p["move_joints"](q7, max_dq=0.03, settle=0); p["hold"](10); p["set_joint_targets"](q7, steps=1)
q, ok, err = s.ik(pos, quat_wxyz=None); s.fk(q7); s.tip_down_quat(yaw)   # kinematics (default orientation: the start pose)
s.tip_pose(); s.joint_positions(); s.press_depth(); s.pen_down()        # measured state
s.wells(); s.sheet_facts()         # the ink well; the two sheets (centre, size, raster, mm per px)
s.canvas(); s.canvas("practice")   # the exact sheet images, uint8 RGB (row 0 = far edge, col 0 = left edge seen from the base)
s.ink(); s.ink("practice")         # the exact ink coverage, float32 [0, 1] (the score uses >= 0.5)
s.score()                          # the grader's metrics for the main sheet (+ success, final_reward)
s.strokes()                        # realized strokes: sheet, inked, 100 Hz samples, own ink
s.brush_state()                    # the pen now (privileged): its pose on the paper and whether ink is loaded
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
Wrist note: turning the pen far about the vertical can run joint 7 into its limit on one side; the other way round reaches the
same orientation of the nib (the mark is the same for a pen turned by 180°).

The grader replays in two fresh processes, each exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_brush.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: z up, table top z = 0, the robot's base at (-0.615, 0, 0), x forward (away from the base), y to the robot's left.
  Quaternions are **WXYZ**. At the start the pen points straight down (`s.tip_pose()` gives the tip's position).
- Action (7): panda_joint1..7 absolute joint-position targets (rad), ManiSkill's `pd_joint_pos` controller. `s.hold_action()`
  is the no-op. Control runs at 20 Hz (physics 100 Hz).
- **Your wall-clock budget is 2 h (7200 s)**; there is no step budget. A runaway guard stops an episode at 72000 control steps
  (1 h of simulated time). Everything runs on the CPU except camera rendering.
- The exemplar comes from a public-domain engraved copybook plate (1741): `/app/NOTICE-exemplar.md`.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included; the `scorer` service is the benchmark's and does not count): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.
