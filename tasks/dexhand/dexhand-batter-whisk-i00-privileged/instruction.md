# DexHand · Whisk batter in a bowl, drain and set the whisk down (privileged)

## Task
Pick up the balloon whisk, whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the
counter.

## Goal
Success: in this order, the whisk is picked up and held clear of the bowl and the counter; its head circles the bowl at
least five full times inside the batter (leaving the batter before that starts the count again); it hangs head-down over
the bowl for a moment to drain; then it is laid down roughly flat on the counter, away from the bowl, and lies there
still and untouched for a second. A replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The bowl tips, slides or lifts.
- After the pickup, the whisk is dropped.
- Before it is laid down, the whisk touches the counter or is out of the hand for more than a moment.
- Once laid down, the whisk is tossed rather than let go on the counter.
- The bowl or the whisk touches the floor, falls below the counter top or leaves the work area.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 4000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a counter with a steel bowl of
batter (DexHand, MuJoCo). The scene is one fixed instance. You have the full simulator to develop with; you hand in a
trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("batter_whisk")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("batter_whisk", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, pickup/revolutions/drain/hold counters, contacts, bowl tilt/slide
s.status()                                # success, done, reason, steps, stage, total_stages (5)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the simulation and verdict state (planning)
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The counter top is at z = 0.68 m (front edge x = 0.25 m), the bowl origin (its outer bottom) starts at (0.58, 0.0,
0.6805) m, its rim is 78 mm above that origin; the whisk frame has its origin at the wire tip and +z along the handle
(handle from 230 mm to 345 mm); at reset the wire tip is at about (0.576, -0.005, 0.813) m and the handle points down to
the counter toward (-0.30, -0.88, -0.36) (`task.json` `reset_state`).

### Actions
Each row is one 50 Hz control with a position target for every actuator, in model order (`s.actuator_names`):

- columns 0-6: left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (each name + `_target`); columns 7-13: the right arm `..._R_J1` to `..._R_J7`;
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers (`l_wuji_*`, vendor order), columns 34-53 the right
  Wuji fingers (`r_wuji_*`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start open above the counter with the arms in a
ready pose (`task.json` `reset_state[<hand>]`: joint positions and start targets); `s.hold_action()` at reset keeps that
pose. The whisk does not start in a hand: it rests against the bowl rim with its handle end on the counter. The left
hand may steady the bowl (for example while the right hand lifts the whisk off its rim).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand on
each wrist. Every arm and finger joint is a position servo in the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags by about 1 cm at the
hand under load unless your targets account for it). The bowl and the whisk move only through contact with the hands,
the arms, each other and the counter. The controller runs at 50 Hz, with ten 2 ms physics substeps. World frame: metres
and radians, +z up, +x forward from the robot stand, +y to the robot's left.

The right arm/hand picks up and uses the whisk; the left arm/hand may steady the bowl.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
