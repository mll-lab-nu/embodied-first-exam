# DexHand: Align and staple three paper sheets

Square up three loose A5 sheets and staple them at a corner with the desk stapler. The sheets lie as a misaligned stack (each upper sheet shifted toward +x) with the bottom sheet's corner resting on the stapler's anvil mouth and the far edge on the desk. Slide the stack into the stapler throat against the stapler's paper stop, square the sheets, press the stapler head through its full stroke onto the stack and let it spring back. Stages, in order: (1) aligned: every corner of sheets 1 and 2 within 2.0 mm of the matching corner of sheet 0 (in sheet 0's plane), the sheets stacked in order (each 0.25-1.5 mm above the one below, along sheet 0's normal) and sheets 0-1 and 1-2 in contact; (2) in the throat: with (1), the staple point (stapler base frame (0.063, 0, 0.012) m, on the anvil under the driver blade) lies inside every sheet 3-30 mm from both edges of one corner and every sheet mid-plane is 0-6 mm above it; (3) pressed: with (1) and (2), the head hinge within 0.01 rad of its bottom stop (0.1701 rad) and the driver blade touching the top sheet; (4) released: after (3), with (1) and (2), the head back up (hinge <= 0.02 rad), no hand contact with any sheet or the stapler and every sheet's centre of mass slower than 0.02 m/s for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when a sheet centre falls below z = 0.77925 m (1 mm under its resting height on the desk top) or any sheet corner below z = 0.765 m, a sheet centre leaves the desk (x 0.25-0.99 m, y -0.36-0.36 m) or the workspace box (x 0.2-1.1 m, y -0.45-0.45 m, z 0.70-1.20 m), a sheet or the stapler touches the floor or a desk leg, a sheet or the stapler has no contact at all while its centre of mass falls faster than 0.2 m/s, the stapler base moves more than 3 cm horizontally from its reset position or tilts more than 0.26 rad, or the physics becomes unstable; later actions cannot undo a failure. Only hand and wrist-stage actuator targets are allowed. Sheets are 0.5 mm rigid plates (real A5 size and mass); staple formation is not simulated. At most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
pushing, pressing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage (world-frame x, y, z slides and serial x-y-z hinges), with the same wrist joints, ranges, gains and start targets.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

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
for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("paper_staple")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("paper_staple", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # corner offsets, staple margins, head angle, contacts, failure details
s.status()                                      # success, done, reason, steps, stage (0-4), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "throat"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. Cameras for `render_frame`: `overview`, `closeup` (stapler and stack) and `throat` (the stapler mouth).

## Scene (frozen instance, world frame)
World frame: z up, metres and radians. The desk top is at z = 0.78 m and spans x 0.25-0.99 m, y -0.36-0.36 m
(friction: paper on paper 0.4, paper on desk 0.15, paper on the chrome anvil and stop 0.1). The NOVUS B2-style desk
stapler is a free body (0.173 kg) whose base origin is at (0.70, -0.10, 0.783) with its nose toward +x. Its anvil top is
at z = 0.795 m; the staple point (base frame (0.063, 0, 0.012) m) is at (0.763, -0.100, 0.795) in the reset pose. A
steel paper stop (insertion guide) stands behind the anvil: its front face is at base-frame x = 0.0525 m (world
x = 0.7525 m) for |y - y_base| <= 0.012 m, z 0.790-0.800 m; a stack whose corner is fed against it puts the staple point
about 10.5 mm inside both edges. The handle with its driver blade turns on one passive hinge about the base-frame y
axis at (-0.052, 0, 0.020): return spring 1.5 N m/rad with 0.15 rad preload against the open stop (0 rad), bottom stop
0.1701 rad (the blade 0.2 mm into a three-sheet stack lying on the anvil). The handle top is about 6.6 cm above the
desk; about 6 N pressed 8 cm in front of the hinge holds it at the bottom stop. The magazine is rigid with the base.

The three sheets are rigid A5 plates (0.210 x 0.148 m, 0.5 mm thick, 2.5 g each), indexed bottom (0) to top (2). At reset
they rest as a loose, misaligned stack: the bottom sheet's (-x, -y) corner lies on the anvil mouth in front of the
paper stop, its +x edge on the desk; sheets 1 and 2 are shifted 4 mm and 8 mm toward +x. Rest poses (centre; all three pitched 0.0733 rad
about +y, i.e. the -x end raised, yaw 0): sheet 0 (0.8690, -0.0360, 0.7879), sheet 1 (0.8730, -0.0356, 0.7881),
sheet 2 (0.8771, -0.0364, 0.7883); exact values in `task.json` `sheets[i].pose` (position, wxyz quaternion). This start is a simplification of the original scene, in
which the sheets lie flat and are lifted into the stapler: here the corner is already at the throat mouth and the
stack is slid in. Staple legs, piercing and clinching are not simulated; "stapled" means the head pressed through
its full stroke onto the aligned, inserted stack and released. The wrist stage starts at (0.95, 0.30, 1.00) with all
three wrist angles 0 (palm up, fingers toward +x); its ranges are x 0.2-1.4 m, y -0.7-0.7 m, z 0.5-1.4 m and +-3.14 rad.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
