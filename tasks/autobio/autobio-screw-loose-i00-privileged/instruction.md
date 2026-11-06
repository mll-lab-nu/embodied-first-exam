# AutoBio · screw_loose — frozen instance

You control two **ALOHA arms** (`arm1` and `arm2`; 6 joints and a parallel gripper each), fixed to the bench on either side of the rack, in AutoBio's simulated biology laboratory (MuJoCo 3.3.0), via Python, through joint
position targets.
**Task:** Unscrew the cap of the 50 mL centrifuge tube and lift it off. Success at the first control step where the cap is more than 0.15 m above the tube body's origin (screwed on it sits 0.1197 m above it, so more than 3.03 cm up), `arm1`'s left finger (geom `1/aloha:leftfinger`) touches the cap (geom `6/cap_cyl`), and the cap's thread (geom `6/nut`) no longer touches the tube's (geom `7/bolt`).

On the bench: a rack with a 50 mL tube standing in it, its cap screwed on. The thread is a real one: the cap comes off only by turning it. AutoBio's prompt for this task: "one stabilizes tube while the other twists cap".

AutoBio's own success test is `s.task.check()`: class `ScrewLoose` in `/opt/AutoBio/autobio/screw_loosen.py`.
Embodied First Exam evaluates it after every control step: the first step at which it holds ends the episode in success (AutoBio's own rule for this task; its time limit is lifted).

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in one fresh process and scored 1 if the episode ends in success, else 0.
Also leave the script that produced it at `/app/output/gen.py`.

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
`python /opt/tools/rcb_autobio.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Action: 14 position targets per control step, in this order: `arm1_waist`, `arm1_shoulder`, `arm1_elbow`, `arm1_forearm_roll`, `arm1_wrist_angle`, `arm1_wrist_rotate`, `arm1_gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m open), `arm2_waist`, `arm2_shoulder`, `arm2_elbow`, `arm2_forearm_roll`, `arm2_wrist_angle`, `arm2_wrist_rotate`, `arm2_gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m open). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry: `s.actuators()`); a target outside the entry's range is clipped to it.
- One control step is one physics step, 2 ms: a row is executed for exactly one step, so a motion lasting 1 s is 500
  rows (repeat a row to hold a target). Your wall-clock time is the budget (the reference replays at about
  800 control steps/s here); the one technical cap is 600000 rows per trajectory (1200 s of simulated
  time). A MuJoCo physics warning (an unstable simulation) ends the episode as a failure.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad.
- Only the rows are replayed: anything else you change in `s.model` or `s.data` is lost in the grader's fresh process.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **12 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
