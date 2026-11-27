# DexHand · Carry a tray with two filled glasses around a bottle to the other counter (privileged)

## Task
Carry the serving tray with the two filled glasses from the source counter to the receiving counter.

## Goal
Success: in this order, the tray is lifted off the source counter with both glasses standing on it; it is carried around
the steel bottle and set down in the middle of the receiving counter, level and turned the same way as at the start,
both glasses still on it; then no hand touches the tray or a glass, the glasses stand upright, and everything is still
for a second. A replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A glass tilts far enough to spill, or slides off its place on the tray.
- The steel bottle touches the tray, a glass or a hand.
- After lift-off, the tray touches the source counter again.
- The tray touches the receiving counter away from its middle (no dragging).
- The tray or a glass is dropped.
- The tray tilts steeply.
- The tray or a glass goes below the counter tops, touches the floor or leaves the work area.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 56)` for `sharpa` or
`(T, 52)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
Two dexterous hands, each on its own six-axis wrist stage (no arm), above a serving tray (DexHand, MuJoCo). The scene is
one fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("tray_glass_carry")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("tray_glass_carry", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names        # selected hand, row width and exact row order
s.hold_action()                               # current motor targets
s.model.actuator_ctrlrange                    # native target limits
s.model, s.data                               # privileged MuJoCo model and state
s.status()                                    # success, done, reason, steps, stage (0..3), hold_steps, features
s.step(row)                                   # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                 # save / restore the simulator and task state
s.render_frame("overview")                    # RGB uint8 (480, 640, 3); also "side", "top", "handle_left"
s.reset()                                     # exact frozen reset
s.replay(actions)                             # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
In this mode you may read the complete simulator state (`s.model`, `s.data`: object poses, contacts, velocities) and the
progress (`s.status()`: `stage` 0 start, 1 lifted, 2 placed, 3 released and held; `hold_steps` counts the 50-control
release window; `reason` names the first failure). The world frame has z up; lengths are in metres and angles in
radians. Both counter tops are at z = 0.88 m; the tray's body frame sits at the bottom centre of its floor, its long
axis along world y.

### Actions
Each row is one 50 Hz control and holds, in this order:

1. the left wrist stage: `l_wrist_x, l_wrist_y, l_wrist_z` (metres, displacement along the world axes from the stage
   base at (0.35, 0.272, 1.15) m) and `l_wrist_rx, l_wrist_ry, l_wrist_rz` (radians, serial XYZ hinges at the wrist);
2. the right wrist stage: `r_wrist_x ... r_wrist_rz` (same, stage base at (0.35, -0.272, 1.15) m);
3. the left hand's finger targets, then the right hand's finger targets, in radians:
   - `sharpa`: 56 values; 22 Sharpa Wave finger targets per hand, `l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, then
     `r_hand_thumb_CMC_FE ... r_hand_pinky_DIP` (the left hand is the mirrored Wave);
   - `wuji`: 52 values; 20 Wuji Hand 2.2 finger targets per hand,
     `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, ..., l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3 ... r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start with every target at 0 clipped into its
range (stages at their base pose, open hands).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `56` wide for `sharpa` and `52` wide for `wuji`; `s.actuator_names` gives the exact order. Two hands of
the selected model, each on its own six-axis wrist stage (no arm): the left hand at the +y end of the tray, the right
hand at the -y end.

### Robot
You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The left hand hangs above the +y end of the tray, the right hand above the -y end,
fingers pointing down and palms facing the tray. Stages and fingers are position actuated in the physics engine under
native force bounds; lifting, carrying and setting down the tray require physical contact. The controller runs at 50 Hz,
with ten 2 ms physics substeps.

Each stage's `x, y, z` targets are displacements (metres, along the world axes) from its base: the left stage's at
(0.35, 0.272, 1.15) m, the right stage's at (0.35, -0.272, 1.15) m; the rotations are serial XYZ hinges at the wrist
(radians).

## Others
- The work area is too low to lift the tray over the steel bottle.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
