# DexHand: Plug a USB cable into a hub port

Connect the USB cable to the hub. You drive the right arm and hand of a Tianji Marvin robot standing in front of the desk (left arm parked). A four-port USB hub rests free on the desk with its ports facing the desk's front edge (world -y); the cable's USB-A plug lies on its side on the desk, with its 0.5 m cable. Pick up the plug, turn it so its polarized (top) face points up, and insert it into port 4, the rightmost port (hub-local x = +33 mm), then let go. Success requires three stages in order. (1) Grasped and lifted: the thumb and at least one other finger touch the rigid plug (shell, housing or strain relief), the plug touches nothing else, and the plug origin (the centre of its metal shell tip) is at z >= 0.73 m (30 mm above the desk top at z = 0.70 m). (2) Seated in port 4: in that port's frame the shell tip is at least 10.8 mm deep in the 12 mm cavity (90%), within 0.6 mm of the port axis sideways and 0.5 mm vertically, the plug axis is within 5 degrees of the port axis, and the plug's top face is within 20 degrees of the hub's top face (correct polarity). (3) Released: the plug stays seated in port 4 with no hand contact on the plug, its cable or the hub and a plug speed of at most 0.01 m/s for 50 consecutive controls (1 s). The episode ends with success at that moment. A plug seated in any other port never counts. The episode ends immediately with failure when the hub moves more than 20 mm from its start position or tilts more than 20 degrees, when the plug falls below z = 0.685 m, when the plug or hub leaves the workspace box x in [0.25, 1.15] m, y in [-0.40, 0.95] m, z in [0.685, 1.10] m, when the cable's far USB-B end falls more than 5 cm below the desk top, when an arm link, the robot's stand or torso, or the parked left hand touches anything (`robot_collision`: the desk, the floor, the hub, the plug or cable, the working hand or another robot part), when the plug is dropped (after stage 1, at the first control at which the plug has no hand contact on it or its cable, is not engaged at least 3 mm deep in a port, and either falls faster than 0.2 m/s or lies on the desk or floor), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. Each port is an open rectangular cavity with generous clearance (0.25 mm per side across, 0.15 mm per side in height); the receptacle tongue and contacts are visual, and there are no retention springs, so the plug stays in by friction and its own weight. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The robot stands on the floor in front of the desk, right of the hub (base centre at x = 0.93,
y = -0.52 on the floor at z = -0.20, facing the desk at yaw 135 deg, i.e. toward world (-1, +1)/sqrt(2); shoulders
at z = 1.021 m, 1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by the right
arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native force
bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held target sags
under the arm's weight unless your targets account for it). Grasping, carrying, inserting and releasing require
physical contact. Only the working right hand may touch the desk and the task objects: any contact of an arm link, the
stand or torso, or the parked left hand with anything fails the episode at once (`robot_collision`). The controller
runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
- Desk: top at z = 0.70 m (0.90 m above the floor at z = -0.20), front edge at y = -0.114 m (world frame, z up,
  metres and radians); its two front legs stand back under the top (x 0.32, y 0.00 and x 1.08, y 0.46), clear of
  the robot's base plate.
- Hub: the original four-port USB hub (103 x 30 x 10 mm, 21.8 g) rests free on the desk on rubber pads, its port face
  flush with the desk's front edge and facing -y; it is not fixed or held. Ports 1-4 are at hub-local
  x = -27, -7, +13, +33 mm; port 4 (the target) is the rightmost seen from the front. Its own upstream cable is drawn
  lying on the desk and has no physics.
- Plug: a free USB-A plug (7 g; metal shell 12.0 x 4.5 x 12 mm, housing 15 x 20 x 8 mm, strain relief) lying on its
  side on the desk, with a passive 0.5 m cable (20 ball-jointed links, 15 g) ending in a free USB-B plug on the desk.
  The plug frame origin is the centre of the shell tip; its +y axis points out of the shell (insertion direction)
  and +z is the polarized top face. Inserted correctly, the plug's +y aligns with the hub's +y and +z with the hub's +z.
- Ports are open rectangular cavities 12.5 x 4.8 x 12 mm (0.25 mm clearance per side across, 0.15 mm in height); the
  receptacle tongue and contacts are visual only, polarity is part of the success predicate, and there are no
  retention springs: a seated plug stays by friction and its own weight.
- Cameras: `overview` (desk, hub and plug from the front left) and `closeup` (the hub's port face).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and only the right arm/hand perform the task.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

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
joint positions, velocities, actuator efforts, wrist pose (`wrist_stage`, the right hand's mount on the arm flange) and current targets; object
poses, contacts and the verdict state are not observable (`r.status()` only reports whether the episode ended and
whether it succeeded). An episode ends at the first success
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all in radians: the 14 Marvin arm
targets (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values; then the right
arm `..._R_J1` ... `..._R_J7`), the left hand's finger targets, then the right hand's. `D` is 58 for `sharpa` (22 Sharpa
Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ...
`right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits
and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured poses use WXYZ; world z is up, the desk top is at z = 0.70 m and its front
edge at y = -0.114 m. Cameras are overview and closeup, at 640 x 480. Requests can return RGB frames or mp4, with depth
`none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras,
fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those
steps. Calling it without seconds only observes the current state. Forward kinematics uses only the robot's own links;
no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
