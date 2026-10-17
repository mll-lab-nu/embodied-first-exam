# DexHand: Unfold a folding sweater dryer and stand it on its legs

Set up the folding sweater dryer on the kitchen counter with the dexterous hand. It starts fully folded and stored underside up, its four legs folded between the two frame halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and stand it on its four feet, then let go: success needs the fold angle at most 0.314 rad, every leg at least 1.571 rad, the rack upright within 10 degrees on all four feet and nothing else, untouched by the hand and still for 50 consecutive controls (1 s). Dropping the rack, pushing it off the counter, or letting it collapse or fall over after it stands ends the episode as a failure at once.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, turning and releasing the rack require physical contact. The controller runs at 50 Hz, with ten
2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage (origin above the counter), with the same wrist joints, ranges, gains and start targets.
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
joint positions, velocities, actuator efforts, wrist pose and current targets; the rack's joint angles and pose are not
published, so you judge the rack from the cameras. An episode ends at the first success or the first failure (see
`## Success and failure`); after that the service accepts no more actions until a reset (see `## Episodes and resets`).
The service records every action and watch step, then replays the graded episode with the recorded hand in two fresh
processes. Leave your controller at `/app/output/gen.py`; no trajectory hand-in is needed.

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
wrist_z` (metres, offsets of the hand mount from the stage origin (0.62, 0, 0.75) m along the world axes; ranges
x [-0.85, 0.85], y [-0.6, 0.6], z [-0.05, 1.0]) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints; rx and rz
[-3.3, 3.3], ry [-1.6, 1.6]), then the finger targets in radians. At zero rotation the hand hangs palm down with the
fingers along +x and the thumb toward +y. `D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 26 for `wuji` (20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`,
`r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits
and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured poses use WXYZ; world z is up, the counter top is at z = 0.75 m and spans
x in [-0.13, 1.37] m, y in [-0.48, 0.48] m; the folded rack starts near (0.30, 0.0). Cameras are overview, side and
closeup, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns
at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for larger chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it without seconds only
observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the
same journaled episode, without a reset, and the wall-clock budget keeps running. The episode allows at most
6000 controls.

## Scene
The rack is a folding sweater dryer: two rectangular frame halves (each 0.33 m x 0.65 m, 0.205 kg) joined by a passive
pole hinge on the side rims (0 rad = open flat, pi rad = folded), each half with two offset 0.098 m legs on passive hinges
(0 rad = folded flat, 1.745 rad = 100 degrees = open stop, no latch: the stop lies 10 degrees past vertical, so the
standing rack's weight keeps an open leg open). The woven net is drawn only and has no collision. The rack is a free
body of 0.51 kg and starts fully folded and stored underside up, its legs sandwiched between the halves.

## Success and failure
The episode is evaluated after every control from simulator state only, in this order:

1. **Unfolded**: the fold angle is at most 0.314 rad (at least 90 % of the opening stroke) and each of the four leg
   angles is at least 1.571 rad (90 degrees, at least 90 % of the leg stroke).
2. **Standing** (only after stage 1): the stage-1 condition holds, the rack's up axis (the normal of the fixed half,
   legs pointing down) is tilted at most 10 degrees from vertical, all four feet touch the counter and no other rack
   part touches it.
3. **Released hold**: the stage-2 condition holds, no hand geometry touches the rack, and every rack body moves at most
   0.02 m/s and 0.2 rad/s (centre-of-mass velocities), for 50 consecutive controls (1 s). The episode ends with success
   at that control.

A partly open rack, a rack on fewer than four feet, a rack resting on a frame part, or a rack that is still held never
counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when

- any rack collision part's centre is below the counter top (z < 0.75 m), outside the counter footprint
  x in [-0.13, 1.37] m, y in [-0.48, 0.48] m, or more than 0.9 m above the counter;
- the rack touches the floor or the counter cabinet;
- the rack touches neither the counter nor the hand while its centre of mass falls faster than 0.05 m/s (dropped);
- after stage 2: the rack tilts more than 20 degrees (fell over), or the fold angle exceeds 0.314 rad or any leg angle
  drops below 1.571 rad (collapsed);
- the physics becomes unstable, or 6000 controls pass without success.

Later actions cannot undo a failure. Only hand and wrist-stage actuator targets are allowed; there are no welds,
attachments, scripted object motion or object forces.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
