# DexHand: Install a desk fan front guard

Install the front guard on the desk fan. The unpowered fan stands on the worktop facing the operator (its axis points along world -x); its rear wire guard carries four perimeter U clips at 45, 135, 225 and 315 degrees. All four clips start swung open (hinge angle 1.40 rad); the hand has to close every one of them. A closed lower clip (225 or 315 degrees) forms an open-topped U channel that can carry the guard's rim. The detached front guard (0.369 m wire cage, 185 g, with a raised hub cap at its centre) lies flat on the worktop, dome up. Lift the guard, turn it upright with its dome facing the operator, seat its rim on the rear rim, close all four clips over the two rims (the lower clips may be closed before or after the guard is seated; the upper clips can only lock over a seated guard), and take the hand away. Success requires, in order: (1) the guard seated: guard centre within 5 mm of the fan axis, axial seat error within 2.5 mm and guard axis within 5 degrees of the fan axis; (2) the guard still seated, all four clip hinges in their locked range (hinge angle at most 0.12 rad) and the guard rim inside every clip's U channel (in each clip's frame, with origin at its hinge, x toward the operator along world -x and y radially outward, the guard-rim point nearest that clip lies at x from 6.8 to 9.9 mm for the upper clips and 6.8 to 8.6 mm for the lower clips and y from -4.8 to -2.2 mm, i.e. between the rear rim and the clip's lip and inside its bridge), each upper clip having locked at or after the first control at which the guard was seated; (3) the complete condition with no hand contact on the guard, the clips or the fan, guard speed at most 0.02 m/s and angular speed at most 0.2 rad/s, for 50 consecutive controls (1 s). The episode ends with success at that moment; a guard that is only placed, or clips that are only partly closed, never count. The episode ends immediately with failure, checked after every 2 ms physics substep, when the fan moves more than 3 cm from its start or tilts more than 0.10 rad, when the guard touches the worktop, a table leg or the floor after its centre of mass has been lifted more than 5 cm above its resting height (dropped or set back down), or at the first substep at which the guard touches nothing while its centre of mass falls faster than 0.2 m/s (dropped, even if caught again), when the guard touches the fan's base, stem, neck, motor housing, feet or buttons, when the guard's centre of mass falls below the worktop (z < 0.65 m) or leaves the workspace box x in [0.20, 1.10] m, y in [-0.55, 0.55] m, z in [0.60, 1.40] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The clips are rigid U channels on passive hinges held by an elastic over-centre spring (a modelled snap detent); the guard is a rigid wire cage. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Scene facts (world frame, metres and radians, z up)
- Worktop: top at z = 0.65, spanning x in [0.28, 1.08], y in [-0.50, 0.50].
- Fan (free body on four rubber feet, 2.15 kg with its clips): body frame starts at (0.73, 0.18, 0.952) with the cage
  axis along world -x. The rear rim (radius 0.1845, wire radius 0.0018) lies in the plane x = 0.73.
- Clip hinges (fixed to the fan; hinge axis tangential to the rim; angle 0 closed over both rims, 1.40 open, the
  elastic detent's over-centre point at 0.70): 45 deg (0.734, 0.3128, 1.0848), 135 deg (0.734, 0.0472, 1.0848),
  225 deg (0.734, 0.0472, 0.8192), 315 deg (0.734, 0.3128, 0.8192). All four clips start open at 1.40 (as in the source
  scene). A closed lower clip (225 or 315 deg) forms an open-topped U channel that can carry the guard's rim; an upper
  clip only counts when it locks at or after the first seated control.
- Front guard (rigid, 0.185 kg): rim radius 0.1845 (wire radius 0.0018), dish 0.047 deep toward the operator, a hub
  cap of radius 0.043 and height 0.022 at its centre (front face 0.057 in front of the rim plane), centre of mass
  0.018 in front of the rim plane on the axis. It starts flat on the worktop, dome up, rim centre at
  (0.48, -0.275, 0.6518).
- Seat: the guard is seated with its centre at (0.72635, 0.18, 0.952), i.e. 3.65 mm in front of the rear-rim plane,
  axis along world -x; the stage-1 tolerances in the task text are measured from this pose in the fan's frame.
- Wrist stage: targets are world positions x in [-0.2, 1.0], y in [-0.6, 0.6], z in [0.35, 1.55] and serial XYZ
  angles in [-3.14, 3.14]; it starts at (0.40, 0.00, 0.95, 3.0, 0, 0) (palm down, fingers along +x).
- Cameras (640 x 480): `overview` at (-0.06, -0.84, 1.40) looking at (0.60, -0.07, 0.84), fovy 45; `closeup` at
  (0.20, -0.27, 1.22) looking at (0.72, 0.17, 1.00), fovy 55.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets.
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
s = Session("fan_guard_install")                # default hand: DEXHAND_HAND or "sharpa"
s = Session("fan_guard_install", hand="wuji")   # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # seat errors, clip angles, contacts, guard speed, failure details
s.status()                                      # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `geometry.py`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry,
failure checks and predicate. In privileged mode you may read the complete simulator state (object poses, contacts,
clip angles, `s.features()`); the scene facts above are the frozen values.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
