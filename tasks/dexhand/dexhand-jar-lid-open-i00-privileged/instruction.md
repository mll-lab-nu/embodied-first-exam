# DexHand · Open a jam jar and set the lid aside (privileged)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a worktop (DexHand, MuJoCo). Open the jam jar with the right hand and set its lid aside on the
worktop: a filled glass jam jar stands upright on the worktop with its red twist-off steel lid closed. The scene is one
fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: in this order: the lid is unscrewed (turned counter-clockwise, seen from above, until its lugs clear the
thread) while it still sits on the jar; it is lifted clear of the jar; then it stands upright on the worktop away from
the jar, the hand off the lid and the jar, the jar upright on the worktop, and both are still for a second. A partial
sequence never counts. A replay ends as soon as the task is done; later rows are not run.

The episode ends at once as a failure if the jar tips, slides or is lifted; the lid touches the worktop before it has
been lifted clear; the lid is dropped from the air (there is no time to catch it; a lid that tips over or falls flat on
the worktop has not dropped); the jar or the lid touches the floor, falls below the worktop top or leaves the worktop or
the work area; the lid is forced up through the thread; the parked left arm or the left hand touches the jar or the lid;
or the physics becomes unstable. Later actions cannot undo a failure.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actuator targets count: changing `s.data` or the scene while you develop changes nothing in the replay.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("jar_lid_open")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("jar_lid_open", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, lid turn, clearance, contacts, tilts, speeds, failure details
s.status()                                # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the full physics and verdict state
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup", "side" and "wide"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may observe everything in privileged mode: the MuJoCo model and state (`s.model`, `s.data`), `s.features()` (stage,
unwrapped lid turn, lid clearance above the rim, contacts, tilts, speeds, failure details) and renders from the
`overview`, `closeup`, `side` and `wide` cameras. The world frame has z up; lengths are in metres and angles in radians.
The jar stands at (-0.22, -0.08) on the worktop, whose top is at z = 0.75 m; the lid starts closed with its origin at z
= 0.8509 m.

### Actions
Each row is one 50 Hz control and holds a position target for every actuator, in radians:

- `sharpa` (58 values): 0-6 the left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (actuators `<joint>_target`; keep them at the parked start values), 7-13 the same right-arm joints (`..._R_J1` to
  `..._R_J7`), 14-35 the 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`, 36-57 the 22 right
  Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets, 14-33 the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, 34-53 the 20 right ones
  (`r_wuji_r_...`, same order).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`); the right hand's frame is the body `wrist_stage` on the right flange (fingers along its +z, palm
normal +x, thumb +y), which forward kinematics of the arm joints places in the world.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist (the robot stands behind the worktop, its base centre at x = -0.56, y = 0.08 on the floor, facing +x;
shoulders at z = 1.121 m (1.221 m above the floor)). The left arm stays parked beside the torso with its hand open; the
task is done by the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine
under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a
held target sags under the arm's weight unless your targets account for it). Turning, lifting, carrying and releasing
the lid require physical contact, and the jar is held by nothing but its own weight and friction on the worktop. The
controller runs at 50 Hz, with ten 2 ms physics substeps. At reset the right hand hangs open, palm down, about 0.1 m
above the lid with its fingers along +x; the left arm is at its parked pose.

### Scene
The worktop top is at z = 0.75 and spans |x| <= 0.45, |y| <= 0.58 (world frame, metres, z up, +x forward from the
robot). The filled 297 ml glass jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.86) stands upright centred at
x = -0.22, y = -0.08; its red 64.8 mm twist-off steel lid weighs 32 g. Jar and lid are free rigid bodies.

## Others
- Nothing holds the jar: it stands on its own weight, and its glass-on-worktop friction resists only about 0.13 N m of
  twisting torque, so turn the lid without turning, sliding or tipping the jar. Any robot part touching the jar or the
  lid counts as the hand touching it.
- The closure is a lug thread made of contact geometry: four inclined ramps on the jar neck hold four lugs inside the
  lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive about +z,
  relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the
  gaps between the ramps (a turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without
  lifting, the lugs run into the next ramps, and turning clockwise from closed tightens and jams. The lid is lightly
  closed: no vacuum, seal adhesion or tightening torque.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
