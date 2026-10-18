# DexHand: Carry a tray with two filled glasses around a bottle to the other counter

Carry the serving tray with the two filled glasses from the source counter (centre x = 0.35 m) to the receiving counter (centre x = 0.78 m). Two dexterous hands, each on its own six-axis wrist stage, start above the two ends of the tray's long axis; the tray rim has open handle slots under the rim bar at both of those ends. Carry the tray around the steel bottle standing on the source counter at (0.52, 0.22) m and across the 30 mm gap between the counters, set it down on the receiving counter and let go. The liquid is not simulated: a glass counts as spilled when its axis tilts more than 15 degrees from vertical. Glass positions are measured in the tray frame, whose origin is the bottom centre of the tray floor (the floor's top surface is at height +2 mm in that frame). A glass is seated when its base centre lies inside the tray footprint ellipse (semi-axes 0.165 m x 0.23 m) and at a height between -3 mm and +8 mm in the tray frame. Success requires, in this order: (1) lift-off: the tray touches neither counter, its base is at least 30 mm above the counter top (z >= 0.91 m) and both glasses are seated; (2) placement: the tray rests on the receiving counter only, its centre within 20 mm in x and 30 mm in y of (0.78, 0.00) m, tray tilt at most 5 degrees, tray yaw within 10 degrees of its start orientation (long axis along y), both glasses seated; (3) release: the placement conditions plus no hand touching the tray or a glass, both glasses within 6 degrees of vertical, tray and glasses at rest (every linear speed at most 0.02 m/s and every angular speed at most 0.2 rad/s), held for 50 consecutive controls (1 s). The episode ends with success at that moment; a partial transfer never counts. The episode ends immediately with failure, checked after every 2 ms physics step, when a glass tilts more than 15 degrees (spilled); a glass base centre leaves the footprint ellipse, or its height in the tray frame exceeds +22 mm (20 mm above the floor's top surface) or falls below -10 mm; the bottle touches the tray, a glass or a hand; the tray touches the source counter again after lift-off; the tray touches the receiving counter while its centre is more than 40 mm in x or 50 mm in y from (0.78, 0.00) m (no dragging); the tray or a glass moves downward faster than 0.6 m/s (dropped; a free fall of about 18 mm), or faster than 0.2 m/s while unsupported (the tray touching no hand and no counter; a glass touching neither the tray, the other glass, a hand nor a counter); the tray tilts more than 35 degrees; the tray or a glass goes below z = 0.86 m, touches the floor or leaves the workspace box x in [0, 1.15] m, y in [-0.6, 0.6] m, z in [0.86, 1.12] m (so the tray cannot be lifted over the bottle); or the physics becomes unstable. Later actions cannot undo a failure. Only actuator targets of the two wrist stages and hands are commanded: no object teleports, grasp welds, scripted object motion or applied forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm). The left hand hangs above the +y end of the tray, the right hand above the -y end,
fingers pointing down and palms facing the tray. Stages and fingers are position actuated in the physics engine under
native force bounds; lifting, carrying and setting down the tray require physical contact. The controller runs at
50 Hz, with ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Two hands of the selected model, each on its own six-axis wrist stage (no arm): the left hand at the +y end of the tray, the right hand at the -y end. Every row holds both stages' targets and both hands' finger targets (layout below).
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

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
joint positions, velocities, actuator efforts, both wrist poses and current targets; object poses, contacts and the
checker's progress are not served (`r.status()` reports whether the episode is done and why it ended). An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (units: the six stage slides
`l_wrist_x, l_wrist_y, l_wrist_z, r_wrist_x, r_wrist_y, r_wrist_z` in metres, every other entry in radians): the left wrist stage `l_wrist_x,
l_wrist_y, l_wrist_z` (metres, displacement from the stage base at (0.35, 0.272, 1.15) m) and `l_wrist_rx, l_wrist_ry,
l_wrist_rz` (radians, serial XYZ hinges), the right wrist stage `r_wrist_x ... r_wrist_rz` (stage base at (0.35,
-0.272, 1.15) m), then the left hand's and the right hand's finger targets in radians. `D` is 56 for `sharpa` (22
Sharpa Wave finger joints per hand, `l_hand_thumb_CMC_FE ... l_hand_pinky_DIP`, `r_hand_thumb_CMC_FE ...
r_hand_pinky_DIP`) and 52 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3 ... l_wuji_l_LFJ0..3`,
`r_wuji_r_THJ0..3 ... r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is
reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation
holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper
opening. Quaternions in measured poses use WXYZ; world z is up and both counter tops are at z = 0.88 m. Cameras are
overview, side, top and handle_left, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last` or
`frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for
larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it
without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive
is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
