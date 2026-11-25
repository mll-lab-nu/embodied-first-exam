# DexHand · Sweep debris into a held dustpan (privileged)

## Task
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan.

## Goal
Success: every one of the six pieces has been touched by the broom's bristles; all six lie on the pan floor, touching
the pan; the pan is held up off the floor; and everything is still for a second. A replay ends as soon as the task is
done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A piece leaves the floor work area.
- Any part of the robot touches a piece (sweep with the broom only).
- After the short settling period at the start, a tool slips in its hand or falls out of it.
- A tool is pressed by any robot part other than its own hand.
- The arms, the torso or the two hands collide with each other.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` (Sharpa) or `(T, 54)`
(Wuji), 1 <= T <= 160000, as a compressed archive of at most 64 MB, and `/app/output/gen.py`, the script that produced
it. Use `s.save_trajectory(actions, "/app/output/trajectory.npz")`, which compresses and records the hand. Row `i` holds
the motor targets for physics step `i` after the frozen reset, in `s.actuator_names` order, within
`s.model.actuator_ctrlrange`. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive larger
than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, over a floor (DexHand, MuJoCo).
The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
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
s.features()                          # task diagnostics: containment, pan contact, lift, grip, speeds
s.observe()                           # joints, targets, palm/tool/debris poses and the diagnostics
snap = s.snapshot(); s.restore(snap)  # exact copies of simulator and task state
s.render_frame("work")                # RGB uint8 (480, 640, 3); cameras: overview, work, pan, side
s.reset()                             # exact frozen reset (of the selected hand)
s.replay(rows)                        # reset, then execute rows as the grader does
s.save_trajectory(rows, "/app/output/trajectory.npz")
s.model, s.data                       # privileged MuJoCo model and state
```
World frame: metres and radians, z up, the robot base at the origin, the floor the plane z = -0.10 m; quaternions are
`wxyz`. The arm and finger targets are joint angles; there is no Cartesian or inverse-kinematics controller.

### Actions
Every row holds both arms' joint targets and both hands' finger targets (layout below). Sharpa rows (58 targets): the 7
left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand Sharpa
Wave finger targets (`l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, `r_hand_thumb_CMC_FE ... r_hand_pinky_DIP`, radians).
Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2 finger
targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC flexion, CMC abduction, MCP,
IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. This task uses two hands of one
model on the two arms of a fixed robot: Sharpa Wave (default) or Wuji Hand 2.2. With Wuji the start differs only in the
finger joints and their targets: both Wuji hands start closed on the same broom and dustpan (the arm, tool, debris and
bristle coordinates and the arm targets are those of the Sharpa start), and `s.hold_action()` keeps them.

### Robot
The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its handle;
the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force bounds; the
broom, the dustpan and the debris move only through contact and gravity. At the reset the motor targets
(`s.hold_action()`) keep both tools in the hands; the first 1.2 s are a settling period in which the grip is not yet
judged. MuJoCo 3.4.0 integrates at 0.5 ms (implicitfast, elliptic friction cones), and every control row is applied for
exactly one physics step, so a row is a 2000 Hz control. Simulating one second of this scene costs a few seconds of CPU:
plan with `snapshot()`/`restore()` instead of replaying from the start. Save a deliverable early and improve it.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 9 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
