# TactileLab · cable_slack_reduce — frozen instance

A cable's head is clamped under a bar; its free part bulges to the side and its tail rests on a notched ridge. Pinch the cable between the gel pads and pull it straight, without letting it slip.

Objects: a 0.26 m cable (radius 3.5 mm) whose first segments are pinned under a clamp bar at about (-0.153, -0.065); a 15.8 mm high, 3 mm wide notched ridge under its tail from x ≈ -0.058 to 0.062 at y ≈ -0.065 (fixed).

Success is judged on the state at the end of the replay: the conditions below must hold at the last step, and have held for the stated number of consecutive steps before it. An episode that was ended early (the cases listed after them) scores 0.
- the cable has been pinched: at some step both pads touched it and the pad gap was at most 22.5 mm; the material point gripped then is the reference
- from the clamp to the gripped point the cable is straight: its length over the chord is at most **1.03**
- the pads have not slid along the cable by more than **12 mm** from the gripped point
- the cable is not stretched beyond **1.06** times its length
- held for **20** steps

This is a *fixed scene instance*: the objects and the robot always start at the same poses. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in one fresh process and scored 1 if the task is solved in the replay, else 0.
After the last row the replay holds that row for 60 more control steps (1 s) before the task is judged (`s.replay` does
the same). Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have
one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded. The file holds
`task` and `actions`, a (T, 22) float array of at most **30,000 rows** (one per control step, 500 s of robot time);
anything else (another shape, inf, NaN in a gripper column, more rows, a file that is not such an npz) scores 0. Each
replay has max(1800 s, 900 s + 1 s per 4 rows) of wall clock.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_tactilelab import Session
s = Session("cable_slack_reduce", instance="/app/instance.json")   # ~1 min: launches Isaac Sim, builds the scene, resets it
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
`s.render_frame("wrist_left_rgb")` (slower: every step renders). The scene, robot and object files are under
`/opt/tactilelab/tactilelab_tasks/` (task logic in `rigid/task.py`, this task's scene in `tasks/cable_slack_reduce/cfg.yaml`); each
object's `Annotation/` folder holds grasp poses (`grasp_pose.json`: right end-effector poses `[x, y, z, qw, qx, qy, qz]` in
the object's frame) and insertion geometry (`insertion_pose.json`).

The grader replays in one fresh process, exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_tactilelab.py replay --task cable_slack_reduce --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Frame: the env frame, metres, z up. The table top is at z = 1.102; the robot base is at (-0.5, 0, 1.1) facing +x.
  Quaternions are **WXYZ**.
- Action row (22): 0-6 the right end-effector target (x, y, z, qw, qx, qy, qz), 7-13 the left one, 14 and 15 the right /
  left gripper command (0 = open, 1 = closed), 16 and 17 an optional right / left finger-gap override in metres (NaN = use
  the open / closed command), 18-21 optional right finger drive settings applied from that step on (NaN = unchanged):
  velocity limit (m/s), effort limit (N, the drive's default is 20 N), stiffness, damping. A NaN in an arm's seven numbers
  holds that arm where it is. The targets are tracked by a differential IK with joint PD drives, so a far target is not
  reached in one step: move in small increments. Rows of 16 or 18 numbers are padded with NaN.
- A release of the right gripper is physical: a step whose right gripper command goes from 1 (closed) to 0 (open) starts a
  release, which counts once both right finger joints have opened by at least 10 mm from where they were at that step
  (and stayed so for the number of steps a task states); a later close command withdraws it.
- The end-effector frame is the wrist link (`J1_6` right, `J2_6` left); the gel-pad centre is 0.1777 m along the wrist's +z
  axis. The right gripper opens to about 0.10 m between the gel faces; its width is 0.082 + q(J1_7) - q(J1_8) (m).
- Control runs at 60 Hz (physics 1/120 s, decimation 2). There is no step budget: the time limit (`## Time limit`) is your
  only budget (a runaway guard ends an episode after 30,000 control steps, the most a trajectory may hold).
- One `Session` per process. Physics is PhysX on the **GPU**, as are rendering and the tactile raycast. Replaying the
  same rows in a fresh process (the CLI above, as the grader does) ends in the same state every time on a machine, but
  that state can differ slightly from the live run that recorded the rows, and after `s.reset()` the state is restored
  but not every PhysX internal. So check the final trajectory with the CLI replay, and leave a margin on the success
  thresholds rather than ending a hair past them. Deformable bodies (where a task has one) are simulated by a Newton
  sidecar on the GPU, whose replays agree closely but not bit for bit.

The deformable bodies (cloth, cable, dough, plug) are simulated by Newton in a sidecar process started by the Session (the first start compiles GPU kernels, a few minutes once per trial); the gel pads and fingers act on them as kinematic colliders. `s.status()['metrics']` reports the task's measured quantities every step. Pad-gap thresholds below are distances between the two gel-pad box centres (the gel-face gap plus 4 mm). Ended early if a pad or finger touches the ridge or its lips (more than 0.2 mm overlap), the pads lose the cable for more than 25 steps after the pinch, a node drops below z = 1.072, or the cable or cloth is pushed through the back of a gel pad (two or more of its samples inside the volume up to 40 mm behind a pad for 10 consecutive steps).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **24 GiB of GPU memory**, **24 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
