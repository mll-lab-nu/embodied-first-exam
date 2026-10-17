# DexHand: Inflate a tire with a portable bicycle pump

Inflate the bicycle tire with the portable bicycle pump, using the right hand of the Tianji Marvin robot that stands at the bench (stand at the world origin, facing +x; the left arm stays parked). A mini floor pump (Topeak Mini Morph type, 154 g class, barrel 0.25 m tall) stands free on its folding foot on the bench next to a 406 (20 inch) wheel lying on the bench; as in the source scene, the pump's hose head starts disconnected from the wheel's Schrader valve and the tire is at 200.0 kPa gauge. The head (TRK-RP04 type) sits on the valve stem's axis 17.5 mm out from its seat (an 8 mm gap to the stem tip) with its thumb lock open (lever pointing up). The head moves only along the stem axis: a passive slide guided by the hose, with 2 N of friction and an end stop at the seat; pushing it 17.5 mm toward the rim seats it on the stem. The thumb lock is a passive hinge on the head (axis along world y, at the lever's foot, 0.004 N m friction) that turns 1.65 rad from up (open) to lying flat toward the wheel hub (closed). The pump's T handle rests at the top of its 0.20 m travel: the piston is a passive slide whose compressed-air spring pushes the handle back up (about 6 N at the top and 46 N at the bottom of the stroke) with viscous damping and 1 N seal friction. A stroke counts only while the head is connected (see stage 1), when the handle is pushed down to a piston depth of at least 0.18 m (90 % of the travel) and then returns to a depth of at most 0.04 m (20 %); shallower strokes never count and are not failures. The tire pressure is a checker quantity, not simulated air: every counted stroke adds 380 Pa (the mean rise per stroke of the source gas model, which reaches 210.6 kPa after its 28 strokes). Success requires, in this order: (1) the head connected: seated within 0.5 mm of its 17.5 mm travel while the thumb lock is closed to within 0.15 rad of its 1.65 rad stop (this latches; a stroke is armed and counted only while the head is seated and locked like this at that very moment); (2) at least 28 counted strokes; (3) tire pressure at least 210.6 kPa gauge; (4) the head disconnected again, as at the end of the source: the thumb lock opened to at most 0.5 rad and the head pulled at least 12.5 mm back off its seat (off the 9.5 mm stem engagement; this latches; the pressure stays, since only counted strokes change it); (5) the handle released at the top: piston depth at most 0.01 m, no contact of any robot part (hands, arms, stand) with any part of the pump or the head, pump tilt at most 0.0873 rad (5 degrees) from upright, pump centre-of-mass speed at most 0.02 m/s and handle speed at most 0.02 m/s, held continuously for 50 consecutive controls (1 s). The episode ends with success at that moment. The episode ends immediately with failure, checked after every 2 ms physics substep, when the pump tilts more than 0.2618 rad (15 degrees) from upright, when its base moves more than 0.03 m horizontally from its start or rises more than 0.02 m above it, when its centre of mass falls below the bench top (z < 0.70 m) or any pump part touches the floor, when the head, once connected and before stage 3 is reached, is pulled back more than 2 mm from its seat or its thumb lock is opened below 1.2 rad (head_disconnected), when the head is pulled back more than 2 mm from its seat while its thumb lock is still closed (at least 1.2 rad) after stage 3 (head_forced_off: open the lock first), or when the physics becomes unstable; later actions cannot undo a failure. The episode allows at most 5000 controls at 50 Hz; reaching that limit without success is a failure. Only robot actuator targets are allowed (the Marvin arm joints and the hands' finger joints); no object teleports, grasp welds, scripted object motion or direct object forces. The wheel, valve and hose are static props (the hose end at the head moves with the head, for display only); the head and its thumb lock move only through contact.

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist, standing at the bench with its base centre at the world origin, facing +x (shoulders at z = 1.121 m,
1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and hand
alone. Every arm and finger joint is a position servo inside the physics engine under native force bounds; arm servos
have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target sags under the arm's
weight and the handle's push unless your targets account for it). Pushing the pump handle requires physical contact.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and only the right arm/hand perform the task.
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

## What you observe
Camera RGB and calibrated depth from `overview` (default) and `closeup` (aimed at the pump), the robot's own joint
positions, velocities, actuator efforts, hand pose and current targets, and robot-link forward kinematics. The
service does not report the pump pose, the head or lever position, the piston depth, the stroke count, the tire
pressure or contacts: judge the
handle and the pump from the images and depth. At the end of an episode the meta reports `done`, `success` and a
failure category; the graded verdict is the replay's (see the task text).

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all position targets in radians: the
14 Marvin arm joints (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values;
then the right arm `..._R_J1` ... `..._R_J7`), then the left hand's and the right hand's finger joints. `D` is 58 for
`sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE`
... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). The arm servos have no gravity compensation. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the bench top is at z = 0.70 m. The pump stands near world (0.42, 0.08) with its
T handle about 0.45 m above the bench at rest; the disconnected hose head sits at the wheel rim near world
(0.546, -0.12, 0.747) with its thumb-lock lever pointing up, and seats by sliding 17.5 mm toward the rim along
(-0.981, 0, -0.196). Cameras are overview, closeup, wide and front, at 640 x 480.
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
