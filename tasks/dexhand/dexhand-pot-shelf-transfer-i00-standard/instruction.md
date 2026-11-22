# DexHand · Place a two-handle pot into a shelf (standard)

## Task
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a kitchen worktop (DexHand,
MuJoCo). A freely moving 1 kg two-handle stockpot (286 mm vessel diameter, 438 mm across its two loop handles) rests on
the worktop; an open kitchen shelf is to the robot's left. Grasp the pot by its two handles, lift it with both hands,
carry it into the shelf compartment and set it down upright on the shelf board at the target, then open both hands and
withdraw them.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the pot has been carried with both hands lifting it, clear of the worktop and the shelf; then it stands upright
on the shelf board at the target, fully inside the compartment (only its front handle may stick out a little past the
board's front edge), resting on the board alone, with both hands opened and moved a little away from it, still for two
seconds. The episode ends as soon as the task is done.

The episode ends at once as a failure if the pot falls or tips; is dropped (a short free fall, or touching nothing for a
moment); leaves the work area; touches anything other than the two hands, the worktop and the shelf board (the floor,
the shelf's side walls, back wall, top board or bases, a non-hand robot link); if a robot link touches the furniture or
the floor, or two robot parts collide; if a hand presses into the pot; if a robot joint is pushed past its range; or if
the physics becomes unstable. Everything else is allowed: the pot may be set back down on the worktop, touch the worktop
or the shelf board again and be regrasped any number of times. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()                    # spec["hand"], spec["action_types"]["joint_position"]["layout"], cameras, limits
obs = r.get_obs(cameras=["overview", "shelf"], depth=True)
obs.last["overview"]               # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]         # z-depth in metres
obs.meta["proprio"]                # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.002, interpolate="hold", video="none")
r.fk(q)                            # robot-link forward kinematics (both wrists); no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`; each call returns at most 1,000 camera
images, counting per-frame depth. Frames are rendered in software, about 0.6 s per camera image, and a call records
`video_fps` frames per simulated second (1 to 50, default 10) whatever `video` returns: lower it for long chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps; without seconds it only
observes. No IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()`
before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps
running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order
(the row layouts below), radians. `dt` must be a multiple of 0.002 s, between 0.002 and 0.5 s; a chunk covers at most 10
s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.

Each row starts with the 14 arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger
targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); one row is one 2 ms physics step.
Row layout, `sharpa` (58): 0-6 left arm
`SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
(actuators `<joint>_target`); 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave
fingers
`l_hand_thumb_CMC_FE, l_hand_thumb_CMC_AA, l_hand_thumb_MCP_FE, l_hand_thumb_MCP_AA, l_hand_thumb_IP, l_hand_index_MCP_FE, l_hand_index_MCP_AA, l_hand_index_PIP, l_hand_index_DIP`,
the same four for middle and ring, then
`l_hand_pinky_CMC, l_hand_pinky_MCP_FE, l_hand_pinky_MCP_AA, l_hand_pinky_PIP, l_hand_pinky_DIP`; 36-57 the right Sharpa
Wave fingers in the same order (`r_hand_...`). Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji
fingers `l_wuji_l_THJ0..THJ3` (thumb), `l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle),
`l_wuji_l_RFJ0..RFJ3` (ring), `l_wuji_l_LFJ0..LFJ3` (little); 34-53 the right Wuji fingers in the same order
(`r_wuji_r_...`).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both wrist poses and current targets. Cameras are overview, front (looking into the shelf compartment) and shelf, at 640
x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand with two 7-joint arms and a dexterous hand on each wrist. Every arm and finger
joint is a position servo inside the physics engine (2 ms physics step). Arm servos have stiffness 700 N m/rad, damping
48 N m s/rad, the arms' own torque limits and no gravity compensation: a held target sags under the arm's and the pot's
weight unless your targets account for it. Every joint's range and effort limit is in `spec()["robot_spec"]`. The pot
moves only through contact and gravity.

Control rate: one action row is one 2 ms physics step (500 Hz). A row holds a position target for every actuator
(radians), applied for exactly one physics step.

Both hands start open at the same arm pose.

### Scene
World frame: metres, radians, seconds; +z up, +x forward from the robot stand, +y to the robot's left; quaternions are
wxyz. The worktop top is at z = 0.75; the pot is upright on it with its base centre at (0.52, -0.05, 0.75) and its two
loop handles along the world y axis (handle loops 0.13 to 0.22 m from the pot axis, 0.133 to 0.187 m above the base);
the open shelf's board top is at z = 0.79 and spans x from -0.14 to 1.14 and y from 0.12 to 0.84; the compartment is
closed by side walls (inner faces x = -0.14 and x = 1.14), a back wall (inner face y = 0.84) and a top board (underside
z = 1.465), and opens toward -y. The target for the pot's base centre is (0.46, 0.31, 0.79).

## Others
- Check each chunk before you send it: the service runs every row you submit, and the first failure ends the episode.

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
- Steps: at most 30,000 rows (one per 2 ms physics step) (60 s of simulated time) per episode; an episode that reaches
  them without success has failed.
