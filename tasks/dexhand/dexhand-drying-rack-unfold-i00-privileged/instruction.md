# DexHand: Unfold a folding sweater dryer and stand it on its legs

Set up the folding sweater dryer on the kitchen counter with the dexterous hand. It starts fully folded and stored underside up, its four legs folded between the two frame halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and stand it on its four feet, then let go: success needs the fold angle at most 0.314 rad, every leg at least 1.571 rad, the rack upright within 10 degrees on all four feet and nothing else, untouched by the hand and still for 50 consecutive controls (1 s). Dropping the rack, pushing it off the counter, or letting it collapse or fall over after it stands ends the episode as a failure at once.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, turning and releasing the rack require physical contact. The controller runs at 50 Hz, with ten
2 ms physics substeps.

## Scene
The rack is a folding sweater dryer: two rectangular frame halves (each 0.33 m x 0.65 m, 0.205 kg, tube rims, end
poles and corner housings; the woven net between the rims is drawn only and has no collision) joined by a passive
pole hinge on the two side rims (`fold_hinge`: 0 rad = open flat, pi rad = folded; damping 0.001 N m s/rad, dry
friction 0.0005 N m). Each half carries two offset legs (0.025 kg, 0.098 m long, ball foot) on passive hinges
`fixed_leg_l_hinge`, `fixed_leg_r_hinge`, `moving_leg_l_hinge`, `moving_leg_r_hinge` (0 rad = folded flat against the
frame, 1.745 rad = 100 degrees = open stop; damping 0.03 N m s/rad, dry friction 0.003 N m). There is no latch: an
open leg stays open because its stop is 10 degrees past vertical, so the weight of the standing rack presses it onto the
stop. The rack is a free body of 0.51 kg. It starts fully folded and stored underside up on the counter (the legs of both
halves are sandwiched between them), exactly as in the scene's storage pose. The counter top is at z = 0.75 m and spans
x in [-0.13, 1.37] m, y in [-0.48, 0.48] m; the folded rack lies near (0.30, 0.0). Geometry, masses and contact
parameters are in `/opt/tools/scene.py` and `/opt/tools/task.json`.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage (origin above the counter), with the same wrist joints, ranges, gains and start targets.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion).
The three prismatic joints are offsets of the hand mount from the stage origin (0.62, 0, 0.75) m along the world axes
(ranges x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0] m; rx and rz [-3.3, 3.3], ry [-1.6, 1.6] rad). At zero rotation
the hand hangs palm down with the fingers along +x and the thumb toward +y. The finger targets follow in native actuator
order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets (the hand
0.3 m to the -y side of the stage origin, 0.45 m above the counter, fingers open); the frozen start pose of each hand is
in `task.json` (`initial_targets`).

## Success and failure
The episode is evaluated after every control from simulator state only, in this order:

1. **Unfolded**: the fold angle is at most 0.314 rad (at least 90 % of the opening stroke) and each of the four leg
   angles is at least 1.571 rad (90 degrees, at least 90 % of the leg stroke).
2. **Standing** (only after stage 1): the stage-1 condition holds, the rack's up axis (the normal of the fixed half,
   legs pointing down) is tilted at most 10 degrees from vertical, all four feet touch the counter and no other rack
   part touches it.
3. **Released hold**: the stage-2 condition holds, no hand geometry touches the rack, and every rack body moves at most
   0.02 m/s and 0.2 rad/s (centre-of-mass velocities), for 50 consecutive controls (1 s). The episode ends with success
   at that control.

A partly open rack, a rack on fewer than four feet, a rack resting on a frame part, or a rack that is still held never
counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when

- any rack collision part's centre is below the counter top (z < 0.75 m), outside the counter footprint
  x in [-0.13, 1.37] m, y in [-0.48, 0.48] m, or more than 0.9 m above the counter;
- the rack touches the floor or the counter cabinet;
- the rack touches neither the counter nor the hand while its centre of mass falls faster than 0.05 m/s (dropped);
- after stage 2: the rack tilts more than 20 degrees (fell over), or the fold angle exceeds 0.314 rad or any leg angle
  drops below 1.571 rad (collapsed);
- the physics becomes unstable, or 6000 controls pass without success.

Later actions cannot undo a failure. Only hand and wrist-stage actuator targets are allowed; there are no welds,
attachments, scripted object motion or object forces.

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
s = Session("drying_rack_unfold")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("drying_rack_unfold", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # fold and leg angles, tilt, foot/hand contacts, rack speeds, stage
s.status()                                      # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save and restore the full episode state (search, planning)
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "side", "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
