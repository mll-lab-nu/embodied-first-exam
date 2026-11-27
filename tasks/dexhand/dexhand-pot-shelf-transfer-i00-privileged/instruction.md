# DexHand · Place a two-handle pot into a shelf (privileged)

## Task
Lift the pot by its two handles with both hands, carry it into the shelf on the left and set it down upright on the
shelf board at the target, then open both hands and move them away.

## Goal
Success: the pot is carried with both hands lifting it, off the worktop and the shelf, for a moment; then it stands
upright on the shelf board at the target (Robot Interface), fully inside the compartment except that its front handle
may stick out a little past the board's front edge, resting on the board alone, with both hands opened and moved a
little away from it, and is still for two seconds. A replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The pot falls or tips over.
- The pot is dropped.
- The pot leaves the work area.
- The pot touches anything but the two hands, the worktop and the shelf board.
- A robot link touches the furniture or the floor, or two robot parts collide.
- A hand presses into the pot.
- A robot joint is pushed past its range.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, 1 <= T <= 30000, plus the `hand` member (`s.save_trajectory(actions, path)` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a kitchen worktop (DexHand,
MuJoCo). The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor
targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("pot_shelf_transfer")          # hand="wuji" or DEXHAND_HAND=wuji for the other hand
s.actuator_names, s.joint_names    # row order (s.action_dim targets)
s.model, s.data                    # privileged MuJoCo model and state
s.hold_action()                    # current targets
s.step(row)                        # one 2 ms physics step; returns status()
s.status()                         # success, done, reason, steps, stage (0-2), carry and hold seconds
s.features()                       # pot pose/speed/tilt, hand loads and contacts, support, unmet terminal condition
s.observe()                        # joint positions/velocities/targets, wrist poses, pot pose
s.snapshot(); s.restore(snap)      # exact save/restore of physics and task state
s.reset()                          # exact frozen reset
s.render_frame("overview")         # RGB uint8 (480, 640, 3); cameras: overview, front, shelf; shadows=True
s.replay(actions)                  # reset, run rows until done, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```

### Actions
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

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
The robot is a fixed Tianji Marvin stand with two 7-joint arms and a dexterous hand on each wrist. Every arm and finger
joint is a position servo inside the physics engine (2 ms physics step). Arm servos have stiffness 700 N m/rad, damping
48 N m s/rad, the arms' own torque limits and no gravity compensation: a held target sags under the arm's and the pot's
weight unless your targets account for it. Finger servos and every joint range and force limit are in `s.model`. The pot
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

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 9 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
