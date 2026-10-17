# DexHand: Stir milk into a mug of coffee with a teaspoon

Mix the milk into the coffee: stir it six times with the teaspoon, then lay the spoon on the worktop beside the mug. The 300 g mug (inner radius 50 mm, 100 mm tall, 8 mm floor) stands upright on the stone worktop (top at z = 0.75 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee, milk already poured, fills it to 64 mm above the mug base (z = 0.814 m). The approved source film (a kinematic demonstration without hands) starts with the teaspoon suspended upright above the rim; here the right hand holds the 35 g teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, with the bowl centre about 0.12 m above the mug base just over the rim (the milk is already poured; the film pours it from an offscreen supply). With the Wuji hand selected (no Wuji start grasp exists yet), the spoon instead starts leaning in the mug (bowl on the mug floor, handle on the rim) and the open Wuji hand hangs about 0.25 m above the mug; the stages are the same. Success requires three stages in order. (1) Submerged in hand: the thumb and at least one other finger touch the spoon, and the bowl centre, bowl tip and bowl neck (23 mm either side of the centre along the spoon) are all between 4 mm and 64 mm above the mug base and within 50 mm of the mug axis. (2) Stirred: the bowl centre revolves at least six full turns about the mug's vertical axis (world frame; net signed angle). The angle accumulates only while the stage-1 condition holds and the bowl centre is at least 8 mm from the axis; a step of more than 0.785 rad in one control is ignored, and the count restarts from zero whenever the bowl leaves the coffee before six turns are complete. (3) Laid down: no part of the hand touches the spoon, the spoon touches the worktop and not the mug, its bowl centre and handle end are both at least 0.10 m from the mug axis horizontally, its axis is within 15 degrees of horizontal, and spoon and mug are still (linear speed at most 0.02 m/s, angular speed at most 0.5 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment. The coffee is not simulated: it exerts no force, and the mixing is judged only by these bowl revolutions below its surface. The episode ends immediately with failure, checked after every 2 ms physics substep, when the mug tilts more than 10 degrees, slides more than 20 mm or is lifted more than 5 mm; when the spoon touches the floor, or touches the worktop before the six turns are complete; when the spoon touches neither the hand, the mug nor the worktop while its centre of mass falls faster than 0.2 m/s (a dropped spoon cannot be caught again); when the mug touches the floor; when a spoon reference point (bowl centre, tip, neck or handle end) is more than 3 mm below the worktop top or the mug base more than 5 mm below it; when the bowl centre or the handle end leaves the workspace box x in [0, 0.96] m, y in [-0.48, 0.48] m, z in [0.70, 1.60] m; when a fingertip enters the coffee (inside the mug radius below the coffee surface); when an arm link, the stand or the parked left hand touches the mug, the spoon or the worktop; or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control the right arm and right hand of a Tianji Marvin dual-arm stand (two 7-joint arms, a dexterous hand on each
wrist; the stand sits at the world origin facing +x, its plate on the floor at z = -0.1 m). The left arm starts parked,
hanging beside the torso, and should stay there. Every arm and finger joint is a position servo in the physics engine
under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad, no gravity compensation, so a held
target sags under the arm's weight unless your targets account for it); stirring and laying the spoon down require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
The mug, the coffee and the teaspoon are the approved T11 kitchen scene: a cream glazed mug with a rounded handle
(pointing +x) on a stone worktop (top at z = 0.75 m, front edge at x = 0.25 m), axis at x = 0.48 m, y = 0.015 m. The
source film (kinematic, without hands) starts with the spoon suspended above the rim; here the right hand holds the
teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, the bowl just above the mug (settled start pose: position (0.452, -0.020, 0.874) m,
quaternion WXYZ (-0.399, 0.006, 0.032, 0.916)). The coffee is a visual surface only: it exerts no force, and the stirring is judged only from the
bowl's revolutions below that surface. Mug and spoon are free rigid bodies that move only through contact and gravity.
Cameras: `overview` (front right of the mug, wide), `closeup` (front right, close) and `top` (looking down the mug axis).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for sharpa, 20 per hand for wuji); the left arm stays parked and only the right arm and hand perform the task.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand, and grading replays with that hand.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets
(left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the right arm `..._R_J1` ... `..._R_J7`, radians), then the
left hand's finger targets and then the right hand's, in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints
per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji`
(20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). The left arm
starts parked and should stay there; arm servos have no gravity compensation. Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up, the worktop top is at
z = 0.75 m and the mug axis at x = 0.48 m, y = 0.015 m; the robot stand is at the world origin facing +x.
Cameras are overview, closeup and top, at 640 x 480.
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
