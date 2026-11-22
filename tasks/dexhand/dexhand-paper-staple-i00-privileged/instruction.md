# DexHand · Align and staple three paper sheets (privileged)

## Task
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
starts parked and may stay there), at a desk (DexHand, MuJoCo). Square up three loose A5 sheets and staple them at a
corner with the desk stapler. The sheets lie as a misaligned stack (each upper sheet shifted toward +x) with the bottom
sheet's corner resting on the stapler's anvil mouth and the far edge on the desk. Slide the stack into the stapler
throat against the stapler's paper stop, square the sheets, press the stapler head through its full stroke onto the
stack and let it spring back. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: in this order: the three sheets are squared and stacked in order; the stack sits in the throat with the staple
point near one of its corners, inside every sheet; the head is pressed down to its bottom stop with the driver blade on
the top sheet; then the head is back up, no part of the robot touches the sheets or the stapler, and the sheets are
still for a second. Partial completion never counts. A replay ends as soon as the task is done; later rows are not run.

The episode ends at once as a failure if a sheet drops below the desk top, leaves the desk or the work area; a sheet or
the stapler touches the floor or a desk leg or is dropped; the stapler base is pushed away or tipped; an arm link or the
robot stand (anything of the robot but the two hands) touches the desk, the stapler or a sheet; or the physics becomes
unstable. Later actions cannot undo a failure.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actuator targets count: changing `s.data` or the scene while you develop changes nothing in the replay.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
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
Cameras for `render_frame`: `overview`, `closeup` (stapler and stack) and `throat` (the stapler mouth).

### Actions
Each row is one 50 Hz control, in `s.actuator_names` order (radians):

- columns 0-6: left arm
  `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
  (actuators `<joint>_target`); columns 7-13: the same right-arm joints (`..._R_J1` to `..._R_J7`);
- `sharpa` (58 values): columns 14-35 the left Sharpa Wave fingers `left_thumb_CMC_FE` ... `left_pinky_DIP`, columns
  36-57 the right Sharpa Wave fingers `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): columns 14-33 the left Wuji Hand 2.2 fingers `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, columns 34-53 the right ones (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm pose; the frozen start row
of each hand is in `task.json` (`initial_targets`). No inverse kinematics is supplied: `s.model` / `s.data` give the
arm's kinematics (the right hand's mount body is `wrist_stage`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous hand on each wrist. The right arm
and its hand suffice for the task; the left arm starts parked beside the stand (hanging straight down) and may stay
there (using it is allowed; every robot contact counts as hand contact). Every arm and finger joint is a position servo
inside the physics engine (2 ms physics step). Arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and the arms'
own torque limits (shoulder 108, elbow 66, wrist 18 N m), and no gravity compensation: a held target sags by about 1 cm
at the hand unless your targets account for it. Pushing, pressing and releasing require physical contact. The controller
runs at 50 Hz, with ten 2 ms physics substeps.

### Scene
World frame.

World frame: z up, metres and radians. The floor is at z = 0. The robot's stand origin is at (0.58, -0.66, 0.10) with
its base plate on the floor, beside the desk's -y edge, facing the desk diagonally (heading 135 deg: toward -x and +y);
the right shoulder is at about (0.737, -0.503, 1.221) and the left at (0.423, -0.817, 1.221); the right hand's mount
starts at (0.80, -0.22, 1.02) with the fingers pointing down. The desk top is at z = 0.78 m and spans x 0.25-0.99 m, y
-0.36-0.36 m (friction: paper on paper 0.4, paper on desk 0.15, paper on the chrome anvil and stop 0.1). The NOVUS
B2-style desk stapler is a free body (0.173 kg) whose base origin is at (0.575, -0.100, 0.783) with its nose toward +x.
Its anvil top is at z = 0.795 m; the staple point (base frame (0.063, 0, 0.012) m) is at (0.638, -0.100, 0.795) in the
reset pose. A steel paper stop (insertion guide) stands behind the anvil: its front face is at base-frame x = 0.0525 m
(world x = 0.6275 m) for |y - y_base| <= 0.012 m, z 0.790-0.800 m; a stack whose corner is fed against it puts the
staple point about 10.5 mm inside both edges. The handle with its driver blade turns on one passive hinge about the
base-frame y axis at (-0.052, 0, 0.020): return spring 7.0 N m/rad with 0.115 rad preload against the open stop (0 rad),
bottom stop 0.1701 rad (the blade 0.2 mm into a three-sheet stack lying on the anvil). The handle top is about 6.6 cm
above the desk; pressed 8 cm in front of the hinge, the head needs about 10 N to start moving and about 25 N at the
bottom stop. The magazine is rigid with the base.

The three sheets are rigid A5 plates (0.210 x 0.148 m, 0.5 mm thick, 2.5 g each), indexed bottom (0) to top (2). At
reset they rest as a loose, misaligned stack: the bottom sheet's (-x, -y) corner lies on the anvil mouth in front of the
paper stop, its +x edge on the desk; sheets 1 and 2 are shifted 4 mm and 8 mm toward +x. Rest poses (centre; all three
pitched 0.0733 rad about +y, i.e. the -x end raised, yaw 0): sheet 0 (0.7440, -0.0360, 0.7879), sheet 1 (0.7480,
-0.0356, 0.7881), sheet 2 (0.7520, -0.0364, 0.7883); exact values in `task.json` `sheets[i].pose` (position, wxyz
quaternion).

## Others
- The head's return spring needs about 10 N pressed 8 cm in front of its hinge to start the stroke and about 25 N at the
  bottom stop. A stack whose corner is fed against the paper stop puts the staple point about 10.5 mm inside both edges.
  The sheets are rigid 0.5 mm plates with the real A5 size and mass; staple legs, piercing and clinching are not
  simulated.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
