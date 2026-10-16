# DexHand: Load two punched pages into a ring binder

Load both punched pages into the open-front ring binder on the desk. The binder (free on the desk, back cover towards +x) has three 1-inch round split rings on two toggle plates with an over-centre spring: both plates rest closed at 0 rad and open at 0.60 rad, and a booster paddle at each end of the mechanism opens them when pressed down. Two rigid punched pages (139.7 x 215.9 mm, 6 g, three 6.35 mm holes 9.5 mm from the binding edge) lie loose and flat on the desk, printed face up, holes towards the binder (-x), as in the source scene. Complete these stages in order. (1) Rings opened: both toggle plates at 0.50 rad or more. (2) Pages placed: with the rings still open (0.50 rad or more), every one of the six holes is threaded by the right ring half of its own station (the ring wire centre line crosses the page plane exactly once within 3.5 mm of the hole centre, the left half not at all), no hand contact on either page, each page touches the binder or the other page, and each page centre (60 mm from the hole line into the sheet) lies over the back cover: binder-frame x in (0.03, 0.16) m, |y| < 0.03 m, z in (-0.01, 0.06) m. (3) Rings closed: both toggle plates at 0.05 rad or less, every hole linked exactly once by its closed ring (one crossing within 3.5 mm of the hole centre) and both page centres over the back cover. (4) Release: the stage-3 condition with no hand contact on any page or any binder part, both pages resting on the binder and each page staying within 2 mm and 0.03 rad of its pose at the start of the window, for 50 consecutive controls (1 s). The episode ends with success at that moment; one page, an unthreaded hole or open rings never count. The episode ends at once with failure, checked after every 2 ms physics substep, when a page touches the floor; when a page has no contact at all, falls faster than 0.2 m/s and no ring runs through any of its holes (dropped); when a page origin goes more than 2 mm below the desk top (z < 0.698 m) or leaves the workspace x in [0.20, 0.98] m, y in [-0.38, 0.48] m, z in [0.698, 1.10] m; when the binder moves more than 0.03 m horizontally from its start or tilts more than 0.35 rad; when a ring wire penetrates a page deeper than 1.2 mm or a hand part penetrates a page deeper than 3 mm (a ring can only enter a page through its hole); or when the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed; the rings, plates, boosters and covers move only through contact and their passive joints. Pages may slide on the desk and hang over its edge (a page touching the desk is not a failure). Pages are stiff cardstock plates: paper bending is not modelled. At most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene and modelling notes
The binder is free on the desk: back cover (with the ring mechanism near its spine edge) towards +x, spine and front
cover on passive hinges towards -x. Its two toggle plates carry the three ring halves on each side; an over-centre
housing spring (a passive spatial tendon) holds them either closed (0 rad) or open (0.60 rad), and the plates and the
two booster paddles are coupled by the binder's internal linkage (passive joint couplings, never attached to the hand).
Pressing a booster paddle down opens the rings; pushing the plates back past the over-centre point (for example by
pressing the raised inner edges of the open plates down) closes them.
Simplifications, stated plainly: the pages are rigid 0.8 mm cardstock plates (paper bending, creasing and tearing are
not modelled; the holes are octagonal openings 6.35 mm across flats); as in the source scene the two sheets start loose and
flat on the desk (a hand can drag a page so that its far edge overhangs the desk edge, then pinch it); the binder geometry is
an authored reconstruction (Avery 05806 dimensions), not manufacturer CAD.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world-aligned offsets from `wrist_base`) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a
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
s = Session("binder_page_load")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("binder_page_load", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # toggle angles, threaded/linked holes, contacts, page poses
s.status()                                      # success, done, reason, steps, stage (0..4), total_stages, hold_steps
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "rings", "pages"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m, the
binder starts at (0.48, 0.00, 0.705) with its back cover towards +x, and the pages lie flat on the desk with their middle hole centres at
`task.json` `page_xy` (0.71, 0.22) and (0.71, -0.025), z = 0.7004 m (page frame: origin at the middle hole centre, +x
across the sheet away from the holes, +z the printed face); the desk's +x edge is at x = 0.98 m. The wrist-stage targets are offsets from `task.json` `wrist_base` (0.62, 0.00, 0.70); at zero wrist
rotation the fingers point down (-z) and the palm faces +x.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
