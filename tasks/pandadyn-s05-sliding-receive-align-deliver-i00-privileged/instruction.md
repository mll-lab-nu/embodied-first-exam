# Panda Dynamic Scenes · Sliding receive, inertial staging and moving hand-off (S05) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** At the start a small cube slides along a raised, slippery lane toward its open end. Receive it in the shallow tray the Panda holds (open on one side) once it has left the lane and let it settle; then, keeping the tray level, make the cube slide inside the tray by moving the tray (tilting is not allowed) until it rests at a staging point; carry it through two waypoints; bring the tray to a pose at a fixed offset from a platform that slides slowly back and forth on a rail while matching its velocity; finally get the cube onto that platform, where it must ride along at rest without touching the tray.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue shallow square tray: floor 5 mm thick, inner 0.18 m x 0.18 m (2 x `tool_half`, `tool_half` = 0.09 m), walls 0.03 m high and 5 mm thick on its +x, +y and -y sides, open (no wall) on its -x side. The tool frame is the centre of the tray floor's top surface, z up, x and y along the walls. The tray hangs from a rigid side adapter (part of the tool): from the hand a horizontal bar at tool z = 0.035 runs from tool x = -0.12 to 0 at tool y = +0.12, then along y to y = 0.09, then a short 12 mm post goes down onto the middle of the +y wall (rising 6 mm above the wall and protruding 6 mm into the tray). The Panda TCP is at (-0.12, 0.12, 0.04) in the tool frame, so with the tray level the gripper points straight down, outside the tray beyond its -x/+y corner. At the start the tray is level (tool axes aligned with the world axes), its frame origin at (0.21, -0.18, 0.13).

A raised orange lane (a slab 0.36 m long along x, 0.11 m wide, on two posts) ends in the open toward +x. An orange cube (36 mm edge) slides along it toward that open end from t = 0; the lane and cube are slippery, so it leaves the lane end within the first second. A blue flat platform (0.28 m along x by 0.18 m, the receiver) rides on a straight rail along the world x axis and moves slowly back and forth along it for the whole episode, slowing to a stop at each end of its stroke. The tray's own surface is slippery too. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Lane: static box of half-extents (0.18, 0.055, 0.012) m centred at (-0.078, 0, 0.123) (top at z = 0.135, x -0.258..0.102, y -0.055..0.055), friction 0.015, two support posts. Cube ('block'): half-extent 0.018 m, mass `object_mass` = 0.035 kg, friction `friction` = 0.05, restitution 0.05. At t = 0 it is at (-0.17, y0, 0.1535), no rotation, with velocity (`incoming_speed`, 0, 0) = (0.58, 0, 0) m/s. Receiver: prismatic fixture with rail centre (`receiver_base_x`, 0.26, 0.13) = (-0.30, 0.26, 0.13), axis +x, limits +-0.5 m, moving link mass 0.3 kg; the platform is 0.28 x 0.18 x 0.02 m with its top surface centre at the link origin (z = 0.13). Drive law (oscillating): target q(t) = q0 + 0.20 sin((`fixture_speed`/0.20) t) = q0 + 0.20 sin(0.2 t) m, velocity target `fixture_speed` cos(0.2 t) (peak `fixture_speed` = 0.04 m/s), PD stiffness 80 N/m, damping 8 N s/m, force limit 8 N; at reset q = q0 and velocity = `fixture_speed`; period 31.4 s (moving +x until about 7.85 s, then -x until about 23.6 s). Random draws at reset, in this order: y0 ~ U(-0.01, 0.01) m, q0 ~ U(-0.02, 0.02) m. Tray: `tool_mass` = 0.2 kg, `tool_friction` = 0.05, restitution 0.05. Table friction `table_friction` = 0.08. Staging point flag `staging` = (`target_offset`, 0, 0.018) in the tray frame (not in the observation); `target_tolerance` = 0.014 m.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.09, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.58, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.05, `friction` = 0.05, `target_offset` = 0.03, `target_tolerance` = 0.014, `receiver_base_x` = -0.3.

**Goal geometry.** Receive line: cube centre at world x > 0.12 m (source_to_tray). Staging point in the tray frame: (0.03, 0) m, tolerance 0.014 m. Waypoint A (0.08, 0.13, 0.22) and waypoint B (0.19, 0.20, 0.22) for the tray's frame origin, tolerance 0.022 m (announced as `goal_waypoints`). Match pose: platform top-surface centre + (0.34, 0, 0.008) m, tolerance 0.012 m.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **source_to_tray**: the cube (which has touched the lane, as it starts on it) is supported by the tray (touched it within the last 25 ms), does not touch the lane, has its centre at world x > 0.12 m, and moves at less than 0.05 m/s relative to the tray, for 0.10 s without interruption. The cube's position in the tray frame at that moment is recorded as its received position.
2. **inertial_staging**: the tray must stay level throughout this phase: tilting its z axis more than 2.1 deg from world vertical fails the task (tilt_only_shortcut). (a) At some physics step of this phase the horizontal (world x-y) acceleration of the Panda TCP, taken as the 1 ms difference of its velocity, must exceed 1.1 x `friction` x g = 0.540 m/s^2; (b) at or after that step the cube's tray-frame x-y position must be more than 0.025 m away from its received position. After both, the cube must rest at the staging point: supported by the tray, its tray-frame x-y within `target_tolerance` = 0.014 m of (`target_offset`, 0) = (0.03, 0) m, moving at less than 0.045 m/s relative to the tray, for 0.3 s without interruption.
3. **transport_turn**: with the cube supported by the tray, the tray's frame origin comes within 0.022 m of waypoint A = (0.08, 0.13, 0.22), then within 0.022 m of waypoint B = (0.19, 0.20, 0.22), in this order.
4. **match_receiver**: at one physics step, all of: the cube is supported by the tray; the tray body's linear velocity differs from the platform's by less than 0.05 m/s; and the tray's frame origin is within 0.012 m of the point offset (0.34, 0, 0.008) m, in world axes, from the centre of the platform's top surface (0.34 m in +x and 8 mm above it).
5. **support_transfer**: the cube touches the platform, is not supported by the tray (no cube-tray contact within the last 25 ms), its centre is within 0.07 m of the platform's centre along both world x and world y, and its velocity differs from the platform's by less than 0.045 m/s, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during inertial_staging, the tray's z axis tilts more than 2.1 deg from world vertical (`tilt_only_shortcut`);
- during inertial_staging, transport_turn or match_receiver, the cube's centre in the tray frame is more than 0.015 m below the tray floor's top surface, or more than `tool_half` + 0.02 = 0.11 m from the tray centre along tray x or y (`spill`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the tray (including its adapter) may touch anything, and it may touch only the cube: touching the lane, the platform or its rail, or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the cube included. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/sliding_receive_align_deliver.py`).

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
