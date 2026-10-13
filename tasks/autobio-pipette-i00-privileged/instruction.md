# AutoBio · pipette — frozen instance

You control two **UR5e** arms fixed to the bench: `arm1` carries a dexterous hand that holds a pipette (its thumb presses the plunger); `arm2` has a Robotiq 2F-85 gripper, in AutoBio's simulated biology laboratory (MuJoCo 3.3.0), via Python, through joint
position targets.
**Task:** Aspirate from the 50 mL centrifuge tube with the pipette. AutoBio's test is a sequence: (1) with the plunger pressed (the thumb's target, action entry `arm1_dh_rh_thj3`, above 0.70 rad), the pipette tip is within 6.5 mm (horizontally) of the tube's axis and more than 5 mm below the liquid surface; (2) the plunger is released (the thumb's target below 0.45 rad) while the tip is still below the surface; (3) success at the first control step after (1) and (2) where the tip is more than 5 cm above the liquid surface. The tube holds 31.5 mL; the test is on positions and commands, and no liquid actually moves (AutoBio models the liquid's surface in the tube, not its transfer).

On the bench, between the arms: a rack with an open, part-filled 50 mL tube standing in it. AutoBio's prompt for this task: "one arm lifts centrifuge tube, the other aligns pipette tip and aspirates liquid"; the test itself does not ask for the tube to be lifted.

AutoBio's own success test is `s.task.check()`: class `Pipette` in `/opt/AutoBio/autobio/mani_pipette.py`.
Robot Coding Bench evaluates it after every control step: the first step at which it holds ends the episode in success (AutoBio's own rule for this task; its time limit is lifted).

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_autobio import Session
s = Session(instance="/app/instance.json")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited)
s.state()                          # privileged view: qpos, qvel, ctrl, the targets in effect, tool poses, gripper openings, score
s.task, s.model, s.data            # AutoBio's task object (its scene helpers and check()), MuJoCo model / data: read them freely
s.actuators()                      # the 14 controlled actuators in action order: name, unit, range, kp, kv, force range
s.command()                        # the targets in effect (after reset: the ones that hold the initial pose)
s.step(a)                          # one control step (2 ms) with 14 targets; s.step(a, n=25) holds them 25 steps; False once the episode is over
s.status()                         # {'success', 'done', 'reason', 'score', 'steps', 'state_sha', 'instance_ok', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 14) targets, one row per control step executed
s.replay(actions)                  # resets, replays open-loop until the episode ends or the rows do, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.tcp_poses()                      # tool frames (`arm1_tcp`, `arm2_tcp`): x y z + wxyz quaternion, world frame
s.fk(q); s.ik({frame: pose})       # kinematics of the arm joints (s.kinematic_joints()), no physics, no collision check
s.render_frame("table_cam_front")   # RGB uint8 (480, 640, 3); cameras: table_cam_front, table_cam_left, arm1_wrist_cam, arm2_wrist_cam; s.render_depth(cam): metres
s.render_video(actions, "/app/output/check.mp4", cameras=["table_cam_front"])
s.close()                          # release the renderer when you are done with a Session
```
There are no ready-made motions: AutoBio's scripted experts are not in this image. Its other code is, under
`/opt/AutoBio/autobio` (importable once a Session exists): the scene helpers `s.task` is built from, its inverse
kinematics (`kinematics.py`) and its path timing (`topp.py`).

CLI equivalent of the grader:
`python /opt/tools/rcb_autobio.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 14 position targets per control step, in this order: `arm1_shoulder_pan`, `arm1_shoulder_lift`, `arm1_elbow`, `arm1_wrist_1`, `arm1_wrist_2`, `arm1_wrist_3`, `arm1_dh_rh_thj3` (the thumb joint that presses the pipette's plunger: 0 .. 1.3 rad, larger presses), `arm2_shoulder_pan`, `arm2_shoulder_lift`, `arm2_elbow`, `arm2_wrist_1`, `arm2_wrist_2`, `arm2_wrist_3`, `arm2_2f85_fingers_actuator` (the Robotiq gripper: 0 open .. 255 closed). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry: `s.actuators()`); a target outside the entry's range is clipped to it.
- One control step is one physics step, 2 ms: a row is executed for exactly one step, so a motion lasting 1 s is 500
  rows (repeat a row to hold a target). Your wall-clock time is the budget (the reference replays at about
  2000 control steps/s here); the one technical cap is 600000 rows per trajectory (1200 s of simulated
  time). A MuJoCo physics warning (an unstable simulation) ends the episode as a failure.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad.
- Only the rows are replayed: anything else you change in `s.model` or `s.data` is lost in the grader's fresh process.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
