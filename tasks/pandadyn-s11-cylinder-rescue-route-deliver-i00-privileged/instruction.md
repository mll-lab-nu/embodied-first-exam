# Panda Dynamic Scenes · Cylinder rescue, guide route and oriented delivery (S11) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A short round-ended cylinder is rolling along a raised lane when the episode starts and will run off its end. Intercept it in the open-sided tray the Panda holds. Bring it to rest in the tray with its long axis along the world's y axis. Put it into a gently sloping guide channel near the channel's entry, and let it travel out past the far end without the tray touching it at that moment. Catch it again in the tray at the exit, aligned and settled. Finally, deliver it lying along y into a pocket that slides back and forth on a rail, where it must rest while the pocket is moving.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a 'receiver': a square tray 0.14 m x 0.14 m inside (2 x `tool_half`), walls 30 mm high and 5 mm thick, floor 5 mm thick. The wall on the tool frame's -x side is missing (open side). The tool frame is the centre of the floor's top surface, z up out of the tray. The tray is side-mounted: an L-shaped adapter bar runs from the hand to the top of the tray's -y wall. In the tool frame the hand's TCP is at (-0.12, -0.12, +0.04), so the tray sits 12 cm ahead of, 12 cm to the side of and 4 cm below the TCP. At the start the tray is level (identity orientation; open side facing world -x), centre at (0.21, -0.18, 0.13).

The cylinder is orange and round-ended (a capsule), 76 mm long overall and 38 mm in diameter. At t = 0 it is rolling on its side, long axis across its direction of travel, along a raised, low-friction static lane (an orange slab on posts), and it rolls off the lane's open end within about the first second. Elsewhere, at a higher level, a static guide channel is mounted on posts. It is 0.09 m wide inside with 22 mm side walls, open at both ends, and slopes very slightly down from its entry end to its exit end. A short static wall stands just behind its entry end. A blue open box (the pocket: 0.15 m x 0.15 m inside, 0.06 m deep) is the moving link of a straight rail along the world's y axis. It is driven back and forth, slowly, by a force-limited drive. On its first outward stroke it runs into the side of the raised source lane and stays pressed against it until the drive reverses; it then moves back along the rail. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Cylinder: capsule of radius 0.019 m and half-length 0.019 m (overall 0.076 m), mass `object_mass` (0.035 kg), friction 0.35, restitution 0.05, long axis = its local x. At reset: centre (0.09 - `incoming_speed` x `preview`, -0.07 + dy, 0.1545) = (-0.225, -0.07 + dy, 0.1545), with dy ~ U(-0.004, 0.004) drawn at reset (first draw). The long axis is along world y, the velocity is (`incoming_speed`, 0, 0) = 0.35 m/s, and the angular velocity is (0, `incoming_speed`/0.019, 0) (rolling). It reaches the lane's +x end (x = 0.09) at about t = `preview` (0.9 s). Source lane `source_lane`: static slab 0.36 x 0.15 x 0.024 m centred at (-0.09, -0.07, 0.123), top z = 0.135, spanning x -0.27 to 0.09 and y -0.145 to 0.005, friction 0.1, with two posts. Guide `guide`: static channel whose floor's top runs from (-0.08, 0.18, 0.23) to (0.24, 0.18, 0.23 - `guide_drop`) = (0.24, 0.18, 0.225). The floor is 0.09 m wide and 10 mm thick, with side walls 8 mm thick and 22 mm tall centred at y = 0.18 +- 0.049, friction 0.16, on posts. Backstop `guide_entry_backstop`: static box 0.016 x 0.10 x 0.07 m centred at (-0.09, 0.18, 0.26). Pocket `pocket`: moving link of a prismatic fixture with rail origin (-0.05, -0.27, 0.07), axis +y, limits +-0.5 m. It is an open box (inner half 0.075, walls 0.06 m) whose floor's top surface is the link origin, mass 0.3 kg. At reset it is placed at q0 ~ U(-0.02, 0.02) (second draw) with velocity `fixture_speed`. It is then driven (PD, kp 80, kd 8, at most 8 N) to the target q0 + 0.20 sin((`fixture_speed`/0.20) t), with target velocity `fixture_speed` cos((`fixture_speed`/0.20) t) (amplitude 0.20 m, peak 0.04 m/s, period 31.4 s). Its +y wall (outer face at the pocket's centre + 0.08 m, top at z = 0.13) meets the source lane's -y face (y = -0.145, slab bottom at z = 0.111) at q of about 0.045 m. In an idle run (seed 0) the pocket stalled there with v = 0 from t of about 1.5 s to about 14.3 s, then followed its target back towards -y. Its speed exceeds 0.5 x `fixture_speed` = 0.02 m/s only before about 1.4 s and from about 14.3 s until about 20.9 s (|cos| > 0.5); the last fast stretch of the oscillation starts after the 25 s horizon. Receiver: `tool_half` 0.07, wall height 0.03, `tool_mass` 0.2 kg, `tool_friction` 0.3. Table friction `table_friction` (0.08). `target` = (-0.08, 0.18, 0.23) is the guide's entry point; `goal_axis` = (0, 1, 0).

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.9, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `guide_drop` = 0.005.

**Goal geometry.** Required orientation: the cylinder's long axis along world y (either sign) within 0.2 rad. Guide test lines: world x = 0.02 (entry contact must occur at x below it) and world x = 0.24 (exit beyond it). `goal_target` is announced at reset. It is not seeded, but it is the guide's entry point, so it is privileged mode only. The axis goal (`goal_axis`) is not exported as an observation.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **rolling_interception**: The cylinder is held by the tray and does not touch the source lane. 'Held' means: in contact with the tray within the last 25 ms; in the tray frame its centre has |x| and |y| < `tool_half` = 0.07 m; and its centre is between 0.013 m and 0.07 m above the tray floor.
2. **axial_alignment**: The cylinder is held (as above) and aligned, moving at less than 0.06 m/s relative to the tray (at its centre), for 0.3 s without interruption. Aligned means its long axis is within 0.2 rad of the world y axis, either way round: |y component of the axis| > cos 0.2.
3. **guide_rail_traverse**: During this phase the cylinder touches the guide while its centre is at world x < 0.02. Later, at a step when it does not touch the tray, its centre is at world x > 0.24, past the guide's exit end.
4. **exit_reception**: The cylinder is held by the tray (as above), aligned with world y within 0.2 rad, not touching the guide, and moving at less than 0.06 m/s relative to the tray, for 0.2 s without interruption.
5. **oriented_moving_delivery**: All of the following hold for 0.7 s without interruption. The cylinder touches the pocket and is not held by the tray. It lies inside the pocket: in the pocket's frame, for both x and y, |centre offset| + 0.019 + 0.019 x |axis component| < 0.075, i.e. the whole capsule is inside the inner walls. Its centre is more than 0.016 m above the pocket floor, and its top (centre height + 0.019 + 0.019 x |axis z component|) is below 0.063 m. Its long axis is within 0.2 rad of world y. The pocket moves faster than 0.5 x `fixture_speed` = 0.02 m/s. The cylinder moves at less than 0.06 m/s relative to the pocket. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- from axial_alignment onwards (after the interception), the cylinder touches the table (`cylinder_left_route_or_receiver`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the tray may touch the cylinder, and the tray may touch nothing but the cylinder: not the source lane, guide, backstop, pocket or its rail, and not the table. No other part of the robot (fingers, hand, links, base) may touch anything. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/cylinder_rescue_route_deliver.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 30 % (acceleration) and 2 % (jerk) of the Panda's joint
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
