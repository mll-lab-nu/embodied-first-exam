# Panda Dynamic Scenes · Swinging load transit and dock (S10) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A carrier rests on two small ledges between the gripper's open fingers. It is a short bar with a pendulum (a rod ending in a ball) hanging from a hinge under it, and the pendulum is already swinging. Grip the bar with both fingers and damp the swing. Carry the carrier, still gripped, through two waypoints without letting the carrier or its pendulum touch a block obstacle, and damp the residual swing again. Finally lower it until the pendulum's ball rests centred in a dock, with the swing settled and the bar still gripped.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame (the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand along the fingers. At the start the TCP is at (-0.03, -0.14, 0.36), exactly at the carrier bar's centre, with the gripper pointing straight down (orientation wxyz (0, 1, 0, 0)). The fingers close along world y and start partly open, at 0.016 m each (aperture 0.032 m), straddling the 30 mm wide bar. The action's last component is the total aperture, 0 to 0.08 m. In this task the finger servo is stiffer (kp 800, kd 8), and finger motion is not time-synchronised with the arm joints.

The carrier is a free rigid assembly, not attached to the robot or the scene. Its bar is blue-grey, 0.12 m long (along world x at the start), 0.03 m wide and 18 mm thick. A pendulum hangs from a hinge just under the bar's middle: a grey 12 mm square rod, 0.15 m long (`length`), ending in an orange ball (the bob) of radius 22 mm. The hinge lets the pendulum swing only in the vertical plane along the bar's length, with almost no friction. At t = 0 the bar rests on two thin static ledges (on posts), and the pendulum is let go from an angle, so it is already swinging. A static orange block obstacle (0.08 m x 0.12 m x 0.11 m tall) stands on the table. A static blue open box (the dock: 0.104 m x 0.10 m inside, walls 55 mm high) is placed low over the table. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Carrier: free articulation whose root link `carrier` (the bar, box 0.12 x 0.03 x 0.018 m, mass 0.055 kg) starts with its centre at (-0.03, -0.14, 0.36), level, resting on the two ledges. The ledges `reset_handle_stand_-1/1` are static plates 0.008 x 0.09 x 0.006 m centred at (-0.083, -0.177, 0.348) and (0.023, -0.177, 0.348), with posts to the table. The pendulum link `load` (mass 0.06 kg) hangs from a revolute hinge 0.012 m below the bar's centre (z = 0.348 at the start). The hinge axis is the bar's y axis (world y at the start), limits +-1.3 rad, joint friction 0.00001, damping 0.00003. The rod is 0.012 x 0.012 x `length` (0.15 m); the bob (radius 0.022, friction 0.4) is centred `length` below the hinge. q is the hinge angle relative to the bar; q > 0 displaces the bob towards -x by `length` sin q. At reset q = `initial_angle` + e, with e ~ U(-0.02, 0.02) the only seeded draw (nominal 0.25 rad, i.e. the bob about 3.7 cm towards -x). The pendulum is released at rest. Idle, it keeps swinging at about +-0.25 rad with a period of about 1 s and practically no decay. Obstacle: static box 0.08 x 0.12 x 0.11 m centred at (0.08, 0, 0.055). Dock: static open box (inner half 0.052 x 0.05, walls 0.055 m, 5 mm floor) whose floor top is at (0.07, 0.19, 0.015). The load_dock predicate tests the bob centre against the world point (0.07, 0.19) and the height z = 0.037. `goal` = (0.07, 0.19, `length` + 0.049) = (0.07, 0.19, 0.199), the bar-centre position when the bob rests in the dock. Waypoints are fixed (see world_goals_fixed).

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.06, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `length` = 0.15, `initial_angle` = 0.25.

**Goal geometry.** Waypoint A (-0.05, 0.04, 0.38) and waypoint B (0.0, 0.15, 0.37), each with radius 3.5 cm, for the bar's centre (announced at reset as `goal_waypoints`). Bar-centre floor: z = 0.16 m. Nothing goal-related is seeded. `goal_goal` (announced at reset) is fixed, but it gives the dock's position (the bar-centre point with the bob resting in the dock), so it is privileged mode only.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **grasp_settle_and_damp**: Both fingers grip the bar (bilateral grip: the left finger or its pad and the right finger or its pad both in contact with the bar at that step), and the swing is settled: the pendulum's hinge angle relative to the bar is less than 0.07 rad in magnitude and its hinge rate is below 0.18 rad/s. This must hold for 0.35 s without interruption.
2. **obstacle_transit**: With the bar gripped by both fingers, the bar's centre (the carrier's root origin) comes within 3.5 cm of waypoint A = (-0.05, 0.04, 0.38).
3. **turn_and_brake**: With the bar gripped by both fingers, the bar's centre comes within 3.5 cm of waypoint B = (0.0, 0.15, 0.37).
4. **residual_swing_cancel**: Bar gripped by both fingers and swing settled (|hinge angle| < 0.07 rad, |hinge rate| < 0.18 rad/s), for 0.5 s without interruption.
5. **load_dock**: Bar gripped by both fingers and swing settled (as above). The pendulum (rod or bob) has touched the dock within the last 10 ms. The bob's centre is within 3.5 cm horizontally of the dock's centre, and within 3 mm of the height at which the bob rests on the dock floor (bob centre 22 mm above the floor's top surface). All of this must hold for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time the carrier bar or the pendulum (rod or bob) touches the obstacle block (`obstacle_collision`);
- at any time the bar's centre drops below z = 0.16 m (with the bob resting in the dock and the bar held above it, the bar's centre is at about 0.199 m) (`carrier_grasp_lost`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** No tool is mounted. Only the finger links (fingers and finger pads) may touch anything, and only the carrier bar. Touching the pendulum (rod or bob) with a finger is forbidden. So is touching the ledges, the obstacle, the dock or the table. No other part of the robot (hand, links, base) may touch anything. The pendulum is expected to touch the dock; neither the bar nor the pendulum may touch the obstacle. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `s.robot_spec()["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task succeeds in both replays and both
end in the same state, else 0. Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.
The file holds `task` and `actions`, a (T, 8) float array of at most **4,500 rows** (one per control step);
anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0.

## Tooling (already installed; run `python` from any directory)
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
The tooling is deliberately thin: joint targets, kinematics and state. Catching, striking, carrying and timing are yours to
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/swinging_load_transit_dock.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `s.robot_spec()["servo"]` has the exact limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. There is no step budget: the time limit (`## Time limit`) is
  your only budget. A simulated episode ends at the latest at the task's horizon (25 s, 2500 rows).
- One `Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame
  is asked for and never moves anything. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
