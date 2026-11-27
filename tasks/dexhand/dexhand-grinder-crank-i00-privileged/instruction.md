# DexHand · Operate a manual coffee grinder (privileged)

## Task
Hold the coffee grinder steady with one hand, turn its crank by the knob two full turns clockwise (seen from above) with
the other, then let go of the grinder.

## Goal
Success: the crank is turned at least two full turns clockwise (seen from above) relative to the grinder body, net of
any turning back; then both hands are off the grinder, which stands upright on the counter, still, for a second. A
replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The grinder tilts, slides or lifts off its spot, or falls below the counter top.
- The grinder body turns on its spot by more than an eighth of a turn.
- The crank is turned more than a quarter turn the wrong way (counter-clockwise).
- An arm, torso or stand link of the robot touches anything (only the hands may make contact).
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
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a counter (DexHand, MuJoCo).
The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("grinder_crank")                 # default hand model: DEXHAND_HAND or "sharpa"
s = Session("grinder_crank", hand="wuji")    # explicit hand model
s.hand, s.action_dim, s.actuator_names       # selected model, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, stage, crank angle, tilt, slide, contacts ...
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full integration and verdict state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.70 m; the crank axis
is the grinder's own axis (vertical at the start), 0.175 m above its base, and the knob starts at (0.45, -0.08, 0.89) m.
"Clockwise" is seen from above, i.e. a negative rotation about the grinder's +z axis.

### Actions
Each row is one 50 Hz control: the 14 Marvin arm joint targets (radians)
`SHOULDER_PITCH_L_J1_target, SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target, WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`,
then the same seven for the right arm (`..._R_J1_target` ... `..._R_J7_target`), then the finger targets in native
actuator order, in radians, left hand first:

- `sharpa`: 58 values, the 14 arm targets, 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`,
  then 22 right targets `right_thumb_CMC_FE` ... `right_pinky_DIP`. The left Sharpa Wave is the right model reflected in
  y.
- `wuji`: 54 values, the same 14 arm targets, 20 left Wuji Hand 2.2 targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the manufacturer's right hand `r_wuji_r_THJ0..3` ...
  `r_wuji_r_LFJ0..3`.

Arm servos: kp 700 N m/rad, kv 48 N m s/rad, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity
compensation. Each hand sits rigidly on its arm's flange (bodies `right_wrist_stage` / `left_wrist_stage`: fingers along
the flange +z, palm normal +x, thumb +y for the right hand). No IK primitive is supplied. Every target must lie within
`s.model.actuator_ctrlrange`; the frozen start pose (arm joints; open fingers) is in `task.json` (`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand of the same model
on each wrist: a right hand and a left hand. The arm joints and the fingers are position actuated in the physics engine
under native force bounds; holding the grinder and turning the crank require physical contact. The controller runs at 50
Hz, with ten 2 ms physics substeps. The stand faces +x behind the counter on the floor (z = -0.1 m), its base origin at
(-0.085, 0, 0) m (shoulders 1.121 m above it, at y = +-0.2215 m); any contact of an arm, torso or stand link with
anything ends the episode (`robot_collision`).

The left hand counterholds the grinder, the right hand turns the crank.

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
