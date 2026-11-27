# DexHand · Inflate a tire with a portable bicycle pump (privileged)

## Task
Pump up the bicycle tire: push the pump's hose head onto the valve and close its lock, pump the handle 28 full strokes,
then open the lock, pull the head off and let go of the pump.

## Goal
Success: in this order, the hose head is pushed fully onto the valve and its thumb lock closed; with the head connected
and locked, the handle is pumped at least 28 full strokes (pushed nearly all the way down and let back up nearly to the
top; shallower strokes do not count); the thumb lock is opened and the head pulled back off the valve; then the handle
rests at the top and the pump stands upright and still, with no part of the robot touching the pump or the head, for a
second. A replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The pump tips over, slides or lifts off its spot.
- The pump falls below the bench top or touches the floor.
- Before the 28 strokes are done, the connected head is pulled back or its lock is opened.
- The head is pulled back while its lock is still closed (open the lock first).
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 5000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a bench (DexHand, MuJoCo). The scene is one fixed instance. You have the full simulator to develop
with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("bicycle_pump_stroke")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("bicycle_pump_stroke", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # strokes, piston depth, pressure, pump pose/speed, contacts, failure
s.status()                                       # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup", "wide", "front"
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()` and `s.status()` report `head_connected`, `head_disconnected`, `head_slide_m`, `lever_angle_rad`,
`hand_head_contacts`, `strokes`, `piston_depth_m`, `tire_gauge_pa`, `stage` (completed stages: 1 = head connected, 2 =
28 strokes, 3 = pressure target, 4 = head disconnected, 5 = released hold), `released_hold_steps`, `pump_tilt_rad`,
`pump_displacement_m`, `pump_lift_m`, `pump_speed_m_s`, `handle_speed_m_s`, `hand_pump_contacts` and, after a failure,
`failure` / `failure_detail`. The world frame has z up; lengths are in metres and angles in radians. The bench top is at
z = 0.70 m; the pump body is `pump` (free joint `pump_free`), its piston slide `piston_extension` (0.20 m = handle up,
at rest) and the T handle geom `t_handle`. The hose head is the body `pump_head` on the slide `head_slide` (0 at reset,
-0.0175 m = seated; axis (0.981, 0, 0.196), pointing from the rim toward the hub) with the thumb lock `thumb_lock` on
the hinge `lever_angle` (0 = up/open at reset, 1.65 rad = closed); at reset the lever's foot is near world (0.547,
-0.129, 0.747).

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
(`initial_targets`): the right hand starts open, palm down, above and to the right of the pump. The right hand's frame
is the body `wrist_stage` on the right flange (fingers along its +z, palm normal +x, thumb +y), which forward kinematics
of the arm joints places in the world.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds;
arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags under the
arm's weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

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
