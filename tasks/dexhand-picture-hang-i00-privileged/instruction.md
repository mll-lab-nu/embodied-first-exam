# DexHand: Hang a large picture on two wall hooks

Hang the framed picture on the two wall hooks. The free 2.0 kg frame (52 x 52 x 6 cm) stands upright on a console; two brass picture hooks are installed on the wall and two D-rings on passive hinges are screwed to the back of the frame. Lift the frame off the console with both hands, engage BOTH D-rings on their matching hooks (left ring on the left hook, right ring on the right hook), then let go: the picture must hang still and level from both hooks with no hand touching it. Success requires, in this order: (1) lift-off: the frame origin (the centre of its bottom edge) at least 0.02 m above its start height z = 0.72 m and no contact with the console; (2) engagement: both rings threaded on their own hooks (the hook's load saddle passes through the ring's D loop, with the ring between the hook's upturned lip and the wall; a ring resting on top of the lip does not count) and each ring touching its hook; (3) a released hang for 50 consecutive controls (1 s): both rings threaded, each hook carrying at least 20 % of the frame's weight vertically through its ring and both hooks together at least 85 %, no hand touching the frame, no frame contact with the console or the floor, the frame's top edge level within 3 degrees, its tilt from upright at most 0.10 rad, its centre-of-mass speed at most 0.02 m/s and its angular speed at most 0.15 rad/s. The episode ends with success at that moment; one engaged hook, or rings left on the hook lips, never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the frame touches the floor, when its origin leaves the workspace box x in [0.20, 0.76] m, y in [-0.45, 0.45] m, z in [0.60, 1.30] m, when it tilts more than 0.6 rad from upright, when after lift-off its origin falls more than 0.01 m below its start height, when after both rings were engaged no hand touches the frame while a ring is not threaded (it fell off a hook), when an arm, torso or stand link of the robot touches anything (only the hands may make contact), or when the physics becomes unstable; and when after lift-off the frame is held by nothing (no hand contact, no console contact and not hanging threaded on both hooks with both rings touching them): at the end of any control, or at any substep where its centre of mass is also moving down faster than 0.2 m/s (dropped, even if caught again, released early, dangling from one hook or resting on the hook lips). Later actions cannot undo a failure. Only the robot's actuator targets (14 arm joints and the fingers of both hands) are allowed; no grasp welds, scripted object motion or forces on the frame. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand on each wrist. The arm joints and the fingers are position actuated in the physics engine under native force bounds;
the frame moves only through contact, gravity and its two passive ring hinges, so lifting, carrying,
hooking and releasing all require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene (world frame: metres, z up, x pointing into the wall)
- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19; the console stands on its two rear legs
  (x = 0.615) so that the robot stand's base plate fits under its front half.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre
  of its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The robot stand faces the wall (+x) in front of the console, its base origin at (0.18, 0.00, 0.20): it stands on a
  0.10 m plinth exactly under its base plate; the shoulders are 1.121 m above the base origin, at y = +-0.2215. Only
  the hands may touch anything: any contact of an arm, torso or stand link with the frame, the hooks, the wall, the
  console, the floor or the other hand ends the episode (`robot_collision`).
- At the start both hands hang palm-inward above the frame's side rails, fingers pointing down, thumbs toward the wall.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7, radians), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`: the genuine right Sharpa Wave on the right flange and its declared mirror image on the left flange; 20 per hand for `wuji`: the manufacturer's left and right Wuji Hand 2.2). Both arms and both hands perform the task.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control: the 14 Marvin arm joint targets (radians) `SHOULDER_PITCH_L_J1_target,
SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target,
WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`, then the same seven for the right arm (`..._R_J1_target` ...
`..._R_J7_target`), then the left hand's finger targets and the right hand's, in radians:

- `sharpa`: 58 values, 22 Sharpa Wave finger targets per hand: `left_thumb_CMC_FE` ... `left_pinky_DIP`, then
  `right_thumb_CMC_FE` ... `right_pinky_DIP`. The right hand is the genuine Sharpa Wave right hand; the left hand is a
  declared mirror image of it (the right model reflected across its palm's sagittal plane, same joints, ranges and
  force limits), not a separate manufacturer left-hand model.
- `wuji`: 54 values, 20 Wuji Hand 2.2 finger targets per hand: `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3,
  l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for `r_wuji_r_` (the manufacturer's left and right models).

Arm servos: kp 700 N m/rad, kv 48 N m s/rad, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no
gravity compensation (a loaded arm sags unless you correct it). Each hand sits rigidly on its arm's flange (bodies
`l_wrist_stage` / `r_wrist_stage`; fingers along the flange +z, palm normal +x, thumb +y for the right hand). No IK
primitive is supplied. Every target must lie within `s.model.actuator_ctrlrange`; the frozen start targets (arm pose
with the hands above the frame, open fingers) are in `task.json` `initial_targets`.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
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
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, the failure checks
and the predicate (`task.json` `predicate` holds every threshold).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
