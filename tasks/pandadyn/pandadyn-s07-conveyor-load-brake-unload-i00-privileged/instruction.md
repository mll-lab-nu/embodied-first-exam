# Panda Dynamic Scenes · Conveyor pick, carriage load, braking and dock unload (S07) (privileged)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). At the start a small cube (the part) rides along a powered roller conveyor,
and a shallow carriage is already coasting along a frictionless rail. Grasp the part with the gripper while it is moving
and lift it; set it on the moving carriage and let go while the carriage is still moving; then grip the carriage's
vertical handle with both fingers and bring the carriage to a stop, with the part still on it, before it reaches the end
of its rail; grasp the part again and lift it off the carriage; finally set it down in a fixed dock and leave it there
at rest. The scene is one fixed instance: everything starts the same way after every reset. Things move by themselves
from the first control step on: the scene does not wait for the robot. You have the full simulator to develop with; you
hand in a trajectory of robot actions.

### Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x), with no tool: the bare Panda hand and its two parallel fingers. The
task's tool frame is the Panda TCP (between the fingertips). At the start the TCP is at (-0.13, -0.11, 0.21) with
orientation wxyz (0, 1, 0, 0): the gripper points straight down, the hand's x axis along world x, the fingers closing
along world y; the fingers start 0.048 m apart (each at 0.024 m). The action's last element is the total finger opening
(0 to 0.08 m); in this task the gripper's motion is not time-synchronised with the arm joints' trajectory.

An orange cube, the part (36 mm edge), lies on a roller conveyor (20 grey rollers of 6 mm radius and 0.136 m length,
axes along x, 12.5 mm apart, on a dark frame) whose powered rollers carry it along +y toward the conveyor's end from t =
0; if nothing takes it, it reaches the end after a few seconds and falls off. A blue carriage (a shallow tray 0.17 m
along x by 0.11 m inside, 9 mm walls, with a vertical blue handle 28 mm x 36 mm x 76 mm outside its +x wall) runs on a
straight rail along y; it has no motor and no friction and is already coasting along +y at t = 0, and it keeps going
until something stops it or it reaches the end of its rail. A blue open box, the dock (0.13 m x 0.12 m inside, 0.04 m
deep), stands fixed just above the table. The table top is the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: both fingers grasp the part while it still rides the conveyor and lift it (above about 0.2 m); the part is set
on the moving carriage and let go while the carriage still moves; then both fingers grip the carriage's vertical handle
(the handle only) and bring the carriage to a stop, the part still on it, before it reaches the end of its rail; the
part is grasped again and lifted off the carriage (above about 0.2 m); finally it is set down in the dock and left there
at rest for about half a second. The task fails at once if the carriage reaches an end of its rail before it is stopped,
or if the part falls off during the braking and the regrasp.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the two fingers may touch anything, and only the part and the carriage's
  moving body (its tray and handle). Every other contact of the robot is forbidden: the hand and arm links may touch
  nothing (not even the part or the carriage), and the fingers must not touch the conveyor (rollers or frame), the
  carriage's rail and base, the dock or the table. In every task the arm never touches itself, no robot part touches the
  table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows,
  and no contact presses deep into anything;
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
