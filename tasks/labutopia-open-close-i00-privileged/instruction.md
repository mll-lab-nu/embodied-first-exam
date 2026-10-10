# LabUtopia · open_close — frozen instance

You control a **Franka Panda** arm (7 joints) with its two-finger gripper, fixed to a laboratory bench, in LabUtopia's simulated chemistry laboratory (NVIDIA Isaac Sim, PhysX), via Python,
through joint targets.
**Task:** Open the top drawer of the cabinet, let go of it, then close it again and let go. Success, at the first control step at which the second condition has held for 60 consecutive control steps (1 s): (1) for 60 consecutive control steps, the drawer handle's centre (`/World/Cabinet_01/drawer_handle_top`) is more than 0.13 m from where it started and the hand (the point between the fingertips) is more than 0.04 m from the handle's centre; (2) after that, measured from where the handle was at the step (1) was met: the handle's centre is more than 0.13 m from there and nearer to where it started than it was at that step (the drawer has come back, not gone further out), and the hand is more than 0.04 m from the handle's centre.

On the bench in front of the arm: a grey cabinet with a white top, about 67 cm deep, 76 cm wide and 79 cm high: two drawers at the top, one above the other, each with a bar handle, and two doors below them. Everything is closed.

The rule is evaluated after every control step (`s.rule` in the tooling: class `OpenCloseRule`, a copy of the success
check of LabUtopia's own controller for this task); the first step at which it is met ends the episode in success.
Positions are LabUtopia's own readings: an object's centre is the centre of its bounding box (`s.centre(path)`), the
hand is the point between the fingertips (`s.hand()`).

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Your time budget is 5400 s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_labutopia import Session
s = Session(instance="/app/instance.json")   # ONE per process. Simulation only (no renderer): about a minute the first
                                   # time in this container, then about 20 s
# s = Session(instance="/app/instance.json", cameras=True)   # with the renderer and the task's cameras: the first such
                                   # Session in this container takes 5 to 10 minutes (Isaac Sim prepares the stage
                                   # for rendering once; longer on a busy host), later ones about 30 s. The physics
                                   # is the same either way
s.reset()                          # back to the initial state (unlimited; see "Fresh processes" below)
s.state()                          # joint positions / velocities, the targets in effect, tool pose, gripper opening, what the rule looks at
s.rule.values(); s.rule.text       # the quantities of the rule at the current state, and the rule in words
s.centre(path); s.size(path); s.origin(path); s.pose(path)   # LabUtopia's readings of any prim (USD path, e.g. from s.rule.values());
                                   # s.size is its bounding-box extent as LabUtopia computes it: a component can be negative
s.rigid_bodies()                   # the USD paths of every rigid body of the scene
s.hand(); s.tcp_pose()             # the point between the fingertips: position; x y z + wxyz quaternion
s.task, s.cfg, s.stage, s.robot, s.objects   # LabUtopia's task object and config, the USD stage, the robot, its ObjectUtils: read freely
s.command()                        # the 18 targets in effect (after reset: LabUtopia's initial targets)
s.action_limits()                  # (18, 2): the range of each entry
s.step(q)                          # one control step (1/60 s): 9 position targets; s.step(q, qd) adds 9 velocity targets;
                                   # s.step(q, n=30) holds them 30 steps; False once the episode is over
s.status()                         # {'success', 'done', 'reason', 'steps', 'state_sha', 'instance_ok', 'rule_state', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 18) targets, one row per control step executed
s.replay(actions)                  # from the start (a Session that has stepped is reset first), open-loop, until the
                                   # episode ends or the rows do; returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.fk(q7); s.ik({"tcp": pose})      # kinematics of the seven arm joints (numpy: no physics, no collision check)
s.render_frame("camera_1")       # (cameras=True) RGB uint8 (512, 512, 3); cameras: camera_1, camera_2, wrist_cam; s.render_depth(cam): metres
                                   # (glassware is nearly transparent in RGB and absent from the depth maps)
s.camera_info(cam)                 # (cameras=True) intrinsics and pose of a camera
s.render_video(actions, "/app/output/check.mp4", cameras=["camera_1"])   # (cameras=True)
```
Isaac Sim prints a lot when it starts; without cameras that includes Vulkan errors (`vkCreateInstance failed`, `GPU
Foundation is not initialized`): expected, the simulation-only Session runs without the renderer. Your own `print`
output comes through as usual, and an uncaught exception still ends your script with a non-zero status.

There are no ready-made motions: LabUtopia's scripted controllers and their motion primitives are not in this image.
The rest of LabUtopia is, under `/opt/labutopia` (importable once a Session exists), and so is Isaac Sim's own motion
generation for the Franka (RMPflow and the Lula kinematics, `isaacsim.robot_motion.motion_generation`; LabUtopia's
wrapper is `/opt/labutopia/robots/franka/rmpflow_controller.py`). Import `pxr`, `omni.*` and `isaacsim.*` modules only
after the Session exists: Isaac Sim loads its own build of USD when the application starts, and with a `pxr` imported
earlier some of its extensions fail to start (at worst the process ends with a symbol lookup error). Do not name a
script after a standard-library module (`inspect.py`, `types.py`): Isaac Sim imports those as it starts.

**Fresh processes.** Isaac Sim repeats an episode bit for bit only in a fresh process: after `s.reset()` the start
state differs from the first one by about 1e-5, which a contact-rich motion can amplify. The grader replays your
trajectory in fresh processes, so check the final one the same way before you stop:
`python /opt/tools/rcb_labutopia.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`
(prints `RESULT {...}` with `success` and `state_sha`; two runs of it must agree; `--video FILE` also renders it).

## Conventions
- Action: 18 numbers per control step: a position target for each of the 9 joints (`panda_joint1` .. `panda_joint7`
  in rad, then `panda_finger_joint1`, `panda_finger_joint2` in m from the gripper's centre line), then a velocity
  target for each (rad/s; m/s; zeros if you give only positions). Each joint has a drive: effort = stiffness x
  (position target - q) + damping x (velocity target - qdot), limited (`s.robot_spec()["controller"]["gains"]`,
  `["joints"]`). `panda_finger_joint2` mirrors `panda_finger_joint1`: its targets are ignored.
- The fingers travel from 0 (closed) to 0.04 m (open) each. A position target may lie beyond a joint's range (arm:
  by 0.1 rad; fingers: -0.1 .. 0.1 m): the joint stops and the drive keeps pushing, so a finger target below the
  point where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Targets outside
  `s.action_limits()` are clipped, and all targets are stored as float32.
- One control step is one physics step, 1/60 s (LabUtopia's own rate): a row is executed for exactly one step, so a
  motion lasting 1 s is 60 rows (repeat a row to hold a target). Your wall-clock time is the budget (a replay runs at
  about 200 control steps/s here); the one technical cap is 36000 rows per trajectory (600 s of simulated
  time).
- At the start the arm is not at rest: LabUtopia's reset leaves it straight up, moving towards its home pose (the
  targets in effect, `s.command()`); holding them brings it there in about two seconds.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad. The arm's base is at
  `s.robot_spec()["base"]["pose"]`.
- Only the rows are replayed: anything else you change in the scene is lost in the grader's fresh process.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of GPU memory**, **32 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.
