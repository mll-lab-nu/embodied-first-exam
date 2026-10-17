# DexHand: {{TITLE}}

{{TASK_TEXT}}

## Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m (the floor is at z = -0.55 m). The remote lies
flat at (0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on
four rubber feet, at the approved scene's size (shell 160 x 64 mm, battery cavity 94 x 52 mm). Its battery door
slides along the remote's -x direction on a passive slide joint (travel 0 to 0.085 m, end stops at both ends, damping
0.1 N s/m, 0.08 N friction loss) and is latched shut: a spring-loaded thumb tab on the door (18 x 18 mm, 3 mm proud
of the door, a passive slide joint pressing down 0 to 5 mm against a 120 N/m spring) carries a hook that sits just in
front of a fixed latch stop at the remote's rear end while the door is shut. The door opens only while the tab is
pressed far enough (about 2.9 to 4.5 mm) for the hook to pass under the stop; it re-latches when it is slid fully
shut and the tab is released. Under the door is a one-cell compartment: the slot centre is at (-0.020, 0.0,
-0.00244) m in the remote frame, the gray cell lies there on two low cradle ribs with its + end toward the gold
contact at the slot's +x end (the silver - contact is at the -x end; 3 mm end play). The green replacement cell (a
23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on the table at (0.115, -0.110, 0.307) with its
+ end pointing 20 degrees clockwise from world +x (seen from above). The receiving tray (free rigid body, inner 74 x
64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). Modelling scope: the compartment holds one cell as in the source
scene; the source's compressible negative spring is not modelled (the terminals are fixed); there is no electrical
simulation. All objects move only through contact and these passive joints.

You control a fixed Tianji Marvin robot standing at the table (stand origin at (-0.45, 0.15, -0.45), facing +x) with
two 7-joint arms and a dexterous hand on each wrist; the right arm and hand do the task, the left arm hangs parked
beside the torso (keep its targets). Every arm and finger joint is a position servo inside MuJoCo 3.4.0 under native
force bounds; the arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held
target sags under the arm's weight unless your targets account for it). Grasping, carrying and releasing require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps per control.

{{HANDS}}
## Action layout
Each row is one 50 Hz control holding a position target for every actuator (radians), in native actuator order:

- `sharpa` (58 values): 0-6 left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
  WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); 7-13 the same right-arm joints
  (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`; 36-57 the
  right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets; 14-33 the left Wuji Hand 2.2 fingers `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`; 34-53 the right Wuji fingers in the
  same order (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm pose (right hand above
the table near the robot, left arm parked); the frozen start targets of each hand are in `task.json`
(`initial_targets`).

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
s = Session("remote_battery_swap")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("remote_battery_swap", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # door travel, tab depth, stage conditions, cell errors, contacts, failure
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
