# DexHand · Put a folded letter into an envelope (standard)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
stays parked), at a desk (DexHand, MuJoCo). Put the folded letter into the envelope: a tri-folded A4 letter lies flat on
the desk at (0.48, -0.14) m, and an empty DL wallet envelope (110 x 220 mm) lies flat at (0.48, 0.16) m with its open
mouth along its +X long edge and the open flap on the desk beyond the mouth. Move the letter to the mouth, feed it in
through the mouth, then let go.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the letter is inside the envelope, all but a sliver of it past the mouth and between the side seams, and the
hand has let go of the letter and the envelope, which lie still for a second. What counts is how things stand at the end
of the episode: a success reached earlier and lost by the end does not count, so finish in the state you want graded and
stop sending commands.

The episode ends at once as a failure if the letter or the envelope falls below the desk top, touches the floor, is
dropped or leaves the desk; if the letter is pressed through a wall, a seam or the mouth lip of the envelope; if the
envelope is pushed away or tilted; if the robot's arm, stand or parked left hand touches the letter or the envelope; or
if the physics becomes unstable. Later actions cannot undo a failure.

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
Forward kinematics uses only the robot's own links (the robot base is at (1.15, -0.25, 0.10) m, facing -x); no IK
primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before
continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (radians): the 7 left-arm joint targets
`SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target`, then the left-hand and the right-hand finger targets. `D` is 58
for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0` ... `r_wuji_r_LFJ3`). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
the hand root pose (`right_hand_C_MC`) and current targets. Quaternions in measured poses use WXYZ; world z is up and
the desk top is at z = 0.70 m. Cameras are overview, closeup and mouth (a low view of the envelope mouth), at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its
base plate stands on the floor at z = 0); the left arm is parked beside the torso and only the right arm and hand do the
task. Arm joints and fingers are position servos in the physics engine under native force bounds; pressing, sliding,
pushing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

Keep the left arm at its start targets; only the right arm and hand do the task.

## Others
- The envelope is a rigid pocket: back and front walls 4 mm apart, permanent side seams (narrowing to nothing over the
  last 10 mm before the mouth), a bottom seam, and a 30 mm elastic mouth lip that starts closed (flush with the front
  wall); a fingertip or the letter can lift it. The flap is a thin wedge on the desk and is never sealed.
- The letter is one stiff 99 x 210 x 2 mm card (5 g) with rounded fold edges: paper bending is not simulated. Both
  objects are free and move only through contact.

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
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; there the episode ends and is graded as it
  stands.
