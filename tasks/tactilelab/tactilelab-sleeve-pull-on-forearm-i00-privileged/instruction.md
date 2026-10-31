# TactileLab · sleeve_pull_on_forearm — frozen instance

A sleeve is already on the left forearm. Pinch its pull tab with the right gripper, pull the sleeve along the forearm until its cuff reaches the target band, release it and let it rest.

Objects: the left arm is posed with its forearm horizontal; the forearm is a cylinder of radius 40 mm (half length 0.22 m) on link `J2_3`; axis coordinate t runs along it from its centre. The sleeve is a cloth tube (radius 50 mm, 9 rings of 20 particles) with its cuff ring at t = 0.02 at the start and a 5 cm pull tab on the cuff rim. Moving the left arm moves the forearm.

Success is judged on the state at the end of the replay: the conditions below must hold at the last step, and have held for the stated number of consecutive steps before it. An episode that was ended early (the cases listed after them) scores 0.
- the cuff ring's mean t is within **30 mm** of t = 0.075
- no sleeve particle is more than **4 mm** inside the forearm surface
- the sleeve is not bunched: every gap between neighbouring rings is within ±50 % of its rest value (11.25 mm)
- the gripper has released the sleeve: after both pads gripped it, no pad touches it and the pad gap is at least 50 mm
- no particle moves faster than **0.01 m/s**
- held for **30** steps

This is a *fixed scene instance*: the objects and the robot always start at the same poses. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task is solved in both replays
and both end in the same state, else 0.
After the last row the replay holds that row for 60 more control steps (1 s) before the task is judged (`s.replay` does
the same). Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have
one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded. The file holds
`task` and `actions`, a (T, 22) float array of 1 to **4,800 rows** (one per control step, 80 s of robot time);
anything else (another shape, no rows, more rows, inf or a number too large for a float32, a gripper command other than
0 or 1, an arm target with some but not all of its seven numbers NaN, outside the +-2 m box around the robot base or
with a zero-length quaternion, a finger drive setting out of its range, a file that is not such an npz) scores 0; the
standard twin refuses the same rows. A replay has a time limit of 1200 s plus 1.9 s per row (Isaac Sim start included;
the rows at half the slowest replay pace measured for this task: 10,370 s for 4,800 rows). From your first row on, a
simulator failure on your rows is your result and scores 0 (`sim_error`): an exception the simulator raises or an error
the soft-body solver reports. A replay that crashes, raises a GPU error, loses its Newton sidecar or runs out of its
time limit is replayed once more; it is your 0 only when it fails again at about the same step on a host a short
reference replay shows healthy and no replay of your trajectory got past that step. A time-out is yours when your rows,
scaled to the speed of the host the limits were measured on, replay below 1.25 x the pace the limit allows: keep your
replays well inside the limit.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_tactilelab import Session
s = Session("sleeve_pull_on_forearm", instance="/app/instance.json")   # ~1 min: launches Isaac Sim, builds the scene, resets it
s.reset()                          # back to the frozen initial state, as often as you like (see Conventions)
s.objects()                        # name -> {"position": [x, y, z], "orientation_wxyz": [w, x, y, z]} (env frame)
s.proprio()                        # joint_pos (16), right_ee_pose / left_ee_pose (7: x y z qw qx qy qz), gripper_width (2, m)
s.tactile()                        # both gel pads: tactile_left_height / tactile_right_height (60, 80) mm,
                                   # *_contact (60, 80) bool, *_press_mm; Session(..., tactile_rgb=True) adds *_rgb (240, 320, 3)
s.step(row)                        # one control step with a (22,) row (layout under Conventions)
s.hold_action()                    # the row that keeps both arms and the gripper commands as they are
s.move_ee(arm, pose7, steps=60)    # straight-line target interpolation for one arm (0 = right, 1 = left) over `steps` steps
s.set_gripper(arm, closed, steps=30)
s.record_start(); ...; actions = s.record_stop()   # (T, 22) rows, one per control step
s.status()                         # {'success': bool, 'sim_steps': int, 'resets': int, 'state_sha': str, 'metrics': {...}}
s.replay(actions)                  # resets, replays open-loop, holds the last row 60 steps, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Cameras (two wrist cameras): `Session(..., cameras=True)` then `s.render_frame("wrist_right_rgb")` /
`s.render_frame("wrist_left_rgb")` (slower: every step renders; `hfov_deg=` asks for a narrower field of view:
`help(Session.render_frame)`). The scene, robot and object files are under
`/opt/tactilelab/tactilelab_tasks/` (task logic in `rigid/task.py`, this task's scene in `tasks/sleeve_pull_on_forearm/cfg.yaml`); each
object's `Annotation/` folder holds grasp poses (`grasp_pose.json`: right end-effector poses `[x, y, z, qw, qx, qy, qz]` in
the object's frame) and insertion geometry (`insertion_pose.json`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_tactilelab.py replay --task sleeve_pull_on_forearm --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Frame: the env frame, metres, z up. The table top is at z = 1.102; the robot base is at (-0.5, 0, 1.1) facing +x.
  Quaternions are **WXYZ**.
- Action row (22): 0-6 the right end-effector target (x, y, z, qw, qx, qy, qz), 7-13 the left one, 14 and 15 the right /
  left gripper command (0 = open, 1 = closed, exactly 0 or 1), 16 and 17 an optional right / left finger-gap override in
  metres (NaN = use the open / closed command; a gap is clipped to the fingers' 0-0.102 m, so a negative one closes them
  fully, while in the standard twin a negative gap means no override), 18-21 optional right finger drive settings
  applied from that step on (NaN = unchanged): velocity limit (m/s, at most 0.2), effort limit (N, at most 20),
  stiffness (N/m, at most 10,000), damping (N s/m, at most 1,000), each above 0; the stock drive, in force after every
  reset, is 0.2 m/s, 20 N, 200 N/m and 40 N s/m (send these to restore it). In this task they change nothing (they are
  checked and recorded only). All seven of an arm's numbers NaN hold that arm where it is (some NaN is refused); a
  target lies within +-2 m of the robot base on every axis. The targets are tracked by a differential IK with joint PD
  drives, so a far target is not reached in one step: move in small increments. Rows of 16 or 18 numbers are padded with
  NaN.
- A release of the right gripper is physical: a step whose right gripper command goes from 1 (closed) to 0 (open) starts a
  release, which counts once both right finger joints have opened by at least 10 mm from where they were at that step
  (and stayed so for the number of steps a task states); a later close command withdraws it.
- The end-effector frame is the wrist link (`J1_6` right, `J2_6` left); the gel-pad centre is 0.1777 m along the wrist's +z
  axis. The right gripper opens to about 0.10 m between the gel faces; its width is 0.082 + q(J1_7) - q(J1_8) (m).
- Control runs at 60 Hz (physics 1/120 s, decimation 2). There is no step budget: the time limit (`## Time limit`) is your
  only budget (a runaway guard ends an episode after 4,860 control steps: the most a trajectory may hold and the
  replay's 60-step hold).
- One `Session` per process. Physics is PhysX on the **GPU**, as are rendering and the tactile raycast. Replaying the
  same rows in a fresh process (the CLI above, as the grader does) ends in the same state every time on a machine, but
  that state can differ slightly from the live run that recorded the rows, and after `s.reset()` the state is restored
  but not every PhysX internal. So check the final trajectory with the CLI replay, and leave a margin on the success
  thresholds rather than ending a hair past them. Deformable bodies (where a task has one) are simulated by a Newton
  sidecar on the GPU: cloth, cables and the soft plug with deterministic kernels (their replays end in the
  same state too); the dough's MPM solver is not guaranteed to, so a dough task is graded on one replay: leave a
  margin there too.

The deformable bodies (cloth, cable, dough, plug) are simulated by Newton in a sidecar process started by the Session (the first start compiles GPU kernels, a few minutes once per trial); the gel pads and fingers act on them as kinematic colliders. `s.status()['metrics']` reports the task's measured quantities every step. Pad-gap thresholds below are distances between the two gel-pad box centres (the gel-face gap plus 4 mm). Ended early if a particle drops below z = 1.052 or the cable or cloth is pushed through the back of a gel pad (two or more of its samples inside the volume up to 40 mm behind a pad for 10 consecutive steps).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **13 GiB of memory**, **2048 processes and threads**, **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`) and **one GPU, 16 GiB of its memory**. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
