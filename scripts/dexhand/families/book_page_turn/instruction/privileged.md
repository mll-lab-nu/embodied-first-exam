# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin stand (at the world origin, facing +x; shoulders at (0, +-0.2215, 1.121)) with
two 7-joint arms and a dexterous hand on each wrist; both arms and both hands may be used. Every arm and finger joint
is a position servo in the physics engine under native force bounds (arm servos: stiffness 700 N m/rad, damping
48 N m s/rad, the arms' own torque limits and **no gravity compensation**, so a held target sags slightly under the
arm's weight unless your targets account for it). Lifting, carrying and laying the page down require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps. The book is not attached to anything: it rests
on the desk under gravity and friction, and a push on its pages moves it unless something holds it.

## Scene
World frame: z up, metres and radians, +x forward from the robot stand, +y to the robot's left. The desk top is the
plane z = 0.78 m (desk x in [0.22, 0.82] m, y in [-0.26, 0.26] m). The board book lies open on the desk as one free
body (`book_spine`, nothing anchors it): its spine runs along the world x axis through y = 0, from x = 0.434 to
x = 0.586 (centre x = 0.51). Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm thick laminated board of 16 g;
the right-hand boards extend from the spine toward -y (the robot's right; fore-edge at y = -0.152), the left-hand
boards toward +y (fore-edge at y = +0.152). Boards hinge at the spine about the world x axis (`<board>_binding`,
passive friction 0.002 N m and damping 0.006 N m s/rad) on a small vertical binding compliance
(`<board>_binding_compliance`, 200 N/m). Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left
stack, leaf 1 on top), leaf 2 9.0 mm, leaf 3 7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm
(right stack, leaf 2 on top), both covers 0.6 mm. **Every board lies flat on its stack, 0.2 mm above the board below
it**: the top board's fore-edge face (1.2 mm tall, at y = -0.152, top at z = 0.7884) sits directly above leaf 3's.
Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf hinge angles are measured from the flat right-hand
position for right-hand boards (0 = flat right, pi = flat left) and from the flat left-hand position for left-hand
boards (negative = lifted toward the right). At the start the right hand (frame `wrist_stage` / `right_hand_C_MC`,
palm up, index straight) is at about (0.47, -0.44, 0.93) and the left arm hangs parked beside the stand.

{{HANDS}}
## Action layout
Each row is one 50 Hz control of all 58 (`sharpa`) or 54 (`wuji`) actuator targets, in radians.
Row layout, `sharpa` (58): 0-6 left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); 7-13 the same right-arm joints
(`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE, left_thumb_CMC_AA,
left_thumb_MCP_FE, left_thumb_MCP_AA, left_thumb_IP, left_index_MCP_FE, left_index_MCP_AA, left_index_PIP,
left_index_DIP`, the same four for middle and ring, then `left_pinky_CMC, left_pinky_MCP_FE, left_pinky_MCP_AA,
left_pinky_PIP, left_pinky_DIP`; 36-57 the right Sharpa Wave fingers in the same order (`right_...`).
Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji fingers `l_wuji_l_THJ0..THJ3` (thumb),
`l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle), `l_wuji_l_RFJ0..RFJ3` (ring), `l_wuji_l_LFJ0..LFJ3`
(little); 34-53 the right Wuji fingers in the same order (`r_wuji_r_...`). The frozen start row of each hand variant
(arm targets and finger targets) is in `task.json` (`initial_targets`).

Every target must lie within `s.model.actuator_ctrlrange`.

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
s = Session("book_page_turn")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("book_page_turn", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names      # selected hand, row width and exact row order
s.hold_action()                             # current motor targets
s.model.actuator_ctrlrange                  # native target limits
s.model, s.data                             # privileged MuJoCo model and state
s.features()                                # leaf-2 angle and speed, other-leaf changes, contacts, book pose change
s.status()                                  # success, done, reason, steps, stage (0-4), total_stages
s.step(row)                                 # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)               # save / restore the full simulation and verdict state
s.render_frame("overview")                  # RGB uint8 (480, 640, 3); also "closeup", "front", "top"
s.reset()                                   # exact frozen reset (includes a fixed 0.5 s passive book settle)
s.replay(actions)                           # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py`, `runtime.py` and `arm_rig.py` for the complete geometry,
robot, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. The desk
top is at z = 0.78 m; the book's spine runs along the world x axis through y = 0, the right-hand pages extend toward
-y and the left-hand pages toward +y. Leaf bodies are `leaf_0` ... `leaf_7` (leaf 0 and 1 on the left, 2 to 7 on the
right, leaf 2 on top), `left_cover`, `right_cover` and the spine `book_spine`. No inverse-kinematics helper is
supplied.
