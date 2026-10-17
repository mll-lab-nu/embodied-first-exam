# DexHand: Replace the battery of a TV remote

Replace the battery of a TV remote that lies on the table. The remote's sliding battery door is shut and latched over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on the table and an empty receiving tray stands beside the remote. In this order: (1) release the door latch by pressing the door's spring-loaded thumb tab down and slide the door open until it is at least 0.060 m open (full travel 0.085 m); (2) move the gray cell out of the compartment into the tray, where it must rest on the tray floor: its centre inside the tray's inner box (|x| <= 0.037 m, |y| <= 0.032 m in the tray frame) and at most 0.014 m above the tray origin (the floor top is 0.003 m above the origin; a resting cell's centre is about 0.010 m above it), touching the tray floor, with no hand contact; (3) seat the green cell in the compartment slot with correct polarity: its centre within 5 mm (along the slot), 3 mm (across) and 2 mm (height) of the slot centre, lying on both cradle ribs, and its + end toward the gold contact (cell axis within 10 degrees of the remote's long axis, + end at the gold contact); (4) slide the door shut and let the latch engage: at most 0.002 m open with the thumb tab released (pressed at most 0.0015 m), so its hook sits in front of the latch stop. Then release everything: with no hand contact on the remote, door, tray or either cell, the gray cell still in the tray, the green cell still seated, the door still shut and latched and every task object at rest (linear speed of its body origin <= 0.02 m/s, angular speed <= 0.5 rad/s; for the cells and the tray the origin is the centre of mass), the condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; each stage counts only after the previous ones, and partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when any cell, the door, the remote or the tray falls below the table top (z < 0.30 m) or leaves the workspace box x in [-0.37, 0.47] m, y in [-0.34, 0.34] m, z in [0.30, 0.80] m, when any of them touches the floor, when the remote slides more than 0.03 m or tilts more than 15 degrees, when the tray slides more than 0.03 m or tilts more than 15 degrees, when the gray cell touches the table top, when the green cell touches the table top again after it has been lifted (lifted: at a control it is clear of the table and its centre is more than 0.01 m above its start height), when a cell without hand contact moves down faster than 0.886 m/s (the speed of a free drop from 0.04 m), or a cell touching nothing at all (no hand, no surface) moves down faster than 0.5 m/s (there is no grace period; a later catch does not undo it), when the parked left arm or the left hand touches the remote, its door, the tray or a cell (left_arm_contact; moving the left arm is not blocked, but the task is done by the right arm and hand), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets (arm joints and fingers) are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m (the floor is at z = -0.55 m). The remote lies
flat at (0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on
four rubber feet, at the approved scene's size (shell 160 x 64 mm, battery cavity 94 x 52 mm). Its battery door
slides along the remote's -x direction on a passive slide joint (travel 0 to 0.085 m, end stops at both ends, damping
0.1 N s/m, 0.08 N friction loss) and is latched shut: a spring-loaded thumb tab on the door (18 x 18 mm, 3 mm proud
of the door, a passive slide joint pressing down 0 to 5 mm against a 120 N/m spring) carries a hook that sits just in
front of a fixed latch stop at the remote's rear end while the door is shut. The door opens only while the tab is
pressed far enough (about 2.9 to 4.5 mm) for the hook to pass under the stop; it re-latches when it is slid fully
shut and the tab is released. Under the door is a one-cell compartment: the slot centre is at (-0.020, 0.0,
-0.00244) m in the remote frame, the gray cell lies there on two low cradle ribs with its + end toward the gold
contact at the slot's +x end (the silver - contact is at the -x end; 3 mm end play). The green replacement cell (a
23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on the table at (0.115, -0.110, 0.307) with its
+ end pointing 20 degrees clockwise from world +x (seen from above). The receiving tray (free rigid body, inner 74 x
64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). Modelling scope: the compartment holds one cell as in the source
scene; the source's compressible negative spring is not modelled (the terminals are fixed); there is no electrical
simulation. All objects move only through contact and these passive joints.

You control a fixed Tianji Marvin robot standing at the table (stand origin at (-0.45, 0.15, -0.45), facing +x) with
two 7-joint arms and a dexterous hand on each wrist; the right arm and hand do the task, the left arm hangs parked
beside the torso (keep its targets). Every arm and finger joint is a position servo inside MuJoCo 3.4.0 under native
force bounds; the arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held
target sags under the arm's weight unless your targets account for it). Grasping, carrying and releasing require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps per control.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and only the right arm/hand perform the task; one row is one 50 Hz control (ten 2 ms physics substeps).
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control holding a position target for every actuator (radians), in native actuator order:

- `sharpa` (58 values): 0-6 left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4,
  WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); 7-13 the same right-arm joints
  (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`; 36-57 the
  right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji` (54 values): 0-13 the same arm targets; 14-33 the left Wuji Hand 2.2 fingers `l_wuji_l_THJ0..3`,
  `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`; 34-53 the right Wuji fingers in the
  same order (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm pose (right hand above
the table near the robot, left arm parked); the frozen start targets of each hand are in `task.json`
(`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("remote_battery_swap")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("remote_battery_swap", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # door travel, tab depth, stage conditions, cell errors, contacts, failure
s.status()                                       # success, done, reason, steps, stage (latched stages), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.snapshot(), s.restore(snap)                    # save / restore the full simulator and predicate state
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json` (the `checker` block holds every threshold), `scene.py`, `checker.py` and `runtime.py`
for the complete geometry, failure checks and predicate. `s.features()["conditions"]` reports the four stage
conditions, `s.status()["stage"]` the number of stages completed in order and `hold_steps` the released-hold count.
You may read the full simulator state and use `s.snapshot()` / `s.restore()` while authoring; only the rows you hand
in are graded.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
