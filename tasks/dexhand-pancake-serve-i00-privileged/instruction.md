# DexHand: Serve a pancake from a frying pan with a spatula

Serve the pancake from the frying pan onto the plate using the kitchen turner (spatula) that the hand already holds. The pancake lies in the frying pan, the empty ceramic plate stands beside it on the counter, and the turner starts in a power grasp of the hand. Only the turner may move the pancake: slide its blade under the pancake, lift it out of the pan on the blade, carry it to the plate, set it down in the plate and withdraw the turner. Success requires three stages in this order. (1) On the blade: the pancake touches the turner blade and no other object (no pan, plate, hand, counter or floor contact), its origin is at least 0.015 m above its starting height and it is tilted at most 30 degrees, for 10 consecutive controls. (2) Over the plate: later, while still touching only the turner, the pancake centre is within 0.058 m (horizontally) of the plate centre and above the plate floor. (3) Served: later, the pancake touches only the plate, its centre is within 0.058 m of the plate centre horizontally (the whole pancake inside the plate's 0.128 m rim radius), it is tilted at most 20 degrees from flat, its linear speed is at most 0.02 m/s and angular speed at most 0.3 rad/s, the turner does not touch it and every point of the blade outline is at least 0.08 m from the pancake centre horizontally (withdrawn); this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; skipping or reordering a stage never counts. The episode ends immediately with failure, checked after every 1 ms physics substep with no grace period, when the pancake touches the counter top or the floor, falls freely (touching nothing while its centre of mass moves down faster than 0.35 m/s, i.e. after about 6 mm of free fall) or its origin falls below the counter top (z < 0.85 m), when any part of the hand touches the pancake, when the turner touches the floor, falls out of the hand (no hand contact while its centre of mass moves down faster than 0.35 m/s) or its origin falls below the counter top, when the pan or the plate moves more than 0.03 m from its starting position or tilts more than 15 degrees, when the pancake, pan, plate or turner leaves the workspace box x in [0.23, 1.13] m, y in [-0.65, 0.45] m, z in [0.80, 1.50] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The pancake is a rigid coherent disk and the turner blade bends through three passive spring hinges. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
the turner is held only by finger and palm contact, and the pancake moves only through contact with the turner, the
pan and the plate. The controller runs at 50 Hz, with twenty 1 ms physics substeps per control.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The episode starts with the turner already held in a settled power grasp: the frozen reset places
the hand, turner, pan, plate and pancake in a state that was reached by closing the fingers on the handle and letting
the whole scene settle under physics; the turner is held only by contact (there is no weld or attachment), so opening
the fingers drops it. Physics runs at 1 ms steps, twenty per 50 Hz control.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage (world-frame x, y, z slides in metres, then serial X, Y, Z hinges in radians), with the same joint ranges, gains and start targets; the reset grasp of the turner is hand-specific.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Each hand starts from a frozen settled grasp of the turner
(`task.json` `initial_qpos` and `initial_targets` per hand); `s.hold_action()` at reset returns the start targets.
Opening the fingers releases the turner.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or `(T, 26)`
for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("pancake_serve")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("pancake_serve", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names     # selected hand, row width and exact row order
s.hold_action()                            # current motor targets
s.model.actuator_ctrlrange                 # native target limits
s.model, s.data                            # privileged MuJoCo model and state
s.features()                               # pancake pose, contacts, plate distance, withdrawal, stage, failure details
s.status()                                 # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                # twenty 1 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)              # full simulator + verdict state, for search
s.render_frame("overview")                 # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                  # exact frozen reset
s.replay(actions)                          # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.85 m,
the pan rests centred at (0.50, 0.10) and the plate at (0.76, 0.18).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
