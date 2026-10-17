# DexHand: Assemble a wooden stool cross brace

Assemble the cross brace of a pine stool dry frame. The lower side frame lies flat on the table with its four bores facing up and three rails already standing seated in three of them. The loose cross brace (a 0.26 m pine rail with an 8 mm dowel exposed 15 mm at each end) lies on the table, and the opposite side frame lies upside down beside the lower frame. Pick up the brace, seat one of its dowels in the empty bore of the lower frame, then lift the opposite side frame and lower it onto all four upper dowels so that both brace dowels end up seated in their legs. Ordered stages: (1) brace lifted: no brace-table contact, brace centre raised at least 0.05 m and its lowest bounding-box corner at least 0.02 m above the table top; (2) one brace dowel seated in a lower-frame bore; (3) opposite side frame lifted (the same lift test); (4) assembled: each of the eight bores holds exactly one seated dowel and every rail, the brace included, has one dowel seated in each side frame. A dowel is seated in a bore when its tip is 12 mm to 19 mm past the bore entry along the bore axis (12 mm is 80% of the exposed dowel), its tip is within 1.6 mm of the bore axis and the dowel axis is within 0.105 rad of the bore axis. Success: after stage 4 the assembled condition holds with no hand contact on any frame or rail and every part's centre-of-mass speed at most 0.02 m/s and angular speed at most 0.2 rad/s for 50 consecutive controls (1 s); the episode then ends. A single seated brace dowel or any partial assembly never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the lower frame moves more than 0.03 m or tilts more than 10 degrees; a pre-seated rail is pulled to less than 8 mm in its bore or tilts more than 10 degrees; the brace touches the table after stage 1, or its centre drops below 0.09 m above the table top after stage 1; the brace tilts more than 20 degrees after stage 2; the opposite side frame touches the table after stage 3 or tilts more than 20 degrees from its upside-down carrying orientation after stage 3; any part with no contact at all (not held, not supported) has its centre of mass falling faster than 0.2 m/s (a drop); any part touches the floor, has its centre below the table top (z < 0.74 m) or leaves the workspace box x in [0.23, 1.23] m, y in [-0.73, 1.03] m, z in [0.70, 1.60] m; or the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed: no object teleports, grasp welds, scripted object motion or direct object forces. All parts are free rigid pine bodies; the bores are hollow contact geometry of the source size (4.1 mm radius for the 4.0 mm dowels: 0.1 mm radial clearance, no entry chamfer); glue, screws, the seat and load capacity are not modelled. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with
ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the wrist x/y/z targets are offsets from the stage origin (stage origin (0.55, -0.1, 1.15) m) along the world axes, and at zero wrist angles the palm faces down with the fingers along +x.
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
wrist_z` (metres, offsets of the stage from its origin along the world axes) and `wrist_rx, wrist_ry, wrist_rz`
(radians, serial XYZ joints), then the finger targets in radians. At zero wrist angles the palm faces down, the fingers
point along +x and the thumb is on the +y side. `D` is 28 for `sharpa` (22 Sharpa Wave finger joints
`right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`,
`r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up and the table top is at
z = 0.74 m. The lower side frame lies centred at (0.61, 0.0) m with its open bores facing up, the brace lies at
(0.57, -0.33) m along x and the opposite side frame lies upside down at (0.61, 0.5) m. Cameras are overview, closeup
and side, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns
at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for larger chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it without seconds
only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied. If
the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes
the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
