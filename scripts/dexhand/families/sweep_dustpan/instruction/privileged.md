# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its
handle; the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force
bounds; the broom, the dustpan and the debris move only through contact and gravity. At the reset the motor targets
(`s.hold_action()`) keep both tools in the hands; the first 1.2 s are a settling period in which the grip is not yet
judged. MuJoCo 3.4.0 integrates at 0.5 ms (implicitfast, elliptic friction cones), and every control row is applied
for exactly one physics step, so a row is a 2000 Hz control. Simulating one second of this scene costs a few seconds
of CPU: plan with `snapshot()`/`restore()` instead of replaying from the start. Save a
deliverable early and improve it.

{{HANDS}}
Sharpa rows (58 targets): the 7 left-arm joints
`SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints `SHOULDER_PITCH_R_J1_target ...
WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand Sharpa Wave finger targets
(`l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, `r_hand_thumb_CMC_FE ... r_hand_pinky_DIP`, radians).
Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2
finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC flexion, CMC
abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians). With Wuji the start
differs only in the finger joints and their targets: both Wuji hands start closed on the same broom and dustpan
(the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa start), and
`s.hold_action()` keeps them. The task, predicate and fail-fast rules are the same for both hands.
The verifier rebuilds the scene with the archive's `hand` and rejects rows whose width does not match it.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` (Sharpa) or `(T, 54)`
(Wuji), 1 <= T <= {{MAX_ROWS}},
as a compressed archive of at most 64 MB, and `/app/output/gen.py`, the script that produced it. Use `s.save_trajectory(actions, "/app/output/trajectory.npz")`, which compresses and records the hand. Row `i` holds the motor
targets for physics step `i` after the frozen reset, in `s.actuator_names` order, within `s.model.actuator_ctrlrange`.
The separate verifier starts from its own frozen scene and replays only these rows in two fresh processes; both
replays must succeed and end in the same state hash. The episode ends at the first success or failure, so rows after
it are not executed. Object poses, success flags or other members of the archive are ignored.

## Tooling
```python
from rcb_dexhand import Session
s = Session("sweep_dustpan")          # Sharpa Wave hands (default); Session("sweep_dustpan", hand="wuji") for Wuji
s.actuator_names, s.action_dim        # row order and width
s.model.actuator_ctrlrange            # target limits (radians)
s.hold_action()                       # current targets; at the reset they hold the tools
s.step(row)                           # one 0.5 ms physics step; no-op once the episode is done
s.step_many(rows)                     # several rows; stops when the episode is done
s.hold(n)                             # keep the current targets for n physics steps
s.status()                            # success, done, failed, reason, steps, in_pan, terminal_run
s.features()                          # predicate diagnostics: containment, pan contact, lift, grip, speeds
s.observe()                           # joints, targets, palm/tool/debris poses and the diagnostics
snap = s.snapshot(); s.restore(snap)  # exact copies of simulator and predicate state
s.render_frame("work")                # RGB uint8 (480, 640, 3); cameras: overview, work, pan, side
s.reset()                             # exact frozen reset (of the selected hand)
s.replay(rows)                        # reset, then execute rows exactly like the verifier
s.save_trajectory(rows, "/app/output/trajectory.npz")
s.model, s.data                       # privileged MuJoCo model and state
```
The tooling is in `/opt/tools`: `instance.json` (instance and predicate parameters), `runtime.py`, `checker.py` and
the frozen model in `assets/`. World frame: metres and radians, z up, the robot base at the origin, the floor the
plane z = -0.10 m; quaternions are `wxyz`. The arm and finger targets are joint angles; there is no Cartesian or
inverse-kinematics controller.
