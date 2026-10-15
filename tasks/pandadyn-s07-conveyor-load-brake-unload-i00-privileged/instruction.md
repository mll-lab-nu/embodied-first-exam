# Panda Dynamic Scenes · Conveyor pick, carriage load, braking and dock unload (S07) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** At the start a small cube (the part) rides along a powered roller conveyor, and a shallow carriage is already coasting along a frictionless rail. Grasp the part with the gripper while it is moving and lift it; set it on the moving carriage and let go while the carriage is still moving; then grip the carriage (it has a vertical handle) and bring it to a stop with the part still on it; grasp the part again and lift it off the carriage; finally set it down in a fixed dock and leave it there at rest.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x), with no tool: the bare Panda hand and its two parallel fingers. The task's tool frame is the Panda TCP (between the fingertips). At the start the TCP is at (-0.13, -0.11, 0.21) with orientation wxyz (0, 1, 0, 0): the gripper points straight down, the hand's x axis along world x, the fingers closing along world y; the fingers start 0.048 m apart (each at 0.024 m). The action's last element is the total finger opening (0 to 0.08 m); in this task the gripper's motion is not time-synchronised with the arm joints' trajectory.

An orange cube, the part (36 mm edge), lies on a roller conveyor (20 grey rollers of 6 mm radius and 0.136 m length, axes along x, 12.5 mm apart, on a dark frame) whose powered rollers carry it along +y toward the conveyor's end from t = 0; if nothing takes it, it reaches the end after a few seconds and falls off. A blue carriage (a shallow tray 0.17 m along x by 0.11 m inside, 9 mm walls, with a vertical blue handle 28 mm x 36 mm x 76 mm outside its +x wall) runs on a straight rail along y; it has no motor and no friction and is already coasting along +y at t = 0, and it keeps going until something stops it or it reaches the end of its rail. A blue open box, the dock (0.13 m x 0.12 m inside, 0.04 m deep), stands fixed just above the table. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Conveyor: centre (-0.13, -0.10, 0.1); roller j (j = 0..19) at y = -0.10 + (j - 9.5) x 0.0125 m (from -0.219 to 0.019), axis height z = 0.108 (tops at z = 0.114), friction 0.9; each roller is velocity-driven at -`incoming_speed`/0.006 rad/s about +x (surface speed `incoming_speed` = 0.08 m/s toward +y), drive damping 0.012, torque limit 0.008 N m, and starts already spinning at that rate. Frame box 0.16 x 0.28 x 0.024 m (z 0.053..0.077). Part: box half-extent 0.018 m, mass `object_mass` = 0.035 kg, friction 0.65, restitution 0.05; at reset at (-0.13, -0.16, 0.133) with velocity (0, `incoming_speed`, 0) = (0, 0.08, 0) m/s. Carriage: articulation with rail centre (0.12, 0, 0.11), prismatic along world +y, limits +-0.42 m, joint friction 0, damping 0, no drive; moving link mass 0.18 kg, tray inner half-size (0.085, 0.055) m, walls 9 mm high, floor top at the link origin (z = 0.11), friction 0.4; handle box 0.028 x 0.036 x 0.076 m centred at link (0.11, 0, 0.035). At reset the carriage starts at q0 = -0.16 + U(-0.01, 0.01) m (the only random draw) with velocity `fixture_speed` = 0.035 m/s along +y, and coasts at that speed; unbraked it reaches its +0.42 m limit after about (0.42 - q0)/0.035 = 16.6 s. Rail base: box 0.036 x 0.48 x 0.024 m at z 0.048..0.072 on a pedestal. Dock: static open box centred at (0.20, -0.23), floor top at z = 0.015, inner half-size (0.065, 0.06) m, walls 0.04 m high and 5 mm thick, friction 0.4, restitution 0.03. Finger friction 1.2 static / 1.0 dynamic. Table friction `table_friction` = 0.08. No goal flags are announced.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.08, `fixture_speed` = 0.035, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3.

**Goal geometry.** Lift height: the part's centre above world z = 0.20 m (moving_acquisition and payload_regrasp). Spill height: world z = 0.09 m (handle_braking and payload_regrasp). The delivery target is the dock's centre (a physical fixture; coordinates in privileged details).

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_acquisition**: at some step both fingers (left and right) touch the part while the part moves faster than 0.025 m/s; then, with both fingers still touching it, the part's centre is above world z = 0.20 m.
2. **loaded_carriage_release**: the part touches the carriage's moving body, is not held by both fingers (at most one finger touches it), and the carriage moves along its rail faster than 0.025 m/s, all at the same step.
3. **handle_braking**: both fingers touch the carriage's moving body (any part of it counts: handle, walls or floor), the carriage moves slower than 0.012 m/s, the part's centre is within 0.07 m of the carriage centre along both carriage-frame x and y (the carriage frame is world-aligned), and the part touches the carriage, for 0.25 s without interruption.
4. **payload_regrasp**: both fingers touch the part, its centre is above world z = 0.20 m, and it does not touch the carriage.
5. **dock_deposit**: the part is not held by both fingers, touches the dock, its centre is within 0.04 m (horizontal distance) of the dock's centre, and it moves slower than 0.03 m/s, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during handle_braking or payload_regrasp, the part's centre drops below world z = 0.09 m (`payload_spill`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the two fingers may touch anything, and only the part and the carriage's moving body (its tray and handle). Every other contact of the robot is forbidden: the hand and arm links may touch nothing (not even the part or the carriage), and the fingers must not touch the conveyor (rollers or frame), the carriage's rail and base, the dock or the table. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/conveyor_load_brake_unload.py`).

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
