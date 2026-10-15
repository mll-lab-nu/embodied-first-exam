# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The robot stands on the floor in front of the desk, right of the hub (base centre at x = 0.93,
y = -0.52 on the floor at z = -0.20, facing the desk at yaw 135 deg, i.e. toward world (-1, +1)/sqrt(2); shoulders
at z = 1.021 m, 1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force
bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target sags
under the arm's weight unless your targets account for it). Grasping, carrying, inserting and releasing require
physical contact. Only the working right hand may touch the desk and the task objects: any contact of an arm link, the
stand or torso, or the parked left hand with anything fails the episode at once (`robot_collision`). The controller
runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
- Desk: top at z = 0.70 m (0.90 m above the floor at z = -0.20), front edge at y = -0.114 m (world frame, z up,
  metres and radians); its two front legs stand back under the top (x 0.32, y 0.00 and x 1.08, y 0.46), clear of
  the robot's base plate.
- Hub: the original four-port USB hub (103 x 30 x 10 mm, 21.8 g) rests free on the desk on rubber pads, its port face
  flush with the desk's front edge and facing -y; it is not fixed or held. Ports 1-4 are at hub-local
  x = -27, -7, +13, +33 mm; port 4 (the target) is the rightmost seen from the front. Its own upstream cable is drawn
  lying on the desk and has no physics.
- Plug: a free USB-A plug (7 g; metal shell 12.0 x 4.5 x 12 mm, housing 15 x 20 x 8 mm, strain relief) lying on its
  side on the desk, with a passive 0.5 m cable (20 ball-jointed links, 15 g) ending in a free USB-B plug on the desk.
  The plug frame origin is the centre of the shell tip; its +y axis points out of the shell (insertion direction)
  and +z is the polarized top face. Inserted correctly, the plug's +y aligns with the hub's +y and +z with the hub's +z.
- Ports are open rectangular cavities 12.5 x 4.8 x 12 mm (0.25 mm clearance per side across, 0.15 mm in height); the
  receptacle tongue and contacts are visual only, polarity is part of the success predicate, and there are no
  retention springs: a seated plug stays by friction and its own weight.
- Cameras: `overview` (desk, hub and plug from the front left) and `closeup` (the hub's port face).

{{HANDS}}
## Action layout
Each row is one 50 Hz control and holds a position target for every actuator, in radians:

- `sharpa` (58 values): 0-6 the left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
  WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`; keep them at the parked start
  values), 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`), 14-35 the 22 left Sharpa Wave finger targets
  `left_thumb_CMC_FE` ... `left_pinky_DIP`, 36-57 the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets, 14-33 the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, 34-53 the 20 right ones
  (`r_wuji_r_...`, same order).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`); the right hand's frame is the body `wrist_stage` on the right flange (fingers along its +z, palm
normal +x, thumb +y), which forward kinematics of the arm joints places in the world.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most {{MAX_ROWS}} rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.

## Tooling
```python
from rcb_dexhand import Session
s = Session("usb_plug_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("usb_plug_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names       # selected hand, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.features()                                 # plug/hub poses, per-port depth/offsets, axis error, contacts, failure
s.status()                                   # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full simulation and verdict state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Privileged mode exposes the full simulator state (`s.model`, `s.data`, `s.features()`); read `/opt/tools/task.json`,
`scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m and its
front edge at y = -0.114 m; the hub's port 4 mouth starts at the hub-local point (0.033, -0.015, 0) and the plug frame
origin is the centre of its metal shell tip, with the plug axis along its local +y and its top (polarized) face +z.
