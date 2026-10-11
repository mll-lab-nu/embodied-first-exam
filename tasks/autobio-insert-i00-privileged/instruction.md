# AutoBio · insert — frozen instance

You control a **UR5e** arm (6 joints) with a Robotiq 2F-85 gripper, fixed to the bench, in AutoBio's simulated biology laboratory (MuJoCo 3.3.0), via Python, through joint
position targets.
**Task:** Move the 50 mL centrifuge tube from the rack it stands in to the other rack, into the slot at row 0, column 4 (AutoBio's indices: `s.task.rack2.get_position(s.data, 0, 4, '50ml')`). Success at the first control step where the tube's body is within 15 mm (horizontally) of that slot's centre and its height is between 0.829 and 0.831 m (standing in a slot it is at 0.830 m).

On the bench: two 10-slot tube racks (2 rows of 5 each) side by side, with one capped 50 mL tube standing in one of them.

AutoBio's own success test is `s.task.check()`: class `Insert` in `/opt/AutoBio/autobio/transfer_centrifuge_tube.py`.
Robot Coding Bench evaluates it after every control step: the first step at which it holds ends the episode in success (AutoBio's own rule for this task; its time limit is lifted).

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Your time budget is 3600 s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
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
s.replay(actions)                  # resets, replays open-loop until the episode ends or the rows do, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.tcp_poses()                      # tool frames (`tcp`): x y z + wxyz quaternion, world frame
s.fk(q); s.ik({frame: pose})       # kinematics of the arm joints (s.kinematic_joints()), no physics, no collision check
s.render_frame("table_cam_front")   # RGB uint8 (480, 640, 3); cameras: table_cam_front, table_cam_left, wrist_cam; s.render_depth(cam): metres
s.render_video(actions, "/app/output/check.mp4", cameras=["table_cam_front"])
s.close()                          # release the renderer when you are done with a Session
```
There are no ready-made motions: AutoBio's scripted experts are not in this image. Its other code is, under
`/opt/AutoBio/autobio` (importable once a Session exists): the scene helpers `s.task` is built from, its inverse
kinematics (`kinematics.py`) and its path timing (`topp.py`).

CLI equivalent of the grader:
`python /opt/tools/rcb_autobio.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 7 position targets per control step, in this order: `shoulder_pan`, `shoulder_lift`, `elbow`, `wrist_1`, `wrist_2`, `wrist_3`, `2f85_fingers_actuator` (the Robotiq gripper: 0 open .. 255 closed). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry: `s.actuators()`); a target outside the entry's range is clipped to it.
- One control step is one physics step, 2 ms: a row is executed for exactly one step, so a motion lasting 1 s is 500
  rows (repeat a row to hold a target). Your wall-clock time is the budget (the reference replays at about
  1000 control steps/s here); the one technical cap is 600000 rows per trajectory (1200 s of simulated
  time). A MuJoCo physics warning (an unstable simulation) ends the episode as a failure.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad.
- Only the rows are replayed: anything else you change in `s.model` or `s.data` is lost in the grader's fresh process.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
