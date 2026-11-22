# Panda Dynamic Scenes · Load a coasting cart, throw the switch, recover the part (S08) (privileged)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). A small cube (the part) rides a powered roller conveyor, and an unpowered
cart is already coasting along a straight channel towards a passive hinged switch that splits the track into two
diagonal branches. Grasp the part with both fingers while it is still moving and lift it, drop it into the moving cart
without stopping the cart, which must keep coasting until the switch is set, then push the switch with a finger so that
it will steer the cart into the branch selected for this instance (one of the two sides, drawn per instance and given
under Goal geometry) before the cart reaches it. The cart must then be deflected by the switch into that branch.
Finally, grasp the part again, lift it out of the cart and hold it up before the cart runs too far down the branch. The
scene is one fixed instance: everything starts the same way after every reset. Things move by themselves from the first
control step on: the scene does not wait for the robot. You have the full simulator to develop with; you hand in a
trajectory of robot actions.

### Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame
(the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand
along the fingers. At the start the TCP is at (-0.13, -0.13, 0.20) with the gripper pointing straight down (orientation
wxyz (0, 1, 0, 0)). The fingers close along world y and start fully open (aperture 0.08 m; the action's last component
is the total aperture, 0 to 0.08 m). In this task the finger motion is not time-synchronised with the arm joints, so a
finger command does not stretch the arm motion. The finger servo damping is also raised to 8.

The part is an orange cube with 36 mm edges. It sits on a short roller conveyor of 20 thin grey rollers, which spin by
themselves and carry it towards the conveyor's open end; past that end it drops to the table. The cart is a small blue
open tray, 0.13 m x 0.11 m inside with 12 mm walls. It rides on four free orange ball bearings (radius 18 mm) and has no
motor: it is already coasting at t = 0 and keeps rolling straight. It first passes between two parallel static walls (an
entry channel, 16 mm thick and 5 cm tall), then meets the switch. The switch is a passive vertical blade (12 mm thick,
0.14 m long, 45 mm tall) on a vertical hinge with joint friction and no spring, and it carries a small knob on top of
its free end. At the start the blade points straight back along the cart's path, edge-on to the incoming cart. Beyond
the switch there are two diagonal branches, one on each side. Each has a static guide rail (16 mm thick, 0.24 m long, 5
cm tall) and, at its far end, a shallow static open box (dock, 0.14 m x 0.12 m inside, 18 mm walls). The table top is
the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: both fingers grip the part while it still rides the conveyor and lift it (above about 0.2 m); it is dropped
into the moving cart without stopping the cart; before the cart reaches the switch, a finger pushes the switch clearly
over toward the selected branch, at this instance branch -1, the diagonal branch on the -x side, nearer the robot's base
(nothing in the images marks it), where it comes to rest; the cart is deflected by the switch into that branch; finally
both fingers grip the part again and hold it up, well above the cart and clear of it, for about half a second, before
the cart runs far down the branch. The task fails at once if the cart reaches the switch before it is set, if the cart
stalls before then (it must keep coasting), if the part spills from the cart before the branch, or if the cart runs out
of reach before the part is recovered.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. No tool is mounted. Only the finger links (fingers and finger pads) may touch
  anything. They may touch the part, the cart's tray and its bearing balls (all free objects), and the moving blade/knob
  of the switch. The fingers may not touch the conveyor (its rollers or its base), the switch base, the entry walls,
  branch rails, docks or the table. No other part of the robot (hand, links, base) may touch anything. Finger-to-finger
  contact is allowed. In every task the arm never touches itself, no robot part touches the table or the floor, a robot
  part other than an allowed one touches nothing, a tool touches only what the task allows, and no contact presses deep
  into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`: it holds `task` and `actions`, a
(T, 8) float array of at most 4,500 rows (one per control step); anything else (another shape, NaN, more rows, a file
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
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 8 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 8) rows executed since the last reset: the trajectory of this episode
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
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger
  moves at most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are
  executed, and the trajectory records the clipped row.
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
