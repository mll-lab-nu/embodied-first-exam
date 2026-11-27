# RoboPaint · oil painting from a reference · Mona Lisa (after Leonardo) (privileged)

## Task
Paint the picture in `/app/target.png` (a square crop of Leonardo da Vinci's Mona Lisa) onto the main sheet with the oil
paints, in at most 2507 strokes.

## Goal
Success: the main sheet looks like the picture (the same colours in the same places, the same lights and darks and
edges, and paint only where the picture has paint), you used at most 2507 strokes, and the process rules below hold; a
small shift of the whole painting does not matter. Your trajectory is replayed from the fixed start. What counts is the
state after its last action.

You are scored on how close your colours are to the picture's.

Paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush. These fail the task
even when the sheet matches the picture: colouring in or filling areas with a thin line, zigzag or serpentine fills, and
fills that circle round and round inside an area. The exact checks are under Process rules in Robot Interface.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`; it is replayed open-loop
from the frozen start and succeeds if the replay meets the rules above. Also leave the script that produced it at
`/app/output/gen.py`. Save a valid trajectory early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A simulated Franka Panda arm holding an oil-paint brush. The scene is one fixed instance. You have the full simulator to
develop with; you hand in one replayable trajectory.

### Session
`rcb_brush`, already installed (`python` from any directory):
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
s.replay(actions)                  # resets, replays open-loop, returns status (as the grader replays it)
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
brush points straight down with the tip at about (0.000, 0.000, 0.108).

### The brush, the paints and the sheets
- The brush is a rigid handle with a 15 mm soft tuft (no collision). The handle hits the paper when the tip is 15 mm
  below the paper's surface. The robot's tool point (TCP) is the tuft's tip. Hold the brush vertical (as at the start).
- Paints (the picture's colours, premixed): 16 wells on a plate on the robot's left (+y), in three rows, radius 9 mm,
  paint surface z = 0.028 m (plate top 0.026 m, rigid); `s.wells()` gives each well's name, colour and centre. Dipping
  means having the tip inside a well's circle and below the paint surface. The brush is then loaded with that paint on a
  fresh brush: the previous paint is gone, nothing mixes on the palette, and it never runs dry. The brush starts dry.
- Sheets (surface z = 0.020 m): the main sheet, a 227.18 mm square centred at world (-0.100, 0.000), is scored; the
  practice sheet, 227.18 x 99.41 mm centred at (-0.100, -0.1856), is for test strokes and is never scored or counted.
- How the paint goes on: at every physics step (100 Hz) the tip over a sheet is one motion event for libmypaint, with
  the mypaint-brushes preset `tanda/oil-03-paint` made pointed. The dab size is scaled to the paper; the preset's random
  dab offset and tracking noise follow the pressure like the dab size, so a light press draws a thin line; the frozen
  preset is the instance's `brush.preset_json`. The result is a wet oil paint whose mark depends on the pressure, the
  speed, the direction (the elliptical dabs follow it) and the engine's own smudging and jitter (deterministic). The
  pressure is press depth / 15 mm: straight strokes are about 2 mm wide at a 1.25 mm press, 2.5 mm at 1.5 mm, 3 mm at 2
  mm, 4.2 mm at 3 mm, 6 mm at 4 mm, 8 mm at 5 mm and 11 mm from 6 mm on; a lighter press thins and fades the line.
  Strokes pick up and blend the wet paint already on the sheet, and later strokes lie over earlier ones. The engine is
  `MyPaintPainter` in `/opt/tools/rcb_brush.py` (+ `/opt/mypaint`). One continuous contact is one stroke; paint is
  permanent (only `s.reset()` clears it).
- The arm is position-controlled (PD, 20 Hz targets): a moving target is followed with a lag of about 0.1 s.

### The target picture
`/app/target.png` (1024 x 1024 px, RGB) shows the exemplar at its true size and place on the main sheet: the image
covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's top-left, has
its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024. X runs to the robot's
right and Y towards the robot; the origin is the sheet's far-left corner as seen from the robot's base. In the world
frame that is x = -0.100 + 0.1136 - Y/1000, y = 0.1136 - X/1000 (m) (`s.geo.mm_to_world(X, Y)`). Image top = the sheet's
far edge (+x), image left = the robot's left (+y): the same orientation as `s.canvas()` and `canvas_cam`.

### Process rules
The grader checks the process rules in Goal on the replayed trajectory with two numbers you can check yourself; only
painted strokes on the main sheet count (the practice sheet is free):
- Paint path budget: `path_mm` ≤ 69900 mm. `path_mm` is the total length of the brush tip's path while it presses on the
  main sheet with paint (all strokes together, sampled at every physics step).
- Strokes are sweeps: `scribble_share` ≤ 0.1. A stroke's scribble ratio is its length divided by the diagonal of its
  bounding box on the sheet (the diagonal taken as at least 10 mm). It is about 1 for a straight or curved sweep, 2 for
  a sweep out and back along the same line, and more for a zigzag, a back-and-forth fill, a spiral or a loop.
  `scribble_share` is the share of `path_mm` in strokes whose ratio is above 2.5.

Breaking a process rule fails the task. `s.score()` reports `path_mm`, `max_path_mm`, `scribble_share`, `scribble_max`
(the largest ratio of a stroke), `longest_stroke_mm`, `image_success` (the picture rule alone), `strict_ok` (the process
rules) and `success` (all).

The score (`final_reward`, 0 to 1) is higher the closer your colours are to the picture's; it is scaled down above the
stroke cap and when a process rule fails. `s.score()` returns the grader's metrics for the current sheet, `success` and
`final_reward` included. A scoring service replays the actions you have executed since your last `s.reset()` and scores
the resulting sheet.

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
- Steps: no step budget; a runaway guard stops an episode at 72000 control steps (1 h of simulated time).
- Resets: as many as you like (`s.reset()`: blank sheets, a dry brush, the robot at its start pose, exact).
