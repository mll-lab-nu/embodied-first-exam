# DexHand · Plug a USB cable into a hub port (standard)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), in front of a desk (DexHand, MuJoCo). Connect the USB cable to the hub: a four-port USB hub rests free on
the desk with its ports facing the desk's front edge (world -y), and the cable's USB-A plug lies on its side on the
desk, with its 0.5 m cable. Pick up the plug, turn it so its polarized (top) face points up, and insert it into port 4,
the rightmost port (hub-local x = +33 mm), then let go.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: in this order: the plug is grasped by the thumb and at least one other finger and lifted off the desk; it is
pushed nearly all the way into port 4, straight and top face up; then it stays seated with the hand off the plug, its
cable and the hub, still for a second. A plug in any other port never counts. What counts is how things stand at the end
of the episode: a success reached earlier and lost by the end does not count, so finish in the state you want graded and
stop sending commands.

The episode ends at once as a failure if the hub is moved or tilted; the plug falls below the desk top; the plug or the
hub leaves the work area; the cable's far USB-B end falls off the desk; an arm link, the robot's stand or torso, or the
parked left hand touches anything (the desk, the floor, the hub, the plug or the cable, the working hand or another
robot part); the plug is dropped after it was grasped (no hand on it or its cable while it is not engaged in a port, and
it falls or lies on the desk or the floor); or the physics becomes unstable. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: when your time is up the
  episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`:
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
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all in radians: the 14 Marvin arm
targets (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values; then the right arm
`..._R_J1` ... `..._R_J7`), the left hand's finger targets, then the right hand's. `D` is 58 for `sharpa` (22 Sharpa
Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`)
and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ... `l_wuji_l_LFJ0..3`, then
`r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`). Actuator targets
are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose (`wrist_stage`, the right hand's mount on the arm flange) and current targets; object poses, contacts are not
observable. Quaternions in measured poses use WXYZ; world z is up, the desk top is at z = 0.70 m and its front edge at y
= -0.114 m. Cameras are overview and closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist. The robot stands on the floor in front of the desk, right of the hub (base centre at x = 0.93, y =
-0.52 on the floor at z = -0.20, facing the desk at yaw 135 deg, i.e. toward world (-1, +1)/sqrt(2); shoulders at z =
1.021 m, 1.221 m above the floor). The left arm stays parked beside the torso with its hand open; the task is done by
the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native
force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and no gravity compensation (a held target
sags under the arm's weight unless your targets account for it). Grasping, carrying, inserting and releasing require
physical contact. Only the working right hand may touch the desk and the task objects: any contact of an arm link, the
stand or torso, or the parked left hand with anything fails the episode at once (`robot_collision`). The controller runs
at 50 Hz, with ten 2 ms physics substeps.

### Scene
- Desk: top at z = 0.70 m (0.90 m above the floor at z = -0.20), front edge at y = -0.114 m (world frame, z up, metres
  and radians); its two front legs stand back under the top (x 0.32, y 0.00 and x 1.08, y 0.46), clear of the robot's
  base plate.
- Hub: the original four-port USB hub (103 x 30 x 10 mm, 21.8 g) rests free on the desk on rubber pads, its port face
  flush with the desk's front edge and facing -y; it is not fixed or held. Ports 1-4 are at hub-local x = -27, -7, +13,
  +33 mm; port 4 (the target) is the rightmost seen from the front. Its own upstream cable is drawn lying on the desk
  and has no physics.
- Plug: a free USB-A plug (7 g; metal shell 12.0 x 4.5 x 12 mm, housing 15 x 20 x 8 mm, strain relief) lying on its side
  on the desk, with a passive 0.5 m cable (20 ball-jointed links, 15 g) ending in a free USB-B plug on the desk. The
  plug frame origin is the centre of the shell tip; its +y axis points out of the shell (insertion direction) and +z is
  the polarized top face. Inserted correctly, the plug's +y aligns with the hub's +y and +z with the hub's +z.
- Ports are open rectangular cavities 12.5 x 4.8 x 12 mm (0.25 mm clearance per side across, 0.15 mm in height); the
  receptacle tongue and contacts are visual only, and there are no retention springs: a seated plug stays by friction
  and its own weight.
- Cameras: `overview` (desk, hub and plug from the front left) and `closeup` (the hub's port face).

## Others
- The ports are open cavities with generous clearance and no retention springs: a seated plug stays in by friction and
  its own weight.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; there the episode ends and is graded as it
  stands.
