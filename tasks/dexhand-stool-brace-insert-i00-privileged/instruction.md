# DexHand: Assemble a wooden stool cross brace

Assemble the cross brace of a pine stool dry frame. The lower side frame lies flat on the table with its four bores facing up and three rails already standing seated in three of them. The loose cross brace (a 0.26 m pine rail with an 8 mm dowel exposed 15 mm at each end) lies on the table, and the opposite side frame lies upside down beside the lower frame. Pick up the brace, seat one of its dowels in the empty bore of the lower frame, then lift the opposite side frame and lower it onto all four upper dowels so that both brace dowels end up seated in their legs. Ordered stages: (1) brace lifted: no brace-table contact, brace centre raised at least 0.05 m and its lowest bounding-box corner at least 0.02 m above the table top; (2) one brace dowel seated in a lower-frame bore; (3) opposite side frame lifted (the same lift test); (4) assembled: each of the eight bores holds exactly one seated dowel and every rail, the brace included, has one dowel seated in each side frame. A dowel is seated in a bore when its tip is 12 mm to 19 mm past the bore entry along the bore axis (12 mm is 80% of the exposed dowel), its tip is within 1.6 mm of the bore axis and the dowel axis is within 0.105 rad of the bore axis. Success: after stage 4 the assembled condition holds with no hand contact on any frame or rail and every part's centre-of-mass speed at most 0.02 m/s and angular speed at most 0.2 rad/s for 50 consecutive controls (1 s); the episode then ends. A single seated brace dowel or any partial assembly never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the lower frame moves more than 0.03 m or tilts more than 10 degrees; a pre-seated rail is pulled to less than 8 mm in its bore or tilts more than 10 degrees; the brace touches the table after stage 1, or its centre drops below 0.09 m above the table top after stage 1; the brace tilts more than 20 degrees after stage 2; the opposite side frame touches the table after stage 3 or tilts more than 20 degrees from its upside-down carrying orientation after stage 3; any part with no contact at all (not held, not supported) has its centre of mass falling faster than 0.2 m/s (a drop); any part touches the floor, has its centre below the table top (z < 0.74 m) or leaves the workspace box x in [0.23, 1.23] m, y in [-0.73, 1.03] m, z in [0.70, 1.60] m; or the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed: no object teleports, grasp welds, scripted object motion or direct object forces. All parts are free rigid pine bodies; the bores are hollow contact geometry of the source size (4.1 mm radius for the 4.0 mm dowels: 0.1 mm radial clearance, no entry chamfer); glue, screws, the seat and load capacity are not modelled. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with
ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the wrist x/y/z targets are offsets from the stage origin (stage origin (0.55, -0.1, 1.15) m) along the world axes, and at zero wrist angles the palm faces down with the fingers along +x.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin `task.json` `stage_origin`, along the world
axes) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion). At zero wrist angles the palm
faces down, the fingers point along +x and the thumb is on the +y side. The finger targets follow in native actuator
order, in radians:

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
s = Session("stool_brace_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("stool_brace_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # stage flags, per-dowel depth/lateral/axis, contacts, speeds, failure
s.status()                                      # success, done, reason, steps, stage, total_stages (4)
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save / restore the full physics and verdict state
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "side"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The table top is at
z = 0.74 m; the lower side frame is centred at `task.json` `lower_frame_pos`, the opposite side frame at
`upper_frame_pos` (upside down) and the brace at `brace_pos` (lying along x). Bore entries and dowel tips are MuJoCo sites
(`<frame>_leg_<m|p>_b<k>_entry`, `<rail>_tip_<m|p>`).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
