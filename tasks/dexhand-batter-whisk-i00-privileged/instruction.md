# DexHand: Whisk batter in a bowl, drain and set the whisk down

Pick up the balloon whisk, whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the counter. The whisk starts at rest, leaning on the bowl rim with its handle end on the counter (where it settles when released from the source scene's start pose, standing in the bowl); both hands start open. The batter is not simulated: whisking is measured on the whisk-head point, 20 mm above the wire tip on the whisk axis, which is in the batter while it is between 3 mm above the bowl origin and the batter surface (35.7 mm above the bowl origin) and at least 4 mm inside the bowl wall. Complete five stages in order. (1) Picked up: a hand holds the whisk clear of everything else, i.e. the robot touches it, it touches neither the counter nor the bowl and its lowest point is at least 30 mm above the counter top, for 10 consecutive controls. (2) Immersed: the head point enters the batter. (3) Whisked: the head point circles the bowl axis by at least 5 full revolutions of net (signed, unwrapped) angle while it stays in the batter; leaving the batter before 5 revolutions resets the count to zero, and controls with the head point closer than 8 mm to the bowl axis add nothing. (4) Drained: while the robot touches the whisk, the wire tip is at least 10 mm above the bowl rim, the head point is within 55 mm of the bowl axis (over the opening) and the whisk hangs head-down within 30 degrees of vertical, for 25 consecutive controls (0.5 s). (5) Set down: lower the whisk until it touches the counter top while the robot still touches it (it is then placed), then let go; the episode succeeds when, for 50 consecutive controls (1 s), the whisk touches the counter top, touches neither the robot nor the bowl, lies within 30 degrees of horizontal with its centre of mass at least 120 mm from the bowl axis, and its centre of mass moves slower than 0.02 m/s and it turns slower than 0.3 rad/s. The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every control, when: the bowl tilts more than 10 degrees, slides more than 30 mm or rises more than 20 mm from its start; after the pickup, the whisk touches nothing, its lowest point is more than 2 mm above the counter top and its centre of mass moves downward faster than 0.2 m/s (dropped); after the pickup and before it is placed, the whisk touches the counter or is out of robot contact for more than 10 consecutive controls (dropped); after it is placed, the whisk touches neither the robot nor the counter for more than 5 consecutive controls (tossed); the bowl or the whisk touches the floor, has its centre of mass below the counter top (z < 0.68 m) or outside the workspace x in [0.25, 0.99] m, y in [-0.36, 0.36] m, z in [0.60, 1.50] m; or the physics becomes unstable. Before the pickup the whisk may be nudged or slide off the rim; the counter, floor and workspace rules still apply. Later actions cannot undo a failure. "Robot" means any hand, arm link or the stand. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct forces. The episode allows at most 4000 controls at 50 Hz; reaching that limit without success is a failure.

The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand
on each wrist (robot id `marvin-bimanual-sharpa-wave`). Every arm and finger joint is a position servo in the physics
engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity
compensation** (a held target sags by about 1 cm at the hand under load unless your targets account for it). The bowl
and the whisk move only through contact with the hands, the arms, each other and the counter. The controller runs at
50 Hz, with ten 2 ms physics substeps. World frame: metres and radians, +z up, +x forward from the robot stand, +y to
the robot's left.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`). The right arm/hand picks up and uses the whisk; the left arm/hand may steady the bowl.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control with a position target for every actuator, in model order (`s.actuator_names`):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (each name + `_target`); columns 7-13: the right arm `..._R_J1` to `..._R_J7`;
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers (`l_wuji_*`, vendor order), columns 34-53 the
  right Wuji fingers (`r_wuji_*`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start open above the counter with the arms in a
ready pose (`task.json` `reset_state[<hand>]`: joint positions and start targets); `s.hold_action()` at reset keeps
that pose. The whisk does not start in a hand: it rests against the bowl rim with its handle end on the counter, where
it settles when released from the source scene's start pose (standing in the bowl). The left hand may steady the bowl
(for example while the right hand lifts the whisk off its rim); the success predicate does not require it.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
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
s.features()                              # stage, pickup/revolutions/drain/hold counters, contacts, bowl tilt/slide
s.status()                                # success, done, reason, steps, stage, total_stages (5)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the simulation and verdict state (planning)
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate, and `arm_rig.py` for the robot. The counter top is at z = 0.68 m (front edge x = 0.25 m), the bowl origin
(its outer bottom) starts at (0.58, 0.0, 0.6805) m, its rim is 78 mm above that origin; the whisk frame has its origin at
the wire tip and +z along the handle (handle from 230 mm to 345 mm); at reset the wire tip is at about (0.576, -0.005,
0.813) m and the handle points down to the counter toward (-0.30, -0.88, -0.36) (`task.json` `reset_state`).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
