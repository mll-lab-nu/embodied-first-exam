# DexHand: Brush the debris off a boot sole

Brush all six soil clods off the upward-facing sole of the boot into the collection tray. The boot stands sole-up on a fixed boot-rack peg inside the tray (its sole plane is at z = 1.292 m); six small dry soil clods are lodged in its tread, held there by gravity and friction only (no glue or cohesive bond is simulated, so a clod moves as soon as something pushes it). The shoe brush lies bristles-down on the counter: pick it up with the robot's right hand and sweep the sole with the bristles. Success requires, in order: (1) the brush's bristle field touches the boot while the hand touches the brush and the brush does not touch the counter, for at least 10 controls in total; (2) every clod has been touched by the brush's bristle field (contact with the wooden back does not count) while it was still up on the boot (clod centre at most 0.01 m below the sole plane), and every clod centre lies inside the tray walls (x in [0.366, 0.694] m, y in [-0.184, 0.384] m) below the wall top (z < 0.931 m); (3) then, for 50 consecutive controls (1 s), all six clods stay in the tray with linear speed at most 0.05 m/s while the brush touches neither the boot nor any clod and is withdrawn (bristle-field centre at least 0.04 m above the sole plane, or at least 0.18 m horizontally from the sole centre). The episode ends with success at that moment; fewer than six clods never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the boot moves more than 0.03 m or tilts more than 0.35 rad from its reset pose; when a clod touches the counter or the floor, falls below the counter top (z < 0.886 m) or leaves the workspace box x in [0.25, 1.2] m, y in [-0.45, 0.45] m, z in [0.886, 1.8] m; when any part of the right hand touches a clod (clods must be brushed, not picked); when the brush touches the floor, the tray or the rack, falls below the counter top, leaves the workspace box, or is released in the air (it touches nothing but clods while its centre of mass sinks faster than 0.2 m/s); when any part of the robot other than its right hand (the stand, the torso, a link of either arm, the parked left hand) touches anything, including the robot itself; or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed: no welds, teleports, scripted object motion or applied object forces. The boot, brush and clods are free rigid bodies; the brush's 32 bristle tufts touch the world through one compliant bristle-pad contact proxy (individual fibre bending is not simulated) and the clods are rigid (no fracture or adhesion). The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The stand rests on the floor (z = 0) beside the counter's -y edge, with its base origin at world
(0.147, -0.591, 0.10), facing +y (shoulders 1.121 m above the base origin, at z = 1.221 m; the right shoulder is on
the +x side). The left arm stays parked beside the torso with its hand open; the task is done by the right arm and
hand alone, and no other part of the robot may touch anything. Every arm and finger joint is a position servo inside
the physics engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no
gravity compensation** (a held target sags under the arm's weight unless your targets account for it). Grasping,
carrying, brushing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps. The frozen reset lets the boot, the clods, the brush and the arms settle for 0.5 s before control 1.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all in radians: the 14 Marvin arm
joint targets (left arm J1-J7, keep them at the parked start values, then right arm J1-J7), then the left hand's and
the right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE`
... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger
joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). The
right hand starts open, palm down, fingers pointing +y, above the brush. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the counter top is at z = 0.886 m. The brush starts bristles-down on the counter at
(0.68, -0.28); the boot's sole plane is at about z = 1.292 m with the sole centre at (0.53, 0.10) and the toe towards
-x. Cameras are overview, closeup and side, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`,
`last` or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or
duration for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps.
Calling it without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK
primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
