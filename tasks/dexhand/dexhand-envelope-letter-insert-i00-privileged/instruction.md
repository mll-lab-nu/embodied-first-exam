# DexHand · Put a folded letter into an envelope (privileged)

## Task
Put the folded letter into the envelope.

## Goal
Success: the letter goes in through the mouth of the envelope until all but a sliver of it is inside, between the side
seams and the walls; then the hand has let go of the letter and the envelope, and both lie still for a second. A replay
ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The letter or the envelope falls below the desk top, touches the floor, is dropped or leaves the desk.
- The letter is pressed through a wall, a seam or the mouth lip of the envelope.
- The envelope is pushed away or tilted.
- The robot's arm, stand or parked left hand touches the letter or the envelope.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a desk (DexHand, MuJoCo). The scene is one fixed instance. You have the full simulator to develop
with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("envelope_letter_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("envelope_letter_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # corners in the envelope frame, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "mouth"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m. The robot's base
pose is `task.json` `marvin`; `s.data.xpos` / `s.data.xmat` of the body `right_hand_C_MC` (the hand root on the right
flange) give the hand's pose, and MuJoCo's Jacobians (`mujoco.mj_jacBody`) are available for your own inverse kinematics
(none is supplied).

### Actions
Each row is one 50 Hz control in native actuator order (`s.actuator_names`), radians:

- `sharpa`: 58 values: the 7 left-arm joint targets
  `SHOULDER_PITCH_L_J1_target, SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target, WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`,
  the 7 right-arm joint targets (`..._R_J1_target` ... `..._R_J7_target`), then the 22 left-hand and the 22 right-hand
  Sharpa Wave finger targets (`left_thumb_CMC_FE` ... `left_pinky_DIP`, `right_thumb_CMC_FE` ... `right_pinky_DIP`).
- `wuji`: 54 values: the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2 finger targets
  (`l_wuji_l_THJ0..3, FFJ0..3, MFJ0..3, RFJ0..3, LFJ0..3`, then the same for `r_wuji_r_`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm targets (`task.json`
`initial_targets`); keep the left arm parked (its start targets), it must not touch the letter or the envelope.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its
base plate stands on the floor at z = 0); the left arm is parked beside the torso and only the right arm and hand do the
task. Arm joints and fingers are position servos in the physics engine under native force bounds; pressing, sliding,
pushing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

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
