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
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control, in `s.actuator_names` order (radians):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); columns 7-13: the same right-arm joints (`..._R_J1` to
  `..._R_J7`);
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, columns 34-53 the right ones (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm pose; the frozen start
row of each hand is in `task.json` (`initial_targets`). No inverse kinematics is supplied: `s.model` / `s.data` give
the arm's kinematics (the right hand's mount body is `wrist_stage`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("paper_staple")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("paper_staple", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # corner offsets, staple margins, head angle, contacts, failure details
s.status()                                      # success, done, reason, steps, stage (0-4), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "throat"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. Cameras for `render_frame`: `overview`, `closeup` (stapler and stack) and `throat` (the stapler mouth).

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
sheet 1 (0.7480, -0.0356, 0.7881), sheet 2 (0.7520, -0.0364, 0.7883); exact values in `task.json` `sheets[i].pose` (position, wxyz quaternion).

Simplifications relative to the source scene (T36), stated plainly: the sheets start with the corner already at the
throat mouth instead of lying flat on the desk (rigid thin sheets cannot be picked up from a flat desk by the modelled
fingertips; the hand only slides the stack in); the paper stop is an added part (the real NOVUS B2 has none; it squares
the stack, which the fingertips cannot do on their own against a flat desk); staple legs, piercing and clinching are
not simulated: "stapled" means the head pressed through its full stroke onto the aligned, inserted stack and released;
the sheets are 0.5 mm thick rigid plates (the source's sheets are 0.1 mm), with the real A5 size and mass.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
