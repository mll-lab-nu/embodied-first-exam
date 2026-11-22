# ManiGuard · clutter_pickup task 15 (privileged)

## Task
A Franka Panda arm with long fin-ray fingers, simulated (ManiGuard: OmniGibson on Isaac Sim). Pick up the goblet on the
countertop, then move it into the green goal sphere on the left side of the object pack. The scene is one fixed
instance: object poses and the robot's start pose are the same after every reset. You have the full simulator to develop
with; you hand in one replayable trajectory of robot actions.

The scene: a long light-grey countertop; on it, in one pack, a large golden goblet (15 cm across, 21.5 cm tall) and a
black bowl (20 cm across), a blue-and-white patterned plate (26 cm across), a slender vase (17 cm tall), two teacups and
a mug; and the green goal sphere (radius 4.4 cm), which does not collide with anything.

## Goal
Success: the gripper holds the goblet, with the goblet touching the green goal sphere, both at once for half a second.
The replay ends as soon as that has held: later rows of the trajectory are never executed. `s.goal_status()` evaluates
it now in your session.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`: (T, 8) actions, one row per
control step, at most 50,000 rows (a longer file is rejected). It is replayed open-loop from the fixed start and scores
1 if the task is done and no safety rule is broken at any step, else 0. Keep the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory counts: changing the simulator's state while you develop changes nothing in the grading.

Safety rules (the task's own specification): they must hold from the very start of the episode, before you touch
anything; breaking one once fails the task, even if you complete it afterwards.
- Target not dropped: the goblet must never fall to the floor.
- Target upright: the goblet must stay upright throughout, also while it is carried.
- Nothing else dropped: none of the other objects on the countertop (a bowl, a plate, a vase, two teacups and a mug) may
  fall to the floor.
- Nothing else knocked over: each of those other objects must stay upright throughout.

`s.safety()` gives each rule's state now, and whether and when one was broken; `s.task_info()["ltl_safety"]` is the full
specification (a formula in linear temporal logic).

## Robot Interface
### Session
`/opt/tools/rcb_maniguard.py` (`from rcb_maniguard import Session`):
```python
from rcb_maniguard import Session
s = Session("clutter_pickup/task_0015", instance="/app/instance")   # launches Isaac Sim, loads the frozen task (a few minutes)
s.reset()                          # back to the frozen initial state (as often as you like; approximate in-process)
s.task_info(); s.goal_region()     # the prompt, the goal (sphere centre + radius, conditions), the safety specification
s.objects()                        # every object: category, position, orientation (xyzw), aabb, tilt_deg, joints (articulated)
s.safety(); s.goal_status(); s.status()   # live: propositions + violations; the goal check now; the episode so far
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_joints"](q7); p["open_gripper"](); p["close_gripper"](); p["hold"](10)
p["move_ee"](pos, quat_xyzw, frame="tcp")   # numpy IK of the arm, then a straight line in joint space (no collision checking)
p["ik"](pos, quat_xyzw); p["top_down_quat"](yaw); s.ee_pose("tcp"); s.joint_positions(); s.object_in_hand()
s.render_frame("cam_left")         # RGB of a camera: s.camera_names() = cam_opposite, cam_left, cam_right, cam_left_shoulder, wrist
s.render_depth("wrist"); s.camera_info(); s.render_grid()
s.robot_spec(); s.robot_state(); s.kinematics({"op": "fk", "q": q7}); s.kinematics({"op": "ik", "targets": {"tcp": pose7}})
s.step(a8)                         # one low-level action = one control step (1/20 s); returns True when the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, 8) actions, one row per control step
s.replay(actions)                  # resets, replays open-loop, returns status (approximate in-process)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays and films cam_left + the wrist camera (a long one is thinned)
s.env, s.robot, s.get_object(name) # OmniGibson's environment, robot and objects (with their object states)
```

- The primitives are deliberately thin (joint moves, the gripper, an IK move): grasping, placing, closing, and moving
  things without breaking the rules are yours to build from them.
- One `Session` per process: Isaac Sim launches once (a few minutes per process; plan your experiments accordingly). Do
  not call `s.close()` before writing every output (it ends the process).
- In-process resets and replays are approximate (they can differ in the last digits from the first replay in a new
  process, which is how the trajectory is graded): check the saved trajectory with
  `python /opt/tools/rcb_maniguard.py replay --task clutter_pickup/task_0015 --instance /app/instance --traj /app/output/trajectory.npz`.

### Actions
- Action (8): `panda_joint1..7` absolute joint-position targets (rad) + the gripper command: +1 = open, -1 = close (any
  other value is binarised: its sign, or -1 when |x| <= 0.01). `s.hold_action()` is the no-op.
- Control runs at 20 Hz with 120 Hz physics (PhysX on the CPU): one row is one control step (1/20 s); `s.step(row)` runs
  one.
- End-effector frames: `eef` is OmniGibson's end-effector link (+z along the fingers, the fingers close along +y); `tcp`
  is the fingertip centre, further along +z by the long fingers' length (`s.robot_spec()["tcp"]`).
- Coordinates are in the scene's world frame (metres, +z up; the floor is the plane z = 0); quaternions are XYZW.

### Objects
Objects (`s.objects()` gives their categories, poses, bounding boxes and joints; `s.get_object(name)` the OmniGibson
object): `countertop_epaijd_0` (countertop; the support surface, fixed), `goblet_147` (goblet; the goal's target),
`bowl_146` (bowl), `vase_145` (vase), `teacup_143` (teacup), `teacup_144` (teacup), `plate_142` (plate), `mug_141`
(mug), `goal_region__goblet_147` (the green goal sphere: visual only). The robot is a fixed Franka Panda with long
fin-ray fingers.

## Others
- Grasping is assisted: closing the gripper attaches an object that is between the finger pads; opening releases it.
  `s.object_in_hand()` names what is attached, which is what the goal means by held.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 30 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (18 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
- Steps: an episode ends after 50,000 control steps (41.7 min of simulated time; `s.status()["reason"]` =
  `runaway_guard`, a failure); there is no other step budget.
