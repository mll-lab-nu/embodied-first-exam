# DexHand · Serve a pancake from a frying pan with a spatula (privileged)

## Task
Serve the pancake from the frying pan onto the plate with the kitchen turner (a spatula).

## Goal
Success: in this order, the pancake rides lifted and roughly level on the turner's blade, touching nothing else, for a
moment; it is carried over the plate on the blade; then it lies flat in the middle of the plate, touching only the
plate, with the turner drawn back from it, and is still for a second. A replay ends as soon as the task is done; later
rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The pancake touches the counter top or the floor, falls freely or drops below the counter top.
- Any part of the robot touches the pancake.
- The turner touches the floor, falls out of the hand or drops below the counter top.
- The pan or the plate is moved or tipped.
- The pancake, the pan, the plate or the turner leaves the work area.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` and `/app/output/gen.py`, the script that produced it. The archive holds a
finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, at most 3000 rows, plus the
`hand` member; `s.save_trajectory` writes both. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (the right arm and hand do the
task; the left arm stays parked), at a counter (DexHand, MuJoCo). The scene is one fixed instance. You have the full
simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("pancake_serve")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("pancake_serve", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names     # selected hand, row width and exact row order
s.hold_action()                            # current motor targets
s.model.actuator_ctrlrange                 # native target limits
s.model, s.data                            # privileged MuJoCo model and state
s.features()                               # pancake pose, contacts, plate distance, withdrawal, stage, failure details
s.status()                                 # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                # twenty 1 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)              # full simulator + verdict state, for search
s.render_frame("overview")                 # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                  # exact frozen reset
s.replay(actions)                          # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.85 m, the pan rests
centred at (0.50, 0.10) and the plate at (0.76, 0.18).

### Actions
Each row is one 50 Hz control with a position target for every actuator, in model order (`s.actuator_names`):

- columns 0-6: left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (each name + `_target`); columns 7-13: the right arm `..._R_J1` to `..._R_J7`;
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers (`l_wuji_*`, vendor order), columns 34-53 the right
  Wuji fingers (`r_wuji_*`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start open, the right arm holding its hand above
the counter and the left arm parked (`task.json` `initial_qpos` and `initial_targets` per hand, a settled state);
`s.hold_action()` at reset returns the start targets and keeps that pose.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand on
each wrist; the right arm and hand do the task and the left arm stays parked beside the torso. Every arm and finger
joint is a position servo in the physics engine under native force bounds; arm servos have stiffness 700 N m/rad,
damping 48 N m s/rad and no gravity compensation (a held target sags by about 1 cm at the hand under load unless your
targets account for it). The turner is held only by finger and palm contact, and the pancake moves only through contact
with the turner, the pan and the plate. The controller runs at 50 Hz, with twenty 1 ms physics substeps per control.
World frame: metres and radians, +z up, +x forward from the robot stand, +y to the robot's left.

### Scene
A 22 cm non-stick frying pan (0.90 kg, free on the counter) holds one cooked pancake (0.06 kg, about 140 mm across and
9.5 mm thick); an empty ceramic plate (0.48 kg, free, rim radius 0.128 m) stands beside it on an oak counter whose top
is at z = 0.85 m; the pan rests centred at (0.50, 0.10) and the plate at (0.76, 0.18). The OXO flexible kitchen turner
(0.15 kg) rests on the counter in front of the plate, at about (0.76, -0.30, 0.878) m with its handle toward -y (handle
end and blade base on the counter, the handle 16 to 30 mm above it). Friction is high for the hand on the turner (1.2)
and for the pancake on the plate (0.60), lower for the pancake on the pan (0.45) and low for the pancake and the pan on
the blade (0.20); objects on the counter have 0.7.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
