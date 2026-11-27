# RoboPaint · 草书 臨帖 · 真 (privileged)

## Task
Copy the character 真 (cursive script, 草书) in `/app/target.png` onto the main sheet with brush and ink, in at most 3
strokes.

## Goal
Success: the ink on the main sheet matches the exemplar's writing character for character (every stroke inked along its
whole length and fully covered, its edges where the exemplar's are, almost no ink anywhere else), you used at most 3
strokes as the process rules count them, and the process rules below hold; a small shift of the whole writing does not
matter. Your trajectory is replayed from the fixed start. What counts is the state after its last action.

You are scored on how closely your ink matches the exemplar's.

Write with brush strokes, the way a person writes: each stroke of the exemplar is written along its length, with the
brush pressed for the stroke's width; going over a stroke again is fine. These fail the task even when the sheet matches
the picture: colouring in or filling the shapes, zigzag or serpentine fills, and fills that go round and round inside a
shape. The exact checks are under Process rules in Robot Interface.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`; it is replayed open-loop
from the frozen start and succeeds if the replay meets the rules above. Also leave the script that produced it at
`/app/output/gen.py`. Save a valid trajectory early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A simulated Franka Panda arm holding a large Chinese writing brush (毛笔). The scene is one fixed instance. You have the
full simulator to develop with; you hand in one replayable trajectory.

### Session
`rcb_brush`, already installed (`python` from any directory):
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
s.replay(actions)                  # resets, replays open-loop, returns status (as the grader replays it)
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
The primitives are deliberately thin (IK moves without collision checking, joint moves, hold); everything else is yours
to build.

This command replays a trajectory as the grader does (run it to self-check):
```bash
python /opt/tools/rcb_brush.py replay --instance /app/instance.json --traj /app/output/trajectory.npz
```

### Actions
An action is 7 values: panda_joint1..7 absolute joint-position targets (rad), ManiSkill's `pd_joint_pos` controller;
`s.hold_action()` is the no-op. Control runs at 20 Hz (physics 100 Hz). World frame: z up, table top z = 0, the robot's
base at (-0.615, 0, 0), x forward (away from the base), y to the robot's left. Quaternions are WXYZ. At the start the
brush points straight down with the tip at about (0.000, 0.000, 0.093).

### The brush, the ink and the sheets
- The brush is a rigid handle with a 30 mm soft tuft (no collision); the robot's tool point (TCP) is the tip of the
  unbent tuft. Hold the brush vertical (as at the start); the model uses the tip's position and ignores tilt (the
  maximum tilt is reported).
- Ink: the brush starts dry (strokes leave no mark). The ink stone lies on a plate on the robot's left (+y): centre (x,
  y) = (-0.100, 0.150), radius 20 mm, ink surface z = 0.028 m (plate top 0.026 m, rigid). Dipping means having the tip
  inside the stone's circle and below the ink surface. The brush is then inked (it never runs dry) and restored: the
  hairs are gathered back to a point, with no spread and no bend. `s.wells()` returns these facts.
- Sheets (surface z = 0.020 m, lying on the board): the main sheet, a 227.18 mm square centred at world (-0.100, 0.000),
  is the one that is scored; the practice sheet, 227.18 x 99.41 mm centred at (-0.100, -0.1856) (the robot's right of
  the main sheet), is for test strokes and is never scored or counted. `s.sheet_facts()`.
- How the brush marks the paper: wherever the brush has ink and its tip is below a sheet's surface over the sheet, the
  pressed hairs leave a mark. The model is the dynamic brush of Wang, Chen, Deng, Hutchinson, Dellaert (IROS 2020, arXiv
  1911.08002), re-implemented; the code is `WangBrush` in `/opt/tools/rcb_brush.py`. The mark is not a disc under the
  tip. Its width and its length (a tapering "drag" tail) grow with the press depth: a light touch makes a hairline, and
  a press of about 15 mm makes a mark about 17 mm wide. Deeper presses do not spread it further, and the handle hits the
  paper at 30 mm. The part of the tuft on the paper stays put until the handle has moved a press-dependent distance away
  (up to about 11 mm); then it is dragged behind the handle, so the mark trails the handle and cuts inside turns.
  Lifting releases the bend: the mark's root snaps back under the handle. The state of the hairs carries over between
  strokes until the next dip. The tip is sampled at every physics step (100 Hz); one continuous contact with a sheet is
  one stroke; ink is permanent (only `s.reset()` clears it).
- The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag of about 0.1 s (2 mm at 2
  cm/s).

### The target picture
`/app/target.png` (1024 x 1024 px, RGB) shows the exemplar at its true size and place on the main sheet: the image
covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's top-left, has
its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024. X runs to the robot's
right and Y towards the robot; the origin is the sheet's far-left corner as seen from the robot's base. In the world
frame that is x = -0.100 + 0.1136 - Y/1000, y = 0.1136 - X/1000 (m) (`s.geo.mm_to_world(X, Y)`). Image top = the sheet's
far edge (+x), image left = the robot's left (+y): the same orientation as `s.canvas()` and `canvas_cam`.

### Process rules
The grader checks the process rules in Goal on the replayed trajectory with two numbers you can compute yourself; only
inked strokes on the main sheet count (the practice sheet is free):
- `path_mm`: the total length of the brush tip's path while it presses on the main sheet with ink (all strokes together,
  sampled at every physics step);
- `mark_width_mm`: the average width of your marks. It is the area each stroke inks on its own, summed over the strokes
  and divided by `path_mm`; a stroke's own area is its own mark where ink coverage is ≥ 0.5, and where different strokes
  overlap, each counts its own.

Colouring in = `path_mm` > 1610 mm and `mark_width_mm` < 1.75 mm (a long path of thin marks): it fails the task. Both of
these are fine: a pressed brush keeps the marks wide enough, even when it goes over a stroke again, and a light hand on
a short path stays under the path limit. The stroke cap counts strokes as they are written, not contacts (this refines
"one continuous contact is one stroke" above). A contact is cut into two strokes wherever the brush moves more than 5 mm
along the main sheet without marking it (its mark narrower than 0.1 mm: a press too light to ink), and a stroke longer
than 1590 mm of path counts as one stroke per started 1590 mm. So pieces joined by a touch too light to ink are separate
strokes, and one contact held down for a long time to write and re-write counts as several. A stroke written with the
brush down and lifted at its end counts as one. Strokes are sweeps: at most 10 % of `path_mm` may lie in strokes whose
path is longer than 12 times the diagonal of their bounding box (the diagonal taken as at least 10 mm). Back-and-forth,
zigzag, spiral or looping fills inside one stroke fail. Breaking a process rule fails the task. `s.score()` reports
`path_mm`, `mark_width_mm`, `max_path_mm`, `min_mark_width_mm`, `colour_in`, `n_strokes_counted`, `n_marked_pieces`,
`longest_counted_stroke_mm`, `max_stroke_path_mm`, `strokes_counted_ok`, `scribble_share`, `scribble_ok`,
`image_success` (the picture rule alone), `strict_ok` (the process rules) and `success` (both); `s.strokes()` holds each
stroke's samples (the mark's width is the fourth column, in m) and its own mark.

The score (`final_reward`, 0 to 1) is how well your ink overlaps the exemplar's (1 = the same); it is scaled down above
the stroke cap and when a process rule fails. `s.score()` returns the grader's metrics for the current sheet, `success`
and `final_reward` included. A scoring service replays the actions you have executed since your last `s.reset()` and
scores the resulting sheet, so a call after a long episode takes as long as that replay.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 12 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (3 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Steps: no step budget. A runaway guard stops an episode at 72000 control steps (1 h of simulated time).
- Resets: as many as you like (`s.reset()`: blank sheets, a dry brush, the robot at its start pose, exact).
