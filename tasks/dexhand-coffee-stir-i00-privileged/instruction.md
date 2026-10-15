# DexHand: Stir milk into a mug of coffee with a teaspoon

Mix the milk into the coffee: stir the coffee with the teaspoon, then leave the spoon resting in the mug. The 300 g mug (inner radius 50 mm, 100 mm tall, 8 mm floor) stands upright on the stone worktop (top at z = 0.75 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee, milk already poured, fills it to 64 mm above the mug base (z = 0.814 m). The coffee is not simulated as a fluid: mixing is measured as stirring. The 35 g stainless teaspoon (181.7 mm long, 24 x 46 mm bowl) starts leaning in the mug with its bowl on the mug floor and its handle on the rim. Three stages must be completed in order. (1) In the coffee: while the spoon is in the hand (the thumb and at least one other finger touch it), the bowl is submerged, i.e. the bowl centre and both bowl ends (23 mm either side of the centre along the spoon axis) lie below the coffee surface and above the mug floor (mug frame z between 0.004 and 0.064 m) and within 50 mm of the mug axis. (2) Stir: while the bowl stays submerged, at least 8 mm from the mug axis, and the spoon is in the hand (thumb and at least one other finger touching it; a single finger pushing the spoon does not count), the unwrapped angle of the bowl centre about the mug's vertical axis (world frame) must accumulate three full revolutions (1080 degrees net in one direction). Increments larger than 45 degrees per control are not counted, and the count restarts from zero whenever the bowl leaves the coffee before the three revolutions are complete. (3) Rest: the spoon is released (no hand contact) with its bowl still submerged in the mug, the spoon touching the mug, spoon and mug linear speeds at most 0.02 m/s and angular speeds at most 0.5 rad/s, continuously for 50 controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the mug tilts more than 10 degrees, slides more than 20 mm horizontally from its start or is lifted more than 5 mm above its start height; when the spoon touches the worktop or the floor (dropped or carried out of the mug) or the mug touches the floor; when the spoon touches neither the hand nor the mug while its centre of mass falls faster than 0.2 m/s (a dropped spoon fails at that physics substep; there is no window to catch it again); when a spoon reference point (bowl centre, bowl ends, handle end) falls below the worktop top or the mug base falls below it; when the bowl centre or handle end leaves the workspace box x in [0, 0.96] m, y in [-0.48, 0.48] m, z in [0.70, 1.60] m; when a fingertip enters the coffee (inside the mug radius and below the coffee surface); or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz (60 s); reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, stirring and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene
The mug, the coffee and the teaspoon are the approved T11 kitchen scene: a cream glazed mug with a rounded handle
(pointing +x) on a stone worktop, a stainless teaspoon leaning in it (bowl on the mug floor near the +y wall, handle on
the -y rim, top end at about x = 0.48 m, y = -0.087 m, z = 0.905 m). The hand starts open about 0.3 m above the mug
with its fingers pointing down and its palm facing +y. The coffee is a visual surface only: it exerts no force, and
the stirring is judged only from the bowl's revolutions below that surface. Mug and spoon are free rigid bodies that
move only through contact and gravity. Cameras: `overview` (front right of the mug, wide), `closeup` (front right,
close) and `top` (looking down the mug axis).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the six wrist targets are world coordinates of the hand mount (metres) and serial XYZ joint angles (radians).
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
for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("coffee_stir")                      # default hand: DEXHAND_HAND or "sharpa"
s = Session("coffee_stir", hand="wuji")         # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # bowl position (mug frame), revolutions, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "top"
s.snapshot(), s.restore(snap)                   # save / restore the full simulation and predicate state
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate (`s.features()` reports the quantities the predicate uses: `bowl_cup_frame`, `bowl_radius_m`,
`bowl_submerged`, `revolutions`, `hand_spoon_contacts`, `spoon_cup_contacts`, speeds, `cup_tilt_deg`, `cup_slide_m`,
`rest_hold_steps`). The world frame has z up; lengths are in metres and angles in radians. The worktop top is at
z = 0.75 m and the mug axis at x = 0.48 m, y = 0.015 m; the spoon start pose is `task.json` `spoon_pos` (position,
quaternion WXYZ). The wrist-stage targets are world coordinates of the hand mount within `task.json` `wrist_range`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
