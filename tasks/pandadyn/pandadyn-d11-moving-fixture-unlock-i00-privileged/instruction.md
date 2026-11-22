# Panda Dynamic Scenes · Moving fixture unlock (D11) (privileged)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). The left gripper starts
around the handle of a free, hand-held fixture: a short channel with a ball inside, closed at its front by a
spring-loaded latch gate, with a square socket on its side above the latch's push button. The left arm must grip the
fixture and move it off its stand. While the fixture is still moving, the right arm must insert its peg into the socket,
press the latch button down with the peg until the gate opens, and then pull the peg back out while the left hand keeps
holding the fixture. The ball must then leave the fixture through its outlet while the outlet is lined up with the top
of a fixed inclined chute, run down the chute and come to rest in a basin at the chute's foot. The fixture must never be
dropped. The scene is one fixed instance: everything starts the same way after every reset. Things move by themselves
from the first control step on: the scene does not wait for the robot. You have the full simulator to develop with; you
hand in a trajectory of robot actions.

### Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x), no tool: its tool
frame is the gripper TCP (the point between the fingertips). It starts with the TCP at (-0.063, 0, 0.285), pointing
straight down (TCP x = world +x, fingers closing along world y). Its fingers start open 0.0175 m each (0.035 m total
aperture), straddling the fixture's 34 mm wide handle without gripping it. For this arm the finger servo is stiffer than
the default (finger PD gains kp 1875 N/m and kd 8 instead of 300 and 12; the force is still capped at 15 N per finger).
Its fingers also follow their own trajectory, not synchronized with the arm joints. panda-1 (right): base at (0.74,
0.22, 0), yaw pi (facing -x). Its tool is a square peg, 16 x 16 mm in section and 70 mm long, hanging straight down from
the tool frame: the tool frame is at the peg's top end and the tip is at tool-frame (0, 0, -0.07). A grey adapter on the
hand side joins the peg: a horizontal bar from the hand (0.035 m above the tool frame, tool x from -0.152 to -0.058), a
short post at tool x = -0.07 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the peg's back face (x
from -0.064 to -0.008, z from -0.012 to 0, along the peg's top 12 mm); peg and adapter form one rigid tool link. With
the peg vertical the hand points straight down and the peg's top is 0.12 m ahead of the gripper TCP along tool x and
0.04 m below it. Start: tool frame at (0.12, 0.15, 0.40), peg vertical, rotated 180 deg about z (tool x = world -x), so
the tip is at (0.12, 0.15, 0.33). On panda-1 the peg's adapter runs between the fingertips: closing that gripper to less
than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a collision with its own
tool (it starts fully open, at 0.08 m).

The fixture is a free rigid body, not attached to anything. At the start it rests level on a small orange stand plate
carried by two thin grey posts. It is a blue channel running along x: a flat floor between two side walls 56 mm apart
and 45 mm high. At its back (-x) end is a small handle block (16 mm along x, 34 mm wide, 28 mm tall). At its front (+x)
end the floor stops short of the walls' ends, leaving an exit opening. An orange spring-loaded latch closes this exit
with a 20 mm high gate standing just beyond the floor's end. The latch slides along the fixture's own vertical axis by
up to 26 mm. Its push button sits right under a square socket (28 mm opening, 30 mm tall, 16 mm walls) that is fixed to
the fixture beside the channel's front end on its +y side, above the wall. Pushing the button down lowers the gate below
the floor and opens the exit, and a spring pushes the latch back up when released. An orange ball (radius 16 mm) lies
loose on the channel floor behind the gate. Fixed in the scene are a grey inclined chute (an open channel, 66 mm wide
inside, 22 mm walls) running downhill toward +x, and at its lower end a blue open basin (0.13 m along x by 0.12 m
inside, 40 mm deep). Nothing moves by itself. The table top is the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the left gripper grips the fixture's body and moves it off its stand, keeping it moving; while it moves, the
right arm inserts its peg into the socket, presses the latch button down with the peg until the gate opens, and pulls
the peg back out, the left hand still holding the fixture; then the ball leaves through the outlet while the outlet is
lined up with the top of the chute (just above the chute's upper end, on its centre line, the fixture pointing down the
chute), runs down the chute and rests in the basin at its foot for about 0.7 s. The task fails at once if the fixture is
dropped, or if the ball leaves the fixture other than through the outlet lined up with the chute.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The fingers of either arm may touch the fixture body (channel, handle, socket)
  and the ball, but not the latch (gate, bar, button). The right peg tool (whole tool link, adapter included) may touch
  the fixture body, the latch and the ball. Nothing on either robot may touch the stand, the chute, the basin or the
  table. No other robot part (hand or arm links) may touch anything. The two arms and their tools may never touch each
  other, and no arm may touch itself. In every task an arm never touches itself, no robot part touches the table or the
  floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows, and no
  contact presses deep into anything;
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
