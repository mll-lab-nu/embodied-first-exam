# DexHand: Open a jam jar and set the lid aside

Open the jam jar with one dexterous hand and set its lid aside on the worktop. Scene (world frame, metres, z up): the worktop top is at z = 0.30 and spans |x| <= 0.45, |y| <= 0.40. A filled 297 ml glass jam jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.41) stands upright on the worktop centred at x = 0, y = 0. Nothing holds the jar: it stands on its own weight and glass-on-worktop friction, which resists only about 0.13 N m of twisting torque, so the hand must turn the lid without turning, sliding or tipping the jar. Its red 64.8 mm twist-off steel lid (32 g) is closed. Jar and lid are free rigid bodies. The closure is a lug thread made of contact geometry only: four inclined glass ramps on the jar neck hold four inward lugs of the lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive rotation about +z relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the gaps between the ramps (turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without lifting, the lugs run into the next ramps' leads, and turning clockwise from the closed position tightens and jams. The lid is lightly closed: no vacuum, seal adhesion or tightening torque is modelled, and the jam is part of the jar's rigid mass, not a fluid. Complete three stages in this order. (1) Unscrew: while the lid is still seated on the thread (lid origin less than 6 mm above its closed height and within 4 mm of the jar axis, in the jar frame), its counter-clockwise turn relative to the jar, unwrapped after every physics substep, reaches at least 1.049 rad. (2) Lift clear: afterwards, the lowest point of the lid skirt rises more than 30 mm above the jar rim. (3) Set aside: afterwards, for 50 consecutive controls (1 s), the lid touches the worktop and touches neither the hand nor the jar, is upright (tilt at most 0.15 rad), has its centre at least 90 mm horizontally from the jar axis, moves at most 0.02 m/s and turns at most 0.3 rad/s, while the jar touches the worktop, is not touched by the hand, is upright within 0.10 rad and moves at most 0.02 m/s. The episode ends with success at that moment; a partial sequence never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when: the jar tilts more than 15 degrees (jar_tipped), slides more than 30 mm horizontally from its start (jar_slid) or is lifted more than 15 mm (jar_lifted); the lid touches the worktop before stage 2 (lid_knocked_off); the lid drops: at any substep it touches nothing (no hand, jar or worktop contact) while its centre of mass moves downward faster than 0.3 m/s (about a 5 mm free fall; there is no window to catch it again), or its centre of mass moves downward faster than 1.0 m/s whatever it touches (lid_dropped); the jar or the lid touches the floor, its origin falls more than 5 mm below the worktop top or leaves the worktop footprint (lid_off_table, jar_off_table) or the workspace box x in [-0.45, 0.45] m, y in [-0.40, 0.40] m, z in [0.28, 0.80] m (object_left_workspace); the lid leaves the thread upward while its lugs are not in the gaps between the ramps, i.e. its turn modulo pi/2 is outside [1.019, 1.291] rad (lid_forced_through_thread); or the physics becomes unstable (unstable_physics). Later actions cannot undo a failure. Only robot actuator targets are allowed: one hand on its wrist stage, no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control a single dexterous hand mounted palm-down on a six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm, no second hand). The stage and the fingers are position actuated in the physics engine
under native force bounds; turning, lifting, carrying and releasing the lid require physical contact, and the jar is
held by nothing but its own weight and friction on the worktop. The controller runs at 50 Hz, with ten 2 ms physics
substeps. At reset the wrist targets are `(0, 0, 0.50)` m and `(0, 0, 0)` rad: the open hand hangs about 0.1 m above the
lid, fingers along +x.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang palm-down from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; wrist_rz turns the hand about the vertical through the stage origin, which sits about 4 cm below the palm.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world frame) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
quaternion). With `wrist_rx = wrist_ry = 0` the palm faces down, the fingers point along +x and the thumb along +y;
`wrist_rz` turns the hand about the vertical through the stage origin, which sits about 4 cm below the palm. The
finger targets follow in native actuator order, in radians:

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
s = Session("jar_lid_open")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("jar_lid_open", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.features()                              # stage, lid turn, clearance, contacts, tilts, speeds, failure details
s.status()                                # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the full physics and verdict state
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may observe everything in privileged mode: the MuJoCo model and state (`s.model`, `s.data`), `s.features()`
(stage, unwrapped lid turn, lid clearance above the rim, contacts, tilts, speeds, failure details) and renders from the
`overview`, `closeup` and `side` cameras. Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the
complete geometry (thread ramps and lugs included), failure checks and predicate. The world frame has z up; lengths
are in metres and angles in radians. The jar stands at the origin on the worktop, whose top is at z = 0.30 m; the lid
starts closed with its origin at z = 0.4009 m.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
