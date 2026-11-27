# LabUtopia · place (privileged)

## Task
Pick up the beaker, lifting it more than a hand's width, and set it down in the middle of the white square plate; then
let go and move the hand away.

## Goal
Success: after being lifted more than a hand's width, the beaker rests in the middle of the white plate, with the hand
let go and moved away, for a second. The episode ends the moment that is reached.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`. It is replayed open-loop
from the same initial state and scores 1 if its episode ends in success. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench, in LabUtopia's simulated
chemistry laboratory (NVIDIA Isaac Sim). The scene is one fixed instance. You have the full simulator to develop with;
you hand in a trajectory of robot actions.

### Session
`rcb_labutopia` (installed; run `python` from any directory):
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
There are no ready-made motions: LabUtopia's scripted controllers and their motion primitives are not in this image. The
rest of LabUtopia is in this image, under `/opt/labutopia` (importable once a Session exists). So is Isaac Sim's own
motion generation for the Franka: RMPflow and the Lula kinematics (`isaacsim.robot_motion.motion_generation`).
LabUtopia's wrapper for it is `/opt/labutopia/robots/franka/rmpflow_controller.py`. Import `pxr`, `omni.*` and
`isaacsim.*` modules only after the Session exists. Isaac Sim loads its own build of USD when the application starts; if
`pxr` was imported earlier, some of its extensions fail to start, and at worst the process ends with a symbol lookup
error. Do not name a script after a standard-library module (`inspect.py`, `types.py`): Isaac Sim imports those as it
starts. One control step is one physics step, 1/60 s (LabUtopia's own rate): a row is executed for exactly one step, so
a motion lasting 1 s is 60 rows (repeat a row to hold a target). Your wall-clock time is the budget; a replay runs at
about 200 control steps/s here. A trajectory has at most 36,000 rows (600 s of simulated time).

### Actions
- An action has 18 numbers per control step. First comes a position target for each of the 9 joints: `panda_joint1` ..
  `panda_joint7` in rad, then `panda_finger_joint1`, `panda_finger_joint2` in m from the gripper's centre line. Then
  comes a velocity target for each joint (rad/s; m/s), all zeros if you give only positions. Each joint has a drive:
  effort = stiffness x (position target - q) + damping x (velocity target - qdot), limited
  (`s.robot_spec()["controller"]["gains"]`, `["joints"]`). `panda_finger_joint2` mirrors `panda_finger_joint1`: its
  targets are ignored.
- The fingers travel from 0 (closed) to 0.04 m (open) each. A position target may lie beyond a joint's range (arm: by
  0.1 rad; fingers: -0.1 .. 0.1 m). The joint then stops and the drive keeps pushing, so a finger target below the point
  where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Targets outside `s.action_limits()`
  are clipped, and all targets are stored as float32.
- At the start the arm is not at rest. LabUtopia's reset leaves it straight up, moving towards its home pose (the
  targets in effect, `s.command()`). Holding those targets brings it there in about two seconds.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad. The arm's base is at
  `s.robot_spec()["base"]["pose"]`.

### Startup output
- Isaac Sim prints a lot when it starts. Without cameras this includes Vulkan errors (`vkCreateInstance failed`,
  `GPU Foundation is not initialized`). They are expected: the simulation-only Session runs without the renderer. Your
  own `print` output comes through as usual, and an uncaught exception still ends your script with a non-zero status.

## Others
- Labels in `s.rule.values()` (USD paths): `object` (the beaker), `target` (the white square plate).
- Isaac Sim repeats an episode exactly only in a newly started process. After `s.reset()` the start state differs from
  the first one by about 1e-5, and a contact-rich motion can amplify that difference. So check the final trajectory from
  the command line before you stop:
  `python /opt/tools/rcb_labutopia.py replay --instance /app/instance.json --traj /app/output/trajectory.npz` (prints
  `RESULT {...}` with `success` and `state_sha`; `--video FILE` also renders it).

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 32 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
