# DexHand · Unfold a folding sweater dryer and stand it on its legs (privileged)

## Task
Set up the folding sweater dryer on the kitchen counter with the dexterous hand.

## Goal
Success: the two halves are opened flat and all four legs are open; the rack stands upright on its four feet with no
other part on the counter; then the hand has let go and the rack stands still for a second. A replay ends as soon as the
task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The rack is dropped.
- The rack falls below the counter top, leaves the counter or is lifted far above it.
- The rack touches the floor or the counter cabinet.
- Once standing, the rack falls over or folds back up.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage (no arm), at a kitchen counter (DexHand, MuJoCo). The scene is one fixed
instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("drying_rack_unfold")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("drying_rack_unfold", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # fold and leg angles, tilt, foot/hand contacts, rack speeds, stage
s.status()                                      # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save and restore the full episode state (search, planning)
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "side", "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians.

### Actions
Each row is one 50 Hz control step. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion).
The three prismatic joints are offsets of the hand mount from the stage origin (0.62, 0, 0.75) m along the world axes
(ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0] m; rx and rz [-3.3, 3.3], ry [-1.6, 1.6] rad). At zero rotation
the hand hangs palm down with the fingers along +x and the thumb toward +y. The finger targets follow in native actuator
order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets (the hand 0.3 m
to the -y side of the stage origin, 0.45 m above the counter, fingers open); the frozen start pose of each hand is in
`task.json` (`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Both hands
hang from the same six-axis wrist stage (origin above the counter), with the same wrist joints, ranges, gains and start
targets.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, turning and releasing the rack require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are offsets of the hand mount from the stage origin (0.62, 0, 0.75) m
along the world axes (ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]); `wrist_rx, wrist_ry, wrist_rz` are serial
XYZ joint angles (radians; rx and rz [-3.3, 3.3], ry [-1.6, 1.6]); at zero rotation the hand hangs palm down with the
fingers along +x and the thumb toward +y.

### Scene
The rack is a folding sweater dryer: two rectangular frame halves (each 0.33 m x 0.65 m, 0.205 kg, tube rims, end poles
and corner housings; the woven net between the rims is drawn only and has no collision) joined by a passive pole hinge
on the two side rims (`fold_hinge`: 0 rad = open flat, pi rad = folded; damping 0.001 N m s/rad, dry friction 0.0005 N
m). Each half carries two offset legs (0.025 kg, 0.098 m long, ball foot) on passive hinges `fixed_leg_l_hinge`,
`fixed_leg_r_hinge`, `moving_leg_l_hinge`, `moving_leg_r_hinge` (0 rad = folded flat against the frame, 1.745 rad = 100
degrees = open stop; damping 0.03 N m s/rad, dry friction 0.003 N m). There is no latch: an open leg stays open because
its stop is 10 degrees past vertical, so the weight of the standing rack presses it onto the stop. The rack is a free
body of 0.51 kg. It starts fully folded and stored underside up on the counter (the legs of both halves are sandwiched
between them). The counter top is at z = 0.75 m and spans x in [-0.13, 1.37] m, y in [-0.48, 0.48] m; the folded rack
lies near (0.30, 0.0). Geometry, masses and contact parameters are in `/opt/tools/scene.py` and `/opt/tools/task.json`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
