# VLABench · select_poker_semantic (privileged)

## Task
Pick up the six of spades and hold it at least a hand's length above the table.

## Goal
Success: the six of spades is in the gripper, at least a hand's length above the table. Your trajectory is replayed from
the fixed start. The episode ends as soon as the task is done, and the trajectory must end on that step: any action
after it makes the trajectory invalid.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: key `actions`, shape `(T, 9)`, 1 ≤ T ≤
4000; only this file is graded. Also leave two files for the people who read your work. `/app/output/gen.py`: the script
that produced the trajectory; it should run and reproduce `trajectory.npz` from `/app/instance.json`.
`/app/output/NOTES.md`: at most 20 lines on your final approach and why it works, and what you tried that failed. Save a
valid trajectory early and overwrite it when you have a better one.

Rules: **No cheating.** VLABench's general skills are allowed. Do not search for, download or use any existing solution
(published or reference solutions, VLABench's expert solutions, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm at a table (VLABench on MuJoCo). The scene is one fixed instance. You have the full simulator to
develop with; you hand in a trajectory of robot actions.

### Session
`/opt/tools/vlb_tool.py`, importable as `vlb_tool`:
```python
import numpy as np, vlb_tool
s = vlb_tool.Session("/app/instance.json")  # the frozen instance; s.env is the VLABench (dm_control) environment
st = s.state()           # entities {name: category, position, quaternion_wxyz, grasp keypoints / place point where
                         #   defined, joint_positions if articulated}, robot {joint, finger and tcp state}, success
s.step(a)                # one control step (0.1 s) -> {"success", "done", "control_steps", "state_sha"}
s.skill("pick", target_entity_name="...")   # VLABench's general skills (vlb_tool.SKILLS) as planning primitives;
                                            #   the control steps they execute are recorded like any other
s.ik(position, quaternion_wxyz)             # inverse kinematics for the hand -> {"success", "joint_positions"}
s.actions                # every control step since the last reset (what save_trajectory() writes)
s.save_trajectory()      # -> /app/output/trajectory.npz
s.replay(A)              # reset, then replay A (as the grader does)
s.reset()                # back to the frozen start, as often as you like
o = s.observe("forward") # rgb, depth_m, intrinsic_cv, cam2world_gl; cameras forward, left, right, wrist
```

`s.step()` and `s.status()` report `success` and `done`.

### Actions
- An action is 9 absolute position targets for VLABench's own actuators: the 7 arm joints (rad) and the 2 fingers (m, 0
  closed … 0.04 open). Each action is held for one control step (0.1 s, 100 physics steps). The model sets no arm joint
  limits; the Panda's own are [-2.90, 2.90], [-1.76, 1.76], [-2.90, 2.90], [-3.07, -0.07], [-2.90, 2.90], [-0.02, 3.75],
  [-2.90, 2.90] rad.
- World frame: metres; the robot's base is at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions are w x y z.
- Everything in `s.env` and `s.physics` is readable (privileged mode). VLABench's expert solutions for its tasks are not
  in this image.

## Others
- `s.state()["instruction"]` holds VLABench's own wording of the task; the Task and Goal here say what counts.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 20 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
