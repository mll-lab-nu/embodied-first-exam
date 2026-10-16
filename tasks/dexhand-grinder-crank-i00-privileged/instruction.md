# DexHand: Operate a manual coffee grinder

Operate the manual coffee grinder on the counter with the two hands of the dual-arm robot standing at the counter. The HARIO-style hand mill (0.40 kg, 174 mm body, 26 mm base radius) stands free on the counter top (z = 0.70 m) with its base centre at (0.45, 0, 0.70) m. Its crank turns on a passive hinge about the grinder axis with grinding resistance (0.08 N m dry friction and 0.012 N m s/rad damping); the knob sits on a free spin bearing at 80 mm crank radius. The grinder is light and narrow: it tips over if the crank is driven without holding the body. Hold the grinder body with one hand and turn the crank by its knob with the other until the crank has turned at least two full turns (720 degrees) net clockwise as seen from above, measured as the unwrapped crank hinge angle relative to the grinder body. Then let go of the grinder. Success requires, at the same time: the crank still at least 720 degrees net clockwise, no contact between any part of either hand and any part of the grinder (body, crank or knob), the grinder base resting on the counter, the grinder axis within 10 degrees of vertical, grinder centre-of-mass linear speed at most 0.02 m/s, grinder angular speed at most 0.2 rad/s and crank speed at most 0.5 rad/s; this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; turning the crank without the released hold never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the grinder axis tilts more than 10 degrees from vertical, the grinder base moves more than 2 cm horizontally from its start or rises more than 2 cm, the base falls below the counter top (z < 0.695 m), the grinder body turns more than 45 degrees about its own axis, the crank has turned more than 90 degrees net counter-clockwise, an arm, torso or stand link of the robot touches anything (only the hands may make contact), or the physics becomes unstable; later actions cannot undo a failure. Only the robot's actuator targets (14 arm joints and the fingers of both hands) are allowed: no object teleports, grasp welds, scripted object motion or direct forces on the grinder. Grinding itself is summarised by the crank angle; no beans or grounds are simulated. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand of the same model on each
wrist: a right hand and a left hand. The arm joints and the fingers are position actuated in the physics engine under
native force bounds; holding the grinder and turning the crank require physical contact. The controller runs at 50 Hz,
with ten 2 ms physics substeps. The stand faces +x behind the counter on the floor (z = -0.1 m), its base origin at
(-0.085, 0, 0) m (shoulders 1.121 m above it, at y = +-0.2215 m); any contact of an arm, torso or stand link with
anything ends the episode (`robot_collision`).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7, radians), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`: the genuine right Sharpa Wave on the right flange and its declared mirror image on the left flange; 20 per hand for `wuji`). The left hand counterholds the grinder, the right hand turns the crank.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control: the 14 Marvin arm joint targets (radians) `SHOULDER_PITCH_L_J1_target,
SHOULDER_ROLL_L_J2_target, ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target,
WRIST_YAW_L_J6_target, WRIST_ROLL_L_J7_target`, then the same seven for the right arm (`..._R_J1_target` ...
`..._R_J7_target`), then the finger targets in native actuator order, in radians, left hand first:

- `sharpa`: 58 values, the 14 arm targets, 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`,
  then 22 right targets `right_thumb_CMC_FE` ... `right_pinky_DIP`. The left Sharpa Wave is the right model reflected
  in y.
- `wuji`: 54 values, the same 14 arm targets, 20 left Wuji Hand 2.2 targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the manufacturer's right hand `r_wuji_r_THJ0..3` ...
  `r_wuji_r_LFJ0..3`.

Arm servos: kp 700 N m/rad, kv 48 N m s/rad, force limits 108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no
gravity compensation. Each hand sits rigidly on its arm's flange (bodies `right_wrist_stage` / `left_wrist_stage`:
fingers along the flange +z, palm normal +x, thumb +y for the right hand). No IK primitive is supplied. Every target
must lie within `s.model.actuator_ctrlrange`; the frozen start pose (arm joints; open fingers) is in `task.json`
(`initial_targets`).

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
s = Session("grinder_crank")                 # default hand model: DEXHAND_HAND or "sharpa"
s = Session("grinder_crank", hand="wuji")    # explicit hand model
s.hand, s.action_dim, s.actuator_names       # selected model, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, stage, crank angle, tilt, slide, contacts ...
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full integration and verdict state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "top"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The counter top is at z = 0.70 m;
the crank axis is the grinder's own axis (vertical at the start), 0.175 m above its base, and the knob starts at
(0.45, -0.08, 0.89) m. "Clockwise" is seen from above, i.e. a negative rotation about the grinder's +z axis.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
