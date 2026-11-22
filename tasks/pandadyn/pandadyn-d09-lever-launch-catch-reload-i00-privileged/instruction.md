# Panda Dynamic Scenes · Lever launch, catch and reload (D09) (privileged)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). A ball starts in the
right arm's cup. The right arm must load it into the small basket of a passive see-saw launcher and move its cup away.
The left arm, holding a mallet, must strike the lever so that the ball is flung up into free flight, and the right arm
must catch it in its cup. The right arm then loads the ball into the basket a second time and clears away, and the left
arm launches it again. In the end the ball must come to rest inside an open box that slides back and forth on a rail,
while the box is moving. The left arm's mallet must never touch the ball. The scene is one fixed instance: everything
starts the same way after every reset. Things move by themselves from the first control step on: the scene does not wait
for the robot. You have the full simulator to develop with; you hand in a trajectory of robot actions.

### Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.44, -0.23, 0), yaw 0 (facing +x). Its tool is a
mallet: a solid block 50 x 50 x 30 mm (along tool x, y, z), with the tool frame at its centre and axes parallel to the
hand's when the hand points straight down (x forward, z up). The mallet is carried on a side adapter of 12 mm square
bars, part of the tool: a riser from the hand down to the bar level (at tool x = -0.114, y = -0.13, from z = 0.075 down
to 0.029), a bar forward from there (y = -0.13, x from -0.12 to 0, z from 0.029 to 0.041), a cross bar along y to y =
-0.02, and a post down onto the mallet's top near its -y edge (at y = -0.02, z from 0.036 down to 0). The mallet centre
is 0.12 m ahead of the gripper TCP along tool x, 0.13 m to its tool +y side and 0.075 m below it. Start: mallet centre
at (0.16, -0.11, 0.28), tool axes aligned with the world. panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x).
Its tool is an open-top square cup: inside 0.14 x 0.14 m, walls 55 mm high and 5 mm thick on all four sides, 5 mm floor.
The tool frame is the centre of the inside floor surface, z up, x pointing away from the arm's own base. With the cup
level the hand points straight down and the cup's floor centre is 0.12 m ahead of the TCP along tool x and 0.04 m below
it. The grey adapter enters at the middle of the cup's back (tool -x) wall: a 12 mm wide post protrudes 6 mm into the
cup from the floor up to 35 mm, and a bar protrudes 12 mm into the cup between 29 and 41 mm above the floor. Start: cup
floor centre at (0.12, 0.17, 0.26), level, rotated 180 deg about z (tool x = world -x). Wrist joints 5-7 of both arms
use higher damping gains (24, 20, 14 instead of the default 12, 10, 7). On both arms the tool's adapter runs between the
fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the
episode as a collision with its own tool (both grippers start fully open, at 0.08 m).

A small orange ball (radius 18 mm) starts at rest on the floor of the right arm's cup. A passive see-saw launcher stands
in the middle of the table on an orange square post (the same orange as the ball). The launcher is blue: a lever on a
horizontal hinge parallel to world y. At the lever's end on the left arm's side (-x) sits a small square basket (54 mm
inside, 12 mm walls). On the other side of the hinge a side arm reaches toward -y to a strike pad (36 x 50 mm), which is
held a few centimetres above the lever on a spring and can be pushed down by up to 30 mm. Pushing or striking the pad
side down rotates the lever and swings the basket end upward along an arc around the hinge; stops limit the lever's
travel. At rest the lever lies horizontal on its lower stop, because the basket side is heavier and a weak return spring
also pulls it back to that position. Beyond the launcher, on the right arm's side, a blue open box (0.15 x 0.15 m
inside, 0.06 m deep) rides a straight rail along y. The box is driven back and forth along the rail in a smooth
sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the
world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the right arm loads the ball into the launcher's basket, where it comes to rest with the lever about level, and
moves its cup well clear of the launcher; the left mallet strikes the lever so that the ball is flung up into free
flight, higher than 0.20 m; the right cup catches it; the right arm loads it into the basket a second time and clears
away; the left arm launches it again; finally the ball rests in the moving box for about 0.7 s while the box moves. A
catch means the ball drops into the cup from above after flying free and stays there, not a bounce. The mallet must
never touch the ball: that fails the task at once.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The right cup (whole tool link) may touch the ball, the lever and the strike
  pad. The left mallet (whole tool link) may touch the lever and the pad, and never the ball. Neither tool may touch the
  lever's base block, the orange pedestal, the moving box or its rail and base, or the table. No other robot part, the
  fingers included, may touch anything. The two arms and their tools may never touch each other, and no arm may touch
  itself. In every task an arm never touches itself, no robot part touches the table or the floor, a robot part other
  than an allowed one touches nothing, a tool touches only what the task allows, and no contact presses deep into
  anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`: it holds `task` and `actions`, a
(T, 16) float array of at most 4,500 rows (one per control step); anything else (another shape, NaN, more rows, a file
that is not such an npz) scores 0. It is replayed open-loop from the fixed start and scores 1 if the task succeeds in
the replay, else 0. Keep the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it
when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory counts: changing the simulator's state while you develop changes nothing in the grading.

## Robot Interface
### Session
`rcb_pandadyn`, already installed (run `python` from any directory):
```python
from rcb_pandadyn import Session
s = Session(instance="/app/instance.json")   # ~5-15 s: builds the scene and resets it to the frozen instance
s.reset()                          # back to the frozen initial state (exact; as often as you like)
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 16 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 16) rows executed since the last reset: the trajectory of this episode
s.replay(actions)                  # reset, run the rows open-loop until the episode ends, return status (+ executed_rows)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.fk(q7, "panda-0"); s.ik(pose7, "panda-0", frame="tool")   # stateless kinematics: hand TCP / tool world poses <-> 7 joint angles
s.robot_spec()                     # arm bases, tools and mounts, joint limits, servo limits and gains, safety limits
s.render_frame("overview")         # RGB uint8 (480, 640, 3) of "overview" (the whole workspace) or "closeup" (the working area)
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state while filming the overview camera
s.u                                # the ManiSkill environment itself (`panda_dynamics` in /opt/pandadyn: read-only reference)
```

The tooling is deliberately thin: joint targets, kinematics and state. Catching, striking, carrying and timing are yours
to build. The environment's source is in `/opt/pandadyn/panda_dynamics`. Check a trajectory as the grader replays it:
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`. One
`Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame is
asked for and never moves anything. Do not call `s.close()` before writing every output.

### Actions
- Action row (16 values per control step): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`.
  Each arm's 8 values are its 7 absolute joint-position targets (rad, `panda_joint1..7`) and its total gripper aperture
  target (m, 0 = closed .. 0.08 = open; each finger moves at most 0.025 m/s). Values outside the joint limits
  (`s.robot_spec()`) are clipped to them before they are executed, and the trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and
  5 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
  control (PD + inverse dynamics, the Panda's torque and torque-rate limits). A new target replans from the current
  reference motion, so a target far away is reached smoothly, not in one step. `s.robot_spec()["servo"]` has the exact
  limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. A simulated episode ends at the latest at the task's
  horizon (25 s, 2500 rows).

### Observations
- World frame: metres, z up, the table top is the plane z = 0; quaternions are wxyz. Each arm's base pose is in the
  robot spec (`arms`).
- Cameras: `s.render_frame("overview")` (the whole workspace) or `s.render_frame("closeup")` (the working area), RGB 640
  x 480; `s.camera_info()` has their calibration. `s.proprio()` and `s.state()` (above) give the robot's and the scene's
  state.

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
- Resources: 5 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (3 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
