# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three world-axis prismatic joints, then
three serial revolute joints in a fixed rotated gimbal frame; no arm). The stage and the fingers are position actuated
in the physics engine under native force bounds; grasping, carrying, inserting and releasing require physical contact.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
- Desk: top at z = 0.70 m, front edge at y = -0.114 m (world frame, z up, metres and radians).
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
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame position of the hand mount) and `wrist_rx, wrist_ry, wrist_rz`
(radians, serial X-Y-Z hinges whose zero orientation is the gimbal frame `wrist_gimbal`, not a quaternion). The finger
targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets; the frozen
finger start pose of each hand is in `task.json` (`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or `(T, 26)`
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
