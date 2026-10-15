# DexHand: Replace the battery of a TV remote

Replace the battery of a TV remote that lies on the table. The remote's sliding battery door is closed over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on the table and an empty receiving tray stands beside the remote. In this order: (1) slide the door open until it is at least 0.060 m open (full travel 0.085 m); (2) move the gray cell out of the compartment into the tray, where it must rest on the tray floor: its centre inside the tray's inner box (|x| <= 0.037 m, |y| <= 0.032 m in the tray frame) and at most 0.014 m above the tray origin (the floor top is 0.003 m above the origin; a resting cell's centre is about 0.010 m above it), touching the tray floor, with no hand contact; (3) seat the green cell in the compartment slot with correct polarity: its centre within 5 mm (along the slot), 3 mm (across) and 2 mm (height) of the slot centre, lying on both cradle ribs, and its + end toward the gold contact (cell axis within 10 degrees of the remote's long axis, + end at the gold contact); (4) slide the door shut (at most 0.004 m open). Then release everything: with no hand contact on the remote, door, tray or either cell, the gray cell still in the tray, the green cell still seated, the door still shut and every task object at rest (linear speed of its body origin <= 0.02 m/s, angular speed <= 0.5 rad/s; for the cells and the tray the origin is the centre of mass), the condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; each stage counts only after the previous ones, and partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when any cell, the door, the remote or the tray falls below the table top (z < 0.30 m) or leaves the workspace box x in [-0.37, 0.47] m, y in [-0.34, 0.34] m, z in [0.30, 0.80] m, when any of them touches the floor, when the remote slides more than 0.03 m or tilts more than 15 degrees, when the tray slides more than 0.03 m or tilts more than 15 degrees, when the gray cell touches the table top, when the green cell touches the table top again after it has been lifted (lifted: at a control it is clear of the table and its centre is more than 0.01 m above its start height), when a cell without hand contact moves down faster than 0.886 m/s (the speed of a free drop from 0.04 m), or a cell touching nothing at all (no hand, no surface) moves down faster than 0.5 m/s (there is no grace period; a later catch does not undo it), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Scene
World frame: z up, metres and radians; the table top is at z = 0.30 m. The remote lies flat at
(0.0, 0.0, 0.32) with its long axis along world x; it is a free rigid body of 0.35 kg (a weighted handset) on four
rubber feet. Its battery door slides along the remote's -x direction on a passive slide joint (travel 0 to 0.085 m,
end stops at both ends); a light friction hold (0.25 N friction loss) keeps it where it is left, and a 3 mm raised
ridge across the door gives a fingertip something to push against. Under the door is a one-cell compartment: the
slot centre is at (-0.020, 0.0, -0.00244) m in the remote frame, the gray cell lies there on two low cradle ribs
with its + end toward the gold contact at the slot's +x end (the silver - contact is at the -x end; 3 mm end play).
The green replacement cell (a 23 g rigid cylinder, radius 7 mm, 49 mm long, like the gray one) lies on the table at
(0.115, -0.110, 0.307) with its + end pointing 20 degrees clockwise from world +x (seen from above). The receiving
tray (free rigid body, inner 74 x 64 mm, 18 mm walls) stands at (0.16, 0.10, 0.303). The hand starts above and to
the side of the remote. Modelling scope: the remote shell is the approved scene's model widened 1.25 times across
(80 mm wide, cavity 65 mm) so two fingertips fit beside one cell; the original door latch tab and the compressible
negative spring are not modelled (the door is held by friction only, the terminals are fixed); the compartment holds
one cell; there is no electrical simulation. All objects move only through contact and these passive joints.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics
substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets.
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
joint positions, velocities, actuator efforts, wrist pose and current targets; object poses, contacts and the stage
conditions are not published; the service reports only whether the episode ended (`done`, with reason `success` or
`task_failure`). An episode ends at the first success
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
`r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the table top is at z = 0.30 m. Cameras are overview, closeup and top, at 640 x 480.
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
