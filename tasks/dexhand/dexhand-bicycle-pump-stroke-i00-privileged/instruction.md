# DexHand · Inflate a tire with a portable bicycle pump (privileged)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a bench (DexHand, MuJoCo). Inflate the bicycle tire with the portable bicycle pump: a mini floor pump
(barrel 0.25 m tall) stands free on its folding foot on the bench next to a 20-inch wheel lying on the bench; the pump's
hose head starts disconnected from the wheel's Schrader valve, its thumb lock open (lever pointing up), and the tire is
at 200.0 kPa. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: in this order: the hose head is pushed onto the valve and its thumb lock closed; with the head connected, the
pump handle goes through at least 28 full strokes (pushed nearly all the way down and let back up nearly to the top;
shallower strokes do not count), which brings the tire to 210.6 kPa; the thumb lock is opened and the head pulled back
off the valve; then the handle rests at the top, the pump stands upright and still, and no part of the robot touches the
pump or the head for a second. A replay ends as soon as the task is done; later rows are not run.

The episode ends at once as a failure if the pump tips over, slides or lifts off its spot, falls below the bench top or
touches the floor; if the connected head is pulled back or its lock opened before the tire is pumped up; if the head is
pulled back while its lock is still closed (open the lock first); or if the physics becomes unstable. Later actions
cannot undo a failure.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 5000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
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
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds;
arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target sags under the
arm's weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Others
- The head sits on the valve stem's axis 17.5 mm out from its seat and moves only along that axis (a passive slide with
  a little friction): pushing it 17.5 mm toward the rim seats it on the stem. The thumb lock is a passive hinge on the
  head that turns from pointing up (open) to lying flat toward the wheel hub (closed).
- The T handle starts at the top of its 0.20 m travel; the piston's air spring pushes it back up (about 6 N at the top,
  46 N at the bottom of the stroke). A stroke counts only while the head is connected and locked; every counted stroke
  raises the tire pressure by the same amount.
- The wheel, valve and hose are fixed props (the hose end moves with the head); the head and its lock move only through
  contact.

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
