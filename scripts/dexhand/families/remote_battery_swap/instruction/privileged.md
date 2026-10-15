# DexHand: {{TITLE}}

{{TASK_TEXT}}

## Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m. The remote lies flat at
(0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on four
rubber feet. Its battery door slides along the remote's -x direction on a passive slide joint (travel 0 to 0.085 m,
end stops at both ends); a light friction hold (0.25 N friction loss) keeps it where it is left, and a 3 mm raised
ridge across the door gives a fingertip something to push against. Under the door is a one-cell compartment: the
slot centre is at (-0.020, 0.0, -0.00244) m in the remote frame, the gray cell lies there on two low cradle ribs
with its + end toward the gold contact at the slot's +x end (the silver - contact is at the -x end; 3 mm end play).
The green replacement cell (a 23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on the table at
(0.115, -0.110, 0.307) with its + end pointing 20 degrees clockwise from world +x (seen from above). The receiving
tray (free rigid body, inner 74 x 64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). The hand starts above and to
the side of the remote. Modelling scope: the remote shell is the approved scene's model widened 1.25 times across
(80 mm wide, cavity 65 mm) so two fingertips fit beside one cell; the original door latch tab and the compressible
negative spring are not modelled (the door is held by friction only, the terminals are fixed); the compartment holds
one cell; there is no electrical simulation. All objects move only through contact and these passive joints.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

{{HANDS}}
## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). The finger targets follow in native actuator order, in radians:

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
s = Session("remote_battery_swap")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("remote_battery_swap", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # door travel, stage conditions, cell errors, contacts, speeds, failure
s.status()                                       # success, done, reason, steps, stage (latched stages), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.snapshot(), s.restore(snap)                    # save / restore the full simulator and predicate state
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json` (the `checker` block holds every threshold), `scene.py`, `checker.py` and `runtime.py`
for the complete geometry, failure checks and predicate. `s.features()["conditions"]` reports the four stage
conditions, `s.status()["stage"]` the number of stages completed in order and `hold_steps` the released-hold count.
You may read the full simulator state and use `s.snapshot()` / `s.restore()` while authoring; only the rows you hand
in are graded.
