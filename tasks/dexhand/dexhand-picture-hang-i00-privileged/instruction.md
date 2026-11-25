# DexHand · Hang a large picture on two wall hooks (privileged)

## Task
Hang the framed picture on the two wall hooks.

## Goal
Success: in this order, the frame is lifted off the console; the left ring on its back is threaded on the left hook and
the right ring on the right hook, behind the hooks' lips; then the picture hangs from both hooks, each carrying part of
its weight, level and upright, off the console and the floor, with no hand touching it, and is still for a second. A
replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The frame touches the floor, leaves the work area or tilts far from upright.
- After the lift, the frame sinks below its start height.
- Once both rings are on, a ring falls off its hook.
- After the lift, the frame is held by nothing: dropped (even if caught again), let go early, dangling from one hook or
  resting on the hook lips.
- An arm, torso or stand link of the robot touches anything (only the hands may make contact).
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or
`(T, 54)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist (both arms and both hands do the
task), facing a wall (DexHand, MuJoCo). The scene is one fixed instance. You have the full simulator to develop with;
you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("picture_hang")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("picture_hang", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names    # selected hand, row width and exact row order
s.hold_action()                           # current motor targets
s.model.actuator_ctrlrange                # native target limits
s.model, s.data                           # privileged MuJoCo model and state
s.status()                                # success, done, reason, failure_detail, steps, stage (0-3), total_stages,
                                          # hold_steps, features (frame pose, threaded rings, hook load shares,
                                          # contacts, roll, tilt, speeds)
s.step(row)                               # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)             # save / restore the full physics and verdict state
s.render_frame("overview")                # RGB uint8 (480, 640, 3); also "front", "side", "hook_closeup"
s.reset()                                 # exact frozen reset
s.replay(actions)                         # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```

### Actions
Each row is one 50 Hz control: the 14 Marvin arm joint targets (radians)
`SHOULDER_PITCH_L_J1_target, SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target, WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`,
then the same seven for the right arm (`..._R_J1_target` ... `..._R_J7_target`), then the left hand's finger targets and
the right hand's, in radians:

- `sharpa`: 58 values, 22 Sharpa Wave finger targets per hand: `left_thumb_CMC_FE` ... `left_pinky_DIP`, then
  `right_thumb_CMC_FE` ... `right_pinky_DIP`. The right hand is the genuine Sharpa Wave right hand; the left hand is a
  declared mirror image of it (the right model reflected across its palm's sagittal plane, same joints, ranges and force
  limits), not a separate manufacturer left-hand model.
- `wuji`: 54 values, 20 Wuji Hand 2.2 finger targets per hand:
  `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3, l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for
  `r_wuji_r_` (the manufacturer's left and right models).

Arm servos: kp 700 N m/rad, kv 48 N m s/rad, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity
compensation (a loaded arm sags unless you correct it). Each hand sits rigidly on its arm's flange (bodies
`l_wrist_stage` / `r_wrist_stage`; fingers along the flange +z, palm normal +x, thumb +y for the right hand). No IK
primitive is supplied. Every target must lie within `s.model.actuator_ctrlrange`; the frozen start targets (arm pose
with the hands above the frame, open fingers) are in `task.json` `initial_targets`.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `58`
wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand on each wrist. The
arm joints and the fingers are position actuated in the physics engine under native force bounds; the frame moves only
through contact, gravity and its two passive ring hinges, so lifting, carrying, hooking and releasing all require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

Both arms and both hands perform the task.

### Scene
World frame: metres, z up, x pointing into the wall.

- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19; the console stands on its two rear legs (x =
  0.615) so that the robot stand's base plate fits under its front half.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre of
  its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The robot stand faces the wall (+x) in front of the console, its base origin at (0.18, 0.00, 0.20): it stands on a
  0.10 m plinth exactly under its base plate; the shoulders are 1.121 m above the base origin, at y = +-0.2215. Only the
  hands may touch anything: any contact of an arm, torso or stand link with the frame, the hooks, the wall, the console,
  the floor or the other hand ends the episode (`robot_collision`).
- At the start both hands hang palm-inward above the frame's side rails, fingers pointing down, thumbs toward the wall.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
