# DexHand: Align and staple three paper sheets

Square up three loose A5 sheets and staple them at a corner with the desk stapler, using the dexterous hand on the right arm of a fixed two-arm robot (the left arm stays parked). The sheets lie as a misaligned stack (each upper sheet shifted toward +x) with the bottom sheet's corner resting on the stapler's anvil mouth and the far edge on the desk. Slide the stack into the stapler throat against the stapler's paper stop, square the sheets, press the stapler head through its full stroke onto the stack and let it spring back. Stages, in order: (1) aligned: every corner of sheets 1 and 2 within 2.0 mm of the matching corner of sheet 0 (in sheet 0's plane), the sheets stacked in order (each 0.25-1.5 mm above the one below, along sheet 0's normal) and sheets 0-1 and 1-2 in contact; (2) in the throat: with (1), the staple point (stapler base frame (0.063, 0, 0.012) m, on the anvil under the driver blade) lies inside every sheet 3-30 mm from both edges of one corner and every sheet mid-plane is 0-6 mm above it; (3) pressed: with (1) and (2), the head hinge within 0.01 rad of its bottom stop (0.1701 rad) and the driver blade touching the top sheet; (4) released: after (3), with (1) and (2), the head back up (hinge <= 0.02 rad), no robot contact (either hand or any arm link) with any sheet or the stapler and every sheet's centre of mass slower than 0.02 m/s for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when a sheet centre falls below z = 0.77925 m (1 mm under its resting height on the desk top) or any sheet corner below z = 0.765 m, a sheet centre leaves the desk (x 0.25-0.99 m, y -0.36-0.36 m) or the workspace box (x 0.2-1.1 m, y -0.45-0.45 m, z 0.70-1.20 m), a sheet or the stapler touches the floor or a desk leg, a sheet or the stapler has no contact at all while its centre of mass falls faster than 0.2 m/s, the stapler base moves more than 3 cm horizontally from its reset position or tilts more than 0.26 rad, an arm link or the robot stand (anything of the robot but the two hands) touches the desk, the stapler or a sheet, or the physics becomes unstable; later actions cannot undo a failure. Only arm-joint and finger actuator targets are allowed. The head's return spring needs about 10 N pressed 8 cm in front of its hinge to start the stroke and about 25 N at the bottom stop. Sheets are 0.5 mm rigid plates (real A5 size and mass); staple formation is not simulated. At most 6000 controls at 50 Hz; reaching that limit without success is a failure.

You control a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous hand on each wrist. The right
arm and its hand suffice for the task; the left arm starts parked beside the stand (hanging straight down) and may stay
there (using it is allowed; every robot contact counts as hand contact). Every arm and finger joint is a position servo inside MuJoCo (implicitfast, 2 ms physics step). Arm servos have
stiffness 700 N m/rad, damping 48 N m s/rad and the arms' own torque limits (shoulder 108, elbow 66, wrist 18 N m), and
**no gravity compensation**: a held target sags by about 1 cm at the hand unless your targets account for it. Pushing,
pressing and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 arm joint targets (left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the same right-arm joints `..._R_J1` ... `..._R_J7`, radians), then
the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per
hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`,
`l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). Only the right arm and hand are needed; keep the left arm at its start
targets. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.78 m. Cameras are overview, closeup and throat, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links (arms and hands); no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.

## Scene (frozen instance, world frame)
World frame: z up, metres and radians. The floor is at z = 0. The robot's stand origin is at (0.58, -0.66, 0.10) with
its base plate on the floor, beside the desk's -y edge, facing the desk diagonally (heading 135 deg: toward -x and +y);
the right shoulder is at about (0.737, -0.503, 1.221) and the left at (0.423, -0.817, 1.221); the right hand's mount
starts at (0.80, -0.22, 1.02) with the fingers pointing down. The desk top is at z = 0.78 m and spans x 0.25-0.99 m, y -0.36-0.36 m
(friction: paper on paper 0.4, paper on desk 0.15, paper on the chrome anvil and stop 0.1). The NOVUS B2-style desk
stapler is a free body (0.173 kg) whose base origin is at (0.575, -0.100, 0.783) with its nose toward +x (the source
scene's pose). Its anvil top is at z = 0.795 m; the staple point (base frame (0.063, 0, 0.012) m) is at
(0.638, -0.100, 0.795) in the reset pose. A steel paper stop (insertion guide) stands behind the anvil: its front face
is at base-frame x = 0.0525 m (world x = 0.6275 m) for |y - y_base| <= 0.012 m, z 0.790-0.800 m; a stack whose corner
is fed against it puts the staple point about 10.5 mm inside both edges. The handle with its driver blade turns on one
passive hinge about the base-frame y axis at (-0.052, 0, 0.020): return spring 7.0 N m/rad with 0.115 rad preload
against the open stop (0 rad), bottom stop 0.1701 rad (the blade 0.2 mm into a three-sheet stack lying on the anvil).
The handle top is about 6.6 cm above the desk; pressed 8 cm in front of the hinge, the head needs about 10 N to start
moving and about 25 N at the bottom stop. The magazine is rigid with the base.

The three sheets are rigid A5 plates (0.210 x 0.148 m, 0.5 mm thick, 2.5 g each), indexed bottom (0) to top (2). At
reset they rest as a loose, misaligned stack: the bottom sheet's (-x, -y) corner lies on the anvil mouth in front of
the paper stop, its +x edge on the desk; sheets 1 and 2 are shifted 4 mm and 8 mm toward +x. Rest poses (centre; all
three pitched 0.0733 rad about +y, i.e. the -x end raised, yaw 0): sheet 0 (0.7440, -0.0360, 0.7879),
sheet 1 (0.7480, -0.0356, 0.7881), sheet 2 (0.7520, -0.0364, 0.7883).

Simplifications relative to the source scene (T36), stated plainly: the sheets start with the corner already at the
throat mouth instead of lying flat on the desk (rigid thin sheets cannot be picked up from a flat desk by the modelled
fingertips; the hand only slides the stack in); the paper stop is an added part (the real NOVUS B2 has none; it squares
the stack, which the fingertips cannot do on their own against a flat desk); staple legs, piercing and clinching are
not simulated: "stapled" means the head pressed through its full stroke onto the aligned, inserted stack and released;
the sheets are 0.5 mm thick rigid plates (the source's sheets are 0.1 mm), with the real A5 size and mass.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
