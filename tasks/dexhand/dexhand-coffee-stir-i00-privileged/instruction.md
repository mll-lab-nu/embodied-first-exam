# DexHand · Stir milk into a mug of coffee with a teaspoon (privileged)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a stone worktop (DexHand, MuJoCo). Mix the milk into the coffee: stir it six times with the teaspoon,
then lay the spoon on the worktop beside the mug. The 300 g mug stands upright on the worktop, filled with coffee (the
milk already poured); the right hand starts holding the 35 g teaspoon upright above the rim, bowl down, in a thumb-index
pinch near the top of its handle. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: in this order: with the spoon held between the thumb and at least one other finger and its bowl down in the
coffee, the bowl circles the mug six full times (leaving the coffee before the sixth turn starts the count again); then
the spoon lies on the worktop beside the mug, roughly flat and clear of it, the hand off the spoon, and spoon and mug
are still for a second. A replay ends as soon as the task is done; later rows are not run.

The episode ends at once as a failure if the mug tips, slides or is lifted; the spoon touches the floor, or touches the
worktop before the six turns are done; the spoon is dropped (it cannot be caught again); the mug touches the floor; the
spoon or the mug goes below the worktop or leaves the work area; a fingertip dips into the coffee; an arm link, the
stand or the parked left hand touches the mug, the spoon or the worktop; or the physics becomes unstable. Later actions
cannot undo a failure.

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
s = Session("coffee_stir")                      # default hand: DEXHAND_HAND or "sharpa"
s = Session("coffee_stir", hand="wuji")         # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # bowl position (mug frame), revolutions, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "top"
s.snapshot(), s.restore(snap)                   # save / restore the full simulation and task state
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The worktop top is at z = 0.75 m and the mug axis
at x = 0.48 m, y = 0.015 m; the spoon start pose is `task.json` `spoon_pos` (position, quaternion WXYZ). The right
hand's mount body is `wrist_stage` (on the right arm's flange); the robot stand is at the world origin (`task.json`
`marvin`).

### Actions
Each row is one 50 Hz control, every actuator target in model order (radians):

- columns 0-6: left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (actuators `<joint>_target`); columns 7-13: the same right-arm joints (`..._R_J1` to `..._R_J7`);
- `sharpa` (58 values): then the 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`, then the
  22 right ones `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): then the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the 20 right ones (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start state of each hand (`task.json`
`initial_qpos`) and its start targets (`initial_targets`) are part of the task; `s.hold_action()` returns the current
targets.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and right hand of a Tianji Marvin dual-arm stand (two 7-joint arms, a dexterous hand on each
wrist; the stand sits at the world origin facing +x, its plate on the floor at z = -0.1 m). The left arm starts parked,
hanging beside the torso, and should stay there. Every arm and finger joint is a position servo in the physics engine
under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad, no gravity compensation, so a held
target sags under the arm's weight unless your targets account for it); stirring and laying the spoon down require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

### Scene
The mug (inner radius 50 mm, 100 mm tall, 8 mm floor), a cream glazed mug with a rounded handle pointing +x, stands on
the stone worktop (top at z = 0.75 m, front edge at x = 0.25 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee
fills it to 64 mm above its base (z = 0.814 m). The teaspoon's start pose is `task.json` `spoon_pos` (position,
quaternion WXYZ). With the Wuji hand the spoon instead starts leaning in the mug (bowl on the mug floor, handle on the
rim) and the open hand hangs about 0.25 m above the mug; the task is the same. Cameras: `overview` (front right of the
mug, wide), `closeup` (front right, close) and `top` (looking down the mug axis).

## Others
- The coffee is not simulated: it exerts no force on the spoon. The mug and the spoon are free rigid bodies that move
  only through contact and gravity.

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
