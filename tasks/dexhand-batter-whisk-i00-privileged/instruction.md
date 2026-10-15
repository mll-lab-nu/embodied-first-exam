# DexHand: Whisk batter in a bowl, drain and set the whisk down

Whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the counter. The hand starts holding the balloon whisk upright just above the free-standing bowl (its 25 mm handle in a closed grasp). The batter is not simulated: whisking is measured on the whisk-head point, 20 mm above the wire tip on the whisk axis, which is in the batter while it is between 3 mm above the bowl origin and the batter surface (35.7 mm above the bowl origin) and at least 4 mm inside the bowl wall. Complete four stages in order. (1) Immersed: the head point enters the batter. (2) Whisked: the head point circles the bowl axis by at least 5 full revolutions of net (signed, unwrapped) angle while it stays in the batter; leaving the batter before 5 revolutions resets the count to zero, and controls with the head point closer than 8 mm to the bowl axis add nothing. (3) Drained: while the hand touches the whisk, the wire tip is at least 10 mm above the bowl rim, the head point is within 55 mm of the bowl axis (over the opening) and the whisk hangs head-down within 30 degrees of vertical, for 25 consecutive controls (0.5 s). (4) Set down: lower the whisk until it touches the counter top while the hand still touches it (it is then placed), then let go; the episode succeeds when, for 50 consecutive controls (1 s), the whisk touches the counter top, touches neither the hand nor the bowl, lies within 30 degrees of horizontal with its centre of mass at least 120 mm from the bowl axis, and its centre of mass moves slower than 0.02 m/s and it turns slower than 0.3 rad/s. The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every control, when: the bowl tilts more than 10 degrees, slides more than 30 mm or rises more than 20 mm from its start; the whisk touches nothing, its lowest point is more than 2 mm above the counter top and its centre of mass moves downward faster than 0.2 m/s (dropped); before it is placed, the whisk touches the counter or is out of hand contact for more than 10 consecutive controls (dropped); after it is placed, the whisk touches neither the hand nor the counter for more than 5 consecutive controls (tossed); the bowl or the whisk touches the floor, has its centre of mass below the counter top (z < 0.68 m) or outside the workspace x in [0.25, 0.99] m, y in [-0.36, 0.36] m, z in [0.60, 1.50] m; or the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct forces. The episode allows at most 4000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds; the
whisk moves only through contact with the hand, the bowl and the counter. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage with the same wrist joints, ranges, gains and start targets: wrist_x/y/z are the world position of the grip point (on the whisk handle axis inside the closed hand at the start), wrist_rx/ry/rz serial XYZ rotations about it; each hand starts from its own frozen, settled grasp of the whisk.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame: the position of the grip point, which lies on the whisk handle axis
inside the closed hand at the start) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints about that point,
not a quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start with the wrist targets at the grip point
`task.json` `stage.origin` = (0.58, 0.0, 1.07) m and zero rotations; each hand starts from its own frozen, settled grasp
of the whisk (`task.json` `reset_state[<hand>]`, joint positions and start targets). `s.hold_action()` at reset keeps
that grasp.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or `(T, 26)`
for `wuji`, at most 4000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("batter_whisk")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("batter_whisk", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, revolutions, drain/hold counters, contacts, bowl tilt/slide, failure
s.status()                                # success, done, reason, steps, stage, total_stages (4)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the simulation and verdict state (planning)
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.68 m,
the bowl origin (its outer bottom) starts at (0.58, 0.0, 0.6805) m, its rim is 78 mm above that origin; the whisk
frame has its origin at the wire tip and +z along the handle (handle from 230 mm to 345 mm).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
