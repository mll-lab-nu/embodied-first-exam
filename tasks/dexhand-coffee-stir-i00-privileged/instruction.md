# DexHand: Stir milk into a mug of coffee with a teaspoon

Mix the milk into the coffee: stir it six times with the teaspoon, then lay the spoon on the worktop beside the mug. The 300 g mug (inner radius 50 mm, 100 mm tall, 8 mm floor) stands upright on the stone worktop (top at z = 0.75 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee, milk already poured, fills it to 64 mm above the mug base (z = 0.814 m). The approved source film (a kinematic demonstration without hands) starts with the teaspoon suspended upright above the rim; here the right hand holds the 35 g teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, with the bowl centre about 0.12 m above the mug base just over the rim (the milk is already poured; the film pours it from an offscreen supply). With the Wuji hand selected (no Wuji start grasp exists yet), the spoon instead starts leaning in the mug (bowl on the mug floor, handle on the rim) and the open Wuji hand hangs about 0.25 m above the mug; the stages are the same. Success requires three stages in order. (1) Submerged in hand: the thumb and at least one other finger touch the spoon, and the bowl centre, bowl tip and bowl neck (23 mm either side of the centre along the spoon) are all between 4 mm and 64 mm above the mug base and within 50 mm of the mug axis. (2) Stirred: the bowl centre revolves at least six full turns about the mug's vertical axis (world frame; net signed angle). The angle accumulates only while the stage-1 condition holds and the bowl centre is at least 8 mm from the axis; a step of more than 0.785 rad in one control is ignored, and the count restarts from zero whenever the bowl leaves the coffee before six turns are complete. (3) Laid down: no part of the hand touches the spoon, the spoon touches the worktop and not the mug, its bowl centre and handle end are both at least 0.10 m from the mug axis horizontally, its axis is within 15 degrees of horizontal, and spoon and mug are still (linear speed at most 0.02 m/s, angular speed at most 0.5 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment. The coffee is not simulated: it exerts no force, and the mixing is judged only by these bowl revolutions below its surface. The episode ends immediately with failure, checked after every 2 ms physics substep, when the mug tilts more than 10 degrees, slides more than 20 mm or is lifted more than 5 mm; when the spoon touches the floor, or touches the worktop before the six turns are complete; when the spoon touches neither the hand, the mug nor the worktop while its centre of mass falls faster than 0.2 m/s (a dropped spoon cannot be caught again); when the mug touches the floor; when a spoon reference point (bowl centre, tip, neck or handle end) is more than 3 mm below the worktop top or the mug base more than 5 mm below it; when the bowl centre or the handle end leaves the workspace box x in [0, 0.96] m, y in [-0.48, 0.48] m, z in [0.70, 1.60] m; when a fingertip enters the coffee (inside the mug radius below the coffee surface); when an arm link, the stand or the parked left hand touches the mug, the spoon or the worktop; or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control the right arm and right hand of a Tianji Marvin dual-arm stand (two 7-joint arms, a dexterous hand on each
wrist; the stand sits at the world origin facing +x, its plate on the floor at z = -0.1 m). The left arm starts parked,
hanging beside the torso, and should stay there. Every arm and finger joint is a position servo in the physics engine
under native force bounds (arm servos: stiffness 700 N m/rad, damping 48 N m s/rad, no gravity compensation, so a held
target sags under the arm's weight unless your targets account for it); stirring and laying the spoon down require
physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene
The mug, the coffee and the teaspoon are the approved T11 kitchen scene: a cream glazed mug with a rounded handle
(pointing +x) on a stone worktop (top at z = 0.75 m, front edge at x = 0.25 m), axis at x = 0.48 m, y = 0.015 m. The
source film (kinematic, without hands) starts with the spoon suspended above the rim; here the right hand holds the
teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, the bowl just above the mug (`task.json` `spoon_pos`, position and quaternion WXYZ, is the
settled start pose). The coffee is a visual surface only: it exerts no force, and the stirring is judged only from the
bowl's revolutions below that surface. Mug and spoon are free rigid bodies that move only through contact and gravity.
Cameras: `overview` (front right of the mug, wide), `closeup` (front right, close) and `top` (looking down the mug axis).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for sharpa, 20 per hand for wuji); the left arm stays parked and only the right arm and hand perform the task.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control, every actuator target in model order (radians):

- columns 0-6: left arm `SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5,
  WRIST_YAW_L_J6, WRIST_ROLL_L_J7` (actuators `<joint>_target`); columns 7-13: the same right-arm joints (`..._R_J1` to
  `..._R_J7`);
- `sharpa` (58 values): then the 22 left Sharpa Wave finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`, then the
  22 right ones `right_thumb_CMC_FE` ... `right_pinky_DIP`;
- `wuji` (54 values): then the 20 left Wuji Hand 2.2 finger targets `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`,
  `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`, `l_wuji_l_LFJ0..3`, then the 20 right ones (`r_wuji_r_...`).

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start state of each hand (`task.json`
`initial_qpos`) and its start targets (`initial_targets`) are part of the task; `s.hold_action()` returns the current
targets.

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
s = Session("coffee_stir")                      # default hand: DEXHAND_HAND or "sharpa"
s = Session("coffee_stir", hand="wuji")         # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # bowl position (mug frame), revolutions, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "top"
s.snapshot(), s.restore(snap)                   # save / restore the full simulation and predicate state
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate (`s.features()` reports the quantities the predicate uses: `bowl_cup_frame`, `bowl_radius_m`,
`bowl_submerged`, `revolutions`, `hand_spoon_contacts`, `spoon_cup_contacts`, `spoon_worktop_contacts`,
`spoon_axis_tilt_deg`, `spoon_cup_clearance_m`, speeds, `cup_tilt_deg`, `cup_slide_m`, `rest_hold_steps`). The world frame has z up; lengths are in metres and angles in radians. The worktop top is at
z = 0.75 m and the mug axis at x = 0.48 m, y = 0.015 m; the spoon start pose is `task.json` `spoon_pos` (position,
quaternion WXYZ). The right hand's mount body is `wrist_stage` (on the right arm's flange); the robot stand is at the
world origin (`task.json` `marvin`).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
