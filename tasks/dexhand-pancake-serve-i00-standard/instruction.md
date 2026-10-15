# DexHand: Serve a pancake from a frying pan with a spatula

Serve the pancake from the frying pan onto the plate using the kitchen turner (spatula) that the hand already holds. The pancake lies in the frying pan, the empty ceramic plate stands beside it on the counter, and the turner starts in a power grasp of the hand. Only the turner may move the pancake: slide its blade under the pancake, lift it out of the pan on the blade, carry it to the plate, set it down in the plate and withdraw the turner. Success requires three stages in this order. (1) On the blade: the pancake touches the turner blade and no other object (no pan, plate, hand, counter or floor contact), its origin is at least 0.015 m above its starting height and it is tilted at most 30 degrees, for 10 consecutive controls. (2) Over the plate: later, while still touching only the turner, the pancake centre is within 0.058 m (horizontally) of the plate centre and above the plate floor. (3) Served: later, the pancake touches only the plate, its centre is within 0.058 m of the plate centre horizontally (the whole pancake inside the plate's 0.128 m rim radius), it is tilted at most 20 degrees from flat, its linear speed is at most 0.02 m/s and angular speed at most 0.3 rad/s, the turner does not touch it and every point of the blade outline is at least 0.08 m from the pancake centre horizontally (withdrawn); this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; skipping or reordering a stage never counts. The episode ends immediately with failure, checked after every 1 ms physics substep with no grace period, when the pancake touches the counter top or the floor, falls freely (touching nothing while its centre of mass moves down faster than 0.35 m/s, i.e. after about 6 mm of free fall) or its origin falls below the counter top (z < 0.85 m), when any part of the hand touches the pancake, when the turner touches the floor, falls out of the hand (no hand contact while its centre of mass moves down faster than 0.35 m/s) or its origin falls below the counter top, when the pan or the plate moves more than 0.03 m from its starting position or tilts more than 15 degrees, when the pancake, pan, plate or turner leaves the workspace box x in [0.23, 1.13] m, y in [-0.65, 0.45] m, z in [0.80, 1.50] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The pancake is a rigid coherent disk and the turner blade bends through three passive spring hinges. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
the turner is held only by finger and palm contact, and the pancake moves only through contact with the turner, the
pan and the plate. The controller runs at 50 Hz, with twenty 1 ms physics substeps per control.

## Scene and modelling
The scene reproduces a 22 cm non-stick frying pan (0.90 kg, free on the counter), an OXO flexible kitchen turner
(0.15 kg), a ceramic plate (0.48 kg, free) and one cooked pancake (0.06 kg, about 140 mm across and 9.5 mm thick) on
an oak counter whose top is at z = 0.85 m. Declared simplifications: the pancake is a single rigid coherent body (no
bending, tearing, heat or fluid); the turner's thin steel-core blade is three rigid strips joined by passive spring
hinges (+-0.35 rad); concave pan and plate interiors use convex sector contact shapes. Pair friction coefficients are
estimates: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, hand-turner grip 1.2, objects on
the counter 0.7. The episode starts with the turner already held in a settled power grasp: the frozen reset places
the hand, turner, pan, plate and pancake in a state that was reached by closing the fingers on the handle and letting
the whole scene settle under physics; the turner is held only by contact (there is no weld or attachment), so opening
the fingers drops it. Physics runs at 1 ms steps, twenty per 50 Hz control.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage (world-frame x, y, z slides in metres, then serial X, Y, Z hinges in radians), with the same joint ranges, gains and start targets; the reset grasp of the turner is hand-specific.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`) and the exact order. The episode record names the hand, and grading replays with that hand.

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then replays the graded episode with the
recorded hand in two fresh processes. Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets `wrist_x, wrist_y,
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). The episode starts with the turner in a settled grasp; holding the start finger targets keeps
it. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of
0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear
interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured poses
use WXYZ; world z is up and the counter top is at z = 0.85 m. Cameras are overview, closeup and side, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
