# DexHand · Brush the debris off a boot sole (privileged)

## Task
Brush all six soil clods off the upward-facing sole of the boot into the collection tray.

## Goal
Success: in this order, the brush's bristles sweep the boot while the hand holds the brush off the counter; all six
clods land in the tray, however they leave the sole; then the brush is drawn back from the sole, touching neither the
boot nor a clod, and the clods lie still in the tray for a second. A replay ends as soon as the task is done; later rows
are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The boot moves or tilts.
- A clod touches the counter or the floor, falls below the counter top or leaves the work area.
- Any part of the right hand touches a clod (brush the clods; do not pick them).
- The brush touches the floor, the tray or the rack, falls below the counter top or leaves the work area.
- The brush is let go in the air.
- Any part of the robot other than its right hand touches anything, the robot itself included.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a counter (DexHand, MuJoCo). The scene is one fixed instance. You have the full simulator to develop
with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("boot_sole_brush")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("boot_sole_brush", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names       # selected hand, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, steps, stage, clods in tray/brushed, features
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full physics and task state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may read the full simulator state (`s.model`, `s.data`); `task.json` has the frozen geometry and the clod start
poses. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.886 m; the
brush starts bristles-down on the counter at (0.68, -0.28); the boot's sole plane is at about z = 1.292 m with the toe
towards -x and the sole centre at (0.53, 0.10); the clod start poses and the robot base pose (`marvin`) are in
`task.json`.

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
(`initial_targets`): the right hand starts open, palm down, fingers pointing +y, above the brush (hand frame at about
(0.68, -0.35, 1.115)). The right hand's frame is the body `wrist_stage` on the right flange (fingers along its +z, palm
normal +x, thumb +y), which forward kinematics of the arm joints places in the world.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The stand rests on the floor (z = 0) beside the counter's -y edge, with its base origin at world
(0.147, -0.591, 0.10), facing +y (shoulders 1.121 m above the base origin, at z = 1.221 m; the right shoulder is on the
+x side). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and hand
alone, and no other part of the robot may touch anything. Every arm and finger joint is a position servo inside the
physics engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity
compensation (a held target sags under the arm's weight unless your targets account for it). Grasping, carrying,
brushing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps. The
frozen reset lets the boot, the clods, the brush and the arms settle for 0.5 s before control 1.

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
