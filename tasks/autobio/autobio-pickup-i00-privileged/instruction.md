# AutoBio · pickup (privileged)

## Task
Pick up the 50 mL tube from the rack by its cap and lift it more than a hand's width.

## Goal
Success: the gripper holds the tube by its cap and has lifted it more than a hand's width. The episode ends the moment
that is reached. A physics warning (an unstable simulation, for instance after the robot was driven hard into something)
ends the episode at once, as a failure.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`. It is replayed open-loop
from the same initial state and scores 1 if its episode ends in success. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
An ALOHA arm (6 joints and a parallel gripper), fixed to the bench, in AutoBio's simulated biology laboratory (MuJoCo).
The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of robot actions.

### Session
`rcb_autobio` (installed; run `python` from any directory):
```python
from rcb_autobio import Session
s = Session(instance="/app/instance.json")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited)
s.state()                          # privileged view: qpos, qvel, ctrl, the targets in effect, tool poses, gripper openings, score
s.task, s.model, s.data            # AutoBio's task object (its scene helpers and check()), MuJoCo model / data: read them freely
s.actuators()                      # the 7 controlled actuators in action order: name, unit, range, kp, kv, force range
s.command()                        # the targets in effect (after reset: the ones that hold the initial pose)
s.step(a)                          # one control step (2 ms) with 7 targets; s.step(a, n=25) holds them 25 steps; False once the episode is over
s.status()                         # {'success', 'done', 'reason', 'score', 'steps', 'state_sha', 'instance_ok', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 7) targets, one row per control step executed
s.replay(actions)                  # resets, replays open-loop until the episode ends or the rows do, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.tcp_poses()                      # tool frames (`tcp`): x y z + wxyz quaternion, world frame
s.fk(q); s.ik({frame: pose})       # kinematics of the arm joints (s.kinematic_joints()), no physics, no collision check
s.render_frame("table_cam_front")   # RGB uint8 (480, 640, 3); cameras: table_cam_front, table_cam_left, wrist_cam; s.render_depth(cam): metres
s.render_video(actions, "/app/output/check.mp4", cameras=["table_cam_front"])
s.close()                          # release the renderer when you are done with a Session
```
There are no ready-made motions: AutoBio's scripted experts are not in this image. Its other code is, under
`/opt/AutoBio/autobio` (importable once a Session exists): the scene helpers `s.task` is built from, its inverse
kinematics (`kinematics.py`) and its path timing (`topp.py`). One control step is one physics step, 2 ms: a row is
executed for exactly one step, so a motion lasting 1 s is 500 rows (repeat a row to hold a target). Your wall-clock time
is the budget (the reference replays at about 1000 control steps/s here); the one technical cap is 600000 rows per
trajectory (1200 s of simulated time).

### Actions
- An action has 7 position targets per control step, in this order: `waist`, `shoulder`, `elbow`, `forearm_roll`,
  `wrist_angle`, `wrist_rotate`, `gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m open). Arm joints
  are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry:
  `s.actuators()`); a target outside the entry's range is clipped to it.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad.

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_autobio.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 12 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
