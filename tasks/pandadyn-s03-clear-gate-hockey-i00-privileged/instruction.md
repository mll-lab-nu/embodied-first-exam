# Panda Dynamic Scenes · Clear the blocker, recover and bank into the goal (S03) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A square puck slides toward the robot over an almost frictionless table at the start. Strike it with the paddle so that it hits a sliding blocker bar that obstructs the way to the goal and pushes it aside along its rail; let the puck come back toward the robot, strike it a second time, and make it bank off the long side rail and then cross the goal line while the blocker is still pushed aside.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue upright paddle: a box 12 mm thick (tool x) x 0.10 m wide (tool y, 2 x `tool_half`, `tool_half` = 0.05 m) x 50 mm tall (tool z), centred at the tool frame origin; its striking faces are normal to the tool x axis. A rigid dark-grey adapter behind the paddle (on its -x side) joins it to the hand: a horizontal bar 0.035 m above the tool origin (tool-frame x from -0.132 to -0.038) and a short vertical post at x = -0.05 reaching down to z = -0.005; both are part of the tool, and the adapter does not touch the paddle plate itself. The Panda TCP is at (-0.12, 0, 0.04) in the tool frame, so with the paddle upright the gripper points straight down. At the start the paddle is upright with tool axes aligned with the world axes (faces normal to world x), its centre at (0.03, -0.20, 0.045), so its lower edge is 0.02 m above the table.

An orange square puck (44 mm x 44 mm, 24 mm tall) slides over the table toward the robot (-x) at t = 0. The table surface and the puck are nearly frictionless and the puck is bouncy, so it keeps sliding and rebounds off walls. A blue blocker bar (140 mm long, 30 mm thick, 64 mm tall), set at an angle to the axes, stands on the table on a passive, unpowered sliding joint along the world y axis; it starts at one end of its travel, so it can only be pushed toward +y, and it obstructs the route to the goal. Three fixed orange walls, 70 mm tall, stand on the table: a long bank rail (0.34 m) running along x on one side of the play area, a return rail (0.20 m) running along y on the robot's side, and a backstop (0.20 m) running along y behind the goal line. The goal itself is not a physical object but a line segment on the table (see world goals). Nothing else moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Puck: box half-extents (0.022, 0.022, 0.012) m, mass `object_mass` = 0.035 kg, friction `table_friction` = 0.004 (the table also uses `table_friction`), restitution 0.65. At t = 0 it is at (0.23, y0, 0.0125) with velocity (-`incoming_speed`, 0, 0) = (-0.35, 0, 0) m/s; y0 ~ U(-0.14, -0.10) m drawn at reset (the only random draw). Blocker: articulation rooted at (0.29, 0.06, 0.032); prismatic joint along world +y, limits [0, 0.17] m, starts at q = 0 at rest, no drive, joint friction `blocker_friction` = 0.003, damping 0; the moving link is a box of half-extents (0.015, 0.07, 0.032) m yawed -0.6 rad about z (long axis along (0.565, 0.825)), bottom at z = 0, friction 0.05, restitution 0.65, density 250 kg/m^3 (about 0.067 kg); at q = 0 it spans about x 0.24 to 0.34 m and y -0.01 to 0.13 m. Return rail: static box 0.016 x 0.20 x 0.07 m centred at (-0.14, 0.035, 0.035), restitution 0.65. Bank rail: static box 0.34 x 0.016 x 0.07 m centred at (0.30, -0.23, 0.035), restitution 0.7. Backstop: static box 0.02 x 0.20 x 0.07 m centred at (0.52, 0.06, 0.035), restitution 0.05. Rails' friction 0.3. Paddle: `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.004, `tool_friction` = 0.3, `blocker_friction` = 0.003.

**Goal geometry.** Goal line: world x = 0.46 m for 0.005 m < y < 0.115 m (centre (0.46, 0.06), half-width 0.055 m), to be crossed in +x. Recover line: puck centre at world x < 0.16 m (recover_deflection). `goal_zone` = (0.08, -0.08, 0.012) is also announced at reset but no predicate uses it.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **first_strike**: the puck touches the paddle.
2. **clear_blocker**: during this phase the puck hits the blocker (puck-blocker contact), and the blocker is displaced more than 0.065 m along its rail from its start (joint position q > 0.065 m); the phase completes at the first step at which the hit has happened and the displacement exceeds 0.065 m.
3. **recover_deflection**: the puck's centre is at world x < 0.16 m (back on the robot's side) while the puck is not touching the paddle.
4. **second_strike**: the puck touches the paddle again.
5. **bank_and_goal**: after the second strike the puck touches the bank rail at least once, and afterwards its centre crosses the goal line, world x = 0.46 m, moving in +x (x <= 0.46 on one physics step and > 0.46 on the next) with |y - 0.06| < 0.055 m (y between 0.005 and 0.115 m), while it is not touching the paddle and the blocker is still displaced more than 0.065 m. This completes the task. A crossing of that segment in this phase without a bank-rail contact since the second strike, or while touching the paddle, or with the blocker at q <= 0.065 m fails the task (skipped_route).

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the paddle touches the blocker (`direct_blocker_shortcut`);
- during bank_and_goal, the puck crosses the goal segment (x = 0.46 m in +x, |y - 0.06| < 0.055 m) without having touched the bank rail in this phase, or while touching the paddle, or while the blocker's displacement is at most 0.065 m (`skipped_route`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the paddle (including its adapter) may touch anything, and it may touch only the puck: touching the blocker (which also fails the task as direct_blocker_shortcut), the return rail, the bank rail, the backstop or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the puck included. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/clear_gate_hockey.py`).

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

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
