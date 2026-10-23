# Panda Dynamic Scenes · Plate catch, transport and release (S02) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A ball is tossed up next to the robot when the episode starts. Catch it on the flat, rimless plate the Panda holds, settle it at the plate's centre, carry it through two waypoints (a turn) without letting it roll off, settle it again, then tip it off the plate into a basin that slides back and forth along a rail, where it must come to rest while the basin is moving.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x. Its hand carries a rigid square plate with no rim, 0.22 m x 0.22 m at this instance (2 x `tool_half`), 8 mm thick, mounted under the hand by a fixed adapter; the tool frame is the centre of the plate's top surface (z up out of the plate). At the start the plate is level, its centre at (0.01, -0.055, 0.22). The tool's adapter runs between the gripper's fingertips: closing the gripper to less than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as `self_collision` (the gripper starts fully open, at 0.08 m).

A small orange ball (radius 18 mm) is thrown upwards beside the plate at the start and falls back down. A basin (an open box, 0.15 m x 0.15 m inside, 0.06 m deep) slides back and forth along a straight rail on the table (along the world's y axis), driven the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Ball: radius `radius`, mass `object_mass`, restitution `restitution`; released at t = 0 from (0.06, y0, 0.42) m with velocity (`incoming_speed`, 0, `incoming_vertical_speed`) m/s, y0 drawn per instance in [-0.04, 0.01] m. Basin: the moving link of a prismatic fixture whose rail centre is (0.29, -0.23, 0.045), axis +y, limits +-0.5 m; at reset it starts at a seeded offset q0 in [-0.04, 0] m and is then driven (PD, kp 80, kd 8, at most 8 N) to the target q0 + 0.20 sin((`fixture_speed` / 0.20) t) with the target velocity `fixture_speed` cos((`fixture_speed` / 0.20) t): an oscillation of 0.20 m amplitude, peak speed `fixture_speed` (0.04 m/s at this instance, period 2 pi x 0.20 / `fixture_speed` = 31.4 s), so its speed exceeds 0.02 m/s only while |cos| > 0.5 (at this instance t < 5.2 s and 10.5 s < t < 20.9 s). Plate: `tool_half`, `tool_mass`, `tool_friction`; table friction `table_friction`.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.11, `radius` = 0.018, `incoming_speed` = 0.08, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `incoming_vertical_speed` = 1.8.

**Goal geometry.** Waypoint A (0.00, 0.08, 0.27) and waypoint B (0.18, 0.13, 0.25), for the plate's centre. `goal_target` (the catch point, at the ball's seeded y0) and `goal_waypoints` are announced at reset in s.state(); `goal_target` reveals the ball's seeded start: privileged mode only.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **airborne_plate_catch**: the ball has flown free (touching nothing) for more than 0.05 s and then touches the plate.
2. **recenter**: the ball rests on the plate (in contact within the last 25 ms; in the plate's frame its centre is at least 2.5 cm inside every edge and between radius - 4 mm and radius + 15 mm above the top surface), within 3.5 cm of the plate's centre, moving at less than 0.08 m/s relative to the plate, for 0.3 s without interruption.
3. **turning_transport**: with the ball resting on the plate, the plate's centre (the tool frame) comes within 2.5 cm of waypoint A = (0.00, 0.08, 0.27), then within 2.5 cm of waypoint B = (0.18, 0.13, 0.25), in this order.
4. **rolling_recovery**: the ball rests on the plate within 3.5 cm of its centre, moving at less than 0.04 m/s relative to the plate, for 0.4 s without interruption.
5. **moving_basin_release**: the ball is inside the basin (its centre at least 0.45 x radius inside the basin's inner walls, resting on the basin, below its rim, moving at less than 0.09 m/s relative to the basin), not touching the plate, while the basin moves at more than 0.02 m/s, for 0.7 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during recenter, turning_transport or rolling_recovery, the ball's centre leaves the plate's square in the plate's frame (|x| or |y| > half the plate's width) or drops more than 1 cm below the plate's top surface (`rimless_plate_spill`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the plate may touch the ball, and the plate may touch nothing but the ball (not the basin or its rail, not the table). No other part of the robot, the fingers included, may touch anything. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/plate_catch_transport_release.py`).

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
