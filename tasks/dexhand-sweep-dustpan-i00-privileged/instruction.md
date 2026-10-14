# DexHand: Sweep debris into a held dustpan

Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan. A fixed two-arm robot starts with a broom held in its right hand and a dustpan held in its left hand; the pan's entrance ramp rests on the floor next to six small rigid debris pieces (packaging pieces, bottle caps, a wood chip and a crumpled-paper ball). Push the debris over the ramp with the broom's bristles, then raise the dustpan. Success requires 2000 consecutive physics steps (1.0 s) in which all of these hold: in the dustpan's own frame every collision shape of all six pieces lies over the pan floor (at least 1 mm inside its 460 mm side-to-side width, inside its 262 mm depth, no lower than 1 mm below the top of the floor plate and no higher than 110 mm above the pan origin); all six pieces touch the pan (contact force at least 1 mN); the pan origin is at least 50 mm above the floor; every piece moves slower than 0.03 m/s and rotates slower than 0.8 rad/s; and every piece has been touched by the bristles at some point. The episode ends with that success, or fails immediately and permanently when: a piece leaves the floor work area (world x outside [0.45, 1.00] m, y outside [-0.50, 0.40] m, or its center more than 0.25 m above or 0.01 m below the floor at z = -0.10 m); any part of the robot touches a piece of debris with at least 1 mN (sweep with the broom only); from 1.2 s on, fewer than two collision parts of a tool's own hand press on its handle with at least 0.01 N each, or the handle's grip point has moved more than 25 mm or turned more than 0.25 rad relative to that palm since 1.2 s (dropped or slipping tool); a tool is pressed (more than 0.01 N) by any robot part other than its own hand; the arms, torso or the two hands collide with each other; or the simulation becomes unstable. Five of six pieces, an unlifted pan or a hold shorter than 1 s is not a success. Only the robot's motor targets act; the tools and the debris are free bodies without welds, scripted motion or applied forces. One control row sets every motor target for one 0.5 ms physics step (2000 Hz); an episode has at most 160000 rows (80 s).

The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its
handle; the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force
bounds; the broom, the dustpan and the debris move only through contact and gravity. At the reset the motor targets
(`s.hold_action()`) keep both tools in the hands; the first 1.2 s are a settling period in which the grip is not yet
judged. MuJoCo 3.4.0 integrates at 0.5 ms (implicitfast, elliptic friction cones), and every control row is applied
for exactly one physics step, so a row is a 2000 Hz control. Simulating one second of this scene costs a few seconds
of CPU: plan with `snapshot()`/`restore()` instead of replaying from the start. Save a
deliverable early and improve it.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
This task uses two hands of one model on the two arms of a fixed robot: Sharpa Wave (default) or Wuji Hand 2.2. Every row holds both arms' joint targets and both hands' finger targets (layout below). With Wuji, both hands start closed on the same broom and dustpan (assets/reset_wuji.npz: the frozen arm, tool, debris and bristle coordinates with Wuji finger joints).
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

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
(Wuji), 1 <= T <= 160000,
as a compressed archive of at most 64 MB, and `/app/output/gen.py`, the script that produced it. Use `s.save_trajectory(actions, "/app/output/trajectory.npz")`, which compresses and records the hand. Row `i` holds the motor
targets for physics step `i` after the frozen reset, in `s.actuator_names` order, within `s.model.actuator_ctrlrange`.
The separate verifier starts from its own frozen scene and replays only these rows in two fresh processes; both
replays must succeed and end in the same state hash. The episode ends at the first success or failure, so rows after
it are not executed. Object poses, success flags or other members of the archive are ignored.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

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

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
