# DexHand: Whisk batter in a bowl, drain and set the whisk down

Whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the counter. The hand starts holding the balloon whisk upright just above the free-standing bowl (its 25 mm handle in a closed grasp). The batter is not simulated: whisking is measured on the whisk-head point, 20 mm above the wire tip on the whisk axis, which is in the batter while it is between 3 mm above the bowl origin and the batter surface (35.7 mm above the bowl origin) and at least 4 mm inside the bowl wall. Complete four stages in order. (1) Immersed: the head point enters the batter. (2) Whisked: the head point circles the bowl axis by at least 5 full revolutions of net (signed, unwrapped) angle while it stays in the batter; leaving the batter before 5 revolutions resets the count to zero, and controls with the head point closer than 8 mm to the bowl axis add nothing. (3) Drained: while the hand touches the whisk, the wire tip is at least 10 mm above the bowl rim, the head point is within 55 mm of the bowl axis (over the opening) and the whisk hangs head-down within 30 degrees of vertical, for 25 consecutive controls (0.5 s). (4) Set down: lower the whisk until it touches the counter top while the hand still touches it (it is then placed), then let go; the episode succeeds when, for 50 consecutive controls (1 s), the whisk touches the counter top, touches neither the hand nor the bowl, lies within 30 degrees of horizontal with its centre of mass at least 120 mm from the bowl axis, and its centre of mass moves slower than 0.02 m/s and it turns slower than 0.3 rad/s. The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every control, when: the bowl tilts more than 10 degrees, slides more than 30 mm or rises more than 20 mm from its start; the whisk touches nothing, its lowest point is more than 2 mm above the counter top and its centre of mass moves downward faster than 0.2 m/s (dropped); before it is placed, the whisk touches the counter or is out of hand contact for more than 10 consecutive controls (dropped); after it is placed, the whisk touches neither the hand nor the counter for more than 5 consecutive controls (tossed); the bowl or the whisk touches the floor, has its centre of mass below the counter top (z < 0.68 m) or outside the workspace x in [0.25, 0.99] m, y in [-0.36, 0.36] m, z in [0.60, 1.50] m; or the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct forces. The episode allows at most 4000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds; the
whisk moves only through contact with the hand, the bowl and the counter. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage with the same wrist joints, ranges, gains and start targets: wrist_x/y/z are the world position of the grip point (on the whisk handle axis inside the closed hand at the start), wrist_rx/ry/rz serial XYZ rotations about it; each hand starts from its own frozen, settled grasp of the whisk.
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
wrist_z` (metres, world position of the grip point on the whisk handle axis inside the closed hand at the start) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints about that point), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). The episode starts with the whisk held in a settled grasp, wrist targets (0.58, 0.0, 1.07) m and
zero rotations; holding the current targets keeps the grasp. Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most
10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has
no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.68 m;
the bowl starts centred at (0.58, 0.0) m. Cameras are overview, closeup and side, at 640 x 480. Requests can return
RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting
per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets
for up to 30 s and records those steps. Calling it without seconds only observes the current state. Forward
kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
