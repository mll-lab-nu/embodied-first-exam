# Panda Dynamic Scenes · Spring gate switchyard (D07) (privileged)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). A low-friction puck
slides inside a U-shaped pen of bouncy rails that is open toward the right arm, and a spring-loaded swinging gate stands
inside the pen. The left Panda has a bare gripper. It must take hold of the gate's handle (the block on the gate's free
end) with both fingers, swing the gate open one way, and keep holding the handle with the gate well open whenever a
later phase is judged. The right Panda's paddle must then hit the puck so that it travels deep into the pen. While the
puck runs round, the left hand, still gripping, must swing the gate the other way: at the moment the puck hits the upper
(+y) rail, the gate must be at that opposite angle. The right paddle then intercepts the puck. Finally the puck must
cross a goal line in front of a backstop on the right arm's side while the left hand still holds the handle with the
gate deflected well away from its rest position and the paddle is not touching the puck. The scene is one fixed
instance: everything starts the same way after every reset. Things move by themselves from the first control step on:
the scene does not wait for the robot. You have the full simulator to develop with; you hand in a trajectory of robot
actions.

### Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It has no tool and uses the stock Panda parallel gripper:
two fingers with a total opening of up to 0.08 m, fully open (0.04 m per finger) at reset. Its tool frame, reported as
`panda-0_tool_pose`, is the gripper TCP between the fingertips. At the start the TCP is at (0.04, -0.10, 0.16), pointing
straight down (quaternion (0, 1, 0, 0)), with the fingers closing along world y. panda-1 (right): base at (0.74, 0.22,
0), yaw pi (facing -x). It carries a flat rigid paddle, 0.10 m long, 0.05 m tall and 12 mm thick, on a rigid adapter on
its back (tool -x) side: a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post
at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from
-0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool link. The tool frame is the paddle
centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre and 0.04 m
above it. Paddle start: centre (0.30, -0.08, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg, faces normal to world x);
its lower edge is then 0.020 m above the table. On panda-1 the paddle's adapter runs between the fingertips: closing
that gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a
collision with its own tool (it starts fully open, at 0.08 m).

An orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction. At t = 0 it is already
moving toward the right arm. Three fixed, very bouncy orange rails, 60 mm tall, form a U-shaped pen open toward the
right arm. The far rail is on the left arm's side, and two long side rails run along it: the upper rail on the +y side
and the lower rail on the -y side. Inside the pen stands a swinging gate: an amber leaf 0.13 m long, 55 mm tall and 12
mm thick that turns about a vertical hinge at one end. Its lower edge is just above the table, so the puck cannot pass
beneath it. A raised orange-red handle block (32 x 24 x 24 mm) sits on the leaf's free end. A weak torsional spring
pulls the gate back toward its rest orientation, in which the leaf runs along the world y axis, and the hinge is nearly
frictionless. A short, non-bouncy backstop wall (0.14 m wide, 60 mm tall) stands outside the pen, beyond the goal line
on the right arm's side. Only the puck moves at the start; the gate moves when pushed and springs back when let go. The
table top is the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the left hand grips the gate's handle with both fingers and swings the gate well open toward +x and from then
on keeps holding the handle with the gate well away from its rest position (either way) whenever a later step is judged;
the right paddle hits the puck so that it runs deep into the pen; while the puck runs round, the left hand swings the
gate the other way, so that it stands open toward -x at the moment the puck hits the upper (+y) rail; the right paddle
intercepts the returning puck; finally the puck crosses the goal line in front of the backstop (x = 0.43, around y =
0.15), not touching the paddle, with the hand still holding the gate deflected well away from its rest position.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 35 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The gripper fingers and finger pads of either arm may touch the puck and the
  gate's swinging part (leaf and handle). They must not touch the gate's base, the rails, the backstop, the table or the
  robot pedestals. The right paddle, including its adapter, may touch only the puck, not the gate, rails, backstop or
  table. No other robot part, such as the hand or the arm links, may touch anything. The two arms and the paddle must
  never touch each other, and the paddle must not touch its own arm. In every task an arm never touches itself, no robot
  part touches the table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what
  the task allows, and no contact presses deep into anything;
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
  horizon (35 s, 3500 rows).

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
