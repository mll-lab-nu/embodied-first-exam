# DexHand: Fold a sheet of paper in half with a permanent crease

Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the marked center line, take the hand away, and leave the folded sheet lying on the table. The 160 x 100 mm sheet (1.28 g) lies flat on the table top. Its left half is glued to a backing patch next to a dark clamp and cannot move; the right half is free, and its last 25 mm overhang the table edge. Success requires 100 consecutive 50 Hz control samples (2 s) in which no part of the hand touches the paper and all of these hold: fold angle of the free half above 2.6 rad, permanent (plastic) crease on the center line above 2.2 rad on average with at least 90% of its hinges above 2.2 rad, free edge within 18 mm of the fixed edge, stretch below 8%, and the whole sheet over the table top: every paper vertex within the table's extent (x from -0.345 to 0.135 m, y from -0.30 to 0.30 m) and at most 2 mm below the table top (z >= 0.298 m). The episode ends with that success, or fails immediately and permanently if any paper vertex sinks more than 10 mm below the table top (z < 0.29 m, for example bent down over the table edge) or leaves the workspace box (x from -0.03 to 0.19 m, y from -0.09 to 0.09 m, z <= 0.45 m), if the paper stretches by more than 8%, or the simulation becomes unstable. A fold that springs back, a crease that is not permanent, or a hand still touching the paper is not a success. Only the robot's motor targets act on the paper; there are no grasp welds, scripted paper motion or applied forces. The episode allows at most 1500 controls at 50 Hz (30 s).

A dexterous hand on a six-DoF wrist positioning stage is your robot. The wrist stage is position actuated in the
physics engine; folding and creasing need physical contact. Physics runs at 0.5 ms (40 substeps per 20 ms control),
and the controller runs at 50 Hz.

## Scene (world frame, metres, z up)
- Table top at z = 0.30 m, spanning x from -0.345 to 0.135 m (the edge on the hand's side) and y from -0.30 to
  0.30 m. Fail-fast limits on every paper vertex, checked every 0.5 ms: z >= 0.29 m (10 mm below the table top)
  and inside the workspace box x -0.03..0.19 m, y -0.09..0.09 m, z <= 0.45 m. At success every vertex must lie
  within the table's x/y extent and at z >= 0.298 m (2 mm tolerance below the table top).
- The sheet starts flat at z = 0.3012 m, spanning x from 0 to 0.16 m and y from -0.05 to 0.05 m. The half with
  x <= 0.08 m is glued down and never moves; the fold line is at x = 0.08 m (an orange guide line marks it). A fold
  brings the free edge (x = 0.16 m) back over the glued edge (x = 0): the free half rotates by more than 2.6 rad about
  the fold line, upward and over.
- The paper is a passive elastic/plastic sheet: it bends elastically about 0.5 rad beyond its rest shape and then
  yields, so a crease becomes permanent only when the paper is bent well past its current rest shape, and a fold
  that is merely held springs partly back when released. Contact compliance gives it an effective thickness of 0.7 mm.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
The first six targets of a row drive the wrist stage that carries the hand: `wrist_x`, `wrist_y`, `wrist_z` (metres, world frame) and `wrist_rx`, `wrist_ry`, `wrist_rz` (radians, serial XYZ joints); the finger targets follow in the hand's native actuator order. Sharpa starts in a near-edge pregrasp; Wuji starts at the same six wrist targets with its fingers curled clear of the paper.
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
joint positions, velocities, actuator efforts, wrist pose and current targets; paper state is not published. An
episode ends at the first success or failure, and after at most 1500 controls; a reset starts a new one (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji" (set by the service)
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
`rows` is `(T, 28)` for `sharpa` or `(T, 26)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]`
order: `wrist_x, wrist_y, wrist_z` translations (metres), `wrist_rx, wrist_ry, wrist_rz` serial XYZ rotational joints
(radians), then the finger joints (radians). Actuator targets are clipped to the published joint limits and clipping
is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview and side, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps (they count toward the 1500 controls). Calling it without
seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
