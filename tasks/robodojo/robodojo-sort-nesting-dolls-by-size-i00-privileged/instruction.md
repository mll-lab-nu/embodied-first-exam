# RoboDojo · sort_nesting_dolls_by_size (privileged)

## Task
Stand the five yellow rubber ducks upright in a straight left-to-right row, smallest on the left to largest on the
right, a little apart. Then move both arms back to where they started.

## Goal
Success: the five yellow rubber ducks stand upright in a straight left-to-right row, smallest on the left to largest on
the right, a little apart, and both arms are back where they started. A replay ends as soon as the task is done; later
rows are not run.

Deliverable: `/app/output/trajectory.npz` with `task` and `actions`, a (T, 14) float array of at most 15,000 rows, one
per action (1/25 s); write it with `s.save_trajectory()`. Anything else (another shape, NaN, more rows) scores 0. Leave
the script that produced it at `/app/output/gen.py`. It is replayed from the fixed start up to 3 times and passes if the
task succeeds in any replay. Replays can end slightly differently: leave a margin. Save a valid one early and overwrite
it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
Two simulated ARX X5 arms with parallel two-finger grippers at a table, in RoboDojo's dual-arm simulation (Isaac Sim /
Isaac Lab, PhysX). The scene is one fixed instance. You have the full simulator to develop with; you hand in a
trajectory of robot actions.

### Session
`/opt/tools/rcb_robodojo.py`, importable as `rcb_robodojo`:
```python
from rcb_robodojo import Session
s = Session("sort_nesting_dolls_by_size", instance="/app/instance.json")   # ~3-5 min: launches Isaac Sim, builds the scene, resets onto the layout
s.reset()                          # back to the frozen layout (as often as you like; see the note below)
s.instruction()                    # RoboDojo's own language instruction for this layout
s.objects()                        # label -> position, orientation_wxyz (env frame), bbox_corners
s.step(action)                     # one action (14 values) = one control step (1/25 s): see Actions
s.hold_action()                    # the action that keeps the current targets (what the robot does when idle)
p = s.primitives()                 # helpers that produce and step actions (each has a docstring):
p["move_joints"](left=q6, right=q6, steps=25); p["set_gripper"]("left", 0.0, steps=10); p["hold"](10)
p["ik"]("left", [x, y, z, qw, qx, qy, qz])         # RoboDojo's IK (cuRobo) for one arm's tool pose -> 6 joint angles, or None
p["move_ee"]("right", [x, y, z, qw, qx, qy, qz], steps=25)
s.proprio()                        # measured joints, gripper commands, end-effector poses of both arms
s.render_frame("cam_head")         # RGB uint8 (480, 640, 3): "cam_head", "cam_left_wrist", "cam_right_wrist"
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'done', 'end_reason', 'actions', 'max_actions', 'state_sha', ...}
s.replay(actions)                  # resets, replays open-loop, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen layout, writes a head-camera video
```

One `Session` per process (~3-5 min). Rendering happens only when a frame is asked for and never moves anything. Do not
call `s.close()` before writing every output. RoboDojo's source is in `/opt/RoboDojo` (read-only). The grader replays
with this command; run it to self-check (it stops at the first success):
`python /opt/tools/rcb_robodojo.py replay --task sort_nesting_dolls_by_size --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, RoboDojo's joint action. Joints:
  absolute position targets (rad). RoboDojo's controller moves each arm from where it is to the new target over the
  action's 10 physics steps: linearly for 8, then holding. Gripper: RoboDojo's normalised command, clipped to 0..1: 1 =
  fully open (as at the start), 0 = closed. A closing gripper stops at whatever is between its fingers.
  `s.hold_action()` keeps the current targets.
- Control runs at 25 Hz (physics dt 4 ms, 10 physics steps per action).
- World frame: RoboDojo's env frame, metres; quaternions are **WXYZ**. Axes: x to the right as seen from behind the arms
  (from the left arm towards the right one), y forward from the arm bases towards the far side of the table, z up. The
  left arm's base is at (-0.3, -0.45, 0.765) and the right arm's at (0.3, -0.45, 0.765), both facing +y; the table top
  is at z = 0.765 (the table spans x in [-0.7, 0.7], y in [-0.6, 0.5]). The head camera `cam_head` is at (0, -0.41,
  1.308), looking forward (+y) and 30° down; each wrist camera rides on its arm. `s.proprio()` gives each arm's
  end-effector pose in this frame.

## Others
- Labels in `s.objects()`: `doll0`..`doll4` (the yellow rubber ducks).
- RoboDojo's own reset settles the scene again from where it is. So a reset after actions gives the same layout and
  start pose, but not bit-for-bit the same state, and a replay after such a reset can end slightly differently from the
  grader's. Each graded replay is the first episode of a newly started Session, with nothing stepped before it. Test
  your trajectory the same way.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 39 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
