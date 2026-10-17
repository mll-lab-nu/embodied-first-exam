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
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets `wrist_x, wrist_y,
wrist_z` (metres, offsets from the stage base at (0.62, 0.00, 0.70)) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.70 m. Cameras are overview, closeup, rings and pages, at
640 x 480.
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

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
